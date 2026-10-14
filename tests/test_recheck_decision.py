"""Re-check: a person asks for a waiting or promoted supply's QA to be run
again where it is filed (REQ-PIPE-164).

Built on the door/flag parity test's own examples (tests/test_door_flag_parity.py),
in this worker's database - so every state here is the one the door shows.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import test_door_flag_parity as parity
from qa_tools.common import decision_log as dl
from qa_tools.common import filing_decisions as fd
from qa_tools.common import recheck, rejection, supply_holds
from test_door_flag_parity import (DS, _actor, _filed, _forget_its_filings, _iso, _now,
                                   _person, minted, quiet)

conn = parity.conn
#: The parity module's fixtures, its autouse tidy-up included (#191).
__all__ = ["conn", "minted", "quiet", "_forget_its_filings"]


def _recheck(conn, period, supply, reason="our null-rate check was wrong"):
    return fd.apply(fd.Request(operation=fd.RECHECK, dataset_id=DS, actor=_actor(),
                               reason=reason, confirmed=True, period=period, supply=supply),
                    effective_at=_iso(_now()), conn=conn)


def _entries(conn, supply):
    return conn.execute(f"SELECT id, action, to_slot, actor_kind FROM {dl.TABLE} "
                        "WHERE supply = ? ORDER BY id", [supply]).fetchall()


def _filed_to(conn, supply):
    from qa_tools.common import filing

    return conn.execute(f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? AND "
                        "supply_id = ?", [DS, supply]).fetchall()


def _arrival_verdicts(conn, supply):
    from qa_tools.common import qa_store

    return conn.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".verdict '
                        "WHERE dataset_id = ? AND supply_id = ?", [DS, supply]).fetchone()[0]


class TestARecheckIsRecordedAndOwed:
    """Criteria 1, 2, 3 and 9."""

    @pytest.mark.parametrize("example", ["awaiting", "promoted"])
    def test_one_decision_and_one_owed_recheck_naming_it(self, conn, minted, quiet,
                                                          monkeypatch, example):
        ran = []
        monkeypatch.setattr(recheck, "execute", lambda **k: ran.append(k))
        build = parity.ex_awaiting_decision if example == "awaiting" else parity.ex_promoted
        state, supply = build(conn, minted)
        holds_before = dl.held(conn, DS, state.period)
        got = _recheck(conn, state.period, supply)
        assert got.changed and len(got.owed) == 1
        (decision_id, action, to_slot, kind) = _entries(conn, supply)[-1]
        assert (action, to_slot, kind) == (dl.RECHECK, state.period, dl.PERSON)
        [owed] = [o for o in recheck.owed(conn, DS) if o.id == got.owed[0]]
        assert (owed.kind, owed.supply_id, owed.caused_by_decision) == (
            recheck.RECHECK, supply, decision_id)
        # NOTHING RAN INSIDE IT (criterion 3), and nothing moved (criterion 9).
        assert ran == []
        assert _filed_to(conn, supply) == [(state.period,)]
        assert dl.held(conn, DS, state.period) == holds_before

    def test_a_reason_is_required(self, conn, minted, quiet):
        state, supply = parity.ex_awaiting_decision(conn, minted)
        with pytest.raises(dl.DecisionRefused):
            _recheck(conn, state.period, supply, reason=" ")
        assert [a for _i, a, *_ in _entries(conn, supply)] == []

    def test_it_is_not_a_persons_decision_about_the_supply(self, conn, minted, quiet):
        """Criterion 20: a waiting supply re-checked green may still promote
        itself under the gate."""
        state, supply = parity.ex_awaiting_decision(conn, minted)
        _recheck(conn, state.period, supply)
        assert not rejection.decided_by_a_person(conn, DS, supply)

    def test_it_records_no_arrival_verdict(self, conn, minted, quiet):
        """Criterion 24."""
        state, supply = parity.ex_awaiting_decision(conn, minted)
        before = _arrival_verdicts(conn, supply)
        _recheck(conn, state.period, supply)
        assert _arrival_verdicts(conn, supply) == before

    def test_a_period_it_is_not_filed_to_is_refused_naming_where_it_is(self, conn, minted,
                                                                       quiet):
        state, supply = parity.ex_awaiting_decision(conn, minted)
        other = minted("due").name
        with pytest.raises(dl.DecisionRefused, match=f"filed to {state.period}"):
            _recheck(conn, other, supply)


class TestOnlyAWaitingOrPromotedSupplyIsRechecked:
    """Criteria 10 and 22: refused, saying why, with the decision that would
    bring it back - and nothing recorded."""

    def _refused(self, conn, period, supply):
        with pytest.raises(dl.DecisionRefused) as got:
            _recheck(conn, period, supply)
        assert [a for _i, a, *_ in _entries(conn, supply)].count(dl.RECHECK) == 0
        assert not [o for o in recheck.owed(conn, DS) if o.supply_id == supply]
        return str(got.value)

    def test_a_held_supply_gives_its_holds_responses(self, conn, minted, quiet):
        import filing_support

        period = minted("due").name
        supply, _ = _filed(conn, period, _iso(_now() - timedelta(days=1)))
        (delivery,) = conn.execute("SELECT delivery FROM qa.filing_current WHERE "
                                   "supply_id = ?", [supply]).fetchall()[0]
        filing_support.place(conn, DS, supply, None, delivery)
        supply_holds.raise_hold(conn, dataset_id=DS, supply_id=supply,
                                kind=supply_holds.ASSIGNMENT_RULE,
                                reason={"unavailable": [], "considered": []},
                                raised_by="pytest")
        said = self._refused(conn, None, supply)
        assert "held" in said
        assert f"\n  mothman supply decide --operation place --dataset {DS} --supply {supply}" \
            in said

    def test_a_rejected_supply_names_promote(self, conn, minted, quiet):
        state, supply = parity.ex_rejected(conn, minted)
        said = self._refused(conn, state.period, supply)
        assert "rejected" in said
        assert f"\n  mothman supply decide --operation promote --dataset {DS} --period " \
               f"{state.period} --supply {supply}" in said

    def test_a_superseded_supply_names_un_supersede(self, conn, minted, quiet):
        from qa_tools.common import supersession

        state, _newer = parity.ov_superseded_under_promoted(conn, minted)
        older = supersession.superseded_in(conn, DS, state.period)[0]["supply"]
        said = self._refused(conn, state.period, older)
        assert "superseded" in said
        assert f"\n  mothman supply decide --operation un-supersede --dataset {DS} --period " \
               f"{state.period} --supply {older}" in said

    def test_one_file_of_an_open_pair_is_settled_first(self, conn, minted, quiet):
        state, pair = parity.ex_two_files(conn, minted)
        with pytest.raises(fd.OpenPair) as got:
            fd.apply(fd.Request(operation=fd.RECHECK, dataset_id=state.dataset_id,
                                actor=_actor(), reason="r", confirmed=True,
                                period=state.period, supply=pair),
                     effective_at=_iso(_now()), conn=conn)
        said = str(got.value)
        assert "Filing decisions" in said and "Supplies waiting on a decision" in said
        assert "settling it checks each file that becomes a supply" in said

    def test_a_refused_dataset_gives_the_backstops_finding_and_fix(self, conn, minted, quiet,
                                                                   monkeypatch):
        """Criterion 23."""
        from qa_tools.common import agreement_drift

        class Refusal:
            def message(self):
                return "FINDING: 2024-Q1 moved.\n  paste: the fix"

        monkeypatch.setattr(agreement_drift, "refusal_for", lambda c, ds, **k: Refusal())
        state, supply = parity.ex_awaiting_decision(conn, minted)
        said = self._refused(conn, state.period, supply)
        assert "judged past changed without a declared correction" in said
        assert "\nFINDING: 2024-Q1 moved.\n  paste: the fix" in said
        assert "re-check can be raised again once the correction is declared" in said



class TestThroughTheRealExecutor:
    """Criteria 7, 8 and 25: recheck.run - the claim and the executor that
    applies the gate to every other re-check - with only the four tools'
    run stubbed (it needs real tables; the gate does not)."""

    def _run(self, conn, minted, monkeypatch, build):
        from qa_tools.common import promotion

        asked = []
        monkeypatch.setattr(recheck, "execute", lambda **k: (object(), []))
        monkeypatch.setattr(promotion, "after_runs", lambda *a, **k: asked.append(k) or
                            promotion.AfterRun(promoted=(), refused={}, failed={}))
        monkeypatch.setattr(promotion, "report", lambda o: None)
        state, supply = build(conn, minted)
        got = _recheck(conn, state.period, supply)
        (cause,) = conn.execute(f"SELECT max(id) FROM {dl.TABLE} WHERE supply = ?",
                                [supply]).fetchall()[0]
        done = recheck.run(got.owed[0], run_by="pytest@example.org")
        after = conn.execute(f"SELECT action FROM {dl.TABLE} WHERE supply = ? AND id > ?",
                             [supply, cause]).fetchall()
        return state, supply, done, asked, after

    def test_a_promoted_supply_is_never_regated_and_stays_promoted(self, conn, minted, quiet,
                                                                   monkeypatch):
        state, supply, done, asked, after = self._run(conn, minted, monkeypatch,
                                                      parity.ex_promoted)
        assert done.completed, done.message
        assert asked == [], "the gate was asked about a promoted supply's re-check"
        assert after == [], f"the re-check of a promoted supply appended {after}"
        assert dl.promoted_into(conn, DS, state.period) == supply
        assert done.stays_promoted and done.promoted is None
        assert f"still promoted - {state.period} keeps it" in done.message

    def test_a_waiting_supply_is_gated_as_an_arrival_is(self, conn, minted, quiet,
                                                        monkeypatch):
        _state, _supply, done, asked, _after = self._run(conn, minted, monkeypatch,
                                                         parity.ex_awaiting_decision)
        assert done.completed, done.message
        assert len(asked) == 1 and not done.stays_promoted


class TestPromotedThenRecheckedWorse:
    """Criteria 15 and 21, and REQ-PIPE-122 criterion 14 as amended (T7): a
    promoted supply whose re-check came back worse than the verdict it was
    promoted on is listed under its own heading, needs a person, and owes an
    acknowledgement until a person acknowledges or demotes it."""

    @pytest.fixture
    def worse(self, conn, minted, quiet, monkeypatch):
        from qa_tools.common import supply_status

        verdict = {"now": "green"}
        monkeypatch.setattr(supply_status, "status", lambda c, ds, s, **k: verdict["now"])
        state, supply = parity.ex_promoted(conn, minted)
        _recheck(conn, state.period, supply)
        verdict["now"] = "red"
        return state, supply, verdict

    def test_it_is_listed_with_both_verdicts(self, conn, worse):
        from qa_tools.common import rechecking

        state, supply, _ = worse
        [w] = [w for w in rechecking.worse_than_promoted(conn, DS) if w.supply == supply]
        assert (w.period, w.promoted_on, w.now) == (state.period, "green", "red")

    def test_it_has_its_own_heading_in_the_queue(self, conn, worse):
        from qa_tools.common import filing_queue

        state, supply, _ = worse
        [item] = [s for s in filing_queue.awaiting(conn, parity.COL) if s.supply == supply]
        assert item.state == filing_queue.RECHECKED_WORSE
        assert item.reason.startswith("Promoted, then re-checked red")
        assert "promoted on green" in item.reason

    def test_it_owes_an_acknowledgement_whatever_the_amber_setting(self, conn, worse):
        from qa_tools.common import acknowledgement, slot_state

        state, supply, _ = worse
        assert acknowledgement.why_not_owed(conn, DS, supply, state.period) is None
        assert acknowledgement.owed(conn, DS, state.period) == supply
        assert slot_state.AWAITING_ACKNOWLEDGEMENT in slot_state.NEEDS_ACTION

    def test_acknowledging_it_takes_it_off_the_list(self, conn, worse):
        from qa_tools.common import acknowledgement, rechecking

        state, supply, _ = worse
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        assert supply not in {w.supply for w in rechecking.worse_than_promoted(conn, DS)}
        assert acknowledgement.owed(conn, DS, state.period) is None

    def test_demoting_it_takes_it_off_the_list(self, conn, worse):
        from qa_tools.common import rechecking

        state, supply, _ = worse
        _person(conn, fd.DEMOTE, period=state.period, supply=supply)
        assert supply not in {w.supply for w in rechecking.worse_than_promoted(conn, DS)}

    def test_re_checked_no_worse_is_not_listed(self, conn, worse):
        from qa_tools.common import acknowledgement, rechecking

        state, supply, verdict = worse
        verdict["now"] = "green"
        assert supply not in {w.supply for w in rechecking.worse_than_promoted(conn, DS)}
        assert acknowledgement.why_not_owed(conn, DS, supply, state.period) is not None


# ---------------------------------------------------------------------------
# The routes: the terminal's door and `mothman supply decide`.
# ---------------------------------------------------------------------------

@pytest.fixture
def cli(monkeypatch):
    from click.testing import CliRunner

    from cli import filing_tui, supply
    from qa_tools.common import knock_on, people

    monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                        lambda: people.person_by_email(parity.REAL_PERSON))
    monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
    monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])
    return lambda argv: CliRunner().invoke(supply.supply_group, argv)


def _said(output: str) -> str:
    import re

    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    return " ".join(re.sub(r"[─-╿]", " ", plain).split())


def _decide(state, supply, *extra):
    return ["decide", "--operation", "re-check", "--dataset", DS, "--period", state.period,
            "--supply", supply, "--reason", "our check was wrong", "--yes", *extra]


class TestTheDoorOffersIt:
    """Criteria 11 and 26."""

    @pytest.mark.parametrize("state", ["awaiting-decision", "returned-by-a-person",
                                       "amber-waiting", "promoted",
                                       "awaiting-acknowledgement", "another-version-waiting"])
    def test_on_a_waiting_or_promoted_supply_after_the_settling_decisions(self, state):
        from qa_tools.common import filing_queue, slot_state

        supply_scoped, _ = filing_queue.operations_for(slot_state.SlotState(
            dataset_id=DS, period="2099-x", state=state, supply=f"{DS}@1"))
        assert supply_scoped[-1] == fd.RECHECK, supply_scoped

    @pytest.mark.parametrize("state", ["two-files", "rejected", "could-not-be-loaded"])
    def test_not_where_it_would_be_refused(self, state):
        from qa_tools.common import filing_queue, slot_state

        supply_scoped, _ = filing_queue.operations_for(slot_state.SlotState(
            dataset_id=DS, period="2099-x", state=state, supply=f"{DS}@1"))
        assert fd.RECHECK not in supply_scoped

    def test_on_a_promoted_supply_rechecked_worse_beside_acknowledge_and_demote(self):
        from qa_tools.common import filing_queue, slot_state

        supply_scoped, _ = filing_queue.operations_for(slot_state.SlotState(
            dataset_id=DS, period="2099-x", state=filing_queue.RECHECKED_WORSE,
            supply=f"{DS}@1"))
        assert supply_scoped[:2] == (fd.ACKNOWLEDGE, fd.DEMOTE)
        assert supply_scoped[-1] == fd.RECHECK

    def test_its_label_says_what_it_does_and_costs(self):
        from cli import filing_tui

        assert filing_tui._WHAT_IT_DOES[fd.RECHECK] == (
            "Re-check: run its checks again where it is (about a minute; recorded and "
            "published)")

    def test_the_queue_heading_names_the_new_verdict(self):
        from cli import filing_tui
        from qa_tools.common import filing_queue, slot_state

        label = filing_tui._label(slot_state.SlotState(
            dataset_id=DS, period="2099-x", state=filing_queue.RECHECKED_WORSE,
            supply=f"{DS}@1", reason="Promoted, then re-checked red: ..."))
        assert "Promoted, then re-checked red" in label

    def test_the_reason_is_said_to_be_published(self, conn, minted, quiet, monkeypatch):
        """Criterion 14."""
        from cli import common, filing_tui

        asked = []
        monkeypatch.setattr(common, "text_prompt",
                            lambda message, **k: asked.append(message) or None)
        state, supply = parity.ex_awaiting_decision(conn, minted)
        assert filing_tui.apply_decision(operation=fd.RECHECK, dataset_id=DS,
                                         period=state.period, supply=supply,
                                         actor=_actor()) is None
        assert asked and "published" in asked[0] and "dashboard" in asked[0]


class TestTheDoorRunsItStraightAfter:
    """Criterion 4: recorded in the door, its owed re-check runs once the
    transaction has committed, while the person waits."""

    def test_the_owed_recheck_runs_after_the_decision_is_recorded(self, conn, minted, quiet,
                                                                  monkeypatch):
        from cli import filing_tui

        state, supply = parity.ex_awaiting_decision(conn, minted)
        seen = []

        def run(owed_id, **k):
            # COMMITTED BY NOW: the decision is visible to a connection of its own.
            from qa_tools.common import supply_db

            with supply_db.connect(label="test-recheck-door") as other:
                seen.append(other.execute(
                    f"SELECT action FROM {dl.TABLE} WHERE supply = ? ORDER BY id DESC "
                    "LIMIT 1", [supply]).fetchall())
            return recheck.Outcome(owed_id, "rk", True, "m", status="green",
                                   period=state.period, promoted=True, before="red")
        monkeypatch.setattr(recheck, "run", run)
        got = filing_tui.apply_decision(operation=fd.RECHECK, dataset_id=DS,
                                        period=state.period, supply=supply,
                                        reason="our check was wrong", actor=_actor(), yes=True)
        assert got is not None and got.checks_finished
        assert seen == [[(dl.RECHECK,)]]


class TestDecideLeavesItOwed:
    """Criterion 5."""

    def test_without_wait_it_names_the_processing_pass(self, conn, minted, cli, monkeypatch):
        def refuse(*a, **k):
            raise AssertionError("decide without --wait must not run the checks")

        monkeypatch.setattr(recheck, "run", refuse)
        state, supply = parity.ex_awaiting_decision(conn, minted)
        got = cli(_decide(state, supply))
        assert got.exit_code == 0, got.output
        assert "\nmothman pipeline process\n" in got.output
        said = _said(got.output)
        assert "checks are owed" in said and "not only this one" in said
        assert "Nothing runs until the processing pass or that command does" in said


class TestDecideWait:
    """Criteria 13, 16, 17 and 18."""

    def _runs_as(self, monkeypatch, **outcome):
        def fake(owed_id, **k):
            if "raise_" in outcome:
                raise outcome["raise_"]
            return recheck.Outcome(owed_id, "rk", **outcome)
        monkeypatch.setattr(recheck, "run", fake)

    def test_a_promoted_supply_rechecked_red_stays_and_names_demote_and_acknowledge(
            self, conn, minted, cli, monkeypatch):
        state, supply = parity.ex_promoted(conn, minted)
        self._runs_as(monkeypatch, completed=True, message="m", status="red",
                      period=state.period, stays_promoted=True, before="green")
        got = cli(_decide(state, supply, "--wait"))
        assert got.exit_code == 0, got.output
        said = _said(got.output)
        assert f"{supply} in {state.period} was green, re-checked red" in said
        assert f"It is still promoted - {state.period} keeps it" in said
        assert (f"\nmothman supply decide --operation demote --dataset {DS} --period "
                f"{state.period} --supply {supply}") in got.output
        assert (f"\nmothman supply decide --operation acknowledge --dataset {DS} --period "
                f"{state.period} --supply {supply}") in got.output

    def test_a_waiting_supply_says_what_the_gate_did(self, conn, minted, cli, monkeypatch):
        state, supply = parity.ex_awaiting_decision(conn, minted)
        self._runs_as(monkeypatch, completed=True, message="m", status="green",
                      period=state.period, promoted=True, before="red")
        got = cli(_decide(state, supply, "--wait"))
        said = _said(got.output)
        assert got.exit_code == 0, got.output
        assert "was red, re-checked green" in said and "promoted it into" in said

    def test_ctrl_c_leaves_it_owed_without_a_traceback(self, conn, minted, cli, monkeypatch):
        from cli import filing_tui

        state, supply = parity.ex_awaiting_decision(conn, minted)
        self._runs_as(monkeypatch, raise_=KeyboardInterrupt())
        got = cli(_decide(state, supply, "--wait"))
        assert got.exit_code == filing_tui.CHECKS_STILL_OWED_EXIT, got.output
        assert "Traceback" not in got.output
        said = _said(got.output)
        assert "re-check stands" in said and "still owed" in said
        assert "\nmothman pipeline process" in got.output
