"""When nothing is confidently claimable, hold it for a human
(REQ-PIPE-064).

The thing under test is a REFUSAL, which is easy to assert vacuously -
a function that always returned "held" would pass a careless test. So
the reachable scenario is driven end to end through the real rule, and
each refusal is paired with a case that must NOT be held.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qa_tools.common import assignment, supply_holds
from qa_tools.common.schedule import Period
from qa_tools.common.slots import Slot

PERTH = timezone(timedelta(hours=8))


def _slot(day: int, hour: int = 22, closes: datetime | None = None) -> Slot:
    due = datetime(2026, 6, day, hour, 0, tzinfo=PERTH)
    return Slot(dataset_id="d", period=Period(name=f"{day:02d}", date=due.date()),
                 due_at=due, grace=timedelta(minutes=60),
                 claim_opens_at=due - timedelta(hours=6), closes_at=closes)


def _daily(*days: int) -> list[Slot]:
    """Every day owed, each closing as the next opens."""
    out = []
    for i, d in enumerate(days):
        nxt = _slot(days[i + 1]).claim_opens_at if i + 1 < len(days) else None
        out.append(_slot(d, closes=nxt))
    return out


def _at(day: int, hour: int) -> datetime:
    return datetime(2026, 6, day, hour, tzinfo=PERTH)


def _gap() -> list[Slot]:
    """A dataset owing the 1st and the 5th of a daily calendar: the 1st
    closes when the CALENDAR's 2nd opens (REQ-PIPE-131), and nothing is
    open again until the 5th's window."""
    return [_slot(1, closes=_slot(2).claim_opens_at), _slot(5, closes=_slot(6).claim_opens_at)]


def _held():
    """The reachable case since REQ-PIPE-131: a supply arriving in a
    calendar period its dataset does not participate in. (The old one -
    a backfill into a slot monotonic filling had closed - cannot happen
    any more: the backfill is filed to the open period.)"""
    return assignment.assign("d", "between", _at(3, 9), _gap(), frozenset({"01"}))


class TestItHoldsRatherThanDefaultingForward:
    """Criteria 1 and 2."""

    def test_the_reachable_case_is_held(self):
        assert _held().branch == assignment.HELD

    def test_a_held_supply_is_filed_nowhere(self):
        assert _held().slot is None

    def test_it_never_reaches_for_a_slot_whose_window_has_not_opened(self):
        """Criterion 2 - "under any fallback, default or recovery
        path". Defaulting into a future slot is the forward cascade
        arriving by the recovery path instead of by the rule."""
        decided = _held()
        future = {name for name, why in decided.unavailable if "has not opened" in why}
        assert future, "the scenario must actually involve a future slot, or this proves nothing"
        assert decided.slot not in future

    def test_an_ordinary_arrival_is_not_held(self):
        """The control: if everything were held, the tests above would
        pass against a rule that does nothing but refuse."""
        ordinary = assignment.assign("d", "s", _at(2, 22), _daily(1, 2, 3, 4, 5),
                                     frozenset({"01"}))
        assert ordinary.branch == assignment.OPEN_UNFILLED and ordinary.slot == "02"

    def test_before_the_first_window_it_is_held_too(self):
        """The other reachable case (REQ-PIPE-131 criterion 10)."""
        early = assignment.assign("d", "s", _at(1, 1), _daily(1, 2), frozenset())
        assert early.branch == assignment.HELD and early.slot is None


class TestItSaysWhy:
    """Criterion 4, and it is the whole deliverable of a hold: the
    resolution is a person assigning the supply, which they cannot do
    without knowing what was ruled out and why."""

    def test_it_names_the_slots_it_considered_and_why_each_was_unavailable(self):
        decided = _held()
        assert decided.unavailable, "a hold that says only 'no slot' is not actionable"
        for name, why in decided.unavailable:
            assert name and why, f"{name!r} has no reason given"

    def test_the_reasons_distinguish_filled_closed_and_not_yet_open(self):
        reasons = dict(_held().unavailable)
        assert "filled by a promoted supply" in reasons["01"] and "closed" in reasons["01"]
        assert "has not opened" in reasons["05"]
        unfilled = dict(assignment.assign("d", "s", _at(3, 9), _gap(), frozenset()).unavailable)
        assert "filled" not in unfilled["01"] and "closed" in unfilled["01"]

    def test_the_description_is_readable_and_says_what_happens_next(self):
        spoken = _held().describe()
        assert "could not be placed" in spoken
        assert "stays staged" in spoken and "assigns it" in spoken

    def test_it_does_not_list_every_slot_a_feed_ever_had(self):
        """Listing hundreds would bury the three that matter - the same
        reasoning that keeps holds aggregated."""
        slots = [_slot(1, closes=_slot(2).claim_opens_at)] + _daily(*range(20, 29))
        decided = assignment.assign("d", "between", _at(3, 9), slots, frozenset())
        assert [name for name, _ in decided.unavailable] == ["01", "20"]


class TestHoldsAggregate:
    """Criterion 8, and the non-functional constraint behind it: at ~30
    datasets a banner per held supply is thirty banners, which is how
    people learn to ignore a whole class."""

    def test_many_holds_come_back_as_one_thing(self):
        decisions = [_held(), _held(), _held()]
        found = supply_holds.holds_in(decisions)
        assert found.total == 3
        assert found.summary().count("held") == 1, (
            "one line for the class, never one per supply")

    def test_the_summary_names_the_datasets_rather_than_a_bare_count(self):
        a = assignment.Assignment(dataset_id="cp-clients", supply_id="s1", slot=None,
                                   branch=assignment.HELD, considered=("02",))
        b = assignment.Assignment(dataset_id="cp-carers", supply_id="s2", slot=None,
                                   branch=assignment.HELD, considered=("02",))
        found = supply_holds.holds_in([a, b])
        assert found.datasets == ("cp-carers", "cp-clients")
        assert "cp-clients" in found.summary()

    def test_nothing_held_says_so_in_words(self):
        found = supply_holds.holds_in([])
        assert found.total == 0 and not found.needs_action
        assert "No supply" in found.summary()

    def test_a_hold_is_an_event_needing_action(self):
        """Criterion 5 - distinguished from an informational one, which
        is the difference between a queue somebody drains and a line in
        a log."""
        assert supply_holds.holds_in([_held()]).needs_action is True

    def test_only_holds_are_counted(self):
        ordinary = assignment.assign("d", "s", _at(2, 22), _daily(1, 2, 3), frozenset({"01"}))
        assert supply_holds.holds_in([ordinary, _held()]).total == 1


class TestHoldingChangesNothingElse:
    """Criteria 6 and 7."""

    def test_the_slots_are_left_exactly_as_they_were(self):
        slots = _gap()
        filled = frozenset({"01"})
        before = list(slots)
        assignment.assign("d", "between", _at(3, 9), slots, filled)
        assert slots == before and filled == frozenset({"01"})

    def test_another_dataset_is_unaffected_by_a_hold(self):
        """Criterion 7 - one held supply must not stop the other 29
        datasets, which is the blast-radius rule this batch applies
        everywhere."""
        held = _held()
        other = assignment.assign("other", "s", _at(2, 22), _daily(1, 2, 3), frozenset({"01"}))
        assert held.branch == assignment.HELD
        assert other.branch == assignment.OPEN_UNFILLED and other.slot == "02"


class TestItIsNoLongerADeadEnd:
    """REQ-PIPE-078 is what ended it, and this class is the previous
    one inverted rather than deleted.

    It used to assert that nothing here pretended to resolve a hold and
    that the module SAID SO - because a hold nobody can clear is
    indistinguishable from a bug, and the requirement of the day
    required the honesty rather than the capability. Both are now
    wrong, and keeping the pair the right way round is what stops a
    future reader taking the old assertion for a rule.
    """

    def test_a_hold_can_be_resolved(self):
        assert hasattr(supply_holds, "resolve")
        assert hasattr(supply_holds, "resolve_for_supply")

    def test_the_module_no_longer_claims_to_be_a_dead_end(self):
        assert "sprint 12" not in supply_holds.__doc__.lower()

    def test_it_says_where_a_hold_now_lives(self):
        """The store is the deliverable, so the module names it."""
        assert "qa.hold" in supply_holds.__doc__
