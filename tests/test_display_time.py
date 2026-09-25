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
            "assetTimezoneOrFail() to validate the zone, once in assetParts() "
            f"to read it. Found {len(hits)}: {hits}")
