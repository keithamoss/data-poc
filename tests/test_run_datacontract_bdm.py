"""Real datacontract-cli integration test for qa_tools/bdm/
run_datacontract_bdm.py's evaluate_datacontract_bdm() - the actual
"parse datacontract-cli's real DataContract.test() result into our
check-result shape" logic, not previously exercised under pytest at
all (see tests/conftest.py's own docstring). Runs the REAL
datacontract-cli Python API against the real contract/
bdm-birth-registrations-contract.yaml and a small, real, session-scoped
BDM CSV fixture."""
from __future__ import annotations

import qa_tools.bdm.run_datacontract_bdm as run_datacontract_bdm

_REF_RUN_ID = "pytest_bdm_ref"
_DIRTY_RUN_ID = "pytest_bdm_dirty"


def _run(monkeypatch, bdm_raw_dir, run_id, csv_filename, run_timestamp):
    monkeypatch.setattr(run_datacontract_bdm, "RAW_DIR", bdm_raw_dir)
    monkeypatch.setattr(run_datacontract_bdm, "write_qa_result", lambda *a, **k: None)
    return run_datacontract_bdm.evaluate_datacontract_bdm(run_id, csv_filename, run_timestamp)


def test_clean_run_resolves_every_check_id_and_mostly_passes(monkeypatch, bdm_raw_dir):
    results = _run(monkeypatch, bdm_raw_dir, _REF_RUN_ID, f"{_REF_RUN_ID}.csv", "2026-01-01T06:30:00Z")

    assert results, "the real datacontract-cli run produced no quality-check results at all"
    assert all(r["check_id"] for r in results), \
        "every result must resolve a real check_id (evaluate_datacontract_bdm raises if not)"
    assert all(r["run_id"] == _REF_RUN_ID for r in results)
    assert all(r["engine"] == run_datacontract_bdm.ENGINE_TAG for r in results)
    assert all(r["status"] in ("pass", "warn", "fail") for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real datacontract-cli failures: {failing}"


def test_dirty_run_produces_a_real_failure(monkeypatch, bdm_raw_dir):
    results = _run(monkeypatch, bdm_raw_dir, _DIRTY_RUN_ID, f"{_DIRTY_RUN_ID}.csv", "2026-01-02T06:30:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty run produced no datacontract-cli failures at all"


def test_custom_sql_rules_get_their_shared_label(monkeypatch, bdm_raw_dir):
    """3 of the real custom_sql rules (sibling match, timestamp
    ordering, freshness) are the same real-world checks as their dbt/
    Soda counterparts under different names - _custom_sql_label() is
    what makes that overlap visible on the dashboard, matched by each
    rule's own real description prefix, not guessed. Other custom_sql
    rules (date-of-birth range, registration/birth date ordering) have
    no such counterpart and correctly get no label - only the 3 named
    ones are asserted on here."""
    results = _run(monkeypatch, bdm_raw_dir, _REF_RUN_ID, f"{_REF_RUN_ID}.csv", "2026-01-01T06:30:00Z")
    custom_sql = [r for r in results if r["check_name"] == "datacontract:custom_sql"]
    assert custom_sql, "no custom_sql rules found - fixture/test drifted from the real contract"
    labels = {r["label"] for r in custom_sql}
    assert {"Freshness", "Sibling record match", "Timestamp ordering"} <= labels
