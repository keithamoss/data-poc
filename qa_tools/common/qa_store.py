"""QA results in the database (REQ-PIPE-089).

WHAT THIS REPLACES. Until now every QA run wrote JSON files under
`qa_results/<agency>/<collection>/<dataset>/<run_id>/<tool>.json`, and
those files were COMMITTED - the durable record of every check this
pipeline ever ran, potentially spanning years. That made the repository
hold state as well as configuration, which is the thing Keith settled
against on 2026-09-27: "the repository only contains configuration, not
actual state, no state at all."

WHY A DATABASE IS BETTER HERE, beyond tidiness. The question this history
exists to answer is "what has this check done over time", and a file tree
can only answer it by being walked in full. One index turns the same
question into a WHERE clause. Retention also becomes possible for the
first time - git cannot forget, a table can.

THE SHAPE, and the reasoning is recorded because reshaping it later
should be cheap. Keith delegated this call on 2026-09-27 ("take the
mindset of a senior engineer who cares about long-term stability... I can
come back and reshape it if I need to"), so it is decided rather than
surveyed.

  `qa.run`           one row per QA run; everything keys to it. A run
                     table rather than repeating a run's facts on every
                     result row, because that is the one place a run's
                     identity could disagree with itself. It is also
                     where completeness lives - see below.

  `qa.check_result`  the resolved verdicts, as REAL COLUMNS for what
                     every tool shares plus a JSONB `extra` for what one
                     tool has. Columns are what make the history query
                     cheap; the sidecar is what stops a fifth tool
                     (REQ-QAC-096's file checks) needing a migration to
                     record one field nothing else has.

  `qa.tool_output`   each tool's own unmodified payload, in a SEPARATE
                     table. These are the bulk and almost nothing reads
                     them - a real dbt run_results.json is large - so
                     keeping them beside the verdicts would make every
                     verdict query risk dragging megabytes it does not
                     want. One join gets it on the rare day somebody is
                     debugging a tool. It is also what makes retention
                     practical: the bulk can be dropped without touching
                     a single verdict.

  `qa.tables_read`   which physical table each logical name resolved to,
                     per run. ROWS rather than a document, and the
                     contrast with dataset_stats below is the whole
                     reasoning: this is a uniform triple answering "which
                     version of this table did that run read", which is
                     exactly the audit question worth being queryable
                     across years.

  `qa.dataset_stats` the dashboard's presentation payload, as a JSONB
                     document. The ONE place this deliberately does not
                     normalise: its shape is the dashboard's, it changes
                     whenever a panel changes, and nothing else reads it,
                     so normalising would buy a migration per chart and
                     no query anybody runs.

A RUN IS NOT OBSERVABLE UNTIL IT SAYS IT IS FINISHED (criterion 13).
`qa.run.completed_at` is NULL while a run is in flight and every read in
this module joins through it, so a half-written run is not a run with
fewer results - it is no run at all. This is a structure rather than a
convention on purpose: "every reader remembers to filter" is the same as
no filter at all on the day one of them forgets, and a partial run
reading as a finished one is the exact false-green shape this project
keeps finding. The `qa.*_visible` views carry the same rule for anything
reading over a grant rather than through this module, which is how the
dashboard build gets it for free (criteria 7 and 23).

RESULTS ARE KEYED BY (run, tool, scope, supply_state), and that tuple is
inherited rather than invented - it is what the retired tree keyed a FILE
by, plus the one dimension criterion 24 adds. Writing replaces exactly
that tuple, so re-running one tool is idempotent and does not disturb
another tool's verdicts from the same run. An earlier draft of this
module replaced by (run, scope) alone, which would have had Soda silently
delete dbt's results; `tests/test_qa_store.py` holds that case.

`metric_value` is `double precision` rather than `numeric` on purpose. It
is a measurement for display and comparison, never money - and numeric
would hand psycopg a Decimal, which is exactly the bug this engine switch
already produced once, where json.dumps refused one on the way out.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from qa_tools.common import supply_db

#: The one reserved metadata schema. Refused as an agency, collection or
#: dataset id by the same gate that refuses a leading underscore, so a
#: real dataset can never collide with it.
SCHEMA = "qa"

#: A result's scope. `DATASET` is a dataset's own verdict; `CROSS_TABLE`
#: is REQ-QAC-037's record that spans datasets and belongs to none of
#: them. The spellings match the retired tree's own directory names so a
#: reader moving between the two is not learning a second vocabulary.
DATASET_SCOPE = "dataset"
CROSS_TABLE_SCOPE = "_cross-table"

#: Whether a result describes an agreed supply or a dataset still being
#: developed against (criterion 24, decision 1). The second is excluded
#: from every read that a viewer would take as real quality history -
#: structurally, by being the default filter rather than by each caller
#: remembering. It is NOT discarded: developing a check is real work and
#: the person doing it has to be able to see the verdicts.
AGREED = "agreed"
IN_DEVELOPMENT = "in-development"

#: Every column of `qa.check_result` that comes straight from a verified
#: record, in order. Anything a record carries that is NOT here lands in
#: `extra` - which is the behaviour that makes a new tool's own field
#: survive without a migration, and the reason this is an explicit list
#: rather than a set difference computed at the call site.
_RESULT_COLUMNS = (
    "agency_id", "collection_id", "dataset_id", "tool",
    "check_id", "check_name", "column_name", "dimension", "label",
    "status", "metric_value", "unit", "warn_threshold", "fail_threshold",
    "row_count_total", "row_count_invalid", "on_fail_action", "engine",
    "reference_run_id",
)

#: Carried on the row rather than left to the record, because they key
#: the write. A record that names its own `tool` is trusted for the
#: column; the delete uses the argument either way, so a record whose
#: `tool` disagrees with the invocation cannot orphan itself.
_KEY_COLUMNS = ("scope", "supply_state")

DDL = f"""
CREATE SCHEMA IF NOT EXISTS "{SCHEMA}";

CREATE TABLE IF NOT EXISTS "{SCHEMA}".run (
    run_key        text PRIMARY KEY,
    agency_id      text NOT NULL,
    collection_id  text NOT NULL,
    run_timestamp  timestamptz NOT NULL,
    run_by         text NOT NULL,
    environment    text NOT NULL,
    tool_versions  jsonb NOT NULL DEFAULT '{{}}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    -- NULL while the run is in flight. Criterion 13 lives here.
    completed_at   timestamptz
);

CREATE INDEX IF NOT EXISTS run_completed
    ON "{SCHEMA}".run (completed_at) WHERE completed_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS "{SCHEMA}".check_result (
    id                bigserial PRIMARY KEY,
    run_key           text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    agency_id         text NOT NULL,
    collection_id     text NOT NULL,
    dataset_id        text,
    scope             text NOT NULL DEFAULT '{DATASET_SCOPE}',
    supply_state      text NOT NULL DEFAULT '{AGREED}',
    tool              text NOT NULL,
    check_id          text NOT NULL,
    check_name        text NOT NULL,
    column_name       text,
    dimension         text,
    label             text,
    status            text NOT NULL,
    metric_value      double precision,
    unit              text,
    warn_threshold    double precision,
    fail_threshold    double precision,
    row_count_total   bigint,
    row_count_invalid bigint,
    on_fail_action    text,
    engine            text,
    reference_run_id  text,
    extra             jsonb NOT NULL DEFAULT '{{}}'
);

-- Each index earns its place from a query that exists rather than from a
-- guess about one that might.
--   the check-history question this whole change is for
CREATE INDEX IF NOT EXISTS check_result_check_history
    ON "{SCHEMA}".check_result (check_id, run_key);
--   one dataset's results for one run, which is every dashboard page
CREATE INDEX IF NOT EXISTS check_result_dataset_run
    ON "{SCHEMA}".check_result (dataset_id, run_key);
--   the write key, which every record_results() call deletes by
CREATE INDEX IF NOT EXISTS check_result_write_key
    ON "{SCHEMA}".check_result (run_key, tool, scope, supply_state);
--   PARTIAL, because the interesting query is always the failures and
--   they are the minority - so the index stays small as history grows
CREATE INDEX IF NOT EXISTS check_result_not_passing
    ON "{SCHEMA}".check_result (dataset_id, check_id)
    WHERE status <> 'pass';

CREATE TABLE IF NOT EXISTS "{SCHEMA}".tool_output (
    run_key    text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    tool       text NOT NULL,
    dataset_id text NOT NULL DEFAULT '',
    raw_output jsonb NOT NULL,
    PRIMARY KEY (run_key, tool, dataset_id)
);

CREATE TABLE IF NOT EXISTS "{SCHEMA}".tables_read (
    run_key        text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    logical_table  text NOT NULL,
    physical_table text NOT NULL,
    PRIMARY KEY (run_key, logical_table)
);

--   "which runs read this table, in order" - the audit question
CREATE INDEX IF NOT EXISTS tables_read_logical
    ON "{SCHEMA}".tables_read (logical_table);

CREATE TABLE IF NOT EXISTS "{SCHEMA}".dataset_stats (
    run_key    text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    dataset_id text NOT NULL,
    stats      jsonb NOT NULL,
    PRIMARY KEY (run_key, dataset_id)
);

-- THE VISIBLE VIEWS carry criterion 13 for readers that come over a
-- GRANT rather than through this module - which is how the dashboard
-- build gets the rule for free (criteria 7 and 23). The publisher role
-- is granted these and never the base tables, so "only finished runs"
-- is something the database enforces rather than something a build
-- remembers.
CREATE OR REPLACE VIEW "{SCHEMA}".run_visible AS
    SELECT * FROM "{SCHEMA}".run WHERE completed_at IS NOT NULL;

CREATE OR REPLACE VIEW "{SCHEMA}".check_result_visible AS
    SELECT r.* FROM "{SCHEMA}".check_result r
    JOIN "{SCHEMA}".run ON run.run_key = r.run_key
    WHERE run.completed_at IS NOT NULL;

CREATE OR REPLACE VIEW "{SCHEMA}".tool_output_visible AS
    SELECT t.* FROM "{SCHEMA}".tool_output t
    JOIN "{SCHEMA}".run ON run.run_key = t.run_key
    WHERE run.completed_at IS NOT NULL;

CREATE OR REPLACE VIEW "{SCHEMA}".tables_read_visible AS
    SELECT t.* FROM "{SCHEMA}".tables_read t
    JOIN "{SCHEMA}".run ON run.run_key = t.run_key
    WHERE run.completed_at IS NOT NULL;

CREATE OR REPLACE VIEW "{SCHEMA}".dataset_stats_visible AS
    SELECT d.* FROM "{SCHEMA}".dataset_stats d
    JOIN "{SCHEMA}".run ON run.run_key = d.run_key
    WHERE run.completed_at IS NOT NULL;
"""


def ensure_schema(conn: supply_db.SupplyConnection) -> None:
    """Create the metadata schema if it is not there.

    Idempotent, and safe to call from every writer rather than from one
    privileged setup step - which is deliberate: a pipeline that only
    works after somebody remembered to run a migration is a pipeline that
    fails on a new environment.
    """
    conn.raw.execute(DDL)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def record_run(conn: supply_db.SupplyConnection, *, run_key: str, agency_id: str,
               collection_id: str, run_timestamp: str, run_by: str,
               environment: str, tool_versions: Mapping[str, str] | None = None) -> None:
    """Register a run, or update it where it is re-run.

    ON CONFLICT rather than a prior existence check, because two workers
    in the same fan-out can legitimately reach this at the same moment -
    and a check-then-insert is a race with a nice-looking shape.

    IT DOES NOT TOUCH `completed_at`, so registering a run that already
    finished does not quietly un-finish it; `reopen_run` is the explicit
    way to do that and says so at the call site.
    """
    conn.execute(
        f'INSERT INTO "{SCHEMA}".run '
        "(run_key, agency_id, collection_id, run_timestamp, run_by, environment, tool_versions) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (run_key) DO UPDATE SET "
        "run_timestamp = EXCLUDED.run_timestamp, run_by = EXCLUDED.run_by, "
        "environment = EXCLUDED.environment, tool_versions = EXCLUDED.tool_versions",
        [run_key, agency_id, collection_id, run_timestamp, run_by, environment,
         json.dumps(dict(tool_versions or {}))])


def complete_run(conn: supply_db.SupplyConnection, run_key: str) -> None:
    """Mark a run finished, which is what makes its results observable.

    The one place completeness flips, which is why the run is a table at
    all (decision 2). Without it, completeness has to be inferred by
    counting results against an expectation - and an expectation that
    can be wrong is how a partial run reads as a finished one.
    """
    conn.execute(f'UPDATE "{SCHEMA}".run SET completed_at = now() WHERE run_key = ?',
                 [run_key])


def reopen_run(conn: supply_db.SupplyConnection, run_key: str) -> None:
    """Put a finished run back in flight, for a re-run.

    Re-running is a real thing this pipeline does, so the marker must not
    latch - but it has to be deliberate, because the alternative is
    `record_run` silently un-finishing a run somebody is reading.
    """
    conn.execute(f'UPDATE "{SCHEMA}".run SET completed_at = NULL WHERE run_key = ?',
                 [run_key])


def record_results(conn: supply_db.SupplyConnection, run_key: str,
                   results: Sequence[Mapping[str, Any]], *, tool: str,
                   scope: str = DATASET_SCOPE,
                   supply_state: str = AGREED) -> int:
    """Write one tool's resolved check results. Returns how many landed.

    REPLACES THIS (run, tool, scope, supply_state) rather than appending,
    so re-running one tool is idempotent - the same reasoning the retired
    writer had for overwriting a file rather than accumulating versions
    inside one, and the same key that file had.
    """
    conn.execute(
        f'DELETE FROM "{SCHEMA}".check_result '
        "WHERE run_key = ? AND tool = ? AND scope = ? AND supply_state = ?",
        [run_key, tool, scope, supply_state])
    columns = ("run_key", *_RESULT_COLUMNS, *_KEY_COLUMNS, "extra")
    placeholders = ", ".join(["?"] * len(columns))
    rows = 0
    for record in results:
        values = [record.get(name) for name in _RESULT_COLUMNS]
        # The invocation's tool wins over the record's, so a record that
        # names a different one cannot land outside the tuple the delete
        # above would clear - which is how a row orphans itself.
        values[_RESULT_COLUMNS.index("tool")] = tool
        extra = {k: v for k, v in record.items()
                 if k not in _RESULT_COLUMNS and k not in ("run_id", "run_timestamp")}
        conn.execute(
            f'INSERT INTO "{SCHEMA}".check_result ({", ".join(columns)}) '
            f"VALUES ({placeholders})",
            [run_key, *values, scope, supply_state, json.dumps(extra, default=str)])
        rows += 1
    return rows


def record_tool_output(conn: supply_db.SupplyConnection, run_key: str, tool: str,
                       raw_output: Any, dataset_id: str | None = None) -> None:
    """Keep a tool's own unmodified payload."""
    conn.execute(
        f'INSERT INTO "{SCHEMA}".tool_output (run_key, tool, dataset_id, raw_output) '
        "VALUES (?, ?, ?, ?) ON CONFLICT (run_key, tool, dataset_id) "
        "DO UPDATE SET raw_output = EXCLUDED.raw_output",
        [run_key, tool, dataset_id or "", json.dumps(raw_output, default=str)])


def record_tables_read(conn: supply_db.SupplyConnection, run_key: str,
                       resolved: Mapping[str, str]) -> None:
    """Record which physical table each logical name resolved to."""
    for logical, physical in sorted(resolved.items()):
        conn.execute(
            f'INSERT INTO "{SCHEMA}".tables_read (run_key, logical_table, physical_table) '
            "VALUES (?, ?, ?) ON CONFLICT (run_key, logical_table) "
            "DO UPDATE SET physical_table = EXCLUDED.physical_table",
            [run_key, logical, physical])


def record_dataset_stats(conn: supply_db.SupplyConnection, run_key: str,
                         dataset_id: str, stats: Mapping[str, Any]) -> None:
    """Keep the dashboard's presentation payload for one dataset."""
    conn.execute(
        f'INSERT INTO "{SCHEMA}".dataset_stats (run_key, dataset_id, stats) '
        "VALUES (?, ?, ?) ON CONFLICT (run_key, dataset_id) "
        "DO UPDATE SET stats = EXCLUDED.stats",
        [run_key, dataset_id, json.dumps(stats, default=str)])


# ---------------------------------------------------------------------------
# Reading it back
#
# These are the queries the retired file-tree reader had to walk the tree
# to answer. Each one is here rather than assembled at a call site so the
# indexes above have a fixed set of shapes to serve - and so that
# criterion 13's join is in one place rather than in every caller.
# ---------------------------------------------------------------------------

def results_for_run(conn: supply_db.SupplyConnection, run_key: str,
                    dataset_id: str | None = None, *,
                    scope: str = DATASET_SCOPE,
                    supply_state: str | None = AGREED) -> list[dict]:
    """One run's verdicts. Only a finished run has any.

    `supply_state` defaults to AGREED rather than to everything, so a
    caller has to ASK for in-development verdicts to see them - criterion
    24 the way round that fails safe.
    """
    sql = (f'SELECT r.* FROM "{SCHEMA}".check_result_visible r '
           "WHERE r.run_key = ? AND r.scope = ?")
    params: list[Any] = [run_key, scope]
    if supply_state is not None:
        sql += " AND r.supply_state = ?"
        params.append(supply_state)
    if dataset_id is not None:
        sql += " AND r.dataset_id = ?"
        params.append(dataset_id)
    return _dicts(conn.execute(sql + " ORDER BY r.id", params))


def cross_table_results(conn: supply_db.SupplyConnection, run_key: str, *,
                        supply_state: str | None = AGREED) -> list[dict]:
    """The records that span datasets and belong to none of them."""
    return results_for_run(conn, run_key, scope=CROSS_TABLE_SCOPE,
                           supply_state=supply_state)


def history_for_check(conn: supply_db.SupplyConnection, check_id: str,
                      dataset_id: str | None = None, *,
                      supply_state: str | None = AGREED) -> list[dict]:
    """Every result this check has ever produced.

    The question the file tree could only answer by being walked in full,
    and the reason check_result_check_history exists.
    """
    sql = (f'SELECT r.*, run.run_timestamp FROM "{SCHEMA}".check_result_visible r '
           f'JOIN "{SCHEMA}".run_visible run USING (run_key) WHERE r.check_id = ?')
    params: list[Any] = [check_id]
    if supply_state is not None:
        sql += " AND r.supply_state = ?"
        params.append(supply_state)
    if dataset_id is not None:
        sql += " AND r.dataset_id = ?"
        params.append(dataset_id)
    return _dicts(conn.execute(sql + " ORDER BY run.run_timestamp, r.id", params))


def runs_for(conn: supply_db.SupplyConnection, agency_id: str,
             collection_id: str) -> list[dict]:
    return _dicts(conn.execute(
        f'SELECT * FROM "{SCHEMA}".run_visible WHERE agency_id = ? AND collection_id = ? '
        "ORDER BY run_timestamp", [agency_id, collection_id]))


def incomplete_runs(conn: supply_db.SupplyConnection) -> list[str]:
    """Runs that started and never said they finished.

    Invisible to a reader of RESULTS is not invisible full stop - an
    operator has to be able to find the wreckage of a crashed run, and
    this is the only thing that can see it.
    """
    return [row[0] for row in conn.execute(
        f'SELECT run_key FROM "{SCHEMA}".run WHERE completed_at IS NULL '
        "ORDER BY created_at").fetchall()]


def tables_read_for_run(conn: supply_db.SupplyConnection, run_key: str) -> dict[str, str]:
    """{logical table: the physical table this run actually read}."""
    return {logical: physical for logical, physical in conn.execute(
        f'SELECT logical_table, physical_table FROM "{SCHEMA}".tables_read_visible '
        "WHERE run_key = ? ORDER BY logical_table", [run_key]).fetchall()}


def table_history(conn: supply_db.SupplyConnection, logical_table: str) -> list[dict]:
    """Which version of one logical table each run read, oldest first."""
    return _dicts(conn.execute(
        f'SELECT t.*, run.run_timestamp FROM "{SCHEMA}".tables_read_visible t '
        f'JOIN "{SCHEMA}".run_visible run USING (run_key) WHERE t.logical_table = ? '
        "ORDER BY run.run_timestamp", [logical_table]))


def tool_output_for(conn: supply_db.SupplyConnection, run_key: str, tool: str,
                    dataset_id: str | None = None) -> Any:
    """One tool's own unmodified payload, on the rare day somebody wants it."""
    rows = conn.execute(
        f'SELECT raw_output FROM "{SCHEMA}".tool_output_visible '
        "WHERE run_key = ? AND tool = ? AND dataset_id = ?",
        [run_key, tool, dataset_id or ""]).fetchall()
    return rows[0][0] if rows else None


def dataset_stats_for(conn: supply_db.SupplyConnection, run_key: str,
                      dataset_id: str) -> dict | None:
    rows = conn.execute(
        f'SELECT stats FROM "{SCHEMA}".dataset_stats_visible '
        "WHERE run_key = ? AND dataset_id = ?",
        [run_key, dataset_id]).fetchall()
    return rows[0][0] if rows else None


def _dicts(cursor) -> list[dict]:
    """Rows as dicts, keyed by the column names the query actually
    returned - never by a hand-maintained list, which is how a new column
    gets silently dropped on the way out."""
    columns = [d.name for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
