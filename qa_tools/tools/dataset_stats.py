"""Each run's presentation-layer statistics, for any collection (REQ-PIPE-243):
row counts, value-count distributions and per-check aggregates of the
failing values. NOT when the rows were extracted: that was `earliest_extract`,
which nothing read once punctuality was measured from our own receipt
(pipeline/recorded_arrival.py), and REQ-QAC-247 stopped recording it.

COMPUTED HERE, ONCE, AT RUN TIME, and recorded (tool `dataset_stats`), because
this is the one point with a legitimate connection to the supply rows. Keith's
rule, 2026-09-27: a build may read recorded QA results, never actual data, and
never anything else - so nothing downstream ever needs a connection to the rows
again. The dashboard builds read these records instead.

BUILT FROM CHILD PROTECTION'S COPY: every table the run can read, each counted
on its own, and a table with no view left out rather than counted - which is
what "not measured" honestly looks like, since REQ-PIPE-105 a sibling can be
held, contested or filed elsewhere. What each collection measures is its
adapter's `.stats`; Birth Registrations' single-table shape went with
REQ-PIPE-248, so a one-table collection records `row_counts` by table and
aggregates keyed `table.column` like any other.

THE ARRIVAL RECORD, NOT THE GENERATOR'S MANIFEST ENTRY (REQ-GEN-043 criterion
7): which run this is, when WE received it, which delivery it came from - an
allowlist, so a field added to the arrival later does not find its way into
the record without anybody deciding.
"""
from __future__ import annotations

from typing import Any

from pipeline.aggregate_values import categorical_aggregate, numeric_date_aggregate
from qa_tools import collections

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


def _aggregate(conn, table: str, column: str, spec: dict) -> dict:
    run = categorical_aggregate if spec["kind"] == "categorical" else numeric_date_aggregate
    return run(conn, table, column, spec["invalid_condition"], spec["classification"])


def _value_counts(conn, table: str, column: str, known: list[str]) -> list[list]:
    """Every known value's count, ZEROS INCLUDED (REQ-QAC-247): a category
    that falls to zero shows as a 0 rather than vanishing from the chart."""
    counts = {k: 0 for k in known}
    other = 0
    for value, n in conn.execute(
            f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}").fetchall():
        if value in counts:
            counts[value] += n
        else:
            other += n
    out = [[k, v] for k, v in counts.items()]
    if other:
        out.append(["(invalid code)", other])
    return out


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def compute_dataset_stats(collection_id: str, conn, entry: dict) -> dict[str, Any]:
    """`conn` has this run's own view schema on its search path, which holds
    exactly the arrival's rows - so nothing here scopes by a row column. A
    re-check's view resolves to the same supply (REQ-PIPE-140)."""
    coll = collections.by_id(collection_id)
    spec = collections.adapter(coll).stats
    tables = [d.table for d in coll.datasets]
    readable = _readable(conn)

    return {
        "arrival_record": arrival_record(entry),
        "row_counts": {t: _count(conn, t) for t in tables if t in readable},
        "value_counts": {col: _value_counts(conn, t, col, known)
                         for (t, col), known in spec.value_counts.items() if t in readable},
        "check_aggregates": {f"{t}.{col}": _aggregate(conn, t, col, s)
                             for (t, col), s in spec.aggregates.items() if t in readable},
    }
