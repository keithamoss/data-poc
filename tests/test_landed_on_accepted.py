"""An uncertain assignment says it is uncertain, and an arrival into a
filled slot is reported (REQ-PIPE-065).

Two rules with one thing in common: both exist so a case the rule
cannot resolve reaches a person while it is still cheap to correct.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from qa_tools.common import assignment, landed_on_accepted
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


class TestAnUncertainAssignmentSaysSo:
    """Criteria 1 and 2. Unbuilt, this leaves ambiguous assignments
    presented as CERTAIN - a false-confidence problem rather than a
    missing nicety, which is why it was raised from should to must."""

    def test_it_is_marked_when_an_earlier_slot_is_also_unfilled(self):
        """The 2nd was filled, so the 1st is closed by monotonic
        filling and still unfilled. A supply then arrives just after
        midnight on the 4th - too late for the 3rd's grace, so it takes
        the 3rd as the oldest CLAIMABLE unfilled slot, while the 1st
        sits there unfilled and unclaimable. Late for the 3rd, or a
        backfill for the 1st? No rule can tell.
        """
        slots = [_slot(d) for d in range(1, 5)]
        got = assignment.assign("d", "s", _at(4, 0, 30), slots, frozenset({"02"}))
        assert got.branch == assignment.OLDEST_CLAIMABLE and got.slot == "03"
        assert got.ambiguous is True
        assert got.ambiguity and "also unfilled" in got.ambiguity

    def test_it_is_not_marked_when_nothing_earlier_is_outstanding(self):
        """The control: if everything were marked ambiguous the flag
        would carry no information at all."""
        slots = [_slot(1), _slot(2)]
        got = assignment.assign("d", "s", _at(2, 3), slots, frozenset())
        assert got.branch == assignment.OLDEST_CLAIMABLE
        assert got.ambiguous is False and got.ambiguity is None

    def test_an_on_time_assignment_is_never_ambiguous(self):
        slots = [_slot(1), _slot(2), _slot(3)]
        got = assignment.assign("d", "s", _at(3, 22), slots, frozenset())
        assert got.branch == assignment.ON_TIME and got.ambiguous is False

    def test_it_defaults_backward_rather_than_refusing(self):
        """Decision 4 - late is commoner than early, so it files and
        flags rather than holding. Cheap to correct, because filing is
        mutable and the verdict recomputes."""
        slots = [_slot(d) for d in range(1, 5)]
        got = assignment.assign("d", "s", _at(4, 0, 30), slots, frozenset({"02"}))
        assert got.slot == "03", "it must still file, not refuse"
        assert got.branch != assignment.HELD

    def test_the_mark_survives_into_the_record(self):
        """The NFR: it must stay visible until somebody looks, not be
        cleared by the next run passing over it again."""
        slots = [_slot(d) for d in range(1, 5)]
        record = assignment.assign(
            "d", "s", _at(4, 0, 30), slots, frozenset({"02"})).as_record()
        assert record["ambiguous"] is True and record["ambiguity"]


class TestArrivingForAnAlreadyAcceptedSlot:
    """Criteria 3 and 6."""

    def test_it_is_reported_when_the_slot_was_promoted_into(self):
        got = landed_on_accepted.report(
            "d", "s", "01", _at(1, 20), {"01": _at(1, 16)})
        assert got is not None
        assert "already accepted" in got.describe()

    def test_it_names_when_the_existing_supply_was_accepted(self):
        got = landed_on_accepted.report(
            "d", "s", "01", _at(1, 20), {"01": _at(1, 16)})
        assert got.accepted_at == _at(1, 16)
        assert "4:00pm" in got.describe() or "16:00" in got.describe()

    def test_an_arrival_for_a_slot_never_filled_stays_silent(self):
        """Criterion 6 - a resupply after REJECTION is the expected
        repair path. Reporting it too would make the report
        wallpaper."""
        assert landed_on_accepted.report("d", "s", "01", _at(1, 20), {}) is None

    def test_another_slot_being_filled_does_not_trigger_it(self):
        assert landed_on_accepted.report(
            "d", "s", "02", _at(2, 20), {"01": _at(1, 16)}) is None


class TestProximityIsTheExplanationNotTheTrigger:
    """Criteria 4 and 5, and the reason the threshold this replaced was
    rejected: any 'within X of the window' number is arbitrary, and a
    case just outside it slips through in silence."""

    def test_it_reports_with_no_proximity_at_all(self):
        got = landed_on_accepted.report(
            "d", "s", "01", _at(1, 20), {"01": _at(1, 16)})
        assert got is not None, "the trigger is structural - it fires without proximity"
        assert got.near_window is None
        assert "may belong to" not in got.describe()

    def test_proximity_adds_a_sentence_rather_than_deciding_anything(self):
        got = landed_on_accepted.report(
            "d", "s", "01", _at(2, 15, 57), {"01": _at(1, 16)},
            next_window_opens=_at(2, 16), next_slot="02")
        assert got.near_window == "02"
        spoken = got.describe()
        assert "3 minute(s) before 02's window opened" in spoken
        assert "may belong to 02" in spoken

    def test_the_same_arrival_reports_either_way(self):
        """Same trigger, different diagnosis - which is the whole
        point of moving proximity out of the trigger."""
        without = landed_on_accepted.report("d", "s", "01", _at(2, 15, 57), {"01": _at(1, 16)})
        with_it = landed_on_accepted.report(
            "d", "s", "01", _at(2, 15, 57), {"01": _at(1, 16)},
            next_window_opens=_at(2, 16), next_slot="02")
        assert without is not None and with_it is not None
        assert len(with_it.describe()) > len(without.describe())

    def test_a_distant_arrival_gets_no_proximity_sentence(self):
        got = landed_on_accepted.report(
            "d", "s", "01", _at(1, 20), {"01": _at(1, 16)},
            next_window_opens=_at(2, 16), next_slot="02")
        assert got.near_window is None


class TestItNamesWhatYouCanDo:
    """Criterion 7 - a warning that does not say what the responses are
    is one somebody has to go and ask about."""

    def test_all_three_responses_are_named(self):
        spoken = landed_on_accepted.report(
            "d", "s", "01", _at(1, 20), {"01": _at(1, 16)}).describe()
        assert "correction" in spoken
        assert "re-file" in spoken
        assert "reject" in spoken and "duplicate" in spoken

    def test_there_are_exactly_three(self):
        assert len(landed_on_accepted.RESPONSES) == 3


class TestItNeverAutoPromotesOverAcceptedData:
    """Criterion 9, and it exists as a function rather than as prose
    because that is exactly how this rule went missing once already -
    an IOU against work that did not exist, appearing in the register
    only in the deferral itself."""

    def test_a_slot_already_promoted_into_may_not_auto_promote(self):
        assert landed_on_accepted.may_auto_promote("01", {"01": _at(1, 16)}) is False

    def test_an_empty_slot_may(self):
        assert landed_on_accepted.may_auto_promote("02", {"01": _at(1, 16)}) is True

    def test_it_does_not_depend_on_the_new_supplys_own_status(self):
        """"Whatever that supply's own status" - a green duplicate must
        not silently supersede accepted data either."""
        import inspect
        signature = inspect.signature(landed_on_accepted.may_auto_promote)
        assert list(signature.parameters) == ["slot", "promoted_slots"], (
            "if this took the supply's status it could be talked into promoting a "
            "green duplicate over data already accepted")
