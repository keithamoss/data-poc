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

EACH ASSET SEES ITS OWN ONLY (REQ-PIPE-365 criterion 2). Both assets'
databases share one server, so both assets' checkpoints do too; every name
carries the asset (mothman_ckpt_<asset>_..., mothman_resume_<asset>_...), and
listing, finding, deleting and pruning read the selected asset's names alone.

BY THE NAME'S SHAPE, NEVER BY A PREFIX ALONE (post-build-review #347): an
asset's name has no underscore (assets.NAME_PATTERN), so one asset's names
never match another's. A copy made BEFORE the split is
mothman_ckpt_<short>_<NNN>_<stamp> - one segment fewer - so an asset named
like a collection short (an asset "cp") can never take it for its own. Those
belong to no asset: listed apart, deletable from either asset, never pruned.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from qa_tools.common import supply_db
from bootstrap import replay_inputs

#: Every checkpoint database's name starts with this, and every resume's with
#: RESUME_PREFIX - so both can be found and cleared on a cluster that already
#: holds dozens of databases.
PREFIX = "mothman_ckpt_"
RESUME_PREFIX = "mothman_resume_"

#: How many checkpoints are kept per source database; taking one more drops
#: that database's oldest.
KEEP_ENV = "MOTHMAN_CHECKPOINTS_KEPT"
DEFAULT_KEEP = 3

# Which collection a checkpoint is of, and the short name its database is
# named with, come from the registry (REQ-PIPE-240).


class CheckpointRefused(RuntimeError):
    """Nothing was copied, replayed or changed - the message says why."""


def require_synthetic() -> None:
    """Criterion 6: never on an asset that has not declared itself synthetic -
    asked of the one reader (REQ-PIPE-382 criterion 7), which reads `is True`,
    NOT TRUTHINESS: a string "false" is truthy (post-build-review #131 D9)."""
    from asset_model import asset_time

    if not asset_time.declared_synthetic():
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


#: PostgreSQL's identifier limit: a longer database name is truncated
#: silently, which would lose the stamp that tells two checkpoints apart.
_MAX_NAME = 63


def _asset() -> str:
    """The selected asset - refused, as every reader refuses, without one."""
    from asset_model import assets

    return assets.selected().name


def _own(prefix: str, asset: str | None = None) -> str:
    """The name prefix of the selected asset's checkpoints (PREFIX) or
    resumes (RESUME_PREFIX)."""
    return f"{prefix}{asset or _asset()}_"


#: The stamp and arrival number every name ends with.
_TAIL = r"_\d{3}_\d{14}"


def _is_own(name: str, prefix: str, asset: str | None = None) -> bool:
    """`name` is one of the asset's checkpoints (PREFIX) or resumes
    (RESUME_PREFIX): <prefix><asset>_<short>_<NNN>_<stamp>."""
    return re.fullmatch(re.escape(_own(prefix, asset)) + r".+" + _TAIL, name) is not None


def is_legacy(name: str) -> bool:
    """A checkpoint or resume made before the asset split,
    <prefix><short>_<NNN>_<stamp>, which belongs to no asset (#347)."""
    return any(re.fullmatch(re.escape(prefix) + r"[^_]+" + _TAIL, name)
               for prefix in (PREFIX, RESUME_PREFIX))


def _named_for(prefix: str, short: str, before: int) -> str:
    name = f"{_own(prefix)}{short}_{before:03d}_{_stamp()}"
    if len(name) > _MAX_NAME:
        raise CheckpointRefused(
            f"a checkpoint of this asset would be named {name!r}, longer than PostgreSQL's "
            f"{_MAX_NAME} characters - nothing was copied")
    return name


def require_names_fit(short: str, before: int) -> None:
    """Refuse UP FRONT (post-build-review #346) a checkpoint, or a resume of
    one, whose database name would pass PostgreSQL's limit - before minutes
    of replay, not at the copy. The resume's prefix is the longer, so it is
    the one measured."""
    for prefix in (PREFIX, RESUME_PREFIX):
        _named_for(prefix, short, before)


def _with_dbname(dsn: str, dbname: str) -> str:
    info = psycopg.conninfo.conninfo_to_dict(dsn)
    info["dbname"] = dbname
    return psycopg.conninfo.make_conninfo(**info)


def _dbname(dsn: str) -> str:
    return psycopg.conninfo.conninfo_to_dict(dsn)["dbname"]


def _admin(dsn: str | None = None):
    """A connection to the server's maintenance database, for creating and
    dropping whole databases - never one of the databases being copied.

    FOR THE SELECTED ASSET, AND REFUSED WITHOUT ONE (REQ-PIPE-363 criterion 6,
    REQ-PIPE-343 criterion 5): a checkpoint is a copy of one asset's supply
    database, so this connection is claimed for that asset before it opens,
    as supply_db.connect() claims its own."""
    from asset_model import assets

    assets.claim_for_connection(assets.selected().name)
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
    # THE SOURCE'S IDENTITY FIRST (post-build-review #334, the critic's M2):
    # the copy and the prune below go through the admin connection, which
    # checks nothing, so a process that lost its DSN would otherwise copy -
    # and prune the checkpoints of - another environment's supply_<asset>.
    supply_db.connect(dsn=dsn, read_only=True, label="mothman:checkpoints").close()
    from asset_model import collections

    short = collections.by_id(collection_id).short
    name = _named_for(PREFIX, short, before)
    supply_db.release_connections()
    # THE TOOL WORKERS' CONNECTIONS TOO (post-build-review #363): a copy is
    # refused while anything is connected to the source, and speed batch A's
    # persistent datacontract-cli worker (REQ-PIPE-431) holds a connection of
    # its own in another process, which release_connections cannot reach. A
    # stopped worker starts again on the next call that needs it.
    from qa_tools.common import datacontract_worker, dbt_worker

    datacontract_worker.stop()
    dbt_worker.stop()
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
    """Criterion 7: every checkpoint OF THE SELECTED ASSET on this server,
    oldest first - never another asset's (REQ-PIPE-365 criterion 2)."""
    asset = _asset()
    found = [Checkpoint.from_comment(name, comment) for name, comment in _rows(dsn, prefix)
             if _is_own(name, prefix, asset)]
    return sorted(found, key=lambda c: (c.taken_at, c.name))


def _rows(dsn: str | None, prefix: str) -> list[tuple[str, str | None]]:
    with _admin(dsn) as admin:
        return admin.execute(
            "SELECT datname, shobj_description(oid, 'pg_database') FROM pg_database "
            "WHERE datname LIKE %s ORDER BY datname",
            [prefix.replace("_", r"\_") + "%"]).fetchall()


def legacy(dsn: str | None = None) -> list[str]:
    """Every checkpoint and resume database made before the asset split,
    which belongs to no asset (#347): shown apart by `checkpoint list`,
    deletable by name, never pruned."""
    return [name for prefix in (PREFIX, RESUME_PREFIX) for name, _ in _rows(dsn, prefix)
            if is_legacy(name)]


def resumes(dsn: str | None = None) -> list[Checkpoint]:
    """Every resume's database of the selected asset on this server (#133
    B8; REQ-PIPE-365 criterion 2). Listed, never
    pruned: a person may be pointed at one. A resume carries no description
    of its own, so only its name is meaningful."""
    return listed(dsn, RESUME_PREFIX)


def arrivals_of(collection_id: str) -> list:
    """The collection's arrivals as a regeneration would produce them, in
    receipt order - generated somewhere of its own, never data/ - so an
    arrival number can be checked, and shown, before anything is touched
    (#133 B3 and B4). About five seconds.

    A GENERATION, SO ONE PIN (REQ-GEN-398 criterion 1): every collection it
    generates reads the configuration as it stood when this began - and never
    a delivery-tree snapshot (criterion 4), since it recognises the temporary
    tree it has just written."""
    import contextlib
    import io
    import tempfile
    import warnings

    from asset_model import config_pin
    from generator.public import generated_into
    from asset_model import arrivals as arrival_tree

    with config_pin.pinned(), tempfile.TemporaryDirectory(prefix="mothman-ckpt-") as tmp, \
            contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with generated_into(Path(tmp)) as root:
            return arrival_tree.arrivals_for(collection_id, "", root / "deliveries",
                                         root / "receipts")


def named(arrivals: list, n: int) -> str:
    """Arrival n with the delivery it belongs to, for every message that
    names an arrival number (#133 B4)."""
    a = arrivals[n - 1] if 1 <= n <= len(arrivals) else None
    return f"arrival {n}" + (f" (delivery {a.delivery_name!r})" if a is not None else "")


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
    # ANOTHER ASSET'S IS NOT THIS ONE'S TO DELETE (REQ-PIPE-365 criterion 2),
    # refused before the server is asked, so it reads the same whether or
    # not that database exists.
    asset = _asset()
    if not (_is_own(name, PREFIX, asset) or _is_own(name, RESUME_PREFIX, asset)
            or is_legacy(name)):
        raise CheckpointRefused(
            f"{name!r} is not one of asset {asset!r}'s checkpoints or resumes - nothing was "
            f"deleted; `mothman pipeline checkpoint list` shows this asset's")
    with _admin(dsn) as admin:
        # A NAME THAT IS NOT THERE IS REFUSED, never reported deleted - a typo
        # must not read as success (post-build-review #133 B7).
        if not admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name]).fetchone():
            raise CheckpointRefused(
                f"there is no checkpoint or resume database called {name!r} - nothing was "
                "deleted; `mothman pipeline checkpoint list` shows those there are")
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


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
    from asset_model import collections

    short = collections.by_id(cp.collection_id).short
    name = _named_for(RESUME_PREFIX, short, cp.before)
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
    # NEVER BETWEEN TWO ARRIVALS OF ONE PACKAGE (REQ-PIPE-266 criterion 18;
    # REQ-TEST-159 criterion 1 as amended): a package - files sharing one
    # receipt instant - is gated together once all of it is checked, so a
    # checkpoint inside one would hold a package checked in part and owed its
    # gate. Refused, naming where the package begins, rather than moved.
    target = arrivals[before - 1]
    if before >= 2 and arrivals[before - 2].received_at == target.received_at:
        first = next(i for i, a in enumerate(arrivals, start=1)
                     if a.received_at == target.received_at)
        raise CheckpointRefused(
            f"arrival {before} is not the first of its package - the files received with "
            f"it at one instant are gated together - so no checkpoint is taken inside it. "
            f"Its package begins at arrival {first}"
            + (f" ({arrivals[first - 1].run_id})" if getattr(arrivals[first - 1], "run_id",
                                                              None) else "")
            + f"; choose --checkpoint-before {first}.")
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
