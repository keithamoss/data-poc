"""dbt asked only for the checks its run records (REQ-PIPE-189).

Written before the code. The bar is REQ-PIPE-188's: a speed change that
moves any verdict is a defect - so the central test runs the real dbt
twice over the same dirty fixture, once asked for the whole collection
and once for the run's scope, and requires every in-scope record to be
identical field for field, failing samples and audit-table re-counts
included.
"""
from __future__ import annotations

import random

import pytest

import qa_tools.tools.run_dbt as run_dbt
from fixture_ids import CP_DIRTY_RUN_ID
from qa_tools.common import asked_for, dbt_common, left_out, qa_results_writer, supply_db

CP = "child-protection"
P = "data-asset-1.child-protection-family-support.child-protection"


@pytest.fixture
def _quiet(monkeypatch, cp_duckdb_dir):
    monkeypatch.setattr(run_dbt, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(run_dbt.asked_for, "record", lambda *a, **k: None)


def _clone(table: str, **withheld) -> str:
    from conftest import clone_run_views

    run_id = f"{table}__{random.randrange(10**17, 10**18)}"
    with supply_db.connect(label="test-dbt-scoped") as conn:
        clone_run_views(conn, CP_DIRTY_RUN_ID, run_id, **withheld)
    return run_id


def _evaluate(run_id: str, monkeypatch, *, scoped: bool) -> list[dict]:
    monkeypatch.setattr(asked_for, "SCOPED",
                        frozenset({"dbt"}) if scoped else frozenset())
    got = run_dbt.evaluate("child-protection", run_id, "2026-04-01T09:00:00Z")
    left_out.take(run_id)
    return got


def _ran(run_id: str) -> set[str]:
    import json
    import os

    path = os.path.join(str(supply_db.dbt_target_path(run_id)), "run_results.json")
    with open(path) as f:
        return {r["unique_id"] for r in json.load(f)["results"]}


class TestTheSelection:

    @pytest.mark.parametrize("collection", [CP, "civil-registration"])
    def test_every_active_dbt_check_names_a_test(self, collection):
        """Through the project's own node-to-check-id lookup, never a list
        of node names kept by hand (NFR 1) - and every check that can be
        asked for has a node to ask for."""
        names = run_dbt.test_names_by_check_id(collection)
        assert set(asked_for.collection_checks(collection, "dbt")) <= set(names)

    def test_each_collection_claims_only_its_own_tests(self):
        """Critic F4: Child Protection's lookup claimed two Birth Registrations
        singular tests, which names_by_check_id's contract says it must not."""
        cp = run_dbt.test_names_by_check_id("child-protection")
        br = run_dbt.test_names_by_check_id("civil-registration")
        assert cp and br
        assert all(".child-protection." in c for c in cp), sorted(
            c for c in cp if ".child-protection." not in c)
        assert all(".civil-registration." in c for c in br)

    def test_the_project_is_parsed_once_while_it_is_unchanged(self, monkeypatch):
        """Criterion 5: the worker's partial parse is kept, and the lookup
        is not paid per run."""
        from qa_tools.common import dbt_worker

        dbt_common.forget_parsed_tests()
        calls = []
        real = dbt_worker.invoke

        def counted(args, env, target_path):
            calls.append(args[0])
            return real(args, env, target_path)
        monkeypatch.setattr(dbt_worker, "invoke", counted)
        for _ in range(3):
            run_dbt.test_names_by_check_id("child-protection")
        assert calls == ["parse"]

    def test_a_selection_names_tests_with_their_parents(self):
        check = f"{P}.cp-notifications.cp_client_id.relationships_dbt"
        (selected,) = run_dbt.selection_for("child-protection", [check])
        assert selected.startswith("+relationships_stg_cp_notifications")

    def test_a_check_with_no_test_refuses(self):
        with pytest.raises(dbt_common.UnknownCheck, match="no_such"):
            run_dbt.selection_for("child-protection", [f"{P}.cp-clients.no_such_dbt"])


class TestTheSameVerdicts:
    """Criteria 1, 2, 4 and the bar: asked for its scope, dbt records the
    same thing for every in-scope check and runs nothing outside it."""

    @pytest.mark.parametrize("table", ["cp_notifications", "cp_placements", "cp_carers"])
    def test_in_scope_records_are_identical(self, table, _quiet, monkeypatch):
        run_id = _clone(table)
        whole = _evaluate(run_id, monkeypatch, scoped=False)
        scoped = _evaluate(run_id, monkeypatch, scoped=True)
        ran = _ran(run_id)

        in_scope = qa_results_writer.scope_of_run(run_id)
        want = {r["check_id"]: r for r in whole if in_scope(r["check_id"])}
        got = {r["check_id"]: r for r in scoped}
        assert want, "the dirty fixture gave this run nothing in scope"
        assert got == want
        assert any(r["status"] == "fail" for r in want.values()) or table != "cp_notifications", \
            "the dirty fixture should fail something for notifications"

        # NOTHING OUTSIDE THE SCOPE RAN (criterion 2), by node.
        nodes = {uid for uid in ran if uid.startswith("test.")}
        names = run_dbt.test_names_by_check_id("child-protection")
        asked = asked_for.for_run(run_id, CP, "dbt", in_scope)
        assert {n.split(".")[2] for n in nodes} == {n for c in asked for n in names[c]}


class TestAnUnreadableTableLeavesItsTestsOut:
    """Criterion 3: dbt's graph still decides, and the left-out
    reconciliation is told."""

    def test_a_scoped_test_reading_an_unreadable_table_is_reported(self, _quiet,
                                                                   monkeypatch):
        run_id = _clone("cp_placements", absent={"cp_carers"})
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"dbt"}))
        got = run_dbt.evaluate("child-protection", run_id, "2026-04-01T09:00:00Z")
        noted = left_out.take(run_id).get("dbt", set())
        carer_checks = {f"{P}.cp-placements.carer_id.relationships_dbt",
                        f"{P}.cp-placements.carer_id.placement_carer_approval_dbt"}
        assert carer_checks <= noted
        assert carer_checks.isdisjoint({r["check_id"] for r in got})
        assert got, "the run's other placements checks still ran"
        in_scope = qa_results_writer.scope_of_run(run_id)
        assert all(in_scope(c) for c in noted), "only asked-for tests are reported"


class TestNothingAskedRunsNothing:

    def test_an_empty_scope_invokes_no_dbt_and_says_so(self, _quiet, monkeypatch):
        """`dbt build` with no `--select` builds the whole project, so an
        empty ask must never reach it. The raw output says nothing was
        asked, so the run still records dbt."""
        from qa_tools.common import dbt_worker

        run_id = _clone("cp_case_workers")
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"dbt"}))
        monkeypatch.setattr(asked_for, "for_run", lambda *a, **k: [])
        monkeypatch.setattr(dbt_worker, "invoke",
                            lambda *a, **k: pytest.fail("dbt was invoked with nothing asked"))
        written = []
        monkeypatch.setattr(run_dbt, "write_qa_result",
                            lambda *a, **k: written.append((a[4], a[5])))
        assert run_dbt.evaluate("child-protection", run_id, "2026-04-01T09:00:00Z") == []
        assert written == [("dbt", {"asked": []})]


class TestBirthRegistrationsTakesTheSamePath:
    """REQ-PIPE-188 criterion 10: the scope is every check on its one
    table, and what it records does not change."""

    def test_the_same_records_scoped(self, bdm_duckdb_dir, monkeypatch):
        import qa_tools.tools.run_dbt as run_dbt
        from conftest import clone_run_views
        from fixture_ids import BDM_DIRTY_RUN_ID

        monkeypatch.setattr(run_dbt, "write_qa_result", lambda *a, **k: None)
        monkeypatch.setattr(run_dbt.asked_for, "record", lambda *a, **k: None)
        run_id = f"birth_registrations__{random.randrange(10**17, 10**18)}"
        with supply_db.connect(label="test-dbt-scoped") as conn:
            clone_run_views(conn, BDM_DIRTY_RUN_ID, run_id)

        def evaluate(scoped):
            monkeypatch.setattr(asked_for, "SCOPED",
                                frozenset({"dbt"}) if scoped else frozenset())
            got = run_dbt.evaluate("civil-registration", run_id, "2026-01-02T09:00:00Z")
            left_out.take(run_id)
            return {r["check_id"]: r for r in got}

        whole, scoped = evaluate(False), evaluate(True)
        assert whole and scoped == whole
        assert any(r["status"] == "fail" for r in whole.values())
