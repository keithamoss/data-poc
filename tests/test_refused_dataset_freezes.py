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


class TestTheRefusalsOwnHoldIsSaidAsSuch:
    """delivery-critic on (f)-(i), finding 1: the dashboard has to tell the
    refusal's own hold from another blocker."""

    def test_the_blocker_record_carries_it(self):
        from qa_tools.common.dataset_blockers import Blocker

        b = Blocker(kind="held", dataset_id="cp-clients", supply="s", opened_at="x",
                    resolved_at=None, reason="r", agreement_refused=True)
        assert b.as_record()["agreementRefused"] is True


class TestAReEvaluationWaitsOnlyForItsRefusedReaders:
    """delivery-critic on (f)-(i), findings 2 and 3: a re-evaluation is owed
    under the WRITER, but runs its READERS' checks - so the freeze belongs to
    each reader, not to the item."""

    def _run(self, monkeypatch, refused, writer="cp-placements"):
        from types import SimpleNamespace

        from qa_tools.common import knock_on

        ran, cleared = [], []
        monkeypatch.setattr(knock_on, "readers", lambda conn, period, tables, reads: [
            knock_on.Reader("cp-clients", "c@1", waiting=False, tables={"placements"},
                            stale=True),
            knock_on.Reader("cp-carers", "k@1", waiting=False, tables={"placements"},
                            stale=True)])
        monkeypatch.setattr(promotion, "_declared_reads", lambda: {})
        monkeypatch.setattr(recheck, "mint_run_id", lambda conn, ds, s: f"key-{ds}")
        monkeypatch.setattr(recheck, "execute", lambda **k: ran.append(k["dataset_id"]))
        monkeypatch.setattr(recheck, "clear", lambda owed_id, key: cleared.append(owed_id))
        monkeypatch.setattr(dl, "follows", lambda conn, d: "2099-01-01T00:00:00+00:00")
        _refuse(monkeypatch, *refused)
        item = SimpleNamespace(id=99, kind=recheck.REEVALUATE, dataset_id=writer,
                               period="2024-Q1", tables=["placements"], caused_by_decision=1)
        return knock_on.complete(item), ran, cleared

    def test_2_a_refused_reader_is_not_run_and_the_item_stays_owed(self, supply_dsn,
                                                                   monkeypatch):
        got, ran, cleared = self._run(monkeypatch, ["cp-clients"])
        assert ran == ["cp-carers"], "the other reader still re-evaluates"
        assert not cleared and got.frozen and not got.completed

    def test_3_a_refused_writer_does_not_freeze_its_readers(self, supply_dsn, monkeypatch):
        got, ran, cleared = self._run(monkeypatch, ["cp-placements"])
        assert sorted(ran) == ["cp-carers", "cp-clients"] and cleared and got.completed


class TestAFrozenArrivalIsNotAFailure:
    """delivery-critic on (f)-(i), finding 4: an arrival checked but left
    ungated because its dataset is refused raised 'its gate outcome was not
    recorded' - a failure (exit 2) holding back its whole collection."""

    def _one(self, monkeypatch, refused):
        from types import SimpleNamespace

        from qa_tools.common import processing_pass as pp

        with supply_db.connect(label="test-refused-freezes") as conn:
            qa_store.ensure_schema(conn)
        arrival = SimpleNamespace(run_id="cp_run_frozen", collection_id="child-protection",
                                  files_by_dataset={"cp-clients": ("cp_clients.csv",)})
        monkeypatch.setattr(pp, "recorded", lambda conn: None)
        monkeypatch.setattr(pp, "state_of", lambda a, rec: pp.UNGATED)
        steps = SimpleNamespace(promote_after=lambda *a, **k: None)
        monkeypatch.setattr(pp, "_modules", lambda c: (SimpleNamespace(STEPS=steps), None))
        _refuse(monkeypatch, *refused)
        report = pp.PassReport()
        pp._one(arrival, [arrival], "ts", "me", report, say=lambda m: None)
        return report

    def test_a_refused_datasets_ungated_arrival_is_left_frozen(self, supply_dsn, monkeypatch):
        report = self._one(monkeypatch, ["cp-clients"])
        assert report.left_frozen == ["cp_run_frozen"] and not report.failures

    def test_any_other_unrecorded_gate_is_still_a_failure(self, supply_dsn, monkeypatch):
        with pytest.raises(RuntimeError, match="gate outcome was not recorded"):
            self._one(monkeypatch, [])


class TestTheCriticsSmallerFindings:
    """delivery-critic on (f)-(i), findings 5 and 6."""

    def test_5_a_dataset_that_could_not_be_checked_outranks_a_refusal(self, monkeypatch):
        """As the pass ranks them: something to retry comes first."""
        from click.testing import CliRunner

        from cli import schedule as schedule_cli

        def refusals(conn=None, dataset_ids=None, *, errors=None):
            if errors is not None:
                errors.append(("cp-carers", RuntimeError("unreadable")))
            return {"cp-clients": agreement_drift.Refusal("cp-clients", ())}
        monkeypatch.setattr(agreement_drift, "refusals", refusals)
        got = CliRunner().invoke(schedule_cli.schedule_group, ["check-agreement"])
        assert got.exit_code == 2, got.output
        assert "cp-clients" in got.output, "the refusal is still said"

    def test_6_the_summary_says_what_waited_rather_than_counting_it_as_run(self, capsys):
        from cli import pipeline as pipeline_cli
        from qa_tools.common import processing_pass as pp

        report = pp.PassReport(
            owed=[recheck.Outcome(1, "k", True, "ran"),
                  recheck.Outcome(2, "k", False, "waits", frozen=True)],
            left_frozen=["cp_run_x"], refused=["cp-clients"])
        pipeline_cli._say_pass(report)
        out = " ".join(capsys.readouterr().out.split())
        assert "ran 1 owed item(s)" in out
        assert "1 owed item(s) and 1 arrival(s) wait on a refused dataset" in out
