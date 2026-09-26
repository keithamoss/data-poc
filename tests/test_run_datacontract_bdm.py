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

# THE REAL STAGED RUN IDS, not invented ones (REQ-QAC-088). These used to
# be arbitrary strings - "pytest_bdm_ref" - because a run id only ever
# named a CSV FILE that this tool read directly. It now reads the
# warehouse, so a run id has to name a run that was actually staged, and
# the fixture stages run_001/run_002. Inventing one produced a missing
# view schema, which datacontract-cli reported as every single check
# failing with a null metric - a confusing symptom for a correct tool.
from fixture_ids import BDM_DIRTY_RUN_ID as _DIRTY_RUN_ID, BDM_REF_RUN_ID as _REF_RUN_ID


def _run(monkeypatch, bdm_raw_dir, bdm_duckdb_dir, run_id, csv_filename, run_timestamp):
    monkeypatch.setattr(run_datacontract_bdm, "RAW_DIR", bdm_raw_dir, bdm_duckdb_dir)
    monkeypatch.setattr(run_datacontract_bdm, "write_qa_result", lambda *a, **k: None)
    return run_datacontract_bdm.evaluate_datacontract_bdm(run_id, csv_filename, run_timestamp)


def test_clean_run_resolves_every_check_id_and_mostly_passes(monkeypatch, bdm_raw_dir, bdm_duckdb_dir):
    results = _run(monkeypatch, bdm_raw_dir, bdm_duckdb_dir, _REF_RUN_ID, f"{_REF_RUN_ID}.csv", "2026-01-01T06:30:00Z")

    assert results, "the real datacontract-cli run produced no quality-check results at all"
    assert all(r["check_id"] for r in results), \
        "every result must resolve a real check_id (evaluate_datacontract_bdm raises if not)"
    assert all(r["run_id"] == _REF_RUN_ID for r in results)
    assert all(r["engine"] == run_datacontract_bdm.ENGINE_TAG for r in results)
    assert all(r["status"] in ("pass", "warn", "fail") for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real datacontract-cli failures: {failing}"


def test_dirty_run_produces_a_real_failure(monkeypatch, bdm_raw_dir, bdm_duckdb_dir):
    results = _run(monkeypatch, bdm_raw_dir, bdm_duckdb_dir, _DIRTY_RUN_ID, f"{_DIRTY_RUN_ID}.csv", "2026-01-02T06:30:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty run produced no datacontract-cli failures at all"


def test_place_of_birth_facility_keeps_its_real_configured_fail_threshold(monkeypatch, bdm_raw_dir, bdm_duckdb_dir):
    """Regression test for item 74's Bug B (plans/qa-pipeline.md, found
    2026-09-18): this check's real rule is `mustBeLessThan: 35` with
    `severity: error` - the code used to collapse every severity:error
    rule's fail_threshold to a blanket 0, discarding the real 35%
    tolerance and making a genuinely passing ~2% null rate read as a
    dashboard failure on almost every run."""
    results = _run(monkeypatch, bdm_raw_dir, bdm_duckdb_dir, _REF_RUN_ID, f"{_REF_RUN_ID}.csv", "2026-01-01T06:30:00Z")
    check = next(r for r in results if r["column_name"] == "place_of_birth_facility"
                 and r["check_name"] == "datacontract:missing_count")
    assert check["fail_threshold"] == 35
    assert check["status"] == "pass"


def test_sql_rules_get_their_shared_label_from_structure_not_prose(monkeypatch, bdm_raw_dir, bdm_duckdb_dir):
    """3 of the real SQL rules (sibling match, timestamp ordering,
    freshness) are the same real-world checks as their dbt/Soda
    counterparts under different names, and the label is what makes that
    overlap visible on the dashboard. The other 2 (date-of-birth range,
    registration/birth date ordering) have no counterpart and correctly
    get none.

    Rewritten for REQ-QAC-023 (2026-09-20). The label used to be matched
    on the rule's own `description:` PREFIX, so reformatting an
    explanation would silently drop it and split one real-world check
    into two unrelated-looking ones. It now comes from the check_id's
    own tail, which is structure."""
    results = _run(monkeypatch, bdm_raw_dir, bdm_duckdb_dir, _REF_RUN_ID, f"{_REF_RUN_ID}.csv", "2026-01-01T06:30:00Z")
    sql = [r for r in results if r["check_name"].startswith("datacontract:sql:")]
    assert sql, "no SQL rules found - fixture/test drifted from the real contract"
    assert {r["label"] for r in sql} >= {"Freshness", "Sibling record match", "Timestamp ordering"}


def test_every_sql_rule_has_its_own_authored_name(monkeypatch, bdm_raw_dir, bdm_duckdb_dir):
    """A real defect REQ-QAC-023 fixed, not a hypothetical: with no
    authored name to use, the runner fell back to the bare metric, so all
    five Birth Registrations SQL checks rendered under the identical name
    `datacontract:custom_sql` - indistinguishable on the dashboard, and
    indistinguishable in the URL that keys on the name."""
    results = _run(monkeypatch, bdm_raw_dir, bdm_duckdb_dir, _REF_RUN_ID, f"{_REF_RUN_ID}.csv", "2026-01-01T06:30:00Z")
    sql = [r for r in results if r["check_name"].startswith("datacontract:sql:")]
    names = [r["check_name"] for r in sql]
    assert len(names) == len(set(names)), f"SQL checks sharing a name: {names}"
    assert "datacontract:custom_sql" not in {r["check_name"] for r in results}
