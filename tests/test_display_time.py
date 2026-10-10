"""The Python half of the shared display-time table (REQ-DASH-071).

Every case comes from display-time-cases.json at the repo root, which
neither this suite nor tests-js/display-time.test.js owns. That is the
point: a table either side could edit is a table either side can
quietly bend to whatever it already does.

Same shape as status-cases.json and for the same reason - two
implementations of one rule drifted once already (plans/qa-pipeline.md
item 74) and the drift rendered a check with 14 real violations green.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_tools.common import display_time
from qa_tools.common.display_time import format_day, format_instant, format_relative

CASES = json.loads((Path(__file__).resolve().parent.parent
                    / "display-time-cases.json").read_text())


def _ids(cases):
    return [c["id"] for c in cases]


class TestEveryDayCase:
    @pytest.mark.parametrize("case", CASES["day_cases"], ids=_ids(CASES["day_cases"]))
    def test_it_reads_the_way_the_table_says(self, case):
        assert format_day(case["at"]) == case["expect"], case["why"]


class TestEveryInstantCase:
    @pytest.mark.parametrize("case", CASES["instant_cases"], ids=_ids(CASES["instant_cases"]))
    def test_it_reads_the_way_the_table_says(self, case):
        assert format_instant(case["at"]) == case["expect"], case["why"]


class TestEveryRelativeCase:
    _REL = [c for c in CASES["relative_cases"] if "id" in c]

    @pytest.mark.parametrize("case", _REL, ids=_ids(_REL))
    def test_it_reads_the_way_the_table_says(self, case):
        assert format_relative(case["from"], case["at"]) == case["expect"]


class TestItNeverEmitsSomethingUnreadable:
    """Criterion 7 - no raw ISO anywhere a person can see one."""

    def test_no_formatter_output_looks_like_an_iso_timestamp(self):
        """Matched as a PATTERN, not by banning characters - the first
        draft of this asserted "T" was absent and failed on Tuesday."""
        import re

        iso = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}|[+-]\d{2}:\d{2}")
        for case in CASES["day_cases"]:
            out = format_day(case["at"])
            assert not iso.search(out), out
        for case in CASES["instant_cases"]:
            out = format_instant(case["at"])
            assert not iso.search(out), out

    def test_it_refuses_a_naive_instant_rather_than_guessing_its_zone(self):
        """An instant with no offset could be anything, and guessing is
        how a date lands on the wrong day."""
        with pytest.raises(Exception):
            format_instant("2026-09-29T14:15:00")


class TestThereIsOnlyOneOfIt:
    """Criterion 9. The standard is worth exactly as much as the number
    of implementations of it: two drifted once already on this project
    (plans/qa-pipeline.md item 74) and the drift rendered a check with
    14 real violations green.

    So this is a real gate rather than a convention - a second formatter
    growing anywhere is what it is looking for, and the file it grew in
    is what it names.
    """

    ROOT = Path(__file__).resolve().parent.parent

    #: The browser's own date formatters. Every one of them takes a
    #: locale and renders on the READER's clock unless handed a
    #: timeZone, which is the bug this requirement ends.
    #:
    #: toLocaleString is deliberately NOT here: on a Number it is this
    #: page's thousands separator (fmtInt), which is a different job and
    #: a legitimate one. Naming it would make this gate cry wolf, and a
    #: gate that cries wolf gets an exemption list and then gets ignored.
    BROWSER_FORMATTERS = ("toLocaleDateString", "toLocaleTimeString",
                          "toDateString", "toTimeString")

    def test_the_template_formats_dates_in_exactly_one_place(self):
        html = (self.ROOT / "dashboard" / "qa-reporting-dashboard.template.html").read_text()
        # Comments are the one legitimate home for these names - several
        # explain what they replaced - so only real code counts.
        code = [ln for ln in html.splitlines()
                if not ln.lstrip().startswith(("//", "*", "/*"))]
        for name in self.BROWSER_FORMATTERS:
            hits = [ln.strip() for ln in code if name + "(" in ln]
            assert not hits, (
                f"{name}() is back in the dashboard template - every user-facing "
                f"date goes through fmtDay/fmtInstant/fmtRelative (REQ-DASH-071 "
                f"criterion 9): {hits[:3]}")

    def test_intl_is_only_reached_for_through_the_one_formatter(self):
        """Intl.DateTimeFormat is the right primitive and assetParts()
        uses it - but a second caller is a second implementation, which
        is the thing being prevented."""
        html = (self.ROOT / "dashboard" / "qa-reporting-dashboard.template.html").read_text()
        code = [ln for ln in html.splitlines()
                if not ln.lstrip().startswith(("//", "*", "/*"))]
        hits = [ln.strip() for ln in code if "Intl.DateTimeFormat" in ln]
        assert len(hits) == 2, (
            "Intl.DateTimeFormat should appear exactly twice - once in "
            "zoneVersions() to validate each zone, once in assetParts() "
            f"to read it. Found {len(hits)}: {hits}")


class TestAPeriodNameWrittenForAPerson:
    """format_period(), added 2026-09-28 after the real dashboard showed
    "Birth Registrations has no supply for 2026-08-27" seventeen times on
    one page.

    A period NAME is an identifier, which is why it took a promotion
    landing to notice: it only becomes a problem when it reaches a
    reader as prose, and nothing put one in prose until the outstanding
    queue's closed-slot items became reachable.
    """

    def test_a_quarterly_name_is_already_how_somebody_says_it(self):
        assert display_time.format_period("2023-Q1") == "2023-Q1"

    def test_a_daily_name_is_a_date_and_is_written_as_one(self):
        assert display_time.format_period("2026-08-27") == "Thursday, 27 August 2026"

    def test_it_agrees_with_format_day(self):
        from datetime import date
        assert display_time.format_period("2026-08-27") == format_day(date(2026, 8, 27))

    def test_a_name_it_does_not_recognise_comes_back_as_it_is(self):
        """A calendar may name its periods anything its agency agreed,
        and guessing at a shape nobody declared is how a display
        standard starts mangling real names."""
        for name in ("Nov-Jan window", "FY2026", "2026-W35", ""):
            assert display_time.format_period(name) == name

    def test_it_does_not_reach_for_a_zone(self):
        """A period name has no instant in it, so there is nothing to
        localise - and treating it as one would move a period across a
        day boundary."""
        assert display_time.format_period(" 2026-01-01 ") == "Thursday, 1 January 2026"

    def test_it_rewrites_every_period_named_in_a_stored_sentence(self):
        """A decision's stored reason is composed once and stored, so it
        has to be written for a person at render time - otherwise only
        entries made after this change would read correctly."""
        assert display_time.format_periods_in(
            "re-filed to 2026-08-31 from 2026-08-27") == \
            "re-filed to Monday, 31 August 2026 from Thursday, 27 August 2026"

    def test_it_leaves_a_quarterly_name_alone(self):
        assert display_time.format_periods_in("filed to 2023-Q1") == "filed to 2023-Q1"

    def test_it_never_touches_the_date_half_of_a_timestamp(self):
        """The trap this was written into on the first attempt:
        "2026-08-31T09:00:00+08:00" became "Monday, 31 August
        2026T09:00:00+08:00". An instant is format_instant's to write."""
        for text in ("at 2026-08-31T09:00:00+08:00", "at 2026-08-31 09:00:00"):
            assert display_time.format_periods_in(text) == text

    def test_empty_and_none_are_the_empty_string(self):
        assert display_time.format_periods_in("") == ""
        assert display_time.format_periods_in(None) == ""
