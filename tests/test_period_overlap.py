"""A dataset's periods never overlap (REQ-PIPE-134).

Configuration only, so these drive the real schedule and contracts and
change one input at a time - the claim window, the grace - to make an
overlap that today's configuration does not have.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from qa_tools.common import period_overlap, schedule, slots, validate_schedule


class TestTodaysConfiguration:
    def test_no_dataset_overlaps(self):
        """The drafting NFR's own claim, held as a test: all seven pass."""
        assert period_overlap.overlaps() == []

    def test_the_gate_passes(self):
        assert validate_schedule.validate() == []


class TestAnOverlapIsFound:
    @pytest.fixture
    def wide_window(self, monkeypatch):
        """A 100-day claim window on a quarterly calendar reaches back
        over the previous quarter's due date."""
        monkeypatch.setattr(schedule, "claim_window",
                            lambda dataset_id, override=None, on=None, agreement=None: timedelta(days=100))

    def test_every_pair_is_reported_not_the_first(self, wide_window):
        found = period_overlap.overlaps_for("cp-clients")
        assert len(found) > 1
        first = found[0]
        assert first.later_claim_opens <= first.on_time_until
        assert first.by > timedelta(0)

    def test_it_reports_every_dataset(self, wide_window):
        datasets = {o.dataset_id for o in period_overlap.overlaps()}
        assert {"cp-clients", "cp-carers", "birth-registrations"} <= datasets

    def test_the_gate_names_the_dataset_both_periods_and_the_size(self, wide_window):
        errors = validate_schedule.validate()
        assert errors, "an overlap must fail the configuration gate"
        e = next(e for e in errors if e.scope == "cp-clients")
        assert "overlap by" in e.problem and "claim window opens" in e.problem

    def test_touching_is_still_an_overlap(self, monkeypatch):
        """'Strictly after': a window opening at the very instant the
        earlier period stops being on time leaves one instant in both."""
        monkeypatch.setattr(slots, "_timing", lambda d, agreement=None: ("09:00", 0, None))
        monkeypatch.setattr(schedule, "claim_window",
                            lambda dataset_id, override=None, on=None, agreement=None: timedelta(days=1))
        found = period_overlap.overlaps_for("birth-registrations")
        assert found and all(o.by == timedelta(0) for o in found)


class TestEveryCalendarPeriodCounts:
    def test_a_period_the_dataset_does_not_take_part_in_is_still_checked(self, monkeypatch):
        """cp-case-workers is not due every quarter; the quarter it skips
        still opens a claim window on it (REQ-PIPE-131 closes the previous
        slot there), so the check walks the CALENDAR's periods."""
        calendar = schedule.calendar_for_dataset("cp-case-workers")
        owed = [p for p in schedule.periods_for_dataset("cp-case-workers") if p.expected]
        all_periods = schedule.periods_for_calendar(calendar.name)
        assert len(all_periods) > len(owed), "precondition: it skips some quarters"
        monkeypatch.setattr(schedule, "claim_window",
                            lambda dataset_id, override=None, on=None, agreement=None: timedelta(days=100))
        pairs = {(o.earlier, o.later) for o in period_overlap.overlaps_for("cp-case-workers")}
        assert len(pairs) == len(all_periods) - 1
