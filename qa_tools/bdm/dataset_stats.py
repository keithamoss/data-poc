"""
Computes the presentation-layer data pipeline/build_dashboard_data.py
used to live-query a warehouse for: per-column value-count distributions,
arrival-lag stats, and per-check aggregate failing-value data (distinct
invalid values/histograms). Moved here from build_dashboard_data.py
2026-09-16 - Keith's hard rule, put explicitly: CI must never touch real
(or, in this PoC, even synthetic-standing-in-for-real) data. Computed
once here, at the point qa_tools.bdm.orchestrate_bdm.py already has a
live per-run warehouse connection for running the real tools, and
committed to qa_results/ (qa_results_writer.py, tool="dataset_stats") so
nothing downstream - Phase 2/3's dashboard-rebuild path included - ever
needs a live connection again. See plans/publishing-and-history.md's
Phase 3 write-up for the full scoping (3 rounds of questions with
Keith: fix scope, where it's committed, who writes it).

AGGREGATE_SPEC is the canonical definition of which columns get an
aggregate view and what "invalid" means for each - the exact same
valid-value lists dbt_project/models/staging/schema.yml's tests
enforce, so this module's notion of "invalid" can't silently drift from
what the real checks actually flag. `check_names` (which specific
check(s) on that column the aggregate attaches to for display) is only
meaningful to the dashboard-building layer - pipeline/
build_dashboard_data.py imports this same dict rather than keeping a
second copy, so the two can't drift apart either.
"""
from __future__ import annotations

from typing import Any

import duckdb

from pipeline.aggregate_values import categorical_aggregate, numeric_date_aggregate

_SEX_VALID = ["M", "F", "X"]
_SUBURB_VALID = ["Fremantle", "Subiaco", "Joondalup", "Rockingham", "Mandurah", "Midland", "Armadale", "Cannington",
                 "Morley", "Cockburn Central", "Scarborough", "Victoria Park", "Bunbury", "Albany", "Geraldton",
                 "Kalgoorlie", "Broome", "Karratha", "Port Hedland", "Busselton", "Northam", "Narrogin", "Esperance",
                 "Collie", "Mount Lawley", "Leederville", "Wembley", "Innaloo", "Success", "Baldivis", "Ellenbrook",
                 "Butler", "Balga", "Girrawheen", "Maddington", "Gosnells", "Kwinana", "Hamilton Hill",
                 "Beaconsfield", "South Perth", "Bentley", "Willetton", "Riverton", "Karrinyup", "Currambine",
                 "Clarkson", "Yanchep", "Byford", "Waroona", "Manjimup", "Margaret River"]


def _sql_list(values: list[str]) -> str:
    return ",".join("'" + v.replace("'", "''") + "'" for v in values)


AGGREGATE_SPEC = {
    "sex": {
        "kind": "categorical",
        "invalid_condition": f"sex NOT IN ({_sql_list(_SEX_VALID)}) OR sex IS NULL",
        "classification": None,
        "check_names": {"dbt:accepted_values", "invalid_percent[all]", "datacontract:invalid_count"},
    },
    "place_of_birth_suburb": {
        "kind": "categorical",
        "invalid_condition": f"place_of_birth_suburb NOT IN ({_sql_list(_SUBURB_VALID)}) OR place_of_birth_suburb IS NULL",
        "classification": None,
        "check_names": {"dbt:accepted_values", "invalid_percent[all]", "datacontract:invalid_count"},
    },
    "date_of_birth": {
        "kind": "numeric_date",
        "invalid_condition": "date_of_birth < DATE '1900-01-01'",
        "classification": None,
        "check_names": {"datacontract:custom_sql"},
    },
}


def _check_aggregates(conn: duckdb.DuckDBPyConnection, run_id: str) -> dict[str, dict]:
    out = {}
    for col, spec in AGGREGATE_SPEC.items():
        condition = f"({spec['invalid_condition']}) AND run_id = ?"
        if spec["kind"] == "categorical":
            out[col] = categorical_aggregate(conn, "birth_registrations", col, condition, spec["classification"], [run_id])
        else:
            out[col] = numeric_date_aggregate(conn, "birth_registrations", col, condition, spec["classification"], [run_id])
    return out


def _sex_value_counts(conn: duckdb.DuckDBPyConnection, run_id: str) -> list[list]:
    rows = conn.execute(
        "SELECT sex, COUNT(*) FROM birth_registrations WHERE run_id = ? GROUP BY sex", [run_id]
    ).fetchall()
    counts = {"M": 0, "F": 0, "X": 0}
    other = 0
    for val, c in rows:
        if val in counts:
            counts[val] += c
        else:
            other += c
    out = [[k, v] for k, v in counts.items()]
    if other:
        out.append(["(invalid code)", other])
    return out


def _arrival(conn: duckdb.DuckDBPyConnection, run_id: str) -> dict:
    max_lag_hours = conn.execute(
        """SELECT MAX(date_diff('second', date_registered, extract_timestamp)) / 3600.0
           FROM birth_registrations WHERE run_id = ?""", [run_id]
    ).fetchone()[0]
    # A real bug found 2026-09-17 (Phase 5j's arrival-status work): a
    # plain MIN(extract_timestamp) over every row picks up
    # generator.dirty.inject_extract_timestamp_disorder's own rows too -
    # deliberately shifted to BEFORE their row's date_registered, to give
    # the UNRELATED "extract timestamp ordering" check something real to
    # catch (rate_ts_disorder in generator/dirty.py, 1-4% of rows on any
    # amber/red-severity run). With thousands of rows per run, even a 1%
    # rate almost always plants at least one such row, so earliest_extract
    # was silently reporting the worst deliberately-corrupted outlier
    # rather than the batch's genuine earliest arrival - directly
    # distorting pipeline.cadence.classify_arrival()'s real early/onTime/
    # late classification (a run's arrival could read "early" by weeks
    # purely because one disordered row happened to land in it). Filtered
    # to `extract_timestamp >= date_registered` - the same "is this row's
    # timestamp even physically possible" test the ordering check itself
    # applies - so a run's genuine earliest arrival is used instead;
    # falls back to the unfiltered MIN only in the (currently unreachable
    # in this generator, but defensive) case where literally every row in
    # the run was disordered.
    earliest_extract = conn.execute(
        """SELECT MIN(extract_timestamp) FROM birth_registrations
           WHERE run_id = ? AND extract_timestamp >= date_registered""", [run_id]
    ).fetchone()[0]
    if earliest_extract is None:
        earliest_extract = conn.execute(
            "SELECT MIN(extract_timestamp) FROM birth_registrations WHERE run_id = ?", [run_id]
        ).fetchone()[0]
    return {"max_lag_hours": max_lag_hours, "earliest_extract": str(earliest_extract) if earliest_extract else None}


def compute_dataset_stats(conn: duckdb.DuckDBPyConnection, run_id: str, manifest_entry: dict) -> dict[str, Any]:
    """`conn` is a connection to the combined warehouse (birth_registrations
    table, tagged by run_id) - the same one build_dashboard_data.py used
    to open directly. `manifest_entry` is this run's own entry from
    data/raw/manifest.json (delivery date, resupply flags, etc.) -
    embedded here so it becomes part of committed history too, rather
    than build_results_from_history.py needing to keep reading local,
    regenerated data/raw/manifest.json on top of qa_results/."""
    return {
        "manifest_entry": manifest_entry,
        "value_counts": {"sex": _sex_value_counts(conn, run_id)},
        "arrival": _arrival(conn, run_id),
        "check_aggregates": _check_aggregates(conn, run_id),
    }
