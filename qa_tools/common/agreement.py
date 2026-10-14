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
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path
from types import MappingProxyType

from qa_tools.common import config_yaml

CALENDAR_YAML = Path(__file__).resolve().parent.parent.parent / "contract" / "calendar.yaml"

#: The key a participation version uses to say which periods it owes.
PARTICIPATES = "participates"
#: `participates: all` - every period the calendar generates.
ALL = "all"
#: A value written as `inherit` - the value from the nearest level above on
#: each period's date (REQ-PIPE-181 criterion 5).
INHERIT = "inherit"
#: The participation values that resolve one at a time (REQ-PIPE-181
#: criterion 2). `reason` travels with `participates` rather than on its own.
VALUES = (PARTICIPATES, "expected_time", "grace", "claim_window", "days_before")
#: Where a resolved value came from.
DATASET, COLLECTION, FALLBACK = "dataset", "collection", "fallback"
#: What a dataset is on a date (REQ-PIPE-179 criterion 27).
NOT_YET_OWING, TURNED_OFF, OWING = "not yet owing", "turned off", "owing"


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
    #: The keys this version wrote, for the restate rule (criterion 33) - a
    #: key written as `inherit` counts as stated (REQ-PIPE-181 criterion 4).
    stated: frozenset[str] = frozenset()
    #: The keys this version wrote as `inherit` (REQ-PIPE-181 criterion 5).
    inherits: frozenset[str] = frozenset()
    #: ON A RESOLVED VERSION ONLY: {value: (level, that level's version's
    #: effective_from or None)} - where each value came from (REQ-PIPE-181
    #: criterion 13). Empty on a version as written.
    sources: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    #: The last day this version governs, inclusive, on the asset's clock -
    #: a turn-off (REQ-PIPE-179 criterion 1). Belongs to this version alone:
    #: never restated, never inherited (criterion 10).
    effective_to: date | None = None
    turned_off_reason: str | None = None
    #: The dates of this version's changelog entries carrying
    #: `turns_off: true`, oldest first (criteria 40 and 41).
    turns_off_logged: tuple[date, ...] = ()

    def off_after(self, on: date) -> bool:
        """Whether this version, as written, has stopped governing by `on`."""
        return self.effective_to is not None and self.effective_to < on

    def gives(self, key: str) -> bool:
        """Whether this version, as written, supplies `key` itself - stated
        and not `inherit`."""
        return key in self.stated and key not in self.inherits


@dataclass(frozen=True)
class TurnOff:
    """Why a dataset owes nothing on a date (REQ-PIPE-179 criterion 27)."""

    effective_to: date
    reason: str
    #: DATASET or COLLECTION - the level whose version stated it.
    level: str
    #: The effective_from of the version that states it.
    version_from: date
    #: The effective_from that ends the gap for this dataset, or None for good.
    until: date | None
    #: The newest changelog entry carrying turns_off: true (criterion 41);
    #: a declared correction's date, where there is one, is the freeze's.
    authored_on: date | None


@dataclass(frozen=True)
class Standing:
    """What a dataset is on a date - THE ONE ANSWER every consumer of
    participation reads (REQ-PIPE-179 criterion 27): not yet owing; turned
    off, with why and the last applying version's resolved timing; or
    owing, with the values REQ-PIPE-181 resolves for the date."""

    state: str
    #: The resolved values - for TURNED_OFF, those in force on its last day
    #: on ('when last on', criterion 29); None while not yet owing.
    values: "ParticipationVersion | None"
    turned_off: TurnOff | None = None
    #: OWING inside its collection's turned-off gap by a version of its own
    #: (criterion 28's 'its own version brought it back').
    brought_back: bool = False

    @property
    def owes(self) -> bool:
        return self.state == OWING


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
    #: collection id -> its participation_defaults versions, oldest first
    #: (REQ-PIPE-181 criterion 1).
    defaults: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

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

    def collection_of(self, dataset_id: str) -> str | None:
        from qa_tools.common import hierarchy

        try:
            return hierarchy.dataset(dataset_id).collection_id
        except hierarchy.UnknownDatasetError:
            return None

    def defaults_for(self, dataset_id: str) -> tuple[ParticipationVersion, ...]:
        """The collection defaults a dataset may take values from - none
        where it names a calendar other than its collection's, whose months
        and windows were written for another calendar (REQ-PIPE-181
        criterion 9; the gate refuses the configuration that would rely
        on them)."""
        collection = self.collection_of(dataset_id)
        own = self.dataset(dataset_id)
        if own is not None and own.calendar and own.calendar != self.collections.get(collection):
            return ()
        return self.defaults.get(collection, ())

    def participation_on(self, dataset_id: str, on: date) -> ParticipationVersion | None:
        """The participation in force on a date, each value RESOLVED from the
        dataset or its collection (REQ-PIPE-181 criterion 2) - or None where
        the dataset's first version has not begun: NOT YET OWING
        (REQ-PIPE-110 criterion 30, REQ-PIPE-181 criterion 3).

        THE VALUES ONLY, never whether the dataset owes (REQ-PIPE-179): on a
        turned-off date these are its last applying version's timing, which
        is what a slot's inputs read; `standing_on` is what says it owes."""
        return self.standing_on(dataset_id, on).values

    def ever_turned_off(self, dataset_id: str) -> bool:
        """Whether any version this dataset reads states an effective_to - a
        cheap first question, so the thirty datasets never turned off pay
        nothing for the ones that are (the requirement's performance NFR)."""
        entry = self.dataset(dataset_id)
        if entry is None:
            return False
        return any(v.effective_to is not None
                   for v in entry.participation + self.defaults_for(dataset_id))

    def timing_on(self, dataset_id: str, on: date) -> ParticipationVersion | None:
        """The values a period's slot inputs take AS IF EVERY effective_to WERE
        ABSENT (REQ-PIPE-179 criterion 14) - what a period inside a turned-off
        gap would have had, which is when the last owed slot before the gap
        closes. Never says whether the dataset owes; None while not yet
        owing."""
        entry = self.dataset(dataset_id)
        if entry is None:
            return None
        return resolve(entry.participation, self.defaults_for(dataset_id), on,
                       ignore_turn_offs=True)

    def standing_on(self, dataset_id: str, on: date) -> Standing:
        """THE ONE HELPER (REQ-PIPE-179 criterion 27): not yet owing, turned
        off (criteria 3, 5 and 6), or owing with its resolved values.

        A DATASET'S OWN TURN-OFF FIRST: its latest version starting on or
        before the date ends before it. Then ITS COLLECTION'S, unless a
        version of its own begins inside the collection's gap - which brings
        that dataset alone back (criterion 6). A later collection version
        never ends a dataset's own turn-off, because only the dataset's own
        latest version is read for it."""
        from qa_tools.common import in_force

        entry = self.dataset(dataset_id)
        if entry is None:
            return Standing(NOT_YET_OWING, None)
        own = entry.participation
        defaults = self.defaults_for(dataset_id)
        mine = in_force.version_on(own, on)
        if mine is None:
            return Standing(NOT_YET_OWING, None)
        if mine.off_after(on):
            return Standing(TURNED_OFF, resolve(own, defaults, mine.effective_to),
                            _turn_off(mine, DATASET, own))
        above = in_force.version_on(defaults, on) if defaults else None
        if above is not None and above.effective_to is not None:
            if above.off_after(on) and mine.effective_from <= above.effective_to:
                return Standing(TURNED_OFF, resolve(own, defaults, above.effective_to),
                                _turn_off(above, COLLECTION, defaults, own))
            if above.off_after(on):
                return Standing(OWING, resolve(own, defaults, on), brought_back=True)
        return Standing(OWING, resolve(own, defaults, on))

    def resolved_versions(self, dataset_id: str) -> tuple[ParticipationVersion, ...]:
        """The resolved participation at every date any of it changes - the
        dataset's own versions and every later collection version - for the
        consumers that ask about all of a dataset's history at once (the
        widest window, the largest days before, the earliest due time)."""
        entry = self.dataset(dataset_id)
        if entry is None or not entry.participation:
            return ()
        first = entry.participation[0].effective_from
        dates = sorted({v.effective_from for v in entry.participation}
                       | {v.effective_from for v in self.defaults_for(dataset_id)
                          if v.effective_from > first})
        return tuple(r for d in dates
                     if (r := self.participation_on(dataset_id, d)) is not None)


def describe_source(source: tuple, *, collection_name: str | None = None,
                    calendar_name: str | None = None, key: str | None = None) -> str:
    """Where a resolved value came from, in words that name the level
    (REQ-PIPE-181 criterion 15) - phrased as amber_setting.describe phrases
    a setting's provenance, and never 'inherited', which names a period
    standing on an earlier period's supply (REQ-PIPE-098)."""
    level, since = source
    when = f", since {since.day} {since.strftime('%b %Y')}" if since else ""
    if level == DATASET:
        return f"set for this dataset{when}"
    if level == COLLECTION:
        return f"set for {collection_name or 'its collection'}{when}"
    if key == "claim_window" and calendar_name:
        return f"from the {calendar_name} calendar{when}"
    return "no level states this"


def resolve(own: tuple[ParticipationVersion, ...], defaults: tuple[ParticipationVersion, ...],
            on: date, *, ignore_turn_offs: bool = False) -> ParticipationVersion | None:
    """THE ONE RESOLUTION FUNCTION (REQ-PIPE-181's second NFR): each value
    separately, on the date - from the dataset's version in force where it
    states it, else from the collection's version in force where that
    states it, else the fallback (REQ-PIPE-110 criterion 6: every period,
    no days before, the calendar's claim window, and no due time or grace -
    which the gate refuses). None before the dataset's first version: a
    dataset not yet owing never takes a value from its collection
    (criterion 3).

    PER VALUE, NOT PER SETTING (the delivery-architect's decision): a
    collection version in force says nothing about a dataset that has not
    started, so only values fall through, one at a time. `reason` travels
    with `participates` from whichever level gave the months (criterion
    18), so a list is never read without its reason."""
    from qa_tools.common import in_force

    mine = in_force.version_on(own, on)
    if mine is None:
        return None
    above = in_force.version_on(defaults, on) if defaults else None
    if above is not None and above.off_after(on) and not ignore_turn_offs:
        # WHILE A COLLECTION IS TURNED OFF it gives no value to anybody
        # (REQ-PIPE-179 criterion 7): a dataset back on states its own.
        above = None
    picked: dict = {}
    sources: dict = {}
    for key in VALUES:
        if mine.gives(key):
            picked[key], sources[key] = getattr(mine, key), (DATASET, mine.effective_from)
        elif above is not None and above.gives(key):
            picked[key], sources[key] = getattr(above, key), (COLLECTION, above.effective_from)
        else:
            picked[key] = 0 if key == "days_before" else None
            sources[key] = (FALLBACK, None)
    level = sources[PARTICIPATES][0]
    reason = (mine.reason if level == DATASET else above.reason if level == COLLECTION else None)
    return replace(mine, participates=picked[PARTICIPATES], reason=reason,
                   expected_time=picked["expected_time"], grace=picked["grace"],
                   claim_window=picked["claim_window"], days_before=picked["days_before"],
                   sources=MappingProxyType(sources))


def _turn_off(version: ParticipationVersion, level: str,
              versions: tuple[ParticipationVersion, ...],
              own: tuple[ParticipationVersion, ...] = ()) -> TurnOff:
    """A version's turn-off, with what ends it: the next version at the same
    level - or, for a collection's, the dataset's own version brought back
    inside it, whichever comes first."""
    later = [v.effective_from for v in versions if v.effective_from > version.effective_from]
    later += [v.effective_from for v in own if v.effective_from > version.effective_to]
    return TurnOff(effective_to=version.effective_to, reason=version.turned_off_reason or "",
                   level=level, version_from=version.effective_from,
                   until=min(later) if later else None,
                   authored_on=version.turns_off_logged[-1] if version.turns_off_logged else None)


def _turns_off_logged(raw) -> tuple[date, ...]:
    """The dates of the changelog entries carrying `turns_off: true`, oldest
    first - criterion 41's 'newest' is the last. The gate refuses any other
    value, so only the literal True counts here."""
    out = []
    for entry in raw or []:
        if isinstance(entry, dict) and entry.get("turns_off") is True:
            try:
                out.append(date.fromisoformat(str(entry.get("date"))))
            except ValueError:
                continue
    return tuple(sorted(out))


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
    # A TURN-OFF (REQ-PIPE-179 criterion 1). The gate refuses one half
    # without the other (criterion 2) and `inherit` for either (criterion
    # 10). A value that is not a date FAILS LOUD here (the requirement's
    # NFR): read as absent, it would be a dataset silently owing again.
    effective_to = (schedule._as_date(raw.get("effective_to"), f"{where} effective_to")
                    if raw.get("effective_to") is not None else None)
    inherits = frozenset(k for k in VALUES if raw.get(k) == INHERIT)
    raw = {k: v for k, v in raw.items() if k not in inherits}
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
        stated=stated, inherits=inherits,
        effective_to=effective_to,
        turned_off_reason=(str(raw["turned_off_reason"]).strip()
                           if raw.get("turned_off_reason") else None),
        turns_off_logged=_turns_off_logged(raw.get("changelog")))


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

    with open(path) as f:
        doc = config_yaml.parse(f) or {}
    return from_doc(doc, path)


def from_doc(doc: dict, path: Path | str = "contract/calendar.yaml") -> Agreement:
    """An `Agreement` from an already-parsed calendar.yaml document - what
    REQ-PIPE-111's freeze gate needs for the file as it stood at an earlier
    commit, which is text from git rather than a path."""
    from qa_tools.common import schedule

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
    defaults: dict = {}
    for c in doc.get("collections") or []:
        where = f"collection {c.get('id')!r} participation_defaults"
        defaults[c.get("id")] = tuple(sorted(
            (_participation_version(v, f"{where} version {i + 1}")
             for i, v in enumerate(((c.get("participation_defaults") or {}).get("versions")) or [])),
            key=lambda v: v.effective_from))
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
                     datasets=MappingProxyType(datasets),
                     defaults=MappingProxyType({k: v for k, v in defaults.items() if v}))


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
    # RESOLVED (REQ-PIPE-181): a value the collection states is this
    # dataset's as much as one it states itself.
    newest = agreement.resolved_versions(dataset_id)[-1]
    out["expected_time"] = newest.expected_time
    out["latency_minutes"] = int(newest.grace.total_seconds() // 60)
    # A FOLLOWING-PERIOD DATASET (REQ-PIPE-167) is due days before each
    # period's date; without this the label names the period's date as
    # the delivery time (post-build-review #142). Only where it is not 0.
    if newest.days_before:
        out["days_before"] = newest.days_before
    return out
