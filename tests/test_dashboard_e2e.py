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
        path = (f"/agency/{quoted['agencyId']}/collection/{quoted['collectionId']}"
                f"/dataset/{quoted['datasetId']}")
        # The drill-down segments, added 2026-09-25 for
        # post-build-review #11. They were missing, which made a test
        # that passed a `columnName` silently drive a plain dataset URL
        # - the assertion then measured the dataset page and said
        # nothing about the column at all.
        if state.get("columnName"):
            path += f"/column/{quoted['columnName']}"
            if state.get("checkKey"):
                path += f"/check/{quoted['checkKey']}"
        return path
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
    """The raw, unembedded template - stays its own explicit test
    (module docstring) since TestBuiltDashboardRenders above only ever
    exercises the real built output.

    WHAT THIS ASSERTS CHANGED with REQ-DASH-055. The template used to
    fall back to an illustrative mock generator, so this checked that
    agency cards appeared. That generator is gone and the whole tree now
    comes from the embedded HIERARCHY, so an unembedded template
    correctly renders NO cards - and has to say why, because a page
    showing "0 agencies" claims something quite different from a page
    nobody has built yet."""
    _goto(clean_page, TEMPLATE_HTML)
    view_text = clean_page.locator("#view").inner_text()
    assert view_text.strip()
    assert clean_page.locator("#agency-grid .card").count() == 0
    assert "no data embedded" in view_text.lower()
    assert "0 agencies" not in view_text


class TestAsOfDatePicking:
    def test_a_date_before_any_real_history_shows_no_data(self, clean_page, built_dashboard_html):
        run_ids = list_run_ids("registry-services", "civil-registration")
        assert run_ids, "no real committed BDM history to test against"
        earliest_run_date = min(
            read_dataset_stats("registry-services", "civil-registration", rid)["arrival_record"]["received_at"][:10]
            for rid in run_ids
        )
        before_all_history = (date.fromisoformat(earliest_run_date) - timedelta(days=1000)).isoformat()

        _goto(
            clean_page, built_dashboard_html,
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
            as_of=before_all_history,
        )

        # `.view-head` rather than `#view h2` - see
        # TestAnExhaustedScheduleIsLoud.test_it_is_not_rendered_as_red
        # for why the pill moved (post-build-review #53).
        assert "No data" in clean_page.locator(".view-head").first.inner_text()


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
        # THE PAGE'S OWN DEFAULT, not `date.today()`. This read the
        # CONTAINER's date until 2026-09-25, and the two are different
        # calendar days for eight hours out of every twenty-four: the
        # asset clock is Australia/Perth (REQ-PIPE-048), so between
        # 16:00 and 24:00 UTC the page's default as-of is already
        # tomorrow. The test then picked a row dated on the page's own
        # default, setAsOfInUrl() correctly dropped the parameter, and
        # the assertion below failed on an entirely healthy page.
        #
        # Found by a real full-suite run in that window, 2026-09-25.
        # Exactly the class of bug the requirement this suite covers
        # exists to prevent, living in the test rather than the code -
        # and unfixable by choosing a better hardcoded date, since the
        # authoritative value is the one the code under test uses.
        today = clean_page.evaluate("() => DEFAULT_AS_OF")
        run_dates = rows.evaluate_all("els => els.map(el => el.dataset.runDate)")
        target_run_date = next((d for d in run_dates if d != today), None)
        assert target_run_date, f"every real supply-history row is dated on the page's own default as-of ({today}) - can't exercise a real non-default as-of date"
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

    def test_dark_mode_actually_renders_dark(self, clean_page, built_dashboard_html):
        """The two tests either side of this one check that an ATTRIBUTE
        flips and survives a reload. Neither checks that anything
        renders differently - `data-theme="dark"` could be set on a page
        whose CSS ignored it entirely and both would still pass.

        Keith asked for this directly, 2026-09-20, after the same gap
        turned up from the other end: REQ-DASH-012's only acceptance
        criterion is that the choice persists, so the register could
        claim dark mode was built and verified without anything ever
        having looked at a colour.

        So this measures real, resolved pixels in both themes -
        `getComputedStyle` on `body`, via the WCAG relative-luminance
        formula - and asserts the page is genuinely dark in one and
        genuinely light in the other, with the text inverting to match.
        """
        _goto(clean_page, built_dashboard_html)

        def render(theme: str) -> dict:
            clean_page.evaluate(
                "t => document.documentElement.setAttribute('data-theme', t)", theme)
            clean_page.wait_for_timeout(250)
            return clean_page.evaluate("""() => {
              const lum = (s) => {
                const [r, g, b] = s.match(/[\d.]+/g).slice(0, 3).map(Number);
                const ch = (c) => {
                  c = c / 255;
                  return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
                };
                return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
              };
              const cs = getComputedStyle(document.body);
              return {bg: lum(cs.backgroundColor), ink: lum(cs.color)};
            }""")

        light, dark = render("light"), render("dark")

        # Genuinely dark/light, not merely different - a theme that
        # swapped one mid-grey for another would pass a bare inequality.
        assert dark["bg"] < 0.05, f"dark background is not dark (luminance {dark['bg']:.3f})"
        assert light["bg"] > 0.5, f"light background is not light (luminance {light['bg']:.3f})"

        # And the text inverts with it, rather than staying put and
        # becoming unreadable against the new background.
        assert dark["ink"] > dark["bg"], "dark mode renders dark text on a dark background"
        assert light["ink"] < light["bg"], "light mode renders light text on a light background"

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

    def test_a_built_requirement_shows_who_signed_it_off(self, clean_page, built_dashboard_html):
        """2026-09-20. Sign-off is enforced in CI, but CI is not where
        anyone reads the register - the panel is, and a rule nobody can
        see is the shape of the failure that prompted the field in the
        first place. Asserted at the layer a human actually looks at,
        per CLAUDE.md's own standing rule about verifying at the last
        transform rather than the first."""
        _goto(clean_page, built_dashboard_html)

        clean_page.locator("#requirements-btn").click()
        rows_text = clean_page.locator("#requirements-panel-body").inner_text()

        assert "Signed off by" in rows_text

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
    def test_it_reads_as_a_whats_new_page_not_an_engineering_log(self, clean_page, built_dashboard_html):
        """Rewritten 2026-09-20 when CHANGELOG.md became CHANGELOG.yaml.

        The previous version asserted a per-item `H:MMam` timestamp
        rendered - a real assertion about the format that existed then,
        and exactly the kind of detail the rewrite removed: entries are
        grouped by day for an audience that does not need the minute.

        What replaces it asserts what the new feed actually promises to a
        reader: a dated day, one summary sentence they can stop at, real
        headlines, and component tags. Plus the absence of the emoji that
        used to lead each item - Keith's own call, and worth asserting
        because nothing else would notice it creeping back."""
        _goto(clean_page, built_dashboard_html)

        clean_page.locator("#changelog-btn").click()
        body = clean_page.locator("#changelog-panel-body")
        rows_text = body.inner_text()

        assert "No release notes yet" not in rows_text
        # The day heading, in the one form this project writes a date in
        # (REQ-DASH-071). It used to be the raw "2026-09-20" out of
        # CHANGELOG.yaml, which criterion 7 rules out wherever a person
        # can see it - so the ISO shape's ABSENCE is asserted too.
        assert re.search(r"\b\w+day, \d{1,2} \w+ \d{4}\b", rows_text), \
            f"no dated day rendered in the release notes panel: {rows_text[:200]!r}"
        assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", rows_text), \
            f"a raw ISO date reached the release notes panel: {rows_text[:200]!r}"
        # A category heading and at least one component tag - the two
        # things the rewrite explicitly KEPT.
        assert any(c in rows_text for c in ("NEW", "IMPROVED", "FIXED")), rows_text[:300]
        assert "QA checks & contract" in rows_text or "Docs & process" in rows_text

        emoji = re.findall(r"[\U0001F300-\U0001FAFF]", rows_text)
        assert not emoji, f"per-component emoji is back in the release notes: {emoji}"


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
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "cp-clients"},
        )
        assert clean_page.locator("a.pill.tag[href*='github.com'][href*='issues']").count() == 0


def _real_amber_bdm_runs() -> list[tuple[str, str]]:
    """(run_id, run_date) for every BDM run the dashboard currently
    renders AMBER, oldest first, and that a decision comment can
    actually resolve to.

    Two things here were got wrong first time and are worth stating.

    It computes status with `status_by_run()` - the same rollup the
    page itself applies - NOT from the generator's own `dirty_severity`
    in the manifest. Those genuinely disagree: dirty_severity is what
    the generator INTENDED to inject, while the badge gates on what the
    real tools actually reported. On the regenerated history they
    produce different sets of runs, and the proxy is the wrong one.

    It also drops any run whose acceptance window is zero-width. Two
    runs sharing a receipt date leave the first with
    window_start == window_end, which `created >= start and created <
    end` can never match - see TestRunWindowsWithTiedArrivedDates. A
    run like that renders amber but no comment can ever attach to it,
    so it is useless to these tests.

    Reads committed qa_results/ via the built dashboard JSON, never
    data/.
    """
    import json as _json

    from qa_tools.common import acceptance_sync as _acc
    from qa_tools.common.dataset_status import status_by_run

    reports = Path(__file__).resolve().parent.parent / "reports"
    with open(reports / "birth_registrations_dashboard.json") as f:
        dataset = _json.load(f)

    amber = {run_id for run_id, status in status_by_run(dataset).items() if status == "amber"}
    usable: list[tuple[str, str]] = []
    for run_id, start, end in _acc._run_windows_for_dataset("birth-registrations"):
        if run_id in amber and start != end:
            usable.append((run_id, start.isoformat()))
    return usable


@pytest.fixture
def dashboard_html_with_amber_decisions(built_dashboard_html, tmp_path, monkeypatch) -> Path:
    """running-thoughts.md #6 ("read-only tension: accepting/rejecting
    amber supplies") - same real-fake-injection shape as dashboard_html_
    with_ticket above (a real gh call only deploy-pages.yml can make
    locally), via QA_COMMENTS_JSON instead of OPEN_TICKETS_JSON. Targets
    3 REAL, currently-amber committed runs, so the decision badge's own
    real gating condition (status==="amber") has genuine amber rows to
    attach to: one gets a real /accept, one gets a real /reject, one
    gets neither.

    Those three runs are COMPUTED HERE, not written down. The original
    version did the right investigation - its docstring said the dates
    were "found by actually computing this dataset's own per-run status
    ... not assumed" - and then froze the answer as three literals
    (2026-05-22/23/24, later run_044/run_062/run_066). Cutting BDM's
    history to 30 deliveries on 2026-09-23 deleted all three, and these
    three tests failed for a reason that had nothing to do with what
    they test. Deriving them means any future regeneration is free.

    Yields the built HTML plus the three run ids it chose, since the
    tests locate rows by data-run-id and can no longer hardcode them.
    """
    from dashboard import embed_dashboard_data as edd

    (tmp_path / "fonts").symlink_to((Path(edd.ROOT) / "dashboard" / "fonts").resolve())
    (tmp_path / "vendor").symlink_to((Path(edd.ROOT) / "dashboard" / "vendor").resolve())

    amber = _real_amber_bdm_runs()
    assert len(amber) >= 3, (
        f"need 3 real amber BDM runs to attach decisions to, found {len(amber)}. "
        "generate_runs.py's RUN_PLAN controls the clean/amber/red mix."
    )
    (accept_id, accept_date), (reject_id, reject_date), (neither_id, _) = amber[:3]

    comments_path = tmp_path / "qa_comments.json"
    comments_path.write_text(json.dumps([{
        "number": 998, "labels": [{"name": "qa-ticket"}, {"name": "dataset:birth-registrations"}],
        "comments": [
            {
                "author": {"login": "keithamoss"}, "body": "/accept",
                "createdAt": f"{accept_date}T10:00:00Z",
                "url": "https://github.com/keithamoss/data-poc/issues/998#issuecomment-1",
            },
            {
                "author": {"login": "keithamoss"}, "body": "/reject",
                "createdAt": f"{reject_date}T10:00:00Z",
                "url": "https://github.com/keithamoss/data-poc/issues/998#issuecomment-2",
            },
        ],
    }]))
    out_html = tmp_path / "dashboard_with_amber_decisions.html"
    monkeypatch.setattr(edd, "QA_COMMENTS_JSON", comments_path)
    monkeypatch.setattr(edd, "DASHBOARD_HTML", out_html)
    edd.embed()
    return {"html": out_html, "accept": accept_id, "reject": reject_id, "neither": neither_id}


class TestAmberDecisionBadge:
    def test_a_real_accept_comment_shows_a_linked_badge_on_its_matching_amber_run(self, clean_page, dashboard_html_with_amber_decisions):
        _goto(
            clean_page, dashboard_html_with_amber_decisions["html"],
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
        )
        toggle = clean_page.locator("#supply-history-toggle")
        if toggle.count():
            toggle.click()

        row = clean_page.locator(f'tr[data-run-id="{dashboard_html_with_amber_decisions["accept"]}"]')
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
            clean_page, dashboard_html_with_amber_decisions["html"],
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
        )
        toggle = clean_page.locator("#supply-history-toggle")
        if toggle.count():
            toggle.click()

        row = clean_page.locator(f'tr[data-run-id="{dashboard_html_with_amber_decisions["reject"]}"]')
        assert row.count() > 0, "the real amber run this test targets isn't in the rendered supply history"
        status_pill_class = row.locator("td").nth(1).locator(".pill").first.get_attribute("class")
        assert "amber" in status_pill_class, "reject must never repaint the pill away from amber"
        badge = row.locator("a.pill.tag[href*='issuecomment-2']")
        assert badge.count() > 0, "no rejection badge rendered on the real amber run it was rejected against"
        assert "keithamoss" in badge.first.inner_text()
        assert "Rejected" in badge.first.inner_text()

    def test_a_different_amber_run_with_no_decision_comment_shows_no_badge(self, clean_page, dashboard_html_with_amber_decisions):
        _goto(
            clean_page, dashboard_html_with_amber_decisions["html"],
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
        )
        toggle = clean_page.locator("#supply-history-toggle")
        if toggle.count():
            toggle.click()

        # a different real amber run, no comment against it
        row = clean_page.locator(f'tr[data-run-id="{dashboard_html_with_amber_decisions["neither"]}"]')
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


class TestStatusMatchesEachToolsOwnVerdict:
    """plans/qa-pipeline.md item 74's own follow-up, 2026-09-19 - the
    test that would have caught the two bugs that shipped.

    Item 74 made each check's real tool verdict authoritative and made
    warn/fail thresholds nullable. That was verified by reading
    reports/*.json and applying the rule in a throwaway script, which
    proved the DATA layer and nothing else - it never exercised the
    template's own buildRealDataset() transform, nor the Python mirror in
    qa_tools/common/dataset_status.py. Both were wrong, and one of them
    wrong in the dangerous direction: buildRealDataset() silently dropped
    `current_status`, so a dbt not_null check with 14 real violations and
    no configured fail threshold rendered GREEN.

    So this asserts at the layer that was actually broken: it drives the
    REAL built dashboard in a REAL browser and uses the page's OWN
    buildRealDataset()/checkStatus()/historyStatus() against the real
    embedded data, comparing every resulting status to the verdict the
    real tool recorded for that same result. ~30k comparisons, a couple
    of seconds - the whole point is that it crosses every transform
    between committed qa_results/ history and what a human actually
    sees, rather than stopping at the first one."""

    _COMPARE_JS = """() => {
      let compared = 0, missingVerdict = 0;
      const disagreements = [];
      for (const raw of [REAL_BIRTH_REG_DATA, REAL_CP_DATA]) {
        if (!raw) continue;
        for (const d of (raw.datasets ? raw.datasets : [raw])) {
          const built = buildRealDataset(d);
          d.columns.forEach((rawCol, ci) => {
            rawCol.checks.forEach((rawCk, ki) => {
              const builtCk = built.columns[ci].checks[ki];
              rawCk.history.forEach((rawH, hi) => {
                if (!rawH.status) { missingVerdict++; return; }
                compared++;
                const got = historyStatus(builtCk.history[hi], builtCk);
                if (got !== rawH.status && disagreements.length < 10) {
                  disagreements.push({check: rawCk.check_id, run: rawH.run_id,
                                      tool: rawH.status, rendered: got, value: rawH.value,
                                      warn: rawCk.warn, fail: rawCk.fail});
                } else if (got !== rawH.status) { compared += 0; }
              });
              if (rawCk.current_status) {
                compared++;
                const got = checkStatus(builtCk);
                if (got !== rawCk.current_status && disagreements.length < 10) {
                  disagreements.push({check: rawCk.check_id, scope: "current",
                                      tool: rawCk.current_status, rendered: got});
                }
              }
            });
          });
        }
      }
      return {compared, missingVerdict, disagreements};
    }"""

    def test_every_rendered_status_matches_the_tool_that_produced_it(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        result = clean_page.evaluate(self._COMPARE_JS)

        # This guard exists so a broken traversal cannot pass vacuously
        # by comparing nothing. It used to read `> 10000`, a figure tied
        # to BDM's 352-run history; cutting that to 30 deliveries on
        # 2026-09-23 left 7,011 real comparisons and this fired BEFORE
        # the disagreement check below - so the test reported a failure
        # while the statuses it exists to police were in fact perfect.
        #
        # The floor is now derived from the data the page was built
        # from: every committed run contributes statuses, so comparing
        # fewer than one per run means the traversal, not the history.
        committed_runs = sum(
            len(list(d.iterdir()))
            for d in (Path(__file__).resolve().parent.parent / "qa_results").glob("*/*")
            if d.is_dir()
        )
        assert result["compared"] > committed_runs, (
            f"only {result['compared']} statuses compared across {committed_runs} "
            "committed runs - the embedded data or the traversal is wrong, "
            "rather than the statuses being right"
        )
        assert result["disagreements"] == [], (
            "the rendered dashboard disagrees with the tools' own verdicts:\n"
            + "\n".join(str(d) for d in result["disagreements"])
        )

    def test_only_the_synthetic_placeholder_check_lacks_a_verdict(self, clean_page, built_dashboard_html):
        """Every real result carries its own tool's verdict. The only
        thing that legitimately doesn't is the "No automated quality rule
        defined" placeholder the builders synthesize for a column no real
        rule covers - and since 2026-09-19 even that states its own
        status explicitly, so the threshold fallback has no live callers
        at all. If this ever fails, some real result lost its verdict on
        the way through - exactly the silent-drop class of bug this
        whole class exists to catch."""
        _goto(clean_page, built_dashboard_html)
        names = clean_page.evaluate("""() => {
          const out = new Set();
          for (const raw of [REAL_BIRTH_REG_DATA, REAL_CP_DATA]) {
            if (!raw) continue;
            for (const d of (raw.datasets ? raw.datasets : [raw]))
              for (const col of d.columns)
                for (const ck of col.checks)
                  for (const h of ck.history)
                    if (!h.status) out.add(ck.name);
          }
          return [...out];
        }""")
        assert names == [], f"real checks are missing their tool verdict: {names}"


# =====================================================================
# REQ-DASH-026 - plain English as a check's primary headline.
#
# Driven in a real browser rather than jsdom for a specific reason:
# renderCheckCard() is a closure inside openColumnDrawer(), so it never
# becomes a window property the way a top-level function does, and half
# of what this requirement asks for is not logic at all - a two-line
# clamp is a computed style, and "a real link" means the BROWSER's
# handling of a modifier-click, not ours.
#
# This is also the layer CLAUDE.md's own standing lesson points at: the
# builders emitting a correct `tool_ref` says nothing about whether the
# render layer, which has its own transform, puts it on the page.
# =====================================================================

_BDM = {"tier": "dataset", "agencyId": "registry-services",
        "collectionId": "civil-registration", "datasetId": "birth-registrations"}


def _open_first_column(page):
    """Opens the first column drawer that actually has checks, and
    returns that column's name."""
    return page.evaluate("""() => {
      const ctx = resolveContext(STATE);
      const col = ctx.ds.columns.find(c => c.checks && c.checks.length);
      openColumnDrawer(ctx.ag, ctx.col, ctx.ds, col);
      return col.name;
    }""")


def _rewrite_checks(page, fields: dict):
    """Overwrites hand-authored fields on every check of the first
    column with checks, then re-renders. Used for the two cases no real
    check can exercise - a description past the clamp, and prose
    containing markup - both of which the requirement's own NFRs call
    out as untestable against today's corpus."""
    page.evaluate("""(fields) => {
      const ctx = resolveContext(STATE);
      const col = ctx.ds.columns.find(c => c.checks && c.checks.length);
      col.checks.forEach(ck => Object.assign(ck, fields));
      openColumnDrawer(ctx.ag, ctx.col, ctx.ds, col);
    }""", fields)
    page.wait_for_timeout(300)


class TestCheckCardReadsAsPlainEnglish:
    def test_the_headline_is_the_authored_name_with_description_and_tool_beneath(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        clean_page.wait_for_timeout(300)

        card = clean_page.locator(".check-card").first
        headline = card.locator(".name").inner_text()
        tool_ref = card.locator(".tool-ref").inner_text()

        # The headline is prose a reader recognises, and carries no tool
        # vocabulary at all - headings used to read "Invalid values -
        # dbt:accepted_values (dbt-core)".
        assert headline.strip()
        assert not re.search(r"dbt|soda|datacontract|evidently", headline, re.I)
        assert card.locator(".check-desc").inner_text().strip()
        # ...and the tool trace is one line below, not a click away.
        assert re.match(r"^(dbt|soda|datacontract|evidently):\S+$", tool_ref), tool_ref

    def test_the_card_does_not_render_the_shared_category_label(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        clean_page.wait_for_timeout(300)

        assert clean_page.locator(".check-card .dim-tag").count() == 0

    def test_the_tool_line_and_the_url_segment_are_the_same_string(
            self, clean_page, built_dashboard_html):
        """The reason for deriving the line from the check_id rather than
        hand-authoring it: what a reader sees is what they can deep-link
        to and grep the contract for."""
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        clean_page.wait_for_timeout(300)

        for i in range(clean_page.locator(".check-card").count()):
            card = clean_page.locator(".check-card").nth(i)
            tool, terse = card.locator(".tool-ref").inner_text().split(":", 1)
            assert card.get_attribute("href").endswith(f"/check/{terse}_{tool}")


class TestCheckCardIsARealLink:
    def test_it_is_an_anchor_carrying_the_checks_own_deep_link(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        column = _open_first_column(clean_page)
        clean_page.wait_for_timeout(300)

        card = clean_page.locator(".check-card").first
        assert card.evaluate("e => e.tagName") == "A"
        href = card.get_attribute("href")
        assert f"/column/{column}/check/" in href

    def test_a_plain_click_is_ours_but_a_modifier_click_is_the_browsers(
            self, clean_page, built_dashboard_html):
        """The whole point of the card being a link. If we swallowed
        every click, cmd-click would silently do nothing instead of
        opening a tab - which is worse than the div it replaced, because
        the element now LOOKS like it should work."""
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        clean_page.wait_for_timeout(300)

        prevented = clean_page.evaluate("""() => {
          const el = document.querySelector('.check-card');
          const fire = init => {
            const e = new MouseEvent('click', {bubbles: true, cancelable: true, ...init});
            el.dispatchEvent(e);
            return e.defaultPrevented;
          };
          return {plain: fire({button: 0}), meta: fire({button: 0, metaKey: true}),
                  ctrl: fire({button: 0, ctrlKey: true}),
                  shift: fire({button: 0, shiftKey: true})};
        }""")

        assert prevented == {"plain": True, "meta": False, "ctrl": False, "shift": False}

    def test_a_plain_click_opens_that_exact_check(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        clean_page.wait_for_timeout(300)

        card = clean_page.locator(".check-card").first
        headline = card.locator(".name").inner_text()
        card.click()
        clean_page.wait_for_timeout(400)

        assert clean_page.locator("#check-panel-title").inner_text() == headline


class TestLongDescriptionsAreClampedOnTheCardOnly:
    _LONG = "long " * 62  # 310 chars; the longest real description is 156

    def _lines(self, page, selector):
        return page.locator(selector).first.evaluate("""e => {
          const lh = parseFloat(getComputedStyle(e).lineHeight);
          return {lines: Math.round(e.getBoundingClientRect().height / lh),
                  clipped: e.scrollHeight > e.clientHeight + 1,
                  chars: e.textContent.length};
        }""")

    def test_the_card_clamps_to_two_lines_and_the_panel_does_not(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        _rewrite_checks(clean_page, {"description": self._LONG})

        card = self._lines(clean_page, ".check-card .check-desc")
        assert card["chars"] == len(self._LONG)
        assert card["lines"] == 2
        assert card["clipped"] is True

        clean_page.locator(".check-card").first.click()
        clean_page.wait_for_timeout(400)
        panel = self._lines(
            clean_page,
            "#check-panel-body .drawer-section:has(h4:text-is('What this check does')) div")
        assert panel["chars"] == len(self._LONG)
        assert panel["lines"] > 2
        assert panel["clipped"] is False

    def test_the_status_pill_holds_its_position_whatever_the_description(
            self, clean_page, built_dashboard_html):
        """Criterion's own wording. The clamp is what makes this true:
        without it a long description would push each card's pill to a
        different offset down the list."""
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        _rewrite_checks(clean_page, {"description": self._LONG})

        offsets = clean_page.locator(".check-card").evaluate_all("""els => els.map(e => {
          const pill = e.querySelector('.row1 .pill');
          return Math.round(pill.getBoundingClientRect().top - e.getBoundingClientRect().top);
        })""")
        assert len(set(offsets)) == 1, offsets


class TestAuthoredProseCannotAlterTheCard:
    """No real check contains a quote or an angle bracket today - 6 of
    257 contain an apostrophe and that is all. This is latent rather
    than live, and it is covered precisely because the corpus is
    hand-authored and growing: the protection has to hold for the check
    somebody writes next year, not for the ones that exist now."""

    _HOSTILE = {
        "name": 'Quote " and <b>bold</b>',
        "description": '</a><script>window.__pwned=1</script> & <img src=x onerror="window.__pwned=2">',
    }

    def test_markup_in_authored_fields_renders_as_text(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        before = clean_page.locator(".check-card").count()
        _rewrite_checks(clean_page, self._HOSTILE)

        card = clean_page.locator(".check-card").first
        assert clean_page.locator(".check-card").count() == before
        assert card.locator(".name").inner_text() == self._HOSTILE["name"]
        assert card.locator(".name b").count() == 0
        assert card.locator("img").count() == 0
        assert clean_page.evaluate("() => window.__pwned ?? null") is None

    def test_a_double_quote_in_a_name_does_not_break_out_of_the_aria_label(
            self, clean_page, built_dashboard_html):
        """The specific escape the requirement's NFR named. The label is
        set with setAttribute rather than interpolated, so the quote is
        simply part of the value."""
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        _rewrite_checks(clean_page, self._HOSTILE)

        label = clean_page.locator(".check-card").first.get_attribute("aria-label")
        assert label.startswith(self._HOSTILE["name"])


class TestAuthoredProseCannotAlterTheDetailPanel:
    """The card's own version of this is above. The panel has six more
    hand-authored fields, and one of them is why an esc() helper was the
    wrong shape: five were found by reading the panel's block builders,
    and the sixth - the trend chart's SVG <title> annotations - was found
    only by driving the real page and noticing a real <img> had appeared.
    A helper protects the call sites somebody remembers to wrap, which is
    the set you already know about.

    Confirmed failing against the pre-fix build first: 1 injected <img>,
    1 injected <b>, and window.__pwned set to 2 by the onerror handler.
    An <img> inside an SVG <title> really does load.
    """

    _SCRIPTY = '</div><script>window.__pwned=1</script><img src=x onerror="window.__pwned=2">'
    _QUOTED = 'Quote " and <b>bold</b>'

    def _open_hostile_check(self, page):
        page.evaluate("""([d, f]) => {
          const ctx = resolveContext(STATE);
          const col = ctx.ds.columns.find(c => c.checks && c.checks.length);
          const ck = col.checks[0];
          ck.description = d;
          ck.failure_indicates = f;
          // Two entries so BOTH chart annotations render - the breaking
          // one draws a glyph between points, the non-breaking one a
          // marker on a point, and they are built by separate code.
          ck.changelog = [
            {date: ck.history[Math.floor(ck.history.length / 2)].date,
             description: d, author: f, breaking: true},
            {date: ck.history[1].date, description: d, author: f, breaking: false},
          ];
          openColumnDrawer(ctx.ag, ctx.col, ctx.ds, col);
          openCheckPanel(ctx.ag, ctx.col, ctx.ds, col, ck);
        }""", [self._SCRIPTY, self._QUOTED])
        page.wait_for_timeout(600)

    def test_nothing_authored_can_inject_an_element_into_the_panel(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        self._open_hostile_check(clean_page)

        counts = clean_page.evaluate("""() => {
          const body = document.getElementById('check-panel-body');
          return {img: body.querySelectorAll('img').length,
                  bold: body.querySelectorAll('b').length,
                  script: body.querySelectorAll('script').length,
                  pwned: window.__pwned ?? null};
        }""")
        assert counts == {"img": 0, "bold": 0, "script": 0, "pwned": None}

    def test_the_authored_sections_still_show_their_real_text(
            self, clean_page, built_dashboard_html):
        """Rendering nothing would also pass the test above. The point is
        that the prose appears, in full, as itself."""
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        self._open_hostile_check(clean_page)

        shown = clean_page.evaluate("""() => {
          const body = document.getElementById('check-panel-body');
          const after = h => {
            const head = [...body.querySelectorAll('h4')].find(x => x.textContent.includes(h));
            return head ? head.nextElementSibling.textContent : null;
          };
          return {what: after('What this check does'),
                  fail: after('What a failure means'),
                  changelog_desc: body.querySelector('.changelog-desc').textContent,
                  changelog_author: body.querySelector('.changelog-author').textContent};
        }""")
        assert shown["what"] == self._SCRIPTY
        assert shown["fail"] == self._QUOTED
        assert shown["changelog_desc"] == self._SCRIPTY
        assert shown["changelog_author"].endswith(self._QUOTED)

    def test_the_charts_own_annotations_hold_the_text_literally(
            self, clean_page, built_dashboard_html):
        """The one that was missed by reading the code. Both the breaking
        glyph and the non-breaking marker build an SVG <title> from the
        same authored description and author."""
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        self._open_hostile_check(clean_page)

        titles = clean_page.locator("#check-panel-body svg title").all_text_contents()
        annotations = [t for t in titles if t.startswith("Definition changed")]
        assert len(annotations) == 2, titles
        for t in annotations:
            assert self._SCRIPTY in t
            assert t.endswith(self._QUOTED)


class TestSupplyAndTableLevelSections:
    """REQ-DASH-033. Driven in a real browser because most of what this
    requirement asks for only exists in a layout: where a section sits
    relative to the column grid, whether it is absent rather than empty,
    and what its own rollup pill says."""

    _CP = {"tier": "dataset", "agencyId": "child-protection-family-support",
           "collectionId": "child-protection", "datasetId": "cp-placements"}

    def _sections(self, page):
        return page.evaluate("""() => [...document.querySelectorAll('.scope-section')].map(s => ({
            scope: s.dataset.scope,
            title: s.querySelector('h3').textContent,
            status: s.querySelector('.head .pill').textContent.trim(),
            rows: [...s.querySelectorAll('.scope-check')].map(r => ({
                name: r.querySelector('.nm').textContent,
                tool: r.querySelector('.tr').textContent,
            })),
        }))""")

    def test_both_sections_render_above_the_column_grid(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, self._CP)

        sections = self._sections(clean_page)
        assert [s["scope"] for s in sections] == ["supply", "table"]
        assert clean_page.evaluate("""() => {
            const wrap = document.getElementById('scope-sections');
            const grid = document.getElementById('col-grid');
            return !!(wrap.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING);
        }""")

    def test_a_section_is_omitted_rather_than_rendered_empty(
            self, clean_page, built_dashboard_html):
        """Real on today's data, not hypothetical - Birth Registrations
        has supply-level checks and no table-level ones. This is the
        case that choosing two sections over one grouped section made
        load-bearing."""
        _goto(clean_page, built_dashboard_html, _BDM)

        assert [s["scope"] for s in self._sections(clean_page)] == ["supply"]

    def test_each_section_carries_its_own_status(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, self._CP)

        by_scope = {s["scope"]: s["status"] for s in self._sections(clean_page)}
        assert set(by_scope) == {"supply", "table"}
        for status in by_scope.values():
            assert status in {"Green", "Amber", "Red"}
        # they are genuinely rolled up independently, not both showing
        # the dataset's own status
        assert by_scope["supply"] != by_scope["table"]

    def test_the_pseudo_columns_no_longer_appear_among_the_real_columns(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, self._CP)

        names = clean_page.locator("#col-grid .col-tile .name").all_text_contents()
        assert names, "the column grid should still have real columns in it"
        assert not [n for n in names if "level checks" in n.lower()]

    def test_rows_sharing_a_name_are_told_apart_by_their_tool(
            self, clean_page, built_dashboard_html):
        """Three tools ask cp-placements' carer-approval question and
        share one name by design (rule 19). Without the tool reference
        the section reads as three identical rows."""
        _goto(clean_page, built_dashboard_html, self._CP)

        rows = [r for s in self._sections(clean_page) for r in s["rows"]]
        repeated = [r for r in rows if sum(1 for x in rows if x["name"] == r["name"]) > 1]
        assert repeated, "expected at least one name shared across tools"
        assert len({r["tool"] for r in repeated}) == len(repeated)

    def test_a_row_opens_that_check_directly_with_a_readable_url(
            self, clean_page, built_dashboard_html):
        """The column drawer exists to pick one check out of a column's
        many; a section with three has already done that. And the URL
        segment is the point of the rename - it used to encode as
        %28table-level%20checks%29."""
        _goto(clean_page, built_dashboard_html, self._CP)

        clean_page.locator(".scope-section[data-scope='table'] .scope-check").first.click()
        clean_page.wait_for_timeout(400)

        assert clean_page.locator("#check-panel-title").inner_text()
        assert not clean_page.evaluate(
            "() => document.getElementById('drawer').classList.contains('open')")
        assert "/column/table/check/" in clean_page.url
        assert "%28" not in clean_page.url


# =====================================================================
# REQ-QAC-039 - the tree the page renders IS the tree in
# contract/data-asset.yaml, not a second copy of it.
#
# Driven in a real browser for the reason CLAUDE.md's own shape-change
# lesson gives: embed_dashboard_data.py writing a correct HIERARCHY
# const says nothing about whether buildData(), which has its own
# transform, actually uses it. Before this the two real agencies and
# collections were literals in the template, and a rename in the config
# would have left the real dataset tiles hanging under a stale id with a
# dead URL - failing silently, in the direction that looks fine.
# =====================================================================

class TestTheRenderedTreeComesFromTheHierarchy:
    def _config_tree(self):
        from qa_tools.common import hierarchy
        out = {}
        for entry in hierarchy.all_datasets():
            out.setdefault((entry.agency_id, entry.agency_name), set()).add(
                (entry.collection_id, entry.collection_name))
        return out

    def test_the_real_agency_and_collection_nodes_match_the_config(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, {"tier": "executive"})
        rendered = clean_page.evaluate("""() => buildData(CURRENT_AS_OF).agencies.map(a => ({
            id: a.id, name: a.name,
            collections: a.collections.map(c => ({id: c.id, name: c.name})),
        }))""")
        by_id = {a["id"]: a for a in rendered}
        for (agency_id, agency_name), collections in self._config_tree().items():
            assert agency_id in by_id, f"{agency_id} is in the config but not on the page"
            assert by_id[agency_id]["name"] == agency_name
            on_page = {(c["id"], c["name"]) for c in by_id[agency_id]["collections"]}
            assert collections <= on_page, (
                f"{agency_id}: config has {collections - on_page} that the page does not")

    def test_the_page_carries_the_hierarchy_const_at_all(
            self, clean_page, built_dashboard_html):
        """A guard against the const silently becoming null in the built
        output - every assertion above would still pass on the
        template's own illustrative fallback, which happens to agree
        with the config today. That is exactly the shape of false green
        this requirement exists to remove."""
        _goto(clean_page, built_dashboard_html, {"tier": "executive"})
        embedded = clean_page.evaluate("() => HIERARCHY")
        assert embedded is not None, "the built dashboard embedded no HIERARCHY"
        assert {a["id"] for a in embedded["agencies"]} == {
            agency_id for agency_id, _ in self._config_tree()}


# =====================================================================
# REQ-PIPE-048 - "today" is answered on the ASSET's clock, not on
# whichever clock the person looking at the page happens to be on.
#
# This was a live bug, not a hypothetical one. liveNowDateStr() used
# toISOString(), which is UTC, so between midnight and 08:00 in Perth
# the dashboard's default as-of date was YESTERDAY - every working
# morning, for eight hours. It went unnoticed because the page tends to
# get opened later in the day, which is exactly why it needs a test
# rather than a careful reader.
#
# Driven in a real browser with the viewer's timezone pinned, because
# that IS the variable: no amount of reading the Python side can tell
# you what a browser in New York does with it.
# =====================================================================

class TestTodayIsTheAssetsToday:
    def _asset_today(self) -> str:
        from qa_tools.common import asset_time
        return asset_time.now().date().isoformat()

    @pytest.mark.parametrize("viewer_tz", [
        "UTC",                 # the old behaviour's own zone
        "America/New_York",    # a day behind Perth for most of the day
        "Pacific/Kiritimati",  # UTC+14, a day AHEAD of Perth
        "Australia/Perth",     # the asset's own
    ])
    def test_the_default_as_of_date_is_the_assets_date_whatever_zone_the_viewer_is_in(
            self, browser, built_dashboard_html, viewer_tz):
        context = browser.new_context(timezone_id=viewer_tz)
        try:
            page = context.new_page()
            page.goto(f"file://{built_dashboard_html}")
            page.wait_for_timeout(400)
            got = page.evaluate("() => ({today: liveNowDateStr(), default: defaultAsOf()})")
        finally:
            context.close()
        assert got["today"] == self._asset_today(), (
            f"a viewer in {viewer_tz} sees {got['today']} as today; the asset's date is "
            f"{self._asset_today()}")
        assert got["default"] == self._asset_today()

    def test_the_page_knows_which_zone_that_is(self, clean_page, built_dashboard_html):
        """Guards the assertions above against going green by accident.
        With ASSET_TIMEZONE absent the page falls back to the viewer's
        own clock, which agrees with the asset's for most of the day -
        so every test above would pass on the broken build for sixteen
        hours out of every twenty-four."""
        from qa_tools.common import asset_time
        _goto(clean_page, built_dashboard_html, {"tier": "executive"})
        assert clean_page.evaluate("() => ASSET_TIMEZONE") == asset_time.asset_timezone().key


class TestAnExhaustedScheduleIsLoud:
    """REQ-PIPE-053, asserted where a person actually looks.

    The requirement exists because a schedule running out looks exactly
    like a healthy feed: no periods, no slots, nothing owed, nothing
    overdue, everything green. So the assertions here are about what is
    ON THE PAGE, not about what the model computed - a correct
    derivation nobody can see is the same failure in a different place.

    The real quarterly calendar's last date is 2027-11-01, and
    cp-case-workers takes only February and August, so it runs out at
    2027-Q3 while its five siblings run to 2027-Q4. That gap gives a
    real window - autumn 2027 - where exactly ONE dataset is exhausted
    among five that are not, which is the case a rollup most wants to
    swallow.
    """

    ONE_EXHAUSTED = "2027-09-15"
    ALL_EXHAUSTED = "2028-06-01"
    NONE_EXHAUSTED = "2026-09-23"
    CP = "child-protection-family-support"
    DS = {"tier": "dataset", "agencyId": CP, "collectionId": "child-protection",
          "datasetId": "cp-case-workers"}

    def test_nothing_is_said_while_the_calendar_still_has_dates(self, page, built_dashboard_html):
        _goto(page, built_dashboard_html, as_of=self.NONE_EXHAUSTED)
        assert page.locator(".notice-exhausted").count() == 0

    def test_the_executive_tier_says_how_many_above_the_grid(self, page, built_dashboard_html):
        _goto(page, built_dashboard_html, as_of=self.ONE_EXHAUSTED)
        notice = page.locator(".notice-exhausted")
        assert notice.count() == 1
        text = " ".join(notice.inner_text().split())
        assert "1 dataset cannot be processed" in text
        assert "schedule has ended" in text

    def test_the_count_tracks_the_as_of_date(self, page, built_dashboard_html):
        _goto(page, built_dashboard_html, as_of=self.ALL_EXHAUSTED)
        text = " ".join(page.locator(".notice-exhausted").inner_text().split())
        assert "6 datasets cannot be processed" in text

    def test_the_notice_names_the_file_to_edit(self, page, built_dashboard_html):
        _goto(page, built_dashboard_html, as_of=self.ONE_EXHAUSTED)
        text = " ".join(page.locator(".notice-exhausted").inner_text().split())
        assert "contract/data-asset.yaml" in text
        assert "candidate-dates" in text, "and how to get the next dates proposed"

    def test_the_notice_cannot_be_dismissed(self, page, built_dashboard_html):
        """A dismissible notice about a task nobody has done is a notice
        about a task nobody will do - and a dismissal persisted in
        browser storage would hide it for that person permanently."""
        _goto(page, built_dashboard_html, as_of=self.ONE_EXHAUSTED)
        assert page.locator(".notice-exhausted button").count() == 0
        assert page.locator(".notice-exhausted [role=button]").count() == 0
        stored = page.evaluate(
            "() => JSON.stringify({l: {...localStorage}, s: {...sessionStorage}})")
        assert "exhaust" not in stored.lower(), stored
        assert "dismiss" not in stored.lower(), stored

    def test_one_exhausted_dataset_among_five_healthy_is_not_swallowed(self, page, built_dashboard_html):
        """The nodata trap, at the tier it would vanish from."""
        _goto(page, built_dashboard_html, state={"tier": "agency", "agencyId": self.CP},
              as_of=self.ONE_EXHAUSTED)
        rows = page.locator("tr", has=page.locator("td", has_text="Delivery schedule ended"))
        assert rows.count() == 1
        assert "Case Workers" in rows.first.inner_text()

    def test_the_dataset_itself_says_so_in_its_own_words(self, page, built_dashboard_html):
        _goto(page, built_dashboard_html, state=self.DS, as_of=self.ONE_EXHAUSTED)
        text = " ".join(page.locator("#view").inner_text().split())
        assert "delivery schedule has ended" in text.lower()
        assert "contract/data-asset.yaml" in text

    def test_it_names_the_datasets_own_last_period_not_its_calendars(self, page, built_dashboard_html):
        """cp-case-workers' last owed period is 2027-Q3; the quarterly
        calendar runs to 2027-Q4. Naming the calendar's would tell a
        reader their dataset ended after a period it never had."""
        _goto(page, built_dashboard_html, state=self.DS, as_of=self.ONE_EXHAUSTED)
        text = " ".join(page.locator("#view").inner_text().split())
        assert "2027-Q3" in text
        assert "2027-Q4" not in text

    def test_it_reads_differently_from_a_dataset_that_simply_has_no_run(self, page, built_dashboard_html):
        """Both are quiet tiles. Only one of them is somebody's job, and
        identical wording is exactly what would hide that."""
        _goto(page, built_dashboard_html, state=self.DS, as_of=self.ONE_EXHAUSTED)
        ended = " ".join(page.locator("#view").inner_text().split())
        _goto(page, built_dashboard_html, state=self.DS, as_of="2023-01-01")
        no_run = " ".join(page.locator("#view").inner_text().split())
        assert ended != no_run
        assert "schedule has ended" in ended.lower()
        assert "schedule has ended" not in no_run.lower()

    def test_it_is_not_rendered_as_red(self, page, built_dashboard_html):
        """A supplier's clean dataset reading red because WE forgot to
        type next year's dates is an attribution error, and the fastest
        way to teach people that red does not mean what it says."""
        _goto(page, built_dashboard_html, state=self.DS, as_of=self.ONE_EXHAUSTED)
        # `.view-head` rather than `#view h2` since 2026-09-25: the
        # status pill moved OUT of the heading and into the right-hand
        # cluster every other dataset page puts it in
        # (post-build-review #53 - a reader who has learned "status is
        # top-right" was finding it top-left, 630px away). What this
        # test is about is which status shows, not which element holds
        # it.
        head = page.locator(".view-head").first
        assert head.locator(".pill.exhausted").count() == 1
        assert head.locator(".pill.red").count() == 0

    def test_the_page_still_has_zero_console_errors(self, clean_page, built_dashboard_html):
        """`clean_page`, NOT `page` (plans/post-build-review.md #43).

        This used to take the plain `page` fixture and register only a
        `console` handler of its own - so an UNCAUGHT EXCEPTION slipped
        straight past it. It passed while the very dataset page it
        navigates to was throwing a TypeError (#5). The suite's own
        `clean_page` fixture has registered both `console` and
        `pageerror` all along, and asserts them empty in teardown.
        """
        for as_of in (self.NONE_EXHAUSTED, self.ONE_EXHAUSTED, self.ALL_EXHAUSTED):
            _goto(clean_page, built_dashboard_html, as_of=as_of)
            _goto(clean_page, built_dashboard_html, state=self.DS, as_of=as_of)


def _contrast(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """WCAG relative-luminance contrast ratio between two sRGB triples."""
    def lum(rgb):
        chan = []
        for v in rgb:
            v /= 255
            chan.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]
    hi, lo = max(lum(a), lum(b)), min(lum(a), lum(b))
    return (hi + 0.05) / (lo + 0.05)


def _rgb(css: str) -> tuple[float, float, float]:
    nums = [float(n) for n in re.findall(r"[\d.]+", css)]
    return tuple(nums[:3])


class TestQuietStatesAreVisiblyBuilt:
    """Two post-build critic findings, verified at the layer a human
    sees (plans/post-build-review.md #49 and #54, signed off by Keith
    2026-09-24).

    Both are asserted against RENDERED values in a real browser rather
    than against the CSS rule that produces them, because both defects
    were invisible in source and only turned up when something was
    actually measured - which is CLAUDE.md's own "verify at the LAST
    transform before the user" lesson, and the reason these live here
    rather than in tests-js/ (jsdom computes no layout and no cascade).
    """

    def _cards(self, page):
        return page.evaluate("""() => [...document.querySelectorAll('#agency-grid .card')].map(card => {
            const meta = card.querySelector('.card-meta');
            if(!meta) return null;
            return Math.round(card.getBoundingClientRect().bottom - meta.getBoundingClientRect().bottom);
        }).filter(v => v !== null)""")

    def test_every_agency_card_pins_its_meta_row_to_the_same_place(self, clean_page, built_dashboard_html):
        """A one-line agency title and a three-line one must not put the
        meta row at two different heights.

        The grid stretches every card in a row to one height, so a card
        whose content is shorter gets the slack as dead space at the
        BOTTOM unless the meta row is pushed down - which is what a
        reader reads as "this card is unfinished". Measured 69px against
        19px on the two real cards before the fix.
        """
        _goto(clean_page, built_dashboard_html)
        gaps = self._cards(clean_page)
        assert len(gaps) >= 2, "needs at least two real agency cards to compare"
        assert len(set(gaps)) == 1, (
            f"agency cards end their meta rows at {gaps} px above the card's own bottom edge - "
            "they should all be the card's own padding, so the rows line up across cards")

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_the_nodata_pills_border_is_at_least_as_visible_as_its_own_label(
            self, clean_page, built_dashboard_html, theme):
        """`.pill.nodata` is distinguished from `.pill.exhausted` by a
        DASHED rather than solid border - the template's own comment
        says so. That distinction is only real if the border can be
        seen: it measured 1.51:1 against its own fill in both themes,
        which is not visible at all, while the label beside it measured
        2.81:1 light / 3.55:1 dark.

        The bar here is deliberately "at least as visible as the text
        next to it" rather than WCAG's 3:1 for non-text contrast. The
        muted tokens do not meet 3:1 yet and raising them is a separate,
        wider decision (post-build-review #49, folded into one
        accessibility pass with #8/#9/#10/#55) - this test guards the
        narrower property that was actually signed off, and will keep
        holding when that pass raises the token.
        """
        _goto(clean_page, built_dashboard_html, as_of="2027-09-01")
        clean_page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
        pill = clean_page.locator(".pill.nodata").first
        pill.wait_for(state="attached")
        styles = pill.evaluate("""el => {
            const s = getComputedStyle(el);
            return {bg: s.backgroundColor, border: s.borderTopColor, text: s.color};
        }""")
        bg = _rgb(styles["bg"])
        border_contrast = _contrast(_rgb(styles["border"]), bg)
        text_contrast = _contrast(_rgb(styles["text"]), bg)
        assert border_contrast >= text_contrast - 0.05, (
            f"{theme}: the nodata pill's border is {border_contrast:.2f}:1 against its own fill while "
            f"its label is {text_contrast:.2f}:1 - a border nobody can see is not a distinction")


class TestTheExecutiveLegendCountsWhatIsActuallyThere:
    """post-build-review #1, Keith's option (b), 2026-09-24.

    The green figure was computed as `total - red - amber`, so an
    agency whose status is `nodata` or `exhausted` landed in the green
    bucket by arithmetic. The single most prominent number on the
    landing page could state that both agencies were healthy directly
    above a notice saying six datasets could not be processed.

    Option (b) was to give the quiet states their own counters rather
    than drop them from the totals, so the legend also stops naming
    three statuses when the vocabulary has five.
    """

    ALL_QUIET = "2028-01-01"   # past the quarterly calendar's last period
    NOTHING_YET = "2022-01-01"  # before any real history exists
    NORMAL = None

    def _legend(self, page):
        return page.locator("#view .legend-key").first.inner_text()

    def test_no_agency_is_counted_green_when_none_is_green(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, as_of=self.ALL_QUIET)
        statuses = clean_page.evaluate("() => DATA.agencies.map(a => a.status)")
        assert "green" not in statuses, "precondition - no agency should be green at this as-of"
        assert re.search(r"Green[^(]*\(0\b", self._legend(clean_page)), (
            f"legend claims green agencies that do not exist: {self._legend(clean_page)}")

    def test_the_quiet_states_are_named_and_counted(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, as_of=self.ALL_QUIET)
        legend = self._legend(clean_page)
        statuses = clean_page.evaluate("() => DATA.agencies.map(a => a.status)")
        for label, status in (("No data", "nodata"), ("Schedule ended", "exhausted")):
            if status in statuses:
                assert label in legend, f"{status!r} is on the page and absent from the legend"

    def test_every_counter_sums_to_the_number_of_agencies(self, clean_page, built_dashboard_html):
        """The arithmetic bug was a subtraction that could not be
        checked. Whatever the legend shows must add up."""
        for as_of in (self.NORMAL, self.ALL_QUIET, self.NOTHING_YET):
            _goto(clean_page, built_dashboard_html, as_of=as_of)
            total = clean_page.evaluate("() => DATA.agencies.length")
            counted = sum(int(n) for n in re.findall(r"\((\d+)\)", self._legend(clean_page)))
            assert counted == total, (
                f"as_of={as_of}: legend counts {counted} of {total} agencies: "
                f"{self._legend(clean_page)}")

    def test_a_normal_as_of_still_reads_the_way_it_always_did(self, clean_page, built_dashboard_html):
        """The quiet counters must not become permanent furniture on a
        page where nothing is quiet."""
        _goto(clean_page, built_dashboard_html, as_of=self.NORMAL)
        legend = self._legend(clean_page)
        statuses = clean_page.evaluate("() => DATA.agencies.map(a => a.status)")
        if "nodata" not in statuses:
            assert "No data" not in legend
        if "exhausted" not in statuses:
            assert "Schedule ended" not in legend


def _open_a_drawer(page):
    """Open the Past snapshots panel, by its label."""
    page.get_by_text("Past snapshots", exact=False).first.click()
    page.wait_for_timeout(300)


class TestTheKeyboardCanReachTheData:
    """The accessibility cluster: post-build-review #8, #9, #10 and #55,
    signed off together 2026-09-25.

    Four findings that are really one job. A reader who does not use a
    mouse could reach Tier 1 and Tier 3 but not Tier 2 - so keyboard
    navigation dead-ended exactly one level above the data this
    dashboard exists to show - while focus could disappear into
    off-screen drawers, seven of eleven interactive element types had no
    visible focus ring, and nothing announced a route change at all.
    """

    # Registry Services rather than Child Protection, deliberately:
    # three of the six CP datasets still throw on drill-down
    # (post-build-review #5, not yet signed off), and that throw aborts
    # navigate() before history.pushState - so a row click there does
    # not change the URL at all. These tests are about keyboard
    # equivalence, not about that bug, and must not be green or red
    # because of it.
    AGENCY = {"tier": "agency", "agencyId": "registry-services"}

    def test_every_dataset_row_is_in_the_tab_order(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, state=self.AGENCY)
        tabindexes = clean_page.evaluate(
            "() => [...document.querySelectorAll('tr[data-nav]')].map(t => t.tabIndex)")
        assert tabindexes, "precondition - the agency page must render dataset rows"
        assert all(t >= 0 for t in tabindexes), (
            f"dataset rows are unreachable by keyboard: tabIndex values {tabindexes}")

    def test_a_dataset_row_navigates_on_enter(self, clean_page, built_dashboard_html):
        """The property that matters is operability, not the attribute."""
        _goto(clean_page, built_dashboard_html, state=self.AGENCY)
        clean_page.locator("tr[data-nav]").first.focus()
        clean_page.keyboard.press("Enter")
        clean_page.wait_for_timeout(300)
        assert "/dataset/" in clean_page.url, (
            f"Enter on a focused dataset row did not drill in: {clean_page.url}")

    def test_nothing_inside_a_closed_drawer_can_take_focus(self, clean_page, built_dashboard_html):
        """Focusable content inside `aria-hidden` is a WCAG 4.1.2
        violation, and to a keyboard user it simply reads as "Tab
        stopped working" - the focus ring vanishes off-screen."""
        _goto(clean_page, built_dashboard_html)
        stuck = clean_page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.drawer:not(.open)').forEach(drawer => {
                drawer.querySelectorAll('a,button,input,select,textarea,[tabindex]')
                      .forEach(el => {
                          el.focus();
                          if(document.activeElement === el) out.push(drawer.id);
                      });
            });
            return [...new Set(out)];
        }""")
        assert not stuck, f"closed drawers still hold focusable controls: {stuck}"

    def test_an_open_drawer_can_still_be_used(self, clean_page, built_dashboard_html):
        """Whatever hides the closed ones must not hide the open one."""
        _goto(clean_page, built_dashboard_html)
        # By its text, not by `.snapshots-btn` - that class is on every
        # masthead chip, and `.first` is "Dark mode", which opens no
        # drawer at all. An earlier draft of this test did exactly that
        # and passed without ever opening one.
        _open_a_drawer(clean_page)
        assert clean_page.locator(".drawer.open").count() == 1, "precondition - a drawer must be open"
        reachable = clean_page.evaluate("""() => {
            const open = document.querySelector('.drawer.open');
            const el = open.querySelector('button, a, input');
            el.focus();
            return document.activeElement === el;
        }""")
        assert reachable, "an OPEN drawer's own controls cannot take focus"

    @pytest.mark.parametrize("selector", [
        ".crumb", ".col-tile", ".snapshots-btn", ".drawer-close",
    ])
    def test_interactive_things_have_a_designed_focus_ring(
            self, clean_page, built_dashboard_html, selector):
        """Seven of eleven element types fell back to Chrome's own
        1px ring. The bar is that focus is styled deliberately, not that
        it is styled identically - the four that already had rings carry
        their own offsets on purpose."""
        _goto(clean_page, built_dashboard_html, state={
            "tier": "dataset", "agencyId": "registry-services",
            "collectionId": "civil-registration", "datasetId": "birth-registrations"})
        # A closed drawer is inert now, so its own close button cannot
        # take focus until the drawer is open - which is the point of
        # the change above, not a gap in this one.
        if selector == ".drawer-close":
            _open_a_drawer(clean_page)
        # Chrome decides :focus-visible from how the LAST interaction
        # arrived, so a programmatic .focus() after a mouse click gets
        # no ring however the CSS is written. One Tab puts the browser
        # back in keyboard mode, which is the mode this test is about.
        clean_page.keyboard.press("Tab")
        found = clean_page.evaluate("""(sel) => {
            const el = document.querySelector(sel + ":not([inert] *)");
            if(!el) return null;
            el.focus();
            const s = getComputedStyle(el);
            return {style: s.outlineStyle, width: s.outlineWidth, color: s.outlineColor};
        }""", selector)
        assert found, f"no {selector} on the page to focus"
        assert found["style"] == "solid" and found["width"] != "0px", (
            f"{selector} falls back to the browser's default focus ring: {found}")

    def test_the_page_title_says_which_view_you_are_on(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        exec_title = clean_page.title()
        _goto(clean_page, built_dashboard_html, state=self.AGENCY)
        agency_title = clean_page.title()
        assert agency_title != exec_title, (
            f"the title never changes - both views are titled {exec_title!r}")
        assert "Registry Services" in agency_title

    def test_a_route_change_is_announced_and_moves_focus(self, clean_page, built_dashboard_html):
        """Without either, a screen-reader user who activates a row is
        told nothing and left where they were."""
        _goto(clean_page, built_dashboard_html, state=self.AGENCY)
        clean_page.locator("tr[data-nav]").first.click()
        clean_page.wait_for_timeout(400)
        focused = clean_page.evaluate("() => document.activeElement.tagName")
        assert focused != "BODY", "focus was not moved to the new view"
        announced = clean_page.evaluate(
            "() => (document.querySelector('[aria-live]') || {}).textContent || ''")
        assert announced.strip(), "nothing was announced for the route change"


class TestEveryDatasetPageSurvivesItsOwnDrillDown:
    """post-build-review #5, signed off 2026-09-25.

    A column with no real rule gets a synthesised placeholder check, and
    that placeholder had no `key`. The scope-section renderer writes
    `data-check="${ck.key}"`, so the attribute became the literal string
    "undefined"; the re-lookup compared `undefined === "undefined"`,
    matched nothing, and dereferenced it.

    Three of seven datasets throw - precisely the three carrying a
    TABLE-scope placeholder, which is the only scope that loop runs
    over. The consequence is worse than a missing panel: navigate()
    calls render() BEFORE history.pushState, so the throw aborts the
    navigation itself and the URL never changes.
    """

    DATASETS = ["cp-clients", "cp-carers", "cp-case-workers",
                "cp-notifications", "cp-investigations", "cp-placements"]

    def _state(self, dataset_id):
        return {"tier": "dataset", "agencyId": "child-protection-family-support",
                "collectionId": "child-protection", "datasetId": dataset_id}

    @pytest.mark.parametrize("dataset_id", DATASETS)
    def test_it_renders_without_throwing(self, clean_page, built_dashboard_html, dataset_id):
        """clean_page's teardown asserts no console error and no
        uncaught exception, which is the whole assertion here."""
        _goto(clean_page, built_dashboard_html, state=self._state(dataset_id))
        assert clean_page.locator("#view h2").count() == 1

    @pytest.mark.parametrize("dataset_id", ["cp-clients", "cp-carers", "cp-case-workers"])
    def test_everything_after_the_scope_sections_still_renders(
            self, clean_page, built_dashboard_html, dataset_id):
        """The throw aborted renderDataset() partway, and Supply History
        is what lived after it."""
        _goto(clean_page, built_dashboard_html, state=self._state(dataset_id))
        assert clean_page.locator("#supply-history-toggle, .supply-history").count() > 0, (
            "the supply-history section is missing - renderDataset() stopped early")

    @pytest.mark.parametrize("dataset_id", ["cp-clients", "cp-carers", "cp-case-workers"])
    def test_clicking_the_row_actually_changes_the_url(
            self, clean_page, built_dashboard_html, dataset_id):
        """The half nobody reported: a throw inside render() means
        history.pushState never runs, so the address bar keeps saying
        the agency while the screen shows a dataset."""
        _goto(clean_page, built_dashboard_html,
              state={"tier": "agency", "agencyId": "child-protection-family-support"})
        row = clean_page.locator(f'tr[data-nav*="{dataset_id}"]').first
        row.click()
        clean_page.wait_for_timeout(400)
        assert f"/dataset/{dataset_id}" in clean_page.url, (
            f"navigating to {dataset_id} left the URL at {clean_page.url}")

    def test_the_placeholder_check_is_deep_linkable(self, clean_page, built_dashboard_html):
        """#12, the same root cause: with no key the check panel opened
        with no URL change, so it was neither shareable nor closable
        with Back."""
        _goto(clean_page, built_dashboard_html, state=self._state("cp-clients"))
        missing = clean_page.evaluate("""() => {
            const out = [];
            (DATA && DATA.agencies || []).forEach(ag => ag.collections.forEach(col =>
                col.datasets.forEach(ds => (ds.columns || []).forEach(c =>
                    (c.checks || []).forEach(ck => { if(!ck.key) out.push(`${ds.id}.${c.name}`); })))));
            return out;
        }""")
        assert not missing, f"checks with no key, so no deep link and no Back: {missing}"


class TestAStaleDeepLinkSaysSo:
    """post-build-review #11, and the half tests-js cannot cover.

    `renderNotFound()` was built for a bookmark pointing at an agency,
    collection or dataset that no longer exists, and never extended to
    a COLUMN or a CHECK. A stale column link landed on the dataset page
    with no message, `STATE.columnName` still set to the value that
    resolved to nothing, and the dead segment still in the URL - so
    re-sharing propagated it. At thirty datasets with evolving schemas
    that is the common case, not the edge.

    The jsdom suite covers the not-found behaviour and cannot cover
    this: its harness carries only a hierarchy, so every dataset has
    zero columns and every column name is stale in it. Proving that a
    REAL column still opens needs real check data, which is here.
    """

    STATE = {"tier": "dataset", "agencyId": "registry-services",
             "collectionId": "civil-registration", "datasetId": "birth-registrations"}

    def _first_column_key(self, page):
        return page.evaluate("""() => {
            const ds = DATA.agencies.find(a=>a.id==="registry-services")
                .collections.find(c=>c.id==="civil-registration")
                .datasets.find(d=>d.id==="birth-registrations");
            return columnKey(ds.columns[0]);
        }""")

    def test_a_real_column_link_still_opens_its_drawer(self, clean_page, built_dashboard_html):
        """The must-not-change half. Repairing a broken deep link is
        worth nothing if it broke the working ones."""
        _goto(clean_page, built_dashboard_html, state=self.STATE)
        key = self._first_column_key(clean_page)
        _goto(clean_page, built_dashboard_html, state={**self.STATE, "columnName": key})
        clean_page.wait_for_timeout(400)
        assert clean_page.locator("#drawer.open").count() == 1, (
            "a column that exists no longer opens its drawer")
        assert key in clean_page.url

    def test_a_dropped_column_is_named_rather_than_ignored(self, clean_page,
                                                            built_dashboard_html):
        _goto(clean_page, built_dashboard_html,
              state={**self.STATE, "columnName": "a_column_that_was_dropped"})
        clean_page.wait_for_timeout(400)
        notice = clean_page.locator(".stale-link-notice")
        assert notice.count() == 1, "no notice - the stale link failed silently"
        assert "a_column_that_was_dropped" in notice.inner_text()

    def test_the_dead_segment_is_taken_out_of_the_url(self, clean_page,
                                                       built_dashboard_html):
        _goto(clean_page, built_dashboard_html,
              state={**self.STATE, "columnName": "a_column_that_was_dropped"})
        clean_page.wait_for_timeout(400)
        assert "a_column_that_was_dropped" not in clean_page.url

    def test_the_rest_of_the_dataset_page_still_renders(self, clean_page,
                                                         built_dashboard_html):
        """Deliberately NOT a full-page not-found: everything the reader
        asked for except the column resolved, and is worth showing."""
        _goto(clean_page, built_dashboard_html,
              state={**self.STATE, "columnName": "a_column_that_was_dropped"})
        clean_page.wait_for_timeout(400)
        assert clean_page.locator("#view h2").count() == 1
        assert clean_page.locator(".column-tile, .col-tile").count() > 0


class TestTheLowRunwayWarningIsOnThePage:
    """post-build-review #2 - REQ-PIPE-053's own criterion says the
    warning appears "both in the dashboard and as a non-fatal warning in
    the repository's gates", and only the gate half was built.

    Live against the real committed config at the time of writing: the
    quarterly calendar has 2 future slots against a threshold of 4, so a
    warning is due right now, which is what makes this assertable
    against the real built page rather than a fixture.
    """

    def test_it_is_visible_on_the_landing_view(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        notice = clean_page.locator(".notice-runway")
        assert notice.count() == 1, (
            "the low-runway warning is computed and still not rendered anywhere")
        assert notice.first.is_visible()

    def test_it_names_the_calendar_and_the_dataset_that_runs_out_first(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        text = clean_page.locator(".notice-runway").first.inner_text()
        assert "quarterly" in text
        assert "cp-case-workers" in text, (
            "the number is a minimum across datasets and the notice does not say whose")

    def test_it_says_in_words_that_nothing_has_failed(self, clean_page,
                                                       built_dashboard_html):
        """Criterion: distinguish a warning from a failure in text as
        well as colour. A reader who cannot tell them apart treats both
        as noise."""
        text = None
        _goto(clean_page, built_dashboard_html)
        text = clean_page.locator(".notice-runway").first.inner_text().lower()
        assert "nothing has failed" in text or "not failing" in text


class TestAnUncheckedColumnSaysSoAtEveryLevel:
    """post-build-review #4, signed off 2026-09-25 with Keith's own
    direction: "a grey, as in a disabled kind of grey colour - kind of
    speaks to it's inactive".

    A column with no rule defined got a synthesised placeholder check
    whose recorded status was GREEN, with the honest explanation in a
    `note` that renders in exactly one place - the check panel, four
    clicks deep. So at every level a reader actually looks, an unchecked
    column read as a healthy one, and a table-scope placeholder rolled a
    whole "Table-level checks" section to green on its own.

    Eleven of these exist across the seven real datasets. At thirty
    datasets the critic called it the most likely thing in the whole
    review to become a real false-green incident.
    """

    STATE = {"tier": "dataset", "agencyId": "child-protection-family-support",
             "collectionId": "child-protection", "datasetId": "cp-clients"}

    def test_no_placeholder_still_claims_to_be_green(self, clean_page,
                                                      built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        wrong = clean_page.evaluate("""() => {
            const out = [];
            (DATA.agencies||[]).forEach(ag => ag.collections.forEach(col =>
              col.datasets.forEach(ds => (ds.columns||[]).forEach(c =>
                (c.checks||[]).forEach(ck => {
                  if(ck.key === "no_rule_defined" && ck.current_status !== "inactive")
                    out.push(`${ds.id}.${c.name}=${ck.current_status}`);
                })))));
            return out;
        }""")
        assert wrong == [], wrong

    def test_the_column_tile_reads_inactive_rather_than_green(self, clean_page,
                                                               built_dashboard_html):
        """The level the reader actually looks at."""
        _goto(clean_page, built_dashboard_html, state=self.STATE)
        status = clean_page.evaluate("""() => {
            const ds = DATA.agencies.find(a=>a.id==="child-protection-family-support")
              .collections.find(c=>c.id==="child-protection")
              .datasets.find(d=>d.id==="cp-clients");
            const col = ds.columns.find(c=>c.name==="extract_timestamp");
            return rollupStatuses((col.checks||[]).map(checkStatus));
        }""")
        assert status == "inactive", (
            f"a column with no rule defined rolls up as {status!r}")

    def test_a_table_scope_section_of_placeholders_is_not_green(self, clean_page,
                                                                 built_dashboard_html):
        """The critic's specific observation: a table-scope placeholder
        rolling a whole section to green on its own."""
        _goto(clean_page, built_dashboard_html, state=self.STATE)
        status = clean_page.evaluate("""() => {
            const ds = DATA.agencies.find(a=>a.id==="child-protection-family-support")
              .collections.find(c=>c.id==="child-protection")
              .datasets.find(d=>d.id==="cp-clients");
            const col = ds.columns.find(c=>/table/i.test(c.name));
            return col ? rollupStatuses((col.checks||[]).map(checkStatus)) : "no-such-column";
        }""")
        assert status == "inactive", status

    def test_an_inactive_column_does_not_drag_its_dataset_down(self, clean_page,
                                                                built_dashboard_html):
        """The constraint the finding stated: it must not win a worstOf
        against a real verdict, in either direction."""
        _goto(clean_page, built_dashboard_html, state=self.STATE)
        same = clean_page.evaluate("""() => {
            const ds = DATA.agencies.find(a=>a.id==="child-protection-family-support")
              .collections.find(c=>c.id==="child-protection")
              .datasets.find(d=>d.id==="cp-clients");
            const all = ds.columns.map(c=> rollupStatuses((c.checks||[]).map(checkStatus)));
            const real = all.filter(s=> s !== "inactive");
            return rollupStatuses(all) === rollupStatuses(real);
        }""")
        assert same, "the inactive columns changed the dataset's own status"

    def test_the_pill_is_labelled_in_words_not_only_by_colour(self, clean_page,
                                                              built_dashboard_html):
        _goto(clean_page, built_dashboard_html, state=self.STATE)
        assert clean_page.evaluate("() => STATUS_LABEL.inactive") == "No rule defined"


class TestNavigationUsesRealLinks:
    """post-build-review #10, Keith's own principle: "there should be
    links everywhere. Everything should be an actual link. Nothing
    should be a magic JavaScript link or magic JavaScript button."

    There were 2 real anchors in the whole rendered page. The jsdom
    suite covers the markup and the modifier guards; this covers what
    only a real browser can show - that the href genuinely resolves, and
    that an ordinary click still routes rather than reloading the page.
    """

    def test_the_landing_view_is_full_of_real_links_now(self, clean_page,
                                                         built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        anchors = clean_page.locator("#agency-grid a.card")
        assert anchors.count() > 0
        href = anchors.first.get_attribute("href")
        assert href.startswith("#/agency/"), href

    def test_an_ordinary_click_routes_without_reloading(self, clean_page,
                                                         built_dashboard_html):
        """The interception still has to work - a real href that always
        navigated the hard way would lose the SPA."""
        _goto(clean_page, built_dashboard_html)
        clean_page.evaluate("window.__stillHere = true")
        clean_page.locator("#agency-grid a.card").first.click()
        clean_page.wait_for_timeout(400)
        assert clean_page.evaluate("window.__stillHere") is True, (
            "the page reloaded - the click was not intercepted")
        assert "/agency/" in clean_page.url

    def test_a_dataset_name_is_a_link_that_resolves(self, clean_page,
                                                     built_dashboard_html):
        _goto(clean_page, built_dashboard_html,
              state={"tier": "agency", "agencyId": "child-protection-family-support"})
        link = clean_page.locator("tbody tr a.dataset-link").first
        href = link.get_attribute("href")
        assert "/dataset/" in href, href
        link.click()
        clean_page.wait_for_timeout(400)
        assert "/dataset/" in clean_page.url

    def test_the_breadcrumbs_are_links(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html,
              state={"tier": "agency", "agencyId": "registry-services"})
        crumbs = clean_page.locator("#rail a.crumb")
        assert crumbs.count() > 1
        assert crumbs.first.get_attribute("href") == "#/"

    def test_a_control_that_acts_rather_than_navigates_is_still_a_button(
            self, clean_page, built_dashboard_html):
        """The other half of the rule - a panel toggle is an action."""
        _goto(clean_page, built_dashboard_html)
        for control_id in ["theme-btn", "activity-btn", "asof-btn"]:
            tag = clean_page.evaluate(
                f"() => (document.getElementById({control_id!r})||{{}}).tagName")
            assert tag in (None, "BUTTON"), f"{control_id} is a {tag}"


class TestAnExhaustedDatasetStillShowsItsHistory:
    """post-build-review #13, decided 2026-09-25: "keep the message
    prominent, and show the last known results below it".

    The exhausted branch replaced the ENTIRE dataset page - columns,
    checks, arrival history, trends - with its message and returned.
    cp-case-workers has 18 real committed runs and 7 columns behind
    that message, with no affordance to reach any of it.

    The reasoning to build against: "nothing is expected" and "nothing
    ever happened" are different statements, and replacing the whole
    page conflates them. This is not a demotion of the message - it
    stays first and stays loud - it is putting the history back
    underneath it.
    """

    # An as-of date past the quarterly calendar's last authored period,
    # so the dataset is genuinely exhausted rather than merely quiet.
    AS_OF = "2028-06-01"
    STATE = {"tier": "dataset", "agencyId": "child-protection-family-support",
             "collectionId": "child-protection", "datasetId": "cp-case-workers"}

    def _open(self, page, html):
        _goto(page, html, state=self.STATE, as_of=self.AS_OF)
        page.wait_for_timeout(400)

    def test_the_message_is_still_there_and_still_first(self, clean_page,
                                                         built_dashboard_html):
        self._open(clean_page, built_dashboard_html)
        text = clean_page.locator("#view").inner_text()
        assert "delivery schedule has ended" in text.lower()

    def test_the_columns_are_reachable_rather_than_replaced(self, clean_page,
                                                             built_dashboard_html):
        self._open(clean_page, built_dashboard_html)
        assert clean_page.locator(".column-tile, .col-tile").count() > 0, (
            "the whole page is still the message - 7 columns of real history are hidden")

    def test_the_supply_history_is_reachable_too(self, clean_page,
                                                  built_dashboard_html):
        self._open(clean_page, built_dashboard_html)
        assert clean_page.locator("#supply-history-toggle, .supply-history").count() > 0

    def test_the_head_still_says_the_schedule_ended(self, clean_page,
                                                     built_dashboard_html):
        """Showing history under the message must not make the page look
        ordinary at a glance - but the pill belongs where every other
        dataset's status pill is, which is the right-hand cluster.
        Putting a second one in the <h2> was the shape #53 complains
        about (a reader who has learned "status is top-right" finding it
        top-left), and the first draft of #13 did exactly that."""
        self._open(clean_page, built_dashboard_html)
        assert clean_page.locator("#view h2 .pill.exhausted").count() == 0
        assert clean_page.locator(".view-head .pill.exhausted").count() == 1

    def test_it_renders_without_throwing(self, clean_page, built_dashboard_html):
        """clean_page's teardown asserts no console error - the whole
        point, since this path never ran the normal renderer before."""
        self._open(clean_page, built_dashboard_html)
        assert clean_page.locator("#view h2").count() == 1


class TestTheQuietPillsSurviveBeingLookedAt:
    """post-build-review #48 and #50 - two visual defects that only a
    real browser can show, which is why both sat unnoticed.

    #48: `.dataset-table tbody tr:hover` and `.pill.nodata` resolve to
    the SAME token, so hovering a row made the pill's fill vanish into
    it - measured at 1.00:1. What was left under the cursor was a 1px
    dashed border. At any past or future as-of, where "No data" is the
    most common row state, the status token disappeared exactly when a
    reader pointed at it.

    #50: `border:1.5px` floors to 1px at DPR 1, which is most government
    desktops - so the exhausted pill's "deliberately unlike the others"
    heavier border was the same weight as the quiet one's, and rendered
    differently between machines. Exactly the case where reading the
    source gives the wrong answer.
    """

    def test_a_hovered_row_does_not_swallow_a_quiet_status_pill(
            self, clean_page, built_dashboard_html):
        """MEASURED AGAINST THE RULES, not against whichever pill a row
        happens to be showing.

        The first draft of this hovered a real row and compared its
        background with its own pill's - and passed, because at the
        as-of it chose that pill was GREEN. It was measuring a state
        that was never in question. The defect is that two CSS rules
        resolve to the same token, so that is what this measures: hover
        a row to get the real hovered colour, then compare it with what
        `.pill.nodata` and `.pill.inactive` actually paint.
        """
        _goto(clean_page, built_dashboard_html,
              state={"tier": "agency", "agencyId": "child-protection-family-support"})
        clean_page.locator("tbody tr").first.hover()
        clean_page.wait_for_timeout(200)
        result = clean_page.evaluate("""() => {
            const tr = document.querySelector("tbody tr");
            const rowBg = getComputedStyle(tr).backgroundColor;
            const probe = (cls) => {
                const el = document.createElement("span");
                el.className = "pill " + cls;
                tr.querySelector("td").appendChild(el);
                const bg = getComputedStyle(el).backgroundColor;
                el.remove();
                return bg;
            };
            return {rowBg, nodata: probe("nodata"), inactive: probe("inactive")};
        }""")
        assert result["rowBg"] != result["nodata"], (
            f"a hovered row and the No data pill are both {result['rowBg']} - the "
            "status token vanishes under the cursor")
        assert result["rowBg"] != result["inactive"], (
            f"a hovered row and the No rule defined pill are both {result['rowBg']}")

    def test_the_heavier_border_is_actually_heavier(self, clean_page,
                                                     built_dashboard_html):
        """Measured, not read: 1.5px is not a width a 1x display has."""
        _goto(clean_page, built_dashboard_html)
        widths = clean_page.evaluate("""() => {
            const probe = (cls) => {
                const el = document.createElement("span");
                el.className = "pill " + cls;
                document.body.appendChild(el);
                const w = getComputedStyle(el).borderTopWidth;
                el.remove();
                return w;
            };
            return {nodata: probe("nodata"), exhausted: probe("exhausted")};
        }""")
        assert widths["exhausted"] != widths["nodata"], (
            f"both borders render at {widths['exhausted']} - the intended weight "
            "difference does not exist on this display")


class TestABuiltRequirementShowsItsOwnHoles:
    """post-build-review #33, Keith: "I'm open to that. Give me a
    proposal" then "ship it".

    REQ-PIPE-053 was marked `built` while six of its criteria were not
    built at all (five, since REQ-PIPE-061 closed one), and the only
    record of that was a `decisions:` note -
    accurate, and in a field nobody has to read. The register's binary
    built/not_started model had no way to say "built except for these",
    so `built` overclaimed and nothing in CI could tell.

    The proposal built here is an optional `unmet_criteria:` list
    rather than a third STATUS: status is what the register is indexed
    and filtered by, and the honest answer for this requirement is that
    it IS built and has a hole in it.
    """

    def test_the_panel_names_them_rather_than_burying_them_in_decisions(
            self, clean_page, built_dashboard_html):
        """Compared against what requirements.yaml actually says, not
        against a literal.

        This asserted `== 6` and went red the day one of the six was
        closed - a test that fails when the work SUCCEEDS, and whose
        only remedy is to edit the number, which is how a number stops
        meaning anything. The claim worth testing is that the panel
        renders what the register holds; how many holes are left is the
        register's business and changes as the batch lands.
        """
        import yaml

        register = yaml.safe_load(Path("requirements.yaml").read_text())
        expected = {r["id"]: len(r.get("unmet_criteria") or [])
                    for r in register["requirements"] if r.get("unmet_criteria")}
        assert expected, "no requirement declares an unmet criterion - this test is vacuous"

        _goto(clean_page, built_dashboard_html)
        rendered = clean_page.evaluate("""() => {
            const out = {};
            (REQUIREMENTS||[]).forEach(r => {
                const n = (r.unmet_criteria||[]).length;
                if(n) out[r.id] = n;
            });
            return out;
        }""")
        assert rendered == expected, (
            f"the page and the register disagree about which requirements have holes: "
            f"page {rendered}, register {expected}")

    def test_every_unmet_criterion_says_which_why_and_who_next(
            self, clean_page, built_dashboard_html):
        """A record that cannot answer those three is the same sentence
        the prose already carried, in a different place."""
        _goto(clean_page, built_dashboard_html)
        bad = clean_page.evaluate("""() => {
            const out = [];
            (REQUIREMENTS||[]).forEach(r => (r.unmet_criteria||[]).forEach(u => {
                if(!u.criterion || !u.why || !u.owner) out.push(r.id);
            }));
            return out;
        }""")
        assert bad == [], bad


class TestTheDisplayStandardHoldsInARealBrowser:
    """REQ-DASH-071, built 2026-09-25.

    The unit suites (tests/test_display_time.py and its browser twin
    tests-js/display-time.test.js) hold the two FORMATTERS to one
    committed case table. This holds the PAGE to the formatters, which
    is a different claim and the one that actually failed before: every
    formatter on this page was already correct about its own arguments,
    and the bug was that three render sites did not call them - one
    character-sliced a wall clock out of the stored string and appended
    " UTC", one emitted the stored string raw, microseconds and offset
    included, and one counted seconds up from a hardcoded 4.

    Same reasoning as CLAUDE.md's own shape-change rule: assert at the
    layer a human sees, not at the layer that computes.
    """

    ALL_DATASETS = [
        ("registry-services", "civil-registration", "birth-registrations"),
        ("child-protection-family-support", "child-protection", "cp-clients"),
        ("child-protection-family-support", "child-protection", "cp-carers"),
        ("child-protection-family-support", "child-protection", "cp-case-workers"),
        ("child-protection-family-support", "child-protection", "cp-notifications"),
        ("child-protection-family-support", "child-protection", "cp-investigations"),
        ("child-protection-family-support", "child-protection", "cp-placements"),
    ]

    # An ISO-8601 instant, an ISO date, or a bare wall clock. Criterion 7
    # rules out all three wherever a person can read one.
    RAW = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\b\d{4}-\d{2}-\d{2}\b|\b\d{2}:\d{2}:\d{2}\b")

    @pytest.mark.parametrize("agency,collection,dataset_id", ALL_DATASETS)
    def test_no_dataset_page_shows_a_raw_timestamp(
            self, clean_page, built_dashboard_html, agency, collection, dataset_id):
        _goto(clean_page, built_dashboard_html, state={
            "tier": "dataset", "agencyId": agency,
            "collectionId": collection, "datasetId": dataset_id})
        text = clean_page.locator("#view").inner_text()
        assert not self.RAW.search(text), (
            f"{dataset_id} renders a raw timestamp: "
            f"{self.RAW.search(text).group(0)!r} in {text[:400]!r}")

    def test_the_supply_history_timing_column_reads_as_a_sentence(
            self, clean_page, built_dashboard_html):
        """43 raw "2026-09-16T05:17:30.280161+00:00" strings were landing
        in this one column when the requirement was written."""
        _goto(clean_page, built_dashboard_html, state={
            "tier": "dataset", "agencyId": "registry-services",
            "collectionId": "civil-registration", "datasetId": "birth-registrations"})
        cells = clean_page.locator("#view table tr td").all_inner_texts()
        timings = [c for c in cells if re.search(r"\d{1,2}:\d{2}(am|pm)", c)]
        assert timings, "no formatted timing rendered in the supply history at all"
        for cell in timings:
            assert re.search(r"\d{1,2}:\d{2}(am|pm) \w+day, \d{1,2} \w+ \d{4}", cell), cell

    def test_the_masthead_says_when_the_page_was_built(
            self, clean_page, built_dashboard_html):
        """Criterion 13 / post-build-review #60. It used to say "Live ·
        updated 4s ago" and count up, so the number a reader saw was the
        age of their own browser tab."""
        _goto(clean_page, built_dashboard_html)
        first = clean_page.locator("#clock-text").inner_text()
        assert first.startswith("Built "), first
        assert re.search(r"\d{1,2}:\d{2}(am|pm) \w+day, \d{1,2} \w+ \d{4}$", first), first

    def test_the_masthead_does_not_count_up_while_the_page_sits_there(
            self, clean_page, built_dashboard_html):
        """The other half of criterion 13: no elapsed time measured from
        when the reader opened it. The old clock ticked every 7 seconds;
        this waits long enough to have caught it twice."""
        _goto(clean_page, built_dashboard_html)
        first = clean_page.locator("#clock-text").inner_text()
        clean_page.wait_for_timeout(15_000)
        assert clean_page.locator("#clock-text").inner_text() == first

    def test_the_page_and_the_python_twin_agree_on_a_real_instant(
            self, clean_page, built_dashboard_html):
        """The cross-runtime check the shared case table cannot make:
        both implementations pass the table independently, and this
        asserts the PAGE's own function against the CLI's own function
        on the same value."""
        from qa_tools.common import display_time

        _goto(clean_page, built_dashboard_html)
        for value in ("2026-09-16T05:17:30.280161+00:00",
                      "2026-01-01T16:00:00+00:00",
                      "2026-09-29T14:15:00+08:00"):
            in_browser = clean_page.evaluate(f"fmtInstant({value!r})")
            assert in_browser == display_time.format_instant(value), value


class TestOutstandingDecisions:
    """REQ-DASH-070, asserted where a person actually looks.

    The standing lesson this follows is CLAUDE.md's own: a green data
    layer says nothing about a render layer with its own transform.
    Everything below drives the REAL built page in a REAL browser and
    reads what the page decided, not what the build wrote.
    """

    def test_every_tier_says_nothing_is_waiting_rather_than_showing_nothing(
            self, clean_page, built_dashboard_html):
        """Criterion 13, at all three tiers.

        An empty element and a missing one look identical to a reader,
        and both look identical to a panel that crashed. The real
        committed history currently has nothing outstanding, so this is
        the state a reader meets today - which makes it the one worth
        holding to a browser-level assertion rather than a unit one.
        """
        _goto(clean_page, built_dashboard_html)
        assert clean_page.locator(".notice-queue").count() == 1
        assert "Nothing is waiting for a person" in clean_page.locator(
            ".notice-queue").inner_text()

        agency = clean_page.locator("#agency-grid .card").first
        agency.click()
        clean_page.wait_for_timeout(400)
        assert "Nothing is waiting for a person" in clean_page.locator(
            ".notice-queue").first.inner_text()

    def test_the_quiet_state_is_not_dressed_as_a_data_verdict(
            self, clean_page, built_dashboard_html):
        """Criterion 5, and the reason this element exists at all: an
        event in our own processing is not a claim about anybody's
        data, so it may not borrow the status vocabulary to say so."""
        _goto(clean_page, built_dashboard_html)
        classes = clean_page.locator(".notice-queue").get_attribute("class")
        for verdict in ("green", "amber", "red"):
            assert verdict not in classes

    def test_no_arrival_anywhere_on_the_page_renders_an_unknown_state_as_on_time(
            self, clean_page, built_dashboard_html):
        """Criterion 10, at the last transform before the user.

        arrivalPill() used to map anything that was not early or late
        to a green 'On time', so REQ-PIPE-066's 'unfiled' - which means
        there is no slot to be punctual against - would have rendered
        as a confident verdict. This asks the PAGE's own function,
        because the page is where that decision is actually made.
        """
        _goto(clean_page, built_dashboard_html)
        for status in ("unfiled", "something-nobody-taught-it", ""):
            label = clean_page.evaluate(f"arrivalStatusLabel({status!r})")
            pill = clean_page.evaluate(f"arrivalPill({status!r})")
            assert label != "On time", status
            assert "pill green" not in pill, status

    def test_an_arrival_verdict_says_it_follows_the_supplys_current_filing(
            self, clean_page, built_dashboard_html):
        """Criterion 11. A punctuality verdict is measured against the
        slot a supply is currently filed to, so it is not a fixed
        historical fact - and a reader who does not know that reads a
        changed figure as the page being wrong."""
        _goto(clean_page, built_dashboard_html)
        clean_page.locator("#agency-grid .card").first.click()
        clean_page.wait_for_timeout(400)
        titles = clean_page.locator("td span[title*='currently filed to']")
        assert titles.count() > 0, "no arrival verdict on Tier 2 carries the qualifier"
