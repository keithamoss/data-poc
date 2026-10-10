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

COMPUTED AS FILING COMPUTES IT (criterion 2) - through the one
slot-instants function filing uses (slots.slot_instants, REQ-PIPE-113
criterion 10), over the same period sequence (slots._calendar_periods,
which honours a dataset's own authored dates), so this check and filing
can never disagree about where a boundary falls. Across a change of
calendar or participation version the two neighbours are compared like
any others (criterion 3), because each period's inputs are resolved on
its own date.

CONFIGURATION ONLY: contract/calendar.yaml and the asset file, never the
database.
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


def overlaps_for(dataset_id: str, until: date | None = None,
                 agreement=None) -> list[Overlap]:
    """Every overlapping pair of consecutive periods for one dataset."""
    from qa_tools.common import slots

    try:
        calendar = schedule.calendar_for_dataset(dataset_id, agreement)
    except schedule.NoCalendarAgreed:
        return []
    bound = (until or horizon()) if calendar.current.is_cadence_rule else until
    if bound is not None:
        # PLUS THE LARGEST days_before (REQ-PIPE-113 criterion 11).
        bound += timedelta(days=slots.max_days_before(dataset_id, agreement))
    # The CALENDAR's periods, not only the ones this dataset owes - see
    # the module docstring - or the dataset's own dates where it states
    # them, exactly the sequence its slots close against.
    if bound is None:
        periods = slots._calendar_periods(dataset_id, None, agreement)
    else:
        periods = [p for p in slots._calendar_periods(dataset_id, bound, agreement)
                   if p.date <= bound]

    found: list[Overlap] = []
    previous = None
    for period in periods:
        instants = slots.slot_instants(dataset_id, period.date, agreement)
        if previous is not None:
            earlier, earlier_instants = previous
            on_time_until = earlier_instants.due_at + earlier_instants.grace
            if not instants.claim_opens_at > on_time_until:
                found.append(Overlap(dataset_id=dataset_id, earlier=earlier.name,
                                     later=period.name, on_time_until=on_time_until,
                                     later_claim_opens=instants.claim_opens_at))
        previous = (period, instants)
    return found


def overlaps(until: date | None = None, agreement=None) -> list[Overlap]:
    """Every overlap for every dataset - all of them, never the first
    alone (criterion 5)."""
    out: list[Overlap] = []
    for dataset in hierarchy.all_datasets():
        out.extend(overlaps_for(dataset.dataset_id, until=until, agreement=agreement))
    return out
