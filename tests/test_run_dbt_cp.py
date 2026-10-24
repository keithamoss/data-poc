"""Real dbt-core integration test for qa_tools/tools/run_dbt.py's
evaluate() - the CP counterpart to tests/test_run_dbt_bdm.py,
covering the same real "parse dbt's real output, re-verify via the
audit-table workaround" logic, plus CP-specific routing (which of the
6 real tables a test result belongs to, via dbt's own attached_node /
the adapter's dbt.business_rule_home_table)."""
from __future__ import annotations

import pytest

import qa_tools.tools.run_dbt as run_dbt
from qa_tools import collections

# The run_ids cp_duckdb_dir's fixture deliveries are RECOGNISED as - see
# tests/test_run_dbt_bdm.py's own comment on why (real parallel-test
# safety for dbt's target-path output lives in evaluate() itself,
# not here - plans/running-thoughts.md #12).
from fixture_ids import CP_DIRTY_RUN_ID as _DIRTY_RUN_ID, CP_REF_RUN_ID as _REF_RUN_ID


@pytest.fixture
def _dbt_cp(monkeypatch, cp_duckdb_dir):
    # dbt's scratch database and its target_path hang off the supply
    # database's own directory (see
    # evaluate()'s own comment) - a per-worker pytest tmp dir, so
    # no manual cleanup is needed here any more, same as
    # tests/test_run_dbt_bdm.py's own equivalent fixture.
    # The environment already points at this worker's database
    # (conftest's supply_dsn); cp_duckdb_dir is what staged the data into it.
    monkeypatch.setattr(run_dbt, "write_qa_result", lambda *a, **k: None)


def test_clean_run_resolves_every_check_id_across_all_6_tables(_dbt_cp):
    """Over a run whose id names no table, so its scope is the whole
    collection (REQ-PIPE-188 criterion 4) - a fixture's placements run is
    asked only for placements' checks since dbt was scoped (REQ-PIPE-189)."""
    import uuid

    from conftest import clone_run_views
    from qa_tools.common import supply_db

    run_id = f"cp_whole_{uuid.uuid4().hex[:8]}"
    with supply_db.connect(label="test-run-dbt-cp") as conn:
        clone_run_views(conn, _REF_RUN_ID, run_id)
    results = run_dbt.evaluate("child-protection", run_id, "2026-01-01T09:00:00Z")

    assert results, "the real dbt build produced no CP test results at all"
    assert all(r["check_id"] for r in results), "every result must resolve a real check_id (evaluate_dbt_cp raises if not)"
    tables_seen = {r["dataset_id"] for r in results}
    assert len(tables_seen) > 1, "results should span more than one of the 6 real CP tables"
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real dbt failures: {failing}"


def test_dirty_run_produces_a_real_failure(_dbt_cp):
    results = run_dbt.evaluate("child-protection", _DIRTY_RUN_ID, "2026-04-01T09:00:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty CP run produced no dbt failures at all"


def test_relationships_and_business_rule_tests_resolve_a_real_table(_dbt_cp):
    """_table_for_test()'s own job: the 7 relationships (FK) tests and 3
    singular cross-table business-rule tests have no natural column of
    their own - each must still resolve to one of the 6 real tables via
    attached_node/BUSINESS_RULE_HOME_TABLE, never silently dropped."""
    results = run_dbt.evaluate("child-protection", _REF_RUN_ID, "2026-01-01T09:00:00Z")
    relationships = [r for r in results if r["check_name"] == "dbt:relationships"]
    business_rules = [r for r in results if r["check_name"].removeprefix("dbt:") in collections.adapter("child-protection").dbt.singular_home]
    assert relationships, "no relationships (FK) test results found - fixture/test drifted from the real schema.yml"
    assert business_rules, "no business-rule singular test results found"
    assert all(r["dataset_id"] for r in relationships + business_rules)


class TestAnUnreadableTableDoesNotTakeTheRunDown:
    """REQ-PIPE-078 criteria 9 and 10, and a REAL LATENT DEFECT they
    uncovered in already-shipped code.

    A held supply gets no view in the run schema - that is how "a held
    supply is not checked" has been enforced since REQ-PIPE-059, by
    construction rather than by remembering. But dbt is asked to build
    a FIXED list of six models, so the model over the missing view
    errors, and an errored node takes the whole run down through
    `_run_step`. Every one of the other five datasets loses its QA for
    one dataset nobody could place - the opposite of what REQ-PIPE-059
    criterion 7, `holds.py` and `supply_holds.py` all promise.

    It was never caught because no hold has ever occurred in the
    corpus, so the path had never run. Written up as
    plans/post-build-review.md #72.

    IT BUILDS ITS OWN RUN RATHER THAN EDITING THE SHARED ONE, and the
    first version did the opposite at real cost: it dropped
    `cp_clients` from `_REF_RUN_ID`'s schema and put it back in a
    `finally`. That run's schema and recorded resolution are shared
    with every other integration module on the same worker, so
    `test_run_soda_cp.py` and `test_orchestrate_single_run.py` went red
    against a view that existed either side of them. Staging is shared
    and immutable here, so a run of one's own costs nothing and cannot
    reach anybody else - and it exercises the REAL `create_run_views`
    held path rather than a hand-made imitation of it.
    """

    def test_the_other_five_tables_are_still_checked(self, _dbt_cp, supply_dsn):
        import uuid

        from qa_tools.common import supply_db

        from conftest import clone_run_views

        mine = f"cp_held_{uuid.uuid4().hex[:8]}"
        with supply_db.connect(label="test-held-dbt") as conn:
            res = clone_run_views(conn, _REF_RUN_ID, mine, held={"cp_clients"})
        assert "cp_clients" in res.held, "the held table must not have resolved"

        try:
            results = run_dbt.evaluate("child-protection", mine, "2026-01-01T09:00:00Z")

            assert results, "one unreadable table must not cost the other five their QA"
            seen = {r["dataset_id"] for r in results}
            assert len(seen) > 1, f"expected several tables still checked, got {seen}"
            assert "cp-clients" not in seen, \
                "nothing may be recorded against the table that could not be read"
        finally:
            with supply_db.connect(label="test-held-dbt") as conn:
                conn.execute(
                    f'DROP SCHEMA IF EXISTS "{supply_db.run_schema(mine)}" CASCADE')
                conn.execute(f'DROP SCHEMA IF EXISTS "dbt_{mine}" CASCADE')
