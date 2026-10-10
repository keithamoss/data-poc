"""Real Soda Core integration test for qa_tools/bdm/run_soda_bdm.py's
evaluate_soda_bdm() - the actual "parse Soda's real scan results into
our check-result shape" logic, not previously exercised under pytest
at all (see tests/conftest.py's own docstring). Runs a REAL Soda Scan
against the real contract/bdm-birth-registrations-soda-checks.yml and
a small, real, session-scoped BDM fixture."""
from __future__ import annotations

import qa_tools.bdm.run_soda_bdm as run_soda_bdm

from fixture_ids import BDM_DIRTY_RUN_ID as _DIRTY_RUN_ID, BDM_REF_RUN_ID as _REF_RUN_ID


def _run(monkeypatch, bdm_duckdb_dir, run_id, run_timestamp):
    # The environment already points at this worker's database
    # (conftest's supply_dsn); bdm_duckdb_dir is what staged the data into it.
    monkeypatch.setattr(run_soda_bdm, "write_qa_result", lambda *a, **k: None)
    return run_soda_bdm.evaluate_soda_bdm(run_id, run_timestamp)


def test_clean_run_resolves_every_check_id_and_mostly_passes(monkeypatch, bdm_duckdb_dir):
    results = _run(monkeypatch, bdm_duckdb_dir, _REF_RUN_ID, "2026-01-01T06:30:00Z")

    assert results, "the real Soda scan produced no check results at all"
    assert all(r["check_id"] for r in results), "every result must resolve a real check_id (evaluate_soda_bdm raises if not)"
    assert all(r["run_id"] == _REF_RUN_ID for r in results)
    assert all(r["engine"] == run_soda_bdm.ENGINE_TAG for r in results)
    assert all(r["status"] in ("pass", "warn", "fail") for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real Soda failures: {failing}"


def test_dirty_run_produces_a_real_failure_and_correct_row_counts(monkeypatch, bdm_duckdb_dir):
    results = _run(monkeypatch, bdm_duckdb_dir, _DIRTY_RUN_ID, "2026-01-02T06:30:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty run produced no Soda failures at all"
    assert all(10 <= r["row_count_total"] <= 30 for r in results)


def test_failed_rows_checks_route_to_their_real_column_not_table(monkeypatch, bdm_duckdb_dir):
    """_CUSTOM_CHECK_COLUMN's whole job: a Soda 'failed rows' check
    (extract_timestamp ordering, multiple-birth sibling match - no
    natural `column` of its own) must still land on a real column, not
    the "(table)" fallback the dashboard silently drops for this
    single-table dataset."""
    results = _run(monkeypatch, bdm_duckdb_dir, _REF_RUN_ID, "2026-01-01T06:30:00Z")
    custom_named = [r for r in results if r["check_name"] in run_soda_bdm._CUSTOM_CHECK_COLUMN]
    assert custom_named, "no 'failed rows' custom-named checks found - fixture/test drifted from the real checks YAML"
    assert all(r["column_name"] != "(table)" for r in custom_named)


def test_a_check_soda_cannot_evaluate_is_recorded_as_an_error(monkeypatch, bdm_duckdb_dir,
                                                               tmp_path):
    """Keith, 2026-10-06 (the road-testing sweep's #7, a defect): a check
    Soda Core cannot evaluate - here a change-over-time check, which needs
    Soda Cloud - used to be ABSENT from the scan's results, so a declared
    check never reported and nothing noticed: a false green. Every declared
    check that does not report is now recorded red, 'could not be
    evaluated', with Soda's own reason."""
    import yaml

    with open(run_soda_bdm.SODA_CHECKS_PATH) as f:
        doc = yaml.safe_load(f)
    doc["checks for birth_registrations"].append({"change for row_count": {
        "warn": "when > 10", "fail": "when > 50",
        "attributes": {"check_id": "test.civil-registration.birth-registrations."
                                   "change_rowcount_soda"}}})
    checks = tmp_path / "checks.yml"
    checks.write_text(yaml.safe_dump(doc, sort_keys=False))
    monkeypatch.setattr(run_soda_bdm, "SODA_CHECKS_PATH", str(checks))
    results = _run(monkeypatch, bdm_duckdb_dir, _REF_RUN_ID, "2026-01-01T06:30:00Z")
    mine = [r for r in results
            if r["check_id"] == "test.civil-registration.birth-registrations.change_rowcount_soda"]
    assert len(mine) == 1, "the check Soda could not evaluate is missing from the results"
    assert mine[0]["status"] == "error"
    assert "could not be evaluated" in mine[0]["finding"]
    others = [r for r in results if r is not mine[0]]
    assert others and all(r["status"] in ("pass", "warn", "fail") for r in others), \
        "the checks Soda could evaluate keep their own results"
