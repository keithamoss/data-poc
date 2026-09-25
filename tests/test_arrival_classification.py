"""Early, on time and late are measured against the slot the supply was
filed to (REQ-PIPE-066).

The two worked failures of the derivation this replaces are tested
directly, because both are plausible enough to be reinstated by
accident: a quarterly supply reading twelve weeks late for a quarter
filled months ago, and a 10pm daily arrival reading late against the
current day when it was meant for the next.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qa_tools.common import arrival_classification as classify_mod
from qa_tools.common.schedule import Period
from qa_tools.common.slots import Slot

PERTH = timezone(timedelta(hours=8))


def _slot(name: str, due: datetime, grace_hours: int = 1) -> Slot:
    return Slot(dataset_id="d", period=Period(name=name, date=due.date()),
                 due_at=due, grace=timedelta(hours=grace_hours),
                 claim_opens_at=due - timedelta(hours=6))


class TestItMeasuresAgainstTheAssignedSlot:
    """Criteria 1, 3, 4 and 5."""

    def test_before_the_due_instant_is_early(self):
        slot = _slot("Q3", datetime(2026, 8, 1, 12, tzinfo=PERTH))
        got = classify_mod.classify(datetime(2026, 7, 25, 9, tzinfo=PERTH), slot)
        assert got == classify_mod.EARLY

    def test_at_the_due_instant_is_on_time(self):
        slot = _slot("Q3", datetime(2026, 8, 1, 12, tzinfo=PERTH))
        got = classify_mod.classify(datetime(2026, 8, 1, 12, tzinfo=PERTH), slot)
        assert got == classify_mod.ON_TIME

    def test_within_the_slots_own_grace_is_on_time(self):
        slot = _slot("Q3", datetime(2026, 8, 1, 12, tzinfo=PERTH), grace_hours=8)
        got = classify_mod.classify(datetime(2026, 8, 1, 19, tzinfo=PERTH), slot)
        assert got == classify_mod.ON_TIME

    def test_past_the_grace_is_late(self):
        slot = _slot("Q3", datetime(2026, 8, 1, 12, tzinfo=PERTH), grace_hours=1)
        got = classify_mod.classify(datetime(2026, 8, 1, 14, tzinfo=PERTH), slot)
        assert got == classify_mod.LATE


class TestTheTwoFailuresItReplaces:
    """The derivation this removes looked backwards from the ARRIVAL
    DATE, so it could only ever find a slot that had already started."""

    def test_a_quarterly_supply_arriving_early_is_not_twelve_weeks_late(self):
        """Arriving 2026-07-25 for the 2026-08-01 anchor. The old
        derivation resolved that to the 2026-05-01 anchor and reported
        it late for a quarter filled months ago."""
        filed_to = _slot("2026-Q3", datetime(2026, 8, 1, 12, tzinfo=PERTH))
        got = classify_mod.classify(datetime(2026, 7, 25, 9, tzinfo=PERTH), filed_to)
        assert got == classify_mod.EARLY, (
            "measured against the slot it was FILED TO this is early, which is the "
            "whole point - the old answer was 'about twelve weeks late'")

    def test_a_late_evening_arrival_meant_for_the_next_day(self):
        """A 10pm arrival intended for the next day read LATE against
        the current one. Filed to tomorrow's slot, it is early."""
        tomorrow = _slot("02", datetime(2026, 6, 2, 12, tzinfo=PERTH))
        got = classify_mod.classify(datetime(2026, 6, 1, 22, tzinfo=PERTH), tomorrow)
        assert got == classify_mod.EARLY

    def test_the_same_arrival_filed_to_the_earlier_slot_is_late(self):
        """The control: the verdict follows the FILING, so the same
        instant classifies differently against a different slot. If it
        did not, the signature change would be doing nothing."""
        yesterday = _slot("01", datetime(2026, 6, 1, 12, tzinfo=PERTH))
        got = classify_mod.classify(datetime(2026, 6, 1, 22, tzinfo=PERTH), yesterday)
        assert got == classify_mod.LATE


class TestAnUnfiledSupply:
    """Criterion 8."""

    def test_it_is_reported_unfiled_rather_than_punctual(self):
        got = classify_mod.classify(datetime(2026, 6, 1, 22, tzinfo=PERTH), None)
        assert got == classify_mod.UNFILED

    def test_unfiled_is_not_one_of_the_three_verdicts(self):
        assert classify_mod.UNFILED not in (
            classify_mod.EARLY, classify_mod.ON_TIME, classify_mod.LATE), (
            "there is nothing to be punctual against, so saying on time or late here "
            "would be inventing a verdict out of an absence")

    def test_it_says_so_in_words(self):
        spoken = classify_mod.describe(classify_mod.UNFILED,
                                        datetime(2026, 6, 1, 22, tzinfo=PERTH), None)
        assert "no slot was assigned" in spoken


class TestEachTableIsClassifiedOnItsOwn:
    """Criterion 6 - one late table must not drag five punctual
    siblings down. It follows from slots being per-table."""

    def test_two_tables_in_one_delivery_get_their_own_verdicts(self):
        clients = _slot("01", datetime(2026, 6, 1, 12, tzinfo=PERTH), grace_hours=1)
        placements = _slot("01", datetime(2026, 6, 1, 18, tzinfo=PERTH), grace_hours=1)
        assert classify_mod.classify(
            datetime(2026, 6, 1, 9, tzinfo=PERTH), clients) == classify_mod.EARLY
        assert classify_mod.classify(
            datetime(2026, 6, 1, 20, tzinfo=PERTH), placements) == classify_mod.LATE

    def test_the_grace_used_is_the_slots_own(self):
        """Birth Registrations allows an hour and Child Protection
        eight - a shared grace would be one table's answer imposed on
        the rest."""
        at = datetime(2026, 6, 1, 17, tzinfo=PERTH)
        due = datetime(2026, 6, 1, 12, tzinfo=PERTH)
        assert classify_mod.classify(at, _slot("01", due, grace_hours=1)) == classify_mod.LATE
        assert classify_mod.classify(at, _slot("01", due, grace_hours=8)) == classify_mod.ON_TIME


class TestItNeverLooksAtTheArrivalDateToPickASlot:
    """Criterion 2, and the reason this is a signature change: deriving
    the period here a second time is what creates two implementations
    of one concept that can disagree."""

    def test_classification_takes_the_slot_and_nothing_that_could_imply_one(self):
        import inspect
        signature = inspect.signature(classify_mod.classify)
        assert list(signature.parameters) == ["arrived_at", "slot"]

    def test_the_module_does_not_reach_for_the_old_derivation(self):
        import inspect
        source = inspect.getsource(classify_mod)
        body = source[source.index("from __future__"):]
        assert "cycle_start" not in body and "classify_arrival(" not in body


class TestARejectedSupplyIsClassifiedToo:
    """Criterion 7 - "arrived three weeks late AND was bad" is exactly
    what belongs on the record for a supply that never got promoted."""

    def test_classification_cannot_see_whether_a_supply_was_promoted(self):
        import inspect
        source = inspect.getsource(classify_mod.classify)
        for banned in ("promoted", "rejected", "status"):
            assert banned not in source, (
                f"classification must not depend on {banned} - it happens at check time, "
                f"before a promotion decision that may never be taken")
