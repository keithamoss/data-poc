"""Smoke test for pipeline/build_cp_dashboard_data.py's reshaping logic,
against a small fixture rather than a real (slow) qa_tools/cp/
orchestrate_cp.py run - the Child Protection counterpart to
tests/test_build_dashboard_data.py. Calls build_one_table() directly
(no results_cp.json file needed) since that's the actual per-table
reshaping function under test."""
from __future__ import annotations

from pipeline import build_cp_dashboard_data as bcd

FIXTURE_RUNS = [
    {
        "run_id": "cp_run_01_2026-01-01", "run_index": 1, "run_date": "2026-01-01",
        "row_counts": {"cp_notifications": 3},
    },
    {
        "run_id": "cp_run_02_2026-04-01", "run_index": 2, "run_date": "2026-04-01",
        "row_counts": {"cp_notifications": 4},
    },
]

FIXTURE_DATASET_STATS = {
    # earliest_extract values deliberately placed relative to CP's real
    # quarterly cadence (contract/child-protection-contract.yaml's
    # slaProperties: - Feb/May/Aug/Nov day 1, 09:00 AWST, 8h latency
    # grace) rather than each run's own run_date, so
    # test_arrival_status_is_genuinely_computed_from_real_cadence below
    # can tell a real onTime/late classification apart from a hardcoded
    # one - see that test's own docstring.
    "cp_run_01_2026-01-01": {
        "value_counts": {"concern_type": [["Neglect", 2], ["Physical abuse", 1]]},
        "arrival": {"cp_notifications": {"max_lag_hours": 5.0, "earliest_extract": "2025-11-01T05:00:00+00:00"}},
        "check_aggregates": {},
    },
    "cp_run_02_2026-04-01": {
        "value_counts": {"concern_type": [["Neglect", 3], ["Physical abuse", 1]]},
        "arrival": {"cp_notifications": {"max_lag_hours": 30.0, "earliest_extract": "2026-02-01T20:00:00+00:00"}},
        "check_aggregates": {},
    },
}


def _check(run_id, column_name, value, status="pass", **overrides):
    rec = {
        "column_name": column_name, "check_name": "dbt:accepted_values",
        "dimension": "validity", "label": "Invalid values",
        "run_id": run_id, "metric_value": value, "unit": "count",
        "warn_threshold": 0.0, "fail_threshold": 5.0, "status": status,
        "row_count_total": 3, "row_count_invalid": 0,
        "engine": "dbt-core 1.12 + dbt-duckdb",
        "check_id": f"data-asset-1.child-protection-family-support.child-protection.cp-notifications.{column_name}.accepted_values_dbt",
    }
    rec.update(overrides)
    return rec


FIXTURE_RESULTS = [
    _check("cp_run_01_2026-01-01", "concern_type", 0),
    _check("cp_run_02_2026-04-01", "concern_type", 1, status="warn", row_count_invalid=1),
]


def test_stats_by_run_carries_every_run_not_just_latest_and_previous():
    dataset = bcd.build_one_table("cp_notifications", FIXTURE_RESULTS, FIXTURE_RUNS, FIXTURE_DATASET_STATS, {})

    col = next(c for c in dataset["columns"] if c["name"] == "concern_type")
    by_run = col["stats"]["byRun"]

    assert set(by_run) == {"cp_run_01_2026-01-01", "cp_run_02_2026-04-01"}
    assert by_run["cp_run_01_2026-01-01"] == {
        "total": 3, "invalid": 0, "valid": 3, "valueCounts": [["Neglect", 2], ["Physical abuse", 1]],
    }
    assert by_run["cp_run_02_2026-04-01"] == {
        "total": 4, "invalid": 1, "valid": 3, "valueCounts": [["Neglect", 3], ["Physical abuse", 1]],
    }
    # current/previous stay exactly as before, unaffected by byRun
    assert col["stats"]["current"]["valueCounts"] == [["Neglect", 3], ["Physical abuse", 1]]


def test_arrival_status_is_genuinely_computed_from_real_cadence():
    """arrivalStatus (Phase 5j, replacing the old hardcoded-then-max-lag-
    based onTime boolean) is a real classify_arrival() result against
    this collection's own real quarterly cadence (contract/child-
    protection-contract.yaml's slaProperties:) - not a hardcoded value.
    FIXTURE_DATASET_STATS' earliest_extract values are placed inside vs.
    well outside each run's own cycle's grace window specifically to
    prove that."""
    dataset = bcd.build_one_table("cp_notifications", FIXTURE_RESULTS, FIXTURE_RUNS, FIXTURE_DATASET_STATS, {})

    assert dataset["arrivalByRun"]["cp_run_01_2026-01-01"]["arrivalStatus"] == "onTime"
    assert dataset["arrivalByRun"]["cp_run_02_2026-04-01"]["arrivalStatus"] == "late"
    assert dataset["arrivalByRun"]["cp_run_02_2026-04-01"]["maxLagHours"] == 30.0
    history_by_run = {h["run_id"]: h["arrivalStatus"] for h in dataset["arrivalHistory"]}
    assert history_by_run == {"cp_run_01_2026-01-01": "onTime", "cp_run_02_2026-04-01": "late"}
