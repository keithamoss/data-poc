"""Real datacontract-cli integration test for qa_tools/cp/
run_datacontract_cp.py's evaluate_datacontract_cp() - the CP
counterpart to tests/test_run_datacontract_bdm.py. Unlike BDM's single
CSV, this reads all 6 real tables from the warehouse -
no explicit csv_filename argument needed."""
from __future__ import annotations

import qa_tools.cp.run_datacontract_cp as run_datacontract_cp

from fixture_ids import CP_DIRTY_RUN_ID as _DIRTY_RUN_ID, CP_REF_RUN_ID as _REF_RUN_ID


def _run(monkeypatch, cp_duckdb_dir, run_id, run_timestamp):
    # NOTHING ON DISK TO REDIRECT (REQ-PIPE-102) - this reads the
    # warehouse, and cp_duckdb_dir is what staged the data into it.
    monkeypatch.setattr(run_datacontract_cp, "write_qa_result", lambda *a, **k: None)
    return run_datacontract_cp.evaluate_datacontract_cp(run_id, run_timestamp)


def test_clean_run_resolves_every_check_id_across_all_6_tables(monkeypatch, cp_duckdb_dir):
    results = _run(monkeypatch, cp_duckdb_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")

    assert results, "the real datacontract-cli run produced no CP quality-check results at all"
    assert all(r["check_id"] for r in results), \
        "every result must resolve a real check_id (evaluate_datacontract_cp raises if not)"
    tables_seen = {r["dataset_id"] for r in results}
    assert len(tables_seen) > 1, "results should span more than one of the 6 real CP tables"
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real datacontract-cli failures: {failing}"


def test_dirty_run_produces_a_real_failure(monkeypatch, cp_duckdb_dir):
    results = _run(monkeypatch, cp_duckdb_dir, _DIRTY_RUN_ID, "2026-04-01T09:00:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty CP run produced no datacontract-cli failures at all"


def test_every_sql_rule_routes_to_a_real_column(monkeypatch, cp_duckdb_dir):
    """Rewritten for REQ-QAC-023 (2026-09-20). It used to assert that the
    7 FK rules resolved a column "via the rule's own description text" -
    which they did, by regex, and which is exactly what this requirement
    removed. Every `type: sql` rule now lives UNDER its column, so the
    column comes from the contract's schema structure and NONE of them
    falls through to "(table)" any more - a stronger assertion than the
    "at least one" the old test made."""
    results = _run(monkeypatch, cp_duckdb_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")
    sql_rules = [r for r in results if r["check_name"].startswith("datacontract:sql:")]
    assert sql_rules, "no custom_sql rules found - fixture/test drifted from the real contract"
    unrouted = [r["check_id"] for r in sql_rules if r["column_name"] == "(table)"]
    assert not unrouted, f"SQL rules still landing on (table): {unrouted}"


def test_a_sql_rules_name_is_authored_not_taken_from_its_description(monkeypatch, cp_duckdb_dir):
    """REQ-QAC-023. A check's name is what a dashboard URL keys on, so
    deriving it from prose meant rewording an explanation moved the
    check. It also shipped visible damage: the first-sentence split had
    already mangled one name into a bare trailing full stop."""
    results = _run(monkeypatch, cp_duckdb_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")
    names = {r["check_id"]: r["check_name"] for r in results
             if r["check_name"].startswith("datacontract:sql:")}
    assert names
    for check_id, name in names.items():
        short = name.removeprefix("datacontract:sql:").strip()
        assert short and short != ".", f"{check_id} has a degenerate name {name!r}"
        assert len(short) < 60, (
            f"{check_id} has a {len(short)}-character name - that is a description, "
            f"not a name: {short!r}")


def test_a_range_check_is_not_labelled_referential_integrity(monkeypatch, cp_duckdb_dir):
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
    results = _run(monkeypatch, cp_duckdb_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")
    mislabelled = [r["check_id"] for r in results
                   if r["label"] == "Referential integrity"
                   and not r["check_id"].endswith("relationships_datacontract")]
    assert not mislabelled, f"non-FK checks labelled Referential integrity: {mislabelled}"


class TestAnUnreadableTableIsNotReportedRed:
    """REAL DEFECT, 2026-10-02, the same class as dbt's
    (post-build-review #72), Soda's and Evidently's - and the WORST of
    them, because it fails in the false-red direction rather than by
    raising. datacontract-cli runs every rule in the contract whatever
    the schema holds, so a rule over a table the run cannot read came
    back `failed`: red for a reason about our own timing - a sibling not
    yet arrived, or filed to another period (REQ-PIPE-105) - rather than
    about the data. That is how people learn to ignore red.
    """

    def test_nothing_is_recorded_for_or_through_the_missing_table(
            self, monkeypatch, cp_duckdb_dir):
        import uuid

        from conftest import clone_run_views
        from qa_tools.common import supply_db
        from qa_tools.common.qa_results_writer import _declared_reads_tables

        monkeypatch.setattr(run_datacontract_cp, "write_qa_result", lambda *a, **k: None)
        mine = f"cp_held_{uuid.uuid4().hex[:8]}"
        with supply_db.connect(label="test-held-datacontract") as conn:
            clone_run_views(conn, _REF_RUN_ID, mine, held={"cp_clients"})
        try:
            results = run_datacontract_cp.evaluate_datacontract_cp(mine, "2026-01-01T09:00:00Z")
            assert {r["dataset_id"] for r in results} - {"cp-clients"}, \
                "the readable tables must still be checked"
            assert not [r for r in results if r["dataset_id"] == "cp-clients"]
            declared = _declared_reads_tables()
            assert not [r for r in results
                        if "cp_clients" in declared.get(r["check_id"], ())], \
                "a rule READING the missing table must be left out, not failed"
            assert not [r for r in results if r["status"] == "fail"], \
                "the clean reference data must not go red because a table is missing"
        finally:
            with supply_db.connect(label="test-held-datacontract") as conn:
                conn.execute(f'DROP SCHEMA IF EXISTS "{supply_db.run_schema(mine)}" CASCADE')
