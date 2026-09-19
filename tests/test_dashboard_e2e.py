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
import re
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


def _state_to_path(state: dict) -> str:
    """Python mirror of the template's own stateToPath() (dashboard/qa-
    reporting-dashboard.template.html) - kept in sync by hand since this
    is test-only code building a URL the real JS then parses, not a
    shared module. Only needs the shapes this test module actually
    drives (agency/dataset tiers - see 2026-09-18's running-thoughts.md
    #9 human-friendlier-URLs rework, which replaced the previous opaque
    `#` + encodeURIComponent(JSON.stringify(state)) encoding this used
    to build here)."""
    if not state or state.get("tier") == "exec":
        return "/"
    if state.get("tier") == "demo":
        return "/demo"
    quoted = {k: urllib.parse.quote(str(v), safe="") for k, v in state.items()}
    if state["tier"] == "agency":
        return f"/agency/{quoted['agencyId']}"
    if state["tier"] == "dataset":
        return f"/agency/{quoted['agencyId']}/collection/{quoted['collectionId']}/dataset/{quoted['datasetId']}"
    return "/"


def _goto(page, html_path: Path, state: dict | None = None, as_of: str | None = None):
    url = f"file://{html_path.resolve()}"
    query = f"?asof={as_of}" if as_of else ""
    fragment = f"#{_state_to_path(state)}" if state else ""
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

    def test_a_theme_url_param_never_overrides_localstorage_on_load(self, clean_page, built_dashboard_html):
        """Human-friendlier URLs (2026-09-18, running-thoughts.md #9) added
        a ?theme= query param the toggle writes for display/bookmark
        purposes - explicitly scoped via AskUserQuestion to NOT also make
        a shared link force the visitor's theme: localStorage stays the
        one source of truth for what actually renders on load."""
        url = f"file://{built_dashboard_html.resolve()}"
        clean_page.goto(url)
        clean_page.evaluate("localStorage.setItem('theme', 'light')")

        clean_page.goto(url + "?theme=dark")
        clean_page.wait_for_timeout(300)

        assert clean_page.evaluate("document.documentElement.getAttribute('data-theme')") == "light"


class TestRequirementsPanel:
    def test_opening_it_shows_real_requirements_with_badges_and_linked_tests(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)

        clean_page.locator("#requirements-btn").click()
        body = clean_page.locator("#requirements-panel-body")
        rows_text = body.inner_text()

        # Real, committed requirements.yaml content - not asserting on
        # every entry, just that a real requirement genuinely rendered
        # (id, MoSCoW label, status label, and a real linked test path),
        # not the empty-state fallback.
        assert "REQ-QAC-001" in rows_text
        assert "No requirements yet" not in rows_text
        assert any(label in rows_text for label in ("Must", "Should", "Could"))
        assert any(label in rows_text for label in ("Built", "In progress", "Not started"))
        assert "tests/" in rows_text or "tests-js/" in rows_text

    def test_opening_it_is_a_real_history_entry_that_the_back_button_closes(self, clean_page, built_dashboard_html):
        """The 4 header side panels used to be DOM-only, outside browser
        history entirely - now unified under STATE.panel/?panel= (2026-09-18,
        running-thoughts.md #9, scoped via AskUserQuestion: Back should
        close a panel, same as the column/check drawers already do)."""
        _goto(clean_page, built_dashboard_html)

        clean_page.locator("#requirements-btn").click()
        assert "panel=requirements" in clean_page.url
        assert clean_page.locator("#requirements-panel").get_attribute("aria-hidden") == "false"

        clean_page.go_back()
        clean_page.wait_for_timeout(300)

        assert "panel=requirements" not in clean_page.url
        assert clean_page.locator("#requirements-panel").get_attribute("aria-hidden") == "true"


class TestReleaseNotesPanel:
    def test_opening_it_shows_real_entries_with_a_leading_timestamp(self, clean_page, built_dashboard_html):
        """The 2026-09-18 CHANGELOG.md timestamp retrofit (plans/qa-
        pipeline.md): every entry now carries a real AWST commit time,
        parsed by dashboard/changelog_md.py and rendered by
        renderChangelogPanel() ahead of the entry's own text - assert a
        real `H:MMam`/`H:MMpm` timestamp actually renders, not just that
        the panel has content (which the pre-timestamp version already
        passed)."""
        _goto(clean_page, built_dashboard_html)

        clean_page.locator("#changelog-btn").click()
        body = clean_page.locator("#changelog-panel-body")
        rows_text = body.inner_text()

        assert "No release notes yet" not in rows_text
        assert re.search(r"\b\d{1,2}:\d{2}(am|pm)\b", rows_text), \
            f"no real timestamp rendered in the release notes panel: {rows_text[:200]!r}"


@pytest.fixture
def dashboard_html_with_ticket(built_dashboard_html, tmp_path, monkeypatch) -> Path:
    """Item 76's UI-integration follow-up (plans/qa-pipeline.md,
    2026-09-18): a second built HTML, alongside the shared built_
    dashboard_html fixture, with a real (fake-for-the-test) open ticket
    injected via OPEN_TICKETS_JSON - the file only deploy-pages.yml's
    own real `gh issue list` step ever writes for real, so this test
    can't rely on the shared fixture's own build (no real GH token
    locally, same as every other local build - see embed_dashboard_
    data.py's own OPEN_TICKETS_JSON docstring). Reuses the already-built
    reports/*.json from built_dashboard_html (an explicit dependency
    above, ensuring those files exist first) rather than re-running the
    whole build chain - dashboard.embed_dashboard_data.embed() is the
    only step that actually needs to re-run.

    Symlinks dashboard/fonts/ and dashboard/vendor/ alongside the output
    file: the template loads its real local @font-face files and (Phase
    6, 2026-09-19) the Demo tab's vendored asciinema-player.{css,min.js}
    via paths relative to the HTML file's own directory, which only
    resolve when something is actually there - built_dashboard_html
    doesn't need this since it writes into the real dashboard/ directory
    itself, alongside the real fonts//vendor/, but this fixture
    deliberately writes to tmp_path instead (see OPEN_TICKETS_JSON's own
    docstring on why isolating embed()'s real file targets matters
    here)."""
    from dashboard import embed_dashboard_data as edd

    (tmp_path / "fonts").symlink_to((Path(edd.ROOT) / "dashboard" / "fonts").resolve())
    (tmp_path / "vendor").symlink_to((Path(edd.ROOT) / "dashboard" / "vendor").resolve())

    tickets_path = tmp_path / "open_tickets.json"
    tickets_path.write_text(json.dumps([{
        "number": 999, "title": "Birth Registrations is red",
        "url": "https://github.com/keithamoss/data-poc/issues/999",
        "labels": [{"name": "qa-ticket"}, {"name": "dataset:birth-registrations"}],
        "updatedAt": "2026-09-18T00:00:00Z",
    }]))
    out_html = tmp_path / "dashboard_with_ticket.html"
    monkeypatch.setattr(edd, "OPEN_TICKETS_JSON", tickets_path)
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    edd.embed()
    return out_html


class TestTicketBadge:
    def test_an_open_ticket_shows_a_linked_badge_at_tier2_and_tier3(self, clean_page, dashboard_html_with_ticket):
        badge_selector = "a.pill.tag[href='https://github.com/keithamoss/data-poc/issues/999']"

        _goto(clean_page, dashboard_html_with_ticket, state={"tier": "agency", "agencyId": "registry-services"})
        tier2_badge = clean_page.locator(badge_selector)
        assert tier2_badge.count() > 0, "no ticket badge rendered in the Tier 2 dataset table"
        assert "#999" in tier2_badge.first.inner_text()

        _goto(
            clean_page, dashboard_html_with_ticket,
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
        )
        tier3_badge = clean_page.locator(badge_selector)
        assert tier3_badge.count() > 0, "no ticket badge rendered on the Tier 3 dataset page"

    def test_a_dataset_with_no_open_ticket_shows_no_badge(self, clean_page, dashboard_html_with_ticket):
        _goto(
            clean_page, dashboard_html_with_ticket,
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "death-registrations"},
        )
        assert clean_page.locator("a.pill.tag[href*='github.com'][href*='issues']").count() == 0


@pytest.fixture
def dashboard_html_with_amber_decisions(built_dashboard_html, tmp_path, monkeypatch) -> Path:
    """running-thoughts.md #6 ("read-only tension: accepting/rejecting
    amber supplies") - same real-fake-injection shape as dashboard_html_
    with_ticket above (a real gh call only deploy-pages.yml can make
    locally), via QA_COMMENTS_JSON instead of OPEN_TICKETS_JSON. Targets
    3 REAL, currently-amber committed runs (birth-registrations,
    2026-05-22/23/24) - found by actually computing this dataset's own
    per-run status from reports/birth_registrations_dashboard.json, not
    assumed - so the decision badge's own real gating condition
    (status==="amber") has genuine amber rows to attach to: one gets a
    real /accept, one gets a real /reject, one gets neither."""
    from dashboard import embed_dashboard_data as edd

    (tmp_path / "fonts").symlink_to((Path(edd.ROOT) / "dashboard" / "fonts").resolve())
    (tmp_path / "vendor").symlink_to((Path(edd.ROOT) / "dashboard" / "vendor").resolve())

    comments_path = tmp_path / "qa_comments.json"
    comments_path.write_text(json.dumps([{
        "number": 998, "labels": [{"name": "qa-ticket"}, {"name": "dataset:birth-registrations"}],
        "comments": [
            {
                "author": {"login": "keithamoss"}, "body": "/accept",
                "createdAt": "2026-07-05T10:00:00Z",
                "url": "https://github.com/keithamoss/data-poc/issues/998#issuecomment-1",
            },
            {
                "author": {"login": "keithamoss"}, "body": "/reject",
                "createdAt": "2026-07-23T10:00:00Z",
                "url": "https://github.com/keithamoss/data-poc/issues/998#issuecomment-2",
            },
        ],
    }]))
    out_html = tmp_path / "dashboard_with_amber_decisions.html"
    monkeypatch.setattr(edd, "QA_COMMENTS_JSON", comments_path)
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    edd.embed()
    return out_html


class TestAmberDecisionBadge:
    def test_a_real_accept_comment_shows_a_linked_badge_on_its_matching_amber_run(self, clean_page, dashboard_html_with_amber_decisions):
        _goto(
            clean_page, dashboard_html_with_amber_decisions,
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
        )
        toggle = clean_page.locator("#supply-history-toggle")
        if toggle.count():
            toggle.click()

        row = clean_page.locator('tr[data-run-id="run_044_2026-07-05"]')
        assert row.count() > 0, "the real amber run this test targets isn't in the rendered supply history"
        badge = row.locator("a.pill.tag[href*='issuecomment-1']")
        assert badge.count() > 0, "no decision badge rendered on the real amber run it was accepted against"
        assert "keithamoss" in badge.first.inner_text()
        assert "Accepted" in badge.first.inner_text()

    def test_a_real_reject_comment_shows_a_linked_rejection_badge_on_its_matching_amber_run(self, clean_page, dashboard_html_with_amber_decisions):
        """Keith's own explicit call, 2026-09-19 (resolving plans/
        conceptual-design.md Thread A's own parked amber-governance
        question): a rejected run's pill still stays amber - only the
        badge differs from accept's."""
        _goto(
            clean_page, dashboard_html_with_amber_decisions,
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
        )
        toggle = clean_page.locator("#supply-history-toggle")
        if toggle.count():
            toggle.click()

        row = clean_page.locator('tr[data-run-id="run_062_2026-07-23"]')
        assert row.count() > 0, "the real amber run this test targets isn't in the rendered supply history"
        status_pill_class = row.locator("td").nth(1).locator(".pill").first.get_attribute("class")
        assert "amber" in status_pill_class, "reject must never repaint the pill away from amber"
        badge = row.locator("a.pill.tag[href*='issuecomment-2']")
        assert badge.count() > 0, "no rejection badge rendered on the real amber run it was rejected against"
        assert "keithamoss" in badge.first.inner_text()
        assert "Rejected" in badge.first.inner_text()

    def test_a_different_amber_run_with_no_decision_comment_shows_no_badge(self, clean_page, dashboard_html_with_amber_decisions):
        _goto(
            clean_page, dashboard_html_with_amber_decisions,
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
        )
        toggle = clean_page.locator("#supply-history-toggle")
        if toggle.count():
            toggle.click()

        row = clean_page.locator('tr[data-run-id="run_066_2026-07-27"]')  # a different real amber run, no comment
        assert row.count() > 0
        assert row.locator("a.pill.tag[href*='issuecomment']").count() == 0


class TestDemoTab:
    """plans/tooling.md #1 Phase 6 - a real recording of the actual
    mothman CLI/TUI, played back by the vendored asciinema-player widget.
    Unlike tests-js/demo-tab.test.js (jsdom, where the vendored external
    <script src="vendor/asciinema-player.min.js"> never actually loads -
    see that file's own header comment), this is a real browser against
    the real BUILT dashboard, so the real player library, the real
    committed dashboard/vendor/asciinema-player.{css,min.js}, and the
    real committed dashboard/demos/qa_wizard.cast (embedded as DEMO_CAST
    by the built_dashboard_html fixture's own real embed step) all
    actually load - this is the one place real playback is verified."""

    def test_opening_it_renders_the_real_player_with_zero_console_errors(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, state={"tier": "demo"})

        assert clean_page.locator("h2", has_text="Demo").count() > 0
        # asciinema-player's own real DOM (a canvas-free, DOM-rendered
        # terminal grid + controls bar) - not the "No demo recording
        # embedded yet" fallback, confirming DEMO_CAST is real, non-null
        # content and the vendored player library actually loaded.
        player = clean_page.locator("#demo-player-container [class*='ap-']")
        assert player.count() > 0, "the real asciinema-player widget never rendered"
        assert clean_page.locator("text=No demo recording embedded yet").count() == 0

    def test_the_demo_header_button_navigates_there_from_anywhere(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)

        clean_page.locator("#demo-btn").click()
        clean_page.wait_for_timeout(300)

        assert "#/demo" in clean_page.url
        assert clean_page.locator("h2", has_text="Demo").count() > 0
