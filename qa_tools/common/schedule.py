"""Delivery calendars, resolved from one place (REQ-PIPE-049).

THE DATES ARE THE SUPPLIER AGREEMENT. Everything here follows from that
one sentence (plans/supply-model.md Thread C). A holiday library
PREDICTS what was probably agreed; it does not CONSTITUTE it. So a
quarterly calendar's dates are AUTHORED and read back verbatim - never
computed from a rule at evaluation time - and the only generated dates
in this module are the CANDIDATES `mothman schedule candidate-dates`
prints for a human to review, edit and commit. Nothing evaluates
against those.

Rejected on the way here, and worth knowing because it sounds
reasonable: derive the date from a holiday library at runtime, or
derive it once and freeze the result. Neither loses on library quality -
holiday packages are year-keyed, so a later gazette amendment does not
silently rewrite a settled past date. They lose because freezing leaves
nowhere to record a date that differs from what the rule would generate,
which is exactly the case that matters: a supplier asked for the 3rd.

TWO SHAPES, AND THAT IS NOT A COMPROMISE. A quarterly calendar
enumerates four authored dates a year, known well in advance, where the
real agreement is "the closest business day to the 1st" - which no
day-of-month rule expresses. A daily calendar states a rule, because
365 enumerated dates would be absurd and the agreement genuinely is
"every day".

THE ASSET OWNS THE CALENDAR, A DATASET OWNS ITS PARTICIPATION. On a
scale argument, not a tidy one: the quarterly asset is heading for ~30
datasets, roughly 70% of them arriving every quarter and the rest once
or twice a year, still landing on one of the same four dates. Thirty
independent date lists would drift, and dataset A saying 2 February
against dataset B's 3 February for the same window is a class of bug
nothing would ever flag.

PERIOD AND SLOT ARE DIFFERENT THINGS, and this module only knows the
first. A PERIOD is a named bucket on the ASSET's calendar - a name and
a date, nothing else. A SLOT is one (dataset, period) pair actually
expected, and carries its own due instant, grace and claim window. One
period, many slots. Slots are REQ-PIPE-051's; asking this module when
something is DUE would be asking the calendar to know a dataset's
expected time, which is deliberately not here (see `carries no time of
day` below).

A CALENDAR DATE CARRIES NO TIME OF DAY. This supersedes Thread H's own
chaos-pass item 5, which said the schedule carries a time alongside the
dates - that predates Thread C's correction moving the deadline onto
the slot, and the two cannot both hold. A time on the calendar date is
a per-period deadline, which is precisely what was ruled out, because
thirty datasets sharing one period do not share one deadline.

EVERY CALENDAR IS VERSIONED AND EFFECTIVE-DATED, in the same shape
check lifecycle already uses. A supply is judged against the calendar in
force when it was due, so editing next year's dates can never
retroactively make a past supply late.
"""
from __future__ import annotations

import calendar as _calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta



from qa_tools.common import hierarchy


# Full month names, lower-cased for comparison. Full names ONLY: an
# abbreviation or a number is a second accepted form, and two forms
# means config that reads differently across thirty datasets for no
# gain. An INDEX would be worse still - it breaks silently the moment a
# calendar is edited or reordered, where a name simply stops matching.
MONTH_NAMES: tuple[str, ...] = tuple(_calendar.month_name[i] for i in range(1, 13))
_MONTH_BY_LOWER = {name.lower(): i for i, name in enumerate(MONTH_NAMES, start=1)}

# A duration carrying its own unit - `14d`, `4h`. One accepted form per
# unit, validated rather than coerced: a new parser is a new thing to
# get wrong, so it stays as small as it can be while reading naturally
# at both a quarterly and a daily scale. Minutes were rejected for
# consistency with the neighbouring `latency` property, because 14 days
# reads as 20160 and nobody can check that by eye.
_DURATION = re.compile(r"^(?P<n>\d+)(?P<unit>[dh])$")
_DURATION_UNITS = {"d": "days", "h": "hours"}


class ScheduleConfigError(ValueError):
    """A schedule configuration that cannot be honoured as written.

    Always names the offending value and where it sits. Rejected rather
    than coerced, throughout: a key this model cannot honour is a config
    author saying something they expect to happen, and accepting it
    silently is how a dataset ends up expecting something other than
    what its author wrote.
    """


class UnknownCalendarError(ScheduleConfigError):
    """A calendar name no calendar defines."""


@dataclass(frozen=True)
class Period:
    """One named bucket on the asset's calendar.

    A name and a date, and deliberately nothing else. The name is
    AUTHORED rather than derived from the date, because a 2 February
    delivery is often for the November-January window and only the
    people who agreed it know what they call that.
    """

    name: str
    date: date


@dataclass(frozen=True)
class DatasetPeriod:
    """One period as it applies to ONE dataset.

    Carries whether a supply is expected, because a period declared
    not-expected is SHOWN rather than omitted (criterion 14). Dropping
    it would make "we agreed there would be no November file" and "we
    forgot to configure November" look identical on the page, and those
    are opposite problems: one is fine and one is a gap.
    """

    period: Period
    expected: bool = True
    not_expected_reason: str | None = None

    @property
    def name(self) -> str:
        return self.period.name

    @property
    def date(self) -> date:
        return self.period.date


@dataclass(frozen=True)
class CalendarVersion:
    """One effective-dated version of a calendar."""

    effective_from: date
    changelog: tuple[str, ...]
    claim_window: timedelta
    periods: tuple[Period, ...]      # empty for a cadence-rule calendar
    cadence_rule: str | None         # None for an authored-date calendar

    @property
    def is_cadence_rule(self) -> bool:
        return self.cadence_rule is not None


@dataclass(frozen=True)
class Calendar:
    name: str
    description: str
    versions: tuple[CalendarVersion, ...]   # newest effective_from last
    # How few future slots left before the runway warning fires
    # (REQ-PIPE-053). NOT versioned, unlike the dates and the claim
    # window: those are the supplier agreement, and this is an
    # operational threshold for when WE want telling. None takes
    # qa_tools.common.runway's own default.
    runway_warning_slots: int | None = None

    def version_in_force(self, on: date) -> CalendarVersion:
        """The version a supply due on `on` is judged against.

        Not simply the newest: that is the whole point of effective
        dating. Editing next year's dates must never retroactively move
        a date a past supply was already judged against.
        """
        from qa_tools.common import in_force

        version = in_force.version_on(self.versions, on)
        if version is None:
            raise ScheduleConfigError(
                f"calendar {self.name!r} has no version in force on {on.isoformat()} - "
                f"its earliest is {self.versions[0].effective_from.isoformat()}")
        return version

    @property
    def current(self) -> CalendarVersion:
        return self.versions[-1]


def parse_duration(value, where: str) -> timedelta:
    """`14d` / `4h` as a timedelta, or `ScheduleConfigError`.

    Rejects rather than coerces - `14 days`, `14D`, a bare `14` and
    `2w` are all errors, and the message says what is accepted. One
    form per unit is the point: the alternative is thirty datasets whose
    config reads differently for no gain.
    """
    m = _DURATION.match(str(value).strip())
    if not m:
        raise ScheduleConfigError(
            f"{where}: {value!r} is not a duration. Expected a whole number followed by "
            f"'d' for days or 'h' for hours - for example 14d or 4h.")
    return timedelta(**{_DURATION_UNITS[m.group("unit")]: int(m.group("n"))})


def format_duration(value: timedelta) -> str:
    """A timedelta back in the form the config authors it in - `14d`,
    `4h`.

    The inverse of `parse_duration`, and it exists because the one
    surface that displayed a claim window printed `str(timedelta)`:
    `14 days, 0:00:00` and `4:00:00`. REQ-PIPE-050 rejects every form
    but one on purpose - "four ways to write one duration is four ways
    for thirty datasets' config to read differently" - so a display
    inventing a fifth is the same problem from the other end. `4:00:00`
    additionally reads as a time of day, in a table whose neighbouring
    columns are times (post-build-review #27).

    Whole days where it divides, whole hours otherwise, and minutes
    only if some future config ever needs them - a duration this cannot
    express has no authored form either, so falling back to the
    timedelta's own repr would be showing something nobody could type
    back in.
    """
    seconds = int(value.total_seconds())
    if seconds and seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds and seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    raise ScheduleConfigError(
        f"{value!r} has no authored form - a claim window is written in whole days "
        f"or whole hours, like 14d or 4h, and nothing else parses.")


def parse_month_name(value, where: str) -> int:
    """A full month NAME as its 1-12 number, case-insensitively.

    Abbreviations, numbers and positional indices are all rejected -
    see MONTH_NAMES above for why full names only.
    """
    text = str(value).strip()
    number = _MONTH_BY_LOWER.get(text.lower())
    if number is None:
        raise ScheduleConfigError(
            f"{where}: {value!r} is not a full month name. Expected one of "
            f"{', '.join(MONTH_NAMES)} - abbreviations, numbers and positions are not accepted, "
            f"because an index breaks silently when a calendar is edited or reordered.")
    return number


def _parse_version(raw: dict, calendar_name: str, index: int) -> CalendarVersion:
    where = f"calendar {calendar_name!r} version {index + 1}"
    effective_from = raw.get("effective_from")
    if not effective_from:
        raise ScheduleConfigError(f"{where}: no effective_from. Every version is effective-dated, "
                                   f"so a past supply is judged against the calendar then in force.")
    changelog = tuple(raw.get("changelog") or ())
    if not changelog:
        raise ScheduleConfigError(
            f"{where}: no changelog entry. A calendar is a governance artefact - a version "
            f"nobody wrote a reason for is a date change nobody can account for.")
    claim_window = parse_duration(raw.get("claim_window"), f"{where} claim_window")

    cadence = raw.get("cadence") or None
    dates = raw.get("dates") or None
    if bool(cadence) == bool(dates):
        raise ScheduleConfigError(
            f"{where}: a calendar version states EITHER authored `dates:` or a `cadence:` rule, "
            f"never both and never neither.")

    if cadence:
        rule = cadence.get("rule")
        if rule != "daily":
            raise ScheduleConfigError(
                f"{where}: cadence rule {rule!r} is not supported - only 'daily' is, which is "
                f"the one schedule genuinely worth expressing as a rule rather than a date list.")
        return CalendarVersion(effective_from=_as_date(effective_from, where),
                                changelog=changelog, claim_window=claim_window,
                                periods=(), cadence_rule=rule)

    periods = []
    seen: dict[str, str] = {}
    for entry in dates:
        name, when = entry.get("period"), entry.get("date")
        if not name or not when:
            raise ScheduleConfigError(f"{where}: every authored date needs both a `period:` name "
                                       f"and a `date:` - got {entry!r}")
        if name in seen:
            raise ScheduleConfigError(
                f"{where}: period {name!r} is authored twice ({seen[name]} and {when}). A period "
                f"names one bucket on the calendar, so two dates for it makes every slot "
                f"referring to it ambiguous.")
        seen[name] = str(when)
        periods.append(Period(name=name, date=_as_date(when, f"{where} period {name!r}")))

    out_of_order = [p.name for a, p in zip(periods, periods[1:]) if p.date <= a.date]
    if out_of_order:
        raise ScheduleConfigError(
            f"{where}: authored dates must run forwards in time, and these do not: "
            f"{', '.join(out_of_order)}.")
    return CalendarVersion(effective_from=_as_date(effective_from, where), changelog=changelog,
                            claim_window=claim_window, periods=tuple(periods), cadence_rule=None)


def _as_date(value, where: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ScheduleConfigError(f"{where}: {value!r} is not an ISO date (YYYY-MM-DD)") from None


def parse_calendar(raw: dict) -> Calendar:
    """One calendar from its config - read by `agreement.load`, the one loader."""
    name = raw.get("name")
    versions = [_parse_version(v, name, i) for i, v in enumerate(raw.get("versions") or [])]
    if not versions:
        raise ScheduleConfigError(f"calendar {name!r} has no versions")
    versions.sort(key=lambda v: v.effective_from)
    runway = raw.get("runway_warning_slots")
    if runway is not None and (not isinstance(runway, int) or isinstance(runway, bool)
                                or runway < 1):
        raise ScheduleConfigError(
            f"calendar {name!r}: runway_warning_slots is {runway!r}. It counts SLOTS, so it "
            f"has to be a whole number of at least 1 - a threshold of 0 is a warning that "
            f"only ever fires once the schedule has already run out.")
    return Calendar(name=name, description=(raw.get("description") or "").strip(),
                    versions=tuple(versions), runway_warning_slots=runway)


def _agreement(agreement=None):
    """The agreement to read: the one passed, or the committed one
    (REQ-PIPE-110 criterion 31 - every reader takes it as an argument)."""
    if agreement is not None:
        return agreement
    from qa_tools.common import agreement as agreement_mod

    return agreement_mod.current()


def _load(agreement=None) -> dict[str, Calendar]:
    calendars = dict(_agreement(agreement).calendars)
    return calendars


def calendars(agreement=None) -> list[Calendar]:
    return list(_load(agreement).values())


def calendar(name: str, agreement=None) -> Calendar:
    try:
        return _load(agreement)[name]
    except KeyError:
        raise UnknownCalendarError(
            f"{name!r} is not a calendar in contract/calendar.yaml. "
            f"Known: {', '.join(sorted(_load(agreement)))}") from None


#: The key a dataset uses to say it has NO calendar, DELIBERATELY
#: (REQ-PIPE-106 criterion 2), and the two things that can mean.
#:
#: WHY A KEY OF ITS OWN rather than allowing `calendar:` to be absent.
#: Absence already means something: `validate_schedule.py` fails a dataset
#: with no calendar, on purpose, because without that a typo'd calendar
#: name leaves a dataset silently expecting nothing - and a dataset
#: expecting nothing reports no missing supply, ever. Allowing absence
#: would destroy a gate that catches a real class of error, which this
#: requirement's own second NFR forbids explicitly. A deliberate
#: declaration is what separates "nobody has agreed a schedule" from
#: "somebody mistyped one".
NO_CALENDAR_KEY = "no_calendar"

#: SAMPLE DATA, BEFORE ANY SUPPLY IS AGREED. It will graduate: a schedule
#: gets agreed, and from that point it owes supplies like anything else.
NOT_YET_AGREED = "not-yet-agreed"

#: A ONE-OFF EXTRACTION FOR A PROJECT. It has supplies and no cadence at
#: all, permanently, and criterion 3 is explicit that it must NOT be made
#: to graduate. Kept apart from the case above because the two look
#: identical in the data and mean opposite things to a person reading the
#: dashboard: one is waiting for something, the other is finished.
NEVER = "never"

NO_CALENDAR_VALUES = (NOT_YET_AGREED, NEVER)


class NoCalendarAgreed(Exception):
    """This dataset has declared that it has no delivery calendar.

    A DISTINCT EXCEPTION, NOT A ScheduleConfigError, and the difference is
    the whole of REQ-PIPE-106 criterion 1: a config error means somebody
    got it wrong and the pipeline should stop, while this means the
    configuration is exactly as intended and there is simply no period
    arithmetic to do. Callers that should carry on - the filing rule, the
    runway warning, the rollups - catch this one and skip the dataset;
    nothing catches ScheduleConfigError.
    """

    def __init__(self, dataset_id: str, kind: str):
        self.dataset_id, self.kind = dataset_id, kind
        agreed = ("no schedule has been agreed for it yet"
                   if kind == NOT_YET_AGREED
                   else "it is a one-off extraction and will never have one")
        super().__init__(
            f"dataset {dataset_id!r} has no delivery calendar because {agreed} "
            f"({NO_CALENDAR_KEY}: {kind}). It owes no supply and is filed to no period.")


def no_calendar(dataset_id: str, agreement=None) -> str | None:
    """Which kind of no-calendar dataset this is, or None where it has one.

    Reads the declaration and validates it here rather than only in the
    gate, so a value nobody recognises cannot be read as "not yet agreed"
    by accident - which would be the quiet direction.
    """
    hierarchy.dataset(dataset_id)
    entry = _agreement(agreement).dataset(dataset_id)
    declared = entry.no_calendar if entry else None
    if declared is None:
        return None
    if declared not in NO_CALENDAR_VALUES:
        raise ScheduleConfigError(
            f"dataset {dataset_id!r}: {NO_CALENDAR_KEY}: {declared!r} is not one of "
            f"{', '.join(NO_CALENDAR_VALUES)}. {NOT_YET_AGREED} means sample data before a "
            f"schedule is agreed, and it will graduate; {NEVER} means a one-off extraction "
            f"that has supplies and no cadence at all.")
    if entry.calendar:
        raise ScheduleConfigError(
            f"dataset {dataset_id!r} declares both `calendar: {entry.calendar}` and "
            f"`{NO_CALENDAR_KEY}: {declared}`. One of those is wrong and this will not guess "
            f"which - a dataset either has an agreed schedule or says it has none.")
    return declared


def will_graduate(dataset_id: str) -> bool:
    """Whether a dataset with no calendar is expected to gain one.

    Criterion 3. False for a one-off extraction, which must never be
    presented as waiting for a schedule somebody has to agree.
    """
    return no_calendar(dataset_id) == NOT_YET_AGREED


def owes_from(dataset_id: str, agreement=None) -> date | None:
    """The date a graduated dataset started owing supplies, or None.

    CRITERION 16'S RECORD OF WHEN IT GRADUATED, and it is CONFIGURATION
    rather than an observed event on purpose: graduation IS the
    configuration change - a calendar gets named - so the date it took
    effect is authored beside it and reviewed with it. An observed
    "when did we first notice a calendar appear" would need the system to
    remember the previous config, which is state about configuration, and
    would date the graduation to whenever the pipeline next happened to
    run.

    It also does real work rather than only recording: a dataset that
    graduated in November must not be reported as having owed supplies
    all year, and this is what every period before that date is judged
    against.

    FOLDED INTO PARTICIPATION (REQ-PIPE-110 criterion 27): it is the
    effective date of the dataset's first participation version, never a
    key of its own.
    """
    hierarchy.dataset(dataset_id)
    entry = _agreement(agreement).dataset(dataset_id)
    if entry is None or not entry.participation:
        return None
    return entry.participation[0].effective_from


def calendar_for_dataset(dataset_id: str, agreement=None) -> Calendar:
    """The calendar a dataset names, resolved through the hierarchy.

    Raises for a dataset the hierarchy does not define, and for a
    calendar no calendar defines - a dataset named in one place and
    absent from the other must be a detectable error, never a silent
    mismatch.

    RAISES `NoCalendarAgreed` FOR A DATASET THAT SAYS IT HAS NONE
    (REQ-PIPE-106), which is a different thing from the config error
    below: one means the configuration is as intended, the other that
    somebody got it wrong.
    """
    hierarchy.dataset(dataset_id)  # raises UnknownDatasetError, naming the known ids
    declared = no_calendar(dataset_id, agreement)
    if declared is not None:
        raise NoCalendarAgreed(dataset_id, declared)
    name = _agreement(agreement).calendar_name_for(dataset_id)
    if not name:
        raise ScheduleConfigError(
            f"dataset {dataset_id!r} names no `calendar:` and does not declare "
            f"`{NO_CALENDAR_KEY}:` either. Every dataset does one or the other - without "
            f"either there is nothing to judge its supplies against, and a typo'd calendar "
            f"name would leave it silently expecting nothing.")
    return calendar(name, agreement)


def delivery_months(dataset_id: str, on: date | None = None,
                    agreement=None) -> tuple[int, ...] | None:
    """The months a dataset participates in, as 1-12 numbers, or None
    for "all of them".

    None and "every month" are deliberately the same answer: a dataset
    that says nothing participates in everything its calendar generates,
    which is the reading that makes ~30 datasets tolerable to configure.

    READ FROM PARTICIPATION (REQ-PIPE-110): the `participates` list of the
    participation version in force on `on` - the period's own date - or of
    the newest version where `on` is not given.
    """
    entry = _agreement(agreement).dataset(dataset_id)
    if entry is None or not entry.participation:
        return None
    if on is None:
        return entry.participation[-1].participates
    version = _agreement(agreement).participation_on(dataset_id, on)
    return version.participates if version else None


def not_expected_periods(dataset_id: str, agreement=None) -> dict[str, str]:
    """{period name: reason} for periods a dataset declares no supply
    for.

    A REASON IS REQUIRED, not decoration. "No November file" with
    nothing beside it is indistinguishable, six months later, from
    somebody having forgotten to configure November - and those are
    opposite problems.
    """
    entry = _agreement(agreement).dataset(dataset_id)
    return dict(entry.not_expected) if entry else {}


def dataset_dates_override(dataset_id: str, agreement=None) -> tuple[Period, ...] | None:
    """A dataset's OWN authored dates, replacing its calendar's.

    Overriding is a different act from subsetting, and both exist
    deliberately. No dataset needs this today - everything is aligned to
    one of the four agreed days - but it is cheap now and awkward to
    retrofit once thirty datasets assume subsetting is the only shape.
    VERSIONED LIKE A CALENDAR (REQ-PIPE-110 criterion 25): each version
    contributes only the periods inside its own period of effect.
    """
    entry = _agreement(agreement).dataset(dataset_id)
    own = entry.own_dates if entry else None
    if own is None:
        return None
    if any(v.participates is not None for v in entry.participation):
        raise ScheduleConfigError(
            f"dataset {dataset_id!r} dates: a dataset states EITHER its own `dates:` "
            f"(overriding its calendar) OR a `participates:` list of months (subsetting it), "
            f"never both - the two mean different things and carrying both leaves no way to "
            f"tell which was meant.")
    return tuple(_calendar_periods(own))


def _calendar_periods(cal: "Calendar", until: date | None = None) -> list[Period]:
    """An authored calendar's periods, version by version - each version
    contributing only the periods inside its own period of effect."""
    out: list[Period] = []
    for version, start, end in _effect_windows(cal):
        for period in version.periods:
            if period.date < start or (end is not None and period.date >= end):
                continue
            out.append(period)
    out.sort(key=lambda p: p.date)
    return [p for p in out if until is None or p.date <= until]


def _effect_windows(cal: Calendar) -> list[tuple[CalendarVersion, date, date | None]]:
    """(version, from, until-exclusive) for each version, in order.

    The last version's window has no end, which is what `None` means -
    a calendar in force now stays in force.
    """
    starts = [v.effective_from for v in cal.versions]
    return [(v, starts[i], starts[i + 1] if i + 1 < len(starts) else None)
            for i, v in enumerate(cal.versions)]


def periods_for_calendar(calendar_name: str, until: date | None = None,
                         agreement=None) -> list[Period]:
    """One calendar's full period sequence, in date order (REQ-PIPE-051).

    DERIVED VERSION BY VERSION, and that is the whole point rather than
    an implementation detail. Each version contributes only the periods
    whose own date falls inside its own period of effect, so a version
    authored today cannot reach back and change - or delete - a period
    that a past supply was already filed against.

    This replaced reading `calendar.current` for the entire sequence,
    which was a real bug rather than a simplification. Adding a version
    effective 2027 did not merely move the earlier periods; it replaced
    them, so four years of history CEASED TO EXIST and every supply
    filed against 2023-Q1 had no period at all. Latent only because no
    second version has ever been authored - see
    tests/test_schedule.py's own account.

    A cadence-rule version generates one period per day across its own
    window, named by its date, so a calendar can legitimately change
    from a rule to authored dates or back.
    """
    cal = calendar(calendar_name, agreement)
    out: list[Period] = []
    for version, start, end in _effect_windows(cal):
        stop = end - timedelta(days=1) if end is not None else until
        if version.is_cadence_rule:
            if stop is None:
                raise ScheduleConfigError(
                    f"calendar {calendar_name!r} is a cadence rule with no end - pass `until` "
                    f"to say where to stop.")
            out.extend(Period(name=(start + timedelta(days=i)).isoformat(),
                               date=start + timedelta(days=i))
                        for i in range((stop - start).days + 1))
            continue
        for period in version.periods:
            if period.date < start:
                continue
            if end is not None and period.date >= end:
                continue
            out.append(period)
    out.sort(key=lambda p: p.date)
    if until is not None:
        out = [p for p in out if p.date <= until]
    return out


def schema_name(period: Period) -> str:
    """The warehouse schema this period's supplies are stored in
    (REQ-PIPE-051 criterion 6).

    ONE PERIOD, ONE SCHEMA - the physical storage model's own shape
    (plans/supply-model.md Thread A). Which makes this function's
    output a PHYSICAL NAME rather than a label: changing how a period
    is named renames real schemas, so the NFR attached to this
    criterion says to name it once and not revisit it, and this
    docstring is where that warning has to live.

    Lower-cased, non-alphanumerics folded to underscores, and prefixed
    - `2026-Q1` becomes `period_2026_q1`, `2026-09-01` becomes
    `period_2026_09_01`. The prefix is not decoration: an authored
    period name is whatever the agency calls it, and a bare `2026_q1`
    is not a legal unquoted identifier in every engine this might ever
    touch, while a leading letter always is.
    """
    folded = re.sub(r"[^a-z0-9]+", "_", period.name.strip().lower()).strip("_")
    if not folded:
        raise ScheduleConfigError(
            f"period {period.name!r} has no characters that can name a schema. A period "
            f"name has to survive becoming a physical identifier.")
    return f"period_{folded}"


def periods_for_dataset(dataset_id: str, until: date | None = None,
                        agreement=None) -> list[DatasetPeriod]:
    """Every period this dataset's schedule produces, in date order.

    An authored calendar's periods, filtered to the months the dataset's
    participation owes on each period's date, or the dataset's own dates where it overrides the
    calendar outright. A cadence-rule calendar generates one period per
    day up to `until`, which is required there - "every day" has no end
    of its own, so the caller has to say where it stops.

    Periods the dataset declares not-expected are RETURNED, flagged,
    never dropped - see DatasetPeriod.
    """
    cal = calendar_for_dataset(dataset_id, agreement)
    months = delivery_months(dataset_id, agreement=agreement)
    version = cal.current
    skipped = not_expected_periods(dataset_id, agreement)
    begins = owes_from(dataset_id, agreement)

    def _decorate(periods):
        return [DatasetPeriod(period=p, expected=p.name not in skipped,
                               not_expected_reason=skipped.get(p.name))
                for p in periods]

    def _owed(periods):
        """NOT YET OWING before the first participation version (criterion
        30), and each period filtered by the participation in force ON ITS
        OWN DATE."""
        out = []
        for p in periods:
            if begins is not None and p.date < begins:
                continue
            on = delivery_months(dataset_id, p.date, agreement)
            if on is not None and _version_in_force(cal, p.date).is_cadence_rule:
                # CRITERION 7 PER VERSION: months mean nothing against a
                # cadence rule, and dropping the period would leave the
                # dataset silently owing nothing for it.
                raise ScheduleConfigError(
                    f"dataset {dataset_id!r}'s participation in force on {p.date.isoformat()} "
                    f"names months, and calendar {cal.name!r} is a cadence rule on that date. "
                    f"Rejected rather than ignored.")
            if on is not None and p.date.month not in on:
                continue
            out.append(p)
        return out

    override = dataset_dates_override(dataset_id, agreement)
    if override is not None:
        return _decorate(_owed([p for p in override if until is None or p.date <= until]))

    if version.is_cadence_rule and months is not None:
        raise ScheduleConfigError(
            f"dataset {dataset_id!r} names calendar {cal.name!r}, which is a cadence rule, "
            f"AND its participation names months. Months only mean something against authored dates; "
            f"a dataset on a cadence rule participates in every period the rule generates. "
            f"Rejected rather than ignored, because a key that is accepted and discarded is "
            f"how a dataset ends up expecting something other than what its author wrote.")
    if version.is_cadence_rule and until is None:
        raise ScheduleConfigError(
            f"dataset {dataset_id!r} is on cadence calendar {cal.name!r}, which generates "
            f"periods without end - pass `until` to say where to stop.")

    # The CALENDAR's full sequence, version by version (REQ-PIPE-051),
    # then this dataset's own participation applied to it. Derived here
    # rather than re-read from `version` so that a dataset sees every
    # period its calendar ever had, not only the newest version's.
    periods = periods_for_calendar(cal.name, until=until, agreement=agreement)
    return _decorate(_owed(periods))


def claim_window(dataset_id: str, contract_value: str | None = None,
                  on: date | None = None, agreement=None) -> timedelta:
    """How long BEFORE a slot's due instant its claim window opens.

    `on` IS THE PERIOD'S OWN DATE, and passing it is what makes the
    answer effective-dated: the calendar version in force on that date
    supplies the default, not whichever version happens to be current
    when the question is asked. Omitting it means "as things stand
    today", which is what a `mothman schedule show` line wants and what
    no slot derivation should ever want (post-build-review #42).

    BEFORE, and the first line of this docstring used to say "after",
    which was wrong in the one way that matters (found building
    REQ-PIPE-052). A window measured forwards from the period's date
    describes something that CLOSES - a deadline for claiming - and the
    settled rule is the opposite: the window opens a configured
    interval BEFORE the due instant, and the slot then stays open until
    the NEXT calendar period's window opens (REQ-PIPE-131, which replaced
    Thread E's "never closes").

    The difference is not pedantry. What the window prevents is
    claiming FORWARD into a slot that is not yet claimable, which is
    what makes the forward cascade structurally impossible. Read as a
    closing deadline it would instead make a late supply unfileable -
    the exact opposite behaviour, from the same number.

    qa_tools/common/slots.py is what applies it.

    The CALENDAR carries the default and a dataset's participation
    version may override it in contract/calendar.yaml - say nothing, get
    the default (REQ-PIPE-110; it used to be a `claimWindow` slaProperty
    in the dataset's own contract).

    WHY THE DEFAULT SITS ON THE CALENDAR rather than on the asset root,
    which is where an earlier answer put it: a quarterly calendar's
    sensible window is measured in days and a daily calendar's in hours,
    so a single asset-root default would be wrong for one of them on day
    one, in this repo. An asset-root default would hand Birth
    Registrations a 14-day claim window on a daily feed. Putting it on
    the calendar makes the default track the thing that sets its scale
    (Keith, 2026-09-22, shown all three shapes side by side).

    Per-dataset-only was rejected twice for the same reason the calendar
    is asset-level at all: thirty near-identical values on one asset,
    which nobody maintains and which drift.

    NOT called earlyWindow, deliberately. Nothing measures how early a
    supply is in order to assign it - earliness is a reported
    consequence of assignment, so earlyWindow would name the wrong half
    of what this does.

    BOTH ARE VERSIONED NOW. The override used to be declared in the
    dataset's own ODCS contract, which had no effective_from, so it
    could not be; since REQ-PIPE-110 it sits on the dataset's
    participation versions and resolves, like the calendar's default, on
    the period's own date. `contract_value` survives only as an explicit
    value a caller passes.
    """
    if contract_value is not None:
        return parse_duration(contract_value, f"dataset {dataset_id!r} claimWindow")
    # A PARTICIPATION VERSION MAY OVERRIDE IT (REQ-PIPE-110 criterion 4).
    entry = _agreement(agreement).dataset(dataset_id)
    if on is not None:
        # A period before the first version takes that first version's
        # inputs - all of them, this override included (REQ-PIPE-113's
        # PROVISIONAL rule, as slots._participation_for applies it).
        version = (_agreement(agreement).participation_on(dataset_id, on)
                   or (entry.participation[0] if entry and entry.participation else None))
    else:
        version = entry.participation[-1] if entry and entry.participation else None
    if version is not None and version.claim_window is not None:
        return version.claim_window
    cal = calendar_for_dataset(dataset_id, agreement)
    if on is None:
        return cal.current.claim_window
    return _version_in_force(cal, on).claim_window


def _version_in_force(cal: Calendar, on: date) -> CalendarVersion:
    """The version whose period of effect contains `on`.

    A date BEFORE the first version's effective_from takes that first
    version rather than raising - the same thing `periods_for_calendar`
    does implicitly by never generating such a period, and the only
    answer that does not turn "this calendar was authored later than
    its own earliest data" into an error nobody can act on.
    """
    from qa_tools.common import in_force

    return in_force.version_on(cal.versions, on) or cal.versions[0]


def candidate_dates(calendar_name: str, year: int) -> list[tuple[Period, str]]:
    """Proposed dates for one year, for a HUMAN to review and commit.

    (period, note) pairs. THESE ARE NOT AN EVALUATION PATH, and that is
    the whole reason this function is allowed to exist at all: the
    authored dates ARE the supplier agreement, so a generated date can
    only ever be a suggestion somebody checks. `mothman schedule
    candidate-dates` prints them; nothing reads them back.

    The pattern is inferred from the calendar's own existing dates - the
    months it lands in, and the day of the month - rather than from a
    holiday library. A weekend lands a note rather than being silently
    moved, because moving it would be this function deciding something
    it has no standing to decide: the real agreement is often "the
    closest business day", and which side of the weekend that falls is
    the supplier's answer, not ours.
    """
    cal = calendar(calendar_name)
    version = cal.current
    if version.is_cadence_rule or not version.periods:
        return []

    months = sorted({p.date.month for p in version.periods})
    day = version.periods[-1].date.day
    # The authored names follow a pattern of their own, and guessing it
    # wrongly is worse than not guessing: a name is authored precisely
    # because only the people who agreed it know what they call it. So
    # the name is offered as a fill-in-the-blank where it cannot be
    # inferred from the same month in an earlier year.
    by_month_position = {}
    for p in version.periods:
        by_month_position.setdefault(p.date.month, p.name)

    out: list[tuple[Period, str]] = []
    for month in months:
        when = date(year, month, min(day, _calendar.monthrange(year, month)[1]))
        template = by_month_position.get(month, "")
        name = _renamed_for_year(template, when, year)
        note = ""
        if when.weekday() >= 5:
            note = f"{when.strftime('%A')} - check what was actually agreed"
        if not name:
            name = f"{year}-?"
            note = (note + "; " if note else "") + "no earlier date in this month to name it from"
        out.append((Period(name=name, date=when), note))
    return out


def _renamed_for_year(template: str, when: date, year: int) -> str:
    """An existing period name with its year advanced, or "" if the name
    does not carry one recognisably.

    Deliberately conservative - a name this cannot confidently rewrite
    comes back blank for a human to fill in, rather than being invented.
    """
    if not template:
        return ""
    m = re.search(r"(19|20)\d{2}", template)
    if not m:
        return ""
    offset = year - int(m.group(0))
    return template[:m.start()] + str(int(m.group(0)) + offset) + template[m.end():]


def date_of(period_name: str, dataset_id: str) -> date | None:
    """The date a named period falls on, for this dataset's calendar.

    THE INVERSE OF A NAME, and it is a lookup rather than a parse
    because a period's name is whatever its calendar's template says -
    "2023-Q1" carries a quarter and "Nov-Jan window" carries nothing at
    all. Only a DAILY calendar happens to name its periods by the day,
    and even there parsing the name would be assuming a template rather
    than reading one.

    BOUNDED BY A YEAR AHEAD of the asset's today, because a daily
    calendar generates periods without end and periods_for_calendar()
    refuses an unbounded ask. A year is comfortably past anything a
    supply can be promoted into and cheap to generate.

    None where the calendar does not name that period, which is a real
    answer rather than an error: a period from another calendar, or one
    whose name changed, is simply not this dataset's.
    """
    from qa_tools.common import asset_time

    horizon = asset_time.now().date() + timedelta(days=365)
    for period in periods_for_calendar(calendar_for_dataset(dataset_id).name,
                                        until=horizon):
        if period.name == period_name:
            return period.date
    return None
