"""The delivery agreement, read once into one immutable value (REQ-PIPE-110).

ONE FILE, contract/calendar.yaml, holds an asset's whole delivery
agreement: the named calendars, which calendar each collection and dataset
is on, and each dataset's participation - which periods it owes, its
expected time of day, its grace allowance and any claim-window override, as
effective-dated versions - with `not_expected`, a dataset's own authored
dates, and the deliberate no-calendar declaration (REQ-PIPE-106).

ONE LOADER, ONE VALUE, PASSED AS AN ARGUMENT (criterion 31; delivery-
architect B1). `load(path)` reads a file into an `Agreement`; `current()` is
the committed file's, read once per process. Every consumer takes an
`agreement=` argument that defaults to `current()`, so two values - the
agreement before and after a change - can be held side by side in one
process, which REQ-PIPE-111's freeze, REQ-PIPE-169's impact preview and
REQ-PIPE-173's backstop all need. Before this, schedule._load,
asset_time and slots._timing each read a fixed path behind
lru_cache, and no process could hold two.

THIS IS CONFIGURATION ONLY (criterion 23): no database, no warehouse
schema, nothing under data/.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from types import MappingProxyType

from qa_tools.common import config_yaml

CALENDAR_YAML = Path(__file__).resolve().parent.parent.parent / "contract" / "calendar.yaml"

#: The key a participation version uses to say which periods it owes.
PARTICIPATES = "participates"
#: `participates: all` - every period the calendar generates.
ALL = "all"


@dataclass(frozen=True)
class ParticipationVersion:
    """One effective-dated version of a dataset's participation (criteria 3-8)."""

    effective_from: date
    #: Delivery months owed (1-12), or None for every period - `all`, or not stated.
    participates: tuple[int, ...] | None
    #: Why only some periods are owed - required where `participates` is a list.
    reason: str | None
    expected_time: str | None
    grace: timedelta | None
    claim_window: timedelta | None
    changelog: tuple[tuple[str, str, str], ...]
    #: Whole days before the period's date the supply is due (REQ-PIPE-113
    #: criterion 1); zero unless stated.
    days_before: int = 0
    #: The keys this version wrote, for the restate rule (criterion 33).
    stated: frozenset[str] = frozenset()


@dataclass(frozen=True)
class DatasetAgreement:
    dataset_id: str
    #: The calendar the dataset names itself, or None to take its collection's.
    calendar: str | None
    no_calendar: str | None
    participation: tuple[ParticipationVersion, ...]
    not_expected: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    #: A dataset's own authored dates, as a calendar of its own, or None.
    own_dates: object | None = None


@dataclass(frozen=True)
class Agreement:
    """The whole delivery agreement of one asset, immutable."""

    path: Path
    calendars: MappingProxyType          # name -> schedule.Calendar
    collections: MappingProxyType        # collection id -> calendar name
    datasets: MappingProxyType           # dataset id -> DatasetAgreement

    def dataset(self, dataset_id: str) -> DatasetAgreement | None:
        return self.datasets.get(dataset_id)

    def calendar_name_for(self, dataset_id: str) -> str | None:
        """The calendar a dataset is on: its own, else its collection's
        (criteria 10 and 11)."""
        from qa_tools.common import hierarchy

        own = self.dataset(dataset_id)
        if own is not None and own.calendar:
            return own.calendar
        return self.collections.get(hierarchy.dataset(dataset_id).collection_id)

    def participation_on(self, dataset_id: str, on: date) -> ParticipationVersion | None:
        """The participation version in force on a date, or None where the
        dataset's first version has not begun - NOT YET OWING (criterion 30)."""
        from qa_tools.common import in_force

        entry = self.dataset(dataset_id)
        return in_force.version_on(entry.participation, on) if entry else None


def _changelog(raw, where: str) -> tuple[tuple[str, str, str], ...]:
    from qa_tools.common.schedule import ScheduleConfigError

    out = []
    for entry in raw or []:
        if not isinstance(entry, dict):
            raise ScheduleConfigError(
                f"{where}: changelog entry {entry!r} is a plain string. Every entry is a date, an "
                f"author and a change - {{date: YYYY-MM-DD, author: ..., change: ...}} (criterion 13).")
        out.append((str(entry.get("date")), str(entry.get("author")), str(entry.get("change"))))
    return tuple(out)


def _participation_version(raw: dict, where: str) -> ParticipationVersion:
    from qa_tools.common import schedule

    stated = frozenset(k for k in (PARTICIPATES, "reason", "expected_time", "grace", "claim_window",
                                   "days_before") if k in raw)
    months = raw.get(PARTICIPATES)
    if months is None or months == ALL:
        participates = None
    elif isinstance(months, list) and months:
        participates = tuple(schedule.parse_month_name(m, f"{where} participates") for m in months)
    else:
        raise schedule.ScheduleConfigError(
            f"{where}: participates is {months!r} - write `all`, or a list of full month names "
            f"like [February, August].")
    grace = raw.get("grace")
    window = raw.get("claim_window")
    days_before = raw.get("days_before", 0)
    # A WHOLE NUMBER, never a duration or a string - "the evening before"
    # is one day before at that evening's time (REQ-PIPE-113 criterion 5).
    if isinstance(days_before, bool) or not isinstance(days_before, int) or days_before < 0:
        raise schedule.ScheduleConfigError(
            f"{where}: days_before is {days_before!r} - write a whole number of days, 0 or "
            f"more, like 1 for a supply due the evening before its period's date.")
    return ParticipationVersion(
        effective_from=schedule._as_date(raw.get("effective_from"), f"{where} effective_from"),
        participates=participates,
        reason=(str(raw["reason"]).strip() if raw.get("reason") else None),
        expected_time=(str(raw["expected_time"]) if raw.get("expected_time") is not None else None),
        grace=schedule.parse_duration(grace, f"{where} grace") if grace is not None else None,
        claim_window=(schedule.parse_duration(window, f"{where} claim_window")
                      if window is not None else None),
        changelog=_changelog(raw.get("changelog"), where),
        days_before=days_before,
        stated=stated)


def _own_dates(raw: dict, dataset_id: str):
    """A dataset's own authored dates as a calendar of its own, versioned like
    any calendar (criterion 25) - or None."""
    from qa_tools.common import schedule

    block = raw.get("dates")
    if not block:
        return None
    versions = []
    for i, version in enumerate(block.get("versions") or []):
        # A dataset's own dates borrow its calendar's claim window, so the
        # version carries none of its own; a zero placeholder keeps the one parser.
        versions.append(schedule._parse_version({**version, "claim_window": "0h"},
                                                f"dataset {dataset_id!r} dates", i))
    versions.sort(key=lambda v: v.effective_from)
    return schedule.Calendar(name=f"{dataset_id} (own dates)", description="",
                             versions=tuple(versions))


def load(path: Path = CALENDAR_YAML) -> Agreement:
    """Read one calendar.yaml into an `Agreement`. The one loader."""
    from qa_tools.common import schedule

    with open(path) as f:
        doc = config_yaml.parse(f) or {}
    calendars: dict = {}
    for raw in doc.get("calendars") or []:
        name = raw.get("name")
        if not name:
            raise schedule.ScheduleConfigError(f"{path}: a calendar has no `name:`")
        if name in calendars:
            raise schedule.ScheduleConfigError(f"{path}: calendar {name!r} is defined twice")
        calendars[name] = schedule.parse_calendar(raw)
    collections: dict = {}
    for c in doc.get("collections") or []:
        if c.get("id") in collections:
            raise schedule.ScheduleConfigError(
                f"{path}: collection {c.get('id')!r} is listed twice - the later entry would "
                f"silently decide its calendar.")
        collections[c.get("id")] = c.get("calendar")
    datasets: dict = {}
    for raw in doc.get("datasets") or []:
        ds = raw.get("id")
        where = f"dataset {ds!r}"
        if ds in datasets:
            raise schedule.ScheduleConfigError(
                f"{path}: {where} is listed twice - the later entry would silently decide its "
                f"due time.")
        versions = tuple(sorted(
            (_participation_version(v, f"{where} participation version {i + 1}")
             for i, v in enumerate(((raw.get("participation") or {}).get("versions")) or [])),
            key=lambda v: v.effective_from))
        not_expected = {}
        for entry in raw.get("not_expected") or []:
            name, reason = entry.get("period"), (entry.get("reason") or "").strip()
            if not name:
                raise schedule.ScheduleConfigError(f"{where} not_expected: an entry has no `period:`")
            if name in not_expected:
                raise schedule.ScheduleConfigError(
                    f"{where} not_expected: period {name!r} is listed twice.")
            if not reason:
                raise schedule.ScheduleConfigError(
                    f"{where} not_expected: period {name!r} has no `reason:`. A period with no "
                    f"supply and no reason is indistinguishable from one somebody forgot to "
                    f"configure.")
            not_expected[name] = reason
        datasets[ds] = DatasetAgreement(
            dataset_id=ds, calendar=raw.get("calendar"), no_calendar=raw.get("no_calendar"),
            participation=versions, not_expected=MappingProxyType(not_expected),
            own_dates=_own_dates(raw, ds))
    return Agreement(path=Path(path), calendars=MappingProxyType(calendars),
                     collections=MappingProxyType(collections),
                     datasets=MappingProxyType(datasets))


def current() -> Agreement:
    """The committed agreement, read once per process.

    Keyed by the path, so a test that points CALENDAR_YAML elsewhere gets
    that file and the committed one is not left shadowed afterwards."""
    return _load_once(CALENDAR_YAML)


@functools.lru_cache(maxsize=4)
def _load_once(path: Path) -> Agreement:
    return load(path)


current.cache_clear = _load_once.cache_clear


def cadence(dataset_id: str, agreement: Agreement | None = None) -> dict:
    """The dashboard's delivery-time label inputs for one dataset - the
    shape the builders embed as `sla.cadence` - from the agreement rather
    than the contract's retired slaProperties (REQ-PIPE-110 criterion 17).

    The calendar says the cycle - a daily rule, or the months and day its
    authored dates fall on - and the newest participation version says the
    expected time and grace. Which version applies on the date on show is
    REQ-DASH-182's; until then each dataset carries one.
    """
    from qa_tools.common import schedule

    agreement = agreement or current()
    cal = schedule.calendar(agreement.calendar_name_for(dataset_id), agreement)
    version = cal.current
    if version.is_cadence_rule:
        out: dict = {"type": version.cadence_rule}
    else:
        months = sorted({p.date.month for p in version.periods})
        days = {p.date.day for p in version.periods}
        out = {"type": "quarterly" if len(months) == 4 else "authored",
               "anchor_months": months, "day_of_month": days.pop() if len(days) == 1 else None}
    entry = agreement.dataset(dataset_id)
    if entry is None or not entry.participation:
        raise schedule.ScheduleConfigError(
            f"dataset {dataset_id!r} has no participation in contract/calendar.yaml, so it has "
            f"no delivery time to label.")
    newest = entry.participation[-1]
    out["expected_time"] = newest.expected_time
    out["latency_minutes"] = int(newest.grace.total_seconds() // 60)
    return out
