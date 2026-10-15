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
        assert got[older].reason.startswith("by the supply that arrived ")
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


# ---------------------------------------------------------------------------
# delivery-critic on REQ-GHUB-229 (post-build-review #201).
# ---------------------------------------------------------------------------

def _slot_of(conn, period, dataset=DS, collection=COL):
    (s,) = [x for x in filing_queue.slots_of(conn, collection, dataset_id=dataset)
            if x.period == period]
    return s


class TestThePromotedSupplyIsInPlaceWhateverElseHappened:
    """#201 F1 and F2: the period's promoted supply reads 'in place' - over an
    open pair, and after an earlier rejection of it."""

    def test_rejected_then_promoted_reads_in_place(self, conn, minted, quiet):
        from test_door_flag_parity import _person

        s = minted("due")
        a, _ = _filed(conn, s.name, _received_late(s))
        _person(conn, fd.REJECT, period=s.name, supply=a)
        _person(conn, fd.PROMOTE, period=s.name, supply=a)
        b, _ = _filed(conn, s.name, _iso(_now() - timedelta(hours=1)))
        got = {e.state.supply: e.state for e in filing_queue.supplies_in(conn, _slot_of(conn, s.name))}
        assert got[a].state == slot_state.PROMOTED
        assert fd.DEMOTE in filing_queue.operations_for(got[a])[0]
        assert got[b].state == filing_queue.ANOTHER_VERSION_WAITING

    def test_an_open_pair_over_a_promoted_supply(self, conn, minted):
        from datetime import date

        import filing_support
        from pair_support import DS as BR
        from pair_support import TABLE as BRT
        from pair_support import Pair, _at, free_day
        from qa_tools.common import hierarchy, supply_db

        day = free_day(conn, date(2026, 11, 1))
        pair = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                                (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
        key = f"{uuid.uuid4().int % 10**18:018d}"
        sup, phys, dlv = f"{BR}@{key}", f"{BRT}__{key}", f"pytest-201-{key}"
        rec = _at(day, "09:00").isoformat()
        conn.execute("INSERT INTO qa.delivery (name, received_at, received_instant) "
                     "VALUES (?, ?, ?)", [dlv, rec, rec])
        conn.execute("INSERT INTO qa.delivery_file (delivery, filename, dataset_id, received_at, "
                     "received_instant, received_from, receipt_sequence) "
                     "VALUES (?, 'x.csv', ?, ?, ?, 'our-clock', 1)", [dlv, BR, rec, rec])
        conn.execute("INSERT INTO qa.filing (dataset_id, supply_id, slot, branch, delivery) "
                     "VALUES (?, ?, ?, 'pytest', ?)", [BR, sup, pair.period, dlv])
        conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{phys}" (id integer)')
        filing_support.checked(conn, BR, sup)
        entry = hierarchy.dataset(BR)
        from qa_tools.common import decision_log as dl
        from qa_tools.common import promotion

        promotion.promote(conn, agency_id=entry.agency_id, collection_id=entry.collection_id,
                          dataset_id=BR, supply=sup, period=pair.period, physical_tables=[phys],
                          actor=promotion.RULE_ACTOR, actor_kind=dl.RULE,
                          effective_at=_iso(_now()), amber=None,
                          reason=promotion.AUTOMATIC_REASON)
        slot = _slot_of(conn, pair.period, BR, entry.collection_id)
        assert slot.state == slot_state.TWO_FILES
        got = {e.state.supply: e.state.state for e in filing_queue.supplies_in(conn, slot)}
        assert got[sup] == slot_state.PROMOTED
        assert got[pair.pair] == slot_state.TWO_FILES


class TestASubstitutedPeriodsFiledSuppliesAreQueued:
    """#201 F3: criterion 14 - a supply waiting in a period that stands on an
    earlier one is in a queue entry, as the door lists it."""

    def test_both_are_in_the_queue(self, conn, minted, quiet):
        st, _ = parity.ex_substituted(conn, minted)
        b, _ = _filed(conn, st.period, _iso(_now() - timedelta(hours=1)))
        c, _ = _filed(conn, st.period, _iso(_now() - timedelta(minutes=30)))
        queued = {x.supply for x in filing_queue.awaiting(conn, COL) if x.period == st.period}
        assert {b, c} <= queued


class TestWhatSupersededItIsATime:
    """#201 F6: 'superseded by the supply that arrived <when>', said as a
    person reads a time - never the raw arrival key."""

    def test_named_by_its_receipt(self, conn, minted):
        slot, newer = parity.ov_superseded_under_promoted(conn, minted)
        (older,) = [e.state for e in filing_queue.supplies_in(conn, slot)
                    if e.state.state == filing_queue.SUPERSEDED]
        assert filing_queue.arrival_key_of(newer) not in older.reason
        assert "arrived" in older.reason and ("am" in older.reason or "pm" in older.reason)


class TestTheDoorsOtherBranches:
    """Criteria 8, 9 and 10 at the door itself (#201 coverage)."""

    def _drive(self, monkeypatch, slot, entries, pick):
        from contextlib import nullcontext

        from cli import filing_tui

        asked, decided = [], {}
        monkeypatch.setattr(filing_tui, "open_log", lambda: nullcontext(None))
        monkeypatch.setattr(filing_queue, "supplies_in", lambda c, s: entries)
        monkeypatch.setattr(filing_tui, "_offers", lambda s, scoped: scoped)

        def select(msg, choices, **_k):
            asked.append(list(choices))
            return pick(choices)
        monkeypatch.setattr(filing_tui.common, "select", select)
        monkeypatch.setattr(filing_tui, "_decide_on",
                            lambda s, offer: decided.update(state=s, offer=offer))
        monkeypatch.setattr(filing_tui, "_settle_on", lambda s: decided.update(settled=s))
        filing_tui._choose_a_supply(slot, filing_queue.operations_for(slot)[1])
        return asked, decided

    def _entry(self, state, supply, **kw):
        return filing_queue.FiledSupply(
            state=slot_state.SlotState(dataset_id=DS, period="2099-x", state=state,
                                       supply=supply, **kw), verdict="green")

    def test_the_period_itself_is_one_choice_beside_the_supplies(self, monkeypatch, capsys):
        slot = slot_state.SlotState(dataset_id=DS, period="2099-x",
                                    state=slot_state.AWAITING_DECISION, supply="cp-carers@1")
        entries = [self._entry(slot_state.AWAITING_DECISION, "cp-carers@1"),
                   self._entry(slot_state.AWAITING_DECISION, "cp-carers@2")]
        asked, decided = self._drive(monkeypatch, slot, entries,
                                     lambda cs: next(c for c in cs if c.startswith("The period")))
        assert sum(c.startswith("The period itself") for c in asked[0]) == 1
        assert set(decided["offer"]) == {fd.SUBSTITUTE, fd.INHERIT}

    def test_an_open_pair_is_the_only_choice_and_says_so(self, monkeypatch, capsys):
        slot = slot_state.SlotState(dataset_id=DS, period="2099-x", state=slot_state.TWO_FILES,
                                    supply="cp-carers@p", files=("a.csv", "b.csv"))
        entries = [self._entry(slot_state.TWO_FILES, "cp-carers@p", files=("a.csv", "b.csv")),
                   self._entry(slot_state.AWAITING_DECISION, "cp-carers@2")]
        asked, decided = self._drive(monkeypatch, slot, entries, lambda cs: cs[0])
        assert len(asked[0]) == 1 and "a.csv and b.csv" in asked[0][0]
        assert "until the pair is settled" in capsys.readouterr().out
        assert decided["state"].state == slot_state.TWO_FILES
        assert decided["offer"] == (fd.CHOOSE_FILE,)

    def test_the_log_unreachable_at_the_list_lists_nothing(self, monkeypatch, capsys):
        from cli import filing_tui

        def unreachable():
            raise filing_queue.LogUnreachable("the log is down")
        monkeypatch.setattr(filing_tui, "open_log", unreachable)
        listed = []
        monkeypatch.setattr(filing_tui.common, "select",
                            lambda *a, **k: listed.append(a) or None)
        slot = slot_state.SlotState(dataset_id=DS, period="2099-x",
                                    state=slot_state.AWAITING_DECISION, supply="cp-carers@1")
        filing_tui._choose_a_supply(slot, ())
        assert "the log is down" in capsys.readouterr().out
        assert listed == []

    def test_bringing_back_a_chosen_version_carries_no_count(self, monkeypatch):
        """#201 F7: the person already chose the version, so the offer is not
        labelled with how many versions the period holds."""
        from contextlib import nullcontext

        from cli import filing_tui

        monkeypatch.setattr(filing_tui, "open_log", lambda: nullcontext(None))
        monkeypatch.setattr(filing_queue, "superseded_to_bring_back",
                            lambda c, s: [{"supply": "a"}, {"supply": "b"}])
        shown = []
        monkeypatch.setattr(filing_tui.common, "select",
                            lambda msg, choices, **k: shown.extend(choices) or None)
        state = slot_state.SlotState(dataset_id=DS, period="2099-x",
                                     state=filing_queue.SUPERSEDED, supply="cp-carers@a")
        filing_tui._decide_on(state, offer=(fd.UN_SUPERSEDE,))
        assert shown and not any("earlier version" in c for c in shown)
