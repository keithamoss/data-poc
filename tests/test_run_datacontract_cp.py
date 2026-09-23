"""Real datacontract-cli integration test for qa_tools/cp/
run_datacontract_cp.py's evaluate_datacontract_cp() - the CP
counterpart to tests/test_run_datacontract_bdm.py. Unlike BDM's single
CSV, this reads all 6 real tables directly from cp_raw_dir/<run_id>/ -
no explicit csv_filename argument needed."""
from __future__ import annotations

import qa_tools.cp.run_datacontract_cp as run_datacontract_cp

from fixture_ids import CP_DIRTY_RUN_ID as _DIRTY_RUN_ID, CP_REF_RUN_ID as _REF_RUN_ID


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


def test_every_sql_rule_routes_to_a_real_column(monkeypatch, cp_raw_dir):
    """Rewritten for REQ-QAC-023 (2026-09-20). It used to assert that the
    7 FK rules resolved a column "via the rule's own description text" -
    which they did, by regex, and which is exactly what this requirement
    removed. Every `type: sql` rule now lives UNDER its column, so the
    column comes from the contract's schema structure and NONE of them
    falls through to "(table)" any more - a stronger assertion than the
    "at least one" the old test made."""
    results = _run(monkeypatch, cp_raw_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")
    sql_rules = [r for r in results if r["check_name"].startswith("datacontract:sql:")]
    assert sql_rules, "no custom_sql rules found - fixture/test drifted from the real contract"
    unrouted = [r["check_id"] for r in sql_rules if r["column_name"] == "(table)"]
    assert not unrouted, f"SQL rules still landing on (table): {unrouted}"


def test_a_sql_rules_name_is_authored_not_taken_from_its_description(monkeypatch, cp_raw_dir):
    """REQ-QAC-023. A check's name is what a dashboard URL keys on, so
    deriving it from prose meant rewording an explanation moved the
    check. It also shipped visible damage: the first-sentence split had
    already mangled one name into a bare trailing full stop."""
    results = _run(monkeypatch, cp_raw_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")
    names = {r["check_id"]: r["check_name"] for r in results
             if r["check_name"].startswith("datacontract:sql:")}
    assert names
    for check_id, name in names.items():
        short = name.removeprefix("datacontract:sql:").strip()
        assert short and short != ".", f"{check_id} has a degenerate name {name!r}"
        assert len(short) < 60, (
            f"{check_id} has a {len(short)}-character name - that is a description, "
            f"not a name: {short!r}")


def test_a_range_check_is_not_labelled_referential_integrity(monkeypatch, cp_raw_dir):
    """A real pre-existing bug, found while rewriting the label logic for
    REQ-QAC-023 and confirmed against committed history before fixing.

    `_custom_sql_label()` returned "Referential integrity" for ANY sql
    rule that was not one of the 3 business rules - so cp_clients'
    date-of-birth range check was labelled, and therefore grouped on the
    dashboard, as a referential-integrity check. `label` is what ties
    equivalent checks together ACROSS tools, so this put a date-range
    rule in a group it has nothing to do with.

    The fix decides the label from the check_id's own tail, which is
    structure: only `relationships_datacontract` is an FK check."""
    results = _run(monkeypatch, cp_raw_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")
    mislabelled = [r["check_id"] for r in results
                   if r["label"] == "Referential integrity"
                   and not r["check_id"].endswith("relationships_datacontract")]
    assert not mislabelled, f"non-FK checks labelled Referential integrity: {mislabelled}"
