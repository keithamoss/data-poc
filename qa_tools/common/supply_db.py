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

#: How long a statement will WAIT FOR A LOCK before giving up, and why
#: this exists at all: a DROP or an ALTER needs an exclusive lock, and
#: PostgreSQL's default is to wait forever for one. Forever is the worst
#: possible answer for a pipeline - it is indistinguishable from slow,
#: it holds its own locks while it waits, and nothing in a log says why.
#:
#: Found the hard way rather than anticipated (2026-09-27): a QA tool
#: left a connection IDLE IN TRANSACTION holding a read lock on a staged
#: table, and the next load's DROP TABLE blocked behind it for six
#: minutes until the run was killed. With this set, that same situation
#: fails in seconds with a message naming the lock.
#:
#: Thirty seconds is chosen to be far longer than any legitimate wait in
#: this pipeline (every lock here is taken and released inside one
#: statement) and far shorter than a person's patience.
LOCK_TIMEOUT_ENV = "MOTHMAN_LOCK_TIMEOUT_MS"
DEFAULT_LOCK_TIMEOUT_MS = 30_000

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
#:
#: SHORTENED FROM `qa_run_` ON 2026-09-27 (Keith, reading a schema
#: name: "why have the duplicate run_run"). Every BDM run id already
#: starts with `run_`, so the old prefix produced `qa_run_run_001`, and
#: Child Protection managed `qa_run_cp_run_001`. Shortening the PREFIX
#: rather than stripping `run_` out of the ID is what keeps this
#: exactly reversible: stripping a substring that can appear anywhere
#: has no unambiguous inverse, so `qa_run_cp_001` could not say whether
#: the run was `cp_001` or `cp_run_001`.
#:
#: It does NOT collide with qa_store's metadata schema, which is
#: exactly `qa` and never `qa_something` - there is a test pinning
#: that, because the two are one character apart.
#: without a manifest, a log, or any other record to cross-reference.
#: At ~30 datasets with years of history, orphaned schemas are a real
#: operational cost rather than untidiness.
RUN_SCHEMA_PREFIX = "qa_"

#: Identifiers are quoted everywhere below, so this is not what keeps
#: the SQL safe - it is what keeps a schema or table name READABLE, and
#: identical whether a tool writes it quoted or not.
#:
#: LOWERCASE, DIGITS AND UNDERSCORE ONLY, tightened 2026-09-27 from a
#: pattern that also allowed uppercase, dots and hyphens. PostgreSQL
#: folds an unquoted identifier to lower case, and dbt and Soda both
#: write these names into their own SQL unquoted, so anything outside
#: this set produces a name that exists when quoted and cannot be found
#: when it is not. Refusing it here is the whole mechanism that lets
#: run_schema() be a readable identity instead of a hex encoding: a name
#: that would need encoding is now a bug reported at its source, and
#: whoever mints one normalises first (see
#: local_check.run_id_from_path). A period name is the deliberate
#: exception and is normalised rather than refused, because it is
#: authored config that should stay human - see period_schema.py.
_SAFE_ID = re.compile(r"^[a-z0-9_]+$")


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


def connect(read_only: bool = False, dsn: str | None = None,
            label: str = "mothman") -> SupplyConnection:
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

    EVERY CONNECTION SAYS WHO IT IS (`label`, 2026-09-27). PostgreSQL
    reports `application_name` in pg_stat_activity and in its own
    lock-wait log, and without it every row reads `[unknown]` - so
    "which of these is ours and which belongs to dbt or Soda" cannot be
    answered while a hang is actually happening, which is exactly when
    it needs answering. dbt sets its own; this is how ours become just
    as identifiable. Cheap, and it turns a diagnosis that took three
    reproductions into reading one line.
    """
    target = dsn if dsn is not None else supply_db_dsn()
    try:
        raw = psycopg.connect(target, autocommit=True, application_name=label)
    except psycopg.Error as exc:
        raise SupplyDbError(
            f"cannot reach the supply database at {_redact(target)}: {exc}") from exc
    # NEVER WAIT FOREVER FOR A LOCK - see LOCK_TIMEOUT_ENV. Set before
    # anything else this connection does, so even the first statement is
    # covered.
    raw.execute(f"SET lock_timeout = {_lock_timeout_ms()}")
    if read_only:
        raw.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    return SupplyConnection(raw)


def _lock_timeout_ms() -> int:
    raw = os.environ.get(LOCK_TIMEOUT_ENV)
    if raw is None:
        return DEFAULT_LOCK_TIMEOUT_MS
    try:
        value = int(raw)
    except ValueError as exc:
        raise SupplyDbError(
            f"{LOCK_TIMEOUT_ENV} must be a whole number of milliseconds, "
            f"got {raw!r}") from exc
    if value < 0:
        raise SupplyDbError(f"{LOCK_TIMEOUT_ENV} cannot be negative: {value}")
    return value


# ---------------------------------------------------------------------------
# Reading what arrives - DuckDB's one remaining job (REQ-PIPE-087)
#
# A supplier sends a file. DuckDB reads it and says what is in it;
# PostgreSQL stores it. That split is the whole of DuckDB's role now, and
# it is kept rather than replaced for a specific reason: `read_csv_auto`
# with an explicit `nullstr` is what already decides what an empty cell
# means in this project, and csv_io.py owns that decision after a real
# bug where "N/A" became NULL. Reading the CSV with pandas and inserting
# the frame would quietly move that decision somewhere else.
#
# ROWS STREAM OVER THE CONNECTION, never a server-side file read
# (criterion 6). `COPY ... FROM '<path>'` is refused to a non-superuser
# by PostgreSQL - measured, not assumed - and would in any case require
# the database to share a filesystem with whatever staged the file, which
# is false the moment this runs against Aurora.
# ---------------------------------------------------------------------------

#: DuckDB's inferred types to PostgreSQL's. Most names agree, which is
#: why this map is short - it holds the ones that do NOT, and anything
#: absent is passed through unchanged so a type this has never seen
#: fails loudly in PostgreSQL rather than being silently coerced to text.
_PG_TYPE = {
    "DOUBLE": "double precision",
    "FLOAT": "real",
    "HUGEINT": "numeric",
    "UHUGEINT": "numeric",
    "UBIGINT": "numeric",
    "UINTEGER": "bigint",
    "USMALLINT": "integer",
    "UTINYINT": "smallint",
    "TINYINT": "smallint",
    "BLOB": "bytea",
    "TIMESTAMP_NS": "timestamp",
    "TIMESTAMP WITH TIME ZONE": "timestamptz",
}

#: How many rows to pull from DuckDB at a time while streaming. Large
#: enough that the per-batch overhead disappears, small enough that a
#: population-scale file does not have to fit in memory - this project's
#: own synthetic_data_generator produces millions of rows.
_COPY_BATCH = 10_000


def _pg_type(duck_type: str) -> str:
    upper = duck_type.upper()
    if upper.startswith("DECIMAL"):
        return upper.replace("DECIMAL", "numeric")
    return _PG_TYPE.get(upper, duck_type)


def load_csv_into(conn: SupplyConnection, schema: str, table: str,
                  csv_path: str | os.PathLike, nullstr: str) -> int:
    """Read a CSV with DuckDB and land it in PostgreSQL. Returns the row count.

    REPLACES WHAT IS THERE, which is not the overwrite this design
    forbids: the physical name carries the arrival, so replacing it
    re-loads the same arrival rather than losing an earlier one. That is
    REQ-PIPE-060 criterion 15 - what is already present is replaced
    rather than trusted, because a table with no load record is unloaded
    whatever the catalogue says.

    NO PARTIAL TABLE SURVIVES A FAILURE. The create and the copy run
    inside one transaction, so a file that turns out to be malformed
    half way through leaves nothing behind rather than a truncated table
    - which criterion 5 requires and which the retired engine got for
    free from `CREATE TABLE AS SELECT` being one statement.
    """
    import duckdb  # the one place this project still needs it

    _ident(table, "table name")
    duck = duckdb.connect(":memory:")
    try:
        # CTAS INTO A TEMP TABLE, not a view, and not for tidiness:
        # DuckDB refuses a prepared parameter in CREATE VIEW ("Unexpected
        # prepared parameter. This type of statement can't be prepared!")
        # while accepting one in CREATE TABLE AS - which is the form the
        # retired code used, so this keeps a proven call shape rather
        # than interpolating a path into SQL.
        duck.execute(
            "CREATE TEMP TABLE arriving AS "
            "SELECT * FROM read_csv_auto(?, header=true, nullstr=?)",
            [str(csv_path), nullstr])
        # INFERRED FROM THE FILE, deliberately, and this was tried the
        # other way first. Building the staged table to the contract's
        # own `physicalType` declarations looked more correct - the
        # contract is the source of truth for schema - and it is wrong
        # here for a reason worth keeping: dirty data that violates a
        # declared length then fails to LOAD, so a dataset reports "no
        # table" instead of "these values are too long". That converts
        # rich information into poverty, which is the opposite of what a
        # QA pipeline is for. The checks report the discrepancy; the
        # loader takes what arrived.
        columns = [(name, _pg_type(dtype)) for name, dtype, *_ in
                   duck.execute("DESCRIBE arriving").fetchall()]
        if not columns:
            raise SupplyDbError(f"{csv_path} produced no columns")
        ddl = ", ".join(f'"{name}" {dtype}' for name, dtype in columns)

        raw = conn.raw
        with raw.transaction():
            # CASCADE: re-loading an arrival replaces a table a run's
            # view schema may already point at, and PostgreSQL refuses a
            # plain DROP in that case where the retired engine allowed it.
            raw.execute(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE')
            raw.execute(f'CREATE TABLE "{schema}"."{table}" ({ddl})')
            result = duck.execute("SELECT * FROM arriving")
            copied = 0
            with raw.cursor() as cur:
                with cur.copy(f'COPY "{schema}"."{table}" FROM STDIN') as copy:
                    while True:
                        batch = result.fetchmany(_COPY_BATCH)
                        if not batch:
                            break
                        for row in batch:
                            copy.write_row(row)
                        copied += len(batch)
        return copied
    finally:
        duck.close()


def connection_fields() -> dict[str, str]:
    """The DSN broken into the discrete fields other tools want.

    ONE PARSE, SEVERAL FORMATS. dbt wants host/port/user/dbname keys in a
    profile, Soda wants them in its own configuration YAML, and
    datacontract-cli wants them in environment variables - so the parsing
    happens once, here, and each tool's module formats what it needs.
    Three call sites each doing their own is three chances to disagree
    about what an empty password or a unix socket means.

    psycopg's own conninfo parser rather than a regex, because the DSN
    legitimately takes three shapes - a URL, a keyword string, and a unix
    socket expressed as `?host=/tmp` - and a hand-rolled parser gets one
    of the three wrong.
    """
    from psycopg import conninfo
    info = conninfo.conninfo_to_dict(supply_db_dsn())
    return {
        "host": str(info.get("host", "localhost")),
        "port": str(info.get("port", 5432)),
        "user": str(info.get("user", "")),
        "password": str(info.get("password", "")),
        "dbname": str(info.get("dbname", "")),
    }


def soda_config_yaml(data_source_name: str, schema: str) -> str:
    """Soda Core's own data-source configuration, for one run's schema.

    REPLACES add_duckdb_connection(), which took a live connection object
    this code already had open. soda-core-postgres has no equivalent - it
    is configured rather than handed a connection - so the run's view
    schema arrives here as the data source's `schema`, which is what the
    old `SET search_path` on that shared connection was doing.

    The password is written only when there is one. An empty `password:`
    key is not the same as no key to every driver, and this project's own
    local and dev-container databases authenticate without one.
    """
    f = connection_fields()
    lines = [f"data_source {data_source_name}:",
             "  type: postgres",
             f"  host: {f['host']}",
             f"  port: {f['port']}",
             f"  username: {f['user']}",
             f"  database: {f['dbname']}",
             f"  schema: {schema}"]
    if f["password"]:
        lines.insert(5, f"  password: {f['password']}")
    return "\n".join(lines) + "\n"


def connect_dbt(run_id: str, read_only: bool = True) -> SupplyConnection:
    """A connection whose UNQUALIFIED names are dbt's own models.

    Replaces the retired connect_dbt_scratch(), and keeps the one
    property its callers actually relied on: `SELECT ... FROM
    stg_birth_registrations` resolves without qualification. It got that
    from opening dbt's own scratch database; it gets it here from a
    search_path, which is the same idea with one fewer database in it.

    STILL READ-ONLY BY DEFAULT for the same reason as before - the caller
    is reading dbt's output to evaluate it, and a reader that can write
    is a reader that can corrupt what it is measuring.
    """
    conn = connect(read_only=read_only, label="mothman:read-dbt-output")
    # SET is allowed inside a read-only session; it changes name
    # resolution, not data.
    #
    # THIS RUN'S dbt SCHEMA, not a shared one (2026-09-27) - otherwise
    # a reader can resolve `stg_birth_registrations` to a model another
    # run is midway through rebuilding.
    conn.raw.execute(f'SET search_path TO "{dbt_schema(run_id)}", public')
    return conn


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
        raise SupplyDbError(
            f"{what} is not a usable identifier: {name!r} - only lowercase "
            f"letters, digits and underscore, because dbt and Soda write this "
            f"name into their own SQL unquoted and PostgreSQL folds an "
            f"unquoted identifier to lower case. Normalise it where it is "
            f"minted rather than encoding it here")
    # POSTGRES TRUNCATES SILENTLY past 63 bytes, so this is the one real
    # portability trap in the move off the old engine - see
    # MAX_IDENTIFIER. Checked on the encoded length rather than the
    # character count, because the limit is bytes. (With the pattern
    # above every character is one byte, so the two agree - the byte
    # check stays because it is the limit PostgreSQL actually applies.)
    if len(name.encode("utf-8")) > MAX_IDENTIFIER:
        raise SupplyDbError(
            f"{what} is {len(name.encode('utf-8'))} bytes, over PostgreSQL's "
            f"{MAX_IDENTIFIER}-byte identifier limit, and would be silently "
            f"truncated into a collision: {name!r}")
    return name


def normalise_ident_part(value: str) -> str:
    """Any string as a safe, lowercase identifier COMPONENT.

    A COMPONENT rather than a whole identifier, and the name says so on
    purpose: the result can begin with a digit, which PostgreSQL will
    not accept unquoted on its own. Both callers prefix it - a run id
    with `adhoc_`, a period schema with `period_` - so the letter is
    always there by the time it is a real name. An earlier draft
    prefixed a bare `n` to make the guarantee unconditional and that was
    worse: `n2026_q3` is a name nobody can explain, solving a problem
    neither caller has.

    Deliberately NOT reversible. The round trip is exactly what the
    retired hex encoding was buying, at the cost of legibility, and the
    legibility is the point.

    Two different strings CAN normalise to the same component, so this
    is only used where something else makes the result unique - here, a
    UTC timestamp to the second. Where the inputs are AUTHORED rather
    than generated the collision has to be refused instead, because
    silently merging two periods' promoted data is not a legibility
    problem: see period_schema.py.
    """
    # Underscore is itself a separator here, not a kept character, which
    # is what collapses a RUN of them: `weird--name!!.csv` would
    # otherwise leave `weird_name__...` because the unsafe run becomes
    # one underscore and the caller's own separator adds another. A
    # single underscore survives unchanged, so `run_001` is untouched.
    safe = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not safe:
        raise ValueError(f"nothing usable as an identifier in {value!r}")
    return safe

def run_schema(run_id: str) -> str:
    """The view schema for one QA run - the run id, prefixed, unchanged.

    NO ENCODING, and the history is worth keeping because the thing it
    was solving is real. PostgreSQL folds an UNQUOTED identifier to
    lower case. This module always quotes, but dbt and Soda write the
    schema name into their own SQL unquoted, so a run id carrying
    uppercase produced a schema those tools could not see - reported as
    every check in the run failing because the relation does not exist,
    which is a brutal symptom to read back to a missing capital letter.

    The first fix hex-encoded every uppercase or non-alphanumeric
    character, to keep the name reversible so two run ids differing only
    in case could not collide. It worked and it was the wrong trade
    (Keith, 2026-09-27: "why do you need to encode the schema names like
    that?"). The collision it prevented was hypothetical; the cost was
    certain and daily, because `qa_run_run_5f_001` is what a person then
    reads in psql, in a log, and in every error message.

    So the invariant moved to where the id is BORN instead.
    `_ident()` refuses a run id that is not already a safe lowercase
    identifier, and `local_check.run_id_from_path()` - the one place an
    unsafe name can enter, since it builds an id from a user-supplied
    filename - normalises before returning. Every other run id is minted
    `run_001`-style and was always safe: all 60 in committed history
    check out. That leaves this function an exact, readable identity,
    and a future caller inventing `Run-001` fails loudly at the source
    rather than quietly getting a hex-encoded schema.
    """
    return RUN_SCHEMA_PREFIX + _ident(run_id, "run id")


def run_id_of(schema: str) -> str | None:
    """The exact inverse, for reporting an orphan in terms a person can
    act on. Returns None for a schema that is not a run schema at all."""
    if not schema.startswith(RUN_SCHEMA_PREFIX):
        return None
    return schema[len(RUN_SCHEMA_PREFIX):]


def arrival_segment(received_at) -> str:
    """The `__<arrival>` part of a staged table's name.

    A REAL RECEIPT GOES THROUGH arrival_key() UNCHANGED, which is the
    half that must not move: committed history records these names, so
    `2026-08-01T01:00:00+00:00` has to keep producing
    `202608010100000000` exactly as it always has.

    A RUN ID DOES NOT (2026-09-27). Callers with no receipt - the
    ad-hoc `--folder` and `--local-file` paths - fall back to passing
    the run id, and arrival_key() keeps only the digits, which is
    right for an instant and lossy for a name. It made
    `adhoc_cp_run_001_20260927t030150` and
    `ref_cp_run_001_20260927t030150` the same arrival, so the two runs
    claimed one physical table - and because re-loading one does
    `DROP TABLE ... CASCADE`, staging the second silently destroyed
    the first run's views. Hidden for as long as the drift check read
    a CSV instead of the warehouse.
    """
    text = received_at if isinstance(received_at, str) else received_at.isoformat()
    # An instant always carries a `:` or a `-`; a run id never does,
    # because run ids are already constrained to [a-z0-9_]. That is
    # what tells the two apart without the caller having to say.
    if any(c in text for c in ":-"):
        return arrival_key(received_at)
    return normalise_ident_part(text)


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
    name = f"{_ident(table, 'table name')}__{arrival_segment(received_at)}"
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
    # THE UNDERSCORE IS ESCAPED, and it matters more now the prefix is
    # short. `_` is a single-character WILDCARD in SQL LIKE, so a bare
    # `qa_%` would also match `qax...` - and with the old seven-character
    # `qa_run_%` the literal text made a false match unlikely enough to
    # go unnoticed. Three characters is not that forgiving.
    rows = conn.execute(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name LIKE ? ESCAPE '!'",
        [RUN_SCHEMA_PREFIX.replace("_", "!_") + "%"]).fetchall()
    return sorted(r[0] for r in rows)


def drop_run_schemas(conn, run_id: str) -> list[str]:
    """Discard ONE run's own schemas - its views, and dbt's.

    CALLED WHEN THAT RUN FINISHES, which is a change from how this
    worked until 2026-09-27 (Keith's question: "shouldn't they be
    automatically discarded when the run is done, not separately later
    on?"). They used to be swept after the whole fan-out, and the
    reason was real at the time and is not any more: under DuckDB a
    drop took an exclusive lock over the WHOLE database, so a worker
    tidying up after itself would have locked out every other worker
    still reading. PostgreSQL locks the objects being dropped, so a run
    dropping its own schemas does not touch a sibling's.

    IT ALSO REMOVES A HAZARD the sweep could not avoid. A blanket sweep
    cannot tell a schema left behind by an interrupted run from one
    belonging to a run happening right now in another process, so it
    was liable to pull the floor out from under a concurrent ad-hoc
    check. Dropping only what this run created cannot.

    Returns what it dropped, and dropping a run that staged nothing is
    an ordinary no-op: a run that failed before staging still reaches
    its own tidy-up, and must not turn one failure into two.
    """
    present = set(run_schemas(conn)) | set(dbt_schemas(conn))
    # DBT MAKES TWO SCHEMAS PER RUN, not one - `--store-failures` puts
    # each failing test's offending rows in `<target_schema>_dbt_test__
    # audit`. Found by running the real pipeline, not by reading dbt's
    # configuration: the first version of this dropped only the target
    # schema and left eighteen audit schemas behind.
    #
    # EXACT, OR FOLLOWED BY AN UNDERSCORE. A bare prefix test would let
    # `run_001` take `run_0011` with it, which is the kind of quiet
    # collateral nobody would look for.
    base = dbt_schema(run_id)
    mine = {run_schema(run_id), base}
    mine |= {s for s in present if s.startswith(base + "_")}
    dropped = []
    for schema in sorted(mine):
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        if schema in present:
            dropped.append(schema)
    return dropped


def drop_orphan_run_schemas(conn, keep: Sequence[str] = ()) -> list[str]:
    """Remove every per-run schema except the ones named in `keep`.
    Returns what it dropped, so a caller can say so rather than tidying
    up silently.

    BOTH KINDS, since 2026-09-27: a run's view schema AND its dbt
    schema. dbt's became per-run the same day, and a per-run thing that
    nothing deletes is just a leak with a tidier name - at ~30 datasets
    on a quarterly cadence that would be thousands of abandoned schemas
    in a year.
    """
    spared = {run_schema(r) for r in keep} | {dbt_schema(r) for r in keep}
    dropped = []
    for schema in run_schemas(conn) + dbt_schemas(conn):
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
# dbt_schema(run_id) is where dbt's own models land. Named, not defaulted: dbt
# would otherwise use `public`, and a model sitting in `public` beside
# real supply schemas is exactly the ambiguity this design removes.
# ---------------------------------------------------------------------------

#: The prefix for dbt's own schemas - its models and its
#: --store-failures audit tables. Never a supply schema.
#:
#: ONE PER RUN, not one shared (2026-09-27). It was a single `dbt`
#: schema, on the reasoning that DuckDB's exclusive file lock was the
#: only thing the retired per-run scratch FILE had been working around,
#: and PostgreSQL has no such lock. That reasoning was wrong about
#: WHICH contention mattered: the file lock was about concurrent
#: writers to a database, and the real problem is concurrent writers to
#: the same TABLES. `dbt build` drops and recreates its models, so two
#: runs sharing a schema race - one reads `stg_birth_registrations`
#: while the other is rebuilding it, and gets "relation does not
#: exist". The retired file gave each run its own by construction; this
#: restores that, the same way dbt_target_path() already does for dbt's
#: on-disk artefacts.
DBT_SCHEMA_PREFIX = "dbt_"


def dbt_schema(run_id: str) -> str:
    """Where dbt's models and audit tables go for ONE run."""
    return DBT_SCHEMA_PREFIX + _ident(run_id, "run id")


def dbt_schemas(conn) -> list[str]:
    """Every per-run dbt schema currently in the database."""
    rows = conn.execute(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name LIKE ? ESCAPE '!'",
        [DBT_SCHEMA_PREFIX.replace("_", "!_") + "%"]).fetchall()
    return sorted(r[0] for r in rows)

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
