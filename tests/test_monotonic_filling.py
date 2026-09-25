"""A slot stops being claimable once a later one is filled
(REQ-PIPE-063).

THE FAILURE THIS PREVENTS IS RATED WORSE THAN A CASCADE in the source
thread, because it does not merely misfile a supply - it MANUFACTURES A
DELIVERY THAT NEVER HAPPENED, erasing a service failure using another
day's data.

A WARNING THE REQUIREMENT ITSELF GIVES, and it shaped these tests: a
test asserting that a slot stayed UNFILLED is easy to write as a no-op
that passes against any implementation, including one with no rule at
all. So each test here either drives the real scenario and asserts
WHERE the supply went, or asserts the negative against a control that
proves the assertion can fail.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qa_tools.common import assignment
from qa_tools.common.schedule import Period
from qa_tools.common.slots import Slot

PERTH = timezone(timedelta(hours=8))


def _slot(day: int, hour: int = 22) -> Slot:
    due = datetime(2026, 6, day, hour, 0, tzinfo=PERTH)
    return Slot(dataset_id="d", period=Period(name=f"{day:02d}", date=due.date()),
                 due_at=due, grace=timedelta(minutes=60),
                 claim_opens_at=due - timedelta(hours=6))


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, day, hour, minute, tzinfo=PERTH)


class TestTheScenarioItExistsFor:
    """Decision 1, traced end to end.

    Tuesday missed entirely. Wednesday arrives on time and is promoted.
    A Wednesday RESUPPLY then arrives at 23:00.
    """

    def test_a_wednesday_resupply_does_not_fill_the_missed_tuesday(self):
        slots = [_slot(1), _slot(2), _slot(3), _slot(4)]
        filled = frozenset({"01", "03"})       # Tuesday (02) was missed

        got = assignment.assign("d", "resupply", _at(3, 23), slots, filled)
        assert got.slot == "03", (
            "a Wednesday resupply filed against the missed Tuesday records a delivery "
            "that never happened - a service failure erased with another day's data")
        assert got.branch == assignment.RESUPPLY

    def test_the_control_proves_that_assertion_can_fail(self):
        """WITHOUT monotonic filling the same arrival takes Tuesday.

        The requirement warns that a stayed-unfilled assertion is easy
        to write as a no-op, so this drives the rule's own helper with
        an empty closed set and shows the bad answer appearing.
        """
        slots = [_slot(1), _slot(2), _slot(3), _slot(4)]
        filled = frozenset({"01", "03"})

        without = assignment.oldest_claimable_unfilled(
            slots, _at(3, 23), filled, closed=frozenset())
        assert without is not None and without.name == "02", (
            "if this does not pick Tuesday, the scenario is not being reproduced and "
            "the test above proves nothing")

        with_rule = assignment.oldest_claimable_unfilled(
            slots, _at(3, 23), filled,
            closed=assignment.closed_by_monotonic_filling(slots, filled))
        assert with_rule is None

    def test_the_missed_slot_is_left_unfilled_and_so_reads_as_unmet(self):
        """Criterion 4. Asserted against the real filings of a whole
        run rather than as a bare negative."""
        slots = [_slot(1), _slot(2), _slot(3), _slot(4)]
        filled = {"01", "03"}
        landed = []
        for hour in (23,):
            got = assignment.assign("d", f"s{hour}", _at(3, hour), slots, frozenset(filled))
            landed.append(got.slot)
        assert "02" not in landed


class TestGenuineLatenessStillWorks:
    """Criteria 2 and 3 - the rule must not buy safety by breaking
    lateness."""

    def test_a_late_supply_fills_its_own_slot_when_nothing_later_is_filled(self):
        slots = [_slot(1), _slot(2), _slot(3)]
        # Monday's supply lands 03:00 Tuesday. Nothing later is filled.
        got = assignment.assign("d", "s", _at(2, 3), slots, frozenset())
        assert got.slot == "01" and got.branch == assignment.OLDEST_CLAIMABLE

    def test_consecutive_late_slots_each_fill_in_sequence(self):
        """Criterion 3 - a feed running behind must read as running
        behind, not as a run of missing slots."""
        slots = [_slot(d) for d in range(1, 6)]
        filled: set[str] = set()
        landed = []
        # Four supplies, each arriving a day late, one after another.
        for day in range(2, 6):
            got = assignment.assign("d", f"s{day}", _at(day, 3), slots, frozenset(filled))
            landed.append(got.slot)
            filled.add(got.slot)
        assert landed == ["01", "02", "03", "04"], (
            f"a feed running one day behind must fill each slot in turn, got {landed}")

    def test_nothing_is_closed_while_nothing_is_filled(self):
        slots = [_slot(d) for d in range(1, 5)]
        assert assignment.closed_by_monotonic_filling(slots, frozenset()) == frozenset()


class TestWhatTheRuleCloses:
    def test_only_slots_before_the_last_filled_one_close(self):
        slots = [_slot(d) for d in range(1, 6)]
        closed = assignment.closed_by_monotonic_filling(slots, frozenset({"02", "04"}))
        assert closed == frozenset({"01", "03"}), (
            "everything before the newest filled slot and still unfilled is closed; "
            "later slots stay open, or a feed could never catch up")

    def test_a_filled_slot_is_not_also_closed(self):
        slots = [_slot(d) for d in range(1, 4)]
        closed = assignment.closed_by_monotonic_filling(slots, frozenset({"01", "03"}))
        assert "01" not in closed and "03" not in closed


class TestItHoldsRatherThanGuessing:
    """Criterion 6, and the named LIMIT of the whole rule.

    Once a delivery is skipped AND a later one has landed, a genuine
    backfill of the older slot cannot be placed by any rule. Keith: "I
    think we can't design around that." Defaulting it into a future
    slot is the forward cascade again, and defaulting it into the
    closed slot is the erasure this requirement exists to stop - so it
    goes to a person.
    """

    def test_an_arrival_that_can_only_go_in_a_closed_slot_is_held(self):
        """The 4th was filled - promoted out of order, or a later
        backfill landed first - so the 1st, 2nd and 3rd are all closed.
        A supply then arrives on the 3rd. Its only candidate is a
        closed slot, the 5th's window has not opened, and the filled
        slot is NOT the one we are in, so there is no confident
        resupply either. Nothing is confidently claimable.
        """
        slots = [_slot(d) for d in range(1, 6)]
        got = assignment.assign("d", "backfill", _at(3, 9), slots, frozenset({"04"}))
        assert got.branch == assignment.HELD
        assert got.slot is None, "a held supply must not be filed anywhere by the rule"

    def test_being_held_names_what_it_could_not_be_placed_in(self):
        slots = [_slot(d) for d in range(1, 6)]
        got = assignment.assign("d", "backfill", _at(3, 9), slots, frozenset({"04"}))
        assert got.considered, "a hold a person cannot act on is the same as no hold"

    def test_it_does_not_quietly_take_the_closed_slot_instead(self):
        """The control: the closed slot is exactly where a rule without
        this would have put it."""
        slots = [_slot(d) for d in range(1, 6)]
        filled = frozenset({"04"})
        without = assignment.oldest_claimable_unfilled(
            slots, _at(3, 9), filled, closed=frozenset())
        assert without is not None and without.name == "01", (
            "without monotonic filling this arrival takes the oldest missed slot - "
            "which is the erasure the whole requirement exists to stop")
        got = assignment.assign("d", "backfill", _at(3, 9), slots, filled)
        assert got.slot != "01"

    def test_a_confident_resupply_is_not_held(self):
        """The distinction that keeps the hold rare: the Wednesday
        23:00 arrival IS confidently a Wednesday resupply, because
        Wednesday is both filled and the slot we are in."""
        slots = [_slot(1), _slot(2), _slot(3), _slot(4)]
        got = assignment.assign("d", "s", _at(3, 23), slots, frozenset({"01", "03"}))
        assert got.branch == assignment.RESUPPLY and got.slot == "03"


class TestClaimabilityIsAskedNeverRecorded:
    """The non-functional constraint: the answer changes as later slots
    fill, so a stored flag is wrong from the moment the next promotion
    lands."""

    def test_the_same_slot_closes_only_once_a_later_one_fills(self):
        slots = [_slot(1), _slot(2), _slot(3)]
        assert "02" not in assignment.closed_by_monotonic_filling(slots, frozenset({"01"}))
        assert "02" in assignment.closed_by_monotonic_filling(slots, frozenset({"01", "03"}))

    def test_nothing_persists_a_closed_flag(self):
        import inspect
        source = inspect.getsource(assignment.closed_by_monotonic_filling)
        for banned in ("write_text", "json.dump", "open("):
            assert banned not in source, (
                "claimability is asked, never recorded - a stored flag is wrong from "
                "the moment the next promotion lands")
