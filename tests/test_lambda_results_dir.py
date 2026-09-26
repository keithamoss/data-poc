"""Tests for qa_tools/common/lambda_results_dir.py - see its own
docstring for the real Lambda-writability gap this exists to fix."""
from __future__ import annotations

import qa_tools.bdm.run_dbt_bdm as run_dbt_bdm
import qa_tools.cp.run_dbt_cp as run_dbt_cp
from qa_tools.common.tables_read import RAW_SCOPE
from qa_tools.common.lambda_results_dir import patch_write_qa_result_for_lambda


def test_patch_write_qa_result_for_lambda_redirects_a_bdm_module_to_the_given_root(tmp_path):
    original = run_dbt_bdm.write_qa_result
    try:
        patch_write_qa_result_for_lambda(["qa_tools.bdm.run_dbt_bdm"], str(tmp_path))

        out_path = run_dbt_bdm.write_qa_result("agency", "dataset", "run_01", "2026-01-01T00:00:00Z", "dbt",
                                                {"ok": True})

        assert str(out_path).startswith(str(tmp_path))
        assert out_path.exists()
    finally:
        run_dbt_bdm.write_qa_result = original


def test_patch_write_qa_result_for_lambda_can_target_multiple_modules_independently(tmp_path):
    original_bdm = run_dbt_bdm.write_qa_result
    original_cp = run_dbt_cp.write_qa_result
    try:
        patch_write_qa_result_for_lambda(["qa_tools.bdm.run_dbt_bdm", "qa_tools.cp.run_dbt_cp"], str(tmp_path))

        run_dbt_bdm.write_qa_result("a", "d", "run_01", "2026-01-01T00:00:00Z", "dbt", {})
        run_dbt_cp.write_qa_result("a", "d", "cp_run_01", "2026-01-01T00:00:00Z", "dbt", {})

        assert (tmp_path / "a" / "d" / RAW_SCOPE / "run_01" / "dbt.json").exists()
        assert (tmp_path / "a" / "d" / RAW_SCOPE / "cp_run_01" / "dbt.json").exists()
    finally:
        run_dbt_bdm.write_qa_result = original_bdm
        run_dbt_cp.write_qa_result = original_cp
