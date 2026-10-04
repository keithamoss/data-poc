"""A supply is filed only to the one slot open at its receipt instant
(REQ-PIPE-131, amending REQ-PIPE-062).

THE RULE: a slot is OPEN from its claim-opening instant until the next
CALENDAR period's claim-opening instant. A supply goes to the slot open
when it was received - to fill it if it is unfilled, as a resupply of it
if a promoted supply already fills it - and is held for a person where
no slot is open. Never forward, and since this change never backward.

THESE DRIVE REAL SEQUENCES, not single calls, where the property is a
sequence property: a cascade is invisible day to day, so a test of one
call's return value would pass against a rule that destroys the next
year of filings.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qa_tools.common import assignment
from qa_tools.common.schedule import Period
from qa_tools.common.slots import Slot

PERTH = timezone(timedelta(hours=8))


def _slot(day: int, hour: int = 12, grace_minutes: int = 60,
           window_hours: int = 6, month: int = 6) -> Slot:
    """One daily slot due at `hour` on 2026-06-`day`, not yet closed."""
    due = datetime(2026, month, day, hour, 0, tzinfo=PERTH)
    return Slot(dataset_id="d", period=Period(name=f"{day:02d}", date=due.date()),
                 due_at=due, grace=timedelta(minutes=grace_minutes),
                 claim_opens_at=due - timedelta(hours=window_hours))


def _chain(slots: list[Slot], last_closes: datetime | None = None) -> list[Slot]:
    """Close each slot when the next one's claim window opens, as
    slots_for_dataset() does for a dataset in every calendar period."""
    from dataclasses import replace
    out = []
    for i, slot in enumerate(slots):
        closes = slots[i + 1].claim_opens_at if i + 1 < len(slots) else last_closes
        out.append(replace(slot, closes_at=closes))
    return out


def _days(*days: int, hour: int = 12) -> list[Slot]:
    return _chain([_slot(d, hour=hour) for d in days])


def _at(day: int, hour: int, minute: int = 0, month: int = 6) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=PERTH)


class TestItFilesToTheOpenSlot:
    """Criteria 6 and 7 - early, on time or late, the open slot."""

    def test_early_on_time_and_late_all_go_to_the_open_slot(self):
        slots = _days(1, 2, 3)
        for at in (_at(1, 7), _at(1, 12), _at(1, 15), _at(2, 5, 59)):
            got = assignment.assign("d", "s", at, slots, frozenset())
            assert got.slot == "01" and got.branch == assignment.OPEN_UNFILLED, at

    def test_the_open_slot_changes_the_instant_the_next_window_opens(self):
        slots = _days(1, 2, 3)
        # The 2nd's window opens 06:00 on the 2nd: from then the 1st is closed.
        got = assignment.assign("d", "s", _at(2, 6), slots, frozenset())
        assert got.slot == "02" and got.branch == assignment.OPEN_UNFILLED

    def test_a_filled_open_slot_takes_a_resupply(self):
        slots = _days(1, 2)
        got = assignment.assign("d", "s", _at(1, 13), slots, frozenset({"01"}))
        assert got.branch == assignment.RESUPPLY and got.slot == "01"
        assert got.resupply_of == "01" and got.is_resupply


class TestItNeverFilesBackward:
    """Criterion 9 - the defect this requirement exists to fix."""

    def test_a_late_file_with_an_older_slot_unfilled_goes_to_the_open_one(self):
        """THE SHAPE FOUND 2026-10-04: the 1st was never filled, the 2nd's
        file arrives late on the 2nd. The old rule filed it BACKWARD into
        the 1st (oldest-claimable-unfilled)."""
        slots = _days(1, 2, 3)
        got = assignment.assign("d", "s", _at(2, 20), slots, frozenset())
        assert got.slot == "02", "filed backward into a closed slot"

    def test_a_resupply_of_a_filled_open_slot_is_not_pushed_into_an_older_gap(self):
        slots = _days(1, 2, 3)
        got = assignment.assign("d", "s", _at(2, 20), slots, frozenset({"02"}))
        assert got.slot == "02" and got.branch == assignment.RESUPPLY

    def test_the_22_00_monday_example(self):
        """Keith's worked consequence: Monday's daily file arriving after
        Tuesday's claim window opened is filed as TUESDAY's, and Monday
        closes with no supply."""
        slots = _days(1, 2, 3, hour=22)   # Tuesday's window opens 16:00 Tuesday
        got = assignment.assign("d", "monday-late", _at(2, 17), slots, frozenset())
        assert got.slot == "02" and got.branch == assignment.OPEN_UNFILLED

    def test_a_feed_running_behind_fills_the_current_period(self):
        """REVERSAL of REQ-PIPE-063 criterion 3: a feed more than one
        window behind fills the open period; the skipped ones close."""
        slots = _days(1, 2, 3, 4, 5, hour=22)
        filled: set[str] = set()
        landed = {}
        for day in (3, 4, 5):
            got = assignment.assign("d", f"s{day}", _at(day, 21), slots, frozenset(filled))
            landed[day] = got.slot
            filled.add(got.slot)
        assert landed == {3: "03", 4: "04", 5: "05"}


class TestItNeverClaimsForward:
    """REQ-PIPE-062 criterion 5, unchanged and absolute."""

    def test_a_slot_whose_window_has_not_opened_is_never_chosen(self):
        slots = _days(1, 2, 3)
        got = assignment.assign("d", "s", _at(1, 13), slots, frozenset({"01"}))
        assert got.slot == "01", "the only alternative was the 2nd, which is forward"
        assert "02" not in got.considered


class TestItHoldsWhereNothingIsOpen:
    """Criterion 10 - before the first window, and in a period the
    dataset does not participate in."""

    def test_before_the_first_claim_window_it_is_held(self):
        slots = _days(10, 11)
        got = assignment.assign("d", "s", _at(1, 9), slots, frozenset())
        assert got.slot is None and got.branch == assignment.HELD and got.is_held
        assert got.unavailable and "not opened" in got.unavailable[0][1]

    def test_in_a_gap_the_dataset_does_not_participate_in_it_is_held(self):
        """Case Workers' February slot closes when MAY's claim window
        opens, not August's - an arrival between is held."""
        from dataclasses import replace
        feb = replace(_slot(1, month=2), period=Period(name="2026-Q1", date=_at(1, 12, month=2).date()))
        aug = replace(_slot(1, month=8), period=Period(name="2026-Q3", date=_at(1, 12, month=8).date()))
        may_opens = datetime(2026, 5, 1, 6, 0, tzinfo=PERTH)
        slots = [replace(feb, closes_at=may_opens), aug]
        got = assignment.assign("d", "s", datetime(2026, 6, 15, 9, 0, tzinfo=PERTH),
                                slots, frozenset())
        assert got.slot is None and got.branch == assignment.HELD
        reasons = dict(got.unavailable)
        assert "closed" in reasons[feb.name] and "not opened" in reasons[aug.name]
        assert "not filed forward or backward" in got.describe()

    def test_a_held_supply_is_never_filed_into_a_filled_closed_slot(self):
        feb = _slot(1, month=2)
        from dataclasses import replace
        slots = [replace(feb, closes_at=datetime(2026, 5, 1, tzinfo=PERTH))]
        got = assignment.assign("d", "s", datetime(2026, 6, 1, tzinfo=PERTH),
                                slots, frozenset({feb.name}))
        assert got.branch == assignment.HELD and got.slot is None


class TestTheRecordSaysWhy:
    """REQ-PIPE-062 criterion 9, with the smaller vocabulary."""

    def test_the_vocabulary_is_exactly_three_branches(self):
        assert {assignment.OPEN_UNFILLED, assignment.RESUPPLY, assignment.HELD} == {
            "open-slot-unfilled", "resupply-of-open-slot", "held-no-open-slot"}
        for gone in ("ON_TIME", "OLDEST_CLAIMABLE", "UNASSIGNABLE"):
            assert not hasattr(assignment, gone), f"{gone} is a retired branch"

    def test_there_is_no_ambiguity_left_to_mark(self):
        """REQ-PIPE-065 criteria 1-2 are retired, not replaced: a file can
        never fit two open periods."""
        record = assignment.assign("d", "s", _at(2, 20), _days(1, 2, 3),
                                   frozenset()).as_record()
        assert "ambiguous" not in record and "ambiguity" not in record

    def test_it_records_the_slot_it_considered(self):
        got = assignment.assign("d", "s", _at(1, 13), _days(1, 2), frozenset({"01"}))
        assert got.considered == ("01",)
        assert got.resupply_of == "01" and "resupply_of" not in got.as_record()


class TestTheRetiredRulesAreGone:
    """Every reader of the retired rules is removed, not left as a
    second rule (NFR 4)."""

    def test_the_retired_helpers_no_longer_exist(self):
        from qa_tools.common import slots
        for name in ("closed_by_monotonic_filling", "oldest_claimable_unfilled",
                     "most_recently_filled"):
            assert not hasattr(assignment, name), name
        for name in ("next_unfilled_claimable", "is_claimable"):
            assert not hasattr(slots, name), name


class TestItReadsNoData:
    """REQ-PIPE-062 criterion 12 - config and promotion state alone."""

    def test_assignment_takes_no_supply_contents_at_all(self):
        import inspect
        assert list(inspect.signature(assignment.assign).parameters) == [
            "dataset_id", "supply_id", "at", "slots", "filled"]

    def test_the_module_never_touches_the_warehouse(self):
        import inspect
        source = inspect.getsource(assignment)
        for banned in ("duckdb", "supply_db", "read_csv", "pandas"):
            assert banned not in source, f"assignment reads {banned}"


class TestItIsDeterministic:
    def test_the_same_inputs_give_the_same_filing_every_time(self):
        slots = _days(1, 2, 3, 4, 5)
        answers = {assignment.assign("d", "s", _at(3, 13), slots,
                                      frozenset({"01", "02"})).as_record()["slot"]
                    for _ in range(25)}
        assert answers == {"03"}


class TestItDoesNotScanEverySlot:
    """Criterion 11 and NFR 1: a bisection per arrival."""

    def test_finding_the_open_slot_reads_only_log_n_slots(self):
        """Counted, not grepped: the first version asserted the word
        "bisect" appeared in a docstring, and a linear walk passed it
        (delivery-critic, overnight sprint 3b)."""
        reads = []

        class Counting(list):
            def __getitem__(self, i):
                reads.append(i)
                return super().__getitem__(i)

            def __iter__(self):
                raise AssertionError("the whole slot sequence was walked")

        base = _at(1, 12)
        slots = Counting(_chain([
            Slot(dataset_id="d", period=Period(name=f"x{i}", date=base.date()),
                 due_at=base + timedelta(days=i), grace=timedelta(minutes=60),
                 claim_opens_at=base + timedelta(days=i) - timedelta(hours=6))
            for i in range(4096)]))
        for at in (base + timedelta(days=2000, hours=1), base - timedelta(days=1)):
            reads.clear()
            assignment.assign("d", "s", at, slots, frozenset())
            assert len(reads) <= 40, f"{len(reads)} slot reads for one arrival"

    def test_it_is_unaffected_by_thousands_of_slots(self):
        import time
        few = _days(*range(1, 29))
        base = _at(1, 12)
        many = _chain([_slot(d) for d in range(1, 29)] + [
            Slot(dataset_id="d", period=Period(name=f"x{i}", date=base.date()),
                  due_at=base + timedelta(days=30 + i), grace=timedelta(minutes=60),
                  claim_opens_at=base + timedelta(days=30 + i) - timedelta(hours=6))
            for i in range(4000)])

        def elapsed(sequence):
            start = time.perf_counter()
            for _ in range(200):
                assignment.assign("d", "s", _at(14, 12), sequence, frozenset())
            return time.perf_counter() - start

        assert elapsed(many) < elapsed(few) * 8 + 0.5


class TestTheScenarioRegisterUnderTheOpenSlotRule:
    """REQ-PIPE-131 criterion 15: the register's slot-assignment
    scenarios, as rewritten in plans/supply-model.md, asserted against
    the real rule. Each states its config, because the answer depends
    on it."""

    def test_ts_5_a_missed_slot_does_not_absorb_a_later_resupply(self):
        """Daily, due 22:00, 6-hour window. Tuesday missed; Wednesday
        promoted; a 23:00 Wednesday arrival is a resupply of WEDNESDAY -
        Tuesday closed when Wednesday's window opened."""
        slots = _days(1, 2, 3, 4, hour=22)
        got = assignment.assign("d", "s", _at(3, 23), slots, frozenset({"01", "03"}))
        assert got.slot == "03" and got.branch == assignment.RESUPPLY

    def test_ts_5_evening_before_variant_fills_thursday(self):
        """Thursday's window already open at 23:00 Wednesday (an evening-
        before feed): Thursday is the open period, so it fills Thursday."""
        thursday = _slot(4, hour=22, window_hours=26)   # opens 20:00 Wednesday
        slots = _chain([_slot(1, hour=22), _slot(2, hour=22), _slot(3, hour=22), thursday])
        got = assignment.assign("d", "s", _at(3, 23), slots, frozenset({"03"}))
        assert got.slot == "04" and got.branch == assignment.OPEN_UNFILLED

    def test_ts_6a_genuine_lateness_fills_its_own_slot(self):
        slots = _days(1, 2, hour=22)          # Tuesday's window opens 16:00 Tuesday
        got = assignment.assign("d", "s", _at(2, 3), slots, frozenset())
        assert got.slot == "01"

    def test_ts_6b_a_one_day_lag_stays_on_its_own_days(self):
        slots = _days(1, 2, 3, 4, hour=22)
        filled: set[str] = set()
        for day, expected in ((2, "01"), (3, "02"), (4, "03")):
            got = assignment.assign("d", "s", _at(day, 3), slots, frozenset(filled))
            assert got.slot == expected
            filled.add(got.slot)

    def test_ts_6c_a_late_backfill_goes_to_the_open_period_not_held(self):
        """Tuesday never came; Wednesday filled. Tuesday's file turning up
        Thursday morning goes to the OPEN period - Wednesday, filled, so a
        resupply of it - for a person to re-file. Never backward, never
        held merely for being late."""
        slots = _days(1, 2, 3, 4, hour=22)
        got = assignment.assign("d", "tuesdays", _at(4, 3), slots, frozenset({"01", "03"}))
        assert got.slot == "03" and got.branch == assignment.RESUPPLY

    def test_ts_7_no_open_period_is_held(self):
        slots = _days(5, 6)
        got = assignment.assign("d", "s", _at(1, 12), slots, frozenset())
        assert got.is_held and got.slot is None

    def test_ts_10_evening_before_both_variants_fill_tuesday(self):
        """Tuesday due 22:00 MONDAY, 4-hour window - so Tuesday opens
        18:00 Monday, and Monday closes then. A 22:00 Monday arrival fills
        Tuesday whether or not Monday was filled."""
        tuesday = Slot(dataset_id="d", period=Period(name="02", date=_at(2, 0).date()),
                       due_at=_at(1, 22), grace=timedelta(minutes=60),
                       claim_opens_at=_at(1, 18))
        monday = Slot(dataset_id="d", period=Period(name="01", date=_at(1, 0).date()),
                      due_at=_at(1, 22) - timedelta(days=1), grace=timedelta(minutes=60),
                      claim_opens_at=_at(1, 18) - timedelta(days=1))
        slots = _chain([monday, tuesday])
        for filled in (frozenset({"01"}), frozenset()):
            got = assignment.assign("d", "s", _at(1, 22), slots, filled)
            assert got.slot == "02" and got.branch == assignment.OPEN_UNFILLED, filled

    def test_ts_33_a_partial_dataset_is_held_and_its_siblings_are_not(self):
        """Case workers (February and August) between May's window and
        August's: held. A sibling owing every quarter: filed to its open
        period."""
        from dataclasses import replace
        feb = replace(_slot(1, month=2), period=Period(name="Q1", date=_at(1, 12, month=2).date()))
        may = replace(_slot(1, month=5), period=Period(name="Q2", date=_at(1, 12, month=5).date()))
        aug = replace(_slot(1, month=8), period=Period(name="Q3", date=_at(1, 12, month=8).date()))
        partial = [replace(feb, closes_at=may.claim_opens_at), aug]
        every = _chain([feb, may, aug])
        june = datetime(2026, 6, 15, 9, 0, tzinfo=PERTH)
        assert assignment.assign("case-workers", "s", june, partial, frozenset()).is_held
        sibling = assignment.assign("clients", "s", june, every, frozenset())
        assert sibling.slot == "Q2" and not sibling.is_held


class TestAHoldsReasonIsWrittenForAPerson:
    """The reason is STORED (a hold is a record) and shown verbatim in the
    queue, so it must not carry a raw instant (REQ-DASH-071) - found by
    the display-standard e2e test on the first bootstrap under
    REQ-PIPE-131, which rendered '2023-04-17T09:00:00+08:00'."""

    def test_no_raw_instant_in_any_reason(self):
        import re
        got = assignment.assign("d", "s", _at(3, 9), [
            _slot(1, hour=22).__class__(**{**vars(_slot(1, hour=22)),
                                           "closes_at": _slot(2, hour=22).claim_opens_at}),
            _slot(5, hour=22)], frozenset({"01"}))
        text = got.describe() + " ".join(why for _, why in got.unavailable)
        assert not re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", text), text
