"""A dataset the agreement backstop refuses is frozen, not only its new
filings (Keith, 2026-10-11, morning-report question (f); REQ-PIPE-173).

Before: a refused dataset's NEW supplies were held, but a re-check already
owed still ran and the gate still promoted on verdicts already recorded.
Keith: "nothing about cp-clients moves until the undeclared change is
explained". Each case stubs the backstop to refuse one dataset, so the
test is about what freezing does, not about how a refusal is worked out
(tests/test_agreement_drift.py covers that).
"""
from __future__ import annotations

import pytest

from fixture_ids import CP_DIRTY_RUN_ID
from qa_tools.common import agreement_drift, decision_log as dl, promotion, qa_store, recheck, \
    supply_db

DATASET = "cp-placements"
SUPPLY = f"{DATASET}@{CP_DIRTY_RUN_ID.split('__')[1]}"


def _refuse(monkeypatch, *datasets):
    def refusals(conn=None, dataset_ids=None, *, errors=None):
        wanted = set(dataset_ids) if dataset_ids is not None else set(datasets)
        return {ds: agreement_drift.Refusal(ds, ())
                for ds in datasets if ds in wanted}
    monkeypatch.setattr(agreement_drift, "refusals", refusals)


@pytest.fixture
def owed_one(cp_duckdb_dir, monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "pytest@example.org")
    with supply_db.connect(label="test-refused-freezes") as conn:
        qa_store.ensure_schema(conn)
        with conn.raw.transaction():
            decision_id = dl.record_automatic(conn, dl.Decision(
                agency_id="child-protection-family-support", collection_id="child-protection",
                dataset_id=DATASET, action=dl.PROMOTION_WITHHELD, supply=SUPPLY,
                actor="pytest", actor_kind=dl.RULE, effective_at="2099-01-01T00:00:00+00:00",
                to_slot="2026-Q2", reason="cause for a frozen re-check"))
            owed_id = recheck.owe(conn, dataset_id=DATASET, supply_id=SUPPLY,
                                  decision_id=decision_id)
    return owed_id


class TestAnOwedReCheckWaits:
    def test_it_is_left_owed_and_not_run(self, owed_one, monkeypatch):
        from qa_tools.cp import orchestrate_cp

        ran = []
        monkeypatch.setattr(orchestrate_cp, "_run_one", lambda *a, **k: ran.append(1))
        _refuse(monkeypatch, DATASET)
        got = recheck.run(owed_one, run_by="pytest@example.org")
        assert not got.completed and got.frozen, got
        assert "refused" in got.message and not ran
        with supply_db.connect(label="test-refused-freezes") as conn:
            (still,) = [o for o in recheck.owed(conn, DATASET) if o.id == owed_one]
            assert not still.last_failure, "waiting is not failing"


class TestTheGatePromotesNothing:
    def test_a_refused_datasets_supply_is_left_ungated(self, supply_dsn, monkeypatch):
        """No promotion and no refusal recorded: the arrival stays checked but
        not gated, so the first pass after the dataset is cleared gates it."""
        import uuid

        supply = f"cp-clients@frozen{uuid.uuid4().hex[:10]}"
        _refuse(monkeypatch, "cp-clients")
        with supply_db.connect(label="test-refused-freezes") as conn:
            qa_store.ensure_schema(conn)
            got = promotion.after_run(
                conn, agency_id="child-protection-family-support",
                collection_id="child-protection",
                supplies=[{"dataset_id": "cp-clients", "supply": supply, "period": "2024-Q1",
                           "physical_tables": ["clients"]}],
                results=[], reads={}, actor="mothman:promotion-gate", actor_kind=dl.RULE,
                effective_at="2099-01-01T00:00:00+00:00")
            assert not got.promoted and not got.refused and "cp-clients" in got.frozen
            assert not conn.execute(f"SELECT 1 FROM {dl.TABLE} WHERE supply = ?",
                                    [supply]).fetchall()


class TestItsOwnExitStatus:
    """Keith, (h): a refusal is not red data, so scripts can tell them apart."""

    def test_codes(self):
        from qa_tools.common import processing_pass as pp

        assert pp.PassReport(refused=["cp-clients"]).exit_status == pp.EXIT_REFUSED == 3
        assert pp.PassReport(refused=["cp-clients"], red=True).exit_status == pp.EXIT_REFUSED
        assert pp.PassReport(refused=["cp-clients"],
                             failures=[("x", "y")]).exit_status == pp.EXIT_FAILED

    def test_the_help_states_it(self):
        from click.testing import CliRunner

        from cli.app import cli

        assert "  3 " in CliRunner().invoke(cli, ["pipeline", "process", "--help"]).output
        assert "Exits 3" in CliRunner().invoke(
            cli, ["schedule", "check-agreement", "--help"]).output

    def test_check_agreement_exits_3(self, monkeypatch):
        from click.testing import CliRunner

        from cli import schedule as schedule_cli

        _refuse(monkeypatch, "cp-clients")
        got = CliRunner().invoke(schedule_cli.schedule_group, ["check-agreement"])
        assert got.exit_code == 3, got.output

    def test_a_frozen_owed_item_is_not_a_pass_failure(self):
        from qa_tools.common import processing_pass as pp

        assert not pp._owed_failure(recheck.Outcome(1, "k", False, "refused", frozen=True))
        assert pp._owed_failure(recheck.Outcome(2, "k", False, "broke"))


class TestTheRecordSaysFromWhen:
    """(g): the page shows a refusal from the earliest period it affects."""

    def test_from_is_the_earliest_affected_period(self):
        r = agreement_drift.Refusal("cp-clients", (
            agreement_drift.Drift("cp-clients", "2024-Q1", (), period_date="2024-02-01"),
            agreement_drift.Drift("cp-clients", "2023-Q4", (), period_date="2023-11-01")))
        assert r.as_record()["from"] == "2023-11-01"

    def test_no_period_dates_means_no_from(self):
        r = agreement_drift.Refusal("cp-clients", (agreement_drift.Drift("cp-clients", "x", ()),))
        assert r.as_record()["from"] is None
