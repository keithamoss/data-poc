"""Smoke test for pipeline/build_dashboard_data.py's reshaping logic,
against a small fixture rather than a real (slow) real_tools/
orchestrate_real.py run - this is meant to catch the kind of silent
shape/crash regression a full pipeline run wouldn't surface quickly, not
to duplicate real_tools' own integration coverage."""
from __future__ import annotations

import json

import duckdb

import build_dashboard_data as bdd

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


def test_build_produces_one_entry_per_known_column(tmp_path, monkeypatch):
    results_path = tmp_path / "results_real.json"
    results_path.write_text(json.dumps({"runs": FIXTURE_RUNS, "results": FIXTURE_RESULTS}))

    db_path = tmp_path / "warehouse.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE birth_registrations (run_id VARCHAR, sex VARCHAR, date_registered DATE, extract_timestamp TIMESTAMP)")
    conn.execute("INSERT INTO birth_registrations VALUES "
                  "('run_01_2026-09-01', 'M', '2026-09-01', '2026-09-01 10:00:00'), "
                  "('run_01_2026-09-01', 'F', '2026-09-01', '2026-09-01 10:00:00'), "
                  "('run_01_2026-09-01', 'F', '2026-09-01', '2026-09-01 10:00:00'), "
                  "('run_02_2026-09-02', 'M', '2026-09-02', '2026-09-02 10:00:00'), "
                  "('run_02_2026-09-02', 'M', '2026-09-02', '2026-09-02 10:00:00'), "
                  "('run_02_2026-09-02', 'F', '2026-09-02', '2026-09-02 10:00:00'), "
                  "('run_02_2026-09-02', 'X', '2026-09-02', '2026-09-02 10:00:00')")
    conn.close()

    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(results_path))
    monkeypatch.setattr(bdd, "DB_PATH", str(db_path))

    data = bdd.build()

    assert [col["name"] for col in data["columns"]] == bdd.ALL_COLUMNS
    assert data["rowCount"] == 4  # latest run (run_02)'s n_rows_generated
    assert data["prevRowCount"] == 3


def test_a_column_with_a_real_check_carries_it_through(tmp_path, monkeypatch):
    results_path = tmp_path / "results_real.json"
    results_path.write_text(json.dumps({"runs": FIXTURE_RUNS, "results": FIXTURE_RESULTS}))
    db_path = tmp_path / "warehouse.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE birth_registrations (run_id VARCHAR, sex VARCHAR, date_registered DATE, extract_timestamp TIMESTAMP)")
    conn.execute("INSERT INTO birth_registrations VALUES "
                  "('run_01_2026-09-01', 'M', '2026-09-01', '2026-09-01 10:00:00'), "
                  "('run_02_2026-09-02', 'F', '2026-09-02', '2026-09-02 10:00:00')")
    conn.close()

    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(results_path))
    monkeypatch.setattr(bdd, "DB_PATH", str(db_path))

    data = bdd.build()
    sex_col = next(c for c in data["columns"] if c["name"] == "sex")
    assert len(sex_col["checks"]) == 1
    assert sex_col["checks"][0]["current"] == 1  # run_02's metric_value
    assert sex_col["checks"][0]["previous"] == 0  # run_01's metric_value
    assert len(sex_col["checks"][0]["history"]) == 2


def test_a_column_with_no_check_gets_an_honest_placeholder(tmp_path, monkeypatch):
    results_path = tmp_path / "results_real.json"
    results_path.write_text(json.dumps({"runs": FIXTURE_RUNS, "results": FIXTURE_RESULTS}))
    db_path = tmp_path / "warehouse.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE birth_registrations (run_id VARCHAR, sex VARCHAR, date_registered DATE, extract_timestamp TIMESTAMP)")
    conn.execute("INSERT INTO birth_registrations VALUES "
                  "('run_01_2026-09-01', 'M', '2026-09-01', '2026-09-01 10:00:00'), "
                  "('run_02_2026-09-02', 'F', '2026-09-02', '2026-09-02 10:00:00')")
    conn.close()

    monkeypatch.setattr(bdd, "REAL_RESULTS_PATH", str(results_path))
    monkeypatch.setattr(bdd, "DB_PATH", str(db_path))

    data = bdd.build()
    # No check in FIXTURE_RESULTS covers "date_registered" - should get the
    # honest placeholder, not a crash or a silently-empty checks list.
    uncovered = next(c for c in data["columns"] if c["name"] == "date_registered")
    assert uncovered["checks"][0]["name"] == "No automated quality rule defined"
