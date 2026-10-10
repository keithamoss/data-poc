"""The data asset's own clock, resolved from one place (REQ-PIPE-048).

WHAT THIS REPLACES. Until 2026-09-23 the asset's timezone was a
hardcoded `AWST_OFFSET = timedelta(hours=8)` in `pipeline/cadence.py`,
and every wall-clock computation in the repo leaned on it - a comment
saying "WA doesn't observe daylight saving" doing the work a
configuration value should. Separately, `classify_arrival()` took any
timestamp without an offset and silently treated it as UTC. Its own
docstring admitted this. That is the bug this requirement is named for:
a supply that arrived at 10pm in Perth read as having arrived the
following afternoon.

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

A DATE IS NOT AN INSTANT, and `end_of_day()` is where that gets
decided. A date means the whole of that day in the asset's own zone, so
as an instant it is that day's last moment - which is what a comparison
like "this run is on or before the as-of date" has always meant. It was
previously true by coincidence, from comparing ISO date STRINGS
lexicographically, and coincidence is a poor thing to build the next
five requirements' comparisons on.
"""
from __future__ import annotations

import re

import functools
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from qa_tools.common import config_yaml

DATA_ASSET_YAML = Path(__file__).resolve().parent.parent.parent / "contract" / "data-asset.yaml"


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


def parse_timezone_versions(doc: dict, where: str = "contract/data-asset.yaml") -> tuple[ZoneVersion, ...]:
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


@functools.lru_cache(maxsize=1)
def timezone_versions() -> tuple[ZoneVersion, ...]:
    """Every timezone version the asset carries, oldest first.

    Cached like the hierarchy next door, and for the same reason: every
    consumer is a short-lived CLI or build process, and the file cannot
    change mid-run. THERE IS NO BARE LOOKUP (criterion 6, NFR 2): every
    caller asks `zone_on(day)`, `zone_at(instant)` or `zone_now()`, so a
    caller that has not thought about 'as at when' cannot quietly get
    today's zone for a date in 2024.
    """
    with open(DATA_ASSET_YAML) as f:
        doc = config_yaml.parse(f) or {}
    return parse_timezone_versions(doc, str(DATA_ASSET_YAML))


def zone_on(day: date) -> ZoneInfo:
    """The zone in force ON a date - for reading a wall-clock time on that
    date as an instant (criterion 3)."""
    from qa_tools.common import in_force

    found = in_force.version_on(timezone_versions(), day)
    if found is None:
        raise NoTimezoneVersion(
            f"no timezone version covers {day.isoformat()} - the earliest starts "
            f"{timezone_versions()[0].effective_from.isoformat()}. Not falling back to it.")
    return found.zone


def zone_at(instant: datetime) -> ZoneInfo:
    """The zone in force AT an instant - for showing it, or reducing it to
    a date (criterion 4)."""
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise NaiveTimestampError(f"zone_at(): {instant!r} carries no UTC offset")
    from qa_tools.common import in_force

    found = in_force.version_on(timezone_versions(), instant, key=lambda v: v.starts_at)
    if found is None:
        raise NoTimezoneVersion(
            f"no timezone version covers {instant.isoformat()} - the earliest starts "
            f"{timezone_versions()[0].starts_at.isoformat()}. Not falling back to it.")
    return found.zone


def zone_now() -> ZoneInfo:
    """The zone in force now (criterion 5) - the real now. A synthetic
    replay's simulated now is an instant like any other: `zone_at` it."""
    return zone_at(datetime.now(UTC))


def now() -> datetime:
    """The current instant, in the asset's own zone as in force now.

    Aware, always. Nothing in this repo should call `datetime.now()`
    without a timezone, and nothing should call it with `timezone.utc`
    either - a UTC instant is correct but reads as a foreign wall clock
    to whoever opens the file.
    """
    return datetime.now(UTC).astimezone(zone_now())


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
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace(" ", "T"))
        except ValueError as exc:
            raise ValueError(f"{where}: {text!r} is not an ISO timestamp - {exc}") from None
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


def localise(value: datetime) -> datetime:
    """An aware instant as the asset's own wall clock.

    The instant is unchanged - this only decides which clock it is read
    against, which is what makes a stored `+00:00` and a stored `+08:00`
    comparable without either being rewritten.
    """
    instant = parse_instant(value, "localise()")
    return instant.astimezone(zone_at(instant))


def wall_clock(day: date, hhmm: str) -> datetime:
    """A wall-clock time on a given day in the asset's zone, as an
    instant. `hhmm` is "HH:MM" - a contract's `expectedTime`.

    Replaces `expected_moment_utc()`'s subtract-a-fixed-offset
    arithmetic. Same answer today, and a correct one in a zone that
    observes daylight saving.

    In the zone in force ON that day (REQ-PIPE-112 criterion 3). A time
    that does not exist that day, or exists twice, raises rather than
    being guessed - the schedule gate refuses such a configuration first
    (criterion 8), so reaching this is a configuration the gate never saw.
    """
    problem = wall_clock_problem(day, hhmm)
    if problem:
        raise ValueError(f"{hhmm} on {day.isoformat()} {problem} in "
                         f"{zone_on(day).key} - daylight saving; no instant is guessed")
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone_on(day))


def wall_clock_problem(day: date, hhmm: str) -> str | None:
    """Why `hhmm` on `day` is not exactly one instant in the zone in force
    that day, or None (REQ-PIPE-112 criterion 8). Found by ROUND-TRIPPING
    the wall-clock time through the zone rather than by consulting
    offsets (decision 14): a time in a spring-forward gap does not come
    back as itself, and one in a fall-back overlap has two offsets."""
    hour, minute = (int(x) for x in hhmm.split(":"))
    zone = zone_on(day)
    first = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone, fold=0)
    second = first.replace(fold=1)
    back = first.astimezone(UTC).astimezone(zone)
    if (back.hour, back.minute, back.date()) != (hour, minute, day):
        return "does not exist (a daylight-saving gap)"
    if first.utcoffset() != second.utcoffset():
        return "occurs twice (a daylight-saving overlap)"
    return None


def start_of_day(day: date) -> datetime:
    """The first instant of a date, in the zone in force on that date."""
    return datetime.combine(day, time.min, tzinfo=zone_on(day))


def end_of_day(day: date) -> datetime:
    """The last instant of a date, in the asset's zone.

    The meaning of a bare date used as a point in time (criterion 6).
    Implemented as "just before the next day starts" rather than as
    23:59:59.999999, so it stays exact rather than exact-to-a-
    microsecond, and so it is still right on a day that daylight saving
    makes 23 or 25 hours long.
    """
    return start_of_day(day + timedelta(days=1)) - timedelta(microseconds=1)


def local_date(value) -> date:
    """The calendar date an instant falls on, ON THE ASSET'S CLOCK.

    The bridge between the supply model's receipt INSTANT and every
    consumer that legitimately wants a date - a warehouse partition, a
    cadence cycle, a row in a supply-history table. Reading the date off
    the string would answer in whatever zone it happens to be stored in,
    which for a 10pm Perth arrival stored as UTC is the following day -
    the exact bug REQ-PIPE-048 is named for, reintroduced one layer up.
    """
    return localise(parse_instant(value, "local_date()")).date()


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
# that means before it can be compared with anything.
#
# The bug REQ-PIPE-048 fixes was not that an assumption existed. It was
# that the assumption was made INVISIBLY, at every read, forever -
# classify_arrival() quietly attached UTC to whatever it was handed, so
# no record existed of a decision having been taken at all. Making it
# once, at the boundary where a supplier's value becomes our stored
# record, and writing the offset into that record permanently, is a
# different thing: the next reader sees what was decided rather than
# inheriting it.
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
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace(" ", "T"))
        except ValueError as exc:
            raise ValueError(f"{where}: {text!r} is not an ISO timestamp - {exc}") from None
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
    """
    text = received_at if isinstance(received_at, str) else received_at.isoformat()
    return re.sub(r"[^0-9]", "", text)[:20] or "0"


# Kept HERE rather than in supply_db, where it started, because the
# committed-history readers need it and may never import duckdb - the
# standing rule that CI and any read-committed-history path never
# depends on live data access. It is a pure function of an instant, so
# this is also simply where it belongs.
