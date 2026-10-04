"""A dataset's periods never overlap (REQ-PIPE-134).

The claim window of each period must open strictly AFTER the previous
period stops being on time - its due instant plus grace. If it did not,
a file arriving in the overlap is on time for one period and already
claimable by the next, and "which period is this for?" has two answers.
REQ-PIPE-131's rule - a file is filed only to the one open slot - assumes
the answer is always one, so this is checked from configuration, in CI,
before any file arrives to find out the hard way.

EVERY PERIOD OF THE DATASET'S CALENDAR, whether or not the dataset takes
part in it (criterion 1): a dataset not due in Q2 still has Q2's claim
window opening on it, because REQ-PIPE-131 closes Q1 when Q2's window
opens whether or not anything is owed for Q2.

COMPUTED AS FILING COMPUTES IT (criterion 2) - the same contract timing
(slots._contract_timing) and the same effective-dated claim window
(schedule.claim_window(on=the period's own date)) - so this check and
filing can never disagree about where a boundary falls. Across a change
of calendar version the two neighbours are compared like any others
(criterion 3), because each period's window is resolved on its own date.

CONFIGURATION ONLY: the schedule and the contracts, never the database.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from qa_tools.common import asset_time, hierarchy, schedule


@dataclass(frozen=True)
class Overlap:
    dataset_id: str
    earlier: str
    later: str
    on_time_until: datetime
    later_claim_opens: datetime

    @property
    def by(self) -> timedelta:
        """How far the later window reaches back over the earlier one;
        zero where it opens exactly as the earlier stops being on time,
        which is still an overlap - "strictly after" is the rule."""
        return self.on_time_until - self.later_claim_opens


def horizon(today: date | None = None) -> date:
    """How far a cadence-rule calendar is generated for this check.

    PROVISIONAL (overnight sprint 3): criterion 4 says "the horizon the
    runway warning uses", and the runway warning skips cadence-rule
    calendars entirely, so there is no such horizon to share. The end of
    next year is long enough to cross any calendar-version boundary
    authored today, and a cadence rule repeats, so a longer one adds
    periods without adding a way to fail.
    """
    today = today or asset_time.local_date(asset_time.now())
    return date(today.year + 1, 12, 31)


def overlaps_for(dataset_id: str, until: date | None = None) -> list[Overlap]:
    """Every overlapping pair of consecutive periods for one dataset."""
    from qa_tools.common import slots

    try:
        calendar = schedule.calendar_for_dataset(dataset_id)
    except schedule.NoCalendarAgreed:
        return []
    expected_time, grace_minutes, window_override = slots._contract_timing(dataset_id)
    grace = timedelta(minutes=grace_minutes)
    bound = (until or horizon()) if calendar.current.is_cadence_rule else until
    # The CALENDAR's periods, not only the ones this dataset owes - see
    # the module docstring. periods_for_calendar, unlike
    # periods_for_dataset, does not apply delivery_months.
    periods = schedule.periods_for_calendar(calendar.name, until=bound)

    found: list[Overlap] = []
    previous = None
    for period in periods:
        due = asset_time.wall_clock(period.date, expected_time)
        window = schedule.claim_window(dataset_id, window_override, on=period.date)
        opens = due - window
        if previous is not None:
            earlier, earlier_due = previous
            on_time_until = earlier_due + grace
            if not opens > on_time_until:
                found.append(Overlap(dataset_id=dataset_id, earlier=earlier.name,
                                     later=period.name, on_time_until=on_time_until,
                                     later_claim_opens=opens))
        previous = (period, due)
    return found


def overlaps(until: date | None = None) -> list[Overlap]:
    """Every overlap for every dataset - all of them, never the first
    alone (criterion 5)."""
    out: list[Overlap] = []
    for dataset in hierarchy.all_datasets():
        out.extend(overlaps_for(dataset.dataset_id, until=until))
    return out
