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
                     identity could disagree with itself.

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

  `qa.dataset_stats` the dashboard's presentation payload, as a JSONB
                     document. The ONE place this deliberately does not
                     normalise: its shape is the dashboard's, it changes
                     whenever a panel changes, and nothing else reads it,
                     so normalising would buy a migration per chart and
                     no query anybody runs.

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

#: Every column of `qa.check_result` that comes straight from a verified
#: record, in order. Anything a record carries that is NOT here lands in
#: `extra` - which is the behaviour that makes a new tool's own field
#: survive without a migration, and the reason this is an explicit list
#: rather than a set difference computed at the call site.
_RESULT_COLUMNS = (
    "agency_id", "collection_id", "dataset_id", "scope", "tool",
    "check_id", "check_name", "column_name", "dimension", "label",
    "status", "metric_value", "unit", "warn_threshold", "fail_threshold",
    "row_count_total", "row_count_invalid", "on_fail_action", "engine",
    "reference_run_id",
)

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
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "{SCHEMA}".check_result (
    id                bigserial PRIMARY KEY,
    run_key           text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    agency_id         text NOT NULL,
    collection_id     text NOT NULL,
    dataset_id        text,
    scope             text NOT NULL,
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
--   everything one run produced, and the FK's own lookups
CREATE INDEX IF NOT EXISTS check_result_run
    ON "{SCHEMA}".check_result (run_key);
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

CREATE TABLE IF NOT EXISTS "{SCHEMA}".dataset_stats (
    run_key    text NOT NULL REFERENCES "{SCHEMA}".run ON DELETE CASCADE,
    dataset_id text NOT NULL,
    stats      jsonb NOT NULL,
    PRIMARY KEY (run_key, dataset_id)
);
"""


def ensure_schema(conn: supply_db.SupplyConnection) -> None:
    """Create the metadata schema if it is not there.

    Idempotent, and safe to call from every writer rather than from one
    privileged setup step - which is deliberate: a pipeline that only
    works after somebody remembered to run a migration is a pipeline that
    fails on a new environment.
    """
    conn.raw.execute(DDL)


def record_run(conn: supply_db.SupplyConnection, *, run_key: str, agency_id: str,
               collection_id: str, run_timestamp: str, run_by: str,
               environment: str, tool_versions: Mapping[str, str] | None = None) -> None:
    """Register a run, or update it where it is re-run.

    ON CONFLICT rather than a prior existence check, because two workers
    in the same fan-out can legitimately reach this at the same moment -
    and a check-then-insert is a race with a nice-looking shape.
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


def record_results(conn: supply_db.SupplyConnection, run_key: str,
                   results: Sequence[Mapping[str, Any]], *, scope: str = "dataset") -> int:
    """Write one run's resolved check results. Returns how many landed.

    REPLACES THIS RUN'S RESULTS FOR THIS SCOPE rather than appending to
    them, so re-running a run is idempotent - the same reasoning the
    retired writer had for overwriting a file rather than accumulating
    versions inside one.
    """
    conn.execute(
        f'DELETE FROM "{SCHEMA}".check_result WHERE run_key = ? AND scope = ?',
        [run_key, scope])
    rows = 0
    for record in results:
        values = [record.get(name) for name in _RESULT_COLUMNS]
        extra = {k: v for k, v in record.items()
                 if k not in _RESULT_COLUMNS and k not in ("run_id", "run_timestamp")}
        placeholders = ", ".join(["?"] * (len(_RESULT_COLUMNS) + 2))
        conn.execute(
            f'INSERT INTO "{SCHEMA}".check_result '
            f'(run_key, {", ".join(_RESULT_COLUMNS)}, extra) VALUES ({placeholders})',
            [run_key, *values, json.dumps(extra, default=str)])
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
# indexes above have a fixed set of shapes to serve.
# ---------------------------------------------------------------------------

def results_for_run(conn: supply_db.SupplyConnection, run_key: str,
                    dataset_id: str | None = None) -> list[dict]:
    sql = (f'SELECT * FROM "{SCHEMA}".check_result WHERE run_key = ?')
    params: list[Any] = [run_key]
    if dataset_id is not None:
        sql += " AND dataset_id = ?"
        params.append(dataset_id)
    return _dicts(conn.execute(sql + " ORDER BY id", params))


def history_for_check(conn: supply_db.SupplyConnection, check_id: str,
                      dataset_id: str | None = None) -> list[dict]:
    """Every result this check has ever produced.

    The question the file tree could only answer by being walked in full,
    and the reason check_result_check_history exists.
    """
    sql = (f'SELECT r.*, run.run_timestamp FROM "{SCHEMA}".check_result r '
           f'JOIN "{SCHEMA}".run run USING (run_key) WHERE r.check_id = ?')
    params: list[Any] = [check_id]
    if dataset_id is not None:
        sql += " AND r.dataset_id = ?"
        params.append(dataset_id)
    return _dicts(conn.execute(sql + " ORDER BY run.run_timestamp, r.id", params))


def runs_for(conn: supply_db.SupplyConnection, agency_id: str,
             collection_id: str) -> list[dict]:
    return _dicts(conn.execute(
        f'SELECT * FROM "{SCHEMA}".run WHERE agency_id = ? AND collection_id = ? '
        "ORDER BY run_timestamp", [agency_id, collection_id]))


def dataset_stats_for(conn: supply_db.SupplyConnection, run_key: str,
                      dataset_id: str) -> dict | None:
    rows = conn.execute(
        f'SELECT stats FROM "{SCHEMA}".dataset_stats WHERE run_key = ? AND dataset_id = ?',
        [run_key, dataset_id]).fetchall()
    return rows[0][0] if rows else None


def _dicts(cursor) -> list[dict]:
    """Rows as dicts, keyed by the column names the query actually
    returned - never by a hand-maintained list, which is how a new column
    gets silently dropped on the way out."""
    columns = [d.name for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
