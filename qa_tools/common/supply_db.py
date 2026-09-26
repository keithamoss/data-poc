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
lock is held`.

THAT CONSTRAINT IS GONE (REQ-PIPE-087). The engine is PostgreSQL, where
readers and writers do not exclude each other, so three pieces of
design that existed only to work around a file lock have been removed
rather than ported:

  - dbt no longer gets a scratch database of its own with this one
    ATTACHed read-only. It writes its models and its --store-failures
    tables into its own SCHEMA in the same database, which is what the
    workaround was imitating.
  - `read_only=True` no longer buys parallelism, because nothing was
    ever serialised. It is kept, and now does what it says: the session
    is set READ ONLY, so a reader that tries to write fails instead of
    succeeding quietly.
  - the view schema is still built once, serially, before any fan-out -
    but for the original reason (every tool must see the same
    resolution) rather than to avoid a lock.

DuckDB is still a dependency and still has one job: reading what
arrives. A supplier sends CSV or Parquet, DuckDB reads it, and the rows
go into PostgreSQL. It is never a warehouse again.

WHAT THIS COSTS, said plainly because it is the real trade: running the
PoC now needs a PostgreSQL to point at. There is no file to open.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from qa_tools.common.asset_time import arrival_key

import psycopg

ROOT = Path(__file__).resolve().parent.parent.parent

#: PostgreSQL's own hard limit on an identifier, and the reason it is
#: checked here rather than discovered later: Postgres TRUNCATES a
#: longer name silently, where DuckDB accepted any length. A truncated
#: schema name collides with its neighbour and a truncated staged table
#: loses the arrival that distinguishes it - both of which read as data
#: loss rather than as a naming problem, and neither of which raises.
MAX_IDENTIFIER = 63

#: Overridable so a test worker gets its own database. That is the
#: deliberate isolation REQ-PIPE-068's own NFR asks for: isolation used
#: to fall out of a database per run, this requirement removes the
#: database per run, and something has to replace it. One database per
#: WORKER is allowed - criterion 7 forbids one per RUN.
#: DELIBERATELY RENAMED from MOTHMAN_SUPPLY_DB rather than reused. The
#: value's SHAPE changed - a filesystem path became a connection string
#: - and a stale path silently reinterpreted as a DSN would fail in a
#: way that names neither problem. A new name makes every consumer
#: visit the change, which is what this project's own rule about shape
#: changes asks for.
SUPPLY_DSN_ENV = "MOTHMAN_SUPPLY_DSN"

#: NO DEFAULT, and this is not an omission. There is no local file to
#: fall back to any more, so a default would have to name somebody's
#: database - and the one thing worse than failing to connect is
#: connecting to the wrong environment. REQ-PIPE-093 makes this a
#: first-class rule for every operation; this is where it starts.

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


def supply_db_dsn() -> str:
    """The connection string for the one database.

    Raises rather than guessing where it is unset, which is the whole
    point - see SUPPLY_DSN_ENV's own note. The error names the variable
    and what to do, because the person who hits this is usually setting
    the project up for the first time.
    """
    dsn = os.environ.get(SUPPLY_DSN_ENV)
    if not dsn:
        raise SupplyDbError(
            f"{SUPPLY_DSN_ENV} is not set, and there is no default - this "
            f"pipeline has no local database file to fall back to. Set it to a "
            f"real PostgreSQL connection string, e.g. "
            f"postgresql://user@host:5432/supply. A dev container and CI each "
            f"supply one; see README's Development section.")
    return dsn


def _translate(sql: str, params) -> str:
    """`?` placeholders to psycopg's `%s`, and ONLY where params say so.

    The whole dialect difference between the retired engine and this one
    lives here, which is deliberate: the alternative was rewriting every
    placeholder at ~40 call sites, a large mechanical diff with far more
    room to get one wrong than one function has.

    IT REFUSES RATHER THAN GUESSES when the counts disagree. A silent
    rewrite is the failure mode to avoid: SQL carrying a literal `?`
    inside a quoted string would be corrupted by a blind replace, and
    the symptom would be a malformed query nobody could trace back to
    here. A mismatch means exactly that case, so it raises and names the
    statement. No caller in this project puts a literal `?` in SQL; if
    one ever needs to, it must not go through here.
    """
    holes = sql.count("?")
    if holes != len(params):
        raise SupplyDbError(
            f"{holes} '?' placeholder(s) but {len(params)} parameter(s) - "
            f"refusing to guess which is right: {sql}")
    return sql.replace("?", "%s")


class SupplyConnection:
    """A PostgreSQL connection that takes this project's own SQL.

    A THIN BOUNDARY, NOT AN ABSTRACTION LAYER. It exists so that the
    ~40 statements already written across qa_tools/ keep working
    unchanged, and so the one place the driver is visible is this file.
    It deliberately does not try to be a database-agnostic wrapper -
    there is one engine, and pretending otherwise would invite somebody
    to point it at a second one.

    AUTOCOMMIT IS ON, matching how the retired engine behaved and how
    every caller here is written: each statement stands alone. Where a
    caller genuinely needs several statements to land together - a
    filing decision and its effect, REQ-PIPE-091 - it must open its own
    transaction explicitly rather than rely on a default, because a
    transaction that is implicit is one nobody knows the boundaries of.
    """

    def __init__(self, raw: "psycopg.Connection"):
        self._raw = raw

    def execute(self, sql: str, params: Sequence | None = None):
        if params is None:
            return self._raw.execute(sql)
        return self._raw.execute(_translate(sql, params), list(params))

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()

    @property
    def raw(self) -> "psycopg.Connection":
        """For the one caller that legitimately needs the driver - a COPY
        stream, or a real transaction. Reaching for this in ordinary code
        is a sign the boundary above is missing something."""
        return self._raw

    def __enter__(self) -> "SupplyConnection":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def connect(read_only: bool = False, dsn: str | None = None) -> SupplyConnection:
    """Open the supply database.

    `read_only` NOW MEANS WHAT IT SAYS. Under the retired engine it was
    load-bearing for a different reason - a writer took an exclusive
    file lock and shut out every reader, so a reader that opened
    read-write broke other processes rather than itself. PostgreSQL has
    no such contention, so this is no longer about parallelism at all:
    it sets the session READ ONLY, which turns "this code should not
    write" from a convention into something the database enforces.

    A FAILURE TO CONNECT IS LOUD AND NAMES THE HOST (REQ-PIPE-087
    criterion 12). It never falls back to another database, a cached
    copy, or a file - all three were available under the old engine and
    all three would hide the one thing worth knowing.
    """
    target = dsn if dsn is not None else supply_db_dsn()
    try:
        raw = psycopg.connect(target, autocommit=True)
    except psycopg.Error as exc:
        raise SupplyDbError(
            f"cannot reach the supply database at {_redact(target)}: {exc}") from exc
    if read_only:
        raw.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    return SupplyConnection(raw)


def _redact(dsn: str) -> str:
    """A DSN in an error message, without its password.

    Errors from here reach logs, CI output and a public repository's own
    Actions pages, so this is not politeness - a connection string is a
    credential, and the failure that prints one is the failure nobody
    notices until it is indexed.
    """
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", dsn)


def _ident(name: str, what: str) -> str:
    if not _SAFE_ID.match(name or ""):
        raise SupplyDbError(f"{what} is not a usable identifier: {name!r}")
    # POSTGRES TRUNCATES SILENTLY past 63 bytes, so this is the one real
    # portability trap in the move off the old engine - see
    # MAX_IDENTIFIER. Checked on the encoded length rather than the
    # character count, because the limit is bytes.
    if len(name.encode("utf-8")) > MAX_IDENTIFIER:
        raise SupplyDbError(
            f"{what} is {len(name.encode('utf-8'))} bytes, over PostgreSQL's "
            f"{MAX_IDENTIFIER}-byte identifier limit, and would be silently "
            f"truncated into a collision: {name!r}")
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
# dbt's own output, and where the file-shaped leftovers live
#
# THE SCRATCH DATABASE IS GONE (REQ-PIPE-087). dbt used to get a small
# DuckDB file of its own with the supply database ATTACHed read-only,
# for one reason only: pointed at the supply database directly it took
# DuckDB's exclusive lock and stalled every parallel reader. PostgreSQL
# has no such contention, so dbt now writes its models and its
# --store-failures tables into its own SCHEMA in the one database, which
# is what the workaround was imitating all along.
#
# What still needs a directory is genuinely file-shaped: the CSV a
# loader hands to the database, and dbt's own target/ (manifest.json,
# run_results.json - artefacts dbt writes to disk, not to a warehouse).
#
# PER-WORKER ISOLATION USED TO FALL OUT OF THE DATABASE'S OWN PATH, and
# there is no path any more, so it is derived from the DSN instead -
# same property, stated rather than inherited: two workers pointed at
# two databases get two scratch directories, and two processes sharing
# one database share one, which is correct because they share its
# tables too.
#
# DBT_SCHEMA is where dbt's own models land. Named, not defaulted: dbt
# would otherwise use `public`, and a model sitting in `public` beside
# real supply schemas is exactly the ambiguity this design removes.
# ---------------------------------------------------------------------------

#: dbt's own schema in the one database - its models and its
#: --store-failures audit tables. Never a supply schema.
DBT_SCHEMA = "dbt"

def scratch_dir() -> Path:
    """Where this database's file-shaped scratch lives.

    Keyed by a short digest of the DSN rather than by the DSN itself,
    which would put a credential into a path - see _redact()'s own note
    for why that matters in this repository.
    """
    key = hashlib.sha256(supply_db_dsn().encode("utf-8")).hexdigest()[:12]
    return ROOT / "data" / "dbt_scratch" / key


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


def dbt_target_path(run_id: str) -> Path:
    """dbt's own target/ for this run.

    Never DBT_PROJECT_DIR/target/, which is a fixed repo-relative path
    shared by every invocation - two runs scheduled onto different
    parallel workers would clobber each other's manifest.json and
    run_results.json mid-write. A real risk, reproduced rather than
    theorised (plans/running-thoughts.md #12).
    """
    return scratch_dir() / "dbt_target" / _ident(run_id, "run id")



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
    except psycopg.errors.UndefinedTable:
        # Nothing has been staged in this database yet, so the carrier
        # table does not exist. Same meaning as the retired engine's
        # CatalogException, handled the same way - a caller asking is
        # reporting, and "nothing recorded" beats a traceback.
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
