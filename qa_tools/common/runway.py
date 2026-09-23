"""Runway and the exhausted schedule (REQ-PIPE-053).

THE FAILURE THIS EXISTS TO PREVENT is not a schedule running out. It is
a schedule running out QUIETLY. An authored date list that reaches its
last date stops producing periods; no periods means no slots; no slots
means nothing is ever owed, so nothing is ever overdue - and the
dashboard goes green and stays green, which looks exactly like a feed
with nothing wrong. That is the same false-green shape as the staleness
bug this project has already been bitten by, and it is the whole reason
authored dates are only safe WITH this module.

TWO STATES, DELIBERATELY DIFFERENT IN KIND:

  LOW RUNWAY is a WARNING and never fails anything, permanently. A
  non-fatal warning that fails a build gets disabled, and then the real
  one is not there when it matters.

  AN EXHAUSTED SCHEDULE is a HARD FAILURE, scoped to the one dataset
  (Keith, 2026-09-21, choosing this over reading the state as unknown).
  It cannot be ignored: once the warning has fired and nobody has typed
  next year's dates, that dataset stops being processed.

RUNWAY IS MEASURED IN SLOTS, NEVER IN ELAPSED TIME, and that is the
whole point of the unit rather than a detail. Three months of runway on
a quarterly calendar is ONE slot, which is already too late to act on.
Months mislead precisely where the cost is highest.

RUNWAY IS A PROPERTY OF THE CALENDAR, not of the dataset. Thirty
datasets on one authored calendar run out on the same day, so thirty
warnings would be one fact repeated thirty times - which is exactly
what the aggregation this requirement asks for exists to prevent. The
TRIGGER is still per-dataset, because a dataset participating in two
months of four runs out of slots twice as fast as its siblings.

NOTHING HERE TOUCHES DATA. Every answer comes from configuration, which
is what lets the dashboard show an exhausted schedule even though the
run that would have reported it never happened - the case where a
dashboard that stopped updating is indistinguishable from one where
nothing changed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from qa_tools.common import hierarchy, schedule

# How few future slots left before we say so. A year of quarterly
# supplies, which is the smallest window in which "ask the agency for
# next year's dates" is a calm request rather than an emergency.
#
# A calendar may override it. There is no per-DATASET override on
# purpose: the thing running out is the calendar's date list, and
# thirty datasets disagreeing about when to mention it would be thirty
# opinions about one fact.
DEFAULT_WARNING_SLOTS = 4


@dataclass(frozen=True)
class CalendarRunway:
    """How much life one calendar has left, as at a date.

    `remaining` is the FEWEST future slots any dataset on this calendar
    has, not the calendar's own period count - a dataset taking two
    months of four runs out twice as fast, and it is the first one to
    run out that decides when this is worth saying.
    """

    calendar_name: str
    remaining: int
    last_period: str | None
    last_date: date | None
    dataset_count: int
    threshold: int

    @property
    def is_low(self) -> bool:
        return self.remaining < self.threshold

    @property
    def is_exhausted(self) -> bool:
        return self.remaining == 0


def _authored_calendars() -> list[schedule.Calendar]:
    """Only authored-date calendars can run out.

    A cadence rule generates periods for ever, so warning about its
    runway would be warning about something that cannot happen - and a
    warning that can never be acted on is how a reader learns to skip
    the whole class.
    """
    return [c for c in schedule.calendars() if not c.current.is_cadence_rule]


def _datasets_on(calendar_name: str) -> list[str]:
    return [d.dataset_id for d in hierarchy.all_datasets()
            if schedule.calendar_for_dataset(d.dataset_id).name == calendar_name]


def _threshold(calendar: schedule.Calendar) -> int:
    return getattr(calendar, "runway_warning_slots", None) or DEFAULT_WARNING_SLOTS


def calendar_runway(calendar_name: str, as_of: date) -> CalendarRunway:
    """One calendar's remaining runway, as at `as_of`.

    `as_of` rather than today's date, because the dashboard asks this
    question against whatever date a viewer has selected - a schedule
    is not exhausted when you are looking at a date its calendar
    covers, and saying otherwise would make the notice wrong in the one
    place somebody is most likely to check it.
    """
    calendar = schedule.calendar(calendar_name)
    periods = schedule.periods_for_calendar(calendar_name)
    future_counts = []
    for dataset_id in _datasets_on(calendar_name):
        owed = [p for p in schedule.periods_for_dataset(dataset_id) if p.expected]
        future_counts.append(len([p for p in owed if p.date > as_of]))

    return CalendarRunway(
        calendar_name=calendar_name,
        remaining=min(future_counts) if future_counts else 0,
        last_period=periods[-1].name if periods else None,
        last_date=periods[-1].date if periods else None,
        dataset_count=len(future_counts),
        threshold=_threshold(calendar),
    )


def low_runway(as_of: date) -> list[CalendarRunway]:
    """Every authored calendar running low, worst first."""
    found = [calendar_runway(c.name, as_of) for c in _authored_calendars()]
    return sorted([r for r in found if r.is_low], key=lambda r: r.remaining)


def exhausted_datasets(as_of: date) -> dict[str, str]:
    """{dataset_id: the calendar that ran out}, for datasets with no
    slot left at all as at `as_of`.

    Per DATASET rather than per calendar, because this is the half that
    stops work: the failure is scoped to the affected dataset so one
    neglected annual dataset cannot halt the other twenty-nine. At
    thirty datasets, a check that stops everything is a check somebody
    disables wholesale.
    """
    out: dict[str, str] = {}
    for dataset in hierarchy.all_datasets():
        calendar = schedule.calendar_for_dataset(dataset.dataset_id)
        if calendar.current.is_cadence_rule:
            continue
        owed = [p for p in schedule.periods_for_dataset(dataset.dataset_id) if p.expected]
        if not [p for p in owed if p.date > as_of]:
            out[dataset.dataset_id] = calendar.name
    return out


def warning_lines(as_of: date) -> list[str]:
    """The low-runway warning, as text, ONCE PER CALENDAR.

    Every line says it is not failing the build, in words rather than
    by colour - a reader who cannot tell a warning from a failure treats
    both as noise, and the one that mattered goes with it.

    Names the calendar, its last authored period and HOW MANY datasets
    name it, without listing them. Thirty dataset names is the fact
    repeated thirty times, which is what this aggregation exists to
    stop.
    """
    lines = []
    for runway in low_runway(as_of):
        datasets = (f"{runway.dataset_count} dataset names it"
                    if runway.dataset_count == 1
                    else f"{runway.dataset_count} datasets name it")
        if runway.is_exhausted:
            lines.append(
                f"WARNING (not failing the build): calendar {runway.calendar_name!r} has NO "
                f"future dates left - its last is {runway.last_period} on {runway.last_date}, "
                f"and {datasets}. Author the next year's dates in "
                f"contract/data-asset.yaml; `mothman schedule candidate-dates` proposes them. "
                f"Until then those datasets cannot be processed.")
        else:
            lines.append(
                f"WARNING (not failing the build): calendar {runway.calendar_name!r} has only "
                f"{runway.remaining} future supply slot(s) left - its last authored period is "
                f"{runway.last_period} on {runway.last_date}, and {datasets}. Author the next "
                f"year's dates in contract/data-asset.yaml; `mothman schedule candidate-dates` "
                f"proposes them.")
    return lines


def summary(as_of: date) -> str | None:
    """One line for several calendars, or None when all is well.

    Criterion: when more than one calendar is low, say HOW MANY rather
    than warning once per dataset.
    """
    low = low_runway(as_of)
    if not low:
        return None
    exhausted = exhausted_datasets(as_of)
    part = (f"{len(low)} calendar(s) low on runway"
            if len(low) > 1 else f"calendar {low[0].calendar_name!r} is low on runway")
    if exhausted:
        return (f"{part}; {len(exhausted)} dataset(s) have no remaining slots and cannot be "
                f"processed until dates are added.")
    return f"{part}."
