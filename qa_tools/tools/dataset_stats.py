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
from asset_model import collections as declared_collections

__all__ = ["allowed_lists", "arrival_record", "compute_dataset_stats"]

_ARRIVAL_KEYS = ("run_id", "run_index", "received_at", "delivery")


def arrival_record(arrival: dict) -> dict:
    """The observed facts about one arrival, and nothing else."""
    return {key: arrival[key] for key in _ARRIVAL_KEYS if key in arrival}


def _readable(conn) -> frozenset[str]:
    """The tables this run's view schema actually holds."""
    return frozenset(row[0] for row in conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema()").fetchall())


def allowed_lists(collection_id: str) -> dict[tuple[str, str], list]:
    """Each counted column's allowed values, read from the collection's ODCS
    contract once (REQ-QAC-389 criterion 1 and NFR PERFORMANCE). Raises
    contract_values.AllowedValuesError, naming the contract, the column and
    the fix, where a column has none or two that disagree - which the
    orchestrator asks before any tool runs (criterion 4)."""
    from asset_model import contract_values

    coll = declared_collections.by_id(collection_id)
    return contract_values.lists_for(coll.check_file("contract"),
                                     collections.adapter(coll).stats.counted_columns())


def _sql_literal(value) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def _invalid_condition(column: str, spec: dict, allowed: list | None) -> str:
    """A categorical column's values outside its contract list, or null; a
    numeric_date column's own declared condition."""
    if spec["kind"] != "categorical":
        return spec["invalid_condition"]
    return f"{column} NOT IN ({','.join(_sql_literal(v) for v in allowed)}) OR {column} IS NULL"


def _aggregate(conn, table: str, column: str, spec: dict, allowed: list | None) -> dict:
    run = categorical_aggregate if spec["kind"] == "categorical" else numeric_date_aggregate
    return run(conn, table, column, _invalid_condition(column, spec, allowed), spec["classification"])


def _value_counts(conn, table: str, column: str, known: list[str]) -> list[list]:
    """Every known value's count, ZEROS INCLUDED (REQ-QAC-247): a category
    that falls to zero shows as a 0 rather than vanishing from the chart -
    folded by evidently_common.fold_value_counts, which the generator's
    drift planning shares."""
    from asset_model.drift import fold_value_counts

    return fold_value_counts(conn.execute(
        f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column}").fetchall(), known)


def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _own_table(entry: dict) -> str | None:
    """The table the run is for: its arrival's dataset, else what its id says
    (run_owner) - None for a fixture's or a trial's run naming none."""
    from asset_model import hierarchy
    from qa_tools.common.qa_results_writer import run_owner

    try:
        if entry.get("dataset_id"):
            return hierarchy.dataset(entry["dataset_id"]).table
    except hierarchy.UnknownDatasetError:
        return None
    owner = run_owner(entry["run_id"]) if entry.get("run_id") else None
    return owner[1] if owner else None


def compute_dataset_stats(collection_id: str, conn, entry: dict,
                          lists: dict | None = None) -> dict[str, Any]:
    """`conn` has this run's own view schema on its search path, which holds
    exactly the arrival's rows - so nothing here scopes by a row column. A
    re-check's view resolves to the same supply (REQ-PIPE-140). `lists` is
    allowed_lists(), as the orchestrator read it before any tool ran; read
    here where a caller passes none."""
    coll = declared_collections.by_id(collection_id)
    spec = collections.adapter(coll).stats
    if lists is None:
        lists = allowed_lists(collection_id)
    tables = [d.table for d in coll.datasets]
    readable = _readable(conn)

    # A COLUMN SEVERAL TABLES DECLARE IS THE RUN'S OWN TABLE'S (REQ-QAC-297
    # criterion 11): value_counts is keyed by column, and the drift reference
    # and the page's value bars both read a run's counts for its own dataset.
    # So such a column is recorded only from the run's own table, and a run
    # owning none of them records none (post-build-review #299 item 1) - never
    # whichever table happened to come last.
    own = _own_table(entry)
    shared: dict[str, set] = {}
    for (t, col) in spec.value_counts:
        shared.setdefault(col, set()).add(t)
    declared = [((t, col), lists[(t, col)]) for (t, col) in spec.value_counts
                if len(shared[col]) == 1 or t == own]
    return {
        "arrival_record": arrival_record(entry),
        "row_counts": {t: _count(conn, t) for t in tables if t in readable},
        "value_counts": {col: _value_counts(conn, t, col, known)
                         for (t, col), known in declared if t in readable},
        "check_aggregates": {f"{t}.{col}": _aggregate(conn, t, col, s, lists.get((t, col)))
                             for (t, col), s in spec.aggregates.items() if t in readable},
    }
