"""Each run's presentation-layer statistics, for any collection (REQ-PIPE-243):
row counts, value-count distributions, per-check aggregates of the failing
values, and when each table's rows were extracted.

COMPUTED HERE, ONCE, AT RUN TIME, and recorded (tool `dataset_stats`), because
this is the one point with a legitimate connection to the supply rows. Keith's
rule, 2026-09-27: a build may read recorded QA results, never actual data, and
never anything else - so nothing downstream ever needs a connection to the rows
again. The dashboard builds read these records instead.

BUILT FROM CHILD PROTECTION'S COPY: every table the run can read, each counted
on its own, and a table with no view left out rather than counted - which is
what "not measured" honestly looks like, since REQ-PIPE-105 a sibling can be
held, contested or filed elsewhere. What each collection measures is its
adapter's `.stats`; Birth Registrations' single-table copy differed in four
places, kept behind its legacy flags (qa_tools/tools/legacy.py).

THE ARRIVAL RECORD, NOT THE GENERATOR'S MANIFEST ENTRY (REQ-GEN-043 criterion
7): which run this is, when WE received it, which delivery it came from - an
allowlist, so a field added to the arrival later does not find its way into
the record without anybody deciding.
"""
from __future__ import annotations

from typing import Any

from pipeline.aggregate_values import categorical_aggregate, numeric_date_aggregate
from qa_tools import collections
from qa_tools.common import asset_time

__all__ = ["arrival_record", "compute_dataset_stats"]

_ARRIVAL_KEYS = ("run_id", "run_index", "received_at", "delivery")


def arrival_record(arrival: dict) -> dict:
    """The observed facts about one arrival, and nothing else."""
    return {key: arrival[key] for key in _ARRIVAL_KEYS if key in arrival}


def _readable(conn) -> frozenset[str]:
    """The tables this run's view schema actually holds."""
    return frozenset(row[0] for row in conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema()").fetchall())


class _Rows:
    """How a query is scoped to this run's rows: by the view schema alone, or
    - under `stats.rows_by_run_id` - also by the `run_id` every staged row
    carries (stage.stamps_run_columns)."""

    def __init__(self, run_id: str | None):
        self.run_id = run_id

    def where(self, condition: str | None = None) -> tuple[str, list]:
        parts = [f"({condition})"] if condition else []
        params: list = []
        if self.run_id is not None:
            parts.append("run_id = ?")
            params.append(self.run_id)
        return " AND ".join(parts), params


def _aggregate(conn, table: str, column: str, spec: dict, rows: _Rows) -> dict:
    run = categorical_aggregate if spec["kind"] == "categorical" else numeric_date_aggregate
    if rows.run_id is None:
        return run(conn, table, column, spec["invalid_condition"], spec["classification"])
    condition, params = rows.where(spec["invalid_condition"])
    return run(conn, table, column, condition, spec["classification"], params)


def _value_counts(conn, table: str, column: str, known: list[str], rows: _Rows) -> list[list]:
    """Every known value's count, ZEROS INCLUDED (REQ-QAC-247): a category
    that falls to zero shows as a 0 rather than vanishing from the chart."""
    condition, params = rows.where()
    sql = f"SELECT {column}, COUNT(*) FROM {table}"
    if condition:
        sql += f" WHERE {condition}"
    counts = {k: 0 for k in known}
    other = 0
    for value, n in conn.execute(f"{sql} GROUP BY {column}", params).fetchall():
        if value in counts:
            counts[value] += n
        else:
            other += n
    out = [[k, v] for k, v in counts.items()]
    if other:
        out.append(["(invalid code)", other])
    return out


def _earliest_extract(conn, table: str, rows: _Rows, after_registration: bool, what: str):
    condition, params = rows.where("extract_timestamp >= date_registered"
                                   if after_registration else None)
    sql = f"SELECT MIN(extract_timestamp) FROM {table}" + (f" WHERE {condition}" if condition else "")
    earliest = conn.execute(sql, params).fetchone()[0]
    if earliest is None and after_registration:
        # Every row extracted before it was registered: the earliest of all.
        condition, params = rows.where()
        sql = f"SELECT MIN(extract_timestamp) FROM {table}" + (f" WHERE {condition}" if condition else "")
        earliest = conn.execute(sql, params).fetchone()[0]
    return {"earliest_extract": asset_time.record_source_instant(earliest, what)}


def _count(conn, table: str, rows: _Rows) -> int:
    condition, params = rows.where()
    sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {condition}" if condition else "")
    return conn.execute(sql, params).fetchone()[0]


def compute_dataset_stats(collection_id: str, conn, entry: dict,
                          data_run_id: str | None = None) -> dict[str, Any]:
    """`conn` has this run's own view schema on its search path.

    `data_run_id` is the run whose id the rows carry, under
    `stats.rows_by_run_id`: a re-run reads the same supply, whose rows carry
    the first run's id in their own column (REQ-PIPE-140)."""
    coll = collections.by_id(collection_id)
    adapter = collections.adapter(coll)
    legacy, spec = adapter.legacy, adapter.stats
    tables = [d.table for d in coll.datasets]
    rows = _Rows((data_run_id or entry["run_id"]) if "stats.rows_by_run_id" in legacy else None)
    after_registration = "stats.arrival_after_registration" in legacy
    readable = _readable(conn)

    if "stats.single_table_shape" in legacy:
        [table] = tables
        if table not in readable:
            return {"arrival_record": arrival_record(entry), "row_count": None,
                    "value_counts": {}, "arrival": {}, "check_aggregates": {}}
        return {
            "arrival_record": arrival_record(entry),
            "row_count": _count(conn, table, rows),
            "value_counts": {col: _value_counts(conn, t, col, known, rows)
                             for (t, col), known in spec.value_counts.items()},
            "arrival": _earliest_extract(conn, table, rows, after_registration,
                                         f"earliest_extract for run {data_run_id or entry['run_id']}"),
            "check_aggregates": {col: _aggregate(conn, t, col, s, rows)
                                 for (t, col), s in spec.aggregates.items()},
        }
    return {
        "arrival_record": arrival_record(entry),
        "row_counts": {t: _count(conn, t, rows) for t in tables if t in readable},
        "value_counts": {col: _value_counts(conn, t, col, known, rows)
                         for (t, col), known in spec.value_counts.items() if t in readable},
        "check_aggregates": {f"{t}.{col}": _aggregate(conn, t, col, s, rows)
                             for (t, col), s in spec.aggregates.items() if t in readable},
        "arrival": {t: _earliest_extract(conn, t, rows, after_registration,
                                         f"earliest_extract for table {t}")
                    for t in tables if t in readable},
    }
