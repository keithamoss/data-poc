"""The data asset's own clock, resolved from one place (REQ-PIPE-048).

THREE RULES, and the third is the one that makes the other two safe:

1. ONE configuration value. `contract/data-asset.yaml`'s `timezone:`,
   an IANA name rather than an offset - an offset is one zone's answer
   for one moment, and a second asset in a daylight-saving jurisdiction
   needs a rule.

2. NO SILENT INTERPRETATION. `parse_instant()` raises on a value with
   no offset rather than guessing. Guessing is what produced the bug,
   and guessing UTC is not safer than guessing local - it is the same
   mistake with a different sign.

3. EVERY STORED INSTANT CARRIES ITS OWN OFFSET, so changing the value
   in (1) never retroactively reinterprets anything already written.
   Without that, editing one config line would silently move every
   timestamp this project has ever recorded - the same retroactivity
   problem effective-dating exists to solve elsewhere in this repo.

THE STAMP AND "TODAY" ARE ONE READING (REQ-PIPE-382, B1 SETTLED by Keith
2026-11-14): `now()` is what a record is stamped with and what "today" is
judged against. A replay replaces it, by installing a clock; nothing else
does. See "THE ONE CLOCK" below.

A DATE IS NOT AN INSTANT, and `end_of_day()` is where that gets
decided. A date means the whole of that day in the asset's own zone, so
as an instant it is that day's last moment - which is what a comparison
like "this run is on or before the as-of date" has always meant.
"""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from asset_model import assets, config_yaml, in_force


def data_asset_yaml() -> Path:
    """The selected asset's data-asset.yaml, resolved now (REQ-PIPE-342
    criterion 6; it was the import-time constant DATA_ASSET_YAML)."""
    return assets.selected().data_asset_yaml


class NaiveTimestampError(ValueError):
    """A timestamp with no UTC offset, where one was required.

    Always names where the value came from: the whole point of failing
    instead of guessing is that somebody can go and fix the source, and
    an error saying only that a timestamp was naive sends them looking.
    """


class NoTimezoneVersion(ValueError):
    """No timezone version covers the date or instant asked about
    (REQ-PIPE-112 criterion 7). Never answered with the newest or the
    oldest version instead: a guess about which clock applied is the
    thing versioning exists to stop."""


@dataclass(frozen=True)
class ZoneVersion:
    """One effective-dated timezone version (REQ-PIPE-112 criterion 1)."""

    effective_from: date
    zone: ZoneInfo

    @property
    def starts_at(self) -> datetime:
        """IN FORCE FROM THE START OF ITS OWN DAY IN ITS OWN ZONE
        (criterion 2), so every instant belongs to exactly one version."""
        return datetime.combine(self.effective_from, time.min, tzinfo=self.zone)


def parse_timezone_versions(doc: dict, where: str = "assets/<asset>/data-asset.yaml") -> tuple[ZoneVersion, ...]:
    """The asset's timezone versions from a parsed data-asset.yaml, oldest
    first. Refuses the old bare `timezone: <name>` form and a fixed UTC
    offset (criterion 1) rather than reading either."""
    block = doc.get("timezone")
    if not block:
        raise ValueError(
            f"{where} declares no `timezone:`. It is required - REQ-PIPE-048 removed every "
            f"hardcoded offset, so there is no fallback to fall back to.")
    if not isinstance(block, dict) or not isinstance(block.get("versions"), list):
        raise ValueError(
            f"{where}: `timezone:` must be effective-dated versions (REQ-PIPE-112) - "
            f"`timezone: {{versions: [{{effective_from: YYYY-MM-DD, zone: <IANA name>, "
            f"changelog: [...]}}]}}` - not a single value.")
    out = []
    for i, version in enumerate(block["versions"]):
        name = str((version or {}).get("zone") or "")
        if re.fullmatch(r"(?i)(utc|gmt)?\s*[+-]\d{1,2}(:?\d{2})?", name.strip()):
            raise ValueError(f"{where}: timezone version {i + 1} names {name!r}, a fixed UTC "
                             f"offset. Name an IANA zone, like 'Australia/Perth' - an offset is "
                             f"one zone's answer for one moment.")
        try:
            zone = ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"{where}: timezone {name!r} is not an IANA zone name "
                f"(expected something like 'Australia/Perth') - {exc}") from None
        out.append(ZoneVersion(date.fromisoformat(str(version.get("effective_from"))), zone))
    out.sort(key=lambda v: v.effective_from)
    return tuple(out)


_BUILT = config_yaml.Built()


def timezone_versions() -> tuple[ZoneVersion, ...]:
    """Every timezone version the asset carries, oldest first.

    Keyed on data-asset.yaml's content like the hierarchy next door
    (REQ-PIPE-254): read on every call, built again only when its text has
    changed. THERE IS NO BARE LOOKUP (criterion 6, NFR 2): every
    caller asks `zone_on(day)`, `zone_at(instant)` or `zone_now()`, so a
    caller that has not thought about 'as at when' cannot quietly get
    today's zone for a date in 2024.
    """
    path = data_asset_yaml()
    return _BUILT.from_file(path, lambda text: parse_timezone_versions(
        config_yaml.parse(text, name=str(path)) or {}, str(path)))


def zone_on(day: date, versions: tuple[ZoneVersion, ...] | None = None) -> ZoneInfo:
    """The zone in force ON a date - for reading a wall-clock time on that
    date as an instant (criterion 3).

    `versions`, here and on every function below that takes it, is a
    `timezone_versions()` the caller already holds: a caller asking about
    many instants takes it once and passes it down rather than reading the
    file for each (REQ-PIPE-254 criterion 19). Without it the file is read
    now."""
    return _zone_in_force(versions, day, lambda v: v.effective_from)


def _zone_in_force(versions, on, start) -> ZoneInfo:
    """The zone of the version in force `on`, each version starting at
    `start(version)`, or NoTimezoneVersion naming `on` and the earliest
    start."""
    versions = timezone_versions() if versions is None else versions
    found = in_force.version_on(versions, on, key=start)
    if found is None:
        raise NoTimezoneVersion(
            f"no timezone version covers {on.isoformat()} - the earliest starts "
            f"{start(versions[0]).isoformat()}. Not falling back to it.")
    return found.zone


def zone_at(instant: datetime, versions: tuple[ZoneVersion, ...] | None = None) -> ZoneInfo:
    """The zone in force AT an instant - for showing it, or reducing it to
    a date (criterion 4)."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise NaiveTimestampError(f"zone_at(): {instant!r} carries no UTC offset")
    return _zone_in_force(versions, instant, lambda v: v.starts_at)


def zone_now() -> ZoneInfo:
    """The zone in force now (criterion 5) - the real now. A synthetic
    replay's simulated now is an instant like any other: `zone_at` it."""
    return zone_at(datetime.now(UTC))


#: The one instant a synthetic asset's clock may be pinned to
#: (REQ-TEST-239 criterion 16, Keith 2026-10-16).
PINNED_NOW_VARIABLE = "MOTHMAN_PINNED_NOW"


class ClockRefused(RuntimeError):
    """The clock was asked to read anything but the wall clock on an asset
    that does not declare `synthetic: true` (REQ-PIPE-382 criterion 6)."""


class PinnedClockRefused(ClockRefused):
    """MOTHMAN_PINNED_NOW was set on an asset that is not synthetic."""


class ClockInstallRefused(ClockRefused):
    """A clock was installed on an asset that is not synthetic."""


def declared_synthetic() -> bool:
    """Whether the selected asset's data-asset.yaml declares it synthetic -
    THE ONE READER of `synthetic: true` (REQ-PIPE-382 criterion 7, #137 group
    D): the clock's refusal, the synthetic reset and the dashboard's footer all
    ask here, so three readers of one declaration cannot come to disagree."""
    raw = config_yaml.load(data_asset_yaml()) or {}
    return raw.get("synthetic") is True


# ---- THE ONE CLOCK (REQ-PIPE-382) --------------------------------------------
#
# ONE READING, AND ONLY A REPLAY REPLACES IT (criterion 2, B1 SETTLED by Keith
# 2026-11-14). Every reader of "now" - the instant stamped on a record and the
# "today" a slot or a due date is judged against - asks now() below, so during
# a replay every one of them reads the replay's instant and otherwise the wall
# clock. The single exception is when_effective(), which asks WHEN A DECISION
# TAKES EFFECT rather than what time it is.
#
# THE PIPELINE ONLY ANNOUNCES (criteria 8 and 9; QA SETTLED by Keith
# 2026-11-14): processing_arrival(), receiving() and taking_effect() say what
# happened - an arrival received at R is being processed, a delivery or file
# received at R is being staged or recorded, a decision takes effect at T -
# unconditionally and with no test of whether a replay is running. The wall
# clock and a pinned clock ignore every one of them; only an installed clock
# (the bootstrap's replay clock, REQ-GEN-381) acts on them. Nothing here knows a
# replay exists, so the real pipeline imports nothing of one.
#
# PROCESS-WIDE, NOT PER THREAD (NFR RELIABILITY): a run's four tools write from
# worker threads, which a context variable would not reach.


class Clock:
    """What the pipeline asks the time of, and announces events to. The base
    is the wall clock, which ignores every event."""

    def now(self) -> datetime:
        return real_now()

    @contextmanager
    def processing_arrival(self, received_at):  # noqa: ARG002 - ignored by design
        """An arrival received at `received_at` is being processed, for the span
        of the context (criterion 8)."""
        yield

    def receiving(self, received_at) -> None:
        """A delivery or file received at `received_at` is being staged or
        recorded (criterion 8). Ignored."""

    def taking_effect(self, instant) -> None:
        """A decision takes effect at `instant`, as it is recorded (criterion
        8). Ignored."""

    def when_effective(self, received_at, *, run_id: str, next_receipt=None,
                       claim_window=None) -> datetime:  # noqa: ARG002
        """When a decision on a supply received at `received_at` takes effect
        (criterion 3): now, the instant it is made, on every asset."""
        return self.now()


class WallClock(Clock):
    """The wall clock - what answers when nothing is installed (criterion 5)."""


class PinnedClock(Clock):
    """A clock pinned at one instant (criterion 12): MOTHMAN_PINNED_NOW."""

    def __init__(self, at: datetime):
        self.at = at

    def now(self) -> datetime:
        return self.at.astimezone(zone_at(self.at))


#: The clock installed for the span of a replay, or None (criterion 6).
_installed: Clock | None = None


def real_now() -> datetime:
    """The real wall-clock present, in the asset's zone - never pinned and
    never replayed. What a replay's 'never after the real present' cap reads
    (criterion 3); everything else asks now()."""
    return datetime.now(UTC).astimezone(zone_now())


def _refusal(what: str) -> str:
    return (f"{what}, and this data asset does not declare `synthetic: true` - a real "
            f"asset's clock is never pinned or replayed: its record of when something "
            f"happened is evidence, and is never invented")


def _admitted(clock: Clock, refused: type[ClockRefused], what: str) -> Clock:
    """THE ONE GATE every clock but the wall clock passes (criteria 6 and 12;
    Q6 and Q7 SETTLED by Keith 2026-11-02): refused unless the asset declares
    itself synthetic, here in asset_model/ so the refusal holds where the
    bootstrap package is absent."""
    if not declared_synthetic():
        raise refused(_refusal(what))
    return clock


def ambient() -> Clock:
    """The clock beneath any installed one: MOTHMAN_PINNED_NOW's pinned clock
    where it is set (through the same gate an installation passes), else the
    wall clock."""
    pinned = os.environ.get(PINNED_NOW_VARIABLE)
    if pinned:
        return _admitted(PinnedClock(parse_instant(pinned, PINNED_NOW_VARIABLE)),
                         PinnedClockRefused, f"{PINNED_NOW_VARIABLE} is set")
    return WallClock()


def current() -> Clock:
    """The clock in force: the installed one, else ambient()."""
    return _installed if _installed is not None else ambient()


@contextmanager
def installed(clock: Clock):
    """THE ONE INSTALLATION CALL (criterion 6): `clock` answers for the span of
    the context, refused unless the asset declares itself synthetic. The clock
    it replaces is restored after, so a replay inside a replay's span is one
    replay."""
    global _installed
    _admitted(clock, ClockInstallRefused, "a clock was installed")
    previous = _installed
    _installed = clock
    try:
        yield clock
    finally:
        _installed = previous


def now() -> datetime:
    """The current instant, in the asset's own zone as in force then.

    Aware, always. Nothing in this repo should call `datetime.now()`
    without a timezone, and nothing should call it with `timezone.utc`
    either - a UTC instant is correct but reads as a foreign wall clock
    to whoever opens the file.

    ONE CLOCK (REQ-PIPE-382): the installed clock during a replay, else the
    pinned instant where MOTHMAN_PINNED_NOW names one (REQ-TEST-239 criterion
    16 - a test, or a person demonstrating a synthetic asset, runs the real
    commands at a chosen moment; tests/test_cli_cp.py pins it this way), else
    the wall clock. Pinned or installed only on an asset declared synthetic.
    """
    return current().now()


def processing_arrival(received_at):
    """Announce: an arrival received at `received_at` is being processed, for
    the span of the returned context (criteria 8 and 10)."""
    return current().processing_arrival(received_at)


def receiving(received_at) -> None:
    """Announce: a delivery or file received at `received_at` is being staged
    or recorded (criterion 8)."""
    current().receiving(received_at)


def taking_effect(instant) -> None:
    """Announce: a decision takes effect at `instant`, as it is recorded
    (criterion 8)."""
    current().taking_effect(instant)


def when_effective(received_at, *, run_id: str, next_receipt=None,
                   claim_window=None) -> datetime:
    """THE ONE NEUTRAL QUESTION (criterion 3): a decision on a supply received
    at `received_at`, run id `run_id`, next receipt `next_receipt`, claim window
    `claim_window` - when does it take effect? The wall clock and a pinned
    clock answer now; an installed replay answers from its own rule."""
    return current().when_effective(received_at, run_id=run_id, next_receipt=next_receipt,
                                    claim_window=claim_window)


def _parse_iso(value, where: str) -> datetime:
    """`value` as a datetime - itself if it is one, else its ISO text, a
    space separator accepted - naive or aware as written."""
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace(" ", "T"))
    except ValueError as exc:
        raise ValueError(f"{where}: {text!r} is not an ISO timestamp - {exc}") from None


def parse_instant(value, where: str) -> datetime:
    """One stored value as an aware instant, or `NaiveTimestampError`.

    `value` may be a `datetime` (a DuckDB column, say) or an ISO string.
    A space separator is accepted because that is how DuckDB renders a
    timestamp; everything else about the format is left to
    `datetime.fromisoformat`, deliberately, rather than growing a parser
    of our own.

    `where` is the human answer to "and where did THAT come from" -
    a field name and its file, ideally.
    """
    parsed = _parse_iso(value, where)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        try:
            zone = zone_on(parsed.date()).key
        except (NoTimezoneVersion, ValueError):
            zone = "the asset's own zone"
        raise NaiveTimestampError(
            f"{where}: timestamp {value!r} carries no UTC offset. It is not "
            f"assumed to be UTC and it is not assumed to be "
            f"{zone} - REQ-PIPE-048 requires every stored "
            f"instant to say what offset it is in. Fix it at the source.")
    return parsed


def localise(value: datetime, versions: tuple[ZoneVersion, ...] | None = None) -> datetime:
    """An aware instant as the asset's own wall clock.

    The instant is unchanged - this only decides which clock it is read
    against, which is what makes a stored `+00:00` and a stored `+08:00`
    comparable without either being rewritten.
    """
    instant = parse_instant(value, "localise()")
    return instant.astimezone(zone_at(instant, versions))


def parse_hhmm(hhmm: str) -> tuple[int, int]:
    """"HH:MM" - a participation's expected time - as (hour, minute)."""
    hour, minute = (int(x) for x in hhmm.split(":"))
    return hour, minute


def wall_clock(day: date, hhmm: str) -> datetime:
    """A wall-clock time on a given day in the asset's zone, as an
    instant. `hhmm` is "HH:MM" - a participation's expected time.

    In the zone in force ON that day (REQ-PIPE-112 criterion 3). A time
    that does not exist that day, or exists twice, raises rather than
    being guessed - the schedule gate refuses such a configuration first
    (criterion 8), so reaching this is a configuration the gate never saw.
    """
    hour, minute = parse_hhmm(hhmm)
    zone = zone_on(day)
    problem = _wall_clock_problem(day, hour, minute, zone)
    if problem:
        raise ValueError(f"{hhmm} on {day.isoformat()} {problem} in "
                         f"{zone.key} - daylight saving; no instant is guessed")
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)


def wall_clock_problem(day: date, hhmm: str) -> str | None:
    """Why `hhmm` on `day` is not exactly one instant in the zone in force
    that day, or None (REQ-PIPE-112 criterion 8). Found by ROUND-TRIPPING
    the wall-clock time through the zone rather than by consulting
    offsets (decision 14): a time in a spring-forward gap does not come
    back as itself, and one in a fall-back overlap has two offsets."""
    hour, minute = parse_hhmm(hhmm)
    return _wall_clock_problem(day, hour, minute, zone_on(day))


def _wall_clock_problem(day: date, hour: int, minute: int, zone: ZoneInfo) -> str | None:
    first = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone, fold=0)
    second = first.replace(fold=1)
    back = first.astimezone(UTC).astimezone(zone)
    if (back.hour, back.minute, back.date()) != (hour, minute, day):
        return "does not exist (a daylight-saving gap)"
    if first.utcoffset() != second.utcoffset():
        return "occurs twice (a daylight-saving overlap)"
    return None


def start_of_day(day: date, versions: tuple[ZoneVersion, ...] | None = None) -> datetime:
    """The first instant of a date, in the zone in force on that date."""
    return datetime.combine(day, time.min, tzinfo=zone_on(day, versions))


def end_of_day(day: date, versions: tuple[ZoneVersion, ...] | None = None) -> datetime:
    """The last instant of a date, in the asset's zone.

    The meaning of a bare date used as a point in time (criterion 6).
    Implemented as "just before the next day starts" rather than as
    23:59:59.999999, so it stays exact rather than exact-to-a-
    microsecond, and so it is still right on a day that daylight saving
    makes 23 or 25 hours long.
    """
    return start_of_day(day + timedelta(days=1), versions) - timedelta(microseconds=1)


def local_date(value, versions: tuple[ZoneVersion, ...] | None = None) -> date:
    """The calendar date an instant falls on, ON THE ASSET'S CLOCK.

    The bridge between the supply model's receipt INSTANT and every
    consumer that legitimately wants a date - a warehouse partition, a
    cadence cycle, a row in a supply-history table. Reading the date off
    the string would answer in whatever zone it happens to be stored in,
    which for a 10pm Perth arrival stored as UTC is the following day -
    the exact bug REQ-PIPE-048 is named for, reintroduced one layer up.
    """
    return localise(parse_instant(value, "local_date()"), versions).date()


def isoformat(value: datetime) -> str:
    """One instant as the string this project stores.

    Aware instants only - storing a naive one is what criterion 3
    forbids, so this refuses rather than letting one through to disk
    where the loud failure would land on whoever reads it years later.
    """
    return parse_instant(value, "isoformat()").isoformat()


# The offset a supplier's own naked timestamp is recorded as carrying.
#
# THIS IS THE ONE PLACE AN ASSUMPTION IS ALLOWED, and it is allowed only
# because of where it sits. A source system's `extract_timestamp` column
# arrives with no offset - this project's synthetic feed included, whose
# arrival calibration is written in hours-from-midnight UTC (see
# generator/daily_batch.py's own comment). Somebody has to decide what
# that means before it can be compared with anything. It is decided once,
# at the boundary where a supplier's value becomes our stored record, and
# written into that record, so the next reader sees what was decided
# rather than inheriting it.
#
# Deliberately UTC and not the asset's own zone: changing it would move
# every arrival verdict in committed history, and criterion 5 says a
# stored instant keeps the meaning it was written with. This preserves
# today's meaning exactly - it only writes it down.
SOURCE_TIMESTAMP_OFFSET = UTC


def record_source_instant(value, where: str) -> str | None:
    """A source system's timestamp as a stored, self-describing instant.

    Returns None for a missing value, so a dataset with no rows stays
    distinguishable from one that arrived at midnight. An already-aware
    value is kept as it is - if a supplier ever does send an offset, it
    is theirs to state, not ours to overwrite.
    """
    if value is None or (not isinstance(value, datetime) and not str(value).strip()):
        return None
    parsed = _parse_iso(value, where)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=SOURCE_TIMESTAMP_OFFSET)
    return parsed.isoformat()


def arrival_key(received_at) -> str:
    """One arrival's instant, as a table-name segment.

    OUR OWN RECEIPT INSTANT, never a supplier's filename and never the
    delivery's name (REQ-PIPE-060's security decision): these become
    SQL identifiers, and DuckDB's parameter binding covers values, not
    identifiers. Everything that reaches a name here is either ours or
    a validated dataset id.

    Kept here rather than in supply_db because the committed-history
    readers need it and never import a database driver - and it is a pure
    function of an instant.
    """
    text = received_at if isinstance(received_at, str) else received_at.isoformat()
    return re.sub(r"[^0-9]", "", text)[:20] or "0"
