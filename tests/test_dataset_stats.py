"""Tests for qa_tools/bdm/dataset_stats.py and qa_tools/cp/dataset_stats.py
- the presentation-layer computation moved out of pipeline/
build_dashboard_data.py's/build_cp_dashboard_data.py's own live queries
(plans/publishing-and-history.md Phase 3, Keith's hard rule: CI must
never touch data). Real small DuckDB fixtures, since these functions'
whole job is running real SQL - a mock wouldn't test anything real."""
from __future__ import annotations

import duckdb

from qa_tools.bdm import dataset_stats as bdm_stats
from qa_tools.cp import dataset_stats as cp_stats


def test_bdm_compute_dataset_stats_shape():
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE birth_registrations (
            run_id VARCHAR, sex VARCHAR, place_of_birth_suburb VARCHAR,
            date_of_birth DATE, date_registered DATE, extract_timestamp TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO birth_registrations VALUES
        ('run_01', 'M', 'Fremantle', '2020-01-01', '2020-01-05', '2020-01-05 10:00:00'),
        ('run_01', 'F', 'Fremantle', '2020-02-01', '2020-02-05', '2020-02-05 12:00:00'),
        ('run_01', 'Q', 'Fremantle', '2020-03-01', '2020-03-05', '2020-03-05 08:00:00'),
        ('run_02', 'M', 'Fremantle', '2021-01-01', '2021-01-05', '2021-01-05 10:00:00')
    """)
    manifest_entry = {"run_id": "run_01", "received_at": "2020-01-05T06:00:00+00:00"}

    stats = bdm_stats.compute_dataset_stats(conn, "run_01", manifest_entry)

    assert stats["manifest_entry"] == manifest_entry
    assert stats["value_counts"]["sex"] == [["M", 1], ["F", 1], ["X", 0], ["(invalid code)", 1]]
    assert stats["check_aggregates"]["sex"]["total_invalid"] == 1  # the 'Q' row
    assert stats["arrival"]["max_lag_hours"] is not None
    # scoped to run_01 only, not run_02's later data
    assert "2021" not in str(stats["arrival"]["earliest_extract"])


def test_bdm_check_aggregates_are_scoped_by_run_id():
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE birth_registrations (
            run_id VARCHAR, sex VARCHAR, place_of_birth_suburb VARCHAR,
            date_of_birth DATE, date_registered DATE, extract_timestamp TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO birth_registrations VALUES
        ('run_01', 'M', 'Fremantle', '2020-01-01', '2020-01-05', '2020-01-05 10:00:00'),
        ('run_02', 'Q', 'Fremantle', '2020-01-01', '2020-01-05', '2020-01-05 10:00:00')
    """)

    stats = bdm_stats.compute_dataset_stats(conn, "run_01", {"run_id": "run_01", "received_at": "2020-01-05T06:00:00+00:00"})

    # run_02's invalid 'Q' must not leak into run_01's own aggregate
    assert stats["check_aggregates"]["sex"]["total_invalid"] == 0


def test_bdm_earliest_extract_ignores_disordered_rows():
    """Real bug (2026-09-17, Phase 5j): generator.dirty.
    inject_extract_timestamp_disorder deliberately shifts a fraction of
    rows' extract_timestamp to BEFORE their own date_registered, so the
    unrelated 'extract timestamp ordering' check has something real to
    catch. A plain MIN(extract_timestamp) picked up those rows too,
    reporting a batch's earliest arrival as days/weeks earlier than any
    row genuinely arrived - silently distorting arrival-status
    classification. earliest_extract must skip rows where
    extract_timestamp < date_registered and report the genuine earliest
    arrival instead."""
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE birth_registrations (
            run_id VARCHAR, sex VARCHAR, place_of_birth_suburb VARCHAR,
            date_of_birth DATE, date_registered DATE, extract_timestamp TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO birth_registrations VALUES
        -- a disordered row: extract_timestamp BEFORE date_registered (the injected defect)
        ('run_01', 'M', 'Fremantle', '2020-01-01', '2020-01-05', '2020-01-04 20:00:00'),
        -- the genuine earliest arrival for this run
        ('run_01', 'F', 'Fremantle', '2020-01-01', '2020-01-05', '2020-01-05 09:00:00'),
        ('run_01', 'M', 'Fremantle', '2020-01-01', '2020-01-05', '2020-01-05 14:00:00')
    """)

    arrival = bdm_stats._arrival(conn, "run_01")

    assert arrival["earliest_extract"] == "2020-01-05T09:00:00+00:00"


def test_bdm_earliest_extract_falls_back_to_min_if_every_row_disordered():
    """Defensive edge case for the fix above: if EVERY row in a run were
    disordered (not currently reachable via the real generator's own
    rates, but the code shouldn't silently return no arrival data at
    all), earliest_extract falls back to the plain MIN rather than
    None."""
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE birth_registrations (
            run_id VARCHAR, sex VARCHAR, place_of_birth_suburb VARCHAR,
            date_of_birth DATE, date_registered DATE, extract_timestamp TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO birth_registrations VALUES
        ('run_01', 'M', 'Fremantle', '2020-01-01', '2020-01-05', '2020-01-04 20:00:00'),
        ('run_01', 'F', 'Fremantle', '2020-01-01', '2020-01-05', '2020-01-04 22:00:00')
    """)

    arrival = bdm_stats._arrival(conn, "run_01")

    assert arrival["earliest_extract"] == "2020-01-04T20:00:00+00:00"


def test_cp_compute_dataset_stats_shape():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE SCHEMA raw")
    for table in cp_stats.TABLES:
        conn.execute(f"""
            CREATE TABLE raw.{table} (
                postcode VARCHAR, date_of_birth DATE, concern_type VARCHAR, extract_timestamp TIMESTAMP
            )
        """)
    conn.execute("""
        INSERT INTO raw.cp_clients VALUES
        ('6007', '2020-01-01', NULL, '2020-01-05 10:00:00'),
        ('9999', '2020-01-01', NULL, '2020-01-05 11:00:00')
    """)
    conn.execute("""
        INSERT INTO raw.cp_notifications VALUES
        (NULL, NULL, 'Neglect', '2020-01-05 09:00:00'),
        (NULL, NULL, 'Not a real category', '2020-01-05 09:30:00')
    """)
    manifest_entry = {"run_id": "cp_run_01", "received_at": "2020-01-05T06:00:00+00:00"}

    stats = cp_stats.compute_dataset_stats(conn, manifest_entry)

    assert stats["manifest_entry"] == manifest_entry
    assert stats["value_counts"]["concern_type"] == [["Neglect", 1], ["(invalid code)", 1]]
    assert stats["check_aggregates"]["cp_clients.postcode"]["total_invalid"] == 1  # the '9999' row
    assert set(stats["arrival"].keys()) == set(cp_stats.TABLES)
    assert stats["arrival"]["cp_clients"]["max_lag_hours"] is not None
