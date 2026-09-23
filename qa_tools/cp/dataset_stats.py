"""
Computes the presentation-layer data pipeline/build_cp_dashboard_data.py
used to live-query a per-run warehouse for: concern_type's value-count
distribution, per-check aggregate failing-value data (distinct invalid
values/histograms), and per-table arrival-lag stats - the Child
Protection counterpart to qa_tools/bdm/dataset_stats.py (see that
module's own docstring for the full rationale/history). Arrival is
computed PER TABLE here, not one dataset-level stat like BDM's -
build_cp_dashboard_data.py's build_one_table() computes it
independently for each of the 6 tables.

AGGREGATE_SPEC is the canonical definition, keyed by (table, column)
since CP has 6 tables - pipeline/build_cp_dashboard_data.py imports this
same dict for its `check_names` attach-decision, rather than keeping a
second copy.
"""
from __future__ import annotations

from typing import Any

import duckdb

from qa_tools.common import hierarchy
from qa_tools.common import asset_time
from pipeline.aggregate_values import categorical_aggregate, numeric_date_aggregate

# The six CP tables, in the order contract/data-asset.yaml declares
# them - resolved, not restated (REQ-QAC-039).
TABLES = [d.table for d in hierarchy.datasets_in_collection("child-protection")]

_POSTCODE_VALID = ["6007", "6008", "6014", "6018", "6019", "6027", "6028", "6030", "6035", "6036", "6050", "6056",
                    "6061", "6062", "6064", "6069", "6100", "6102", "6107", "6109", "6110", "6112", "6122", "6148",
                    "6151", "6155", "6160", "6162", "6163", "6164", "6167", "6168", "6171", "6210", "6215", "6225",
                    "6230", "6258", "6280", "6285", "6312", "6330", "6401", "6430", "6450", "6530", "6714", "6721",
                    "6725"]
_CONCERN_TYPE_VALID = ["Neglect", "Physical abuse", "Emotional abuse", "Sexual abuse",
                        "Domestic violence exposure", "Parental substance use", "Parental mental health concern"]


def _sql_list(values: list[str]) -> str:
    return ",".join("'" + v.replace("'", "''") + "'" for v in values)


AGGREGATE_SPEC = {
    ("cp_clients", "postcode"): {
        "kind": "categorical",
        "invalid_condition": f"postcode NOT IN ({_sql_list(_POSTCODE_VALID)}) OR postcode IS NULL",
        "classification": None,
        "check_names": {"dbt:accepted_values", "invalid_percent", "datacontract:invalid_count"},
    },
    ("cp_clients", "date_of_birth"): {
        "kind": "numeric_date",
        "invalid_condition": "date_of_birth < DATE '1900-01-01'",
        "classification": None,
        "check_names": {"dbt:cp_client_date_of_birth_range", "date_of_birth out of range"},
    },
    ("cp_notifications", "concern_type"): {
        "kind": "categorical",
        "invalid_condition": f"concern_type NOT IN ({_sql_list(_CONCERN_TYPE_VALID)}) OR concern_type IS NULL",
        "classification": None,
        "check_names": {"datacontract:invalid_count"},
    },
}


def _check_aggregates(conn: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    """Keyed by "table.column" (a string, not a tuple - this becomes JSON)."""
    out = {}
    for (table, col), spec in AGGREGATE_SPEC.items():
        full_table = f"raw.{table}"
        if spec["kind"] == "categorical":
            value = categorical_aggregate(conn, full_table, col, spec["invalid_condition"], spec["classification"])
        else:
            value = numeric_date_aggregate(conn, full_table, col, spec["invalid_condition"], spec["classification"])
        out[f"{table}.{col}"] = value
    return out


def _concern_type_value_counts(conn: duckdb.DuckDBPyConnection) -> list[list]:
    rows = conn.execute(
        "SELECT concern_type, COUNT(*) FROM raw.cp_notifications GROUP BY concern_type"
    ).fetchall()
    known = ["Neglect", "Physical abuse", "Emotional abuse", "Sexual abuse",
             "Domestic violence exposure", "Parental substance use", "Parental mental health concern"]
    counts = {k: 0 for k in known}
    other = 0
    for val, c in rows:
        if val in counts:
            counts[val] += c
        else:
            other += c
    out = [[k, v] for k, v in counts.items() if v]
    if other:
        out.append(["(invalid code)", other])
    return out


def _arrival(conn: duckdb.DuckDBPyConnection, run_date: str) -> dict[str, dict]:
    """Per table, not one dataset-level stat - build_cp_dashboard_data.py
    computes "extracted within 24h of the snapshot date" independently
    for each of the 6 tables (its own build_one_table() call), a real
    gap missed on the first pass at this module (found re-tracing the
    live-query call sites a second time, not assumed complete)."""
    out = {}
    for table in TABLES:
        max_lag_hours = conn.execute(
            f"SELECT MAX(date_diff('second', TIMESTAMP '{run_date}', extract_timestamp)) / 3600.0 "
            f"FROM raw.{table}"
        ).fetchone()[0]
        earliest_extract = conn.execute(f"SELECT MIN(extract_timestamp) FROM raw.{table}").fetchone()[0]
        out[table] = {"max_lag_hours": max_lag_hours,
                      "earliest_extract": asset_time.record_source_instant(
                          earliest_extract, f"earliest_extract for table {table}")}
    return out


def compute_dataset_stats(conn: duckdb.DuckDBPyConnection, manifest_entry: dict) -> dict[str, Any]:
    """`conn` is a connection to this run's own per-run warehouse
    (data/cp_duckdb_runs/<run_id>.duckdb, `raw` schema) - the same one
    build_cp_dashboard_data.py used to open directly per run. No run_id
    scoping needed in the queries themselves (unlike BDM's combined
    warehouse) - this file only ever holds this one run's data.
    `manifest_entry` is this run's own entry from data/cp_raw/
    manifest.json, embedded for the same reason dataset_stats.py's BDM
    counterpart does."""
    return {
        "manifest_entry": manifest_entry,
        "value_counts": {"concern_type": _concern_type_value_counts(conn)},
        "check_aggregates": _check_aggregates(conn),
        "arrival": _arrival(conn, asset_time.local_date(manifest_entry["received_at"]).isoformat()),
    }
