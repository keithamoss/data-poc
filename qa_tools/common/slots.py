"""Slots - one expected supply, for one dataset, in one period
(REQ-PIPE-052).

THE DISTINCTION THIS MODULE EXISTS FOR, because everything downstream
is defined against it: a PERIOD is shared by every dataset on a
calendar, and a SLOT belongs to exactly one dataset. Child Protection's
six datasets share 2026-Q1; they have six different slots in it, with
six due instants, six grace allowances and six claim windows, because
all three of those are per-dataset facts.

Flattening that is the failure the requirement's own story names: one
late table dragging five punctual ones down with it. A collection-level
deadline can only ever be one table's answer imposed on the rest.

SLOTS ARE DERIVED, NEVER AUTHORED. Nobody writes a slot down; it falls
out of a dataset's participation in its calendar's periods. At ~30
datasets across years of history that is the only tractable shape - and
it means a slot cannot drift from the schedule, because there is
nothing to drift.

NOTHING HERE RECORDS ANYTHING. Whether a slot is overdue is a QUESTION
asked of the schedule and the slot's current state, not a flag some
sweep sets - see is_overdue() for why that matters. Same for
whether a slot is open or closed.

A dataset's expected time of day, grace allowance and claim window come
from its participation in contract/calendar.yaml, read through the one
loader (qa_tools/common/agreement.py, REQ-PIPE-110). They used to live in
each ODCS contract's slaProperties, parsed by pipeline/cadence.py, which
this module had to reach into from qa_tools/common/.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from qa_tools.common import asset_time, schedule
from qa_tools.common.schedule import Period


@dataclass(frozen=True)
class Slot:
    """ONE expected supply: this dataset, this period.

    `due_at` and `claim_opens_at` are real instants carrying their own
    offset (REQ-PIPE-048), never wall-clock times somebody has to
    interpret.

    `closes_at` IS WHEN THE NEXT CALENDAR PERIOD'S CLAIM WINDOW OPENS
    (REQ-PIPE-131), whether or not this dataset owes anything in that
    next period - so a dataset delivering February and August on a
    quarterly calendar closes February when MAY's window opens, and has
    no open slot until August's does. None only where the calendar has
    no next period and none before it to measure by (a calendar of a
    single date) - an authored calendar's LAST date closes as long after
    it opened as the period before it stayed open (REQ-PIPE-131
    criterion 16).

    This REVERSES the open-ended window this docstring used to defend
    ("NEVER CLOSES, because late is always allowed" - plans/supply-
    model.md Thread E). Lateness is still allowed WITHIN a period's open
    interval; it is no longer allowed across the next period's opening,
    which is what let a late file be filed backward into an older,
    unfilled period. Claiming FORWARD stays impossible: a slot whose
    window has not opened cannot be claimed at all.
    """

    dataset_id: str
    period: Period
    due_at: datetime
    grace: timedelta
    claim_opens_at: datetime
    closes_at: datetime | None = None

    @property
    def name(self) -> str:
        return self.period.name

    @property
    def date(self) -> date:
        return self.period.date

    @property
    def late_after(self) -> datetime:
        """The instant a supply stops counting as on time.

        A separate property rather than a stored field, so `due_at` and
        `grace` cannot disagree with it.
        """
        return self.due_at + self.grace


def _timing(dataset_id: str, agreement=None) -> tuple[str, int, str | None]:
    """(expected time of day, grace minutes, claim-window override) for one
    dataset, from its participation in contract/calendar.yaml (REQ-PIPE-110).

    THE NEWEST PARTICIPATION VERSION'S. Taking each period's own version is
    REQ-PIPE-113's; until it lands every dataset carries one version, so the
    answer is the same. The claim-window override is not returned here: it
    lives on the participation version, and schedule.claim_window reads it
    there, effective-dated, so the third value is always None.
    """
    entry = schedule._agreement(agreement).dataset(dataset_id)
    version = entry.participation[-1] if entry and entry.participation else None
    if version is None or version.expected_time is None or version.grace is None:
        raise schedule.ScheduleConfigError(
            f"dataset {dataset_id!r} has no participation version stating an expected time and "
            f"a grace allowance in contract/calendar.yaml, so none of its slots has a due "
            f"instant.")
    return version.expected_time, int(version.grace.total_seconds() // 60), None


def claimable_until(dataset_id: str, at: date, agreement=None) -> date:
    """How far ahead to generate slots for a supply arriving on `at`
    (post-build-review #73).

    THE BOUND IS THE WINDOW'S REACH, NOT TODAY. `slots_for_dataset`'s
    `until` is a GENERATION bound - where to stop, which a cadence-rule
    calendar needs because "every day" has no end. Passing the arrival
    date turns it into a SELECTION rule saying a supply may only claim a
    period that has already begun, which is precisely what the claim
    window exists to contradict: the window's whole job is to let a
    supply arrive BEFORE its slot's due instant and still be recognised
    as that period's.

    THE BUG THIS CLOSES, with its worked example, because the old
    behaviour looks reasonable. Child Protection's 2023-Q3 is due
    2023-08-01 and its window opens 2023-07-18. A supply arriving on
    the 25th - a week early, exactly as the calendar allows - was
    offered only Q1 and Q2, so it was filed against Q2, as a late
    resupply, and read about twelve weeks LATE. The honest answer is
    EARLY for Q3. Nothing was wrong with the classifier; it was handed
    the wrong slot before it was asked.

    ONE FEED HAD IT AND THE OTHER DID NOT, which is why it survived.
    The fault bites only where the window reaches back ACROSS a period
    boundary: four hours never leaves its own day, so Birth
    Registrations was immune, while fourteen days reaches a fortnight
    into the previous quarter - 14 days of every 91 exposed.

    WIDENING THE LIST IS NOT WIDENING WHAT MAY BE CLAIMED.
    `assignment.open_slot()` still filters on `claim_opens_at`, so a
    slot whose window has not opened is offered and not chosen - the behaviour the daily feed has always had for
    the current day. This only stops a claimable slot being absent.
    """
    return at + claim_window(dataset_id, agreement)


def claim_window(dataset_id: str, agreement=None) -> timedelta:
    """This dataset's claim window, as things stand today.

    NOT EFFECTIVE-DATED, deliberately, and the difference from
    `schedule.claim_window(on=...)` matters. That one answers "what
    window applied to THIS period", which is what a slot's own
    `claim_opens_at` needs. This one answers "how far ahead could any
    slot's window reach", which is a bound on generation rather than a
    property of a slot - so the widest current answer is the safe one,
    and generating a period too many costs nothing because the slot it
    makes is still filtered on its own `claim_opens_at`.
    """
    _, _, override = _timing(dataset_id, agreement)
    return schedule.claim_window(dataset_id, override, agreement=agreement)


def slots_for_dataset(dataset_id: str, until: date | None = None,
                      agreement=None) -> list[Slot]:
    """Every slot this dataset has, oldest first.

    One per period it PARTICIPATES in. A period the dataset declares
    not-expected produces NO slot - there is no supply owed, so there
    is nothing to be overdue, and creating one would invent an
    obligation the agency explicitly agreed did not exist. Note this is
    different from how periods themselves behave: a not-expected period
    is still RETURNED by the schedule, flagged, so the dashboard can
    show "no November file, agreed" rather than a silent gap.
    """
    agreement = schedule._agreement(agreement)
    expected_time, grace_minutes, window_override = _timing(dataset_id, agreement)
    grace = timedelta(minutes=grace_minutes)

    def claim_opens(period_date: date) -> datetime:
        # Resolved PER PERIOD, on that period's own date. Hoisting this
        # out of the loop is what made a new calendar version move every
        # historical slot's claim_opens_at - the same retroactivity
        # _effect_windows() already prevents for the dates themselves
        # (post-build-review #42). A zero window opens at the due
        # instant, which is REQ-PIPE-131 criterion 3 for free.
        window = schedule.claim_window(dataset_id, window_override, on=period_date,
                                       agreement=agreement)
        return asset_time.wall_clock(period_date, expected_time) - window

    # THE CALENDAR'S periods, not only the ones this dataset owes, so a
    # slot closes when the NEXT CALENDAR PERIOD's window opens
    # (REQ-PIPE-131 criterion 1). Read by index, never by walking the
    # sequence per slot (NFR 1).
    sequence = _calendar_periods(dataset_id, until, agreement)
    following = {p.name: sequence[i + 1].date for i, p in enumerate(sequence[:-1])}
    preceding = {p.name: sequence[i - 1].date for i, p in enumerate(sequence) if i > 0}

    def closes(period, opens: datetime) -> datetime | None:
        nxt = following.get(period.name)
        if nxt is not None:
            return claim_opens(nxt)
        # AN AUTHORED CALENDAR'S LAST PERIOD CLOSES TOO (REQ-PIPE-131
        # criterion 16, Keith 2026-10-05; post-build-review #93): it used
        # to stay open for ever, so a 2030 file was filed to 2027-Q4. It
        # stays open as long as the period before it did - the PROVISIONAL
        # measure, there being no claim-window end to use - and a file
        # after that finds no open slot and is held (criterion 10). A
        # calendar of one date has nothing to measure by and stays open.
        prev = preceding.get(period.name)
        return opens + (opens - claim_opens(prev)) if prev is not None else None

    out = []
    for dataset_period in schedule.periods_for_dataset(dataset_id, until=until,
                                                       agreement=agreement):
        if not dataset_period.expected:
            continue
        opens = claim_opens(dataset_period.date)
        due_at = asset_time.wall_clock(dataset_period.date, expected_time)
        out.append(Slot(dataset_id=dataset_id, period=dataset_period.period,
                         due_at=due_at, grace=grace, claim_opens_at=opens,
                         closes_at=closes(dataset_period.period, opens)))
    return out


#: How far ahead a slot is looked for by name: far enough for any period a
#: person would re-file into, bounded so a daily calendar does not
#: generate without end.
SLOT_LOOKUP_YEARS = 3


def slot_named(dataset_id: str, period: str, agreement=None) -> Slot | None:
    """This dataset's slot for `period`, or None where its calendar has no
    such period it takes part in."""
    from qa_tools.common import asset_time

    horizon = asset_time.local_date(asset_time.now())
    horizon = horizon.replace(year=horizon.year + SLOT_LOOKUP_YEARS)
    return next((s for s in slots_for_dataset(dataset_id, until=horizon, agreement=agreement)
                 if s.name == period), None)


def _calendar_periods(dataset_id: str, until: date | None, agreement=None) -> list[Period]:
    """The full period sequence a dataset's slots close against - its
    calendar's, or its own dates where it overrides the calendar - with
    the period AFTER `until` included, so the last slot generated still
    knows when it closes.

    ONE EXTRA PERIOD, not a longer horizon: a cadence rule generates a
    day at a time, so `until` plus a day reaches its next period; an
    authored calendar is finite, so it is read whole where the next
    period lies beyond that.
    """
    override = schedule.dataset_dates_override(dataset_id, agreement)
    if override is not None:
        return sorted(override, key=lambda p: p.date)
    cal = schedule.calendar_for_dataset(dataset_id, agreement)
    if until is None:
        return schedule.periods_for_calendar(cal.name, agreement=agreement)
    # FAR ENOUGH TO REACH THE NEXT PERIOD: a day for a cadence rule, or -
    # where `until` sits in an authored stretch - the start of the next
    # calendar version, which is where a following cadence rule's first
    # period is (delivery-critic, overnight sprint 3b: generated with
    # `until` just before such a switch, the last authored slot had no
    # closing instant at all).
    # Tried with a day FIRST, so a daily calendar with a far-future version
    # never generates the years in between.
    periods = schedule.periods_for_calendar(cal.name, until=until + timedelta(days=1),
                                            agreement=agreement)
    if periods and periods[-1].date > until:
        return periods
    later = [v.effective_from for v in cal.versions if v.effective_from > until]
    if later:
        periods = schedule.periods_for_calendar(cal.name, until=min(later), agreement=agreement)
        if periods and periods[-1].date > until:
            return periods
    if not cal.current.is_cadence_rule:
        periods = schedule.periods_for_calendar(cal.name, agreement=agreement)
    return periods


def is_open(slot: Slot, at: datetime) -> bool:
    """Is this slot OPEN at `at` (REQ-PIPE-131 criterion 1)?

    From its claim-opening instant until the next calendar period's.
    DERIVED, NEVER RECORDED, like is_overdue(), so it cannot be stale.
    """
    asset_time.parse_instant(at, "is_open(at)")
    return at >= slot.claim_opens_at and (slot.closes_at is None or at < slot.closes_at)


def is_closed(slot: Slot, at: datetime) -> bool:
    """Has this slot CLOSED by `at` - the next calendar period's claim
    window has opened? A closed slot is never filed to automatically,
    though a person may still re-file into it, substitute it, mark it
    not supplied, or promote what is already filed there
    (REQ-PIPE-131 criteria 9 and 13)."""
    asset_time.parse_instant(at, "is_closed(at)")
    return slot.closes_at is not None and at >= slot.closes_at


def is_overdue(slot: Slot, now: datetime, filled: bool) -> bool:
    """Is this slot overdue, as at `now`?

    ASKED, NEVER RECORDED, which is criterion 7 and a real design
    choice rather than a convenience. An overdue flag written by a
    nightly sweep is wrong between the moment a slot lapses and the
    moment the sweep runs, is wrong forever if the sweep does not run,
    and quietly makes "nothing is overdue" indistinguishable from
    "nothing checked". Deriving it means the answer is correct the
    instant it is asked, including for a dashboard built from
    configuration alone.

    `filled` is the caller's - only a promotion fills a slot
    (plans/supply-model.md), and this module has no access to promotion
    state by design: it would need data.
    """
    asset_time.parse_instant(now, "is_overdue(now)")
    return not filled and now > slot.late_after


def is_owed_supplies(dataset_id: str) -> bool:
    """Whether anything is ever owed from this dataset.

    NOT `slots_for_dataset(...) != []`, which is the obvious spelling
    and raises: a cadence-rule calendar generates for ever, so asking
    it for slots without a horizon is a question with no answer, and it
    says so rather than picking one. A cadence rule therefore always
    owes something; an authored calendar owes something if it has any
    periods at all.

    Used to tell an UNEXPECTED TABLE - a supplier sending something
    nothing is owed from - apart from an unrecognised artefact, which
    matched no pattern at all (REQ-PIPE-057 criterion 11), and to fail
    a dataset that is owed supplies and declares no arrival pattern
    (REQ-PIPE-058 criterion 7).
    """
    from qa_tools.common import schedule

    try:
        calendar = schedule.calendar_for_dataset(dataset_id)
    except schedule.NoCalendarAgreed:
        # CRITERION 1 OF REQ-PIPE-106, and it is the answer this whole
        # function exists to give: a dataset with no agreed schedule owes
        # nothing, so nothing it sends is unexpected and nothing it fails
        # to send is missing. Caught SEPARATELY from the config error
        # below, because that one means somebody got the configuration
        # wrong and this one means they got it right.
        return False
    except (schedule.ScheduleConfigError, KeyError):
        return False
    if calendar.current.is_cadence_rule:
        return True
    return bool(schedule.periods_for_dataset(dataset_id))
