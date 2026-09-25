"""One database, and one place where a logical table name becomes a
physical table (REQ-PIPE-068).

WHAT THIS REPLACES. Until now every QA run built its own DuckDB FILE -
`data/duckdb_runs/<run_id>.duckdb` for Birth Registrations,
`data/cp_duckdb_runs/<run_id>.duckdb` for Child Protection - each
holding that run's rows under a schema called `raw`, because the real
tools have no run-scoped `where` clause to filter by and the only way to
get a genuine per-run `dbt test` or `soda scan` was to point them at a
file containing one run's data. That worked, and it is the wrong shape
for a supply model: a supply arrives, is staged, is assigned to a slot
and is later promoted, and none of that survives in a file that exists
for the length of one run.

So there is one durable database holding the staging schema, the
rejected schema and (from delivery sprint 13) the period schemas, and
each QA run gets a SCHEMA OF VIEWS rather than a database of its own.

WHY A VIEW AND NOT A TABLE, which is the part worth understanding
before changing anything here. `REQ-PIPE-060` criterion 7 says a staged
table is visible to a check only once its load record exists. The
honest implementation of that against physical tables is a
whole-delivery transaction, which Keith turned down on scale. A view
delivers it instead: the physical table can be half-written, ambiguous
or simply the wrong version, and the check never sees it, because the
check reads a logical name and a logical name only exists if this
module created a view for it. PHYSICAL PRESENCE IS NOT READABILITY.

AMBIGUITY IS ABSENCE, NOT A CHOICE (criterion 3). Where a logical name
has more than one candidate physical table and nothing to choose
between them, no view is made and the name is simply not there for that
run. A check against a missing table fails loudly; a check against
whichever version happened to sort first fails silently, years later,
in a way nobody can reconstruct. `REQ-PIPE-059` relies on exactly this
for two files delivered for one dataset.

CONCURRENCY, verified by real experiment rather than taken from the
docs (2026-09-25 - and `duckdb.org` is blocked from this environment
anyway): many processes may open one DuckDB file READ-ONLY at the same
time, and a single writer excludes everyone, read-only readers
included - `IOException: Could not set lock on file ... Conflicting
lock is held`. That is why:

  - the view schema is built ONCE, serially, before any fan-out, and
  - every tool that only reads - Soda, datacontract-cli, Evidently -
    opens this database read-only and so may run in parallel, and
  - dbt, the one tool that writes, gets a small scratch database of its
    own and ATTACHes this one read-only (Keith's call, 2026-09-25).

That last one is the only reason a per-run FILE still exists anywhere,
and the distinction matters: criterion 7 forbids a database per run for
SUPPLY DATA, which now lives here and nowhere else. dbt's scratch file
holds its own materialised staging views and its own test results - a
tool artefact, replaced at delivery sprint 15 when dbt stops being
invoked this way at all.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import duckdb

ROOT = Path(__file__).resolve().parent.parent.parent

#: Overridable so a test worker gets its own database. That is the
#: deliberate isolation REQ-PIPE-068's own NFR asks for: isolation used
#: to fall out of a database per run, this requirement removes the
#: database per run, and something has to replace it. One database per
#: WORKER is allowed - criterion 7 forbids one per RUN.
SUPPLY_DB_ENV = "MOTHMAN_SUPPLY_DB"
DEFAULT_SUPPLY_DB = ROOT / "data" / "supply.duckdb"

#: Where a supply lands before anything has decided which slot it fills.
STAGING_SCHEMA = "staging"
#: Where a supply goes when it was recognised and could not be loaded.
REJECTED_SCHEMA = "rejected"

#: A per-run view schema carries this prefix so one left behind by an
#: interrupted run is identifiable on its own terms (criterion 6) -
#: without a manifest, a log, or any other record to cross-reference.
#: At ~30 datasets with years of history, orphaned schemas are a real
#: operational cost rather than untidiness.
RUN_SCHEMA_PREFIX = "qa_run_"

#: DuckDB identifiers are quoted everywhere below, so this is not what
#: keeps the SQL safe - it is what keeps a schema name READABLE and
#: reversible back to the run it belongs to. A run id that cannot
#: survive the round trip is a bug in whoever minted it.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


class SupplyDbError(RuntimeError):
    """Raised where continuing would mean guessing. Loud on purpose -
    every silent fallback this project has removed was once a
    reasonable-looking default."""


def supply_db_path() -> Path:
    """The one database. `MOTHMAN_SUPPLY_DB` wins where it is set."""
    override = os.environ.get(SUPPLY_DB_ENV)
    return Path(override) if override else DEFAULT_SUPPLY_DB


def connect(read_only: bool = False, path: str | os.PathLike | None = None):
    """Open the supply database.

    READ-ONLY IS THE RIGHT DEFAULT FOR A CHECK and the wrong one for
    this signature, so it is spelt out at every call site instead: a
    reader that quietly opened read-write would take the exclusive lock
    and lock out every parallel reader, which is a failure that shows up
    as someone else's crash rather than its own.
    """
    db = Path(path) if path is not None else supply_db_path()
    if read_only and not db.exists():
        raise SupplyDbError(
            f"no supply database at {db} - nothing has been staged yet. "
            f"Run `mothman pipeline run` to build one, or set {SUPPLY_DB_ENV}.")
    db.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db), read_only=read_only)


def _ident(name: str, what: str) -> str:
    if not _SAFE_ID.match(name or ""):
        raise SupplyDbError(f"{what} is not a usable identifier: {name!r}")
    return name


def run_schema(run_id: str) -> str:
    """The view schema for one QA run."""
    return RUN_SCHEMA_PREFIX + _ident(run_id, "run id").replace(".", "_").replace("-", "_")


def run_id_of(schema: str) -> str | None:
    """The inverse, for reporting an orphan in terms a person can act
    on. Returns None for a schema that is not a run schema at all."""
    if not schema.startswith(RUN_SCHEMA_PREFIX):
        return None
    return schema[len(RUN_SCHEMA_PREFIX):]


def staged_table(table: str, run_id: str) -> str:
    """The physical name a staged table takes.

    One name per (logical table, arrival), never an overwrite - a
    resupply is a NEW TABLE in the same schema, matching Keith's real
    operational database. The cheapest implementation is the wrong one:
    `CREATE OR REPLACE`, which is what the retired per-run builders did,
    keeps exactly one version and so destroys the history the
    read-the-newest rule exists for.

    `REQ-PIPE-060` refines this to carry the arrival INSTANT rather than
    a run id, once arrivals have instants of their own. The shape - one
    physical table per arrival, resolved to a logical name by a view -
    is what matters here and does not change.
    """
    return f"{_ident(table, 'table name')}__{_ident(run_id, 'run id')}"


def ensure_schemas(conn) -> None:
    """The durable schemas. Period schemas are delivery sprint 13 and
    are deliberately not created here - shelves years before anything
    decides what goes on them."""
    for schema in (STAGING_SCHEMA, REJECTED_SCHEMA):
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')


@dataclass
class Resolution:
    """What one run can actually read, and what it cannot.

    `absent` and `ambiguous` are kept apart on purpose. Both mean the
    same thing to a check - the table is not there - and they mean
    completely different things to whoever has to fix it: nothing
    arrived, versus several things arrived and nobody has said which
    one counts.
    """
    run_id: str
    schema: str
    resolved: dict[str, str] = field(default_factory=dict)
    ambiguous: dict[str, list[str]] = field(default_factory=dict)
    absent: list[str] = field(default_factory=list)

    @property
    def readable(self) -> list[str]:
        return sorted(self.resolved)

    def as_record(self) -> dict:
        """The committed form (criterion 5): which physical version of
        each table this run actually read. Written to `qa_results/`,
        because the view schema it describes is discarded when the run
        ends and the question "what did that run read" is asked years
        afterwards."""
        return {"run_id": self.run_id, "schema": self.schema,
                "resolved": dict(sorted(self.resolved.items())),
                "ambiguous": {k: sorted(v) for k, v in sorted(self.ambiguous.items())},
                "absent": sorted(self.absent)}


def candidates_in(conn, schema: str, logical_names: Sequence[str]) -> dict[str, list[str]]:
    """Every physical table in `schema` that claims one of these logical
    names, keyed by the name it claims.

    Matched on the `<table>__<suffix>` convention `staged_table()`
    writes, and NOT by a prefix test: `cp_case_workers__x` must never be
    a candidate for `cp_case`, and a prefix test says it is.
    """
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
        [schema]).fetchall()
    wanted = set(logical_names)
    found: dict[str, list[str]] = {name: [] for name in wanted}
    for (physical,) in rows:
        logical, sep, _suffix = physical.partition("__")
        if sep and logical in wanted:
            found[logical].append(physical)
    return found


def create_run_views(conn, run_id: str, candidates: Mapping[str, Sequence[str]],
                     source_schema: str = STAGING_SCHEMA) -> Resolution:
    """Build the run's view schema and report what it holds.

    A logical name becomes a view only where exactly one candidate
    physical table claims it (criterion 4). Zero candidates is absence;
    two or more with no basis to choose is ALSO absence (criterion 3),
    recorded separately so the reason survives.
    """
    schema = run_schema(run_id)
    conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    conn.execute(f'CREATE SCHEMA "{schema}"')

    res = Resolution(run_id=run_id, schema=schema)
    for logical in sorted(candidates):
        physical = sorted(candidates[logical])
        if len(physical) == 1:
            conn.execute(
                f'CREATE VIEW "{schema}"."{_ident(logical, "table name")}" AS '
                f'SELECT * FROM "{source_schema}"."{physical[0]}"')
            res.resolved[logical] = physical[0]
        elif not physical:
            res.absent.append(logical)
        else:
            res.ambiguous[logical] = physical
    return res


def drop_run_schema(conn, run_id: str) -> None:
    """Discard the run's schema once the run completes (criterion 1).
    Idempotent, because the interesting caller is a cleanup path that
    cannot know whether the run got far enough to create one."""
    conn.execute(f'DROP SCHEMA IF EXISTS "{run_schema(run_id)}" CASCADE')


def run_schemas(conn) -> list[str]:
    """Every per-run view schema currently in the database.

    During a run this includes that run's own. Between runs, anything
    listed here is an orphan - a run that was interrupted before it
    could discard its schema.
    """
    rows = conn.execute(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name LIKE ?", [RUN_SCHEMA_PREFIX + "%"]).fetchall()
    return sorted(r[0] for r in rows)


def drop_orphan_run_schemas(conn, keep: Sequence[str] = ()) -> list[str]:
    """Remove every per-run view schema except the ones named in
    `keep`. Returns what it dropped, so a caller can say so rather than
    tidying up silently."""
    spared = {run_schema(r) for r in keep}
    dropped = []
    for schema in run_schemas(conn):
        if schema in spared:
            continue
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        dropped.append(schema)
    return dropped
