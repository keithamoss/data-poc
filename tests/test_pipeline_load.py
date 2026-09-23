"""Tests for pipeline/load.py's load_all() - the combined-warehouse
loader build_dashboard_data.py's own direct DuckDB queries run against
(pipeline/orchestrate.py's own docstring). Reuses the shared bdm_raw_dir
fixture (tests/conftest.py) - real generator output, not hand-crafted
rows - with db_path/raw_dir both redirected to tmp_path, never touching
this project's own data/ directory."""
from __future__ import annotations

import duckdb

from fixture_ids import BDM_DIRTY_RUN_ID, BDM_REF_RUN_ID
from pipeline.load import TABLE, load_all


def test_load_all_builds_one_combined_table_across_both_runs(tmp_path, bdm_raw_dir, bdm_delivery_dirs):
    db_path = str(tmp_path / "warehouse.duckdb")
    deliveries, receipts = bdm_delivery_dirs

    # The delivery tree is passed EXPLICITLY (REQ-GEN-043). load_all()
    # recognises arrivals rather than reading a manifest, and raw_dir
    # is only scratch space now - so without these the test would load
    # the real data/deliveries/ tree instead of the fixture's two.
    load_all(db_path=db_path, raw_dir=bdm_raw_dir,
              deliveries_dir=deliveries, receipts_dir=receipts)

    conn = duckdb.connect(db_path)
    try:
        run_ids = [r[0] for r in conn.execute(f"SELECT DISTINCT run_id FROM {TABLE} ORDER BY run_id").fetchall()]
        assert run_ids == [BDM_REF_RUN_ID, BDM_DIRTY_RUN_ID]

        # the reference run is requested at 600 rows and the dirty run at 20
        # (conftest.bdm_raw_dir's own docstring), but generate_daily_batch()'s
        # multiple-birth handling and apply_birth_registrations_presets()'s own
        # injectors can each add extra real rows on top - so only relative size
        # (reference comfortably bigger than dirty) is asserted, not exact counts.
        counts = dict(conn.execute(f"SELECT run_id, COUNT(*) FROM {TABLE} GROUP BY run_id").fetchall())
        assert counts[BDM_REF_RUN_ID] > counts[BDM_DIRTY_RUN_ID]
        assert counts[BDM_DIRTY_RUN_ID] > 0

        # is_multiple_birth round-trips through CSV as "True"/"False" - stored as 0/1 ints, not strings
        distinct_values = {r[0] for r in conn.execute(f"SELECT DISTINCT is_multiple_birth FROM {TABLE}").fetchall()}
        assert distinct_values <= {0, 1}

        # dirty_severity used to be a real column here, carried in from
        # the generator's manifest. REQ-GEN-043 removed it: an injected
        # defect severity is generator bookkeeping, and the warehouse
        # the four real tools query must not be able to see which rows
        # were deliberately broken. Asserted as absent rather than just
        # dropped, so reintroducing it fails here.
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info('{TABLE}')").fetchall()}
        assert "dirty_severity" not in columns, \
            "the warehouse must not carry the generator's injected-defect label"

        # the run_id index load_all() creates
        indexes = [r[0] for r in conn.execute("SELECT index_name FROM duckdb_indexes()").fetchall()]
        assert any("run" in name for name in indexes)
    finally:
        conn.close()


def test_load_all_rebuilds_an_existing_db_file(tmp_path, bdm_raw_dir, bdm_delivery_dirs):
    """load_all() removes any pre-existing file at db_path before
    reconnecting (a stale warehouse.duckdb from a previous run) - only
    exercised by calling it twice against the same path."""
    db_path = str(tmp_path / "warehouse.duckdb")
    deliveries, receipts = bdm_delivery_dirs

    for _ in range(2):
        load_all(db_path=db_path, raw_dir=bdm_raw_dir,
                  deliveries_dir=deliveries, receipts_dir=receipts)

    conn = duckdb.connect(db_path)
    try:
        run_ids = [r[0] for r in conn.execute(f"SELECT DISTINCT run_id FROM {TABLE} ORDER BY run_id").fetchall()]
        assert run_ids == [BDM_REF_RUN_ID, BDM_DIRTY_RUN_ID]
    finally:
        conn.close()
