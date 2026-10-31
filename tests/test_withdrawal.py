"""Withdrawing an acknowledgement or a mark as not supplied (REQ-PIPE-166).

Built on the door/flag parity test's own examples, in this worker's database.
"""
from __future__ import annotations

import pytest

import test_door_flag_parity as parity
from qa_tools.common import decision_log as dl
from qa_tools.common import filing_decisions as fd
from qa_tools.common import people, slot_state, slots
from test_door_flag_parity import (DS, _actor, _forget_its_filings, _iso, _now, _person,
                                   minted, quiet)

conn = parity.conn
#: The parity module's fixtures, its autouse tidy-up included.
__all__ = ["conn", "minted", "quiet", "_forget_its_filings"]


def _withdraw(conn, op, period, supply=None, reason="recorded on the wrong slot"):
    return fd.apply(fd.Request(operation=op, dataset_id=DS, actor=_actor(), reason=reason,
                               confirmed=True, period=period, supply=supply),
                    effective_at=_iso(_now()), conn=conn)


def _state_now(conn, minted, period):
    slot = next(s for s in slots.slots_for_dataset(DS) if s.name == period)
    return slot_state.state_of(conn, dataset_id=DS, slot=slot, now=minted.now,
                               filings={}, ever_delivered=True)


def _last(conn, action):
    return conn.execute(f"SELECT id, caused_by_decision, actor_kind, to_slot, supply "
                        f"FROM {dl.TABLE} WHERE action = ? ORDER BY id DESC LIMIT 1",
                        [action]).fetchall()[0]


class TestTheOperations:
    """Criteria 1, 2 and 8."""

    def test_named_and_offered_on_both_routes(self):
        assert fd.WITHDRAW_ACKNOWLEDGEMENT == "withdraw-acknowledgement"
        assert fd.WITHDRAW_NOT_SUPPLIED == "withdraw-not-supplied"
        assert {fd.WITHDRAW_ACKNOWLEDGEMENT, fd.WITHDRAW_NOT_SUPPLIED} <= set(fd.OPERATIONS)
        assert not {fd.WITHDRAW_ACKNOWLEDGEMENT, fd.WITHDRAW_NOT_SUPPLIED} & set(fd.TERMINAL_ONLY)
        assert fd.WITHDRAW_NOT_SUPPLIED in fd.PERIOD_SCOPED
        assert fd.WITHDRAW_ACKNOWLEDGEMENT in fd.SUPPLY_SCOPED

    def test_a_reason_is_required(self, conn, minted, quiet):
        state, _ = parity.ex_not_supplied_accepted(conn, minted)
        with pytest.raises(dl.DecisionRefused):
            _withdraw(conn, fd.WITHDRAW_NOT_SUPPLIED, state.period, reason=" ")


class TestWithdrawingAMark:
    """Criteria 2, 3 and 5."""

    def test_the_period_reads_as_if_never_marked(self, conn, minted, quiet):
        state, _ = parity.ex_not_supplied_accepted(conn, minted)
        assert state.state == slot_state.NOT_SUPPLIED_ACCEPTED
        (mark_id,) = conn.execute(
            f"SELECT max(id) FROM {dl.TABLE} WHERE action = ? AND to_slot = ?",
            [dl.MARK_NOT_SUPPLIED, state.period]).fetchall()[0]
        got = _withdraw(conn, fd.WITHDRAW_NOT_SUPPLIED, state.period)
        assert got.changed
        wid, caused_by, kind, to_slot, _supply = _last(conn, dl.WITHDRAW_NOT_SUPPLIED)
        assert (caused_by, kind, to_slot) == (mark_id, dl.PERSON, state.period)
        # THE MARK STAYS, unaltered (criterion 2).
        assert conn.execute(f"SELECT action FROM {dl.TABLE} WHERE id = ?",
                            [mark_id]).fetchall() == [(dl.MARK_NOT_SUPPLIED,)]
        now = _state_now(conn, minted, state.period)
        assert now.state != slot_state.NOT_SUPPLIED_ACCEPTED
        assert now.state in slot_state.NEEDS_ACTION and now.closed

    def test_nothing_to_withdraw_is_refused(self, conn, minted, quiet):
        state, _ = parity.ex_closed_unfilled(conn, minted)
        with pytest.raises(dl.DecisionRefused, match="no mark as not supplied"):
            _withdraw(conn, fd.WITHDRAW_NOT_SUPPLIED, state.period)

    def test_withdrawn_twice_is_refused(self, conn, minted, quiet):
        state, _ = parity.ex_not_supplied_accepted(conn, minted)
        _withdraw(conn, fd.WITHDRAW_NOT_SUPPLIED, state.period)
        with pytest.raises(dl.DecisionRefused, match="no mark as not supplied"):
            _withdraw(conn, fd.WITHDRAW_NOT_SUPPLIED, state.period)

    def test_it_can_be_marked_again(self, conn, minted, quiet):
        state, _ = parity.ex_not_supplied_accepted(conn, minted)
        _withdraw(conn, fd.WITHDRAW_NOT_SUPPLIED, state.period)
        _person(conn, fd.MARK_NOT_SUPPLIED, period=state.period)
        assert _state_now(conn, minted, state.period).state == slot_state.NOT_SUPPLIED_ACCEPTED


class TestWithdrawingAnAcknowledgement:
    """Criteria 2, 4, 5 and 17."""

    @pytest.fixture
    def acknowledged(self, conn, minted, quiet):
        state, supply = parity.ex_awaiting_acknowledgement(conn, minted)
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        (ack_id,) = conn.execute(f"SELECT max(id) FROM {dl.TABLE} WHERE action = ? AND "
                                 "supply = ?", [dl.ACKNOWLEDGE, supply]).fetchall()[0]
        return state, supply, ack_id

    def test_it_awaits_acknowledgement_again(self, conn, acknowledged):
        from qa_tools.common import acknowledgement

        state, supply, ack_id = acknowledged
        assert acknowledgement.owed(conn, DS, state.period) is None
        _withdraw(conn, fd.WITHDRAW_ACKNOWLEDGEMENT, state.period, supply)
        _wid, caused_by, kind, to_slot, wsupply = _last(conn, dl.WITHDRAW_ACKNOWLEDGEMENT)
        assert (caused_by, kind, to_slot, wsupply) == (ack_id, dl.PERSON, state.period, supply)
        assert acknowledgement.owed(conn, DS, state.period) == supply
        assert acknowledgement.acknowledged_by(conn, DS, supply, state.period) is None

    def test_acknowledged_again_the_newer_one_stands(self, conn, acknowledged):
        from qa_tools.common import acknowledgement

        state, supply, _ack_id = acknowledged
        _withdraw(conn, fd.WITHDRAW_ACKNOWLEDGEMENT, state.period, supply)
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        got = acknowledgement.acknowledged_by(conn, DS, supply, state.period)
        assert got is not None and got["reason"] == "seeding"
        assert acknowledgement.owed(conn, DS, state.period) is None
        (newest,) = conn.execute(f"SELECT max(id) FROM {dl.TABLE} WHERE action = ? AND "
                                 "supply = ?", [dl.ACKNOWLEDGE, supply]).fetchall()[0]
        assert got["id"] == newest

    def test_nothing_to_withdraw_is_refused(self, conn, minted, quiet):
        state, supply = parity.ex_awaiting_acknowledgement(conn, minted)
        with pytest.raises(dl.DecisionRefused, match="no acknowledgement"):
            _withdraw(conn, fd.WITHDRAW_ACKNOWLEDGEMENT, state.period, supply)

    def test_a_rechecked_worse_supply_is_listed_again(self, conn, minted, quiet,
                                                      monkeypatch):
        """Criterion 9."""
        from qa_tools.common import recheck, rechecking, supply_status

        verdict = {"now": "green"}
        monkeypatch.setattr(supply_status, "status", lambda c, ds, s, **k: verdict["now"])
        state, supply = parity.ex_promoted(conn, minted)
        got = fd.apply(fd.Request(operation=fd.RECHECK, dataset_id=DS, actor=_actor(),
                                  reason="r", confirmed=True, period=state.period,
                                  supply=supply), effective_at=_iso(_now()), conn=conn)
        recheck.clear(got.owed[0], "rk")
        verdict["now"] = "red"
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        assert supply not in {w.supply for w in rechecking.worse_than_promoted(conn, DS)}
        _withdraw(conn, fd.WITHDRAW_ACKNOWLEDGEMENT, state.period, supply)
        assert supply in {w.supply for w in rechecking.worse_than_promoted(conn, DS)}


class TestTheRoutes:
    """Criteria 6, 10 and 14."""

    def test_the_door_offers_withdraw_not_supplied_beside_substitute(self):
        from qa_tools.common import filing_queue

        _, period_scoped = filing_queue.operations_for(slot_state.SlotState(
            dataset_id=DS, period="2099-x", state=slot_state.NOT_SUPPLIED_ACCEPTED))
        assert period_scoped == (fd.SUBSTITUTE, fd.WITHDRAW_NOT_SUPPLIED)

    def test_withdraw_acknowledgement_is_offered_where_one_stands(self, conn, minted, quiet):
        from qa_tools.common import filing_queue

        state, supply = parity.ex_awaiting_acknowledgement(conn, minted)
        assert fd.WITHDRAW_ACKNOWLEDGEMENT not in filing_queue.acknowledgement_offers(conn, state)
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        assert filing_queue.acknowledgement_offers(conn, state) == (fd.WITHDRAW_ACKNOWLEDGEMENT,)

    def test_the_reason_is_said_to_be_published(self, conn, minted, quiet, monkeypatch):
        from cli import common, filing_tui

        asked = []
        monkeypatch.setattr(common, "text_prompt",
                            lambda message, **k: asked.append(message) or None)
        state, _ = parity.ex_not_supplied_accepted(conn, minted)
        filing_tui.apply_decision(operation=fd.WITHDRAW_NOT_SUPPLIED, dataset_id=DS,
                                  period=state.period, actor=_actor())
        assert asked and "published" in asked[0] and "dashboard" in asked[0]
        # A MARK HAS NO SUPPLY (#193 F8): its reason is shown in the period's row.
        assert "beside the supply" not in asked[0] and "period" in asked[0]

    def test_confirming_a_mark_withdrawal_names_it_and_what_follows(self, conn, minted, quiet):
        state, _ = parity.ex_not_supplied_accepted(conn, minted)
        found = fd.consequences(conn, fd.Request(
            operation=fd.WITHDRAW_NOT_SUPPLIED, dataset_id=DS, actor=_actor(), reason="r",
            period=state.period))
        said = " ".join(found.notes)
        assert "seeding" in said and people.display_name(parity.REAL_PERSON) in said
        # REQ-PIPE-166 c14 AS AMENDED 2026-10-15 (Keith, morning report 5 Q14):
        # owed again, and no promise about the ticket.
        assert "is owed again and reads overdue or never supplied again" in said
        assert "ticket" not in said
        assert "can be recorded again" in said
        assert not found.lines, "no --acknowledge key on the flag route"
        got = _withdraw(conn, fd.WITHDRAW_NOT_SUPPLIED, state.period)
        assert "ticket" not in got.message

    def test_confirming_an_acknowledgement_withdrawal_names_it_and_what_follows(
            self, conn, minted, quiet):
        state, supply = parity.ex_awaiting_acknowledgement(conn, minted)
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        said = " ".join(fd.consequences(conn, fd.Request(
            operation=fd.WITHDRAW_ACKNOWLEDGEMENT, dataset_id=DS, actor=_actor(), reason="r",
            period=state.period, supply=supply)).notes)
        assert "seeding" in said
        assert "stops showing it from now" in said and "supply's history" in said
        assert "needs a person again" in said and "can be recorded again" in said

    def test_nothing_standing_is_refused_before_the_reason(self, conn, minted, quiet,
                                                           monkeypatch):
        from cli import common, filing_tui

        asked = []
        monkeypatch.setattr(common, "text_prompt",
                            lambda message, **k: asked.append(message) or "r")
        state, _ = parity.ex_closed_unfilled(conn, minted)
        assert filing_tui.apply_decision(operation=fd.WITHDRAW_NOT_SUPPLIED, dataset_id=DS,
                                         period=state.period, actor=_actor()) is None
        assert asked == []


class TestTheDashboardData:
    """Criteria 13, 15 and 16: the builders carry each withdrawal's instant,
    who and why, beside the entry it withdrew - the page compares them with
    the date on show."""

    def test_a_withdrawn_mark_travels_with_its_withdrawal(self, conn, minted, quiet):
        from pipeline import closed_slots

        state, _ = parity.ex_not_supplied_accepted(conn, minted)
        _withdraw(conn, fd.WITHDRAW_NOT_SUPPLIED, state.period, reason="it came after all")
        (slot,) = [s for s in closed_slots.for_dataset(DS, conn, now=minted.now)
                   if s["period"] == state.period]
        (mark,) = slot["marks"]
        assert mark["reason"] == "seeding" and mark["withdrawn"] is not None
        assert mark["withdrawn"]["reason"] == "it came after all"
        assert mark["withdrawn"]["at"] >= mark["at"]
        assert "@" not in mark["withdrawn"]["actor"], "a name, never the email"

    def test_a_standing_mark_carries_no_withdrawal(self, conn, minted, quiet):
        from pipeline import closed_slots

        state, _ = parity.ex_not_supplied_accepted(conn, minted)
        (slot,) = [s for s in closed_slots.for_dataset(DS, conn, now=minted.now)
                   if s["period"] == state.period]
        assert [m["withdrawn"] for m in slot["marks"]] == [None]

    def test_every_acknowledgement_travels_with_its_withdrawal(self, conn, minted, quiet,
                                                               monkeypatch):
        from pipeline import acknowledgements, slot_timeline

        state, supply = parity.ex_awaiting_acknowledgement(conn, minted)
        monkeypatch.setattr(slot_timeline, "_run_for",
                            lambda c, ds, s: "run-x" if s == supply else None)
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        _withdraw(conn, fd.WITHDRAW_ACKNOWLEDGEMENT, state.period, supply, reason="too quick")
        got = acknowledgements.for_dataset(DS, conn)["run-x"]
        assert got["acknowledged"] is None
        (only,) = got["acks"]
        assert only["withdrawn"]["reason"] == "too quick"
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        got = acknowledgements.for_dataset(DS, conn)["run-x"]
        assert [a["withdrawn"] is None for a in got["acks"]] == [False, True]
        assert got["acknowledged"]["reason"] == "seeding"


def test_the_page_has_words_for_every_decision():
    """Criterion 12: every action the log admits has the page's words for
    what it did, so a new one cannot reach the page unnamed."""
    import re
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent
            / "dashboard" / "qa-reporting-dashboard.template.html").read_text()
    block = re.search(r"const DECISION_DONE\s*=\s*\{(.*?)\};", html, re.S)
    assert block, "DECISION_DONE not found in the template"
    named = set(re.findall(r'"?([a-z][a-z-]*)"?\s*:\s*"', block.group(1)))
    assert dl.ACTIONS, "the log admits no actions - nothing to check"
    assert set(dl.ACTIONS) <= named, sorted(set(dl.ACTIONS) - named)


class TestCriticFindingsOn193:
    """post-build-review #193: what a person is told when withdrawing."""

    def test_a_marks_confirmation_gives_the_asset_clock_and_a_name(self, conn, minted, quiet):
        """F2: the mark's instant was printed as raw UTC, and both
        confirmations printed the recorded email rather than a name."""
        state, _ = parity.ex_not_supplied_accepted(conn, minted)
        said = " ".join(fd.consequences(conn, fd.Request(
            operation=fd.WITHDRAW_NOT_SUPPLIED, dataset_id=DS, actor=_actor(), reason="r",
            period=state.period)).notes)
        assert "+00:00" not in said and "T" not in said.split("recorded ")[1][:12]
        assert parity.REAL_PERSON not in said, said

    def test_an_acknowledgements_confirmation_gives_a_name(self, conn, minted, quiet):
        state, supply = parity.ex_awaiting_acknowledgement(conn, minted)
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        said = " ".join(fd.consequences(conn, fd.Request(
            operation=fd.WITHDRAW_ACKNOWLEDGEMENT, dataset_id=DS, actor=_actor(), reason="r",
            period=state.period, supply=supply)).notes)
        assert parity.REAL_PERSON not in said, said

    def test_a_lapsed_acknowledgement_is_not_said_to_need_a_person(self, conn, minted, quiet):
        """F3: once the supply has left its period nothing is owed, so the
        confirmation must not promise it awaits acknowledgement again."""
        from qa_tools.common import acknowledgement

        state, supply = parity.ex_awaiting_acknowledgement(conn, minted)
        _person(conn, fd.ACKNOWLEDGE, period=state.period, supply=supply)
        _person(conn, fd.DEMOTE, period=state.period, supply=supply)
        said = " ".join(fd.consequences(conn, fd.Request(
            operation=fd.WITHDRAW_ACKNOWLEDGEMENT, dataset_id=DS, actor=_actor(), reason="r",
            period=state.period, supply=supply)).notes)
        assert "needs a person again" not in said
        assert "no longer" in said and state.period in said
        _withdraw(conn, fd.WITHDRAW_ACKNOWLEDGEMENT, state.period, supply)
        assert acknowledgement.owed(conn, DS, state.period) is None

    def test_withdrawing_an_acknowledgement_without_a_supply_says_so(self, conn, minted, quiet):
        """F9: the refusal named a blank supply and blamed the record."""
        state, _ = parity.ex_awaiting_acknowledgement(conn, minted)
        with pytest.raises(dl.DecisionRefused, match="names no supply"):
            _withdraw(conn, fd.WITHDRAW_ACKNOWLEDGEMENT, state.period, None)
