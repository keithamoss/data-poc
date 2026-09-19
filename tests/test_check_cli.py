"""Real integration tests for the Thread A on-demand CLIs
(qa_tools/bdm/check_file.py, qa_tools/cp/check_delivery.py) -
plans/running-thoughts.md #5, scoped 2026-09-19. Runs the real local
dbt/Soda/datacontract-cli/Evidently chain against the same small, real
fixture data tests/conftest.py already builds for the batch-path tests -
this sandbox has real access to those four tools."""
from __future__ import annotations
import os

import qa_tools.bdm.build_per_run_warehouses as build_per_run_warehouses
import qa_tools.bdm.check_file as check_file
import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
import qa_tools.bdm.run_datacontract_bdm as run_datacontract_bdm
import qa_tools.bdm.run_dbt_bdm as run_dbt_bdm
import qa_tools.bdm.run_evidently_bdm as run_evidently_bdm
import qa_tools.bdm.run_soda_bdm as run_soda_bdm
import qa_tools.cp.check_delivery as check_delivery
import qa_tools.cp.orchestrate_cp as orchestrate_cp

_REF_RUN_ID = "pytest_bdm_ref"
_DIRTY_RUN_ID = "pytest_bdm_dirty"
_CP_REF_RUN_ID = "pytest_cp_ref"
_CP_DIRTY_RUN_ID = "pytest_cp_dirty"


def _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir):
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", raw_dir)
    monkeypatch.setattr(build_per_run_warehouses, "OUT_DIR", duckdb_dir)
    monkeypatch.setattr(run_datacontract_bdm, "RAW_DIR", raw_dir)
    monkeypatch.setattr(run_evidently_bdm, "RAW_DIR", raw_dir)
    monkeypatch.setattr(run_dbt_bdm, "DUCKDB_RUNS_DIR", duckdb_dir)
    monkeypatch.setattr(run_soda_bdm, "DUCKDB_RUNS_DIR", duckdb_dir)


def test_check_file_cli_reports_real_failures_and_does_not_touch_the_real_committed_qa_results_dir(
        monkeypatch, tmp_path, capsys, bdm_raw_dir):
    raw_dir = str(tmp_path / "raw")
    duckdb_dir = str(tmp_path / "duckdb_runs")
    os.makedirs(raw_dir)
    _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir)

    from qa_tools.common.qa_results_writer import QA_RESULTS_DIR
    run_id = "adhoc_no_commit_test"
    real_committed_dir = QA_RESULTS_DIR / orchestrate_bdm.AGENCY_ID / orchestrate_bdm.DATASET_ID / run_id
    assert not real_committed_dir.exists(), "test precondition - this run_id must not already exist for real"

    exit_code = check_file.main([
        os.path.join(bdm_raw_dir, f"{_DIRTY_RUN_ID}.csv"),
        "--reference-csv", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--run-id", run_id,
        "--run-date", "2026-01-02",
    ])

    out = capsys.readouterr().out
    assert "fail" in out.lower()
    assert "local-only check" in out
    assert exit_code == 1, "a real red-severity dirty run should exit non-zero"
    assert not real_committed_dir.exists(), \
        "a default (non---commit) run must never write into the real, permanent qa_results/ history"


def test_check_file_cli_commit_flag_writes_into_the_real_qa_results_dir(monkeypatch, tmp_path, capsys, bdm_raw_dir):
    raw_dir = str(tmp_path / "raw")
    duckdb_dir = str(tmp_path / "duckdb_runs")
    os.makedirs(raw_dir)
    _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir)

    committed_root = tmp_path / "committed_qa_results"
    import functools
    from pathlib import Path

    from qa_tools.common.qa_results_writer import write_qa_result as real_write_qa_result
    patched = functools.partial(real_write_qa_result, results_dir=Path(committed_root))
    for mod in (orchestrate_bdm, run_dbt_bdm, run_soda_bdm, run_datacontract_bdm, run_evidently_bdm):
        monkeypatch.setattr(mod, "write_qa_result", patched)

    exit_code = check_file.main([
        os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--reference-csv", os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"),
        "--run-id", "adhoc_committed_test",
        "--run-date", "2026-01-01",
        "--commit",
    ])

    out = capsys.readouterr().out
    assert "local-only check" not in out
    assert exit_code == 0, "the clean reference run checked against itself should have no failures"
    assert (committed_root / "registry-services" / "birth-registrations" / "adhoc_committed_test" /
            "dataset_stats.json").exists()


def test_check_delivery_cli_reports_real_cp_failures(monkeypatch, tmp_path, capsys, cp_raw_dir, cp_duckdb_dir):
    import qa_tools.cp.run_datacontract_cp as run_datacontract_cp
    import qa_tools.cp.run_dbt_cp as run_dbt_cp
    import qa_tools.cp.run_evidently_cp as run_evidently_cp
    import qa_tools.cp.run_soda_cp as run_soda_cp

    monkeypatch.setattr(run_dbt_cp, "CP_DUCKDB_RUNS_DIR", cp_duckdb_dir)
    monkeypatch.setattr(run_soda_cp, "CP_DUCKDB_RUNS_DIR", cp_duckdb_dir)
    monkeypatch.setattr(run_datacontract_cp, "CP_RAW_DIR", cp_raw_dir)
    monkeypatch.setattr(run_evidently_cp, "CP_RAW_DIR", cp_raw_dir)
    monkeypatch.setattr(orchestrate_cp, "CP_DUCKDB_RUNS_DIR", cp_duckdb_dir)
    monkeypatch.setattr(check_delivery.build_cp_warehouses, "OUT_DIR", cp_duckdb_dir)
    monkeypatch.setattr(check_delivery.build_cp_warehouses, "CP_RAW_DIR", cp_raw_dir)

    exit_code = check_delivery.main([
        os.path.join(cp_raw_dir, _CP_DIRTY_RUN_ID),
        "--reference-folder", os.path.join(cp_raw_dir, _CP_REF_RUN_ID),
        "--run-date", "2026-04-01",
    ])

    out = capsys.readouterr().out
    assert "fail" in out.lower()
    assert "local-only check" in out
    assert exit_code == 1


def test_check_delivery_cli_errors_on_a_partial_delivery(tmp_path):
    partial = tmp_path / "partial_delivery"
    partial.mkdir()
    (partial / "cp_clients.csv").write_text("id\n1\n")
    # the other 5 real tables are deliberately missing

    import pytest
    with pytest.raises(SystemExit):
        check_delivery.main([str(partial), "--reference-folder", str(partial)])
