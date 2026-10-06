"""A replay of one collection can keep a checkpoint and resume from it
(REQ-TEST-159, signed by Keith 2026-10-06), from the first arrival a change
can affect - which is computed, never typed in (REQ-TEST-160).

A SLICE IS A REPLAY FROM A POINT, not a replay of some arrivals alone: a
row-count or drift check reads the previous supply, and filing depends on
what was promoted before. So a checkpoint is the WHOLE database as it stood
once arrival N-1 was fully processed, and a resume replays N onwards into a
copy of it.

A CHECKPOINT IS A DATABASE, copied inside the server with `CREATE DATABASE
... TEMPLATE` - no new tool, measured at 7.4s for a 55MB bootstrapped
database. PostgreSQL refuses that copy while anything is connected to the
source, so the replay lets go of every connection it holds first
(REQ-PIPE-158's release_connections, and the pass lock's pause). What the
checkpoint recorded about its inputs, its collection and N travels as the
database's own COMMENT, so a checkpoint cannot lose its description and the
list needs nothing but the server.

A RESUME LANDS IN A DATABASE OF ITS OWN (Keith, signing): the checkpoint
is copied again and the replay runs into the copy, which a person then points
MOTHMAN_SUPPLY_DSN at. The checkpoint is never written to, and nor is the
database the person had been using.

ONE COLLECTION AT A TIME: a bootstrap runs both side by side in separate
processes, so there is no instant when both are between arrivals and neither
is connected. And only on an asset declared synthetic.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from qa_tools.common import config_yaml, replay_inputs, supply_db

#: Every checkpoint database's name starts with this, and every resume's with
#: RESUME_PREFIX - so both can be found and cleared on a cluster that already
#: holds dozens of databases.
PREFIX = "mothman_ckpt_"
RESUME_PREFIX = "mothman_resume_"

#: How many checkpoints are kept per source database; taking one more drops
#: that database's oldest.
KEEP_ENV = "MOTHMAN_CHECKPOINTS_KEPT"
DEFAULT_KEEP = 3

COLLECTIONS = {"bdm": "civil-registration", "cp": "child-protection"}


class CheckpointRefused(RuntimeError):
    """Nothing was copied, replayed or changed - the message says why."""


def require_synthetic() -> None:
    """Criterion 6: never on an asset that has not declared itself synthetic."""
    from qa_tools.common.hierarchy import DATA_ASSET_YAML

    doc = config_yaml.parse(Path(DATA_ASSET_YAML).read_text()) or {}
    if not doc.get("synthetic"):
        raise CheckpointRefused(
            "checkpoints and resumes are for a synthetic history only, and this data asset "
            "does not declare `synthetic: true` - nothing was copied")


def keep() -> int:
    raw = os.environ.get(KEEP_ENV)
    if raw is None:
        return DEFAULT_KEEP
    try:
        value = int(raw)
    except ValueError as exc:
        raise CheckpointRefused(f"{KEEP_ENV} must be a whole number, got {raw!r}") from exc
    if value < 1:
        raise CheckpointRefused(f"{KEEP_ENV} must be at least 1, got {value}")
    return value


@dataclass(frozen=True)
class Checkpoint:
    name: str
    collection_id: str
    before: int
    taken_at: str
    source: str
    recorded: replay_inputs.Recorded
    pending_scripts: list[dict] = field(default_factory=list)

    def describe(self) -> str:
        return json.dumps({"collection_id": self.collection_id, "before": self.before,
                           "taken_at": self.taken_at, "source": self.source,
                           "recorded": self.recorded.to_json(),
                           "pending_scripts": self.pending_scripts})

    @classmethod
    def from_comment(cls, name: str, comment: str | None) -> "Checkpoint":
        try:
            doc = json.loads(comment or "")
            return cls(name=name, collection_id=doc["collection_id"], before=int(doc["before"]),
                       taken_at=doc["taken_at"], source=doc["source"],
                       recorded=replay_inputs.Recorded.from_json(doc["recorded"]),
                       pending_scripts=list(doc.get("pending_scripts", [])))
        except (ValueError, KeyError, TypeError):
            # UNREADABLE IS NOT FATAL TO LISTING, and resolves to "replay from
            # the first arrival" if resumed - the safe direction (REQ-TEST-160).
            return cls(name=name, collection_id="", before=0, taken_at="", source="",
                       recorded=replay_inputs.Recorded(collection_id="", readable=False))


def _with_dbname(dsn: str, dbname: str) -> str:
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    info["dbname"] = dbname
    return psycopg.conninfo.make_conninfo(**info)


def _dbname(dsn: str) -> str:
    return psycopg.conninfo.conninfo_to_dict(dsn)["dbname"]


def _admin(dsn: str | None = None):
    """A connection to the server's maintenance database, for creating and
    dropping whole databases - never one of the databases being copied."""
    return psycopg.connect(_with_dbname(dsn or supply_db.supply_db_dsn(), "postgres"),
                           autocommit=True, application_name="mothman:checkpoints")


def _copy(admin, source: str, target: str) -> None:
    try:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
            sql.Identifier(target), sql.Identifier(source)))
    except psycopg.errors.ObjectInUse as exc:
        who = admin.execute(
            "SELECT coalesce(nullif(application_name, ''), '(unnamed)') FROM pg_stat_activity "
            "WHERE datname = %s", [source]).fetchall()
        raise CheckpointRefused(
            f"{source!r} cannot be copied while anything is connected to it - connected now: "
            f"{', '.join(sorted({w[0] for w in who})) or 'nothing, by the time it was asked'}"
        ) from exc


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def save(collection_id: str, before: int, *, recorded: replay_inputs.Recorded,
         pending_scripts: list[dict], dsn: str | None = None) -> Checkpoint:
    """Criterion 1: copy the database as it stands now - once arrival
    before-1 is fully processed - with what it was made from. The caller has
    let go of the pass lock; every pooled connection is closed here."""
    require_synthetic()
    source = _dbname(dsn or supply_db.supply_db_dsn())
    short = next(k for k, v in COLLECTIONS.items() if v == collection_id)
    name = f"{PREFIX}{short}_{before:03d}_{_stamp()}"
    supply_db.release_connections()
    cp = Checkpoint(name=name, collection_id=collection_id, before=before,
                    taken_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    source=source, recorded=recorded, pending_scripts=pending_scripts)
    with _admin(dsn) as admin:
        _copy(admin, source, name)
        admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(
            sql.Identifier(name), sql.Literal(cp.describe())))
    prune(keep(), dsn=dsn, source=source)
    return cp


def listed(dsn: str | None = None, prefix: str = PREFIX) -> list[Checkpoint]:
    """Criterion 7: every checkpoint on this server, oldest first."""
    with _admin(dsn) as admin:
        rows = admin.execute(
            "SELECT datname, shobj_description(oid, 'pg_database') FROM pg_database "
            "WHERE datname LIKE %s ORDER BY datname", [prefix.replace("_", r"\_") + "%"]).fetchall()
    found = [Checkpoint.from_comment(name, comment) for name, comment in rows]
    return sorted(found, key=lambda c: (c.taken_at, c.name))


def find(name: str, dsn: str | None = None) -> Checkpoint:
    for cp in listed(dsn):
        if cp.name == name:
            return cp
    raise CheckpointRefused(f"there is no checkpoint called {name!r} - "
                            "`mothman pipeline checkpoint list` shows those there are")


def delete(name: str, dsn: str | None = None) -> None:
    """Criterion 7. Only a checkpoint or a resume's database - never anything
    else, whatever name is asked for."""
    if not name.startswith((PREFIX, RESUME_PREFIX)):
        raise CheckpointRefused(f"{name!r} is not a checkpoint or a resume's database - "
                                "nothing was deleted")
    with _admin(dsn) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
            sql.Identifier(name)))


def prune(keep_n: int, dsn: str | None = None, *, source: str) -> list[str]:
    """Drop the oldest checkpoints OF ONE SOURCE DATABASE beyond `keep_n`;
    returns what was dropped. Per source, because a cluster is shared - a
    test's scratch database taking a checkpoint must never prune a person's."""
    mine = [cp for cp in listed(dsn) if cp.source == source]
    gone = [cp.name for cp in mine[:-keep_n]] if keep_n else []
    for name in gone:
        delete(name, dsn)
    return gone


def copy_for_resume(cp: Checkpoint, dsn: str | None = None) -> str:
    """Criterion 2: a database of the resume's own, copied from the
    checkpoint, which is left unchanged. Returns its DSN."""
    short = next(k for k, v in COLLECTIONS.items() if v == cp.collection_id)
    name = f"{RESUME_PREFIX}{short}_{cp.before:03d}_{_stamp()}"
    with _admin(dsn) as admin:
        _copy(admin, cp.name, name)
    return _with_dbname(dsn or supply_db.supply_db_dsn(), name)


def snapped(arrivals: list, before: int) -> int:
    """`before`, moved back to where its group begins - a delivery's files
    are staged together and a zip's are filed together (arrival_lifecycle.
    arriving_with), so a checkpoint inside one would hold half of it.
    Earlier is the safe direction."""
    if not 2 <= before <= len(arrivals):
        raise CheckpointRefused(
            f"a checkpoint before arrival {before} is not possible - this collection has "
            f"{len(arrivals)} arrivals, and the first must be processed before one is taken "
            f"(choose 2 to {len(arrivals)})")
    group = [arrivals[before - 1]]

    def together(a) -> bool:
        return any(a.received_at == g.received_at
                   or getattr(a, "delivery_name", None) == getattr(g, "delivery_name", object())
                   for g in group)
    while before > 1 and together(arrivals[before - 2]):
        before -= 1
        group.append(arrivals[before - 1])
    if before < 2:
        raise CheckpointRefused(
            "every arrival before that one belongs with it - the same delivery or the same "
            "receipt instant - so there is no point between them to take a checkpoint at")
    return before


def pending_of(player) -> list[dict]:
    """The scripted decisions a replay has not played yet, as data the
    checkpoint can carry: a resume must not play one twice."""
    return [asdict(s) for s in (player.pending if player is not None else [])]


def taking_checkpoint(collection_id: str, before: int, pause, on_taken=None):
    """An `after_each` for process_all that takes the checkpoint once arrival
    before-1 is processed, with the pass lock paused around the copy."""
    def after_each(position, arrival, player) -> None:
        if position != before - 1:
            return
        with pause():
            cp = save(collection_id, before, recorded=replay_inputs.Recorded.now(collection_id),
                      pending_scripts=pending_of(player))
        if on_taken is not None:
            on_taken(cp)
    return after_each
