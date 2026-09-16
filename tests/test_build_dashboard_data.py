"""Smoke test for pipeline/build_dashboard_data.py's reshaping logic,
against a small fixture rather than a real (slow) qa_tools/bdm/
orchestrate_bdm.py run - this is meant to catch the kind of silent
shape/crash regression a full pipeline run wouldn't surface quickly, not
to duplicate qa_tools' own integration coverage.

No real DuckDB warehouse here since Phase 3 (plans/publishing-and-
history.md) - value-counts/arrival/check-aggregate data comes from
results_bdm.json's own "dataset_stats" key now (qa_tools/bdm/
dataset_stats.py's precomputed output), not a live query."""
from __future__ import annotations

import json

from pipeline import build_dashboard_data as bdd

FIXTURE_RUNS = [
    {
        "run_id": "run_01_2026-09-01", "run_index": 1, "delivery_id": "delivery_01",
        "run_date": "2026-09-01", "n_rows_generated": 3, "dirty_severity": None,
    },
    {
        "run_id": "run_02_2026-09-02", "run_index": 2, "delivery_id": "delivery_02",
        "run_date": "2026-09-02", "n_rows_generated": 4, "dirty_severity": "amber",
    },
]

FIXTURE_DATASET_STATS = {
    "run_01_2026-09-01": {
        "manifest_entry": FIXTURE_RUNS[0],
        "value_counts": {"sex": [["M", 1], ["F", 2], ["X", 0]]},
        "arrival": {"max_lag_hours": 5.0, "earliest_extract": "2026-09-01 10:00:00"},
        "check_aggregates": {"sex": {"type": "categorical", "suppressed": False, "total_invalid": 0, "values": []}},
    },
    "run_02_2026-09-02": {
        "manifest_entry": FIXTURE_RUNS[1],
        "value_counts": {"sex": [["M", 2], ["F", 1], ["X", 1]]},
        "arrival": {"max_lag_hours": 6.0, "earliest_extract": "2026-09-02 10:00:00"},
        "check_aggregates": {"sex": {"type": "categorical", "suppressed": False, "total_invalid": 1,
                                      "values": [{"value": "X", "count": 1}]}},
    },
}


def _check(run_id, column_name, value, status="pass", **overrides):
    rec = {
        "column_name": column_name, "check_name": "dbt:accepted_values",
        "dimension": "validity", "label": "Invalid values",
        "run_id": run_id, "metric_value": value, "unit": "count",
        "warn_threshold": 0.0, "fail_threshold": 5.0, "status": status,
        "row_count_total": 3, "row_count_invalid": 0,
        "engine": "dbt-core 1.12 + dbt-duckdb (real)",
    }
    rec.update(overrides)
    return rec


FIXTURE_RESULTS = [
    _check("run_01_2026-09-01", "sex", 0),
    _check("run_02_2026-09-02", "sex", 1, status="warn", row_count_invalid=1),
]


def _write_results(tmp_path):
    results_path = tmp_path / "results_bdm.json"
    results_path.write_text(json.dumps({
        "runs": FIXTURE_RUNS, "results": FIXTURE_RESULTS, "dataset_stats": FIXTURE_DATASET_STATS,
    }))
    return results_path


def test_build_produces_one_entry_per_known_column(tmp_path, monkeypatch):
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()

    assert [col["name"] for col in data["columns"]] == bdd.ALL_COLUMNS
    assert data["rowCount"] == 4  # latest run (run_02)'s n_rows_generated
    assert data["prevRowCount"] == 3


def test_a_column_with_a_real_check_carries_it_through(tmp_path, monkeypatch):
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()
    sex_col = next(c for c in data["columns"] if c["name"] == "sex")
    assert len(sex_col["checks"]) == 1
    assert sex_col["checks"][0]["current"] == 1  # run_02's metric_value
    assert sex_col["checks"][0]["previous"] == 0  # run_01's metric_value
    assert len(sex_col["checks"][0]["history"]) == 2
    # aggregate_values attached from dataset_stats, not a live query
    assert sex_col["checks"][0]["history"][-1]["aggregate_values"]["total_invalid"] == 1
    assert sex_col["stats"]["current"]["valueCounts"] == [["M", 2], ["F", 1], ["X", 1]]


def test_a_column_with_no_check_gets_an_honest_placeholder(tmp_path, monkeypatch):
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()
    # No check in FIXTURE_RESULTS covers "date_registered" - should get the
    # honest placeholder, not a crash or a silently-empty checks list.
    uncovered = next(c for c in data["columns"] if c["name"] == "date_registered")
    assert uncovered["checks"][0]["name"] == "No automated quality rule defined"


def test_stats_by_run_carries_every_run_not_just_latest_and_previous(tmp_path, monkeypatch):
    """Phase 4 prerequisite (plans/publishing-and-history.md Thread C):
    stats["current"]/["previous"] stay exactly as before, but stats
    ["byRun"] now carries every run, keyed by run_id - the actual data
    Thread C's as-of picker will need."""
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(_write_results(tmp_path)))

    data = bdd.build()
    sex_col = next(c for c in data["columns"] if c["name"] == "sex")
    by_run = sex_col["stats"]["byRun"]

    assert set(by_run) == {"run_01_2026-09-01", "run_02_2026-09-02"}
    # run_01 is clean (metric_value 0) - matches "previous" above
    assert by_run["run_01_2026-09-01"] == {
        "total": 3, "invalid": 0, "valid": 3, "valueCounts": [["M", 1], ["F", 2], ["X", 0]],
    }
    # run_02 matches "current" above (metric_value 1)
    assert by_run["run_02_2026-09-02"] == {
        "total": 4, "invalid": 1, "valid": 3, "valueCounts": [["M", 2], ["F", 1], ["X", 1]],
    }
    # a column with no real check (the honest-placeholder path) still
    # gets a byRun entry per run, all zero - never crashes or gets skipped
    uncovered = next(c for c in data["columns"] if c["name"] == "date_registered")
    assert set(uncovered["stats"]["byRun"]) == {"run_01_2026-09-01", "run_02_2026-09-02"}


def test_arrival_by_run_is_genuinely_computed_not_hardcoded_true(tmp_path, monkeypatch):
    """A real bug fixed alongside the byRun work: arrivalHistory's onTime
    used to be hardcoded True for every run but the latest, even though
    every run's own max_lag_hours already existed to compute it for
    real. A run with a real >24h lag must now show onTime=False."""
    late_stats = json.loads(json.dumps(FIXTURE_DATASET_STATS))
    late_stats["run_01_2026-09-01"]["arrival"]["max_lag_hours"] = 30.0
    results_path = tmp_path / "results_bdm.json"
    results_path.write_text(json.dumps({
        "runs": FIXTURE_RUNS, "results": FIXTURE_RESULTS, "dataset_stats": late_stats,
    }))
    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(results_path))

    data = bdd.build()

    assert data["arrivalByRun"]["run_01_2026-09-01"]["onTime"] is False
    assert data["arrivalByRun"]["run_01_2026-09-01"]["maxLagHours"] == 30.0
    assert data["arrivalByRun"]["run_02_2026-09-02"]["onTime"] is True
    history_by_run = {h["run_id"]: h["onTime"] for h in data["arrivalHistory"]}
    assert history_by_run == {"run_01_2026-09-01": False, "run_02_2026-09-02": True}
