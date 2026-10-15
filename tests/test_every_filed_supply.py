"""Every supply filed to a period, listed at the terminal's period door and in
the Filing decisions queue (REQ-GHUB-229).

THE CASE THAT PROMPTED IT (criterion 16): a period holding a good supply
waiting on a decision, then a resupply that could not be loaded. The slot
speaks for its latest live filing - the failed one - so the period door
offered the failed load promote, and the queue listed the failed load and
dropped the good supply from every entry. Built in this test worker's own
database, on a minted period (test_door_flag_parity's own fixtures).
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

import test_door_flag_parity as parity
from qa_tools.common import filing_decisions as fd
from qa_tools.common import filing_queue, slot_state
from test_door_flag_parity import (COL, DS, TABLE, _filed, _forget_its_filings, _iso,
                                   _now, _received_late, minted, quiet)

conn = parity.conn
__all__ = ["_forget_its_filings", "minted", "quiet"]


def _failed_resupply(conn, period: str) -> str:
    """A supply filed to `period` whose load failed, received after the good one."""
    import filing_support
    from qa_tools.common import assignment, load_log

    arrival = f"t{uuid.uuid4().hex[:10]}"
    load_log.record(f"probe-{arrival}", DS, f"{TABLE}__{arrival}", load_log.FAILED,
                    _iso(_now()), reason="the file is empty", conn=conn)
    supply = f"{DS}@{arrival}"
    filing_support.file(assignment.Assignment(
        dataset_id=DS, supply_id=supply, slot=period, branch=assignment.OPEN_UNFILLED,
        considered=(period,), received_at=_now() - timedelta(minutes=5)))
    return supply


@pytest.fixture
def mixed(conn, minted):
    """(slot, good, failed): a good supply waiting, then a failed resupply."""
    s = minted("due")
    good, _ = _filed(conn, s.name, _received_late(s))
    failed = _failed_resupply(conn, s.name)
    (slot,) = [x for x in filing_queue.slots_of(conn, COL, dataset_id=DS)
               if x.period == s.name]
    return slot, good, failed


class TestAFailedResupplyHidesNothing:
    """Criterion 16."""

    def test_the_period_lists_both_each_with_its_own_state(self, conn, mixed):
        slot, good, failed = mixed
        got = {e.state.supply: e for e in filing_queue.supplies_in(conn, slot)}
        assert set(got) == {good, failed}
        assert got[good].state.state == slot_state.AWAITING_DECISION
        assert got[failed].state.state == filing_queue.COULD_NOT_LOAD
        assert got[failed].state.reason == "the file is empty"

    def test_promote_on_the_good_one_and_only_reject_on_the_failed_one(self, conn, mixed):
        slot, good, failed = mixed
        got = {e.state.supply: e for e in filing_queue.supplies_in(conn, slot)}
        assert fd.PROMOTE in filing_queue.operations_for(got[good].state)[0]
        assert filing_queue.operations_for(got[failed].state)[0] == (fd.REJECT,)

    def test_the_queue_lists_both(self, conn, mixed):
        _slot, good, failed = mixed
        queued = {s.supply: s.state for s in filing_queue.awaiting(conn, COL)}
        assert queued.get(good) == slot_state.AWAITING_DECISION
        assert queued.get(failed) == filing_queue.COULD_NOT_LOAD

    def test_the_door_lists_both_and_offers_each_its_own(self, conn, mixed, monkeypatch,
                                                        capsys):
        """Driven through period_flow itself: the period line says 2
        supplies, both are listed with their states, and choosing each
        offers what that supply's own state offers."""
        from cli import filing_tui

        slot, good, failed = mixed
        offered: dict = {}
        asked: list = []
        for pick in (good, failed):
            def select(msg, choices, *, _pick=pick, **_k):
                asked.append((msg, list(choices)))
                if msg == "Which dataset?":
                    return DS
                if msg.startswith("Which period"):
                    return next(c for c in choices if c.startswith(slot.period))
                return next(c for c in choices
                            if filing_tui.arrived(_pick) in c)
            monkeypatch.setattr(filing_tui.common, "select", select)
            monkeypatch.setattr(filing_tui, "_decide_on",
                                lambda s, offer, _p=pick: offered.__setitem__(_p, (s, offer)))
            filing_tui.period_flow(COL)
        period_line = next(c for m, cs in asked if m.startswith("Which period")
                           for c in cs if c.startswith(slot.period))
        assert "2 supplies" in period_line
        out = capsys.readouterr().out
        assert "could not be loaded" in out and "waiting on a decision" in out
        assert fd.PROMOTE in offered[good][1]
        assert offered[failed][1] == (fd.REJECT,)


class TestEachListedSupplyCarriesAVerdict:
    """Criteria 4 and 11."""

    def test_no_check_read_it(self, conn, mixed):
        slot, good, _failed = mixed
        (entry,) = [e for e in filing_queue.supplies_in(conn, slot) if e.state.supply == good]
        assert entry.verdict == filing_queue.NO_VERDICT

    def test_a_verdict_that_cannot_be_read_is_said_and_the_supply_still_listed(
            self, conn, mixed, monkeypatch):
        from qa_tools.common import supply_status

        def broken(*_a, **_k):
            raise RuntimeError("results unreadable")
        monkeypatch.setattr(supply_status, "status", broken)
        slot, good, failed = mixed
        got = filing_queue.supplies_in(conn, slot)
        assert {e.state.supply for e in got} == {good, failed}
        assert {e.verdict for e in got} == {filing_queue.VERDICT_UNREADABLE}

    def test_a_recorded_verdict_is_shown(self, conn, mixed, monkeypatch):
        from qa_tools.common import supply_status

        monkeypatch.setattr(supply_status, "status", lambda *a, **k: "amber")
        slot, good, _failed = mixed
        (entry,) = [e for e in filing_queue.supplies_in(conn, slot) if e.state.supply == good]
        assert entry.verdict == "amber"


class TestTheCountIsTheSameEverywhere:
    """Criteria 3 and 15: one line per period, saying how many."""

    def test_one_slot_per_period_with_its_count(self, conn, mixed):
        slot, _good, _failed = mixed
        states = [s for s in filing_queue.slots_of(conn, COL, dataset_id=DS)
                  if s.period == slot.period]
        assert len(states) == 1
        assert filing_queue.filed_counts(conn, DS)[(DS, slot.period)] == 2

    def test_where_every_period_stands_shows_the_count(self, conn, mixed, capsys,
                                                      monkeypatch):
        from cli import filing_tui

        slot, _good, _failed = mixed
        monkeypatch.setattr(filing_tui.console, "width", 220)
        filing_tui.standing_view(COL, DS)
        (line,) = [ln for ln in capsys.readouterr().out.splitlines()
                   if ln.startswith(slot.period)]
        assert "2 supplies" in line


class TestAPromotedPeriodWithAnotherVersionWaiting:
    """Criteria 5 and 7: in place, and waiting behind it - one period line."""

    def test_both_listed_in_their_own_words(self, conn, minted):
        slot, promoted = parity.ex_promoted(conn, minted)
        later, _ = _filed(conn, slot.period, _iso(_now() - timedelta(hours=1)))
        got = {e.state.supply: e.state for e in filing_queue.supplies_in(conn, slot)}
        assert got[promoted].state == slot_state.PROMOTED
        assert got[later].state == filing_queue.ANOTHER_VERSION_WAITING
        assert fd.PROMOTE in filing_queue.operations_for(got[later])[0]
        assert len([s for s in filing_queue.slots_of(conn, COL, dataset_id=DS)
                    if s.period == slot.period]) == 1


class TestRejectedAndSupersededSayWhoAndWhat:
    """Criterion 5."""

    def test_a_rejected_supply_names_who_rejected_it(self, conn, minted):
        slot, supply = parity.ex_rejected(conn, minted)
        later, _ = _filed(conn, slot.period, _iso(_now() - timedelta(hours=1)))
        (slot,) = [x for x in filing_queue.slots_of(conn, COL, dataset_id=DS)
                   if x.period == slot.period]
        (entry,) = [e for e in filing_queue.supplies_in(conn, slot)
                    if e.state.supply == supply]
        assert entry.state.state == slot_state.REJECTED
        assert parity.REAL_PERSON in entry.state.reason
        # AFTER THE SUPPLIES STILL IN PLAY (Keith, 2026-10-15): the rejected
        # one arrived first and is listed last.
        assert [e.state.supply for e in filing_queue.supplies_in(conn, slot)] == [later, supply]

    def test_a_superseded_supply_names_what_superseded_it(self, conn, minted):
        slot, newer = parity.ov_superseded_under_promoted(conn, minted)
        got = {e.state.supply: e.state for e in filing_queue.supplies_in(conn, slot)}
        (older,) = [s for s in got if s != newer]
        assert got[older].state == filing_queue.SUPERSEDED
        assert filing_queue.arrival_key_of(newer) in got[older].reason
        # Its own offer: bringing it back - named, so no version picker.
        assert filing_queue.supersede_offers(conn, got[older]) == (fd.UN_SUPERSEDE,)


class TestAnOpenPairIsOneEntry:
    """Criterion 9."""

    def test_the_pair_is_one_entry_offering_only_settle(self, conn, minted):
        slot, pair = parity.ex_two_files(conn, minted)
        got = filing_queue.supplies_in(conn, slot)
        (entry,) = [e for e in got if e.state.supply == pair]
        assert entry.state.state == slot_state.TWO_FILES
        assert len(entry.state.files) == 2
        assert filing_queue.operations_for(entry.state) == ((fd.CHOOSE_FILE,), ())


class TestTheLogUnreachableListsNothing:
    """Criterion 10."""

    def test_it_says_so(self, monkeypatch, capsys):
        from cli import filing_tui

        monkeypatch.setattr(filing_tui.common, "select", lambda msg, choices, **k: DS)

        def unreachable():
            raise filing_queue.LogUnreachable("down")
        monkeypatch.setattr(filing_tui, "open_log", unreachable)
        filing_tui.period_flow(COL)
        out = capsys.readouterr().out
        assert "down" in out or "could not" in out.lower()
