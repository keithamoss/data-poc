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
    #: The dataset whose count IS `remaining`, and that dataset's own
    #: last period - not the calendar's. Carried as fields rather than
    #: only written into the warning text, because the dashboard
    #: renders its own message and should not parse one back out
    #: (post-build-review #22).
    driving_dataset: str | None = None
    driving_last_period: str | None = None
    driving_last_date: date | None = None

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
    # A DATASET WITH NO CALENDAR IS ON NO CALENDAR (REQ-PIPE-106
    # criterion 1). It cannot run out of runway, and warning that it has
    # none would be telling somebody to author dates for a schedule
    # nobody has agreed - or, for a one-off extraction, will ever agree.
    return [d.dataset_id for d in hierarchy.all_datasets()
            if _calendar_name(d.dataset_id) == calendar_name]


def _calendar_name(dataset_id: str) -> str | None:
    try:
        return schedule.calendar_for_dataset(dataset_id).name
    except schedule.NoCalendarAgreed:
        return None


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
    # (future count, dataset_id, that dataset's own last owed period).
    # The dataset is carried alongside its count because `remaining` is
    # a minimum, and a minimum with no owner is a number nobody can
    # check against the file (post-build-review #22).
    per_dataset: list[tuple[int, str, object]] = []
    turning_off: list[tuple[int, str, object]] = []
    for dataset_id in _datasets_on(calendar_name):
        if off_for_good(dataset_id, as_of):
            # REQ-PIPE-179 criterion 25: a dataset turned off for good owes
            # no more dates, so it never drives the minimum. A temporary
            # gap needs nothing here - its periods are not owed, so only
            # those it owes once back on are counted.
            continue
        owed = [p for p in schedule.periods_for_dataset(dataset_id) if p.expected]
        # COUNTED IN SLOTS STILL TO COME DUE, BY THE ROUND EACH IS DUE ON
        # (REQ-PIPE-321 criterion 8; post-build-review #142 item 5): at
        # files_go_to_period N a dataset reads N slots shorter than its
        # calendar's last date suggests.
        entry = (len([p for p in owed if p.round_date > as_of]), dataset_id,
                 owed[-1] if owed else None)
        # AN AUTHORED FOR-GOOD TURN-OFF STOPS DRIVING THE MINIMUM too
        # (post-build-review #199 F7, Keith 2026-10-15): it has the fewest
        # dates left by construction and would hide a sibling that is also
        # short. It drives only where every dataset counted is turning off,
        # and its line then says no more dates are needed.
        (turning_off if _turning_off_for_good(dataset_id, as_of) else per_dataset).append(entry)
    counted = len(per_dataset) + len(turning_off)
    per_dataset = per_dataset or turning_off

    # min() on the count alone, with the dataset id as a tie-break, so
    # the same configuration always names the same dataset rather than
    # whichever one the hierarchy happened to list first.
    driver = min(per_dataset, key=lambda x: (x[0], x[1])) if per_dataset else None
    driving_last = driver[2] if driver else None

    return CalendarRunway(
        calendar_name=calendar_name,
        remaining=driver[0] if driver else 0,
        last_period=periods[-1].name if periods else None,
        last_date=periods[-1].date if periods else None,
        dataset_count=counted,
        threshold=_threshold(calendar),
        driving_dataset=driver[1] if driver else None,
        driving_last_period=driving_last.name if driving_last else None,
        driving_last_date=driving_last.date if driving_last else None,
    )


def low_runway(as_of: date) -> list[CalendarRunway]:
    """Every authored calendar running low, worst first."""
    found = [calendar_runway(c.name, as_of) for c in _authored_calendars()]
    # A CALENDAR NO DATASET IS COUNTED ON (every one off for good) has no
    # runway to warn about - not "NO future dates left" (#190 D1).
    return sorted([r for r in found if r.is_low and r.dataset_count],
                  key=lambda r: r.remaining)


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
        try:
            calendar = schedule.calendar_for_dataset(dataset.dataset_id)
        except schedule.NoCalendarAgreed:
            continue            # owes nothing, so cannot be exhausted
        if calendar.current.is_cadence_rule or off_for_good(dataset.dataset_id, as_of):
            continue    # a turn-off for good is not an exhausted schedule (criterion 25)
        try:
            ends = schedule_ends_on(dataset.dataset_id)
        except (ValueError, KeyError, FileNotFoundError):
            # NO SLOTS CAN BE BUILT (no contract timing) - the filing rule
            # then holds everything anyway, so the last owed date is the
            # honest answer left. Blast radius: never raised for one dataset.
            owed = [p for p in schedule.periods_for_dataset(dataset.dataset_id) if p.expected]
            ends = owed[-1].date if owed else None
        if ends is not None and as_of >= ends:
            out[dataset.dataset_id] = calendar.name
    return out


def off_for_good(dataset_id: str, on: date, agreement=None) -> bool:
    """Whether the dataset is turned off FOR GOOD on `on` (REQ-PIPE-179
    criteria 5 and 25) - a turn-off with no end that has STARTED. One still
    ahead does not count (post-build-review #190 D1, PROVISIONAL, J3): until
    its effective_to the dataset owes, so a schedule ending before then is
    exhausted like any other."""
    from qa_tools.common import agreement as agreement_mod

    agr = schedule._agreement(agreement)
    if not agr.ever_turned_off(dataset_id):
        return False
    standing = agr.standing_on(dataset_id, on)
    return standing.state == agreement_mod.TURNED_OFF and standing.turned_off.until is None


def off_gaps(dataset_id: str, agreement=None) -> list[dict]:
    """[{from, until, effectiveTo, authoredOn}] - each turned-off gap's first
    day (the day after its effective_to) and the day it ends, None for good,
    with its effective_to and the date it was authored - for the page, which
    judges them on the date on show (REQ-DASH-180 criteria 17 and 20, and
    REQ-PIPE-053 criterion 19 as it amends)."""
    from datetime import timedelta

    from qa_tools.common import turned_off

    agr = schedule._agreement(agreement)
    if not agr.ever_turned_off(dataset_id):
        return []
    return [{"from": (date.fromisoformat(t["effectiveTo"]) + timedelta(days=1)).isoformat(),
             "until": t["until"], "effectiveTo": t["effectiveTo"],
             # WHEN IT WAS WRITTEN DOWN, so the low-runway line can say no more
             # dates are needed once it is (REQ-DASH-180 criterion 17 as
             # amended by Keith, 2026-10-15).
             "authoredOn": t["authoredOn"]} for t in turned_off.timeline(dataset_id, agr)]


def schedule_ends_on(dataset_id: str) -> date | None:
    """The asset-local date this dataset's schedule ends: when its LAST slot
    closes, the instant from which the pipeline holds a supply rather than
    files it (REQ-DASH-155 criterion 6; Keith, 2026-10-06). None where the
    last slot never closes - a calendar of one date - or there is none.

    NOT the last period's own date, which is what this used to read: the
    last slot stays open about one more period after it, so the page said
    "cannot be processed" while supplies were still being filed normally."""
    from qa_tools.common import asset_time
    from qa_tools.common import slots as slots_mod

    found = slots_mod.slots_for_dataset(dataset_id)
    if not found or found[-1].closes_at is None:
        return None
    return asset_time.localise(found[-1].closes_at).date()


def _turning_off_for_good(dataset_id: str | None, as_of: date) -> str | None:
    """The effective_to of this dataset's for-good turn-off where it is
    authored on or before `as_of` and not yet started, else None."""
    if not dataset_id:
        return None
    for gap in off_gaps(dataset_id):
        if (gap["until"] is None and gap.get("authoredOn")
                and gap["authoredOn"] <= as_of.isoformat() < gap["from"]):
            return gap["effectiveTo"]
    return None


def warning_lines(as_of: date) -> list[str]:
    """The low-runway warning, as text, ONCE PER CALENDAR.

    Every line says it is not failing the build, in words rather than
    by colour - a reader who cannot tell a warning from a failure treats
    both as noise, and the one that mattered goes with it.

    Names the calendar, HOW MANY datasets name it - without listing
    them, since thirty dataset names is one fact repeated thirty times,
    which is what this aggregation exists to stop - and, for the low
    case, the ONE dataset the number actually belongs to.

    That last part is not a detail: `remaining` is a minimum across
    datasets, so naming the calendar and stopping made the figure
    unreproducible from the config (post-build-review #22). The
    calendar's own horizon is still given when it differs, as a
    separate clause rather than folded into the same sentence.
    """
    lines = []
    for runway in low_runway(as_of):
        datasets = (f"{runway.dataset_count} dataset names this calendar"
                    if runway.dataset_count == 1
                    else f"{runway.dataset_count} datasets name this calendar")
        if runway.is_exhausted:
            # NOT "WARNING", and that is the whole point of this branch
            # (plans/post-build-review.md #21, Keith's call 2026-09-24).
            # This module's own docstring calls the two states
            # "deliberately different in kind"; until this change they
            # opened with the same word, so the severest one read as the
            # mild one. The promise that nothing is failing the build
            # stays - it is the label that was wrong, not the
            # behaviour.
            lines.append(
                f"EXHAUSTED (not failing the build, yet): calendar {runway.calendar_name!r} has NO "
                f"future dates left - its last is {runway.last_period} on {runway.last_date}, "
                f"and {datasets}. Author the next year's dates in "
                f"contract/calendar.yaml; `mothman schedule candidate-dates` proposes them. "
                f"Until then those datasets cannot be processed.")
        else:
            # THE NUMBER AND THE PERIOD BELONG TO ONE DATASET, and the
            # sentence now says which. It used to attribute the minimum
            # to the calendar and pair it with the CALENDAR's last
            # period, so a reader who opened the config and counted
            # found a different number and no way to reconcile them
            # (post-build-review #22). The dashboard half of
            # REQ-PIPE-053 had already made this fix - "a dataset's
            # message names its OWN last period, not its calendar's" -
            # and the CLI kept the old shape.
            # TURNING OFF FOR GOOD, AND AUTHORED (REQ-DASH-180 criterion 17 as
            # amended by Keith, 2026-10-15 - 'the gate's warning likewise'):
            # still warned, but no dates are asked for that it will not owe.
            off = _turning_off_for_good(runway.driving_dataset, as_of)
            if off:
                lines.append(
                    f"WARNING (not failing the build): calendar {runway.calendar_name!r} runs out "
                    f"first for {runway.driving_dataset!r}, which turns off for good after "
                    f"{off} - no more dates are needed for it. "
                    f"{datasets[0].upper()}{datasets[1:]}.")
                continue
            horizon = ""
            if runway.driving_last_period != runway.last_period:
                horizon = (f" The calendar itself runs to {runway.last_period} on "
                            f"{runway.last_date}.")
            lines.append(
                f"WARNING (not failing the build): calendar {runway.calendar_name!r} runs out "
                f"first for {runway.driving_dataset!r}, which has only {runway.remaining} "
                f"future supply slot(s) left - its own last is {runway.driving_last_period} on "
                f"{runway.driving_last_date}. {datasets[0].upper()}{datasets[1:]}."
                f"{horizon} Author the next year's dates in contract/calendar.yaml; "
                f"`mothman schedule candidate-dates` proposes them.")
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

    # A CALENDAR WITH NO FUTURE DATES AT ALL IS NOT "LOW ON RUNWAY"
    # (#21). It used to be described that way here, which is how the
    # severest state ended up reading as the mild one in the one line a
    # reader is most likely to skim. When both kinds are present the
    # exhausted ones lead and the rest are counted after, so the worse
    # fact is never the parenthetical.
    out_of_dates = [r for r in low if r.is_exhausted]
    if out_of_dates:
        part = (f"{len(out_of_dates)} calendar(s) EXHAUSTED"
                if len(out_of_dates) > 1
                else f"calendar {out_of_dates[0].calendar_name!r} is EXHAUSTED")
        others = len(low) - len(out_of_dates)
        also = f" ({others} more low on runway)" if others else ""
        return (f"{part}{also}; {len(exhausted)} dataset(s) have no remaining slots and cannot be "
                f"processed until dates are added.")

    part = (f"{len(low)} calendar(s) low on runway"
            if len(low) > 1 else f"calendar {low[0].calendar_name!r} is low on runway")
    return f"{part}."
