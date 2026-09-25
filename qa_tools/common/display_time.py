"""The one way this project writes a date or a time for a person to read
(REQ-DASH-071, signed off 2026-09-25).

WHY THIS EXISTS. Every date on the dashboard rendered in the VIEWER's
timezone, not the asset's, so for any reader west of UTC the displayed
date was a day early - silently. Two render sites disagreed about the
same instant: one character-sliced the wall clock out of a stored string
and appended " UTC" unconditionally, the other emitted the stored string
RAW into a user-facing timing column, microseconds and offset included.
A reader comparing an SLA tile reading "by 14:00 AWST" with an arrival
tile reading "05:29 UTC" had to add eight hours in their head, across
two tiles, to judge a verdict sitting in the same cell.

THE FORMAT IS ONE STRING WITH AN OPTIONAL TIME IN FRONT OF IT, not two
formats. Keith's two dictated examples disagreed on the comma, and the
cheapest way to settle that is not to pick a winner but to stop having
two strings - so there is no rule about when the comma appears, because
it always does, in the same place.

NO TIMEZONE LABEL, because there is only one: everything a person reads
is on the asset's own clock. That is criterion 6, and it is the
substantive answer to the whole question rather than a styling choice -
a label would imply there is a second zone to distinguish it from.

THIS CHANGES NOTHING ABOUT STORAGE (criterion 10). Every stored instant
keeps its ISO-8601 form and its own offset: `qa_results/` is a permanent
machine-read history, REQ-PIPE-048 exists to make those offsets
explicit, and rewriting what is written would break the lot. This module
is the last transform before a human eye and nothing else.

ITS TWIN IS IN THE BROWSER, and the two are held to the same committed
table - `display-time-cases.json`, read by `tests/test_display_time.py`
and `tests-js/display-time.test.js`. Neither suite owns it, so neither
side can bend a case to whatever it already does. Same shape as
`status-cases.json` and for the same reason: two implementations of one
rule drifted once already and the drift rendered a check with 14 real
violations green.
"""
from __future__ import annotations

from datetime import date, datetime

from qa_tools.common import asset_time

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _localised(value) -> datetime:
    """The instant, on the asset's clock.

    REFUSES A NAIVE INSTANT rather than assuming one. An instant with no
    offset could be anything, and guessing is exactly how a date lands
    on the wrong day - which is the bug this module exists to end.
    `asset_time.parse_instant` already raises for one, so this leans on
    it rather than writing a second rule.
    """
    if isinstance(value, datetime):
        return asset_time.localise(asset_time.parse_instant(value, "display_time"))
    return asset_time.localise(
        asset_time.parse_instant(datetime.fromisoformat(str(value)), "display_time"))


def format_day(value) -> str:
    """`Tuesday, 29 September 2026` - a date, on the asset's clock.

    Accepts an instant or a plain date. A plain date has no zone to
    resolve and is rendered as written; an instant is localised first,
    because 6:30pm UTC is the NEXT DAY in Perth and that difference is
    the whole point.
    """
    when = value if isinstance(value, date) and not isinstance(value, datetime) \
        else _localised(value).date()
    return (f"{_WEEKDAYS[when.weekday()]}, {when.day} "
            f"{_MONTHS[when.month - 1]} {when.year}")


def format_instant(value) -> str:
    """`2:15pm Tuesday, 29 September 2026` - the time, prefixed onto the
    same date string.

    Lowercase am/pm with no full stops, no leading zero on the hour, and
    the minutes always shown even on the hour - that last one is about
    alignment rather than taste: a column where some times carry minutes
    and some do not does not line up.
    """
    when = _localised(value)
    hour = when.hour % 12 or 12          # 0 and 12 both read as 12
    meridiem = "am" if when.hour < 12 else "pm"
    return f"{hour}:{when.minute:02d}{meridiem} {format_day(when)}"


#: (seconds in the unit, singular name). Months and years are averaged
#: deliberately - a relative string is a rough answer to a rough
#: question, and a calendar-exact "2 months ago" would still be rounded
#: to the same words.
#:
#: A YEAR IS TWELVE MONTHS HERE, not 365 days, and that is deliberate:
#: with a 30-day month and a 365-day year there is a five-day window
#: where this prints "12 months ago", which Keith ruled out on
#: 2026-09-24. Making the year the month's own multiple removes the
#: window rather than special-casing it.
_MONTH = 2_592_000                       # 30 days
_UNITS = (
    (_MONTH * 12, "year"),
    (_MONTH, "month"),
    (604_800, "week"),
    (86_400, "day"),
    (3_600, "hour"),
    (60, "minute"),
)


def format_relative(value, now) -> str:
    """`3 weeks ago`, `in 2 days` - both directions, scaling by unit.

    NEVER FALLS BACK TO AN ABSOLUTE DATE at any threshold, which its
    browser twin used to do at 30 days. A caller that wants an absolute
    date asks for one.

    `now` is REQUIRED and has no default, which is the point rather than
    an inconvenience: the dashboard is routinely read as of a past or
    future date, and a relative string measured against the real clock
    while the page is showing 2027 is not merely unhelpful, it is false.
    Making the caller name its own reference is what stops that being
    forgotten (criterion 12).
    """
    delta = (_localised(value) - _localised(now)).total_seconds()
    seconds = abs(delta)
    if seconds < 45:
        return "just now"
    for size, name in _UNITS:
        if seconds >= size:
            n = int(seconds // size)
            unit = name if n == 1 else name + "s"
            return f"in {n} {unit}" if delta > 0 else f"{n} {unit} ago"
    return "just now"
