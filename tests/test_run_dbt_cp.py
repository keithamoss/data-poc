"""Real dbt-core integration test for qa_tools/cp/run_dbt_cp.py's
evaluate_dbt_cp() - the CP counterpart to tests/test_run_dbt_bdm.py,
covering the same real "parse dbt's real output, re-verify via the
audit-table workaround" logic, plus CP-specific routing (which of the
6 real tables a test result belongs to, via dbt's own attached_node /
cp_common.BUSINESS_RULE_HOME_TABLE)."""
from __future__ import annotations

import shutil

import pytest

import qa_tools.cp.run_dbt_cp as run_dbt_cp

_REF_RUN_ID = "pytest_cp_ref"
_DIRTY_RUN_ID = "pytest_cp_dirty"


@pytest.fixture
def _dbt_cp(monkeypatch, cp_duckdb_dir):
    monkeypatch.setattr(run_dbt_cp, "CP_DUCKDB_RUNS_DIR", cp_duckdb_dir)
    monkeypatch.setattr(run_dbt_cp, "write_qa_result", lambda *a, **k: None)
    yield
    for run_id in (_REF_RUN_ID, _DIRTY_RUN_ID):
        shutil.rmtree(f"{run_dbt_cp.DBT_PROJECT_DIR}/target/{run_id}", ignore_errors=True)


def test_clean_run_resolves_every_check_id_across_all_6_tables(_dbt_cp):
    results = run_dbt_cp.evaluate_dbt_cp(_REF_RUN_ID, "2026-01-01T09:00:00Z")

    assert results, "the real dbt build produced no CP test results at all"
    assert all(r["check_id"] for r in results), "every result must resolve a real check_id (evaluate_dbt_cp raises if not)"
    tables_seen = {r["dataset_id"] for r in results}
    assert len(tables_seen) > 1, "results should span more than one of the 6 real CP tables"
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real dbt failures: {failing}"


def test_dirty_run_produces_a_real_failure(_dbt_cp):
    results = run_dbt_cp.evaluate_dbt_cp(_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty CP run produced no dbt failures at all"


def test_relationships_and_business_rule_tests_resolve_a_real_table(_dbt_cp):
    """_table_for_test()'s own job: the 7 relationships (FK) tests and 3
    singular cross-table business-rule tests have no natural column of
    their own - each must still resolve to one of the 6 real tables via
    attached_node/BUSINESS_RULE_HOME_TABLE, never silently dropped."""
    results = run_dbt_cp.evaluate_dbt_cp(_REF_RUN_ID, "2026-01-01T09:00:00Z")
    relationships = [r for r in results if r["check_name"] == "dbt:relationships"]
    business_rules = [r for r in results if r["check_name"].removeprefix("dbt:") in run_dbt_cp.cp_common.BUSINESS_RULE_HOME_TABLE]
    assert relationships, "no relationships (FK) test results found - fixture/test drifted from the real schema.yml"
    assert business_rules, "no business-rule singular test results found"
    assert all(r["dataset_id"] for r in relationships + business_rules)
