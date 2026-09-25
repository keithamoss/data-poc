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

import functools
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

DATA_ASSET_YAML = Path(__file__).resolve().parent.parent.parent / "contract" / "data-asset.yaml"


class NaiveTimestampError(ValueError):
    """A timestamp with no UTC offset, where one was required.

    Always names where the value came from: the whole point of failing
    instead of guessing is that somebody can go and fix the source, and
    an error saying only that a timestamp was naive sends them looking.
    """


@functools.lru_cache(maxsize=1)
def asset_timezone() -> ZoneInfo:
    """The asset's timezone, from the one configuration value.

    Cached like the hierarchy next door, and for the same reason: every
    consumer is a short-lived CLI or build process, and the file cannot
    change mid-run.
    """
    with open(DATA_ASSET_YAML) as f:
        doc = yaml.safe_load(f) or {}
    name = doc.get("timezone")
    if not name:
        raise ValueError(
            f"{DATA_ASSET_YAML} declares no `timezone:`. It is required - "
            f"REQ-PIPE-048 removed every hardcoded offset, so there is no "
            f"fallback to fall back to.")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"{DATA_ASSET_YAML}: timezone {name!r} is not an IANA zone name "
            f"(expected something like 'Australia/Perth') - {exc}") from None


def now() -> datetime:
    """The current instant, in the asset's own zone.

    Aware, always. Nothing in this repo should call `datetime.now()`
    without a timezone, and nothing should call it with `timezone.utc`
    either - a UTC instant is correct but reads as a foreign wall clock
    to whoever opens the file.
    """
    return datetime.now(asset_timezone())


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
        raise NaiveTimestampError(
            f"{where}: timestamp {value!r} carries no UTC offset. It is not "
            f"assumed to be UTC and it is not assumed to be "
            f"{asset_timezone().key} - REQ-PIPE-048 requires every stored "
            f"instant to say what offset it is in. Fix it at the source.")
    return parsed


def localise(value: datetime) -> datetime:
    """An aware instant as the asset's own wall clock.

    The instant is unchanged - this only decides which clock it is read
    against, which is what makes a stored `+00:00` and a stored `+08:00`
    comparable without either being rewritten.
    """
    return parse_instant(value, "localise()").astimezone(asset_timezone())


def wall_clock(day: date, hhmm: str) -> datetime:
    """A wall-clock time on a given day in the asset's zone, as an
    instant. `hhmm` is "HH:MM" - a contract's `expectedTime`.

    Replaces `expected_moment_utc()`'s subtract-a-fixed-offset
    arithmetic. Same answer today, and a correct one in a zone that
    observes daylight saving.
    """
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=asset_timezone())


def start_of_day(day: date) -> datetime:
    """The first instant of a date, in the asset's zone."""
    return datetime.combine(day, time.min, tzinfo=asset_timezone())


def end_of_day(day: date) -> datetime:
    """The last instant of a date, in the asset's zone.

    The meaning of a bare date used as a point in time (criterion 6).
    Implemented as "just before the next day starts" rather than as
    23:59:59.999999, so it stays exact rather than exact-to-a-
    microsecond, and so it is still right on a day that daylight saving
    makes 23 or 25 hours long.
    """
    return start_of_day(day + timedelta(days=1)) - timedelta(microseconds=1)


def as_of_instant(day: date) -> datetime:
    """A bare as-of DATE as the instant a comparison should use.

    A named alias for `end_of_day()`, because "runs on or before the
    as-of date" is the single most common comparison in this repo and
    reading `end_of_day` at the call site invites someone to wonder
    whether the boundary is inclusive. It is: the whole of that day
    counts.
    """
    return end_of_day(day)


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
