"""Real Soda Core integration test for qa_tools/cp/run_soda_cp.py's
evaluate_soda_cp() - the CP counterpart to tests/test_run_soda_bdm.py."""
from __future__ import annotations

import qa_tools.cp.run_soda_cp as run_soda_cp

from fixture_ids import CP_DIRTY_RUN_ID as _DIRTY_RUN_ID, CP_REF_RUN_ID as _REF_RUN_ID


def _run(monkeypatch, cp_duckdb_dir, run_id, run_timestamp):
    # The environment already points at this worker's database
    # (conftest's supply_dsn); cp_duckdb_dir is what staged the data into it.
    monkeypatch.setattr(run_soda_cp, "write_qa_result", lambda *a, **k: None)
    return run_soda_cp.evaluate_soda_cp(run_id, run_timestamp)


def test_clean_run_resolves_every_check_id_across_all_6_tables(monkeypatch, cp_duckdb_dir):
    results = _run(monkeypatch, cp_duckdb_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")

    assert results, "the real Soda scan produced no CP check results at all"
    assert all(r["check_id"] for r in results), "every result must resolve a real check_id (evaluate_soda_cp raises if not)"
    tables_seen = {r["dataset_id"] for r in results}
    assert len(tables_seen) > 1, "results should span more than one of the 6 real CP tables"
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real Soda failures: {failing}"


def test_dirty_run_produces_a_real_failure(monkeypatch, cp_duckdb_dir):
    results = _run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID, "2026-04-01T09:00:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty CP run produced no Soda failures at all"
