"""Tests for qa_tools/tools/dataset_stats.py, driven for each collection
- the presentation-layer computation moved out of pipeline/
the dashboard builders' own live queries
(plans/publishing-and-history.md Phase 3, Keith's hard rule: CI must
never touch data). Real small DuckDB fixtures, since these functions'
whole job is running real SQL - a mock wouldn't test anything real."""
from __future__ import annotations

import duckdb

from qa_tools import collections
from qa_tools.tools import dataset_stats

BDM, CP = "civil-registration", "child-protection"
CP_TABLES = [d.table for d in collections.by_id(CP).datasets]


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
    arrival = {"run_id": "run_01", "run_index": 1, "delivery": "BDM_20200105",
               "received_at": "2020-01-05T06:00:00+00:00",
               # Generator bookkeeping, deliberately offered to prove it
               # is dropped rather than carried (REQ-GEN-043 criterion 7).
               "dirty_severity": "red", "seed": 12345, "slot_id": "2020-01"}

    stats = dataset_stats.compute_dataset_stats(BDM, conn, arrival)

    assert stats["arrival_record"] == {"run_id": "run_01", "run_index": 1,
                                        "delivery": "BDM_20200105",
                                        "received_at": "2020-01-05T06:00:00+00:00"}
    assert stats["row_count"] == 3, "measured from the warehouse, not taken from the arrival"
    assert stats["value_counts"]["sex"] == [["M", 1], ["F", 1], ["X", 0], ["(invalid code)", 1]]
    assert stats["check_aggregates"]["sex"]["total_invalid"] == 1  # the 'Q' row
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

    stats = dataset_stats.compute_dataset_stats(BDM, conn, {"run_id": "run_01", "received_at": "2020-01-05T06:00:00+00:00"})

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

    arrival = dataset_stats.compute_dataset_stats(BDM, conn, {"run_id": "run_01"})["arrival"]

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

    arrival = dataset_stats.compute_dataset_stats(BDM, conn, {"run_id": "run_01"})["arrival"]

    assert arrival["earliest_extract"] == "2020-01-04T20:00:00+00:00"


def test_cp_compute_dataset_stats_shape():
    """The tables live in a RUN'S OWN VIEW SCHEMA, reached by search
    path, which is how the real caller reaches them since REQ-PIPE-068 -
    the orchestrator opens the supply database and sets the search path to
    this run's schema. They used to live in a schema literally named
    `raw`, which was the per-run database's own convention, and the
    module's SQL said `raw.<table>` to match."""
    from qa_tools.common import supply_db

    conn = duckdb.connect(":memory:")
    schema = supply_db.run_schema("cp_run_01")
    conn.execute(f'CREATE SCHEMA "{schema}"')
    conn.execute(f"SET search_path = '{schema}'")
    for table in CP_TABLES:
        conn.execute(f"""
            CREATE TABLE "{schema}".{table} (
                postcode VARCHAR, date_of_birth DATE, concern_type VARCHAR, extract_timestamp TIMESTAMP
            )
        """)
    conn.execute(f"""
        INSERT INTO "{schema}".cp_clients VALUES
        ('6007', '2020-01-01', NULL, '2020-01-05 10:00:00'),
        ('9999', '2020-01-01', NULL, '2020-01-05 11:00:00')
    """)
    conn.execute(f"""
        INSERT INTO "{schema}".cp_notifications VALUES
        (NULL, NULL, 'Neglect', '2020-01-05 09:00:00'),
        (NULL, NULL, 'Not a real category', '2020-01-05 09:30:00')
    """)
    arrival = {"run_id": "cp_run_01", "run_index": 1, "delivery": "cp-drop-1",
               "received_at": "2020-01-05T06:00:00+00:00",
               # As above - offered, and required not to survive.
               "dirty_severity": "red", "seed": 12345, "slot_id": "2020-01"}

    stats = dataset_stats.compute_dataset_stats(CP, conn, arrival)

    assert stats["arrival_record"] == {"run_id": "cp_run_01", "run_index": 1,
                                        "delivery": "cp-drop-1",
                                        "received_at": "2020-01-05T06:00:00+00:00"}
    # EVERY KNOWN VALUE, ZEROS INCLUDED (REQ-QAC-247, Keith 2026-10-18): a
    # category that falls to zero shows as a 0 rather than vanishing.
    from qa_tools.collections.child_protection import _CONCERN_TYPE_VALID
    assert stats["value_counts"]["concern_type"] == (
        [[k, 1 if k == "Neglect" else 0] for k in _CONCERN_TYPE_VALID] + [["(invalid code)", 1]])
    assert stats["check_aggregates"]["cp_clients.postcode"]["total_invalid"] == 1  # the '9999' row
    assert set(stats["arrival"].keys()) == set(CP_TABLES)


def test_cp_stats_leave_out_a_table_the_run_cannot_read():
    """REAL DEFECT, 2026-10-02. One file is one arrival (REQ-PIPE-105),
    so a run reads its siblings from its period and one can be absent -
    Case Workers' April file belongs to a different period from its
    siblings. compute_dataset_stats() counted all six unconditionally,
    raised UndefinedTable, and took the run down after every tool had
    recorded its results. Not measured is the honest answer."""
    from qa_tools.common import supply_db

    conn = duckdb.connect(":memory:")
    schema = supply_db.run_schema("cp_placements__202604010600000000")
    conn.execute(f'CREATE SCHEMA "{schema}"')
    conn.execute(f"SET search_path = '{schema}'")
    present = [t for t in CP_TABLES if t not in ("cp_case_workers", "cp_notifications")]
    for table in present:
        conn.execute(f'CREATE TABLE "{schema}".{table} (postcode VARCHAR, date_of_birth DATE, '
                     f'concern_type VARCHAR, extract_timestamp TIMESTAMP)')
    arrival = {"run_id": "r", "run_index": 1, "delivery": "d",
               "received_at": "2026-04-01T06:00:00+00:00"}

    stats = dataset_stats.compute_dataset_stats(CP, conn, arrival)

    assert set(stats["row_counts"]) == set(present)
    assert set(stats["arrival"]) == set(present)
    assert stats["value_counts"] == {}
    assert not any(k.startswith(("cp_case_workers.", "cp_notifications."))
                   for k in stats["check_aggregates"])
