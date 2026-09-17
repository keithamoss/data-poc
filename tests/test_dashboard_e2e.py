"""Real end-to-end browser tests for the dashboard, under pytest-playwright
(Phase 6 step 6, plans/publishing-and-history.md) - real user-flow
scenarios (as-of date picking, supply-history drill-down, dark mode
persistence), not just an extension of dashboard/check_dashboard_renders.py's
existing render-and-zero-console-errors check. Confirmed with Keith: a
well-built suite with a shared "zero console errors" assertion on every
single test's teardown naturally subsumes that script's built-output
check as a side effect of testing real behaviour - but the raw
TEMPLATE-with-no-real-data-embedded scenario needs to stay its own
explicit test case, since a suite built only against the real built
output wouldn't otherwise cover it (see test_raw_template_renders_with_
zero_console_errors below).

The built dashboard this module tests against is produced by the SAME
real, CI-safe build chain deploy-pages.yml itself runs (qa_tools.{bdm,cp}.
build_results_from_history -> pipeline.build_{,cp_}dashboard_data ->
dashboard.embed_dashboard_data) - reading only committed qa_results/
history, never data/ (CLAUDE.md's own hard rule) - via real subprocess
calls, matching that workflow's own steps exactly rather than
reimplementing their __main__ write-to-file logic here. Session-scoped:
built once, reused by every test in this module.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import pytest

from qa_tools.common.qa_results_reader import list_run_ids, read_dataset_stats

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_HTML = ROOT / "dashboard" / "qa-reporting-dashboard.html"
TEMPLATE_HTML = ROOT / "dashboard" / "qa-reporting-dashboard.template.html"

_BUILD_STEPS = [
    ["qa_tools.bdm.build_results_from_history"],
    ["qa_tools.cp.build_results_from_history"],
    ["pipeline.build_dashboard_data"],
    ["pipeline.build_cp_dashboard_data"],
    ["dashboard.embed_dashboard_data"],
]


@pytest.fixture(scope="session")
def built_dashboard_html() -> Path:
    for module in _BUILD_STEPS:
        subprocess.run([sys.executable, "-m", *module], cwd=ROOT, check=True)
    assert DASHBOARD_HTML.exists()
    return DASHBOARD_HTML


@pytest.fixture
def clean_page(page):
    """Wraps pytest-playwright's own `page` fixture with a real console-
    error/uncaught-exception collector, asserted empty in THIS fixture's
    own teardown - applies to every test that uses it, not just one
    dedicated test, per Keith's own confirmed design for this suite."""
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    yield page
    assert errors == [], f"real console errors during this test: {errors}"


def _goto(page, html_path: Path, state: dict | None = None, as_of: str | None = None):
    url = f"file://{html_path.resolve()}"
    query = f"?asof={as_of}" if as_of else ""
    fragment = f"#{urllib.parse.quote(json.dumps(state))}" if state else ""
    page.goto(url + query + fragment)
    page.wait_for_timeout(500)


class TestBuiltDashboardRenders:
    """Absorbs check_dashboard_renders.py's own built-output render check
    (structural JSON validity is still covered separately, tests/
    test_check_dashboard_renders.py - only the real-browser half moves
    here, per that test module's own docstring on why it didn't try to
    mock a browser for that half)."""

    def test_renders_with_zero_console_errors_and_a_populated_view(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        view_html = clean_page.locator("#view").inner_html()
        assert view_html.strip(), "#view is empty after load - the dashboard app never rendered"
        assert clean_page.locator("#agency-grid .card").count() > 0


def test_raw_template_renders_with_zero_console_errors(clean_page):
    """The raw-template-with-illustrative-mock-data scenario - stays its
    own explicit test (module docstring) since TestBuiltDashboardRenders
    above only ever exercises the real built output."""
    _goto(clean_page, TEMPLATE_HTML)
    view_html = clean_page.locator("#view").inner_html()
    assert view_html.strip()
    assert clean_page.locator("#agency-grid .card").count() > 0


class TestAsOfDatePicking:
    def test_a_date_before_any_real_history_shows_no_data(self, clean_page, built_dashboard_html):
        run_ids = list_run_ids("registry-services", "birth-registrations")
        assert run_ids, "no real committed BDM history to test against"
        earliest_run_date = min(
            read_dataset_stats("registry-services", "birth-registrations", rid)["manifest_entry"]["run_date"]
            for rid in run_ids
        )
        before_all_history = (date.fromisoformat(earliest_run_date) - timedelta(days=1000)).isoformat()

        _goto(
            clean_page, built_dashboard_html,
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
            as_of=before_all_history,
        )

        assert "No data" in clean_page.locator("#view h2").inner_text()


class TestSupplyHistoryDrillDown:
    def test_clicking_a_supply_history_entry_sets_the_as_of_date_to_that_run(self, clean_page, built_dashboard_html):
        _goto(
            clean_page, built_dashboard_html,
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
        )

        # A run can legitimately land dated "today" (generator/anchor_date.py's
        # own real wall-clock default), and setAsOfInUrl() deliberately drops
        # the `asof` param entirely when it equals DEFAULT_AS_OF (today) - "a
        # plain shared link never implies someone deliberately chose a date"
        # (that function's own comment) - so this test needs a row whose
        # run_date is NOT today, to actually exercise the asof=<date> case,
        # not just whichever row happens to render first.
        toggle = clean_page.locator("#supply-history-toggle")
        if toggle.count():
            toggle.click()

        rows = clean_page.locator(".supply-history tbody tr")
        assert rows.count() > 0, "no real supply-history rows rendered - fixture/test drifted from real committed history"
        today = date.today().isoformat()
        run_dates = rows.evaluate_all("els => els.map(el => el.dataset.runDate)")
        target_run_date = next((d for d in run_dates if d != today), None)
        assert target_run_date, f"every real supply-history row is dated today ({today}) - can't exercise a real non-default as-of date"
        target_index = run_dates.index(target_run_date)

        rows.nth(target_index).click()
        clean_page.wait_for_timeout(300)

        assert f"asof={target_run_date}" in clean_page.url


class TestDarkModeToggle:
    def test_toggling_dark_mode_persists_across_a_reload(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)

        theme_btn = clean_page.locator("#theme-btn")
        before = clean_page.evaluate("document.documentElement.getAttribute('data-theme')")
        theme_btn.click()
        after_click = clean_page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert after_click != before
        assert after_click in ("light", "dark")

        clean_page.reload()
        clean_page.wait_for_timeout(300)
        after_reload = clean_page.evaluate("document.documentElement.getAttribute('data-theme')")

        assert after_reload == after_click
        assert clean_page.evaluate("localStorage.getItem('theme')") == after_click
