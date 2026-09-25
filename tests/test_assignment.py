"""A supply is assigned to a slot by rule, and the rule can never claim
forward (REQ-PIPE-062).

THESE DRIVE REAL SEQUENCES, not single calls, and that is the
requirement's own non-functional constraint rather than a preference.
Both cascades are invisible day to day - every day looks locally
plausible and nothing self-corrects - so a test asserting one call's
return value would pass against a rule that destroys the next year of
filings. Each cascade test runs a real run of arrivals over real slots
and asserts the WHOLE sequence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


from qa_tools.common import assignment
from qa_tools.common.schedule import Period
from qa_tools.common.slots import Slot

PERTH = timezone(timedelta(hours=8))


def _slot(day: int, hour: int = 12, grace_minutes: int = 60,
           window_hours: int = 6, month: int = 6) -> Slot:
    """One daily slot due at `hour` on 2026-06-`day`."""
    due = datetime(2026, month, day, hour, 0, tzinfo=PERTH)
    return Slot(dataset_id="d", period=Period(name=f"{day:02d}", date=due.date()),
                 due_at=due, grace=timedelta(minutes=grace_minutes),
                 claim_opens_at=due - timedelta(hours=window_hours))


def _at(day: int, hour: int, minute: int = 0, month: int = 6) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=PERTH)


class TestItNeverClaimsForward:
    """Criterion 5, which is absolute - "under any rule or any
    circumstance". An absolute rule with one exception is how forward
    claiming comes back."""

    def test_a_slot_whose_window_has_not_opened_cannot_be_claimed(self):
        slots = [_slot(1), _slot(2), _slot(3)]
        # 08:00 on the 1st: the 2nd's window opens at 06:00 on the 2nd.
        got = assignment.assign("d", "s1", _at(1, 8), slots, frozenset())
        assert got.slot == "01"
        assert "02" not in got.considered

    def test_not_even_when_every_open_slot_is_filled(self):
        slots = [_slot(1), _slot(2), _slot(3)]
        got = assignment.assign("d", "s1", _at(1, 13), slots, frozenset({"01"}))
        assert got.branch == assignment.RESUPPLY
        assert got.slot == "01", "the only alternative was to claim the 2nd, which is forward"

    def test_an_arrival_before_the_first_window_is_unassignable_not_forced(self):
        slots = [_slot(10), _slot(11)]
        got = assignment.assign("d", "s1", _at(1, 9), slots, frozenset())
        assert got.slot is None and got.branch == assignment.UNASSIGNABLE


class TestTheForwardCascade:
    """Decision 3, run as a real sequence.

    The rule that produces it - "oldest unfilled slot" - reads
    perfectly reasonable and would be re-proposed. Its cause is that it
    assumes every arrival fills a NEW obligation, and a resupply does
    not.
    """

    def test_a_third_file_on_monday_does_not_become_tuesdays_delivery(self):
        slots = [_slot(1), _slot(2), _slot(3), _slot(4)]

        # 14:00 arrives and is REJECTED, so Monday stays unfilled -
        # only a promotion fills a slot.
        first = assignment.assign("d", "s1", _at(1, 14), slots, frozenset())
        assert first.slot == "01"

        # 16:00 arrives, is promoted: Monday filled.
        second = assignment.assign("d", "s2", _at(1, 16), slots, frozenset())
        assert second.slot == "01"
        filled = frozenset({"01"})

        # 20:00, a third file. Under "oldest unfilled" this would take
        # TUESDAY and every later supply would be off by one for ever.
        third = assignment.assign("d", "s3", _at(1, 20), slots, filled)
        assert third.slot == "01", (
            "a Monday resupply filed as Tuesday starts a permanent off-by-one - every "
            "later supply takes the next slot and nothing self-corrects")
        assert third.branch == assignment.RESUPPLY

        # And the sequence stays put: Tuesday's real supply is Tuesday's.
        fourth = assignment.assign("d", "s4", _at(2, 12), slots, filled)
        assert fourth.slot == "02" and fourth.branch == assignment.ON_TIME


class TestTheBackwardCascade:
    """Decision 4, run as a real sequence.

    Introduced by the fix for the forward one, and the reason
    on-time-wins exists. A permanent lag where every day is locally
    plausible is exactly what no single-call test would catch.
    """

    def test_a_punctual_supply_after_an_outage_fills_todays_slot(self):
        slots = [_slot(d, hour=22) for d in range(1, 6)]
        filled = frozenset({"01"})

        # The supplier's system is down on the 2nd and 3rd. The next
        # supply arrives ON TIME at 22:00 on the 4th.
        got = assignment.assign("d", "s", _at(4, 22), slots, filled)
        assert got.slot == "04" and got.branch == assignment.ON_TIME, (
            "filing this as the 2nd starts a permanent two-day lag: the next supply "
            "takes the 3rd, the next the 4th, and it never catches up")

        # The missed days stay missed, which is TRUE and is the point.
        assert "02" not in (got.slot or "") and "03" not in (got.slot or "")

    def test_the_whole_run_after_an_outage_stays_on_its_own_day(self):
        """The cascade only shows across a SEQUENCE - each day alone
        looks fine."""
        slots = [_slot(d, hour=22) for d in range(1, 8)]
        filled = {"01"}
        landed = {}
        for day in range(4, 8):          # the 2nd and 3rd were missed
            got = assignment.assign("d", f"s{day}", _at(day, 22), slots, frozenset(filled))
            landed[day] = got.slot
            filled.add(got.slot)
        assert landed == {4: "04", 5: "05", 6: "06", 7: "07"}, (
            f"a two-day lag cascaded through the whole run: {landed}")

    def test_a_late_supply_still_files_late_rather_than_as_today(self):
        """Lateness has to keep working, or the fix for the cascade
        just breaks the thing it was protecting."""
        slots = [_slot(d, hour=22) for d in range(1, 6)]
        # Monday's supply arrives 03:00 Tuesday - NOT on time for
        # Tuesday, whose window opens 16:00 Tuesday.
        got = assignment.assign("d", "s", _at(2, 3), slots, frozenset())
        assert got.slot == "01" and got.branch == assignment.OLDEST_CLAIMABLE


class TestOnlyAPromotionFillsASlot:
    """Decision 10, load-bearing rather than definitional."""

    def test_a_rejected_supply_leaves_the_slot_unfilled(self):
        slots = [_slot(1), _slot(2)]
        # Nothing promoted, so nothing filled - a staged or rejected
        # supply must not count.
        got = assignment.assign("d", "s2", _at(1, 16), slots, frozenset())
        assert got.slot == "01", (
            "if a rejected supply filled the slot, this resupply would be pushed to "
            "Tuesday - the forward cascade, reintroduced by the definition of 'filled'")


class TestTheRecordSaysWhy:
    """Criterion 9. Recomputing later is NOT equivalent - the slot
    state it was decided against has moved on."""

    def test_it_records_the_branch_and_the_slots_it_considered(self):
        slots = [_slot(1), _slot(2)]
        got = assignment.assign("d", "s", _at(1, 13), slots, frozenset({"01"}))
        assert got.branch == assignment.RESUPPLY
        assert got.considered and all(isinstance(n, str) for n in got.considered)
        assert got.as_record()["resupply_of"] == "01"

    def test_every_branch_is_named_rather_than_left_blank(self):
        slots = [_slot(1), _slot(2), _slot(3)]
        cases = [
            (_at(1, 12), frozenset(), assignment.ON_TIME),
            (_at(2, 3), frozenset(), assignment.OLDEST_CLAIMABLE),
            (_at(1, 13), frozenset({"01"}), assignment.RESUPPLY),
        ]
        for at, filled, expected in cases:
            assert assignment.assign("d", "s", at, slots, filled).branch == expected


class TestItReadsNoData:
    """Criterion 12 - config and promotion state alone."""

    def test_assignment_takes_no_supply_contents_at_all(self):
        import inspect
        signature = inspect.signature(assignment.assign)
        assert list(signature.parameters) == [
            "dataset_id", "supply_id", "at", "slots", "filled"], (
            "nothing about the supply's CONTENT may reach this - deriving the period "
            "from the data is circular, since a resupply exists precisely because the "
            "first attempt was wrong, possibly wrong in its dates")

    def test_the_module_never_touches_the_warehouse(self):
        import inspect
        source = inspect.getsource(assignment)
        for banned in ("duckdb", "supply_db", "read_csv", "pandas"):
            assert banned not in source, f"assignment reads {banned}"


class TestItIsDeterministic:
    """The seeded regenerate-and-diff check stops meaning anything
    otherwise."""

    def test_the_same_inputs_give_the_same_filing_every_time(self):
        slots = [_slot(d) for d in range(1, 6)]
        answers = {assignment.assign("d", "s", _at(3, 13), slots,
                                      frozenset({"01", "02"})).as_record()["slot"]
                    for _ in range(25)}
        assert len(answers) == 1


class TestItDoesNotScanEverySlot:
    """The cost constraint: at a daily feed with years of history the
    sequence is thousands of slots, and the rule only ever needs the
    current one and the oldest claimable unfilled one."""

    def test_finding_the_current_slot_is_a_bisection(self):
        import inspect
        assert "bisect" in inspect.getsource(assignment.current_slot), (
            "a linear scan per arrival is what this constraint forbids")

    def test_it_is_unaffected_by_thousands_of_slots(self):
        import time
        few = [_slot(d, month=6) for d in range(1, 29)]
        many = few + [
            Slot(dataset_id="d", period=Period(name=f"x{i}", date=_at(1, 12).date()),
                  due_at=_at(1, 12) + timedelta(days=30 + i),
                  grace=timedelta(minutes=60),
                  claim_opens_at=_at(1, 12) + timedelta(days=30 + i) - timedelta(hours=6))
            for i in range(4000)]

        def elapsed(sequence):
            start = time.perf_counter()
            for _ in range(200):
                assignment.assign("d", "s", _at(14, 12), sequence, frozenset())
            return time.perf_counter() - start

        # Generous: the claim is "does not scale with the sequence",
        # not a specific speed on a shared sandbox.
        assert elapsed(many) < elapsed(few) * 8 + 0.5


class TestAKnownImperfectionStaysContained:
    """TS-3 - LABELLED DELIBERATELY, and this label is part of the
    requirement rather than a comment.

    THESE ASSERT THAT A KNOWN IMPERFECTION STAYS CONTAINED, NOT THAT
    THE SYSTEM GETS THE RIGHT ANSWER. Do not "fix" them.

    The imperfection: a supply arriving in the window of the NEXT slot,
    for the previous one, is misfiled at the boundary - and it is wrong
    twice, because the punctual supplier reads as a very late resupply
    AND the slot they actually filled goes overdue as a phantom missing
    delivery. Generous or contiguous claim windows were rejected as the
    cure because they reintroduce the forward cascade exactly; no window
    sizing gets both. The trade is taken in favour of never claiming
    forward, and the DATA half is fine - it sits in the previous slot,
    present and checked.
    """

    def test_a_supply_arriving_before_its_own_window_reads_as_a_resupply(self):
        """The misfile TIGHT windows buy, and it is wrong twice.

        Tuesday is due 12:00 with a six-hour window, so it opens at
        06:00 Tuesday. The supplier sends Tuesday's file at 05:00 -
        genuinely early, genuinely Tuesday's. It cannot claim Tuesday,
        because Tuesday's window has not opened and claiming forward is
        absolute. Monday is filled, so there is no claimable unfilled
        slot either, and it files as a RESUPPLY OF MONDAY.
        """
        slots = [_slot(1, hour=12), _slot(2, hour=12)]
        got = assignment.assign("d", "s", _at(2, 5), slots, frozenset({"01"}))
        assert got.branch == assignment.RESUPPLY and got.slot == "01", (
            "EXPECTED IMPERFECTION, do not 'fix': a punctual supplier reads as a late "
            "resupply of the previous slot. Widening the window to catch this "
            "reintroduces the forward cascade exactly - no sizing gets both, and the "
            "trade is taken in favour of never claiming forward.")

    def test_and_the_slot_it_actually_filled_goes_overdue(self):
        """The SECOND wrong thing, which is the half that is easy to
        miss: Tuesday is left unfilled, so it reads as a phantom
        missing delivery for data that arrived early, one slot over.
        The DATA half is fine - it sits in Monday, present and
        checked."""
        slots = [_slot(1, hour=12), _slot(2, hour=12)]
        got = assignment.assign("d", "s", _at(2, 5), slots, frozenset({"01"}))
        assert got.slot != "02", "EXPECTED IMPERFECTION - Tuesday is left to go overdue"

    def test_the_imperfection_does_not_propagate(self):
        """Contained is the whole claim: one supply, one slot, and the
        next arrival is unaffected. A cascade would be a different
        thing entirely."""
        slots = [_slot(1, hour=12), _slot(2, hour=12), _slot(3, hour=12)]
        assignment.assign("d", "s", _at(2, 5), slots, frozenset({"01"}))
        after = assignment.assign("d", "s2", _at(2, 12), slots, frozenset({"01"}))
        assert after.slot == "02" and after.branch == assignment.ON_TIME
        later = assignment.assign("d", "s3", _at(3, 12), slots, frozenset({"01", "02"}))
        assert later.slot == "03" and later.branch == assignment.ON_TIME
