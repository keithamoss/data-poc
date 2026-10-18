"""Soda handed only the checks its run records (REQ-PIPE-191).

Written before the code, to the same bar as tests/test_dbt_scoped.py:
the real scan twice over the same dirty fixture, whole file and scoped,
and every in-scope record identical field for field.
"""
from __future__ import annotations

import functools

import random

import pytest
import yaml

from fixture_ids import BDM_DIRTY_RUN_ID, CP_DIRTY_RUN_ID
from qa_tools.common import asked_for, left_out, qa_results_writer, soda_common, supply_db

P = "data-asset-1.child-protection-family-support.child-protection"


def _ids(text: str) -> set[str]:
    out = set()
    for checks in (yaml.safe_load(text) or {}).values():
        for item in checks if isinstance(checks, list) else []:
            check = soda_common._check_id_of(item)
            if check:
                out.add(check)
    return out


class TestTheHandedText:
    """Criterion 1, as a text: only the asked checks, removed by check id."""

    def test_only_the_asked_checks_are_handed(self):
        import qa_tools.tools.run_soda as cp

        every = asked_for.collection_checks("child-protection", "soda")
        keep = set(every[:5])
        handed = soda_common.readable_checks_yaml(cp.checks_path("child-protection"), set(), keep=keep)
        assert _ids(handed) == keep

    def test_a_section_left_with_nothing_is_dropped(self):
        import qa_tools.tools.run_soda as cp

        keep = {c for c in asked_for.collection_checks("child-protection", "soda")
                if ".cp-clients." in c}
        sections = yaml.safe_load(soda_common.readable_checks_yaml(cp.checks_path("child-protection"), set(),
                                                                   keep=keep))
        assert all(checks for checks in sections.values())
        assert "checks for cp_clients" in sections

    def test_left_out_counts_only_asked_checks(self):
        """A check outside the scope was never this run's to leave out."""
        import qa_tools.tools.run_soda as cp

        keep = {c for c in asked_for.collection_checks("child-protection", "soda")
                if ".cp-placements." in c}
        left = soda_common.left_out_checks(cp.checks_path("child-protection"), {"cp_carers"}, keep=keep)
        assert left and set(left) <= keep

    def test_an_unreadable_tables_filtered_section_and_filter_go_too(self):
        """A FILTERED SECTION READS ITS TABLE (post-build-review #239):
        `checks for birth_registrations [recent]` and its `filter` entry were
        handed over an unreadable table, and the scan failed the run."""
        import qa_tools.tools.run_soda as cp

        handed = yaml.safe_load(soda_common.readable_checks_yaml(
            cp.checks_path("civil-registration"), {"birth_registrations"}) or "{}") or {}
        assert not [k for k in handed if "birth_registrations" in k], list(handed)

    def test_nothing_kept_back_hands_the_file_verbatim(self):
        import qa_tools.tools.run_soda as cp

        with open(cp.checks_path("child-protection")) as f:
            assert soda_common.readable_checks_yaml(cp.checks_path("child-protection"), set()) == f.read()


@pytest.fixture
def _quiet(monkeypatch, cp_duckdb_dir, bdm_duckdb_dir):
    import qa_tools.tools.run_soda as shared

    monkeypatch.setattr(shared, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(shared.asked_for, "record", lambda *a, **k: None)


def _clone(source: str, table: str, **withheld) -> str:
    from conftest import clone_run_views

    run_id = f"{table}__{random.randrange(10**17, 10**18)}"
    with supply_db.connect(label="test-soda-scoped") as conn:
        clone_run_views(conn, source, run_id, **withheld)
    return run_id


def _evaluate(evaluate, run_id, monkeypatch, *, scoped):
    monkeypatch.setattr(asked_for, "SCOPED", frozenset({"soda"}) if scoped else frozenset())
    got = evaluate(run_id, "2026-04-01T09:00:00Z")
    left_out.take(run_id)
    return got


class TestTheSameVerdicts:
    """Criteria 1 and 2, and the bar."""

    @pytest.mark.parametrize("table", ["cp_notifications", "cp_placements", "cp_carers"])
    def test_child_protection(self, table, _quiet, monkeypatch):
        import qa_tools.tools.run_soda as cp

        run_id = _clone(CP_DIRTY_RUN_ID, table)
        whole = _evaluate(functools.partial(cp.evaluate, "child-protection"), run_id, monkeypatch, scoped=False)
        scoped = _evaluate(functools.partial(cp.evaluate, "child-protection"), run_id, monkeypatch, scoped=True)
        in_scope = qa_results_writer.scope_of_run(run_id)
        want = {r["check_id"]: r for r in whole if in_scope(r["check_id"])}
        assert want
        assert {r["check_id"]: r for r in scoped} == want

    def test_birth_registrations(self, _quiet, monkeypatch):
        import qa_tools.tools.run_soda as bdm

        run_id = _clone(BDM_DIRTY_RUN_ID, "birth_registrations")
        whole = _evaluate(functools.partial(bdm.evaluate, "civil-registration"), run_id, monkeypatch, scoped=False)
        scoped = _evaluate(functools.partial(bdm.evaluate, "civil-registration"), run_id, monkeypatch, scoped=True)
        assert whole and {r["check_id"]: r for r in scoped} == \
            {r["check_id"]: r for r in whole}


class TestUnreportedStaysWithinTheScope:
    """Criterion 2: a handed check Soda did not report is red and not
    evaluated; one outside the scope was never handed, so never counted."""

    def test_an_unreported_handed_check_is_recorded_and_others_are_not(self, _quiet,
                                                                       monkeypatch):
        import qa_tools.tools.run_soda as cp

        run_id = _clone(CP_DIRTY_RUN_ID, "cp_clients")
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"soda"}))
        real = soda_common.execute_scan
        lost = []

        def drops_one(scan):
            got = real(scan)
            dropped = got["checks"].pop()
            lost.append(soda_common.check_id_from_resource_attributes(dropped))
            return got
        monkeypatch.setattr(cp, "execute_scan", drops_one)
        got = cp.evaluate("child-protection", run_id, "2026-04-01T09:00:00Z")
        left_out.take(run_id)
        in_scope = qa_results_writer.scope_of_run(run_id)
        unreported = [r for r in got if r.get("not_evaluated_reason")]
        assert [r["check_id"] for r in unreported] == lost
        assert all(in_scope(r["check_id"]) for r in got), "an out-of-scope check was counted"
        assert len({r["check_id"] for r in got}) == len(got)


class TestNothingAsked:

    def test_an_empty_ask_runs_no_scan_and_says_so(self, cp_duckdb_dir, monkeypatch):
        import qa_tools.tools.run_soda as cp

        run_id = _clone(CP_DIRTY_RUN_ID, "cp_case_workers")
        monkeypatch.setattr(cp.asked_for, "record", lambda *a, **k: None)
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"soda"}))
        monkeypatch.setattr(asked_for, "for_run", lambda *a, **k: [])
        monkeypatch.setattr(cp, "execute_scan", lambda *a, **k: pytest.fail("scanned"))
        written = []
        monkeypatch.setattr(cp, "write_qa_result", lambda *a, **k: written.append((a[4], a[5])))
        assert cp.evaluate("child-protection", run_id, "2026-04-01T09:00:00Z") == []
        assert written == [("soda", {"asked": []})]
