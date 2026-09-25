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

from qa_tools.common.asset_time import arrival_key

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


def staged_table(table: str, received_at, ordinal: int = 0) -> str:
    """The physical name a staged table takes.

    ONE NAME PER (LOGICAL TABLE, ARRIVAL), carrying that arrival's own
    instant (REQ-PIPE-060 criterion 4), and never an overwrite - a
    resupply is a NEW TABLE in the same schema, matching Keith's real
    operational database. The cheapest implementation is the wrong one:
    `CREATE OR REPLACE` on a shared name, which is what the retired
    per-run builders did, keeps exactly one version and so destroys the
    history the read-the-newest rule exists for.
    """
    name = f"{_ident(table, 'table name')}__{arrival_key(received_at)}"
    if not ordinal:
        return name
    # A HELD SUPPLY STAGES EVERY FILE THAT MATCHED (REQ-PIPE-059), so
    # two files claiming one dataset in one arrival need two physical
    # names. Without this the second overwrites the first and the hold
    # has nothing left to resolve WITH - the exact failure the hold
    # exists to prevent, reintroduced one layer down.
    #
    # AN ORDINAL, not the filename: a supplier's filename must never
    # reach a SQL identifier, and the ordinal is ours.
    return f"{name}__{int(ordinal)}"


def ensure_schemas(conn) -> None:
    """The durable schemas that exist whether or not anything has been
    promoted.

    PERIOD SCHEMAS ARE STILL NOT CREATED HERE, and the reason changed
    with REQ-PIPE-035 rather than going away. They are no longer future
    work - qa_tools/common/period_schema.py builds them - but one is
    created when a period is first promoted into, by
    ensure_period_schema(), not swept into existence ahead of time.
    Creating every period a calendar declares would put years of empty
    schemas in the database, and an empty period schema and a period
    nobody has promoted into are the same fact stated twice.
    """
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


def split_staged(physical: str) -> tuple[str, str, str] | None:
    """`(logical table, arrival key, ordinal)` for a staged table name,
    or None for a name that is not one.

    `__` is the separator because no table name in this project
    contains one - `cp_case_workers` is single underscores throughout -
    and the arrival key and ordinal are digits, so the segments come
    apart unambiguously.
    """
    parts = physical.split("__")
    if len(parts) < 2 or not all(parts[:2]):
        return None
    return parts[0], parts[1], "__".join(parts[2:])


def candidates_in(conn, schema: str, logical_names: Sequence[str],
                   arrival: str | None = None,
                   loaded: frozenset[str] | None = None) -> dict[str, list[str]]:
    """Every physical table in `schema` that claims one of these logical
    names, keyed by the name it claims.

    `arrival` SCOPES IT TO ONE ARRIVAL, and leaving it out is almost
    never what a caller wants. The bug that put it here: a QA run built
    its views from every version ever staged, so on the forty-second
    run the logical name had forty-two candidates, the ambiguity rule
    correctly refused to choose between them, and dbt failed to find a
    table that was sitting right there. The rule was right; the
    question it was asked was wrong. Candidates for a run are the
    tables that arrival staged - several only where several files
    claimed one dataset in one delivery, which is REQ-PIPE-059's case
    and the ambiguity this is really for.

    `loaded` IS THE LOAD-RECORD GATE (REQ-PIPE-060 criterion 7). A
    physically present table with no load record is not a candidate,
    because physical presence is not readability: without a
    whole-delivery transaction a truncated table is physically there
    and physically readable, and a truncated table in staging is
    indistinguishable from a genuinely short supply. Pass None to skip
    the gate, which only a caller that is not building a check's view
    should do.

    Matched on the `<table>__<arrival>` convention `staged_table()`
    writes, and NOT by a prefix test: `cp_case_workers__x` must never
    be a candidate for `cp_case`, and a prefix test says it is.
    """
    # NARROWED IN SQL where the arrival is known, rather than listing
    # the schema and filtering here. Staging only ever grows - a new
    # table per arrival, never an overwrite, across ~30 datasets and
    # years - so the table count is the fastest-growing thing in this
    # design, and an ordinary question must not have to enumerate all
    # of it. The LIKE is a SUPERSET filter, not the decision: the exact
    # `<table>__<arrival>` test below still decides.
    if arrival is None:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [schema]).fetchall()
    else:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name LIKE ?",
            [schema, f"%__{arrival}%"]).fetchall()
    wanted = set(logical_names)
    found: dict[str, list[str]] = {name: [] for name in wanted}
    for (physical,) in rows:
        parts = split_staged(physical)
        if parts is None:
            continue
        logical, staged_arrival, _ordinal = parts
        if logical not in wanted:
            continue
        if arrival is not None and staged_arrival != arrival:
            continue
        if loaded is not None and physical not in loaded:
            continue
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


# ---------------------------------------------------------------------------
# dbt's scratch database
#
# The one tool that WRITES, and the reason a per-run file still exists
# anywhere. dbt materialises its staging models and its --store-failures
# audit tables somewhere; pointed at the supply database it would take
# DuckDB's exclusive lock and stall every parallel reader. So it gets its
# own small file and ATTACHes the supply database read-only, which is
# Keith's call of 2026-09-25 over serialising the whole fan-out.
#
# NOT THE THING CRITERION 7 FORBIDS, and the distinction is worth being
# precise about: SUPPLY DATA lives in one database. What lands here is
# dbt's own derived output - a tool artefact, and delivery sprint 15
# stops invoking dbt this way at all.
#
# Both paths hang off the supply database's own directory, so a test
# worker that has its own database gets its own scratch for free - the
# per-worker uniqueness the retired data/duckdb_runs/ layout used to
# provide, inherited rather than re-invented.
# ---------------------------------------------------------------------------

def scratch_dir() -> Path:
    return supply_db_path().parent / "dbt_scratch"


def staging_csv(physical: str) -> Path:
    """Where a loader writes the CSV it hands to DuckDB.

    NEVER INSIDE THE DELIVERY. The first version put it beside the
    source file, which IS the delivery directory - a supplier-owned
    tree this pipeline treats as immutable, and the one place a stray
    file becomes an "unrecognised artefact" warning on every later run.
    That is not hypothetical: one leaked through a crash and turned up
    in recognition as a file no dataset claimed.
    """
    directory = scratch_dir() / "staging"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{_ident(physical, 'staged table')}.csv"


def dbt_scratch_db(run_id: str) -> Path:
    d = scratch_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_ident(run_id, 'run id')}.duckdb"


def dbt_target_path(run_id: str) -> Path:
    """dbt's own target/ for this run.

    Never DBT_PROJECT_DIR/target/, which is a fixed repo-relative path
    shared by every invocation - two runs scheduled onto different
    parallel workers would clobber each other's manifest.json and
    run_results.json mid-write. A real risk, reproduced rather than
    theorised (plans/running-thoughts.md #12).
    """
    return scratch_dir() / "dbt_target" / _ident(run_id, "run id")


def connect_dbt_scratch(run_id: str, read_only: bool = True):
    """Open dbt's scratch database for a run, with the supply database
    ATTACHed read-only exactly as dbt's own profile attaches it.

    WITHOUT THE ATTACH THIS RAISES `Catalog "supply" does not exist`,
    which is how it was found: dbt's staging models are VIEWS, and a
    view carries its source reference rather than its source's rows -
    `stg_birth_registrations` is defined over
    `supply.<run schema>.birth_registrations`. Reading it from a
    connection that has never heard of `supply` fails at bind time. The
    rows are fine; the name is not resolvable.

    Both sides open read-only, so this adds no lock contention - many
    readers on one DuckDB file is exactly the case that is safe.
    """
    conn = duckdb.connect(str(dbt_scratch_db(run_id)), read_only=read_only)
    conn.execute(f"ATTACH IF NOT EXISTS '{supply_db_path()}' AS supply (READ_ONLY)")
    return conn


# ---------------------------------------------------------------------------
# What a run actually read (criterion 5)
#
# The view schema is discarded when the run ends, and "which version of
# this table did that run read" is a question asked years afterwards -
# of an audit, of a disagreement between two runs, of a check that
# started failing. So the answer is recorded rather than reconstructed.
#
# RECORDED AT STAGING TIME, which is the only moment it is an OBSERVED
# FACT rather than a re-derivation: the resolution is what create_run_views
# decided, and deciding it again later against a staging schema that has
# moved on would answer a different question and look like the same one.
# This table is the carrier; qa_results/ is the durable record the
# criterion asks for, written by the orchestrator once the run has a
# timestamp to file it under.
# ---------------------------------------------------------------------------

_RESOLUTIONS = "_resolutions"


def record_resolution(conn, res: Resolution) -> None:
    """Persist one run's resolution, replacing any earlier one for that
    run - re-staging an arrival re-decides it, and the latest decision
    is the one that holds."""
    conn.execute(
        f'CREATE TABLE IF NOT EXISTS "{STAGING_SCHEMA}"."{_RESOLUTIONS}" '
        "(run_id VARCHAR, logical VARCHAR, physical VARCHAR, state VARCHAR)")
    conn.execute(
        f'DELETE FROM "{STAGING_SCHEMA}"."{_RESOLUTIONS}" WHERE run_id = ?', [res.run_id])
    rows = ([(res.run_id, k, v, "resolved") for k, v in res.resolved.items()]
            + [(res.run_id, k, p, "ambiguous") for k, ps in res.ambiguous.items() for p in ps]
            + [(res.run_id, k, None, "absent") for k in res.absent])
    for row in rows:
        conn.execute(
            f'INSERT INTO "{STAGING_SCHEMA}"."{_RESOLUTIONS}" VALUES (?, ?, ?, ?)', list(row))


def resolution_for(conn, run_id: str) -> Resolution:
    """Read back what was decided for one run. An unrecorded run comes
    back empty rather than raising: a caller asking is reporting, and a
    report that says "nothing recorded" is more useful than a
    traceback."""
    res = Resolution(run_id=run_id, schema=run_schema(run_id))
    try:
        rows = conn.execute(
            f'SELECT logical, physical, state FROM "{STAGING_SCHEMA}"."{_RESOLUTIONS}" '
            "WHERE run_id = ? ORDER BY logical, physical", [run_id]).fetchall()
    except duckdb.CatalogException:
        return res
    for logical, physical, state in rows:
        if state == "resolved":
            res.resolved[logical] = physical
        elif state == "ambiguous":
            res.ambiguous.setdefault(logical, []).append(physical)
        else:
            res.absent.append(logical)
    return res


def expected_tables(recognition, received_at) -> dict[str, str]:
    """The physical tables one delivery should have produced, keyed by
    dataset id where that dataset produced exactly one.

    REQ-PIPE-060 criterion 16 asks whether a delivery is processed, and
    that question cannot be answered without knowing what "all of it"
    was. Derived from RECOGNITION rather than from the catalogue,
    because the catalogue only ever knows what did load - a file that
    failed outright leaves nothing there to count, which is precisely
    the case being looked for.

    A dataset that matched several files (REQ-PIPE-059's held supply)
    contributes one entry per file, keyed `<dataset id>#<ordinal>`: the
    hold is resolved by a person looking at both, so both must be
    accounted for.
    """
    from qa_tools.common import hierarchy

    out: dict[str, str] = {}
    for dataset_id, names in sorted(recognition.by_dataset.items()):
        table = hierarchy.dataset(dataset_id).table
        several = len(names) > 1
        for ordinal, _name in enumerate(sorted(names), start=1):
            key = f"{dataset_id}#{ordinal}" if several else dataset_id
            out[key] = staged_table(table, received_at, ordinal if several else 0)
    return out
