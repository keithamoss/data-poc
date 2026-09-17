"""Real datacontract-cli integration test for qa_tools/cp/
run_datacontract_cp.py's evaluate_datacontract_cp() - the CP
counterpart to tests/test_run_datacontract_bdm.py. Unlike BDM's single
CSV, this reads all 6 real tables directly from cp_raw_dir/<run_id>/ -
no explicit csv_filename argument needed."""
from __future__ import annotations

import qa_tools.cp.run_datacontract_cp as run_datacontract_cp

_REF_RUN_ID = "pytest_cp_ref"
_DIRTY_RUN_ID = "pytest_cp_dirty"


def _run(monkeypatch, cp_raw_dir, run_id, run_timestamp):
    monkeypatch.setattr(run_datacontract_cp, "CP_RAW_DIR", cp_raw_dir)
    monkeypatch.setattr(run_datacontract_cp, "write_qa_result", lambda *a, **k: None)
    return run_datacontract_cp.evaluate_datacontract_cp(run_id, run_timestamp)


def test_clean_run_resolves_every_check_id_across_all_6_tables(monkeypatch, cp_raw_dir):
    results = _run(monkeypatch, cp_raw_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")

    assert results, "the real datacontract-cli run produced no CP quality-check results at all"
    assert all(r["check_id"] for r in results), \
        "every result must resolve a real check_id (evaluate_datacontract_cp raises if not)"
    tables_seen = {r["dataset_id"] for r in results}
    assert len(tables_seen) > 1, "results should span more than one of the 6 real CP tables"
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real datacontract-cli failures: {failing}"


def test_dirty_run_produces_a_real_failure(monkeypatch, cp_raw_dir):
    results = _run(monkeypatch, cp_raw_dir, _DIRTY_RUN_ID, "2026-04-01T09:00:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty CP run produced no datacontract-cli failures at all"


def test_fk_custom_sql_rules_route_to_a_real_column(monkeypatch, cp_raw_dir):
    """_fk_column_for()'s own job: the 7 FK custom_sql rules (type: sql,
    indistinguishable from the 3 business-rule checks by type alone)
    must resolve to a real column via the rule's own description text,
    not fall through to the "(table)" fallback."""
    results = _run(monkeypatch, cp_raw_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")
    sql_rules = [r for r in results if r["check_name"].startswith("datacontract:sql:")]
    assert sql_rules, "no custom_sql rules found - fixture/test drifted from the real contract"
    fk_rules = [r for r in sql_rules if r["column_name"] != "(table)"]
    assert fk_rules, "no FK custom_sql rule resolved a real column - _fk_column_for() may have regressed"
