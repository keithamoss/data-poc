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
built once PER WORKER, into that worker's own directory, and reused by
every test of this module the worker runs - the module spreads across
workers a class at a time (REQ-TEST-281).
"""
from __future__ import annotations

import json
import re
import os
import subprocess
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import pytest

from qa_tools import collections as _registry

from qa_tools.common.qa_results_reader import list_run_ids, read_dataset_stats

# NEEDS A BOOTSTRAPPED DEPLOYMENT (plans/tooling.md #27). This module
# reads `reports/*.json`, which is built from the deployment's recorded
# QA history - so it belongs in the CI job that bootstraps one. Nothing
# in a signature says so, which is why the mark is here rather than
# derived; tests/test_publish.py asserts it is not forgotten.
pytestmark = pytest.mark.needs_deployment


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_HTML = ROOT / "dashboard" / "qa-reporting-dashboard.html"
TEMPLATE_HTML = ROOT / "dashboard" / "qa-reporting-dashboard.template.html"

#: The build chain the fixture below runs, every step through mothman with
#: the worker's own `--out-dir` (REQ-TEST-281).
_BUILD_STEPS = ["rebuild-results", "build-data", "embed"]


def _deployment_dsn():
    import conftest
    return getattr(conftest, "DEPLOYMENT_SUPPLY_DSN", None)


def _deployment_environment():
    import conftest
    return getattr(conftest, "DEPLOYMENT_ENVIRONMENT", None)


@pytest.fixture(autouse=True)
def reads_the_deployments_history(supply_dsn, monkeypatch):
    """Point THIS FILE's own reads at the deployment's database.

    The same reasoning as `built_dashboard_html` below, one level up.
    Several helpers here - `_real_amber_bdm_runs`, `status_by_run`,
    the as-of date bounds - ask the reader for real QA history IN
    PROCESS, and since REQ-PIPE-089 that reader goes to whatever
    `MOTHMAN_SUPPLY_DSN` names. conftest points it at this worker's
    own empty database, correctly, for every test that WRITES.

    Autouse and scoped to this file, because this whole module is
    about the real built dashboard and none of it writes supply data.
    Restored by monkeypatch after each test, so nothing leaks to
    another file sharing the worker.
    """
    dsn = _deployment_dsn()
    if dsn:
        monkeypatch.setenv("MOTHMAN_SUPPLY_DSN", dsn)
        import conftest
        conftest.use_deployment_environment(monkeypatch)


#: The real tree's build outputs, which nothing in this module may write
#: (REQ-TEST-281 criterion 4): each collection's results and dashboard files
#: and the built page with its data files.
def _real_build_outputs() -> list[Path]:
    reports = ROOT / "reports"
    files = [reports / name for c in _registry.all_collections()
             for name in (c.results_file, c.dashboard_file)]
    files.append(DASHBOARD_HTML)
    data = ROOT / "dashboard" / "data"
    files += sorted(data.iterdir()) if data.is_dir() else []
    return files


def _stat_of(paths: list[Path]) -> dict[str, tuple[int, int] | None]:
    return {str(p): ((st := p.stat()).st_mtime_ns, st.st_size) if p.exists() else None
            for p in paths}


@pytest.fixture(scope="session")
def real_tree_before_the_build() -> dict:
    """The real tree's build outputs as they stood before this worker built."""
    return _stat_of(_real_build_outputs())


@pytest.fixture(scope="session")
def built_dashboard_html(supply_dsn, worker_id, tmp_path_factory,
                         real_tree_before_the_build) -> Path:
    """The real dashboard, built by the real chain, ONCE PER WORKER, into a
    directory named for that worker (REQ-TEST-281 criterion 3).

    PER WORKER BECAUSE THIS MODULE NOW SPREADS ACROSS WORKERS a class at a
    time (`--dist loadgroup`, tests/conftest.py's distribution groups), so a
    session-scoped fixture runs once on each. It used to build into the real
    `reports/` and `dashboard/`, and `--dist loadfile` kept the whole module
    on one worker so two builds never rewrote the same files
    (plans/tooling.md #10, race 2). Each build now has a directory of its own
    - `mothman dashboard ... --out-dir` - so no two builds share a file, and
    the real tree is never written at all (criterion 4). A developer wanting
    a current local dashboard runs `mothman dashboard rebuild`.

    IT BUILDS AGAINST THE DEPLOYMENT'S DATABASE, NOT THE WORKER'S, and
    that is the point rather than a shortcut. This fixture's input is
    recorded QA HISTORY - a shared, read-only corpus. It used to arrive
    with the checkout as committed `qa_results/` files, so every worker
    saw the same thing for free; REQ-PIPE-089 made it a database, and a
    worker's database is empty by design, so building from one produces
    an empty dashboard and 147 errors that name a subprocess rather
    than the cause. NOTHING HERE WRITES TO IT.

    It needs the deployment's database POPULATED, which is
    `mothman pipeline bootstrap` - see CLAUDE.md's setup section. That
    is a real new requirement for running the suite, not an accident.
    """
    dsn = _deployment_dsn()
    if not dsn:
        pytest.fail(
            "no deployment database to build the dashboard from. Set "
            "MOTHMAN_SUPPLY_DSN and run `mothman pipeline bootstrap` - since "
            "REQ-PIPE-089 the dashboard's input is recorded QA history in a "
            "database rather than a committed tree, so a checkout alone is no "
            "longer enough.")

    out = tmp_path_factory.mktemp(f"dashboard-build-{worker_id}", numbered=False)
    env = {**os.environ, "MOTHMAN_SUPPLY_DSN": dsn}
    env.pop("MOTHMAN_DASHBOARD_OUT", None)
    # The environment the deployment's database is marked for (REQ-PIPE-107).
    if _deployment_environment():
        env["MOTHMAN_ENVIRONMENT"] = _deployment_environment()
    for step in _BUILD_STEPS:
        subprocess.run([sys.executable, "-m", "cli.app", "dashboard", step, "--out-dir", str(out)],
                       cwd=ROOT, check=True, env=env)
    page = out / "qa-reporting-dashboard.html"
    assert page.exists()
    return page


def _reports_of(built: Path) -> Path:
    """The `reports/` a built page was built from - its worker's own."""
    return built.parent / "reports"


def _embed_variant(built: Path, out: Path, *, reports: dict | None = None) -> Path:
    """A second page, embedded in-process by the real embed() into `out`, from
    THIS WORKER'S own built reports (REQ-TEST-281 criterion 6) - never the
    real tree's. `out/reports/` links each of the worker build's reports
    files, except those `reports` replaces ({file name: JSON value}); the page
    lands at `out/qa-reporting-dashboard.html` with its data/, fonts/ and
    vendor/ beside it, the same `--out-dir` shape the worker's build has.

    AGAINST THE DEPLOYMENT'S DATABASE, like the worker's build, never the
    worker's own (post-build-review #272). embed() reads the database for
    everything that is not in reports/ - the outstanding blockers, the
    changelog feed, the build's provenance - and a class-scoped fixture runs
    before this module's autouse `reads_the_deployments_history`, so it used
    to read the worker's test database: empty on a fresh worker, and holding
    whatever another module on the same worker left there otherwise. A
    variant must differ from the worker's page only in what it replaces."""
    import conftest

    from dashboard import embed_dashboard_data as edd
    from qa_tools.common import build_output

    reports = reports or {}
    (out / "reports").mkdir(parents=True, exist_ok=True)
    for f in sorted(_reports_of(built).iterdir()):
        if f.name not in reports:
            (out / "reports" / f.name).symlink_to(f.resolve())
    for name, value in reports.items():
        (out / "reports" / name).write_text(json.dumps(value))
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(build_output.OUT_DIR_ENV, str(out))
        if _deployment_dsn():
            mp.setenv("MOTHMAN_SUPPLY_DSN", _deployment_dsn())
            conftest.use_deployment_environment(mp)
        edd.embed()
    return out / build_output.PAGE_NAME


class TestTheBuildIsTheWorkersOwn:
    """REQ-TEST-281 criteria 3 to 5: the page every test here reads was built
    into this worker's own directory, the real tree was not written, and the
    page's fonts and player load from beside it."""

    def test_the_page_is_built_into_a_directory_named_for_this_worker(self, built_dashboard_html,
                                                                       worker_id):
        assert built_dashboard_html.parent.name == f"dashboard-build-{worker_id}"
        assert ROOT not in built_dashboard_html.parents
        reports = _reports_of(built_dashboard_html)
        for c in _registry.all_collections():
            assert (reports / c.results_file).is_file(), c.id
            assert (reports / c.dashboard_file).is_file(), c.id

    def test_the_build_did_not_write_the_real_tree(self, built_dashboard_html,
                                                   real_tree_before_the_build):
        assert real_tree_before_the_build, "no real-tree outputs listed - this test proves nothing"
        now = _stat_of([Path(p) for p in real_tree_before_the_build])
        changed = [p for p, before in real_tree_before_the_build.items() if now[p] != before]
        assert changed == [], f"the browser-test build wrote the real tree: {changed}"
        new_data = set(_stat_of(_real_build_outputs())) - set(real_tree_before_the_build)
        assert not new_data, f"the browser-test build added files to the real tree: {new_data}"

    def test_every_browser_test_is_grouped_by_its_class(self, request):
        """Criterion 1: --dist loadgroup moves a CLASS between workers, never
        part of one - the class-scoped variant pages assume it."""
        mine = [i for i in request.session.items if i.path == request.node.path]
        assert len(mine) > 1, "only this test collected - this test proves nothing"
        for item in mine:
            groups = [m.args[0] for m in item.iter_markers("xdist_group")]
            path = item.nodeid.split("::", 1)[0]
            expected = f"{path}::{item.cls.__name__}" if item.cls else path
            assert groups == [expected], (item.nodeid, groups)

    def test_the_self_hosted_fonts_load_from_beside_the_page(self, clean_page, built_dashboard_html):
        fonts = []
        clean_page.on("requestfinished",
                      lambda r: fonts.append(r.url) if r.url.endswith(".woff2") else None)
        _goto(clean_page, built_dashboard_html)
        status = clean_page.evaluate(
            "() => document.fonts.ready.then(() => [...document.fonts].map(f => f.status))")
        assert "loaded" in status, status
        assert "error" not in status, status
        here = (built_dashboard_html.parent / "fonts").as_uri()
        assert fonts and all(u.startswith(here) for u in fonts), fonts


def _await_requirements_plans(page, *, start: bool = False) -> None:
    """Wait for the Requirements and Plans data to have arrived.

    REQ-DASH-291 criterion 7: on the built page it is a data file of its
    own, loaded on demand when a reader opens the Requirements panel or the
    Plans tab, so a test that opens either and reads straight away would
    read the loading state. `start` asks for it without opening either, for
    a test that reads REQUIREMENTS itself. A page with no list of data files
    (the raw template) has nothing to wait for."""
    if start:
        page.evaluate("() => { requirementsPlansData(); }")
    page.wait_for_function(
        "() => !DATA_FILES || (REQ_PLANS_LOAD && REQ_PLANS_LOAD.state !== 'loading')")


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
    if state.get("tier") == "feedback":
        return "/feedback"
    quoted = {k: urllib.parse.quote(str(v), safe="") for k, v in state.items()}
    if state["tier"] == "period":
        return (f"/agency/{quoted['agencyId']}/collection/{quoted['collectionId']}"
                f"/period/{quoted['period']}")
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


def _goto(page, html_path: Path, state: dict | None = None, in_place_on: str | None = None):
    """Navigate, and wait for the page to have actually RENDERED.

    This used to end in `page.wait_for_timeout(500)`. With 126 call
    sites that was over a minute of the gate spent asleep, and it was
    wrong in both directions at once - slower than needed locally, and
    too short on a loaded runner, which is how time-dependent flakes get
    written. The template now bumps `data-render-count` at the end of
    every render (the only thing that reads it is this function), so
    there is a real condition to wait on.

    THE FIDDLY PART IS TELLING THE TWO NAVIGATIONS APART. A goto to a
    different path reloads the document, which resets the counter - so
    the right condition is "has rendered at all". A goto that changes
    only the fragment does NOT reload, so the counter keeps its value
    and the right condition is "has rendered AGAIN". Waiting for the
    wrong one of those either returns instantly on a stale render or
    hangs forever. `window.__e2eMark` distinguishes them: set before
    navigating, it survives a same-document hash change and does not
    survive a reload.
    """
    url = f"file://{html_path.resolve()}"
    query = f"?in-place-on={in_place_on}" if in_place_on else ""
    fragment = f"#{_state_to_path(state)}" if state else ""
    try:
        before = page.evaluate(
            "() => { window.__e2eMark = true;"
            "        return Number(document.documentElement.dataset.renderCount || 0); }")
    except Exception:
        before = 0  # no document yet - the first navigation of this page
    page.goto(url + query + fragment)
    page.wait_for_function(
        """(before) => {
             const n = Number(document.documentElement.dataset.renderCount || 0);
             if (!n) return false;
             return !window.__e2eMark || n > before;
           }""",
        arg=before)


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


class TestInPlaceOnDatePicking:
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
            in_place_on=before_all_history,
        )

        # `.view-head` rather than `#view h2` - see
        # TestAnExhaustedScheduleIsLoud.test_it_is_not_rendered_as_red
        # for why the pill moved (post-build-review #53).
        # A thousand days before any history is also before the dataset's
        # first participation version, so the pill says it was not owed yet
        # (REQ-DASH-182 criterion 3 as amended, Keith 2026-10-15 Q19) - and
        # never a status it had no supply to earn (post-build-review #200).
        head = clean_page.locator(".view-head").first.inner_text()
        assert "Not owed yet" in head
        assert not any(word in head for word in ("Green", "Amber", "Red"))


class TestTheInPlaceOnPanelSaysWhichPeriod:
    """REQ-DASH-054 criteria 6, 8, 9 and 10, at the layer a reader sees.

    THE DATA LAYER IS NOT ENOUGH HERE, and this project has the scar:
    item 74 shipped a correct `reports/*.json` and a template whose own
    transform silently dropped the new field, rendering a check with 14
    real violations green. The lookups have their own unit tests in
    tests-js/; what this holds is that the built page actually renders
    what they answer.
    """

    def _open_panel(self, page):
        page.click("#in-place-on-btn")
        page.wait_for_selector("#in-place-on-panel.open")

    def test_the_panel_names_the_period_per_calendar(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        self._open_panel(clean_page)
        text = clean_page.locator("#in-place-on-periods").inner_text()
        # This asset has two named calendars, and the same chosen date is a
        # different period on each - which is the whole reason a reader
        # needs telling rather than inferring it from the date.
        assert "quarterly calendar" in text
        assert "daily calendar" in text

    def test_the_named_period_follows_the_date_the_reader_picks(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        self._open_panel(clean_page)
        before = clean_page.locator("#in-place-on-periods").inner_text()
        # A date inside the covered range but well away from the default,
        # taken from the page's own embedded range rather than from a
        # literal - a hard-coded date here would go stale the moment the
        # calendars were re-authored.
        first = clean_page.evaluate("() => coveredDateRange().first")
        clean_page.evaluate("(d) => renderInPlaceOnPeriods(d)", first)
        after = clean_page.locator("#in-place-on-periods").inner_text()
        assert after != before, "the period statement did not follow the date"

    def test_the_input_is_bounded_to_what_the_page_has_periods_for(self, clean_page, built_dashboard_html):
        """Criterion 8. A native date input greys out anything outside
        min/max, which puts the limit where the reader is choosing rather
        than in a correction afterwards."""
        _goto(clean_page, built_dashboard_html)
        self._open_panel(clean_page)
        bounds = clean_page.evaluate(
            "() => ({min: document.getElementById('in-place-on-input').min,"
            "        max: document.getElementById('in-place-on-input').max,"
            "        range: coveredDateRange()})")
        assert bounds["min"] == bounds["range"]["first"]
        assert bounds["max"] == bounds["range"]["last"]
        # And the maximum is NOT the future: criterion 3 embeds no period
        # that has not begun, so there is nothing beyond it to offer.
        assert bounds["max"] >= bounds["min"]

    def test_an_out_of_range_date_by_url_says_so_and_offers_a_way_back(
            self, clean_page, built_dashboard_html):
        """Criteria 9 and 10. A URL is the way in - an old bookmark, a
        hand-edited query string - and the input's own bounds cannot stop
        any of those."""
        _goto(clean_page, built_dashboard_html, in_place_on="1990-01-01")
        notice = clean_page.locator("#in-place-on-range-notice")
        assert notice.is_visible()
        text = notice.inner_text()
        assert "outside the dates" in text
        # It states the covered range, so the reader knows what to ask for.
        first = clean_page.evaluate("() => coveredDateRange().first")
        assert first[:4] in text, "the notice does not state the covered range"

        # The page itself is still there - every dataset resolved to a real
        # state at that date, and hiding correct answers to make a point
        # about the date is the empty view criterion 10 forbids.
        assert clean_page.locator("#view").inner_html().strip()

        clean_page.click("#in-place-on-range-reset")
        # wait_for_function rather than wait_for_selector: the default
        # selector state is "visible", and what is being waited for here is
        # the element going hidden - which that condition can never see.
        clean_page.wait_for_function(
            "() => document.getElementById('in-place-on-range-notice').hidden")
        assert "in-place-on=" not in clean_page.url

    def test_a_date_inside_the_range_draws_no_notice_at_all(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        assert clean_page.locator("#in-place-on-range-notice").is_hidden()


class TestSupplyHistoryDrillDown:
    def test_clicking_a_supply_history_entry_sets_the_in_place_on_date_to_that_run(self, clean_page, built_dashboard_html):
        _goto(
            clean_page, built_dashboard_html,
            state={"tier": "dataset", "agencyId": "registry-services", "collectionId": "civil-registration", "datasetId": "birth-registrations"},
        )

        # A run can legitimately land dated "today" (generator/anchor_date.py's
        # own real wall-clock default), and setInPlaceOnInUrl() deliberately drops
        # the `in-place-on` param entirely when it equals DEFAULT_IN_PLACE_ON (today) - "a
        # plain shared link never implies someone deliberately chose a date"
        # (that function's own comment) - so this test needs a row whose
        # run_date is NOT today, to actually exercise the in-place-on=<date> case,
        # not just whichever row happens to render first.
        toggle = clean_page.locator("#supply-history-toggle")
        if toggle.count():
            toggle.click()

        # RUN ROWS ONLY: a period with no supply (REQ-DASH-133) and a supply
        # waiting for a person sit in the same history with no run to set.
        rows = clean_page.locator(".supply-history tbody tr[data-run-date]")
        assert rows.count() > 0, "no real supply-history rows rendered - fixture/test drifted from real committed history"
        # THE PAGE'S OWN DEFAULT, not `date.today()`. This read the
        # CONTAINER's date until 2026-09-25, and the two are different
        # calendar days for eight hours out of every twenty-four: the
        # asset clock is Australia/Perth (REQ-PIPE-048), so between
        # 16:00 and 24:00 UTC the page's default as-of is already
        # tomorrow. The test then picked a row dated on the page's own
        # default, setInPlaceOnInUrl() correctly dropped the parameter, and
        # the assertion below failed on an entirely healthy page.
        #
        # Found by a real full-suite run in that window, 2026-09-25.
        # Exactly the class of bug the requirement this suite covers
        # exists to prevent, living in the test rather than the code -
        # and unfixable by choosing a better hardcoded date, since the
        # authoritative value is the one the code under test uses.
        today = clean_page.evaluate("() => DEFAULT_IN_PLACE_ON")
        run_dates = rows.evaluate_all("els => els.map(el => el.dataset.runDate)")
        target_run_date = next((d for d in run_dates if d != today), None)
        assert target_run_date, f"every real supply-history row is dated on the page's own default as-of ({today}) - can't exercise a real non-default as-of date"
        target_index = run_dates.index(target_run_date)

        rows.nth(target_index).click()
        clean_page.wait_for_timeout(300)

        assert f"in-place-on={target_run_date}" in clean_page.url


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
        # WAITED ON THE PAGE'S OWN SIGNAL, NOT A CLOCK (Keith, 2026-10-25,
        # morning report #9 (k)). A fixed 300ms read the attribute before the
        # reloaded page had applied the stored theme under a busy gate, and
        # the 10-second wait that replaced it ran out once in six module
        # runs. The render counter is set only after the main script's
        # applyTheme() has run, and the stored theme is applied before that
        # by the head script, so once the page has rendered the theme is
        # either applied or never will be - nothing is left to wait for.
        _wait_rendered(clean_page)
        after_reload = clean_page.evaluate("document.documentElement.getAttribute('data-theme')")

        assert after_reload == after_click
        assert clean_page.evaluate("localStorage.getItem('theme')") == after_click
        assert clean_page.locator("#theme-btn").inner_text() == (
            "☀️ Light mode" if after_click == "dark" else "🌙 Dark mode"), "applyTheme() ran with it"

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
            return clean_page.evaluate(r"""() => {
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

        _await_requirements_plans(clean_page)
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

        _await_requirements_plans(clean_page)
        rows_text = clean_page.locator("#requirements-panel-body").inner_text()

        assert "Signed off by" in rows_text

    def test_opening_it_is_a_real_history_entry_that_the_back_button_closes(self, clean_page, built_dashboard_html):
        """The 4 header side panels used to be DOM-only, outside browser
        history entirely - now unified under STATE.panel/?panel= (2026-09-18,
        running-thoughts.md #9, scoped via AskUserQuestion: Back should
        close a panel, same as the column/check drawers already do)."""
        _goto(clean_page, built_dashboard_html)

        clean_page.locator("#requirements-btn").click()

        _await_requirements_plans(clean_page)
        assert "panel=requirements" in clean_page.url
        assert clean_page.locator("#requirements-panel").get_attribute("aria-hidden") == "false"

        clean_page.go_back()
        clean_page.wait_for_timeout(300)

        assert "panel=requirements" not in clean_page.url
        assert clean_page.locator("#requirements-panel").get_attribute("aria-hidden") == "true"

    def test_the_status_filter_shows_only_the_chosen_status(self, clean_page, built_dashboard_html):
        """REQ-DOCS-143 criterion 7 - retired requirements are filterable,
        which needs a status filter at all. Asserted on the real register:
        choosing 'Built' leaves only Built pills, and 'All' brings the rest
        back."""
        _goto(clean_page, built_dashboard_html)
        clean_page.locator("#requirements-btn").click()
        _await_requirements_plans(clean_page)
        body = clean_page.locator("#requirements-panel-body")
        everything = body.inner_text()

        rows = body.locator("[data-req-row-status]")
        all_rows = rows.count()

        body.locator('[data-req-status="built"]').click()
        statuses = {rows.nth(i).get_attribute("data-req-row-status") for i in range(rows.count())}
        assert statuses == {"built"}, statuses
        assert rows.count() < all_rows, "the real register has unbuilt requirements to hide"

        body.locator('[data-req-status="all"]').click()
        assert rows.count() == all_rows
        assert body.inner_text() == everything


class TestARequirementHasItsOwnAddress:
    """REQ-DASH-222: `?panel=requirements&req=<id>` opens the Requirements
    panel at one requirement - cold-loaded, followed as a link, and
    stepped through with Back and Forward."""

    def _url(self, html_path, query):
        return f"file://{html_path.resolve()}?{query}"

    def _load(self, page, html_path, query):
        page.goto("about:blank")
        page.goto(self._url(html_path, query))
        page.wait_for_function("() => Number(document.documentElement.dataset.renderCount || 0) > 0")
        if "panel=requirements" in query:
            _await_requirements_plans(page)

    def _ids(self, page):
        _await_requirements_plans(page, start=True)
        ids = page.evaluate("() => REQUIREMENTS.map(r => [r.id, r.status])")
        assert ids, "precondition: the built dashboard embeds the register"
        return ids

    def _linked(self, page):
        return page.evaluate("""() => {
            const row = document.querySelector('#requirements-panel-body .req-linked');
            return row ? row.dataset.reqId : null; }""")

    def _add_link(self, page, rid):
        page.evaluate("""(id) => {
            const a = document.createElement('a');
            a.href = requirementHref(id); a.dataset.reqLink = id; a.id = 'e2e-req-link';
            a.textContent = id; document.getElementById('view').prepend(a); }""", rid)

    def _add_card_link(self, page, rid):
        """A link the view re-renders on Back, as a Feedback card's is: the
        page must find it again by the requirement it names."""
        page.evaluate("""(id) => {
            const original = window.render;
            window.render = function(){ original();
              const a = document.createElement('a');
              a.href = requirementHref(id); a.dataset.reqLink = id; a.className = 'e2e-card-link';
              a.textContent = id; document.getElementById('view').prepend(a); };
            window.render(); }""", rid)

    def test_a_cold_loaded_address_opens_the_panel_at_that_requirement(self, clean_page,
                                                                       built_dashboard_html):
        self._load(clean_page, built_dashboard_html, "panel=requirements")
        rid = self._ids(clean_page)[-1][0]
        self._load(clean_page, built_dashboard_html, f"panel=requirements&req={rid}")
        assert clean_page.locator("#requirements-panel").get_attribute("aria-hidden") == "false"
        assert self._linked(clean_page) == rid
        focused = clean_page.evaluate(
            "() => document.activeElement.closest('[data-req-id]')?.dataset.reqId || null")
        assert focused == rid
        assert "Linked here" in clean_page.locator(".req-linked").inner_text()

    def test_register_text_is_shown_as_text_never_read_as_markup(self, clean_page,
                                                                 built_dashboard_html):
        """post-build-review #265: the panel wrote register text into the
        page as HTML, so REQ-PIPE-257's "<script src>" opened a real script
        element and swallowed every requirement after it (231 of 272 shown),
        and placeholders such as <dataset> had always rendered as nothing."""
        self._load(clean_page, built_dashboard_html, "panel=requirements")
        found = clean_page.evaluate("""() => {
            const rows = new Map([...document.querySelectorAll(
                '#requirements-panel-body [data-req-id]')].map(e => [e.dataset.reqId, e.textContent]));
            const withMarkup = REQUIREMENTS.flatMap(r => (r.acceptance_criteria || [])
                .filter(c => /<[a-zA-Z]/.test(c)).map(c => [r.id, c]));
            return {rows: rows.size, total: REQUIREMENTS.length, checked: withMarkup.length,
                    missing: withMarkup.filter(([id, c]) => !(rows.get(id) || "").includes(c))
                                       .map(([id]) => id)};
        }""")
        assert found["checked"], "precondition: some criterion carries a <placeholder>"
        assert found["rows"] == found["total"]
        assert found["missing"] == []

    def test_every_row_carries_a_link_to_its_own_address(self, clean_page, built_dashboard_html):
        self._load(clean_page, built_dashboard_html, "panel=requirements")
        ids = self._ids(clean_page)
        hrefs = clean_page.evaluate("""() => [...document.querySelectorAll(
            '#requirements-panel-body [data-req-id] a[data-req-link]')].map(a => a.getAttribute('href'))""")
        assert len(hrefs) == len(ids)
        assert all("panel=requirements" in h and "req=" in h for h in hrefs)

    def test_following_a_link_pushes_one_entry_that_back_and_forward_step_through(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        rid = self._ids(clean_page)[0][0]
        self._add_card_link(clean_page, rid)
        before = clean_page.evaluate("() => history.length")
        clean_page.locator(".e2e-card-link").click()
        assert clean_page.evaluate("() => history.length") == before + 1
        assert f"req={rid}" in clean_page.url and self._linked(clean_page) == rid
        clean_page.go_back()
        clean_page.wait_for_function("() => !STATE.panel")
        assert "req=" not in clean_page.url
        assert clean_page.evaluate("() => document.activeElement.className") == "e2e-card-link"
        clean_page.go_forward()
        clean_page.wait_for_function("() => STATE.panel === 'requirements'")
        assert self._linked(clean_page) == rid

    def _follow_in_panel(self, page, rid):
        page.locator(f'#requirements-panel a[data-req-link="{rid}"]').first.click()
        page.wait_for_function("(r) => STATE.req === r", arg=rid)

    @pytest.mark.parametrize("close", ["Escape", "x"])
    def test_close_closes_after_following_links_inside_the_panel(
            self, clean_page, built_dashboard_html, close):
        """post-build-review #182, Keith 2026-10-14: 'Close always closes'.
        Each in-panel link pushed an entry and Close was Back, so the first
        press only stepped to the previous requirement."""
        _goto(clean_page, built_dashboard_html)
        before = clean_page.evaluate("() => history.length")
        ids = [r for r, _ in self._ids(clean_page)][:3]
        clean_page.locator("#requirements-btn").click()
        _await_requirements_plans(clean_page)
        clean_page.wait_for_function("() => STATE.panel === 'requirements'")
        self._follow_in_panel(clean_page, ids[1])
        self._follow_in_panel(clean_page, ids[2])
        clean_page.go_back()
        clean_page.wait_for_function("(r) => STATE.req === r", arg=ids[1])
        if close == "Escape":
            clean_page.keyboard.press("Escape")
        else:
            clean_page.locator("#requirements-panel-close").click()
        clean_page.wait_for_function("() => !STATE.panel")
        assert clean_page.locator("#requirements-panel").get_attribute("aria-hidden") == "true"
        assert "panel=" not in clean_page.url and "req=" not in clean_page.url
        # Closing stepped back to the page the panel was opened over.
        assert clean_page.evaluate("() => history.length") >= before

    def test_close_closes_a_cold_loaded_panel_after_following_a_link(
            self, clean_page, built_dashboard_html):
        self._load(clean_page, built_dashboard_html, "panel=requirements")
        ids = [r for r, _ in self._ids(clean_page)][:2]
        self._load(clean_page, built_dashboard_html, f"panel=requirements&req={ids[0]}")
        self._follow_in_panel(clean_page, ids[1])
        clean_page.keyboard.press("Escape")
        clean_page.wait_for_function("() => !STATE.panel")
        assert clean_page.locator("#requirements-panel").get_attribute("aria-hidden") == "true"
        assert "qa-reporting-dashboard" in clean_page.url
        assert "panel=" not in clean_page.url and "req=" not in clean_page.url

    def test_a_requirement_hidden_by_the_status_filter_resets_it(self, clean_page,
                                                                 built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        ids = self._ids(clean_page)
        hidden = next(i for i, st in ids if st != "built")
        clean_page.locator("#requirements-btn").click()
        _await_requirements_plans(clean_page)
        clean_page.locator('#requirements-panel-body [data-req-status="built"]').click()
        clean_page.locator("#requirements-panel-close").click()
        clean_page.wait_for_function("() => !STATE.panel")
        self._add_link(clean_page, hidden)
        clean_page.locator("#e2e-req-link").click()
        assert self._linked(clean_page) == hidden
        assert clean_page.evaluate("() => REQ_STATUS_FILTER") == "all"

    def test_an_unknown_id_opens_at_the_top_with_the_stale_notice(self, clean_page,
                                                                  built_dashboard_html):
        self._load(clean_page, built_dashboard_html, "panel=requirements&req=REQ-NOPE-999")
        notice = clean_page.locator("#requirements-panel-body .stale-link-notice")
        assert notice.count() == 1 and notice.get_attribute("role") == "status"
        assert "REQ-NOPE-999" in notice.inner_text()
        assert "req=" not in clean_page.url and "panel=requirements" in clean_page.url
        assert self._linked(clean_page) is None

    def test_req_beside_another_panel_is_dropped(self, clean_page, built_dashboard_html):
        self._load(clean_page, built_dashboard_html, "panel=activity&req=REQ-DASH-222")
        assert clean_page.locator("#activity-panel").get_attribute("aria-hidden") == "false"
        assert "req=" not in clean_page.url

    def test_an_empty_req_is_dropped_and_the_panel_opens_at_the_top(self, clean_page,
                                                                     built_dashboard_html):
        """post-build-review #182: `req=` with no value used to stay in the
        address, so a copied link carried a parameter that meant nothing."""
        self._load(clean_page, built_dashboard_html, "panel=requirements&req=")
        assert clean_page.locator("#requirements-panel").get_attribute("aria-hidden") == "false"
        assert "req=" not in clean_page.url and "panel=requirements" in clean_page.url
        assert clean_page.locator(".req-linked").count() == 0

    def test_closing_a_cold_loaded_one_drops_both_parameters(self, clean_page,
                                                             built_dashboard_html):
        self._load(clean_page, built_dashboard_html, "panel=requirements")
        rid = self._ids(clean_page)[0][0]
        self._load(clean_page, built_dashboard_html, f"panel=requirements&req={rid}")
        clean_page.keyboard.press("Escape")
        clean_page.wait_for_function("() => !STATE.panel")
        assert "qa-reporting-dashboard" in clean_page.url
        assert "req=" not in clean_page.url and "panel=" not in clean_page.url

    def test_the_header_button_opens_at_the_top_without_req(self, clean_page,
                                                            built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        rid = self._ids(clean_page)[-1][0]
        self._add_link(clean_page, rid)
        clean_page.locator("#e2e-req-link").click()
        clean_page.locator("#requirements-panel-close").click()
        clean_page.wait_for_function("() => !STATE.panel")
        clean_page.locator("#requirements-btn").click()
        _await_requirements_plans(clean_page)
        assert "panel=requirements" in clean_page.url and "req=" not in clean_page.url
        assert self._linked(clean_page) is None

    def test_navigating_away_does_not_carry_the_panel_or_req(self, clean_page,
                                                             built_dashboard_html):
        self._load(clean_page, built_dashboard_html, "panel=requirements")
        rid = self._ids(clean_page)[0][0]
        self._load(clean_page, built_dashboard_html, f"panel=requirements&req={rid}")
        clean_page.evaluate("() => navigate({tier:'exec'})")
        assert "req=" not in clean_page.url and "panel=" not in clean_page.url


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


@pytest.fixture(scope="class")
def dashboard_html_with_ticket(built_dashboard_html, tmp_path_factory) -> Path:
    """CLASS-SCOPED (2026-09-27) because it rebuilds the dashboard, and
    that costs ~6.5s every time. Function-scoped it was paid once per
    TEST; the three fixtures of this shape accounted for about 65s of a
    230s module. Nothing here mutates the built file, so one per class
    is the same guarantee for a fraction of the cost.

    It takes `tmp_path_factory` and its own `MonkeyPatch.context()`
    rather than `tmp_path`/`monkeypatch`, which are function-scoped and
    cannot be requested from a class-scoped fixture.

    Item 76's UI-integration follow-up (plans/qa-pipeline.md,
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

    Built by _embed_variant from THIS WORKER'S own reports (REQ-TEST-281
    criterion 6), with the ticket written to the variant's own
    `reports/open_tickets.json` - where an `--out-dir` build reads it -
    and fonts/ and vendor/ placed beside it by the build itself."""
    return _embed_variant(built_dashboard_html, tmp_path_factory.mktemp("ticket"), reports={
        "open_tickets.json": [{
            "number": 999, "title": "Birth Registrations is red",
            "url": "https://github.com/keithamoss/data-poc/issues/999",
            "labels": [{"name": "qa-ticket"}, {"name": "dataset:birth-registrations"}],
            "updatedAt": "2026-09-18T00:00:00Z",
        }]})


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


class TestOwedNothingPeriods:
    """REQ-DASH-182 on the real built dashboard. Criterion 15 is a
    REGRESSION GUARD (Keith, 2026-10-14, review Q2): it passes on today's
    page, and asserts first that the date is one the dataset owes nothing
    in, so it cannot pass vacuously."""

    CP = "child-protection-family-support"
    DS = {"tier": "dataset", "agencyId": CP, "collectionId": "child-protection",
          "datasetId": "cp-case-workers"}
    #: The agency page carries each collection's table of datasets.
    COLLECTION = {"tier": "agency", "agencyId": CP}
    #: In a May quarter, after cp-case-workers' first supply.
    ON = "2025-06-15"

    def _owes_nothing_on(self, page, date):
        return page.evaluate(
            """(date) => {
                const raw = rawRealDatasetById('cp-case-workers');
                const period = periodNameFor('cp-case-workers', date);
                const supplied = (raw.runs || []).some(r => r.run_date <= date);
                return supplied && (raw.owedNothing || []).some(e => e.period === period);
            }""", date)

    def test_an_owed_nothing_quarter_is_not_stale_on_the_page(self, page, built_dashboard_html):
        _goto(page, built_dashboard_html, state=self.DS, in_place_on=self.ON)
        assert self._owes_nothing_on(page, self.ON), "precondition: an owed-nothing date"
        text = " ".join(page.locator("#view").inner_text().split())
        assert "nothing has landed yet" not in text
        assert "No data" not in page.locator(".view-head").inner_text()

    def test_nor_in_its_collection_table(self, page, built_dashboard_html):
        _goto(page, built_dashboard_html, state=self.COLLECTION, in_place_on=self.ON)
        assert self._owes_nothing_on(page, self.ON), "precondition: an owed-nothing date"
        row = page.locator("tr", has_text="Case Workers").first
        assert row.count() == 1
        # THE WORDS, not the class: the timing pill "Not filed to a slot"
        # shares .pill.nodata and says nothing about staleness.
        text = " ".join(row.inner_text().split())
        assert "No data" not in text and "nothing has landed yet" not in text

    def test_the_period_is_a_quiet_row_and_the_tile_names_its_own_months(self, page,
                                                                         built_dashboard_html):
        _goto(page, built_dashboard_html, state=self.DS, in_place_on=self.ON)
        # THE VISIBLE CURRENT BLOCK, not the first match, which may be a hidden
        # older one (post-build-review #194 F1). This period also holds a
        # supply (cp-case-workers' unfiled May files), so since Q18 (REQ-DASH-
        # 182 criterion 12 as amended 2026-10-15) it is ONE block - the supply's
        # cycle with the period's label beneath - never a second row.
        sub = page.locator(".supply-history > .supply-cycle [data-owed-nothing-sub]")
        assert sub.count() == 1 and sub.is_visible()
        assert "Not owed — outside its agreed months (Feb, Aug)" in sub.inner_text()
        label = sub.locator("xpath=ancestor::div[contains(@class,'supply-cycle-label')][1]")
        assert "Current cycle" in label.inner_text()
        assert page.locator(".supply-history > [data-owed-nothing]").count() == 0
        tile = page.locator(".sla-tile", has_text="SLA").first.inner_text()
        assert "Twice a year (Feb, Aug, day 1), by 09:00" in tile
        assert "staffing register" in tile

    def test_rows_show_before_anything_is_supplied(self, page, built_dashboard_html):
        """post-build-review #194 F2 (criterion 1, 'even where the dataset has
        no supply cycles yet'): the never-supplied branch drew no history.
        The real data has no such dataset, so one is made from cp-case-workers
        by dropping its early runs and adding a not_expected first period."""
        _goto(page, built_dashboard_html, state=self.DS, in_place_on="2023-03-15")
        page.evaluate("""() => {
            const raw = rawRealDatasetById('cp-case-workers');
            raw.runs = raw.runs.filter(r => r.run_date >= '2023-04-01');
            raw.owedNothing = [{period: '2023-Q1', date: '2023-02-01', kind: 'not_expected',
                                reason: 'System migration', months: null}, ...(raw.owedNothing || [])];
            DATA = buildData(CURRENT_IN_PLACE_ON);
            render();
        }""")
        assert page.evaluate("""() => {
            const raw = rawRealDatasetById('cp-case-workers');
            return !raw.runs.some(r => r.run_date <= '2023-03-15')
                && raw.owedNothing.some(e => e.period === periodNameFor('cp-case-workers', '2023-03-15'));
        }"""), "precondition: nothing supplied, and the date is owed nothing"
        rows = page.locator("[data-owed-nothing]")
        assert rows.count() >= 1
        assert "Not expected — System migration" in rows.first.inner_text()


class TestTurnedOffOnThePage:
    """REQ-DASH-180 in a real browser. The real configuration turns nothing
    off, so a turn-off is added to cp-clients' embedded data in the page and
    the page rebuilt from it - every reading after that is the page's own."""

    CP = "child-protection-family-support"
    DS = {"tier": "dataset", "agencyId": CP, "collectionId": "child-protection",
          "datasetId": "cp-clients"}
    ON = "2026-06-15"
    TURN = """{effectiveTo: '2026-03-31', until: null, reason: 'Supplier <b>paused</b>',
               level: 'dataset', versionFrom: '2023-01-01', authoredOn: '2026-01-10',
               authoredBy: 'changelog', collection: 'Child Protection',
               lastOwed: {period: '2026-Q1', dueAt: '2026-02-01T01:00:00+00:00',
                          closesAt: '2026-04-20T16:00:00+00:00'}}"""

    def _turn_off(self, page):
        page.evaluate(f"""() => {{
            rawRealDatasetById('cp-clients').turnOffs = [{self.TURN}];
            DATA = buildData(CURRENT_IN_PLACE_ON);
            render();
        }}""")

    def test_the_dataset_page_reads_turned_off(self, page, built_dashboard_html):
        _goto(page, built_dashboard_html, state=self.DS, in_place_on=self.ON)
        self._turn_off(page)
        head = page.locator(".view-head")
        marker = head.locator(".turnoff-marker")
        assert marker.count() == 1
        assert "Turned off since" in marker.inner_text()
        assert marker.get_attribute("title") == "Supplier <b>paused</b>"
        # The reason as visible text, as text (criteria 2 and 21).
        why = page.locator("[data-turn-off-reason]")
        assert why.inner_text().strip() == "Supplier <b>paused</b>"
        assert page.locator("[data-turn-off-reason] b").count() == 0
        tile = page.locator(".sla-tile", has_text="SLA").first.inner_text()
        assert "Turned off — nothing due" in tile

    def test_its_collection_row_carries_the_marker(self, page, built_dashboard_html):
        _goto(page, built_dashboard_html, state={"tier": "agency", "agencyId": self.CP},
              in_place_on=self.ON)
        self._turn_off(page)
        row = page.locator("tr", has_text="Client Register").first
        assert row.locator(".turnoff-marker").count() == 1
        # THE BAR ICON, not the small pills' square (post-build-review #195 D3).
        size = row.locator(".turnoff-marker .ico").evaluate(
            "e => [getComputedStyle(e).width, getComputedStyle(e).height]")
        assert size == ["8px", "2px"]
        # OUT OF THE ROLLUP ONLY WHILE NOTHING ABOUT AN OWED PERIOD WAITS
        # (criteria 6 and 7) - the real cp-clients may have something waiting.
        got = page.evaluate("""() => {
            const ds = DATA.agencies.flatMap(a => a.collections).flatMap(c => c.datasets)
                .find(d => d.id === 'cp-clients');
            return {phase: ds.turnOff.phase, out: ds.turnedOffOutOfRollup,
                    waiting: !!(ds.blocked || ds.waitingBlocker || ds.noSupply)};
        }""")
        assert got["phase"] == "off"
        assert got["out"] is (not got["waiting"])


class TestPlacedOnThePage:
    """REQ-DASH-175 in a real browser. No real supply has been placed by a
    person, so a placement of one of cp-clients' real runs is added to its
    embedded data and the page rebuilt from it."""

    CP = "child-protection-family-support"
    DS = {"tier": "dataset", "agencyId": CP, "collectionId": "child-protection",
          "datasetId": "cp-clients"}

    def test_the_tag_is_in_the_provenance_cell_not_the_timing_cell(self, page,
                                                                   built_dashboard_html):
        _goto(page, built_dashboard_html, state=self.DS)
        run_id = page.evaluate("""() => {
            const raw = rawRealDatasetById('cp-clients');
            const run = raw.runs[raw.runs.length - 1];
            raw.placements = {'cp-clients@x': {period: '2026-Q3', at: run.run_date + 'T00:00:00+00:00',
              actor: 'Keith Moss', reason: 'placed by hand', when: 'closed', runId: run.run_id}};
            DATA = buildData(CURRENT_IN_PLACE_ON);
            render();
            return run.run_id;
        }""")
        if page.locator("#supply-history-toggle").count():
            page.click("#supply-history-toggle")
        tag = page.locator("[data-placed]")
        assert tag.count() == 1
        row = page.locator("tr", has=tag)
        cells = row.locator("td")
        # The last cell says how the row came to be in its cycle; the third is timing.
        assert cells.last.locator("[data-placed]").count() == 1
        assert cells.nth(2).locator("[data-placed]").count() == 0
        assert "placed by hand" in cells.last.inner_text()
        assert run_id


class TestAcknowledgementBadge:
    """REQ-PIPE-122 criterion 21, which replaced REQ-QAC-017's per-run
    /accept badge (retired by criterion 23): a promoted amber supply reads
    "awaiting acknowledgement" from its promotion and "acknowledged by"
    from the acknowledgement, judged as at the date on show. Injected onto
    a real supply-history row, so it does not depend on which supplies a
    bootstrap happened to promote under promote-and-acknowledge."""

    PROMOTED = "2026-09-10T02:00:00+00:00"
    ACKNOWLEDGED = "2026-09-15T02:00:00+00:00"

    def _page(self, built, tmp_path, acks=None):
        data = _collection_data(built)
        record = next(d for entry in data.values() for d in entry["datasets"]
                      if d["id"] == "birth-registrations")
        run_id = record["runs"][-1]["run_id"]
        record["acknowledgements"] = {run_id: {
            "supply": "birth-registrations@k", "period": "p", "promotedAt": self.PROMOTED,
            "acknowledged": {"actor": "Keith Moss", "reason": "looked", "at": self.ACKNOWLEDGED},
            "lapsedAt": None, **({"acks": acks} if acks is not None else {})}}
        out = tmp_path / "ack.html"
        for name in ("fonts", "vendor"):
            if not (tmp_path / name).exists():
                (tmp_path / name).symlink_to((built.parent / name).resolve())
        out.write_text(_with_collection_data_inline(built.read_text(), data))
        return out, run_id

    def _badge(self, page, run_id, in_place_on):
        return page.evaluate(f"() => acknowledgementBadge('birth-registrations', '{run_id}', '{in_place_on}')")

    def test_it_reads_as_at_the_date_on_show(self, page, tmp_path, built_dashboard_html):
        out, run_id = self._page(built_dashboard_html, tmp_path)
        _goto(page, out)
        assert self._badge(page, run_id, "2026-09-05") == ""
        assert "awaiting acknowledgement" in self._badge(page, run_id, "2026-09-12")
        assert "Acknowledged by Keith Moss" in self._badge(page, run_id, "2026-09-20")

    def test_a_withdrawn_one_reads_as_at_the_date_on_show(self, page, tmp_path,
                                                          built_dashboard_html):
        """REQ-PIPE-166 criteria 13, 16 and 17 in a real browser
        (post-build-review #193 F6): standing before the withdrawal with its
        reason as visible text, awaiting again from it with the withdrawn one
        beneath, and the newer acknowledgement standing once given."""
        first = {"actor": "Keith Moss", "reason": "looked", "at": self.ACKNOWLEDGED,
                 "withdrawn": {"actor": "Ana Lee", "reason": "wrong supply",
                               "at": "2026-09-18T02:00:00+00:00"}}
        again = {"actor": "Bo Chen", "reason": "second look",
                 "at": "2026-09-22T02:00:00+00:00", "withdrawn": None}
        out, run_id = self._page(built_dashboard_html, tmp_path, acks=[first, again])
        _goto(page, out)
        before = self._badge(page, run_id, "2026-09-16")
        assert "Acknowledged by Keith Moss" in before and "withdrawn" not in before
        page.set_content(f"<div id=b>{before}</div>")
        assert page.locator("[data-acknowledgement-reason]").inner_text().strip() == "looked"
        _goto(page, out)
        between = self._badge(page, run_id, "2026-09-20")
        assert "awaiting acknowledgement" in between
        assert "withdrawn by Ana Lee" in between and "wrong supply" in between
        after = self._badge(page, run_id, "2026-09-23")
        assert "Acknowledged by Bo Chen" in after
        assert "awaiting acknowledgement" not in after


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
      for (const raw of Object.values(COLLECTION_DATA)) {
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

    _IN_PLACE_ON_JS = """() => {
      let compared = 0;
      const disagreements = [];
      for (const raw of Object.values(COLLECTION_DATA)) {
        if (!raw) continue;
        for (const d of (raw.datasets ? raw.datasets : [raw])) {
          for (const r of d.runs) {
            const date = String(r.run_date).slice(0, 10);
            const clipped = clipDatasetToInPlaceOn(d, date);
            if (!clipped || !clipped.runs.length) continue;
            // THE NEWEST RESULT RECORDED BY THEN (REQ-DASH-264 criterion 1):
            // from the dataset's own runs on show or any other table's run -
            // worked out here from the raw history, not from the page's own
            // filter. NEWEST BY THE BUILD'S RANK (REQ-PIPE-279 criteria 9 and
            // 16): this picked the latest recorded_at, an order the rule now
            // forbids; recorded_at still decides only what is recorded BY the
            // date on show, as the page's clip does.
            const own = new Set(clipped.runs.map(x => x.run_id));
            const raw = new Map(d.columns.flatMap(c => c.checks).map(ck => [ck.check_id || ck.key, ck]));
            const built = buildRealDataset(clipped);
            // THE SUPPLY ON SHOW, whose counted answer a cross-table card
            // carries (REQ-DASH-264 criterion 1 as amended by REQ-PIPE-269).
            const onShow = clipped.runs[clipped.runs.length - 1].supply_id;
            built.columns.forEach(c => c.checks.forEach(ck => {
              if (ck.blockedThisPeriod) return;   // a held table's own check: criterion 3, tested apart
              const rawCk = raw.get(ck.check_id || ck.key) || {history: []};
              let h = null;
              if (rawCk.counted && onShow) {
                // COUNTED TOWARD THE SUPPLY ON SHOW: the build's answer for
                // that supply on that date, looked up in the raw data - a
                // result about another supply, or a partner not in the
                // warehouse, is never the current one.
                const point = newestOnOrBefore(rawCk.counted[onShow], date);
                if (!point || point.rank == null) {
                  compared++;
                  const want = point && point.reason !== "not-counted" ? "red" : "nodata";
                  const got = checkStatus(ck);
                  if (got !== want && disagreements.length < 10) {
                    disagreements.push({dataset: d.id, inPlaceOn: date, check: ck.check_id || ck.id,
                                        counted: point && point.reason, tool: want, rendered: got});
                  }
                  return;
                }
                h = [...rawCk.history, ...(rawCk.superseded || [])]
                  .find(x => x.rank === point.rank) || null;
              } else {
                // AND A SUPERSEDED RUN'S, while the run that replaced it is not
                // yet recorded (post-build-review #266, Keith answer A).
                const by = x => !x.recorded_at || assetDateStrOf(x.recorded_at) <= date;
                const all = [...rawCk.history, ...(rawCk.superseded || [])];
                for (const x of all) {
                  const replacedBy = x.replaced_by;
                  if (replacedBy) {
                    if (!(own.has(x.supply_run) || x.recorded_by)) continue;
                    if (all.some(y => y.run_id === replacedBy && by(y))) continue;
                  } else if (!(own.has(x.run_id) || x.recorded_by)) continue;
                  if (!by(x)) continue;
                  if (!h || x.rank >= h.rank) h = x;
                }
              }
              if (!h || !h.status) return;
              compared++;
              const got = checkStatus(ck);
              if (got !== h.status && disagreements.length < 10) {
                disagreements.push({dataset: d.id, inPlaceOn: date, check: ck.check_id || ck.id,
                                    tool: h.status, rendered: got});
              }
            }));
          }
        }
      }
      return {compared, disagreements};
    }"""

    def test_on_every_past_date_too(self, clean_page, built_dashboard_html):
        """dashboard UX critic on 8a942e7, H2: a past date kept each check's
        NEWEST status, so 96 of 227 checks as of 2 May 2026 rendered a
        colour their own run did not record - a check red that day read
        green. This test only ever looked at the default date. Since
        REQ-DASH-264 the expected verdict is the newest one RECORDED by the
        date, whichever table's run recorded it - and since REQ-PIPE-269, for
        a cross-table check, the newest one COUNTED toward the supply on
        show (REQ-DASH-264 criterion 1 as amended). And since Keith's answer A
        to post-build-review #266, a superseded run's result until the run
        that replaced it was recorded."""
        _goto(clean_page, built_dashboard_html)
        result = clean_page.evaluate(self._IN_PLACE_ON_JS)
        assert result["compared"] > 100, result
        assert result["disagreements"] == [], (
            "on a past date the page disagrees with the run it shows:\n"
            + "\n".join(str(d) for d in result["disagreements"]))

    def test_every_rendered_status_matches_the_tool_that_produced_it(self, clean_page, built_dashboard_html,
                                                                       deployment_history):
        _goto(clean_page, built_dashboard_html)
        result = clean_page.evaluate(self._COMPARE_JS)

        # This guard exists so a broken traversal cannot pass vacuously
        # by comparing nothing. It used to read `> 10000`, a figure tied
        # to BDM's 352-run history; cutting that to 30 deliveries on
        # 2026-09-23 left 7,011 real comparisons and this fired BEFORE
        # the disagreement check below - so the test reported a failure
        # while the statuses it exists to police were in fact perfect.
        #
        # The floor is derived from the data the page was built from:
        # every recorded run contributes statuses, so comparing fewer than
        # one per run means the traversal, not the history. COUNTED IN THE
        # DATABASE (Keith, 2026-10-12, docs/test-review-pass2.md): it used
        # to count the deleted qa_results/ tree, so the floor had silently
        # become zero.
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(label="test-e2e") as conn:
            recorded_runs = conn.execute(
                f'SELECT count(*) FROM "{qa_store.SCHEMA}".run').fetchall()[0][0]
        assert recorded_runs > 0, "no recorded runs - the floor would be vacuous"
        assert result["compared"] > recorded_runs, (
            f"only {result['compared']} statuses compared across {recorded_runs} "
            "recorded runs - the embedded data or the traversal is wrong, "
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
          for (const raw of Object.values(COLLECTION_DATA)) {
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
                // A cross-table GRID row is one check, every tool's result in
                // its cells (REQ-DASH-272), so it names no single tool.
                tool: (r.querySelector('.tr') || {}).textContent || null,
                between: (r.querySelector('.bt') || {}).textContent || null,
            })),
        }))""")

    def test_every_section_renders_above_the_column_grid(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, self._CP)

        sections = self._sections(clean_page)
        # REQ-QAC-037 added the third. The ORDER is asserted, not just
        # the set: supply, then table, then cross-table reads outward
        # from the dataset, and a section appearing in a different place
        # each page would be its own defect.
        assert [s["scope"] for s in sections] == ["supply", "table", "cross-table"]
        assert clean_page.evaluate("""() => {
            const wrap = document.getElementById('scope-sections');
            const grid = document.getElementById('col-grid');
            return !!(wrap.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING);
        }""")

    def test_an_empty_table_section_shows_and_a_one_table_cross_table_section_does_not(
            self, clean_page, built_dashboard_html):
        """Real on today's data - Birth Registrations has supply-level checks
        and no table-level ones. It used to leave the empty section out;
        since REQ-QAC-247 (Keith, 2026-10-18) a missing rule is shown, as it
        always was for Child Protection, but a collection with one table
        never shows a Cross-table section it could not fill.

        IN PLACE ON ITS NEWEST SUPPLY'S DAY, read from the data: a daily
        dataset read on today's date has no current supply once its history
        ends, and every section reads "No data" (CLAUDE.md's shelf-life note)."""
        from qa_tools import collections

        built = json.loads((_reports_of(built_dashboard_html) / collections.by_id(
            "civil-registration").dashboard_file).read_text())
        newest = max(r["run_date"] for r in built["datasets"][0]["runs"])
        _goto(clean_page, built_dashboard_html, _BDM, in_place_on=newest)

        sections = self._sections(clean_page)
        assert [s["scope"] for s in sections] == ["supply", "table"]
        table = sections[1]
        assert [r["name"] for r in table["rows"]] == ["No automated quality rule defined"]
        assert table["status"] == "No rule defined"

    def test_each_section_carries_its_own_status(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, self._CP)

        by_scope = {s["scope"]: s["status"] for s in self._sections(clean_page)}
        assert set(by_scope) == {"supply", "table", "cross-table"}
        for status in by_scope.values():
            assert status in {"Green", "Amber", "Red", "No rule defined", "No data"}
        # they are genuinely rolled up independently, not all three
        # showing the dataset's own status
        assert len(set(by_scope.values())) > 1

    def test_a_section_with_no_real_check_does_not_claim_green(
            self, clean_page, built_dashboard_html):
        """A real false green, found 2026-09-26.

        post-build-review #4 already settled this - `rollupStatuses()`
        carries a comment saying in as many words that "a section whose
        only check is a placeholder rolls up GREEN ... precisely the
        false green that finding is about". The fix went into that
        function and the SECTION renderer kept its own reduce over
        STATUS_ORDER, which has no entry for `inactive`, so the
        comparison was always false and the seed value survived.

        It became visible when REQ-QAC-037 moved cp-placements' two
        table-level business rules into the cross-table section, leaving
        its table section with nothing but the placeholder - and a Green
        pill over the words "No automated quality rule defined".
        """
        _goto(clean_page, built_dashboard_html, self._CP)

        table = next(s for s in self._sections(clean_page) if s["scope"] == "table")
        assert [r["name"] for r in table["rows"]] == ["No automated quality rule defined"], (
            "this dataset has a real table-level check now - the test needs a "
            "different one, not deleting")
        assert table["status"] == "No rule defined"

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

        sections = self._sections(clean_page)
        # THE CROSS-TABLE SECTION IS ONE ROW PER CHECK (REQ-DASH-272 criterion
        # 6, amending REQ-DASH-264 criterion 2): the three tools' results sit
        # in the row's cells as marks, so no two rows share a name AND tables.
        (cross,) = [s for s in sections if s["scope"] == "cross-table"]
        keys = [(r["name"], r["between"]) for r in cross["rows"]]
        assert keys and len(keys) == len(set(keys)), keys
        rows = [r for s in sections if s["scope"] != "cross-table" for r in s["rows"]]
        by_name: dict[str, list[str]] = {}
        for row in rows:
            by_name.setdefault(row["name"], []).append(row["tool"])
        shared = {name: tools for name, tools in by_name.items() if len(tools) > 1}
        if not shared:
            # Every name the tools share on this page is a cross-table check's,
            # which the grid shows once, its tools as marks.
            return
        # Per NAME, not across the whole section. Two differently-named
        # rows may legitimately share a tool - "Client reference" and
        # "Carer reference" are both soda:relationships - and an
        # assertion over all repeated rows at once forbids that, which
        # is a rule this page has never had.
        for name, tools in shared.items():
            assert len(set(tools)) == len(tools), f"{name!r} repeats a tool: {tools}"

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
        rendered = clean_page.evaluate("""() => buildData(CURRENT_IN_PLACE_ON).agencies.map(a => ({
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
    def test_the_default_in_place_on_date_is_the_assets_date_whatever_zone_the_viewer_is_in(
            self, browser, built_dashboard_html, viewer_tz):
        context = browser.new_context(timezone_id=viewer_tz)
        try:
            page = context.new_page()
            page.goto(f"file://{built_dashboard_html}")
            page.wait_for_timeout(400)
            got = page.evaluate("() => ({today: liveNowDateStr(), default: defaultInPlaceOn()})")
        finally:
            context.close()
        assert got["today"] == self._asset_today(), (
            f"a viewer in {viewer_tz} sees {got['today']} as today; the asset's date is "
            f"{self._asset_today()}")
        assert got["default"] == self._asset_today()

    def test_the_page_knows_which_zone_that_is(self, clean_page, built_dashboard_html):
        """Guards the assertions above against going green by accident.
        With ASSET_TIMEZONES absent the page falls back to the viewer's
        own clock, which agrees with the asset's for most of the day -
        so every test above would pass on the broken build for sixteen
        hours out of every twenty-four."""
        from qa_tools.common import asset_time
        _goto(clean_page, built_dashboard_html, {"tier": "executive"})
        # EVERY VERSION (REQ-PIPE-112 criterion 11), as the config states them.
        assert clean_page.evaluate("() => ASSET_TIMEZONES") == [
            {"effective_from": v.effective_from.isoformat(), "zone": v.zone.key}
            for v in asset_time.timezone_versions()]


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

    THE WINDOW STARTS WHEN ITS LAST SLOT CLOSES (REQ-DASH-155 criterion 6;
    Keith, 2026-10-06), not at 2027-Q3's own date: the Q3 slot stays open
    until Q4's claim window opens in late October, and its siblings' Q4
    slot until early 2028. 15 September, the old date, is inside the open
    Q3 slot, where the pipeline still files a supply.
    """

    ONE_EXHAUSTED = "2027-12-15"
    ALL_EXHAUSTED = "2028-06-01"
    NONE_EXHAUSTED = "2026-09-23"
    CP = "child-protection-family-support"
    DS = {"tier": "dataset", "agencyId": CP, "collectionId": "child-protection",
          "datasetId": "cp-case-workers"}

    def test_nothing_is_said_while_the_calendar_still_has_dates(self, page, dashboard_html_without_blockers):
        _goto(page, dashboard_html_without_blockers, in_place_on=self.NONE_EXHAUSTED)
        assert page.locator(".notice-exhausted").count() == 0

    def test_the_executive_tier_says_how_many_above_the_grid(self, page, dashboard_html_without_blockers):
        _goto(page, dashboard_html_without_blockers, in_place_on=self.ONE_EXHAUSTED)
        notice = page.locator(".notice-exhausted")
        assert notice.count() == 1
        text = " ".join(notice.inner_text().split())
        assert "1 dataset cannot be filed" in text
        assert "delivery dates have run out" in text
        assert "Case Workers" in text, "the dataset is named (post-build-review #132 A4)"

    def test_the_count_tracks_the_in_place_on_date(self, page, dashboard_html_without_blockers):
        _goto(page, dashboard_html_without_blockers, in_place_on=self.ALL_EXHAUSTED)
        text = " ".join(page.locator(".notice-exhausted").inner_text().split())
        # Every dataset on the quarterly calendar, from configuration, so a
        # new quarterly collection (Emergency Department) is counted.
        from qa_tools.common import hierarchy, schedule
        quarterly = []
        for ds in hierarchy.all_datasets():
            try:
                if schedule.calendar_for_dataset(ds.dataset_id).name == "quarterly":
                    quarterly.append(ds.dataset_id)
            except schedule.NoCalendarAgreed:
                pass
        assert len(quarterly) > 1
        assert f"{len(quarterly)} datasets cannot be filed" in text

    def test_the_notice_names_the_file_to_edit(self, page, dashboard_html_without_blockers):
        _goto(page, dashboard_html_without_blockers, in_place_on=self.ONE_EXHAUSTED)
        text = " ".join(page.locator(".notice-exhausted").inner_text().split())
        assert "contract/calendar.yaml" in text
        assert "candidate-dates" in text, "and how to get the next dates proposed"

    def test_the_notice_cannot_be_dismissed(self, page, dashboard_html_without_blockers):
        """A dismissible notice about a task nobody has done is a notice
        about a task nobody will do - and a dismissal persisted in
        browser storage would hide it for that person permanently."""
        _goto(page, dashboard_html_without_blockers, in_place_on=self.ONE_EXHAUSTED)
        assert page.locator(".notice-exhausted button").count() == 0
        assert page.locator(".notice-exhausted [role=button]").count() == 0
        stored = page.evaluate(
            "() => JSON.stringify({l: {...localStorage}, s: {...sessionStorage}})")
        assert "exhaust" not in stored.lower(), stored
        assert "dismiss" not in stored.lower(), stored

    def test_one_exhausted_dataset_among_five_healthy_is_not_swallowed(self, page, dashboard_html_without_blockers):
        """The nodata trap, at the tier it would vanish from."""
        _goto(page, dashboard_html_without_blockers, state={"tier": "agency", "agencyId": self.CP},
              in_place_on=self.ONE_EXHAUSTED)
        rows = page.locator("tr", has=page.locator("td", has_text="Delivery schedule ended"))
        assert rows.count() == 1
        assert "Case Workers" in rows.first.inner_text()

    def test_the_dataset_itself_says_so_in_its_own_words(self, page, dashboard_html_without_blockers):
        _goto(page, dashboard_html_without_blockers, state=self.DS, in_place_on=self.ONE_EXHAUSTED)
        text = " ".join(page.locator("#view").inner_text().split())
        assert "delivery schedule has ended" in text.lower()
        assert "contract/calendar.yaml" in text

    def test_it_names_the_datasets_own_last_period_not_its_calendars(self, page, dashboard_html_without_blockers):
        """cp-case-workers' last owed period is 2027-Q3; the quarterly
        calendar runs to 2027-Q4. Naming the calendar's would tell a
        reader their dataset ended after a period it never had."""
        _goto(page, dashboard_html_without_blockers, state=self.DS, in_place_on=self.ONE_EXHAUSTED)
        text = " ".join(page.locator("#view").inner_text().split())
        assert "2027-Q3" in text
        assert "2027-Q4" not in text

    def test_it_reads_differently_from_a_dataset_that_simply_has_no_run(self, page, dashboard_html_without_blockers):
        """Both are quiet tiles. Only one of them is somebody's job, and
        identical wording is exactly what would hide that."""
        _goto(page, dashboard_html_without_blockers, state=self.DS, in_place_on=self.ONE_EXHAUSTED)
        ended = " ".join(page.locator("#view").inner_text().split())
        _goto(page, dashboard_html_without_blockers, state=self.DS, in_place_on="2023-01-01")
        no_run = " ".join(page.locator("#view").inner_text().split())
        assert ended != no_run
        assert "schedule has ended" in ended.lower()
        assert "schedule has ended" not in no_run.lower()

    def test_it_is_not_rendered_as_red(self, page, dashboard_html_without_blockers):
        """A supplier's clean dataset reading red because WE forgot to
        type next year's dates is an attribution error, and the fastest
        way to teach people that red does not mean what it says."""
        _goto(page, dashboard_html_without_blockers, state=self.DS, in_place_on=self.ONE_EXHAUSTED)
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

    def test_the_page_still_has_zero_console_errors(self, clean_page, dashboard_html_without_blockers):
        """`clean_page`, NOT `page` (plans/post-build-review.md #43).

        This used to take the plain `page` fixture and register only a
        `console` handler of its own - so an UNCAUGHT EXCEPTION slipped
        straight past it. It passed while the very dataset page it
        navigates to was throwing a TypeError (#5). The suite's own
        `clean_page` fixture has registered both `console` and
        `pageerror` all along, and asserts them empty in teardown.
        """
        for in_place_on in (self.NONE_EXHAUSTED, self.ONE_EXHAUSTED, self.ALL_EXHAUSTED):
            _goto(clean_page, dashboard_html_without_blockers, in_place_on=in_place_on)
            _goto(clean_page, dashboard_html_without_blockers, state=self.DS, in_place_on=in_place_on)


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
            self, clean_page, dashboard_html_without_blockers, theme):
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

        ON THE PAGE WITHOUT BLOCKERS OR GAPS (2026-10-05): on the real
        corpus every dataset now has a closed, unmarked period by 2027 and
        reads red (REQ-DASH-133), so no nodata pill is left to measure.
        This is about the pill's styling, not the corpus.
        """
        _goto(clean_page, dashboard_html_without_blockers, in_place_on="2027-09-01")
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
    NOTHING_YET = "2012-01-01"  # before any real history exists
    # One agency green, the other with no data yet: Child Protection's
    # history reaches back to 2013 since REQ-GEN-207, Birth Registrations'
    # starts in 2026. The legend once printed this as "(1 agencies)" for
    # green alone, which no counter could add up (post-build-review #206).
    ONE_GREEN = "2022-01-01"
    NORMAL = None

    def _legend(self, page):
        return page.locator("#view .legend-key").first.inner_text()

    def test_no_agency_is_counted_green_when_none_is_green(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, in_place_on=self.ALL_QUIET)
        statuses = clean_page.evaluate("() => DATA.agencies.map(a => a.status)")
        assert "green" not in statuses, "precondition - no agency should be green at this as-of"
        assert re.search(r"Green[^(]*\(0\b", self._legend(clean_page)), (
            f"legend claims green agencies that do not exist: {self._legend(clean_page)}")

    def test_the_quiet_states_are_named_and_counted(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, in_place_on=self.ALL_QUIET)
        legend = self._legend(clean_page)
        statuses = clean_page.evaluate("() => DATA.agencies.map(a => a.status)")
        for label, status in (("No data", "nodata"), ("Schedule ended", "exhausted")):
            if status in statuses:
                assert label in legend, f"{status!r} is on the page and absent from the legend"

    def test_every_counter_sums_to_the_number_of_agencies(self, clean_page, built_dashboard_html):
        """The arithmetic bug was a subtraction that could not be
        checked. Whatever the legend shows must add up."""
        for in_place_on in (self.NORMAL, self.ALL_QUIET, self.NOTHING_YET, self.ONE_GREEN):
            _goto(clean_page, built_dashboard_html, in_place_on=in_place_on)
            total = clean_page.evaluate("() => DATA.agencies.length")
            counted = sum(int(n) for n in re.findall(r"\((\d+)\)", self._legend(clean_page)))
            assert counted == total, (
                f"in_place_on={in_place_on}: legend counts {counted} of {total} agencies: "
                f"{self._legend(clean_page)}")

    def test_a_normal_in_place_on_still_reads_the_way_it_always_did(self, clean_page, built_dashboard_html):
        """The quiet counters must not become permanent furniture on a
        page where nothing is quiet."""
        _goto(clean_page, built_dashboard_html, in_place_on=self.NORMAL)
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
        for control_id in ["theme-btn", "activity-btn", "in-place-on-btn"]:
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
    IN_PLACE_ON = "2028-06-01"
    STATE = {"tier": "dataset", "agencyId": "child-protection-family-support",
             "collectionId": "child-protection", "datasetId": "cp-case-workers"}

    def _open(self, page, html):
        _goto(page, html, state=self.STATE, in_place_on=self.IN_PLACE_ON)
        page.wait_for_timeout(400)

    def test_the_message_is_still_there_and_still_first(self, clean_page,
                                                         dashboard_html_without_blockers):
        self._open(clean_page, dashboard_html_without_blockers)
        text = clean_page.locator("#view").inner_text()
        assert "delivery schedule has ended" in text.lower()

    def test_the_columns_are_reachable_rather_than_replaced(self, clean_page,
                                                             dashboard_html_without_blockers):
        self._open(clean_page, dashboard_html_without_blockers)
        assert clean_page.locator(".column-tile, .col-tile").count() > 0, (
            "the whole page is still the message - 7 columns of real history are hidden")

    def test_the_supply_history_is_reachable_too(self, clean_page,
                                                  dashboard_html_without_blockers):
        self._open(clean_page, dashboard_html_without_blockers)
        assert clean_page.locator("#supply-history-toggle, .supply-history").count() > 0

    def test_the_head_still_says_the_schedule_ended(self, clean_page,
                                                     dashboard_html_without_blockers):
        """Showing history under the message must not make the page look
        ordinary at a glance - but the pill belongs where every other
        dataset's status pill is, which is the right-hand cluster.
        Putting a second one in the <h2> was the shape #53 complains
        about (a reader who has learned "status is top-right" finding it
        top-left), and the first draft of #13 did exactly that."""
        self._open(clean_page, dashboard_html_without_blockers)
        assert clean_page.locator("#view h2 .pill.exhausted").count() == 0
        assert clean_page.locator(".view-head .pill.exhausted").count() == 1

    def test_it_renders_without_throwing(self, clean_page, dashboard_html_without_blockers):
        """clean_page's teardown asserts no console error - the whole
        point, since this path never ran the normal renderer before."""
        self._open(clean_page, dashboard_html_without_blockers)
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
        _await_requirements_plans(clean_page, start=True)
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
        _await_requirements_plans(clean_page, start=True)
        bad = clean_page.evaluate("""() => {
            const out = [];
            (REQUIREMENTS||[]).forEach(r => (r.unmet_criteria||[]).forEach(u => {
                if(!u.criterion || !u.why || !u.owner) out.push(r.id);
            }));
            return out;
        }""")
        assert bad == [], bad


class TestTheDependencyViewInThePlansTab:
    """REQ-DOCS-073 criterion 6, against the real built dashboard.

    The page must not re-derive this: qa_tools/common/sprint_state.py
    computes it and `mothman plans dependencies` renders the same
    structure. So what is worth asserting here is that the page shows
    what that function produced, not that the page's own arithmetic
    agrees with itself - this project has already shipped a shared
    rule implemented twice and had one copy render a check with
    fourteen real violations green.
    """

    def test_it_matches_what_the_python_computed(self, clean_page, built_dashboard_html):
        from qa_tools.common.sprint_state import dependency_data

        expected = dependency_data()
        assert expected["sprints"], "no sprint is waiting on anything - this test is vacuous"

        _goto(clean_page, built_dashboard_html)
        embedded = clean_page.evaluate("() => SPRINT_DEPENDENCIES")
        assert embedded == expected

    def test_the_tab_renders_a_row_per_sprint_in_the_graph(
            self, clean_page, built_dashboard_html):
        from qa_tools.common.sprint_state import dependency_data

        _goto(clean_page, built_dashboard_html)
        clean_page.evaluate("() => navigate({tier:'plans'})")
        clean_page.wait_for_selector("details.plans-deps")
        rows = clean_page.locator("details.plans-deps tbody tr")
        assert rows.count() == len(dependency_data()["sprints"])

    def test_it_is_collapsed_until_asked_for(self, clean_page, built_dashboard_html):
        """The Plans tab's job is the hundred-odd entries below it. A
        ten-row table expanded by default pushes the thing people came
        for off the screen."""
        _goto(clean_page, built_dashboard_html)
        clean_page.evaluate("() => navigate({tier:'plans'})")
        clean_page.wait_for_selector("details.plans-deps")
        assert not clean_page.locator("details.plans-deps").evaluate("d => d.open")

    def test_the_summary_names_the_worst_blocker_without_opening(
            self, clean_page, built_dashboard_html):
        """The single fact the whole view exists to surface, readable
        without interacting - promotion holds up more than anything
        else, which the sprint list alone could never show."""
        from qa_tools.common.sprint_state import dependency_data

        worst = max(dependency_data()["sprints"], key=lambda s: s["holds_up"])
        _goto(clean_page, built_dashboard_html)
        clean_page.evaluate("() => navigate({tier:'plans'})")
        text = clean_page.locator("details.plans-deps summary").inner_text()
        assert f"sprint {worst['sprint']}" in text and str(worst["holds_up"]) in text

    def test_a_shared_requirement_does_not_double_count(
            self, clean_page, built_dashboard_html):
        """REQ-PIPE-035 is owned by two sprints. Counting per owner
        rather than per criterion made promotion read as holding up
        twenty when it holds up seventeen."""
        from qa_tools.common.sprint_state import all_deferrals

        _goto(clean_page, built_dashboard_html)
        embedded = clean_page.evaluate("() => SPRINT_DEPENDENCIES")
        most = max(s["holds_up"] for s in embedded["sprints"])
        assert most <= len(all_deferrals())

    def test_it_renders_without_console_errors(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        errors = []
        clean_page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        clean_page.evaluate("() => navigate({tier:'plans'})")
        clean_page.wait_for_selector("details.plans-deps")
        clean_page.locator("details.plans-deps summary").click()
        clean_page.wait_for_timeout(200)
        assert errors == []


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
        age of their own browser tab.

        THE INSTANT IS NO LONGER THE END OF THE LINE (REQ-PIPE-092
        criteria 7 and 17), which is why the date pattern is no longer
        anchored to it. The build stamp now also says WHICH environment
        built the page and from which commit, because the build happens
        wherever the database is reachable and a production build and a
        developer's build are otherwise two identical-looking artifacts.
        """
        _goto(clean_page, built_dashboard_html)
        first = clean_page.locator("#clock-text").inner_text()
        assert first.startswith("Built "), first
        assert re.search(r"\d{1,2}:\d{2}(am|pm) \w+day, \d{1,2} \w+ \d{4}", first), first

    def test_the_masthead_says_which_environment_and_commit_built_the_page(
            self, clean_page, built_dashboard_html):
        """REQ-PIPE-092 criteria 7 and 17, asserted AT THE RENDER LAYER
        rather than on the embedded const - which is CLAUDE.md's own
        standing lesson, that a correct data layer says nothing about a
        template with its own transform.

        A SHORT SHA IN THE LINE, THE FULL ONE IN THE TITLE: a reader
        recognises seven characters and does not read forty.
        """
        _goto(clean_page, built_dashboard_html)
        stamp = clean_page.locator("#clock-text")
        text = stamp.inner_text()
        assert " · " in text, f"the build stamp names no environment: {text}"

        title = stamp.get_attribute("title") or ""
        assert "Built in:" in title, title
        assert "Commit:" in title, title
        # The full sha is in the title and a short one in the line, so the
        # line must NOT carry the whole forty characters.
        commit = title.split("Commit:")[1].strip()
        assert len(commit) >= 7, title
        assert commit not in text, "the full sha is in the line rather than the title"
        assert commit[:7] in text, f"the short sha is not in the line: {text}"

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
        and both look identical to a panel that crashed - so the panel
        is ALWAYS present and always says which it is.

        IT USED TO ASSERT THE QUIET WORDING EVERYWHERE, because the
        generated history had nothing outstanding anywhere. REQ-GEN-044
        injected TS-38, whose renamed resupplies are a real unattributed
        artefact, and one tier now correctly reports it. That is the
        scenario working rather than a regression, so what this holds is
        the property that survives both states: the panel exists, and it
        either names what is waiting or says nothing is - never neither.
        """
        quiet = "Nothing is waiting for a person"
        waiting = "waiting for a person"

        _goto(clean_page, built_dashboard_html)
        assert clean_page.locator(".notice-queue").count() == 1
        top = clean_page.locator(".notice-queue").inner_text()
        assert quiet in top or waiting in top, top

        agency = clean_page.locator("#agency-grid .card").first
        agency.click()
        clean_page.wait_for_timeout(400)
        assert clean_page.locator(".notice-queue").count() >= 1
        tier2 = clean_page.locator(".notice-queue").first.inner_text()
        assert quiet in tier2 or waiting in tier2, tier2

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
        changed figure as the page being wrong.

        THE AS-OF DATE COMES FROM THE PAGE'S OWN DATA, not from today.
        The first version of this test drove the default as-of, which
        is today on the asset clock, and went red the moment the Perth
        date rolled past the newest generated run: Birth Registrations
        is DAILY, so a day later its newest supply falls outside its own
        current cycle and the row correctly renders the quiet state,
        which has no arrival cell to carry a qualifier. Nothing about
        the page was wrong. That is post-build-review #59's shape
        exactly - an assertion resting on an ambient date - and it
        would have gone red in CI on the next run for the same reason.
        """
        _goto(clean_page, built_dashboard_html)
        newest = clean_page.evaluate(
            "rawRealDatasetById('birth-registrations').runs.at(-1).run_date")
        _goto(clean_page, built_dashboard_html, in_place_on=newest)
        clean_page.locator("#agency-grid .card").first.click()
        clean_page.wait_for_timeout(400)
        titles = clean_page.locator("td span[title*='currently filed to']")
        assert titles.count() > 0, (
            f"no arrival verdict on Tier 2 carries the qualifier as of {newest}")


@pytest.fixture(scope="class")
def dashboard_html_with_divergent_arrivals(built_dashboard_html, tmp_path_factory) -> Path:
    """A second built HTML whose Child Protection datasets arrive on
    their OWN schedules (REQ-DASH-041).

    The real committed history cannot exercise this requirement at all:
    all six CP datasets arrive together, eighteen runs each on the same
    dates, because the generator emits one six-table delivery per
    period. So the divergence is constructed here - two datasets cut
    short by a quarter, one cut to a single late arrival - rather than
    waited for.

    The CUT IS ON `runs` AND EVERYTHING KEYED BY RUN, not on `runs`
    alone: leaving a check's history pointing at a run the dataset no
    longer has is a shape the real data can never produce, and a test
    built on one proves nothing about the real page.
    """
    from qa_tools import collections

    name = collections.by_id("child-protection").dashboard_file
    data = json.loads((_reports_of(built_dashboard_html) / name).read_text())

    # How many of each dataset's own runs to keep. One is left whole,
    # so the collection genuinely does not line up.
    from tests.divergent_arrivals import cut_datasets_short
    cut_datasets_short(data, {"cp-carers": 9, "cp-case-workers": 1, "cp-investigations": 14})

    page = _embed_variant(built_dashboard_html, tmp_path_factory.mktemp("divergent"),
                          reports={name: data})
    # WITH NOTHING HELD OR CONTESTED (post-build-review #272), for the reason
    # dashboard_html_without_blockers gives: a held or contested dataset is
    # RED, and red outranks the quiet state these tests are about. The
    # deployment holds cp-case-workers' unplaceable supplies, so on its real
    # blockers the cut-short cp-case-workers reads red rather than quiet.
    page.write_text(_rewrite_const(page.read_text(), "OUTSTANDING",
                                   lambda record: record.__setitem__("blockers", [])))
    return page


class TestPerDatasetArrivals:
    """REQ-DASH-041, at the render layer in a real browser.

    The requirement exists BECAUSE the data layer was already checked:
    buildSupplyHistory was driven against a doctored dataset and held
    up, and a correct builder says nothing about a template with its
    own transform. So every assertion here is on the rendered page.
    """

    def _open_cp(self, page, html):
        _goto(page, html)
        page.locator('#agency-grid a.card[data-agency="child-protection-family-support"]').click()
        page.wait_for_timeout(500)

    def test_a_collection_arriving_on_six_schedules_renders_without_console_errors(
            self, clean_page, dashboard_html_with_divergent_arrivals):
        """Criterion 5, and the NFR's "should not look like a bug"."""
        self._open_cp(clean_page, dashboard_html_with_divergent_arrivals)
        rows = clean_page.locator(".dataset-table tbody tr")
        assert rows.count() >= 6, "the Child Protection table lost datasets"

    def test_each_dataset_resolves_on_its_OWN_history_not_the_collections(
            self, clean_page, dashboard_html_with_divergent_arrivals):
        """Criterion 1, and the assertion is about DIVERGENCE rather
        than about dates.

        Three datasets are cut short, and at the default as-of date
        their newest arrival falls outside their own current cycle - so
        the page correctly renders them in the quiet state while the
        three whole ones render a real arrival. A collection-wide
        as-of would put all six in the same state, whichever it chose,
        which is exactly what this is here to rule out.
        """
        self._open_cp(clean_page, dashboard_html_with_divergent_arrivals)
        rows = clean_page.locator(".dataset-table tbody tr")
        quiet = [i for i in range(rows.count())
                  if "no qa run within tolerance" in rows.nth(i).inner_text().lower()]
        assert len(quiet) == 3, (
            f"expected the three cut-short datasets to resolve quietly, got {quiet}")
        assert rows.count() - len(quiet) == 3, "the untouched datasets stopped rendering"

    def test_a_dataset_with_no_arrival_by_the_in_place_on_date_shows_the_existing_quiet_state(
            self, clean_page, dashboard_html_with_divergent_arrivals):
        """Criterion 4. cp-case-workers is cut to its single earliest
        arrival, so an as-of date before that has nothing to show - and
        the page must say so in the state it already has rather than
        rendering an empty panel."""
        _goto(clean_page, dashboard_html_with_divergent_arrivals, in_place_on="2023-01-01")
        clean_page.locator('#agency-grid a.card[data-agency="child-protection-family-support"]').click()
        clean_page.wait_for_timeout(500)
        text = clean_page.locator("#view").inner_text().lower()
        assert "no qa run within tolerance" in text or "no data" in text, text[:400]

    def test_the_in_place_on_picker_moves_each_dataset_on_its_own_history(
            self, clean_page, dashboard_html_with_divergent_arrivals):
        """Criteria 2 and 3. Stepping the as-of date back must change
        what SOME datasets show without emptying the page - the case a
        collection-wide as-of would get wrong."""
        self._open_cp(clean_page, dashboard_html_with_divergent_arrivals)
        before = clean_page.locator(".dataset-table tbody tr td:nth-child(5)").all_inner_texts()

        _goto(clean_page, dashboard_html_with_divergent_arrivals, in_place_on="2024-06-01")
        clean_page.locator('#agency-grid a.card[data-agency="child-protection-family-support"]').click()
        clean_page.wait_for_timeout(500)
        after = clean_page.locator(".dataset-table tbody tr td:nth-child(5)").all_inner_texts()

        assert before != after, "the as-of date changed nothing on any dataset"
        assert clean_page.locator(".dataset-table tbody tr").count() >= 6, (
            "moving the as-of date emptied the collection")

    def test_a_short_datasets_own_supply_history_still_renders_at_tier_3(
            self, clean_page, dashboard_html_with_divergent_arrivals):
        """Criterion 1 at the dataset page - the surface the original
        data-layer check never reached."""
        _goto(clean_page, dashboard_html_with_divergent_arrivals,
              state={"tier": "dataset", "agencyId": "child-protection-family-support",
                      "collectionId": "child-protection", "datasetId": "cp-carers"})
        text = clean_page.locator("#view").inner_text()
        assert text.strip(), "the cut-short dataset's own page rendered nothing"


class TestScenariosTab:
    """REQ-DASH-046's behaviours, kept, on REQ-DASH-139's top-level tab - in a
    real browser against the real built page.

    The dashboard deliberately carries NO label on a deliberately
    broken supply - "this is still just a proof of concept", and the
    red is the point - so this panel is the one place that says which
    red was on purpose.
    """

    def test_it_opens_and_renders_the_committed_map(self, clean_page, built_dashboard_html):
        """Criteria 1 and 6 - the console-error collector this suite
        runs under covers the second."""
        _goto(clean_page, built_dashboard_html)
        clean_page.locator("#scenarios-btn").click()
        clean_page.wait_for_timeout(400)

        assert "/scenarios" in clean_page.url
        body = clean_page.locator("#scenarios-panel-body").inner_text()
        assert "which red was on purpose" in body.lower()
        assert "TS-1" in body, body[:300]

    def test_an_entry_with_no_coordinates_is_plain_text_not_a_link(
            self, clean_page, built_dashboard_html):
        """Criterion 4.

        IT USED TO BE EVERY ENTRY, because nothing was injected and a
        panel full of dead links was the whole failure this ruled out.
        REQ-GEN-044 changed that: three scenarios have real coordinates
        now, so the assertion is no longer "no links anywhere" but the
        thing it always meant - an entry with nothing behind it does not
        pretend to lead somewhere. Counting controls against the number
        of PLACED scenarios keeps it honest as more are injected, where
        a fixed count would have to be edited every time and would
        eventually be edited to whatever the page happened to render.
        """
        from qa_tools.common import scenario_map

        placed = {sid for sid, p in scenario_map.read_placements().items()
                  if p.is_complete}
        _goto(clean_page, built_dashboard_html)
        clean_page.locator("#scenarios-btn").click()
        clean_page.wait_for_timeout(400)

        panel = clean_page.locator("#scenarios-panel-body")
        # Each placed chip is a real link since REQ-DASH-208 criterion 10.
        controls = panel.locator("a").count()
        assert controls <= len(placed), (
            f"the panel offers {controls} control(s) for {len(placed)} placed "
            f"scenario(s) - one of them leads nowhere")
        assert "no data behind it" in panel.inner_text(), (
            "no entry says it has nothing behind it, and most still have nothing")

    def test_a_coordinate_lands_on_the_right_page_and_date(
            self, clean_page, built_dashboard_html):
        """REQ-DASH-139 NFR 2 (sprint 11 critic: it was only done by hand).
        TS-47 is planted, so its entry leads somewhere: the Birth
        Registrations page, at the in-place-on date its placement records."""
        from qa_tools.common import scenario_map

        placement = scenario_map.read_placements().get("TS-47")
        if placement is None or not placement.is_complete:
            pytest.skip("TS-47 is not placed in this history")
        _goto(clean_page, built_dashboard_html)
        clean_page.locator("#scenarios-btn").click()
        clean_page.wait_for_timeout(400)
        index = clean_page.evaluate("SCENARIO_MAP.findIndex(e => e.id === 'TS-47')")
        assert index >= 0, "TS-47 is not in the embedded map"
        clean_page.locator(f'a[data-scenario="{index}"]').click()
        clean_page.wait_for_timeout(600)
        assert f"in-place-on={placement.in_place_on}" in clean_page.url
        assert "/dataset/birth-registrations" in clean_page.url

    def test_a_jump_says_so_and_back_undoes_it(self, clean_page, built_dashboard_html):
        """Keith, 2026-10-06 (post-build-review #123 B4): a scenario jump
        silently moved the whole dashboard to a past date, and Back did not
        put it back. It now shows a bar naming the scenario and the date,
        with a way back to today, and Back restores the date it left."""
        from qa_tools.common import scenario_map

        placement = scenario_map.read_placements().get("TS-47")
        if placement is None or not placement.is_complete:
            pytest.skip("TS-47 is not placed in this history")
        _goto(clean_page, built_dashboard_html)
        before = clean_page.evaluate("CURRENT_IN_PLACE_ON")
        clean_page.locator("#scenarios-btn").click()
        clean_page.wait_for_timeout(400)
        index = clean_page.evaluate("SCENARIO_MAP.findIndex(e => e.id === 'TS-47')")
        clean_page.locator(f'a[data-scenario="{index}"]').click()
        clean_page.wait_for_timeout(600)
        bar = clean_page.locator("[data-testid=scenario-jump-bar]")
        assert bar.count() == 1
        assert "TS-47" in bar.inner_text()
        assert clean_page.evaluate("CURRENT_IN_PLACE_ON") == placement.in_place_on

        clean_page.go_back()
        clean_page.wait_for_timeout(600)
        assert "/scenarios" in clean_page.url
        assert clean_page.evaluate("CURRENT_IN_PLACE_ON") == before
        assert f"in-place-on={placement.in_place_on}" not in clean_page.url

    def test_the_committed_map_carries_no_url_for_the_page_to_follow(
            self, clean_page, built_dashboard_html):
        """Criterion 3. The page constructs the link; a URL written into
        the map would break silently the next time a route changed."""
        _goto(clean_page, built_dashboard_html)
        embedded = clean_page.evaluate("JSON.stringify(SCENARIO_MAP)")
        assert embedded and embedded != "[]", "no scenario map was embedded"
        assert "http" not in embedded
        assert "#/" not in embedded

    def test_it_is_a_real_history_entry_that_the_back_button_leaves(
            self, clean_page, built_dashboard_html):
        """A tab is navigation like Plans and Demo (REQ-DASH-139 criterion 1):
        it has its own URL, and back returns to where the reader was."""
        _goto(clean_page, built_dashboard_html)
        clean_page.locator("#scenarios-btn").click()
        clean_page.wait_for_timeout(400)
        assert "/scenarios" in clean_page.url

        clean_page.go_back()
        clean_page.wait_for_timeout(400)
        assert "/scenarios" not in clean_page.url


class TestCrossTableChecks:
    """REQ-QAC-037 criteria 6 and 7, in a real browser.

    The requirement's own NFR asks for exactly this: it changes the
    shape of a stored result, so assert at the last transform before
    the user rather than at the first one after the source.
    """

    COLLECTION = ("#/agency/child-protection-family-support"
                   "/collection/child-protection")

    def test_the_collection_gathers_them_into_one_section(
            self, clean_page, built_dashboard_html):
        """Criterion 6's collection half, and deduped - every
        participating dataset carries the same record, so an
        un-deduped section would list one problem several times."""
        _goto(clean_page, built_dashboard_html,
              state={"tier": "agency", "agencyId": "child-protection-family-support"})
        section = clean_page.locator('.scope-section[data-scope="cross-table"]')
        assert section.count() == 1, f"expected one section, got {section.count()}"
        rows = section.first.locator("button.scope-check")
        assert rows.count() > 0
        # DEDUPED BY check_id, which is the actual claim. Display
        # LABELS legitimately repeat - "Client reference" is the name
        # of the dbt, Soda and datacontract-cli versions of the same
        # relationship, on each of three tables - so asserting unique
        # labels would assert something untrue about the corpus.
        ids = clean_page.evaluate("""() => {
            const cp = DATA.agencies.flatMap(a=>a.collections)
                .find(c=>c.id === "child-protection");
            return collectionCrossTableChecks(cp).map(e=>e.check.check_id);
        }""")
        assert ids, "the collection gathered no cross-table checks"
        assert len(ids) == len(set(ids)), "a check_id appears twice in the section"
        assert rows.count() == len(ids)

    def test_a_dataset_that_only_reads_a_check_still_shows_it(
            self, clean_page, built_dashboard_html):
        """Criterion 6's dataset half. cp-carers declares none of these
        checks - it is only read BY them - so before this requirement
        its page showed nothing about them at all."""
        _goto(clean_page, built_dashboard_html,
              state={"tier": "dataset", "agencyId": "child-protection-family-support",
                      "collectionId": "child-protection", "datasetId": "cp-carers"})
        section = clean_page.locator('.scope-section[data-scope="cross-table"]')
        assert section.count() == 1, "cp-carers shows no cross-table section"
        assert section.first.locator("button.scope-check").count() > 0

    def test_a_cross_table_failure_turns_a_participating_dataset_red(
            self, clean_page, built_dashboard_html):
        """Criterion 7, and the cost Keith took knowingly on 2026-09-26,
        superseding Thread I's "healthy neighbour green": cp-carers goes
        red for a disagreement with a neighbour, on a day nothing about
        cp-carers itself changed.

        Asserted through the PAGE's own status function rather than off
        the rendered pill, so it cannot pass because some other check
        happens to be red on the same dataset.
        """
        _goto(clean_page, built_dashboard_html)
        # ASSERTED PER RUN, not over the whole history: cp-carers has its
        # own failing checks in some runs, so "is it ever red" would be
        # true with or without folding and prove nothing.
        #
        # AND THE CONDITION IS BUILT, NOT FOUND (REQ-GEN-184, 2026-10-11).
        # This used to look for a run in the generated history that was
        # green on its own checks and red through a cross-table check. That
        # shape came from blunt "amber" supplies dirtying placements as a
        # side effect; ordinary ambers are now built to touch one rule
        # only, and the shape went with them. The claim is about the
        # page's folding, not about the corpus, so the test takes a run
        # cp-carers' own checks do not hold red, fails one cross-table
        # result in that run, and asks the page's own function.
        found = clean_page.evaluate("""() => {
            const cp = DATA.agencies.flatMap(a=>a.collections)
                .find(c=>c.id === "child-protection");
            const ds = cp.datasets.find(d=>d.id === "cp-carers");
            const cross = ds.columns.filter(c=>c.scope === "cross-table");
            const own = {columns: ds.columns.filter(c=>c.scope !== "cross-table")};
            const ownOnly = datasetStatusByRun(own);
            const candidates = cross.flatMap(c=>(c.checks||[]).flatMap(ck=>
                // A run only enters the map once it is worse than green,
                // so an absent run is a green one.
                (ck.history||[]).filter(h=>ownOnly.get(h.run_id) !== "red")
                    .map(h=>({ck, h}))));
            if(!candidates.length) return {nCross: cross.length, candidates: 0};
            const {ck, h} = candidates[0];
            const failed = cross.map(c=>({...c, checks: (c.checks||[]).map(k=>k !== ck ? k
                : {...k, history: k.history.map(e=>e === h ? {...e, status: "red"} : e)})}));
            const after = datasetStatusByRun({columns: [...own.columns, ...failed]}).get(h.run_id);
            return {nCross: cross.length, candidates: candidates.length,
                    own: ownOnly.get(h.run_id) || "green", after};
        }""")
        assert found["nCross"] > 0, "cp-carers carries no cross-table checks"
        assert found["candidates"], "no run where cp-carers' own checks are not red"
        assert found["own"] != "red"
        assert found["after"] == "red", (
            f"a failing cross-table result left cp-carers {found['after']} in that run "
            "- folding is not reaching this dataset's status")

    def test_a_cross_table_check_is_not_among_the_real_columns(
            self, clean_page, built_dashboard_html):
        """A referential check declared on cp_notifications reads
        cp_client_id, which is not a column of cp_carers. Rendering it
        as one would invent a column."""
        _goto(clean_page, built_dashboard_html,
              state={"tier": "dataset", "agencyId": "child-protection-family-support",
                      "collectionId": "child-protection", "datasetId": "cp-carers"})
        invented = clean_page.evaluate("""() => {
            const cp = DATA.agencies.flatMap(a=>a.collections)
                .find(c=>c.id === "child-protection");
            const ds = cp.datasets.find(d=>d.id === "cp-carers");
            return realColumns(ds).map(c=>c.name);
        }""")
        assert "cp_client_id" not in invented, invented


class TestArrivedVersusPromoted:
    """REQ-DASH-056, in a real browser against the real built page.

    Driven here rather than only in tests-js because the thing being
    checked is a chain: a decision in the log, through the build, into
    the embedded data, into a rendered panel. Each link is tested on its
    own; only this asserts at the layer a person actually sees, which is
    the lesson plans/qa-pipeline.md item 74 paid for - a green data
    layer says nothing about a render layer with its own transform.
    """

    DATASETS = (
        ("registry-services", "civil-registration", "birth-registrations"),
        ("child-protection-family-support", "child-protection", "cp-carers"),
    )

    def _open(self, page, html, agency, collection, dataset_id, in_place_on=None):
        _goto(page, html, state={"tier": "dataset", "agencyId": agency,
                                  "collectionId": collection, "datasetId": dataset_id},
              in_place_on=in_place_on)

    def _open_where_it_shows(self, page, html, agency, collection, dataset_id):
        """Open the dataset on the newest date its panel shows, TAKEN FROM THE
        EMBEDDED CHANGE POINTS (REQ-DASH-197) - it used to skip whenever the
        latest arrival happened to be promoted today, proving nothing."""
        self._open(page, html, agency, collection, dataset_id)
        if page.locator('[data-testid="promotion-split"]').count():
            return
        days = page.evaluate(
            "(id) => rawRealDatasets().find(d => d.id === id).promotionTimeline.points"
            ".filter(p => p.differs).map(p => p.on)", dataset_id)
        assert days, f"precondition: {dataset_id}'s history has a date the panel shows"
        self._open(page, html, agency, collection, dataset_id, in_place_on=days[-1])

    @pytest.mark.parametrize("agency,collection,dataset_id", DATASETS)
    def test_the_panel_agrees_with_the_data_about_whether_to_show_at_all(
            self, clean_page, built_dashboard_html, agency, collection, dataset_id):
        """Criteria 1 and 3 together, and asserting them as ONE claim is
        deliberate: "show both" and "stay quiet" are the same rule read
        from its two sides, and a test for either alone passes on a page
        that always does that one thing."""
        self._open(clean_page, built_dashboard_html, agency, collection, dataset_id)
        differs = clean_page.evaluate(
            """(id) => {
                 const ds = DATA.agencies.flatMap(a=>a.collections)
                   .flatMap(c=>c.datasets).find(d=>d.id === id);
                 return Boolean(ds && ds.promotionState && ds.promotionState.differs);
               }""", dataset_id)
        shown = clean_page.locator('[data-testid="promotion-split"]').count()
        assert shown == (1 if differs else 0), (
            f"{dataset_id}: promotionState.differs is {differs} and the panel "
            f"rendered {shown} time(s)")

    @pytest.mark.parametrize("agency,collection,dataset_id", DATASETS)
    def test_where_it_shows_it_names_both_supplies_and_says_why(
            self, clean_page, built_dashboard_html, agency, collection, dataset_id):
        self._open_where_it_shows(clean_page, built_dashboard_html, agency, collection,
                                  dataset_id)
        panel = clean_page.locator('[data-testid="promotion-split"]')
        text = panel.inner_text()
        state = clean_page.evaluate(
            """(id) => DATA.agencies.flatMap(a=>a.collections)
                 .flatMap(c=>c.datasets).find(d=>d.id === id).promotionState""",
            dataset_id)
        assert state["arrived"]["supply"] in text
        if state["promoted"]:
            assert state["promoted"]["supply"] in text
        # CASE-INSENSITIVELY, because the labels are uppercased by CSS
        # and inner_text() reports what is rendered. The claim is that
        # the two are LABELLED rather than left to the reader's guess at
        # the order (criterion 2) - which letter-case they are in is the
        # stylesheet's business.
        lower = text.lower()
        assert "promoted" in lower and "latest arrival" in lower
        assert state["explanation"] and state["explanation"] in text

    @pytest.mark.parametrize("agency,collection,dataset_id", DATASETS)
    def test_it_shows_no_raw_period_code(
            self, clean_page, built_dashboard_html, agency, collection, dataset_id):
        """A DAILY calendar names its periods by the day, so the period
        name is a bare ISO date - the one thing REQ-DASH-071 says a
        reader never sees. The panel is the newest place one could leak
        in."""
        self._open_where_it_shows(clean_page, built_dashboard_html, agency, collection,
                                  dataset_id)
        panel = clean_page.locator('[data-testid="promotion-split"]')
        # The supply IDENTIFIER legitimately carries digits, so the line
        # holding it is excluded rather than the whole panel: an
        # identifier is what somebody quotes in a ticket, not a date
        # being shown to them.
        prose = [ln for ln in panel.inner_text().splitlines() if "@" not in ln]
        raw = [ln for ln in prose if re.search(r"\b\d{4}-\d{2}-\d{2}\b", ln)]
        assert not raw, f"{dataset_id} shows a raw period code: {raw}"


class TestAPeriodStandingInOnAnEarlierOne:
    """REQ-DASH-085 and REQ-DASH-100, in a real browser.

    NO DATASET IN THIS DEPLOYMENT IS SUBSTITUTED, and that is stated
    rather than worked around: writing a substitution into the real
    decision log to make a test pass would be fabricating an operator
    decision in an append-only record. (cp-case-workers IS inherited
    since REQ-GEN-044 gave inheritance a real instance; the real chain
    from those decisions to the page is held by
    TestTheQualifierAsAtTheDateOnShow below.)

    So these set the state ON THE PAGE and re-render. What that proves
    is the render layer - that the qualifier reaches the status line,
    that the detail panel says what it must, and that a real browser
    reports no errors doing it. What it cannot prove is the chain from a
    real decision, which waits on REQ-GEN-044 giving inheritance a real
    instance and on the operator routes giving substitution one.
    """

    SUBSTITUTED = {
        "kind": "substituted", "level": "warning", "period": "2026-Q3",
        "standsOn": "2026-Q2", "supply": "cp-carers@202605010100000000",
        "decidedBy": "Keith", "byAPerson": True,
        "reason": "the supplier confirmed no extract will be sent this quarter",
    }
    INHERITED = {
        "kind": "inherited", "level": "information", "period": "2026-Q3",
        "standsOn": "2026-Q1", "supply": "cp-carers@202602010100000000",
        "decidedBy": None, "byAPerson": False,
        "reason": "carers are supplied annually, so no quarterly file is due",
    }

    def _with_state(self, page, html, standing_in):
        _goto(page, html, state={"tier": "dataset",
                                  "agencyId": "child-protection-family-support",
                                  "collectionId": "child-protection",
                                  "datasetId": "cp-carers"})
        page.evaluate(
            """(st) => {
                 const ds = DATA.agencies.flatMap(a=>a.collections)
                   .flatMap(c=>c.datasets).find(d=>d.id === "cp-carers");
                 ds.promotionState = Object.assign({}, ds.promotionState,
                                                    {standingIn: st});
                 render();
               }""", standing_in)

    @pytest.mark.parametrize("kind,word", [("SUBSTITUTED", "Substituted"),
                                            ("INHERITED", "Inherited")])
    def test_the_qualifier_appears_beside_the_status(
            self, clean_page, built_dashboard_html, kind, word):
        self._with_state(clean_page, built_dashboard_html, getattr(self, kind))
        marker = clean_page.locator('[data-testid="standing-in"]')
        assert marker.count() >= 1
        assert word in marker.first.inner_text()

    @pytest.mark.parametrize("kind", ["SUBSTITUTED", "INHERITED"])
    def test_it_names_the_period_the_data_came_from_in_the_label(
            self, clean_page, built_dashboard_html, kind):
        state = getattr(self, kind)
        self._with_state(clean_page, built_dashboard_html, state)
        text = clean_page.locator('[data-testid="standing-in"]').first.inner_text()
        assert state["standsOn"] in text

    @pytest.mark.parametrize("kind", ["SUBSTITUTED", "INHERITED"])
    def test_the_drill_down_shows_the_reason_as_written(
            self, clean_page, built_dashboard_html, kind):
        state = getattr(self, kind)
        self._with_state(clean_page, built_dashboard_html, state)
        detail = clean_page.locator('[data-testid="standing-in-detail"]')
        assert detail.count() == 1
        assert state["reason"] in detail.inner_text()

    def test_a_substitution_names_who_decided_it(self, clean_page,
                                                  built_dashboard_html):
        self._with_state(clean_page, built_dashboard_html, self.SUBSTITUTED)
        assert "Keith" in clean_page.locator(
            '[data-testid="standing-in-detail"]').inner_text()

    def test_an_inheritance_names_nobody(self, clean_page, built_dashboard_html):
        """Naming the rule as though it were a person would put a
        decision on somebody who never made one."""
        self._with_state(clean_page, built_dashboard_html, self.INHERITED)
        text = clean_page.locator('[data-testid="standing-in-detail"]').inner_text()
        assert "no person decided it" in text
        assert "Decided by" not in text

    def test_the_two_are_told_apart_by_more_than_colour(
            self, clean_page, built_dashboard_html):
        self._with_state(clean_page, built_dashboard_html, self.SUBSTITUTED)
        one = clean_page.locator('[data-testid="standing-in"]').first.inner_text()
        self._with_state(clean_page, built_dashboard_html, self.INHERITED)
        two = clean_page.locator('[data-testid="standing-in"]').first.inner_text()
        assert one != two, "the label carries the whole meaning, never the colour"

    @pytest.mark.parametrize("kind", ["SUBSTITUTED", "INHERITED"])
    def test_it_renders_with_zero_console_errors(
            self, clean_page, built_dashboard_html, kind):
        errors = []
        clean_page.on("console",
                       lambda m: errors.append(m.text) if m.type == "error" else None)
        self._with_state(clean_page, built_dashboard_html, getattr(self, kind))
        assert clean_page.locator('[data-testid="standing-in"]').count() >= 1
        assert errors == []


class TestDrillingThroughToThePeriodThatEarnedTheResults:
    """REQ-DASH-085 criteria 9-11 and REQ-DASH-100 criteria 8-10.

    THE STATE IS SET ON THE EMBEDDED SOURCE, not on the built DATA tree,
    and the difference is the whole reason this class exists separately
    from the one above. Drilling REBUILDS DATA for the new as-of date,
    so a standing-in record patched onto DATA disappears on the first
    click - which would make every assertion after it about a page in a
    state the test never set up. Patching COLLECTION_DATA, which buildData()
    reads, survives the rebuild exactly as a real record would.

    Still not a real decision, for the reason the class above states:
    writing one into an append-only log to make a test pass would be
    fabricating an operator's decision.
    """

    SUBSTITUTED = {
        "kind": "substituted", "level": "warning", "period": "2026-Q3",
        "standsOn": "2026-Q2", "supply": "cp-carers@202605010100000000",
        "decidedBy": "Keith", "byAPerson": True,
        "reason": "the supplier confirmed no extract will be sent this quarter",
    }
    # The two dates the real quarterly calendar gives those period names.
    # Written out rather than computed, so a change to the calendar shows
    # up here as a failing assertion rather than as a test that quietly
    # agrees with whatever it now says.
    PERIOD_DATE = "2026-08-01"
    STANDS_ON_DATE = "2026-05-01"
    WHERE = {"tier": "dataset", "agencyId": "child-protection-family-support",
              "collectionId": "child-protection", "datasetId": "cp-carers"}

    def _open(self, page, html, standing_in=None):
        _goto(page, html, state=self.WHERE)
        if standing_in is not None:
            # THE CHANGE POINTS, since REQ-DASH-197/198: the page resolves the
            # qualifier from them for the period on show and reads nothing
            # else, so a patched promotionState would simply be overwritten.
            page.evaluate(
                """(st) => {
                     const d = rawRealDatasetById("cp-carers");
                     const tl = d.promotionTimeline || {points: [], standing: []};
                     d.promotionTimeline = {...tl, standing: [...tl.standing,
                       {on: "2026-08-01", period: st.period, standingIn: st, decisions: []}]};
                     DATA = buildData(CURRENT_IN_PLACE_ON);
                     renderFromState();
                   }""", standing_in)

    def _params(self, page):
        return dict(urllib.parse.parse_qsl(
            urllib.parse.urlparse(page.url).query))

    def test_the_page_says_whose_results_these_are_before_offering_the_drill(
            self, clean_page, built_dashboard_html):
        """Criterion 9's first half. A reader who never clicks still
        reads the checks below as this period's, which is the whole
        false green - so the sentence is not optional decoration around
        the link."""
        self._open(clean_page, built_dashboard_html, self.SUBSTITUTED)
        text = " ".join(clean_page.locator(
            '[data-testid="standing-in-detail"]').inner_text().split())
        assert "ran against 2026-Q2's supply" in text
        assert "not 2026-Q3's own results" in text

    def test_drilling_moves_the_in_place_on_date_and_records_where_from(
            self, clean_page, built_dashboard_html):
        """Criterion 9's second half, and criterion 11's first: the
        framing is in the URL, so a refresh or a shared link says the
        same thing."""
        self._open(clean_page, built_dashboard_html, self.SUBSTITUTED)
        clean_page.locator('[data-testid="standing-in-drill"]').click()
        params = self._params(clean_page)
        assert params.get("in-place-on") == self.STANDS_ON_DATE
        assert params.get("from") == "2026-Q3"

    def test_the_reader_is_told_they_have_left_the_period_they_were_on(
            self, clean_page, built_dashboard_html):
        self._open(clean_page, built_dashboard_html, self.SUBSTITUTED)
        clean_page.locator('[data-testid="standing-in-drill"]').click()
        notice = clean_page.locator('[data-testid="arrival-notice"]')
        assert notice.count() == 1
        assert "You have left 2026-Q3" in notice.inner_text()

    def test_the_way_back_returns_and_takes_the_framing_with_it(
            self, clean_page, built_dashboard_html):
        self._open(clean_page, built_dashboard_html, self.SUBSTITUTED)
        clean_page.locator('[data-testid="standing-in-drill"]').click()
        clean_page.locator('[data-testid="arrival-back"]').click()
        params = self._params(clean_page)
        # EXACTLY THE DATE LEFT (REQ-DASH-198 criterion 11) - here the
        # default date, which the address bar carries as no parameter.
        assert params.get("in-place-on") is None
        assert "from" not in params
        assert clean_page.locator('[data-testid="arrival-notice"]').count() == 0

    def test_a_reader_who_came_here_directly_is_told_nothing(
            self, clean_page, built_dashboard_html):
        """The 'only' in criterion 10 is half of it: telling somebody
        they have left a period they were never on is a false alarm."""
        self._open(clean_page, built_dashboard_html, self.SUBSTITUTED)
        assert clean_page.locator('[data-testid="arrival-notice"]').count() == 0

    def test_the_framing_does_not_travel_onto_the_next_page(
            self, clean_page, built_dashboard_html):
        """Criterion 11's second half. A banner saying 'you have left
        2026-Q3' is true of the one page it was followed to and a lie
        everywhere else - and pushState() with a bare hash keeps the
        query string, so this does not happen by itself."""
        self._open(clean_page, built_dashboard_html, self.SUBSTITUTED)
        clean_page.locator('[data-testid="standing-in-drill"]').click()
        assert self._params(clean_page).get("from") == "2026-Q3"
        clean_page.locator("#rail .crumb").first.click()
        clean_page.wait_for_function(
            "() => !new URLSearchParams(location.search).get('from')")
        params = self._params(clean_page)
        assert "from" not in params
        # The orthogonal query state a navigation has always kept stays.
        assert params.get("in-place-on") == self.STANDS_ON_DATE
        assert clean_page.locator('[data-testid="arrival-notice"]').count() == 0

    def test_the_whole_drill_reports_no_console_errors(
            self, clean_page, built_dashboard_html):
        errors = []
        clean_page.on("console",
                       lambda m: errors.append(m.text) if m.type == "error" else None)
        self._open(clean_page, built_dashboard_html, self.SUBSTITUTED)
        clean_page.locator('[data-testid="standing-in-drill"]').click()
        clean_page.locator('[data-testid="arrival-back"]').click()
        assert errors == []


def _collection_data(built: Path) -> dict:
    """The built page's COLLECTION_DATA, through the one reader that finds it
    in the page's data files (REQ-DASH-291 criterion 13)."""
    from dashboard import data_files

    found = data_files.read_page(built.read_text(), built.parent)
    assert found.problems == [], found.problems
    return found.collections


def _with_collection_data_inline(html: str, data: dict) -> str:
    """The built page with COLLECTION_DATA written back INTO it as a
    literal, the way the template takes it from a test (tests-js does the
    same), and its list of data files and their script elements removed -
    so a test can change one dataset without re-encoding the files. A page
    in this shape has no Requirements and Plans data, which none of its
    callers reads."""
    html = re.sub(r'<script src="[^"]*" data-mothman-key="[^"]+" data-mothman-file="[^"]+"></script>\n',
                  "", html)
    html = re.sub(r"const DATA_FILES = .*?;\n", "const DATA_FILES = null;\n", html, count=1)
    line = "const COLLECTION_DATA = assembleCollectionData();\n"
    assert html.count(line) == 1
    return html.replace(line, f"const COLLECTION_DATA = {json.dumps(data, separators=(',', ':'))};\n")


def _rewrite_const(html: str, name: str, change) -> str:
    start = html.index(f"const {name} = ") + len(f"const {name} = ")
    end = html.index(";\n", start)
    record = json.loads(html[start:end])
    change(record)
    return html[:start] + json.dumps(record, separators=(",", ":")) + html[end:]


def _with_blockers(built: Path, out: Path, blockers: list,
                   closed_slots: dict | None = None) -> Path:
    """The built page with its OUTSTANDING record's blockers replaced -
    only that one const rewritten, every other byte the real build.

    `closed_slots`, when given, replaces every real dataset's closed,
    unfilled periods (REQ-DASH-133) - the dataset ids it names get those
    slots, every other dataset none."""
    for name in ("fonts", "vendor", "data"):
        if not (out.parent / name).exists():
            (out.parent / name).symlink_to((built.parent / name).resolve())
    html = _rewrite_const(built.read_text(), "OUTSTANDING",
                          lambda record: record.__setitem__("blockers", blockers))
    if closed_slots is not None:
        def _slots(record):
            for entry in record.values():
                for d in entry["datasets"]:
                    d["closedSlots"] = closed_slots.get(d["id"], [])
        data = _collection_data(built)
        _slots(data)
        html = _with_collection_data_inline(html, data)
    out.write_text(html)
    return out


@pytest.fixture(scope="class")
def dashboard_html_without_blockers(built_dashboard_html, tmp_path_factory) -> Path:
    """The built page with no held supply or contested pair in it.

    WHY THE ENDED-SCHEDULE TESTS NEED IT (REQ-PIPE-115, 2026-10-05). The
    real corpus files cp-case-workers' May and November supplies to no
    period - it takes only February and August, so REQ-PIPE-131 holds
    them - and nobody resolves a hold in a bootstrap. An open hold makes
    the dataset RED, and red OUTRANKS an ended schedule (PROVISIONAL): a
    file is here waiting on a person, so "no supply expected" would be
    untrue. Those tests are about the ended schedule alone, so they read
    a page where nothing is held; TestHeldOutranksAnEndedSchedule covers
    the two together.

    NOR A PERIOD THAT CLOSED WITH NO SUPPLY (REQ-DASH-133, 2026-10-05):
    an unmarked gap is red too and outranks an ended schedule for the
    same reason, so this page carries none - TestClosedWithNoSupply
    covers gaps on a page that has them.
    """
    tmp = tmp_path_factory.mktemp("noblockers")
    return _with_blockers(built_dashboard_html, tmp / "dashboard_no_blockers.html", [],
                          closed_slots={})


@pytest.fixture(scope="class")
def dashboard_html_with_blockers(built_dashboard_html, tmp_path_factory) -> Path:
    """Exactly two blockers - one held supply, one contested pair - in
    place of whatever the deployment held, so REQ-PIPE-115 criterion 13
    is asserted against a known case rather than a corpus that may have
    none of either."""
    opened = TestAHeldOrContestedDatasetReadsRed.OPENED
    tmp = tmp_path_factory.mktemp("blockers")
    return _with_blockers(built_dashboard_html, tmp / "dashboard_with_blockers.html", [
        {"kind": "held", "datasetId": "cp-carers", "supply": "cp-carers@k1",
         "openedAt": opened, "resolvedAt": None,
         "reason": "cp-carers@k1 could not be placed - no slot was open.",
         "files": [], "loadFailures": [], "delivery": "d1"},
        {"kind": "contested", "datasetId": "cp-clients", "supply": "cp-clients@k2#1",
         "openedAt": opened, "resolvedAt": None,
         "reason": "Two files claim this dataset's table: a.csv and b.csv.",
         "files": ["a.csv", "b.csv"], "loadFailures": [], "delivery": "d2"}])


class TestAHeldOrContestedDatasetReadsRed:
    """REQ-PIPE-115 criterion 13: one dataset held, another contested;
    each reads red with its reason, the red rolls up to its collection
    and agency, and none of its own checks reads as passing."""

    OPENED = "2026-09-01T02:00:00+00:00"
    IN_PLACE_ON = "2026-09-23"
    BEFORE = "2026-08-20"
    CP = "child-protection-family-support"

    def _ds(self, dataset_id):
        return {"tier": "dataset", "agencyId": self.CP, "collectionId": "child-protection",
                "datasetId": dataset_id}

    def test_each_reads_red_with_its_reason_at_the_agency_tier(self, page,
                                                               dashboard_html_with_blockers):
        _goto(page, dashboard_html_with_blockers, state={"tier": "agency", "agencyId": self.CP},
              in_place_on=self.IN_PLACE_ON)
        contested = page.locator("tr[data-blocked=contested]")
        assert contested.count() == 1
        assert "Two files for one table" in contested.inner_text()
        assert contested.locator(".pill.red").count() == 1
        # One reason row: no row count, run date or sparkline beside it.
        assert contested.locator("svg").count() == 0
        # A HELD SUPPLY HAS NO PERIOD, so it no longer replaces the row
        # (criterion 11 as amended 2026-10-05, Keith): the row keeps the
        # latest checked supply's columns, red, with the hold beneath.
        held = page.locator("tr", has=page.locator("[data-waiting-blocker=held]"))
        assert held.count() == 1
        assert "Carer Register" in held.inner_text() and "Held" in held.inner_text()
        assert held.locator(".pill.red").count() == 1

    def test_the_red_rolls_up_to_the_collection_and_the_agency(self, page,
                                                               dashboard_html_with_blockers):
        _goto(page, dashboard_html_with_blockers, state={"tier": "agency", "agencyId": self.CP},
              in_place_on=self.IN_PLACE_ON)
        statuses = page.evaluate(f"""() => {{
            const ag = DATA.agencies.find(a => a.id === "{self.CP}");
            return {{agency: ag.status, collection: ag.collections[0].status}};
        }}""")
        assert statuses == {"agency": "red", "collection": "red"}

    @pytest.mark.parametrize("dataset_id", ["cp-clients"])
    def test_none_of_its_own_checks_reads_as_passing(self, page, dashboard_html_with_blockers,
                                                     dataset_id):
        _goto(page, dashboard_html_with_blockers, state=self._ds(dataset_id), in_place_on=self.IN_PLACE_ON)
        got = page.evaluate(f"""() => {{
            const ds = DATA.agencies.flatMap(a => a.collections).flatMap(c => c.datasets)
                           .find(d => d.id === "{dataset_id}");
            // ITS OWN checks (REQ-DASH-264 criterion 3): a cross-table row
            // that ran since, on a reading table's supply, shows what it found.
            const own = ds.columns.filter(c => c.scope !== "cross-table");
            return {{status: ds.status,
                     checks: [...new Set(own.flatMap(c => c.checks).map(checkStatus))],
                     columns: [...new Set(own.map(c => c.status))]}};
        }}""")
        assert got["status"] == "red"
        assert got["checks"] in ([], ["nodata"]) and got["columns"] in ([], ["nodata"])
        text = " ".join(page.locator("#view").inner_text().split())
        assert "this dataset's own supply is not checked until a person resolves it" in text
        assert "Every check on this dataset's own data reads No data for this period" in text
        assert page.locator("#col-grid .pill.green").count() == 0

    def test_a_held_supply_keeps_the_latest_checked_results(self, page,
                                                            dashboard_html_with_blockers):
        """Criterion 11 as amended 2026-10-05 (Keith): an open hold no
        longer blanks later periods - red with its reason, the latest
        checked supply's results shown."""
        _goto(page, dashboard_html_with_blockers, state=self._ds("cp-carers"), in_place_on=self.IN_PLACE_ON)
        got = page.evaluate("""() => {
            const ds = DATA.agencies.flatMap(a => a.collections).flatMap(c => c.datasets)
                           .find(d => d.id === "cp-carers");
            return {status: ds.status,
                    checks: [...new Set(ds.columns.flatMap(c => c.checks).map(checkStatus))]};
        }""")
        assert got["status"] == "red"
        assert got["checks"] and got["checks"] != ["nodata"]
        text = " ".join(page.locator("#view").inner_text().split())
        assert "The dataset stays red until a person resolves it" in text

    def test_its_check_panel_does_not_show_an_earlier_run_as_current(
            self, page, dashboard_html_with_blockers):
        """Criteria 11 and 26 in the check panel (delivery-critic, sprint 6):
        the pill read No data while the panel still showed the last run's
        value and row counts as "current"."""
        _goto(page, dashboard_html_with_blockers, state=self._ds("cp-clients"), in_place_on=self.IN_PLACE_ON)
        page.evaluate("""() => {
          const ctx = resolveContext(STATE);
          const col = ctx.ds.columns.find(c => c.checks && c.checks.length);
          openCheckPanel(ctx.ag, ctx.col, ctx.ds, col, col.checks[0]);
        }""")
        # innerText carries the CSS text-transform, so the heading reads
        # upper case here - compared case-insensitively for that reason.
        text = " ".join(page.locator("body").inner_text().split()).lower()
        assert "not run for this period" in text
        assert "rows checked, current run" not in text

    def test_its_supply_history_lists_it(self, page, dashboard_html_with_blockers):
        _goto(page, dashboard_html_with_blockers, state=self._ds("cp-carers"), in_place_on=self.IN_PLACE_ON)
        assert page.locator("tr[data-blocker=held]").count() == 1

    def test_before_its_receipt_nothing_is_red_for_it(self, page, dashboard_html_with_blockers):
        """Criterion 12: open from the supply's own receipt, so the as-of
        view of an earlier date shows what a reader saw then."""
        _goto(page, dashboard_html_with_blockers, state={"tier": "agency", "agencyId": self.CP},
              in_place_on=self.BEFORE)
        assert page.locator("tr[data-blocked]").count() == 0


class TestHeldOutranksAnEndedSchedule:
    """The two together (PROVISIONAL, 2026-10-05): a held supply on a
    dataset whose schedule has ended reads RED with the hold's reason,
    not as the quiet ended-schedule row - a file arrived and waits on a
    person, so "no supply expected" would be untrue."""

    def test_the_row_says_held(self, page, built_dashboard_html, tmp_path):
        out = _with_blockers(built_dashboard_html, tmp_path / "both.html", [
            {"kind": "held", "datasetId": "cp-case-workers", "supply": "cp-case-workers@k",
             "openedAt": "2027-08-20T02:00:00+00:00", "resolvedAt": None,
             "reason": "could not be placed", "files": [], "loadFailures": []}])
        _goto(page, out, state={"tier": "agency", "agencyId": "child-protection-family-support"},
              in_place_on="2027-09-15")
        # A held supply keeps the row (REQ-PIPE-115 criterion 11 as amended
        # 2026-10-05), red, with the hold beneath its pill.
        row = page.locator("tr", has=page.locator("[data-waiting-blocker=held]"))
        assert row.count() == 1 and "Case Workers" in row.inner_text()
        assert row.locator(".pill.red").count() == 1


class TestASupplyThatCouldNotBeLoaded:
    """REQ-DASH-148 criterion 9 and REQ-PIPE-153 criterion 15: one Child
    Protection table could not be loaded while the other five loaded. Its
    dataset reads red with the reason and rolls up; none of its own checks
    reads as passing; the other five are checked as usual. Once a person
    rejects it, it is no longer red on that account - and still is as at
    an instant between the failure and the rejection."""

    CP = "child-protection-family-support"
    FAILED = "2026-09-01T02:00:00+00:00"
    REJECTED = "2026-09-10T02:00:00+00:00"

    def _page(self, built, tmp_path, *, rejected: bool):
        return _with_blockers(built, tmp_path / f"refused{int(rejected)}.html", [
            {"kind": "refused", "datasetId": "cp-placements", "supply": "cp-placements@k",
             "openedAt": self.FAILED,
             "resolvedAt": self.REJECTED if rejected else None,
             "reason": "The supply could not be loaded: malformed row: line 3 has 4 fields "
                       "where 2 were expected. Nothing can read the table, so nothing is checked.",
             "files": [], "loadFailures": [], "delivery": "d",
             "rejected": ({"actor": "Keith Moss", "at": self.REJECTED,
                           "reason": "supplier is resending"} if rejected else None)}])

    def _status(self, page, dataset_id):
        return page.evaluate(f"""() => DATA.agencies.flatMap(a => a.collections)
            .flatMap(c => c.datasets).find(d => d.id === "{dataset_id}").status""")

    def test_it_reads_red_with_the_reason_and_the_rest_are_checked(self, page, tmp_path,
                                                                   built_dashboard_html):
        out = self._page(built_dashboard_html, tmp_path, rejected=False)
        _goto(page, out, state={"tier": "agency", "agencyId": self.CP}, in_place_on="2026-09-23")
        row = page.locator("tr[data-blocked=refused]")
        assert row.count() == 1 and "Could not be loaded" in row.inner_text()
        assert self._status(page, "cp-placements") == "red"
        assert page.evaluate(f"""() => DATA.agencies.find(a => a.id === "{self.CP}").status""") == "red"
        others = page.evaluate("""() => DATA.agencies.flatMap(a => a.collections)
            .flatMap(c => c.datasets).filter(d => d.id.startsWith("cp-") && d.id !== "cp-placements")
            .map(d => !!d.blocked)""")
        assert others and not any(others)

    def test_its_own_checks_do_not_read_as_passing(self, page, tmp_path, built_dashboard_html):
        out = self._page(built_dashboard_html, tmp_path, rejected=False)
        _goto(page, out, state={"tier": "dataset", "agencyId": self.CP,
                                "collectionId": "child-protection", "datasetId": "cp-placements"},
              in_place_on="2026-09-23")
        text = " ".join(page.locator("#view").inner_text().split())
        assert "line 3 has 4 fields" in text
        assert page.locator("#col-grid .pill.green").count() == 0

    def test_a_rejection_settles_it_and_the_in_place_on_view_still_shows_it(self, page, tmp_path,
                                                                     built_dashboard_html):
        out = self._page(built_dashboard_html, tmp_path, rejected=True)
        _goto(page, out, state={"tier": "agency", "agencyId": self.CP}, in_place_on="2026-09-23")
        assert page.locator("tr[data-blocked=refused]").count() == 0
        _goto(page, out, state={"tier": "agency", "agencyId": self.CP}, in_place_on="2026-09-05")
        assert page.locator("tr[data-blocked=refused]").count() == 1
        _goto(page, out, state={"tier": "dataset", "agencyId": self.CP,
                                "collectionId": "child-protection", "datasetId": "cp-placements"},
              in_place_on="2026-09-23")
        row = page.locator("tr[data-blocker=refused]")
        assert row.count() == 1
        assert "rejected by Keith Moss" in row.inner_text()
        assert "supplier is resending" in row.inner_text()


class TestClosedWithNoSupply:
    """REQ-DASH-133: a period that closed with nothing in it reads RED and
    says 'no supply' at agency and dataset level, consecutive periods as
    one item; a period a person accepted reads quietly with its reason and
    stays out of the red; both are judged as at the date on show and both
    stay in the supply history. Injected rather than taken from the corpus,
    so the assertions do not depend on which gaps a bootstrap happened to
    leave."""

    CP = "child-protection-family-support"
    DS = {"tier": "dataset", "agencyId": CP, "collectionId": "child-protection",
          "datasetId": "cp-clients"}
    MARKED = "2026-09-10T02:00:00+00:00"

    def _slot(self, period, index, closes, **extra):
        return {"period": period, "index": index, "closesAt": closes, "changes": [],
                "filedAt": None, "marks": [], "rejected": None, **extra}

    def _page(self, built, tmp_path):
        slots = [self._slot("2025-Q2", 5, "2025-08-15T16:00:00+00:00"),
                 self._slot("2025-Q3", 6, "2025-11-15T16:00:00+00:00"),
                 self._slot("2024-Q4", 2, "2025-02-15T16:00:00+00:00",
                            marks=[{"at": self.MARKED, "actor": "Keith Moss",
                                    "reason": "supplier had a system outage"}])]
        return _with_blockers(built, tmp_path / "gaps.html", [],
                              closed_slots={"cp-clients": slots})

    def _ds(self, page, dataset_id="cp-clients"):
        return page.evaluate(f"""() => {{ const d = DATA.agencies.flatMap(a => a.collections)
            .flatMap(c => c.datasets).find(d => d.id === "{dataset_id}");
            return {{status: d.status, noSupply: d.noSupply, accepted: d.acceptedGaps}}; }}""")

    def test_an_unmarked_gap_is_red_and_rolls_up_in_words(self, page, tmp_path,
                                                         built_dashboard_html):
        out = self._page(built_dashboard_html, tmp_path)
        _goto(page, out, in_place_on="2026-09-23")
        assert self._ds(page)["status"] == "red"
        assert page.evaluate(f"""() => DATA.agencies.find(a => a.id === "{self.CP}").status""") == "red"
        card = page.locator(f'a.card[href*="{self.CP}"]')
        text = " ".join(card.inner_text().split())
        assert "1 no supply" in text, text
        assert "1 dataset with a period accepted as not supplied" in text, text

    def test_consecutive_periods_are_one_item_on_the_agency_page(self, page, tmp_path,
                                                                built_dashboard_html):
        out = self._page(built_dashboard_html, tmp_path)
        _goto(page, out, state={"tier": "agency", "agencyId": self.CP}, in_place_on="2026-09-23")
        note = page.locator("[data-no-supply]")
        assert note.count() == 1
        assert "2 periods with no supply, 2025-Q2 to 2025-Q3" in note.inner_text()

    def test_the_dataset_page_says_no_supply_and_names_the_accepted_reason(
            self, page, tmp_path, built_dashboard_html):
        out = self._page(built_dashboard_html, tmp_path)
        _goto(page, out, state=self.DS, in_place_on="2026-09-23")
        text = " ".join(page.locator("#view").inner_text().split())
        assert "No supply — 2 periods with no supply, 2025-Q2 to 2025-Q3" in text
        assert "Not supplied (accepted)" in text and "supplier had a system outage" in text
        # Chase the supplier first, then the filing wizard, which offers all
        # three decisions (Keith, 2026-10-05; post-build-review #104).
        assert "Chase the supplier first" in text
        assert "Filing decisions" in text, "and names where to decide it"

    def test_the_supply_history_lists_every_closed_period(self, page, tmp_path,
                                                        built_dashboard_html):
        out = self._page(built_dashboard_html, tmp_path)
        _goto(page, out, state=self.DS, in_place_on="2026-09-23")
        assert page.locator("tr[data-gap=open]").count() == 1
        assert page.locator("tr[data-gap=accepted]").count() == 1

    def test_in_place_on_before_the_mark_the_accepted_period_was_still_red(
            self, page, tmp_path, built_dashboard_html):
        out = self._page(built_dashboard_html, tmp_path)
        _goto(page, out, in_place_on="2025-06-01")
        got = self._ds(page)
        assert got["accepted"] is None, "not marked yet on this date"
        assert [g["periods"] for g in got["noSupply"]] == [["2024-Q4"]], \
            "and Q2/Q3 had not closed yet"

    def test_a_daily_feed_awaiting_todays_file_keeps_its_row(self, page, tmp_path,
                                                            built_dashboard_html):
        """UX critic, 2026-10-05: the reason row is for a dataset with
        nothing current at all. A daily feed whose file for the day on
        show has not arrived (23 September has no Birth Registrations
        run in the seeded corpus) keeps its arrival columns, with the old
        gap beneath its pill - the period actually late and still open
        must not be hidden behind it."""
        slot = self._slot("2026-09-09", 250, "2026-09-09T16:00:00+00:00")
        out = _with_blockers(built_dashboard_html, tmp_path / "daily.html", [],
                             closed_slots={"birth-registrations": [slot]})
        _goto(page, out, state={"tier": "agency", "agencyId": "registry-services"},
              in_place_on="2026-09-23")
        assert page.locator("tr[data-no-supply]").count() == 0
        note = page.locator(".no-supply-note")
        assert note.count() == 1 and "9 September 2026" in note.inner_text()


class TestFileChecksOnThePage:
    """REQ-DASH-097 criterion 12, against the bootstrapped history rather
    than a fixture (Keith's choice, 2026-10-04): TS-12 plants a Child
    Protection delivery whose cp_clients goes ragged partway, refused by
    the fields-per-row file check; TS-56 plants cp_carers with its columns
    reordered, which only warns. Zero console errors comes from the page
    fixture this suite runs under."""

    CP = "child-protection-family-support"

    def _placement(self, scenario):
        from qa_tools.common import scenario_map

        placement = scenario_map.read_placements().get(scenario)
        if placement is None or not placement.is_complete:
            pytest.skip(f"{scenario} is not placed in this history")
        return placement

    def _dataset(self, page, dataset_id):
        return page.evaluate(f"""() => DATA.agencies.flatMap(a => a.collections)
            .flatMap(c => c.datasets).find(d => d.id === "{dataset_id}")""")

    def test_a_refused_file_reads_red_naming_the_check(self, clean_page, built_dashboard_html):
        placement = self._placement("TS-12")
        _goto(clean_page, built_dashboard_html,
              state={"tier": "dataset", "agencyId": self.CP, "collectionId": "child-protection",
                     "datasetId": "cp-clients"}, in_place_on=placement.in_place_on)
        section = clean_page.locator(".file-section")
        assert section.get_attribute("data-file-outcome") == "refused"
        assert "fields per row" in section.inner_text().lower()
        assert "file check" in section.inner_text().lower()
        ds = self._dataset(clean_page, "cp-clients")
        assert ds["status"] == "red"
        # By the check's NAME, in one sentence (post-build-review #118 D-G).
        assert ds["blocked"] and "Fields per row" in ds["blocked"]["reason"]
        assert ".." not in ds["blocked"]["reason"]
        # Its waiting item shows on the scenario's own date too (#118 D-B).
        assert "Nothing is waiting for a person here" not in clean_page.inner_text("body")
        assert clean_page.evaluate(
            f"""() => DATA.agencies.find(a => a.id === "{self.CP}").status""") == "red"

    def test_a_warned_file_leaves_the_status_alone(self, clean_page, built_dashboard_html):
        placement = self._placement("TS-56")
        _goto(clean_page, built_dashboard_html,
              state={"tier": "dataset", "agencyId": self.CP, "collectionId": "child-protection",
                     "datasetId": "cp-carers"}, in_place_on=placement.in_place_on)
        section = clean_page.locator(".file-section")
        assert section.get_attribute("data-file-outcome") == "warned"
        assert "column order" in section.inner_text().lower()
        ds = self._dataset(clean_page, "cp-carers")
        assert not ds.get("blocked")
        # Unchanged: the dataset's status is exactly its data checks' roll-up.
        own = clean_page.evaluate("""() => {
            const d = DATA.agencies.flatMap(a => a.collections).flatMap(c => c.datasets)
              .find(d => d.id === "cp-carers");
            return rollupStatuses((d.columns||[]).map(c => c.status));
        }""")
        assert ds["status"] == own


class TestSampleFinePrint:
    """post-build-review #129 (Keith 2026-10-07): the example failing rows
    say which rows they are, in the real panel."""

    def test_a_soda_check_past_its_limit_says_soda_chose_them(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        text = clean_page.evaluate("""() => {
          const ctx = resolveContext(STATE);
          const col = ctx.ds.columns.find(c => c.checks && c.checks.length);
          const ck = col.checks[0];
          ck.tool_ref = "soda:missing_count";
          for (const h of ck.history) {
            h.failing_sample_keys = ["A1", "A2", "A3", "A4", "A5"];
            h.row_count_invalid = 250;
          }
          openColumnDrawer(ctx.ag, ctx.col, ctx.ds, col);
          openCheckPanel(ctx.ag, ctx.col, ctx.ds, col, ck);
          const fp = document.querySelector('#check-panel-body .sample-fine-print');
          return fp ? fp.textContent : null;
        }""")
        assert text and "Soda returns up to 100 of the failing rows" in text


class TestAChecksChartNamesWhatItMeasures:
    """REQ-DASH-228: a check's trend chart says what quantity it plots and
    in what unit, above the plot and as the table's column header - one
    check of each unit, count, % and PSI, on the real built dashboard."""

    @pytest.mark.parametrize("kind,expected", [
        ("dbt:not_null", "Rows with no value (count)"),
        ("soda:invalid_percent", "Invalid values (%)"),
        ("evidently:drift_psi", "Drift score (PSI)"),
    ])
    def test_axis_title_and_table_header_name_the_measure(
            self, clean_page, built_dashboard_html, kind, expected):
        _goto(clean_page, built_dashboard_html, _BDM)
        found = clean_page.evaluate("""(kind) => {
          const ctx = resolveContext(STATE);
          for (const col of ctx.ds.columns) {
            const ck = (col.checks || []).find(c => c.tool_ref === kind);
            if (ck) {
              openColumnDrawer(ctx.ag, ctx.col, ctx.ds, col);
              openCheckPanel(ctx.ag, ctx.col, ctx.ds, col, ck);
              return true;
            }
          }
          return false;
        }""", kind)
        assert found, f"no {kind} check on the Birth Registrations page"
        body = clean_page.locator("#check-panel-body")
        title = body.locator(".chart-axis-title")
        assert title.is_visible()
        assert title.inner_text().strip() == expected
        body.locator("[data-toggle-table]").first.click()
        header = body.locator(".trend-table thead th").nth(1)
        assert header.is_visible()
        assert header.inner_text().strip() == expected


class TestAStaleDatasetsSectionsSayNoData:
    """post-build-review #183: on a date a dataset has nothing in its current
    period, its column tiles roll up to 'No data' (Phase 5g) but its check
    sections' head pills still rolled up the old run's verdicts - a green
    claim about a period nothing was checked for. Found building REQ-DASH-225,
    whose row count is checked against exactly these pills."""

    def test_section_heads_go_quiet_with_the_tiles(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        seen = clean_page.evaluate("""() => ({
          stale: !!resolveContext(STATE).ds.noDataInPlaceOn,
          tiles: [...document.querySelectorAll('.col-tile')].map(b => b.dataset.status),
          heads: [...document.querySelectorAll('.scope-section .head .pill')].map(p => p.className)})""")
        assert seen["stale"], "precondition: Birth Registrations is daily and stale on the build's own date"
        assert seen["tiles"] and set(seen["tiles"]) == {"nodata"}
        assert seen["heads"], "precondition: it has a check section"
        assert all("nodata" in c for c in seen["heads"]), seen["heads"]

    def test_no_tile_lines_key_when_no_tile_draws_lines(self, clean_page, built_dashboard_html):
        """post-build-review #184 (D3): the line explaining the tiles' two
        lines showed above thirteen 'No data' tiles that draw none."""
        _goto(clean_page, built_dashboard_html, _BDM)
        seen = clean_page.evaluate("""() => ({
          lines: document.querySelectorAll('.col-tile svg').length,
          key: document.querySelectorAll('.tile-lines-key').length})""")
        assert seen["lines"] == 0, "precondition: a stale dataset's tiles draw no lines"
        assert seen["key"] == 0


class TestColumnsNotGreenMatchesTheDatasetPage:
    """REQ-DASH-225 criterion 18: each ordinary row's 'Columns not green'
    count says what the dataset's own page shows - its red and amber column
    tiles and check sections, of those with a verdict - and the lines' last
    point (their accessible name) says the same, at the build's own date and
    at an earlier one."""

    # Read from the hierarchy, never listed (REQ-DASH-234 criterion 5).
    _AGENCIES = list(dict.fromkeys(c.agency_id for c in _registry.all_collections()))

    def _rows(self, page):
        return page.evaluate("""() => [...document.querySelectorAll('tr[data-nav]')]
          .filter(tr => tr.querySelector('.not-green-td'))
          .map(tr => {
            const td = tr.querySelector('.not-green-td');
            const svg = td.querySelector('svg.spark');
            return {nav: JSON.parse(tr.dataset.nav), text: td.innerText.replace(/\\s+/g, ' ').trim(),
                    label: svg ? svg.getAttribute('aria-label') : null};
          })""")

    def _page_counts(self, page):
        return page.evaluate("""() => {
          const st = [...document.querySelectorAll('.col-tile')].map(b => b.dataset.status)
            .concat([...document.querySelectorAll('.scope-section .head .pill')]
              .map(p => ['red','amber','green'].find(s => p.classList.contains(s)) || 'other'));
          return {red: st.filter(s => s === 'red').length, amber: st.filter(s => s === 'amber').length,
                  counted: st.filter(s => ['red','amber','green'].includes(s)).length};
        }""")

    @staticmethod
    def _parse(text):
        import re
        m = re.match(r"(\d+) of (\d+) (\d+) red, (\d+) amber", text)
        if m:
            n, total, red, amber = map(int, m.groups())
            assert n == red + amber, text
            return {"red": red, "amber": amber, "counted": total}
        m = re.match(r"All (\d+) green", text)
        assert m, f"unexpected cell text {text!r}"
        return {"red": 0, "amber": 0, "counted": int(m.group(1))}

    def test_each_point_of_a_rows_lines_names_its_cause(self, clean_page, built_dashboard_html):
        """REQ-PIPE-279 criterion 13 on the list (Keith, 2026-10-24, reversing
        provisional #18): every point of a row's sparkline has a tooltip
        naming the run or re-check that caused it, in the panel's words, and
        the sparkline keeps its one accessible name."""
        import re
        titles, sparks = [], 0
        for agency in self._AGENCIES:
            _goto(clean_page, built_dashboard_html, {"tier": "agency", "agencyId": agency})
            for got in clean_page.evaluate("""() => [...document.querySelectorAll(
                  'tr[data-nav] .not-green-td svg.spark')].map(svg => ({
                    labels: svg.querySelectorAll('[aria-label]').length + 1,
                    titles: [...svg.querySelectorAll('title')].map(t => t.textContent)}))"""):
                sparks += 1
                assert got["labels"] == 1 and got["titles"], got
                titles += got["titles"]
        assert sparks, "no row drew a sparkline - this proves nothing"
        bad = [s for s in titles if not re.match(r"^From the .+'s (run|re-check)(, .+)?$", s)]
        assert not bad, bad[:5]

    # 15 May 2025: the readers are red there (see TestTheDatasetPageSaysWhatItsTrendPlots).
    @pytest.mark.parametrize("in_place_on", [None, "2025-05-15"])
    def test_each_rows_count_matches_its_dataset_page(self, clean_page, built_dashboard_html, in_place_on):
        import re
        checked, not_green = 0, 0
        for agency in self._AGENCIES:
            _goto(clean_page, built_dashboard_html, {"tier": "agency", "agencyId": agency}, in_place_on)
            for row in self._rows(clean_page):
                if row["text"].startswith("No column has a verdict"):
                    _goto(clean_page, built_dashboard_html, row["nav"], in_place_on)
                    assert self._page_counts(clean_page)["counted"] == 0, row
                    _goto(clean_page, built_dashboard_html, {"tier": "agency", "agencyId": agency}, in_place_on)
                    continue
                said = self._parse(row["text"])
                if row["label"]:
                    m = re.search(r"latest (\d+) red and (\d+) amber of (\d+)", row["label"])
                    assert m and list(map(int, m.groups())) == [said["red"], said["amber"], said["counted"]], row
                _goto(clean_page, built_dashboard_html, row["nav"], in_place_on)
                shown = self._page_counts(clean_page)
                assert shown == said, (row["nav"]["datasetId"], in_place_on, said, shown)
                checked += 1
                not_green += said["red"] + said["amber"] > 0
                _goto(clean_page, built_dashboard_html, {"tier": "agency", "agencyId": agency}, in_place_on)
        assert checked >= 5, "precondition: most real datasets have an ordinary row"
        # At the build's own date every dataset can legitimately be all
        # green - it is, since REQ-GEN-207 moved TS-56 to the newest quarter
        # (held, so nothing amber is in place). The earlier date is the run
        # that must have something not green, or this proves nothing.
        if in_place_on is not None:
            assert not_green, "precondition: at least one dataset is not all green, or this proves nothing"


class TestTheDatasetPageSaysWhatItsTrendPlots:
    """REQ-DASH-227 criterion 9: on a real dataset with a unit that is not
    green at the build's own date, the dataset page's trend says what it
    plots in words, its table's latest row agrees with the dataset list, and
    the column panel's latest row agrees with the checks listed in it."""

    _CP = {"tier": "agency", "agencyId": "child-protection-family-support"}
    # A date with a Child Protection unit not green in place. The build's own
    # date need not have one (since REQ-GEN-207 every dataset is all green
    # there), and a test that depends on the newest quarter being red has a
    # shelf life of one quarter. 15 May, not 15 June, since REQ-DASH-264: the
    # readers' Client reference is red from their 1 May supply until the Client
    # Register's late supply re-checks it green on 29 May.
    _ON = "2025-05-15"

    def test_trend_title_axis_and_table_agree_with_the_list_and_the_panel(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, self._CP, self._ON)
        row = clean_page.evaluate("""() => [...document.querySelectorAll('tr[data-nav]')]
          .map(tr => ({nav: JSON.parse(tr.dataset.nav), td: tr.querySelector('.not-green-td')}))
          .filter(r => r.td && /\\d+ red, \\d+ amber/.test(r.td.innerText))
          .map(r => ({nav: r.nav, text: r.td.innerText.replace(/\\s+/g, ' ').trim()}))[0] || null""")
        assert row, "precondition: a Child Protection dataset has a unit that is not green"
        import re
        n, m, red, amber = map(int, re.match(r"(\d+) of (\d+) (\d+) red, (\d+) amber", row["text"]).groups())

        _goto(clean_page, built_dashboard_html, row["nav"], self._ON)
        trend = clean_page.locator('[data-unit-trend="dataset"]')
        assert trend.locator(".unit-trend-title").inner_text().strip() == "Columns red and amber, each QA run"
        assert trend.locator(".chart-axis-title").inner_text().strip() == "% of columns"
        assert trend.locator(".legend-key").is_visible()
        trend.locator("[data-toggle-unit-table]").click()
        latest = trend.locator(".trend-table tbody tr").first.locator("td").all_inner_texts()
        assert [int(latest[1]), int(latest[2])] == [red, amber]
        assert latest[3] == f"{n} of {m} not green"

        tile = clean_page.locator('.col-tile[data-status="red"], .col-tile[data-status="amber"]').first
        if tile.count() == 0:
            tile = clean_page.locator(".col-tile").first
        tile.click()
        panel = clean_page.locator('[data-unit-trend="column"]')
        assert panel.locator(".unit-trend-title").inner_text().strip() == "Checks on this column red and amber, each QA run"
        assert panel.locator(".chart-axis-title").inner_text().strip() == "% of checks"
        panel.locator("[data-toggle-unit-table]").click()
        cells = panel.locator(".trend-table tbody tr").first.locator("td").all_inner_texts()
        listed = clean_page.evaluate("""() => {
          const pills = [...document.querySelectorAll('#drawer-body .check-card:not(.is-retired) .pill')];
          const has = s => pills.filter(p => p.classList.contains(s)).length;
          return {red: has('red'), amber: has('amber'), counted: has('red') + has('amber') + has('green')};
        }""")
        assert [int(cells[1]), int(cells[2])] == [listed["red"], listed["amber"]]
        assert cells[3].endswith(f"of {listed['counted']} not green")


class TestDatasetsNotGreenOnCardsAndHeadings:
    """REQ-DASH-226 criterion 12: each agency card's and each collection
    heading's count of datasets not green agrees with the pills of the
    datasets it counts on the agency tier, and its weekly trend ends on the
    same numbers - at the build's own date and at an earlier one."""

    # Read from the hierarchy, never listed (REQ-DASH-234 criterion 5).
    _AGENCIES = list(dict.fromkeys(c.agency_id for c in _registry.all_collections()))

    @staticmethod
    def _said(text):
        import re
        if not text:
            return None
        m = re.match(r"(\d+) of (\d+) (?:counted )?datasets? not green (\d+) red, (\d+) amber", text)
        if m:
            n, total, red, amber = map(int, m.groups())
            assert n == red + amber, text
            return [red, amber, total]
        m = re.match(r"All (\d+) (?:counted )?datasets? green", text)
        assert m, text
        return [0, 0, int(m.group(1))]

    @staticmethod
    def _latest(label):
        import re
        m = re.search(r"latest (\d+) red and (\d+) amber of (\d+)", label or "")
        return list(map(int, m.groups())) if m else None

    def _wait_trends(self, page):
        page.wait_for_function("() => document.querySelector('[data-trends-drawn]')")

    @pytest.mark.parametrize("in_place_on", [None, "2025-06-15"])
    def test_counts_and_trends_agree_with_the_pills(self, clean_page, built_dashboard_html, in_place_on):
        _goto(clean_page, built_dashboard_html, {"tier": "exec"}, in_place_on)
        self._wait_trends(clean_page)
        cards = clean_page.evaluate("""() => [...document.querySelectorAll('a.card[data-agency]')].map(a => ({
          id: a.dataset.agency,
          text: (a.querySelector('.datasets-not-green') || {innerText: ''}).innerText.replace(/\\s+/g, ' ').trim(),
          label: (a.querySelector('.datasets-trend svg') || {getAttribute: () => null}).getAttribute('aria-label')}))""")
        if in_place_on is None:
            assert any((self._said(c["text"]) or [0, 0])[0] + (self._said(c["text"]) or [0, 0])[1] > 0
                       for c in cards), "precondition: some agency card has a dataset not green"
        for card in cards:
            said = self._said(card["text"])
            _goto(clean_page, built_dashboard_html, {"tier": "agency", "agencyId": card["id"]}, in_place_on)
            self._wait_trends(clean_page)
            pills = clean_page.evaluate("""() => {
              const ctx = {ag: DATA.agencies.find(a => a.id === STATE.agencyId)};
              const tally = ds => {
                const c = ds.filter(d => inRollup(d) && ['red','amber','green'].includes(d.status));
                // the pill each counted dataset shows in its row
                const shown = c.map(d => {
                  const tr = [...document.querySelectorAll('tr[data-nav]')].find(r => JSON.parse(r.dataset.nav).datasetId === d.id);
                  const p = tr && tr.querySelector('td:nth-child(2) .pill');
                  return p ? ['red','amber','green'].find(s => p.classList.contains(s)) : null;
                });
                return [shown.filter(s => s === 'red').length, shown.filter(s => s === 'amber').length, shown.length];
              };
              return {agency: tally(ctx.ag.collections.flatMap(c => c.datasets)),
                      collections: ctx.ag.collections.map(col => {
                        const el = document.querySelector(`.collection-not-green[data-collection="${col.id}"]`);
                        const line = el.querySelector('.datasets-not-green');
                        const svg = el.querySelector('.datasets-trend svg');
                        return {pills: tally(col.datasets), text: line ? line.innerText.replace(/\\s+/g, ' ').trim() : '',
                                label: svg ? svg.getAttribute('aria-label') : null};
                      })};
            }""")
            if said is not None:
                assert said == pills["agency"], (card["id"], in_place_on, said, pills["agency"])
                if card["label"]:
                    assert self._latest(card["label"]) == said, card
            for col in pills["collections"]:
                col_said = self._said(col["text"])
                if col_said is not None:
                    assert col_said == col["pills"], (card["id"], col)
                    if col["label"]:
                        assert self._latest(col["label"]) == col_said, col
            _goto(clean_page, built_dashboard_html, {"tier": "exec"}, in_place_on)
            self._wait_trends(clean_page)


class TestTheFeedbackTab:
    """REQ-DASH-220: one card per road-testing entry, with the status derived
    from the requirements it cites, reached at #/feedback."""

    def _cards(self):
        from dashboard.plans_md import feedback_data
        cards = feedback_data(ROOT / "plans", ROOT / "requirements.yaml")["cards"]
        assert cards, "precondition: plans/road-testing.md has cards"
        return cards

    def test_it_shows_every_card_with_its_derived_status(self, clean_page, built_dashboard_html):
        cards = self._cards()
        _goto(clean_page, built_dashboard_html, {"tier": "feedback"})
        assert clean_page.locator("#view h2").inner_text().strip() == "Feedback"
        shown = clean_page.locator(".fb-card")
        assert shown.count() == len(cards)
        statuses = sorted(clean_page.evaluate(
            "() => [...document.querySelectorAll('.fb-card')].map(c => c.dataset.fbStatus)"))
        assert statuses == sorted(c["status"] for c in cards)
        # One pill per card, never a data verdict's colour (criteria 7, 17).
        assert clean_page.locator(".fb-card .pill").count() == len(cards)
        assert clean_page.locator(".fb-card .pill.red, .fb-card .pill.amber, .fb-card .pill.green").count() == 0
        # The reviewer is never named, and no entry number is shown (4, 13).
        text = clean_page.locator("#view").inner_text()
        assert "Keith" not in text and "#1" not in text

    def test_the_header_entry_is_a_real_link_and_the_route_survives_back(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        link = clean_page.locator("a#feedback-btn")
        assert link.get_attribute("href") == "#/feedback"
        link.click()
        clean_page.wait_for_function("() => STATE.tier === 'feedback'")
        assert clean_page.url.endswith("#/feedback")
        clean_page.go_back()
        clean_page.wait_for_function("() => STATE.tier === 'exec'")
        clean_page.go_forward()
        clean_page.wait_for_function("() => STATE.tier === 'feedback'")

    def test_a_requirement_link_opens_the_panel_there_and_focus_comes_back(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, {"tier": "feedback"})
        link = clean_page.locator(".fb-card a[data-req-link]").first
        rid = link.get_attribute("data-req-link")
        link.click()
        clean_page.wait_for_function("(r) => STATE.panel === 'requirements' && STATE.req === r", arg=rid)
        clean_page.keyboard.press("Escape")
        clean_page.wait_for_function("() => !STATE.panel && STATE.tier === 'feedback'")
        assert clean_page.evaluate("() => document.activeElement.dataset.reqLink") == rid

    def test_a_past_date_link_lands_as_a_jump_and_back_returns(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, {"tier": "feedback"})
        today = clean_page.evaluate("() => CURRENT_IN_PLACE_ON")
        link = clean_page.locator('.fb-card a[data-fb-link*="2023-08-05"]').first
        assert link.count() == 1, "precondition: a card cites a past date"
        link.click()
        clean_page.wait_for_function("() => STATE.tier === 'dataset'")
        assert clean_page.evaluate("() => CURRENT_IN_PLACE_ON") == "2023-08-05"
        bar = clean_page.locator('[data-testid="scenario-jump-bar"]').inner_text()
        assert "Viewing" in bar and "not today" in bar and " for " not in bar
        clean_page.go_back()
        clean_page.wait_for_function("() => STATE.tier === 'feedback'")
        assert clean_page.evaluate("() => CURRENT_IN_PLACE_ON") == today


class TestClosingASidePanelReachedByItsUrl:
    """post-build-review #180 (2026-10-14): the side-panel twin of
    road-testing #8. closePanel() always called history.back(), which is
    right only when the app itself pushed the panel's entry. A panel the
    page was LOADED with - `?panel=<name>` pasted, shared or opened in a
    new tab - has whatever came before the dashboard underneath, so X,
    the backdrop or Escape left the dashboard (and in a tab with no
    history at all, did nothing, so the panel could not be closed).
    It now closes in place there, dropping `panel=` from the address."""

    PANELS = ["activity", "changelog", "requirements", "snapshots", "leaderboard"]

    def _cold_load(self, page, html_path, name):
        page.goto("about:blank")
        page.goto(f"file://{html_path.resolve()}?panel={name}")
        page.wait_for_function("() => Number(document.documentElement.dataset.renderCount || 0) > 0")
        assert page.locator(f"#{name}-panel").get_attribute("aria-hidden") == "false", \
            "precondition: the panel opens from its address"

    def _assert_closed_on_the_dashboard(self, page, name):
        assert page.url.startswith("file://") and "qa-reporting-dashboard" in page.url, page.url
        assert f"panel={name}" not in page.url
        assert page.locator(f"#{name}-panel").get_attribute("aria-hidden") == "true"
        assert page.evaluate("() => STATE.panel || null") is None

    @pytest.mark.parametrize("name", PANELS)
    def test_its_close_button_closes_it_and_stays_on_the_dashboard(self, clean_page,
                                                                   built_dashboard_html, name):
        self._cold_load(clean_page, built_dashboard_html, name)
        clean_page.locator(f"#{name}-panel-close").click()
        clean_page.wait_for_timeout(400)
        self._assert_closed_on_the_dashboard(clean_page, name)

    def test_escape_closes_it_and_stays_on_the_dashboard(self, clean_page, built_dashboard_html):
        self._cold_load(clean_page, built_dashboard_html, "requirements")
        clean_page.keyboard.press("Escape")
        clean_page.wait_for_timeout(400)
        self._assert_closed_on_the_dashboard(clean_page, "requirements")

    def test_a_panel_opened_from_its_button_still_closes_by_stepping_back(self, clean_page,
                                                                          built_dashboard_html):
        """The pushed case is unchanged: Close steps back over the entry
        the app pushed, so Forward reopens it rather than history
        accumulating a 'closed' entry."""
        _goto(clean_page, built_dashboard_html)
        before = clean_page.evaluate("() => history.length")
        clean_page.locator("#requirements-btn").click()
        _await_requirements_plans(clean_page)
        clean_page.locator("#requirements-panel-close").click()
        clean_page.wait_for_function("() => !STATE.panel")
        assert clean_page.evaluate("() => history.length") == before + 1
        clean_page.go_forward()
        clean_page.wait_for_function("() => STATE.panel === 'requirements'")


class TestClosingAPanelReachedByItsUrl:
    """road-testing #8 (Keith, 2026-09-24): closing a check panel landed
    on the AGENCY view. Reproduced 2026-10-12: Close was always
    history.back(), which is right only when the app itself pushed the
    entry underneath. A check reached by its URL - pasted, edited, or a
    link from elsewhere - has the previous page underneath (here the
    agency view), and in a fresh tab nothing at all, so Close left the
    dashboard. Close now steps to the parent view in place there."""

    _CHECK = {**_BDM, "columnName": "registration_number", "checkKey": "not_null_dbt"}

    def _state(self, page):
        return page.evaluate("() => [STATE.tier, STATE.columnName || null, STATE.checkKey || null,"
                             " document.getElementById('check-panel').getAttribute('aria-hidden')]")

    def test_reached_from_the_agency_view_it_closes_to_its_column(self, clean_page,
                                                                  built_dashboard_html):
        _goto(clean_page, built_dashboard_html, {"tier": "agency",
                                                 "agencyId": "registry-services"})
        _goto(clean_page, built_dashboard_html, self._CHECK)
        assert self._state(clean_page)[2] == "not_null_dbt"
        clean_page.locator("#check-panel-close").click()
        clean_page.wait_for_function("() => !STATE.checkKey")
        assert self._state(clean_page) == ["dataset", "registration_number", None, "true"]

    def test_in_a_fresh_tab_it_closes_and_stays_on_the_dashboard(self, clean_page,
                                                                 built_dashboard_html):
        _goto(clean_page, built_dashboard_html, self._CHECK)
        clean_page.locator("#check-panel-close").click()
        clean_page.wait_for_timeout(500)
        assert clean_page.url.startswith("file://") and "qa-reporting-dashboard" in clean_page.url
        assert self._state(clean_page) == ["dataset", "registration_number", None, "true"]

    def test_a_column_drawer_reached_by_its_url_closes_to_its_dataset(self, clean_page,
                                                                    built_dashboard_html):
        _goto(clean_page, built_dashboard_html, {"tier": "agency",
                                                 "agencyId": "registry-services"})
        _goto(clean_page, built_dashboard_html, {**_BDM, "columnName": "registration_number"})
        clean_page.keyboard.press("Escape")
        clean_page.wait_for_function("() => !STATE.columnName")
        assert clean_page.evaluate("() => STATE.tier") == "dataset"

    def test_opened_in_the_app_close_is_still_one_step_back(self, clean_page,
                                                          built_dashboard_html):
        _goto(clean_page, built_dashboard_html, _BDM)
        _open_first_column(clean_page)
        clean_page.locator(".check-card").first.click()
        clean_page.wait_for_function("() => !!STATE.checkKey")
        length = clean_page.evaluate("() => history.length")
        clean_page.locator("#check-panel-close").click()
        clean_page.wait_for_function("() => !STATE.checkKey")
        assert clean_page.evaluate("() => [!!STATE.columnName, history.length]") == [True, length]


def _dataset_raw(page, dataset_id):
    return page.evaluate("(id) => rawRealDatasets().find(d => d.id === id)", dataset_id)


class TestTheQualifierAsAtTheDateOnShow:
    """REQ-DASH-198 criterion 7, on the REAL inheritances cp-case-workers
    carries - dates taken from the embedded change points, never the clock.
    """

    WHERE = {"tier": "dataset", "agencyId": "child-protection-family-support",
              "collectionId": "child-protection", "datasetId": "cp-case-workers"}

    def _standing(self, page, html):
        _goto(page, html, state=self.WHERE)
        raw = _dataset_raw(page, "cp-case-workers")
        opened = [e for e in raw["promotionTimeline"]["standing"] if e["standingIn"]]
        assert opened, "precondition: cp-case-workers carries a real inheritance"
        return opened[-1]

    def test_no_qualifier_on_a_date_in_an_earlier_period(self, clean_page,
                                                          built_dashboard_html):
        entry = self._standing(clean_page, built_dashboard_html)
        earlier = entry["earnedOn"]
        assert earlier and earlier < entry["on"]
        _goto(clean_page, built_dashboard_html, state=self.WHERE, in_place_on=earlier)
        assert clean_page.locator('[data-testid="standing-in"]').count() == 0

    def test_no_qualifier_on_the_builds_own_date_for_an_earlier_period(
            self, clean_page, built_dashboard_html):
        """The road-testing #18 case: 2026-Q2 stood on 2026-Q1, and a
        2026-Q3 view said so."""
        entry = self._standing(clean_page, built_dashboard_html)
        today_period = clean_page.evaluate(
            "() => periodNameFor('cp-case-workers', DEFAULT_IN_PLACE_ON)")
        assert today_period != entry["period"], "precondition: today is a later period"
        _goto(clean_page, built_dashboard_html, state=self.WHERE)
        assert clean_page.locator('[data-testid="standing-in"]').count() == 0

    def test_the_drill_from_a_past_date_and_the_way_back(self, clean_page,
                                                          built_dashboard_html):
        entry = self._standing(clean_page, built_dashboard_html)
        on = entry["on"]
        _goto(clean_page, built_dashboard_html, state=self.WHERE, in_place_on=on)
        marker = clean_page.locator('[data-testid="standing-in"]')
        assert marker.count() >= 1
        assert "On " in (marker.first.get_attribute("title") or "")
        clean_page.locator('[data-testid="standing-in-drill"]').click()
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(clean_page.url).query))
        assert params.get("in-place-on") == entry["earnedOn"]
        assert params.get("from") == entry["period"]
        assert params.get("from-on") == on
        assert params.get("via") == "inheritance"
        notice = clean_page.locator('[data-testid="arrival-notice"]')
        text = " ".join(notice.inner_text().split())
        assert f"You have left {entry['period']}" in text
        assert entry["standingIn"]["standsOn"] in text
        assert "an inherited period" in text
        clean_page.reload()
        clean_page.wait_for_function(
            "() => Number(document.documentElement.dataset.renderCount || 0) > 0")
        assert clean_page.locator('[data-testid="arrival-notice"]').count() == 1
        clean_page.locator('[data-testid="arrival-back"]').click()
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(clean_page.url).query))
        assert params.get("in-place-on") == on
        assert clean_page.locator('[data-testid="arrival-notice"]').count() == 0
        assert clean_page.locator('[data-testid="standing-in"]').count() >= 1

    def test_the_drill_shows_the_banner_and_browser_back_returns(
            self, clean_page, built_dashboard_html):
        """Keith, 2026-10-13 (#166): the drill takes the reader to the banner,
        and the browser's own Back returns to the date left."""
        entry = self._standing(clean_page, built_dashboard_html)
        _goto(clean_page, built_dashboard_html, state=self.WHERE, in_place_on=entry["on"])
        clean_page.locator('[data-testid="standing-in-drill"]').click()
        notice = clean_page.locator('[data-testid="arrival-notice"]')
        assert notice.is_visible()
        box = notice.bounding_box()
        assert box and 0 <= box["y"] < clean_page.viewport_size["height"], \
            "the banner is on screen after the drill"
        clean_page.go_back()
        clean_page.wait_for_function(
            "(on) => new URLSearchParams(location.search).get('in-place-on') === on",
            arg=entry["on"])


@pytest.fixture(scope="class")
def dashboard_html_with_a_later_rejection(built_dashboard_html, supply_dsn,
                                          tmp_path_factory) -> Path:
    """The real built page, with cp-carers' change points replaced by the
    REAL change-point build (pipeline.promotion_timeline) run over a small
    fixture history in this worker's own database - never the deployment's.

    REQ-DASH-197 criterion 16 asks for an arrival awaiting a decision on a
    date and rejected later. The bootstrapped history holds one since
    REQ-GEN-199 (TS-75, TestTheAsAtReadingsOnTheRealHistory); this fixture
    history stays as the path that does not depend on which scenarios the
    history happens to plant. The fixture is
    one promoted supply, a second awaiting until a rejection three weeks
    later, and a third filed after the date the test looks at.
    """
    import uuid
    from datetime import datetime, timezone

    import filing_support
    from pipeline import promotion_timeline, slot_timeline
    from qa_tools.common import assignment, promotion, qa_store, rejection, schedule, supply_db
    from qa_tools.common import decision_log as dl

    ds = f"cp-{uuid.uuid4().hex[:10]}"
    dates = {"2026-Q2": date(2026, 5, 1), "2026-Q3": date(2026, 8, 1)}
    at = lambda m, d, h=1: datetime(2026, m, d, h, tzinfo=timezone.utc)  # noqa: E731
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MOTHMAN_SUPPLY_DSN", supply_dsn)
        mp.setattr(schedule, "date_of", lambda name, _ds: dates.get(name))
        with supply_db.connect(label="e2e-fixture-history") as conn:
            qa_store.ensure_schema(conn)
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')

            def file(n, period, when):
                filing_support.file(assignment.Assignment(
                    dataset_id=ds, supply_id=f"{ds}@{n}", slot=period,
                    branch=assignment.OPEN_UNFILLED, considered=(period,),
                    received_at=when))

            def table(n):
                name = f"carers__e2e{n}{ds[3:]}"
                conn.execute(f'CREATE TABLE IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"."{name}" '
                             "(id integer)")
                return name
            file(1, "2026-Q2", at(5, 2))
            promotion.promote(conn, agency_id="child-protection-family-support",
                              collection_id="child-protection", dataset_id=ds,
                              supply=f"{ds}@1", period="2026-Q2", physical_tables=[table(1)],
                              actor="tester", actor_kind=dl.PERSON,
                              effective_at=at(5, 3).isoformat())
            file(2, "2026-Q3", at(8, 2))
            rejection.reject(conn, agency_id="child-protection-family-support",
                             collection_id="child-protection", dataset_id=ds,
                             supply=f"{ds}@2", physical_tables=[table(2)], actor="Keith",
                             reason="wrong extract", effective_at=at(8, 25).isoformat(),
                             from_slot="2026-Q3")
            file(3, "2026-Q3", at(9, 1))
            points = promotion_timeline.for_dataset(
                ds, slot_timeline.for_dataset(ds, conn=conn), conn=conn)

    tmp_path = tmp_path_factory.mktemp("later_rejection")
    for name in ("fonts", "vendor"):
        (tmp_path / name).symlink_to((built_dashboard_html.parent / name).resolve())
    out = tmp_path / "dashboard_later_rejection.html"
    html = built_dashboard_html.read_text()

    def splice(record):
        for d in record["child-protection"]["datasets"]:
            if d["id"] == "cp-carers":
                d["promotionTimeline"] = points
    data = _collection_data(built_dashboard_html)
    splice(data)
    out.write_text(_with_collection_data_inline(html, data))
    return out


class TestThePanelAsAtTheDateOnShow:
    """REQ-DASH-197 criterion 16, cold-loading a past date's URL."""

    WHERE = {"tier": "dataset", "agencyId": "child-protection-family-support",
              "collectionId": "child-protection", "datasetId": "cp-carers"}
    PAST = "2026-08-10"

    def _panel(self, page):
        panel = page.locator('[data-testid="promotion-split"]')
        assert panel.count() == 1
        return " ".join(panel.inner_text().split())

    def test_a_later_rejection_reads_as_awaiting_in_the_past_tense(
            self, clean_page, dashboard_html_with_a_later_rejection):
        _goto(clean_page, dashboard_html_with_a_later_rejection, state=self.WHERE,
              in_place_on=self.PAST)
        text = self._panel(clean_page)
        assert "nobody had decided" in text
        assert "rejected" not in text.lower()
        day = clean_page.evaluate(f"() => fmtDay('{self.PAST}')")
        assert f"On {day} the warehouse did not hold the latest file" in text

    def test_no_supply_filed_after_the_date_appears(
            self, clean_page, dashboard_html_with_a_later_rejection):
        _goto(clean_page, dashboard_html_with_a_later_rejection, state=self.WHERE,
              in_place_on=self.PAST)
        text = self._panel(clean_page)
        assert "@2" in text and "@3" not in text

    def test_changing_the_date_with_the_page_open_re_renders_it(
            self, clean_page, dashboard_html_with_a_later_rejection):
        _goto(clean_page, dashboard_html_with_a_later_rejection, state=self.WHERE,
              in_place_on=self.PAST)
        clean_page.evaluate("() => applyInPlaceOn('2026-09-05')")
        clean_page.wait_for_timeout(300)
        assert "@3" in self._panel(clean_page)

    def test_on_the_builds_own_date_it_reads_as_it_always_has(
            self, clean_page, dashboard_html_with_a_later_rejection):
        _goto(clean_page, dashboard_html_with_a_later_rejection, state=self.WHERE)
        text = self._panel(clean_page)
        assert "What is in the warehouse is not the latest file" in text
        assert "nobody has decided" in text

    def test_the_verdict_line_and_the_panel_name_the_same_promoted_supply(
            self, clean_page, built_dashboard_html):
        """Criterion 13, on the real build, compared INDEPENDENTLY
        (post-build-review #165 - the first version compared a value with
        itself). On every date the verdict line says a newer supply is
        awaiting, the RENDERED line must name the receipt of the run whose
        arrival key is the panel's promoted supply's - found here by key, not
        through the runId the page used."""
        _goto(clean_page, built_dashboard_html, state=self.WHERE)
        checked = clean_page.evaluate("""() => {
          const d = rawRealDatasets().find(x => x.id === "cp-carers");
          let n = 0, bad = [];
          for (const p of d.promotionTimeline.points) {
            const c = clipDatasetToInPlaceOn(d, p.on);
            if (!c || c.verdictOf.state !== "awaiting" || !p.promoted) continue;
            const key = p.promoted.supply.split("@")[1].split("#")[0];
            const run = d.runs.find(r => r.run_id.includes(key));
            if (!run) continue;
            n += 1;
            const named = run.received_at ? fmtInstant(run.received_at) : fmtDay(run.run_date);
            if (!verdictLine(c).includes(named)) bad.push(p.on);
          }
          return {n, bad};
        }""")
        assert checked["n"], "precondition: a date where the verdict is awaiting"
        assert checked["bad"] == []


@pytest.fixture(scope="class")
def dashboard_html_with_a_settled_pair(built_dashboard_html, supply_dsn, tmp_path_factory):
    """REQ-PIPE-194 criterion 11: the real built page with Birth
    Registrations' blockers replaced by the REAL blocker record of a pair
    settled in this worker's own database - never the deployment's, which
    REQ-GEN-196 supplies pairs to and which depends on this requirement.
    File one is the supply; file two is re-filed to the next day; the
    settlement takes effect three asset days after the receipt."""
    import sys
    from datetime import timedelta

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pair_support import DS, Pair, _at, free_day

    from qa_tools.common import dataset_blockers, people, qa_store, supply_db

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MOTHMAN_SUPPLY_DSN", supply_dsn)
        with supply_db.connect(label="e2e-settled-pair") as conn:
            qa_store.ensure_schema(conn)
            day = free_day(conn, date(2026, 9, 1), span=18)
            nxt = day + timedelta(days=1)
            p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                                  (f"birth_registrations_{nxt}.csv", _at(day, "13:45"))])
            one, two = (n for n, _ in p.files)
            actor = people.person_by_email("fpycnkgvmt@privaterelay.appleid.com")
            p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()),
                     at=_at(day + timedelta(days=3), "10:00"))
            (blocker,) = [b.as_record() for b in dataset_blockers.contests(conn)
                          if b.supply == p.pair]
    tmp = tmp_path_factory.mktemp("settled_pair")
    out = _with_blockers(built_dashboard_html, tmp / "dashboard_settled_pair.html", [blocker])
    return out, day, (one, two), DS


class TestASettledPairOnThePage:
    """REQ-PIPE-194 criteria 10, 11 and 12, in a real browser."""

    def _where(self, ds):
        from qa_tools.common import hierarchy

        e = hierarchy.dataset(ds)
        return {"tier": "dataset", "agencyId": e.agency_id, "collectionId": e.collection_id,
                "datasetId": ds}

    def _blocked(self, page, ds):
        return page.evaluate(f"""() => {{
            for (const ag of DATA.agencies) for (const c of ag.collections)
              for (const d of c.datasets) if (d.id === "{ds}")
                return [(d.blocked || d.waitingBlocker || {{}}).kind || null, d.status];
            return "missing";
        }}""")

    def test_it_reads_contested_until_the_settlement_then_settled(
            self, page, dashboard_html_with_a_settled_pair):
        from datetime import timedelta

        html, day, (one, two), ds = dashboard_html_with_a_settled_pair
        # ON THE RECEIPT'S OWN DAY: a daily dataset's next day is the next
        # period, which has its own supply in the real history.
        _goto(page, html, state=self._where(ds), in_place_on=str(day))
        assert self._blocked(page, ds) == ["contested", "red"]
        row = page.locator("tr[data-blocker=contested]")
        assert row.count() == 1 and row.locator("[data-settled-file]").count() == 0

        _goto(page, html, state=self._where(ds), in_place_on=str(day + timedelta(days=3)))
        assert self._blocked(page, ds)[0] != "contested"
        # THE CONTEST ITSELF, by date - open the day before the settlement,
        # closed from its day (a daily dataset's verdict alone would pass
        # trivially, its period having moved on).
        open_on = lambda on: page.evaluate(  # noqa: E731
            f"() => blockersOpenInPlaceOn('{ds}', '{on}').length")
        assert open_on(day + timedelta(days=2)) == 1
        assert open_on(day + timedelta(days=3)) == 0
        settled = page.locator("tr[data-blocker=contested][data-settled]")
        assert settled.count() == 1
        text = " ".join(settled.inner_text().split())
        assert "Settled" in text and one in text and two in text
        assert "this period's supply (" in text and "re-filed to" in text

    def test_the_refiled_files_link_cold_loads_framed_as_a_refile(
            self, page, dashboard_html_with_a_settled_pair):
        from datetime import timedelta

        html, day, _files, ds = dashboard_html_with_a_settled_pair
        _goto(page, html, state=self._where(ds), in_place_on=str(day + timedelta(days=4)))
        href = page.locator('[data-testid="refiled-file-link"]').get_attribute("href")
        assert "via=refile" in href and f"from-on={day + timedelta(days=4)}" in href
        query, fragment = href.split("?", 1)[1].split("#", 1)
        page.goto(f"file://{html.resolve()}?{query}#{fragment}")
        page.wait_for_selector('[data-testid="arrival-notice"]')
        notice = " ".join(page.locator('[data-testid="arrival-notice"]').inner_text().split())
        assert "re-filed file" in notice and "substitution" not in notice
        assert page.locator('[data-testid="arrival-back"]').count() == 1


class TestThePlantedPairsOnTheBuiltDashboard:
    """REQ-GEN-196 criterion 13, on the real bootstrapped history: each
    planted pair reads 'Two files for one table' on its arrival day - the
    date its scenario link opens on - and no longer contested from the
    settlement's asset day, the next."""

    PAIRS = ("TS-68", "TS-69", "TS-70", "TS-71", "TS-72", "TS-73", "TS-74")

    @pytest.mark.parametrize("sid", PAIRS)
    def test_contested_on_its_arrival_day_and_settled_the_next(self, page, built_dashboard_html,
                                                                sid):
        from datetime import date, timedelta

        from qa_tools.common import scenario_map

        placed = scenario_map.read_placements().get(sid)
        assert placed is not None, f"{sid} is not in the generated history"
        ds, day = placed.dataset, date.fromisoformat(placed.period)
        assert placed.in_place_on == str(day), "its link opens on the arrival day"
        where = TestASettledPairOnThePage()._where(ds)
        open_on = lambda on: page.evaluate(  # noqa: E731
            f"() => blockersOpenInPlaceOn('{ds}', '{on}').filter(b => b.kind === 'contested')"
            ".length")

        _goto(page, built_dashboard_html, state=where, in_place_on=str(day))
        assert TestASettledPairOnThePage()._blocked(page, ds) == ["contested", "red"]
        # EARLIER PAIRS STAY LISTED, SETTLED - only this one is open.
        row = page.locator("tr[data-blocker=contested]:not([data-settled])")
        assert row.count() == 1 and "Two files for one table" in row.inner_text()
        assert open_on(day) == 1
        settled_before = page.locator("tr[data-blocker=contested][data-settled]").count()

        nxt = day + timedelta(days=1)
        _goto(page, built_dashboard_html, state=where, in_place_on=str(nxt))
        assert open_on(nxt) == 0
        assert TestASettledPairOnThePage()._blocked(page, ds)[0] != "contested"
        assert page.locator("tr[data-blocker=contested]:not([data-settled])").count() == 0
        settled = page.locator("tr[data-blocker=contested][data-settled]")
        assert settled.count() == settled_before + 1
        mine = [t for t in (" ".join(settled.nth(i).inner_text().split())
                            for i in range(settled.count()))
                if f"birth_registrations_{day}" in t]
        assert len(mine) == 1 and "Settled" in mine[0], mine

    def _text_on(self, page, html, sid, days_after):
        from datetime import date, timedelta

        from qa_tools.common import scenario_map

        placed = scenario_map.read_placements()[sid]
        on = date.fromisoformat(placed.period) + timedelta(days=days_after)
        _goto(page, html, state=TestASettledPairOnThePage()._where(placed.dataset),
              in_place_on=str(on))
        # THE PAIR'S OWN DAY IS AN OLDER CYCLE by then, behind the toggle.
        toggle = page.locator("#supply-history-toggle")
        if toggle.count():
            toggle.click()
        return " ".join(page.locator("#view").inner_text().split()), date.fromisoformat(placed.period)

    def test_ts70_reads_late_from_the_corrected_files_receipt(self, page, built_dashboard_html):
        """Criterion 14: D's supply is the 16:30 re-export, so D is late."""
        text, _day = self._text_on(page, built_dashboard_html, "TS-70", 1)
        assert "Late 4:30pm" in text, text[:2000]

    def test_ts72_marks_the_refused_file_never_loaded(self, page, built_dashboard_html):
        """Criterion 16 (#172 D2): the settled row says which file never loaded."""
        text, day = self._text_on(page, built_dashboard_html, "TS-72", 1)
        assert f"birth_registrations_{day}-test.csv" in text
        assert "never loaded" in text, text[:2000]

    def test_ts73_says_both_files_were_rejected(self, page, built_dashboard_html):
        """Criterion 17: D is left owed, and the page says two files came and
        were both rejected - not 'a supply'."""
        text, _day = self._text_on(page, built_dashboard_html, "TS-73", 2)
        assert "2 files arrived and were rejected" in text, text[:2000]


#: REQ-GEN-199 criteria 32-34: each chip, the element holding the text its
#: register Expect quotes, and that text - from plans/supply-model.md.
_AS_AT_CHIPS = (
    ("TS-75a", '[data-testid="promotion-split"]',
     "this supply was staged and nobody had decided about it yet"),
    ("TS-75b", '[data-testid="promotion-split"]',
     "a person had rejected this supply, so it was not promoted"),
    ("TS-76", '[data-testid="standing-in"]', "Substituted from 2024-Q4"),
    ("TS-76", '[data-testid="standing-in-since"]', "Since removed, as from"),
    ("TS-77a", '[data-testid="standing-in"]', "Substituted from 2023-Q1"),
    ("TS-77a", '[data-testid="standing-in-since"]', "Since replaced, as from"),
    ("TS-77b", '[data-testid="promotion-split"]', "this one had been superseded"),
    ("TS-77b", '[data-testid="standing-in-detail"]',
     "2023-Q2 holds 2023-Q1's supply; the results below are a newer supply awaiting "
     "a decision."),
    ("TS-78a", '[data-testid="promotion-split"]',
     "the newest file was not the newest promotion"),
    # 'In place' says where (REQ-DASH-277; REQ-GEN-199 criterion 18 as amended):
    # the status clause after it comes with REQ-DASH-272.
    ("TS-78b", ".verdict-of", "The supply in place in the warehouse is the one received "
     "2:00pm Sunday, 30 August 2026."),
    ("TS-79a", '[data-testid="standing-in"]', "Inherited from 2026-Q1"),
    ("TS-79b", '[data-testid="standing-in"]', "Inherited from 2023-Q1"),
)

_VISIBLE_TEXT = """() => {
  const out = [];
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walk.nextNode())) {
    const el = node.parentElement;
    if (!el || el.closest("script, style, [hidden]")) continue;
    if (el.checkVisibility && !el.checkVisibility()) continue;
    const text = node.textContent.replace(/\\s+/g, " ").trim();
    if (text) out.push(text);
  }
  return {nodes: out, whole: document.body.innerText.replace(/\\s+/g, " ")};
}"""

#: 'In place' with nothing after it to say where - the idiom 'in place of' aside.
_IN_PLACE_ALONE = re.compile(r"\bin place\b(?! in the warehouse)(?! of\b)", re.IGNORECASE)


class TestInPlaceInTheWarehouse:
    """REQ-DASH-277 criterion 7: no visible text on a DATASET or COLLECTION
    view says 'in place' without saying where - walked as every visible text
    node, with a past date selected and an awaiting supply on show (TS-78b's
    placement: Birth Registrations, its newest supply awaiting a decision
    beside the one in the warehouse). Release Notes and Plans are left out:
    they render CHANGELOG.yaml and plans/, which say 'in place' as history."""

    def _walk(self, page) -> dict:
        found = page.evaluate(_VISIBLE_TEXT)
        assert found["nodes"], "nothing visible to walk"
        return found

    def _check(self, found: dict, where: str) -> None:
        alone = [t for t in found["nodes"] if _IN_PLACE_ALONE.search(t)]
        assert not alone, f"{where}: says 'in place' without where: {alone[:3]}"
        assert not _IN_PLACE_ALONE.search(found["whole"]), f"{where}: across nodes"

    def test_no_visible_text_says_in_place_alone(self, clean_page, built_dashboard_html):
        from qa_tools.common import scenario_map

        placement = scenario_map.read_placements().get("TS-78b")
        assert placement is not None and placement.in_place_on, "TS-78b is not placed"
        _goto(clean_page, built_dashboard_html)
        clean_page.locator("#scenarios-btn").click()
        clean_page.wait_for_timeout(400)
        index = clean_page.evaluate("SCENARIO_MAP.findIndex(e => e.id === 'TS-78b')")
        clean_page.locator(f'a[data-scenario="{index}"]').click()
        clean_page.wait_for_selector('.verdict-of[data-verdict-of="awaiting"]', timeout=10000)
        assert "in-place-on=" in clean_page.url
        clean_page.locator("#in-place-on-btn").click()
        clean_page.wait_for_selector("#in-place-on-input", state="visible")
        dataset = self._walk(clean_page)
        # IT CANNOT PASS ON AN EMPTY PAGE: the verdict line, the past-date
        # notice and the date panel all say where.
        said = [t for t in dataset["nodes"] if "in place in the warehouse" in t.lower()]
        assert len(said) >= 2, said
        assert any(t.startswith("In the warehouse on") for t in dataset["nodes"])
        self._check(dataset, "the dataset view")

        state = clean_page.evaluate("({...STATE})")
        _goto(clean_page, built_dashboard_html,
              state={"tier": "collection", "agencyId": state["agencyId"],
                     "collectionId": state["collectionId"]},
              in_place_on=placement.in_place_on)
        collection = self._walk(clean_page)
        assert any("in place in the warehouse" in t.lower() for t in collection["nodes"])
        self._check(collection, "the collection view")


class TestTheAsAtScenarioChips:
    """REQ-GEN-199 criteria 32-37 as amended by REQ-DASH-208 (Keith, 2026-10-14):
    each of this requirement's chips opens on a date where the text its
    register Expect quotes is on the page and, once the scenario jump has
    brought it there, inside the 1280x800 viewport - and the jump's own URL,
    cold-reloaded, puts it inside the viewport again. No console error
    (clean_page). Post-build-review #174's below-the-fold findings are fixed
    by the jump, so none is carried as an expected failure any more."""

    @pytest.mark.parametrize("sid,where,text", [
        pytest.param(sid, where, text, id=f"{sid}-{where}") for sid, where, text in _AS_AT_CHIPS])
    def test_the_quoted_text_is_on_screen_and_survives_a_cold_reload(
            self, clean_page, built_dashboard_html, sid, where, text):
        from qa_tools.common import scenario_map

        placement = scenario_map.read_placements().get(sid)
        assert placement is not None and placement.in_place_on, f"{sid} is not placed"
        clean_page.set_viewport_size({"width": 1280, "height": 800})
        _goto(clean_page, built_dashboard_html)
        clean_page.locator("#scenarios-btn").click()
        clean_page.wait_for_timeout(400)
        index = clean_page.evaluate(f"SCENARIO_MAP.findIndex(e => e.id === '{sid}')")
        assert index >= 0, f"{sid} is not in the embedded map"
        clean_page.locator(f'a[data-scenario="{index}"]').click()
        clean_page.wait_for_selector("[data-scenario-label]", timeout=10000)
        assert f"in-place-on={placement.in_place_on}" in clean_page.url
        assert f"scenario={sid.lower()}" in clean_page.url

        def on_screen():
            # After the fonts and two frames, when the page has made its last
            # adjustment (post-build-review #259).
            clean_page.evaluate("() => document.fonts.ready.then(() => new Promise("
                                "r => requestAnimationFrame(() => requestAnimationFrame(r))))")
            found = clean_page.locator(where).filter(has_text=text)
            assert found.count() >= 1, f"{sid}: {text!r} is not in {where}"
            el = found.first
            assert text in " ".join(el.text_content().split())
            box = el.bounding_box()
            span = f"{box and int(box['y'])}-{box and int(box['y'] + box['height'])}px"
            # A WHOLE PIXEL INSIDE THE FOLD (post-build-review #255): an edge
            # within a pixel of it rounds either way with the machine's fonts,
            # and TS-78a's landed 0.28px past it on CI's.
            assert box and box["y"] >= 0 and box["y"] + box["height"] <= 799, (
                f"{sid}: {where} spans {span}, outside the viewport after the jump")

        on_screen()
        clean_page.reload()
        clean_page.wait_for_function(
            "() => Number(document.documentElement.dataset.renderCount || 0) > 0")
        clean_page.wait_for_selector("[data-scenario-label]", timeout=10000)
        on_screen()


def _scenario_chip(page, html, sid):
    """Open the Scenarios tab and follow scenario `sid`'s chip (post-build-review
    #202), waiting until it has landed or said there is nothing to show."""
    page.set_viewport_size({"width": 1280, "height": 800})
    _goto(page, html)
    page.locator("#scenarios-btn").click()
    page.wait_for_timeout(300)
    index = page.evaluate(f"SCENARIO_MAP.findIndex(e => e.id === '{sid}')")
    assert index >= 0, f"{sid} is not in the embedded map"
    page.locator(f'a[data-scenario="{index}"]').click()
    page.wait_for_selector("[data-scenario-label], [data-scenario-not-found]",
                           timeout=10000)


class TestEveryPlacedScenarioChipLandsRuled:
    """post-build-review #202 F1, F5: every placed chip lands on its subject
    with the accent rule. ONE TEST TO A CLASS, with the one below (Keith,
    2026-10-25, morning report #9 (j)): the two walk every placed scenario,
    ~400-500s each, and `--dist loadgroup` keeps a class on one worker, so
    together in TestEveryScenarioJumpLands they were the module's floor
    (REQ-TEST-281 NFR 7)."""

    def test_every_placed_chip_lands_with_the_accent_rule(self, clean_page,
                                                          built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        ids = clean_page.evaluate(
            "SCENARIO_MAP.filter(e => scenarioTarget(e)).map(e => e.id)")
        assert ids, "no placed scenario to follow"
        missed, unruled = [], []
        for sid in ids:
            _scenario_chip(clean_page, built_dashboard_html, sid)
            if clean_page.locator("[data-scenario-not-found]").count():
                missed.append(sid)
                continue
            width = clean_page.evaluate(
                "getComputedStyle(document.querySelector('#view .scenario-subject:not(tr)')"
                " || document.querySelector('#view tr.scenario-subject > td')).borderLeftWidth")
            if width != "3px":
                unruled.append((sid, width))
        assert not missed, f"chips that said 'nothing to show': {missed}"
        assert not unruled, f"subjects without the 3px accent rule: {unruled}"


class TestEveryScenarioSubjectLandsCentred:
    """post-build-review #202 F7, alone in its class for the reason given
    on the class above."""

    def test_every_subject_lands_centred(self, clean_page, built_dashboard_html):
        """#202 F7 (Keith, 2026-10-15): the subject lands centred rather than
        flush on the bottom edge - unless the page cannot scroll that far
        (near its top or its end), or the subject is taller than the window,
        when its top is at the window's top; or the page head is brought back
        above it (Keith, 2026-10-15, REQ-DASH-208), when the subject is whole
        and either the head's top is in view or the subject sits on the
        window's bottom edge."""
        _goto(clean_page, built_dashboard_html)
        ids = clean_page.evaluate(
            "SCENARIO_MAP.filter(e => scenarioTarget(e)).map(e => e.id)")
        assert ids, "no placed scenario to follow"
        off = []
        for sid in ids:
            _scenario_chip(clean_page, built_dashboard_html, sid)
            if clean_page.locator("[data-scenario-not-found]").count():
                continue
            got = clean_page.evaluate("""() => {
                const el = document.querySelector('#view .scenario-subject');
                const r = el.getBoundingClientRect();
                const max = document.documentElement.scrollHeight - innerHeight;
                const head = document.querySelector('#view .view-head');
                return {top: r.top, mid: r.top + r.height / 2, h: r.height, bottom: r.bottom,
                        headTop: head ? head.getBoundingClientRect().top : null,
                        y: scrollY, atEnd: scrollY >= max - 1, vh: innerHeight};
            }""")
            if got["h"] > got["vh"]:
                ok = abs(got["top"]) <= 2
            else:
                centred = abs(got["mid"] - got["vh"] / 2) <= 2
                whole = got["top"] >= 0 and got["bottom"] <= got["vh"] + 1
                head_back = whole and got["headTop"] is not None and (
                    0 <= got["headTop"] <= got["top"] or abs(got["bottom"] - got["vh"]) <= 2)
                ok = (centred or head_back or (got["y"] == 0 and got["mid"] < got["vh"] / 2)
                      or (got["atEnd"] and got["mid"] > got["vh"] / 2))
            if not ok:
                off.append((sid, got))
        assert not off, f"subjects not centred: {off}"


class TestEveryScenarioJumpLands:
    """post-build-review #202 - the REQ-DASH-208 critic's findings, on the
    real built history (every placed chip and every centred subject are the
    two classes above, split out for REQ-TEST-281's module target): Back
    after a date change still restores the date (F2); a reload under an open panel leaves focus to the panel (F3); the
    browser's own scroll restoration comes back after a reloaded jump (F8);
    and a mixed-case parameter is rewritten lowercase (F9)."""

    def test_the_page_head_stays_in_view_when_it_fits_beside_the_subject(
            self, clean_page, built_dashboard_html):
        """REQ-DASH-208 decision (Keith, 2026-10-15): the jump centres its subject,
        but where the view head and the subject fit in the window together the
        head is never left above it - TS-76's quoted pill is in the head. A block
        between them is sized so the pill and the subject span 700px of the
        800px window, so the test does not depend on how long the queue above
        happens to be."""
        _scenario_chip(clean_page, built_dashboard_html, "TS-76")
        got = clean_page.evaluate("""() => {
            const head = document.querySelector('#view .view-head');
            const span = document.querySelector('#view .scenario-subject').getBoundingClientRect().bottom
                - document.querySelector('[data-testid="standing-in"]').getBoundingClientRect().top;
            const spacer = document.createElement('div');
            spacer.style.height = Math.max(0, 700 - span) + 'px';
            head.after(spacer);
            const entry = SCENARIO_MAP.find(e => e.id === 'TS-76');
            landOnScenarioSubject(entry, scenarioTarget(entry).inPlaceOn);
            const sub = document.querySelector('#view .scenario-subject').getBoundingClientRect();
            const pill = document.querySelector('[data-testid="standing-in"]').getBoundingClientRect();
            return {pill: pill.top, subBottom: sub.bottom, vh: innerHeight};
        }""")
        assert 0 <= got["pill"] and got["subBottom"] <= got["vh"], got

    def test_back_after_a_date_change_restores_the_date(self, clean_page,
                                                        built_dashboard_html):
        _scenario_chip(clean_page, built_dashboard_html, "TS-75a")
        clean_page.evaluate("applyInPlaceOn('2024-03-01')")
        clean_page.go_back()
        clean_page.wait_for_timeout(400)
        shown, url_date = clean_page.evaluate(
            "[CURRENT_IN_PLACE_ON, inPlaceOnFromUrl() || DEFAULT_IN_PLACE_ON]")
        assert shown == url_date, f"showing {shown} while the address says {url_date}"

    def test_a_reload_under_an_open_panel_leaves_focus_to_it(self, clean_page,
                                                             built_dashboard_html):
        _scenario_chip(clean_page, built_dashboard_html, "TS-75a")
        clean_page.evaluate("openPanel('activity')")
        clean_page.reload()
        clean_page.wait_for_function(
            "() => Number(document.documentElement.dataset.renderCount || 0) > 0")
        clean_page.wait_for_timeout(400)
        assert not clean_page.evaluate(
            "document.activeElement && document.activeElement.classList.contains('scenario-subject')")

    def test_scroll_restoration_comes_back_after_a_reloaded_jump(self, clean_page,
                                                                 built_dashboard_html):
        _scenario_chip(clean_page, built_dashboard_html, "TS-75a")
        clean_page.reload()
        clean_page.wait_for_selector("[data-scenario-label]", timeout=10000)
        clean_page.wait_for_timeout(500)
        assert clean_page.evaluate("history.scrollRestoration") == "auto"

    def test_a_mixed_case_parameter_is_rewritten_lowercase(self, clean_page,
                                                          built_dashboard_html):
        _scenario_chip(clean_page, built_dashboard_html, "TS-75a")
        url = clean_page.url.replace("scenario=ts-75a", "SCENARIO=Ts-75A")
        clean_page.goto(url)
        clean_page.wait_for_selector("[data-scenario-label]", timeout=10000)
        assert "scenario=ts-75a" in clean_page.url and "SCENARIO" not in clean_page.url


class TestThePeriodComposition:
    """REQ-DASH-209 on the real bootstrapped build: the view's rows agree with
    the period's own _manifest at the build's date, both ways (criterion 10),
    an earlier date agrees with the decision log's as-at reader, the view is
    reached from a dataset's supply history and lands with focus on its h2,
    and an unknown period is the not-found page."""

    AGENCY, COLLECTION = "child-protection-family-support", "child-protection"

    def _open(self, page, html, period, on=None):
        _goto(page, html, state={"tier": "period", "agencyId": self.AGENCY,
                                 "collectionId": self.COLLECTION, "period": period},
              in_place_on=on)

    @staticmethod
    def _rows(page):
        return {r["dataset"]: r for r in page.evaluate(
            """() => [...document.querySelectorAll(
                 '#view [data-testid="period-composition"] tbody tr')].map(tr => (
                 {dataset: tr.dataset.dataset, kind: tr.dataset.kind, text: tr.innerText}))""")}

    def test_today_agrees_with_the_periods_manifest_both_ways(
            self, clean_page, built_dashboard_html, deployment_history):
        from qa_tools.common import period_schema, supply_db

        from qa_tools.common import slots

        found = None
        periods = [s.name for s in slots.slots_for_dataset("cp-clients")]
        with supply_db.connect(read_only=True, label="test-composition") as conn:
            present = {r[0] for r in conn.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname LIKE ?",
                [period_schema.PERIOD_SCHEMA_PREFIX + "%"]).fetchall()}
            for period in reversed(periods):
                schema = period_schema.period_schema(period)
                if schema not in present:
                    continue
                rows = conn.execute(
                    f'SELECT dataset_id, kind, decided_by FROM "{schema}"._manifest '
                    "WHERE dataset_id LIKE 'cp-%'").fetchall()
                if rows and (found is None or any(k == "inherited" for _d, k, _b in rows)):
                    found = (period, rows)
                    if any(k == "inherited" for _d, k, _b in rows):
                        break
        assert found, "no Child Protection period has a _manifest to compare with"
        period, manifest = found
        self._open(clean_page, built_dashboard_html, period)
        page = self._rows(clean_page)
        held = {d: (k, b) for d, k, b in manifest}
        for dataset, (kind, by) in held.items():
            assert page[dataset]["kind"] == kind, (period, dataset, page[dataset], kind)
            said = "Decided by" if by == "person" else "Applied automatically by the schedule"
            assert said in page[dataset]["text"], (period, dataset, page[dataset]["text"])
        for dataset, row in page.items():
            if row["kind"] not in ("notsupplied", "notowed"):
                assert dataset in held, (period, dataset, row)

    def test_an_earlier_date_agrees_with_the_decision_log_then(
            self, clean_page, built_dashboard_html, deployment_history):
        from qa_tools.common import asset_time, qa_store, scenario_map, supply_db

        placement = scenario_map.read_placements().get("TS-76")
        assert placement is not None and placement.in_place_on
        on, period = placement.in_place_on, placement.period
        self._open(clean_page, built_dashboard_html, period, on=on)
        page = self._rows(clean_page)
        assert page["cp-placements"]["kind"] == "substituted", page["cp-placements"]
        end = asset_time.end_of_day(date.fromisoformat(on))
        with supply_db.connect(read_only=True, label="test-composition") as conn:
            for dataset, row in page.items():
                got = conn.execute(
                    f'SELECT held_as FROM "{qa_store.SCHEMA}".slot_holds(?, ?) WHERE slot = ?',
                    [dataset, end, period]).fetchall()
                held_as = got[0][0] if got else None
                if held_as:
                    assert row["kind"] == held_as, (dataset, row, held_as)
                else:
                    assert row["kind"] in ("notsupplied", "notowed"), (dataset, row)

    def test_reached_from_a_supply_history_with_focus_on_its_heading(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, state={
            "tier": "dataset", "agencyId": self.AGENCY, "collectionId": self.COLLECTION,
            "datasetId": "cp-clients"})
        link = clean_page.locator("#view .supply-history a[data-period-link]").first
        assert link.count() == 1
        link.click()
        clean_page.wait_for_selector('#view [data-testid="period-composition"]')
        assert "/period/" in clean_page.url
        assert clean_page.evaluate("document.activeElement && document.activeElement.tagName") == "H2"

    def test_an_unknown_period_is_the_not_found_page(self, clean_page, built_dashboard_html):
        self._open(clean_page, built_dashboard_html, "1999-Q9")
        assert "Period not found" in clean_page.locator("#view h2").inner_text()
        assert clean_page.locator('#view [data-testid="period-composition"]').count() == 0


class TestTheAsAtReadingsOnTheRealHistory:
    """REQ-GEN-199 criteria 30 and 31: REQ-DASH-197 criterion 16's
    awaiting-then-rejected reading and REQ-DASH-198 criterion 7's removed and
    replaced substitutions, on dates taken from the built data - beside the
    fixture-history tests above, which stay for a run with no deployment."""

    CLIENTS = {"tier": "dataset", "agencyId": "child-protection-family-support",
               "collectionId": "child-protection", "datasetId": "cp-clients"}
    PLACEMENTS = {**CLIENTS, "datasetId": "cp-placements"}

    @staticmethod
    def _on(sid):
        from qa_tools.common import scenario_map

        placement = scenario_map.read_placements().get(sid)
        assert placement is not None, f"{sid} is not placed in this history"
        return placement.in_place_on

    def _panel(self, page):
        panel = page.locator('[data-testid="promotion-split"]')
        assert panel.count() == 1
        return " ".join(panel.inner_text().split())

    def test_awaiting_on_the_day_it_waited(self, clean_page, built_dashboard_html):
        on = self._on("TS-75a")
        _goto(clean_page, built_dashboard_html, state=self.CLIENTS, in_place_on=on)
        text = self._panel(clean_page)
        day = clean_page.evaluate(f"() => fmtDay('{on}')")
        assert f"On {day} the warehouse did not hold the latest file" in text
        assert "nobody had decided" in text and "rejected" not in text.lower()

    def test_rejected_after_the_rejection(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html, state=self.CLIENTS,
              in_place_on=self._on("TS-75b"))
        assert "a person had rejected this supply" in self._panel(clean_page)

    def test_a_removed_substitution_says_since_removed(self, clean_page,
                                                       built_dashboard_html):
        _goto(clean_page, built_dashboard_html, state=self.PLACEMENTS,
              in_place_on=self._on("TS-76"))
        since = clean_page.locator('[data-testid="standing-in-since"]')
        assert since.count() == 1 and "Since removed" in since.inner_text()

    def test_a_replaced_substitution_says_since_replaced(self, clean_page,
                                                         built_dashboard_html):
        _goto(clean_page, built_dashboard_html, state=self.PLACEMENTS,
              in_place_on=self._on("TS-77a"))
        since = clean_page.locator('[data-testid="standing-in-since"]')
        assert since.count() == 1 and "Since replaced" in since.inner_text()


class TestTheGitHubLinks:
    """REQ-DASH-244 criteria 12, 13 and 15, in a real browser: a dataset's
    'View on GitHub' opens its collection's ODCS contract at that dataset's
    own entry, an agency's opens its contract/<agency-id>/ folder, and each
    one's tooltip names the target - for every registered collection."""

    def test_every_dataset_opens_its_contract_at_its_entry(self, clean_page, built_dashboard_html):
        from qa_tools import collections

        every = collections.all_collections()
        assert every, "the registry must hold collections for this test to mean anything"
        for coll in every:
            contract = coll.check_file("contract")
            lines = (Path(__file__).resolve().parent.parent / contract).read_text().splitlines()
            for d in coll.datasets:
                _goto(clean_page, built_dashboard_html,
                      state={"tier": "dataset", "agencyId": coll.agency_id,
                             "collectionId": coll.id, "datasetId": d.dataset_id})
                link = clean_page.locator(".view-head a", has_text="View on GitHub").first
                href, title = link.get_attribute("href"), link.get_attribute("title")
                assert "/blob/" in href and f"/{contract}#L" in href, (d.dataset_id, href)
                assert lines[int(href.rsplit("#L", 1)[1]) - 1].strip() == f"- name: {d.table}"
                assert contract in title, (d.dataset_id, title)

    def test_every_agency_opens_its_folder(self, clean_page, built_dashboard_html):
        from qa_tools import collections

        for agency_id in dict.fromkeys(c.agency_id for c in collections.all_collections()):
            _goto(clean_page, built_dashboard_html, state={"tier": "agency", "agencyId": agency_id})
            link = clean_page.locator("a", has_text="View on GitHub").first
            href, title = link.get_attribute("href"), link.get_attribute("title")
            assert href.endswith(f"/contract/{agency_id}"), (agency_id, href)
            assert f"contract/{agency_id}/" in title, (agency_id, title)


class TestAPendingCorrectionIsANeedsActionItem:
    """REQ-DASH-263 criterion 5, on the bootstrapped history: Birth
    Registrations' page lists REQ-GEN-205-WINDOW among the things waiting for
    a person from the correction's own date, and not before it."""

    DS = {"tier": "dataset", "agencyId": "registry-services",
          "collectionId": "civil-registration", "datasetId": "birth-registrations"}
    REF = "REQ-GEN-205-WINDOW"

    def _items(self, page, html, on):
        _goto(page, html, state=self.DS, in_place_on=on)
        return [t for t in page.locator(".notice-queue .queue-item").all_inner_texts()
                if self.REF in t]

    def test_listed_from_its_date(self, clean_page, built_dashboard_html):
        [item] = self._items(clean_page, built_dashboard_html, "2026-09-25")
        assert "Calendar correction to confirm" in item
        assert f"mothman supply corrections --reference {self.REF}" in item

    def test_not_listed_before_it(self, clean_page, built_dashboard_html):
        assert self._items(clean_page, built_dashboard_html, "2026-09-23") == []


class TestACrossTableCheckOnTS80:
    """REQ-DASH-264 criterion 6, on the bootstrapped history (post-build-review
    #253, Keith 2026-10-19). TS-80: two Client Registers on 1 November 2020,
    settled at 11:00 on 2 November, the settlement's re-check re-running the
    readers' Client reference under the Client Register's own run."""

    AG, COL = "child-protection-family-support", "child-protection"

    def _rows(self, page, html, dataset_id, on):
        _goto(page, html, in_place_on=on, state={
            "tier": "dataset", "agencyId": self.AG, "collectionId": self.COL,
            "datasetId": dataset_id})
        section = page.locator('.scope-section[data-scope="cross-table"]')
        return [" ".join(t.split()) for t in section.locator(".scope-check").all_inner_texts()]

    def _labels(self, page) -> list[str]:
        return page.locator('.scope-section[data-scope="cross-table"] .scope-check').evaluate_all(
            "els => els.map(e => e.getAttribute('aria-label') || '')")

    def test_the_readers_client_reference_is_green_after_the_settlement(
            self, clean_page, built_dashboard_html):
        rows = [r for r in self._rows(clean_page, built_dashboard_html, "cp-notifications",
                                      "2020-11-03")
                if r.startswith("Client reference")]
        # ONE ROW FOR THE CHECK, its three tools as marks (REQ-DASH-272
        # criterion 6, amending REQ-DASH-264 criterion 2).
        assert len(rows) == 1, rows
        assert "Notifications → Client Register" in rows[0] and "Green" in rows[0], rows
        # Criterion 7 as amended by REQ-DASH-272: where the result came from is
        # said in the row's accessible name (and the panel), every time.
        labels = [x for x in self._labels(clean_page) if x.startswith("Client reference")]
        assert len(labels) == 1 and ("Re-checked 11:00am Monday, 2 November 2020, when the "
                                     "Client Register was re-checked") in labels[0], labels

    def test_the_panel_says_latest_result_and_where_it_came_from(self, clean_page, built_dashboard_html):
        """Criterion 8."""
        self._rows(clean_page, built_dashboard_html, "cp-notifications", "2020-11-03")
        clean_page.locator('.scope-section[data-scope="cross-table"] .scope-check',
                           has_text="Client reference").first.click()
        clean_page.wait_for_selector("[data-recheck-note]")
        panel = " ".join(clean_page.locator("[data-recheck-note]")
                         .locator("xpath=ancestor::aside[1]").inner_text().split())
        # The labels are upper-cased by CSS, and inner_text keeps that.
        assert "latest result" in panel.lower() and "current run" not in panel.lower(), panel[:400]
        # Criterion 9: the chart's last date is when the result was recorded.
        assert panel.rstrip().endswith("Monday, 2 November 2020 View as table"), panel[-200:]
        assert ("Re-checked 11:00am Monday, 2 November 2020, when the Client Register was "
                "re-checked.") in panel

    def test_both_sides_of_the_comparison_stay_inside_the_panel(self, clean_page, built_dashboard_html):
        """post-build-review #261: a long compared-run label ("... · from the
        Client Register's run (previous)") widened the "Compared run" column
        until the "Latest result" box sat outside the panel, so the card showed
        one side of a comparison with no hint of the other."""
        self._rows(clean_page, built_dashboard_html, "cp-notifications", "2020-11-03")
        clean_page.locator('.scope-section[data-scope="cross-table"] .scope-check',
                           has_text="Client reference").first.click()
        clean_page.wait_for_selector(".check-panel .compare-col")
        boxes = clean_page.evaluate("""() => {
          const panel = document.querySelector('.check-panel').getBoundingClientRect();
          return {panel: [panel.left, panel.right],
                  cols: [...document.querySelectorAll('.check-panel .compare-col')].map(c => {
                    const r = c.getBoundingClientRect();
                    return [c.querySelector('.k').textContent.trim(), r.left, r.right]; })};
        }""")
        assert len(boxes["cols"]) == 2, boxes
        left, right = boxes["panel"]
        for name, l, r in boxes["cols"]:
            assert left <= l and r <= right, (name, l, r, boxes["panel"])

    def test_the_held_register_shows_its_cross_table_rows_red_and_its_own_checks_not_run(
            self, clean_page, built_dashboard_html):
        rows = self._rows(clean_page, built_dashboard_html, "cp-clients", "2020-11-01")
        client_refs = [r for r in rows if r.startswith("Client reference")]
        assert len(client_refs) == 3, rows
        assert any("Red" in r for r in client_refs), client_refs
        labels = clean_page.locator('.scope-section[data-scope="cross-table"] .scope-check .bt')
        assert {t for t in labels.all_inner_texts() if t.startswith(("Notif", "Invest", "Place"))} == {
            "Notifications → Client Register", "Investigations → Client Register",
            "Placements → Client Register"}
        own = clean_page.evaluate("""() => {
            const ds = DATA.agencies.flatMap(a => a.collections).flatMap(c => c.datasets)
                           .find(d => d.id === "cp-clients");
            return [...new Set(ds.columns.filter(c => c.scope !== "cross-table")
                                .flatMap(c => c.checks).map(checkStatus))];
        }""")
        assert own == ["nodata"], own
        text = " ".join(clean_page.locator("#view").inner_text().split())
        # On 1 November the readers' results are "could not run" - two files
        # claimed the Client Register. The rows say so and when, and the banner
        # says they could not run either (post-build-review #258 Q1, Keith
        # 2026-10-20, option a). Never "did run" or "Checked".
        assert "The cross-table checks did run" not in text
        assert ("The cross-table checks could not run either: the tables that read this one "
                "need its supply first.") in text
        # The row also says why (Keith 2026-10-24, on provisional #21): the
        # reason follows a colon where the sentence used to end.
        labels = " ".join(self._labels(clean_page))
        assert ("Could not be checked 8:20am Sunday, 1 November 2020, when the Notifications "
                "supply arrived: two Client Register files (cp_clients.csv, cp_clients_TEST.csv) "
                "are waiting to be settled") in labels
        assert "Checked 8:20am" not in labels
        # Criterion 5: the section's own pill follows its rows.
        head = clean_page.locator('.scope-section[data-scope="cross-table"] .head .pill')
        assert "Red" in head.inner_text(), head.inner_text()

    def test_a_row_that_could_not_be_checked_names_both_of_the_pairs_files(
            self, clean_page, built_dashboard_html):
        """Keith, 2026-10-24: the row says why, not only the banner."""
        self._rows(clean_page, built_dashboard_html, "cp-clients", "2020-11-01")
        labels = self._labels(clean_page)
        assert any("when the Notifications supply arrived: two Client Register files "
                   "(cp_clients.csv, cp_clients_TEST.csv) are waiting to be settled" in r
                   for r in labels), labels


class TestASupersededRunOnTheDatesItWasCurrent:
    """post-build-review #266, Keith 2026-10-24 (answer A), on the bootstrapped
    history. Child Protection's 12 October 2023 delivery was re-checked in full
    on 21 October. A page listed each supply by its current run only, so as at
    15 October the Client Register had no result at all - its own checks and
    its cross-table rows alike - while the gate counted the arrival's. The page
    now keeps a superseded run's results for the dates they were current."""

    AG, COL = "child-protection-family-support", "child-protection"
    WHERE = {"tier": "dataset", "agencyId": AG, "collectionId": COL, "datasetId": "cp-clients"}
    #: The Client Register received 10:00am 12 October 2023, re-checked in full
    #: on 21 October with the rest of its delivery (the seeded history).
    SUPPLY = "cp-clients@202310121000000800"

    def _shown(self, page, html, on):
        _goto(page, html, state=self.WHERE, in_place_on=on)
        return page.evaluate("""() => {
            const ds = DATA.agencies.flatMap(a => a.collections).flatMap(c => c.datasets)
                           .find(d => d.id === "cp-clients");
            // A section with no rule has a synthesized card, dated by nothing.
            const of = c => c.checks.filter(ck => ck.key !== "no_rule_defined").map(ck => {
              const last = (ck.history || []).at(-1) || {};
              return {name: ck.name, status: checkStatus(ck),
                      runs: (ck.history || []).map(h => h.run_id),
                      supply: last.supply_id || null, recorded: last.recorded_at || null};
            });
            return {own: ds.columns.filter(c => c.scope !== "cross-table").flatMap(of),
                    cross: ds.columns.filter(c => c.scope === "cross-table").flatMap(of)};
        }""")

    def test_between_the_arrival_and_the_recheck_the_arrivals_results_are_shown(
            self, clean_page, built_dashboard_html):
        """Before the fix the own checks showed the PREVIOUS supply's results
        as the newest, and every Client reference row read No data."""
        shown = self._shown(clean_page, built_dashboard_html, "2023-10-15")
        assert shown["own"], shown
        assert {c["supply"] for c in shown["own"]} == {self.SUPPLY}, shown["own"][:3]
        refs = [c for c in shown["cross"] if c["name"] == "Client reference"]
        assert refs, shown["cross"]
        assert {c["supply"] for c in refs} == {self.SUPPLY}, refs
        assert all(c["recorded"][:10] <= "2023-10-15" for c in refs), refs
        assert "nodata" not in {c["status"] for c in refs}, refs

    def test_after_the_recheck_only_its_results_are_shown(self, clean_page, built_dashboard_html):
        before = self._shown(clean_page, built_dashboard_html, "2023-10-15")
        after = self._shown(clean_page, built_dashboard_html, "2023-10-22")
        assert {c["supply"] for c in after["own"]} == {self.SUPPLY}, after["own"][:3]
        earlier = {r for c in before["own"] for r in c["runs"]}
        later = {r for c in after["own"] for r in c["runs"]}
        # The arrival is shown only before its re-check, the re-check only after.
        assert earlier - later and later - earlier, (earlier ^ later)


# --- REQ-DASH-291: the built page's data files, from file:// -------------

def _copy_of_the_built_page(built: Path, dest: Path) -> Path:
    """The built page and its data files copied somewhere a test may break
    them, with fonts/ and vendor/ beside it as on the real site."""
    import shutil

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(built, dest / built.name)
    shutil.copytree(built.parent / "data", dest / "data")
    for name in ("fonts", "vendor"):
        (dest / name).symlink_to((built.parent / name).resolve())
    return dest / built.name


def _data_file(page_path: Path, kind: str) -> dict:
    from dashboard import data_files

    entries = data_files.page_manifest(page_path.read_text())["files"]
    return next(e for e in entries if e["kind"] == kind)


def _wait_rendered(page):
    page.wait_for_function("() => Number(document.documentElement.dataset.renderCount || 0) > 0")


class TestTheDataFilesLoadFromDisk:
    """REQ-DASH-291 criteria 6 to 9, 15 and 18, in a real browser over
    file:// - the supported local path, and the one fetch() could not use."""

    def test_every_collection_renders_from_its_own_file(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        assert clean_page.url.startswith("file://")
        got = clean_page.evaluate("""() => ({
            collections: Object.keys(COLLECTION_DATA),
            datasets: Object.values(COLLECTION_DATA).map(e => e.datasets.length),
            scripts: [...document.querySelectorAll('script[src][data-mothman-file]')]
                .map(s => [s.getAttribute('src'), s.async, s.defer, s.type]),
        })""")
        assert got["collections"] == [c.id for c in _registry.all_collections()]
        assert all(n > 0 for n in got["datasets"]), got["datasets"]
        assert got["scripts"] and all(src.startswith("data/") and not a and not d and t == ""
                                      for src, a, d, t in got["scripts"]), got["scripts"]
        assert clean_page.locator('[data-testid="data-file-error"]').count() == 0
        for agency in clean_page.evaluate("() => HIERARCHY.agencies.map(a => a.name)"):
            assert agency in clean_page.locator("#view").inner_text()

    def test_a_deleted_collection_file_is_named_and_the_rest_is_shown(
            self, page, built_dashboard_html, tmp_path):
        """Criterion 8 as amended (Keith, 2026-10-25, post-build-review #268
        (g)): one broken collection no longer blocks the page. The others
        render, one notice names the broken one, its own pages show its
        error, and Plans needs no collection data at all."""
        copy = _copy_of_the_built_page(built_dashboard_html, tmp_path / "site")
        gone = _data_file(copy, "collection")
        (copy.parent / "data" / gone["name"]).unlink()
        page.goto(f"file://{copy}")
        _wait_rendered(page)
        error = page.locator('[data-testid="data-file-error"]')
        assert error.count() == 1
        text = error.inner_text()
        assert gone["name"] in text and "missing" in text
        assert text.index("Reload the page") < text.index("mothman dashboard embed")
        assert "tell the data team" in text and "publish is incomplete" not in text
        assert error.get_attribute("data-broken-collections") == gone["collection"]
        healthy = [c.id for c in _registry.all_collections() if c.id != gone["collection"]]
        assert page.evaluate("() => Object.keys(COLLECTION_DATA)") == healthy
        agencies = page.evaluate("() => HIERARCHY.agencies.map(a => a.name)")
        assert all(name in page.locator("#view").inner_text() for name in agencies)
        page.locator("#plans-btn").click()
        page.wait_for_selector("#plans-list .plans-entry")
        assert page.locator('[data-testid="data-file-error"]').count() == 0

    def test_a_file_from_another_build_is_named(self, page, built_dashboard_html, tmp_path):
        from dashboard import data_files

        copy = _copy_of_the_built_page(built_dashboard_html, tmp_path / "site")
        entry = _data_file(copy, "collection")
        [other] = data_files.encode(entry["key"], {"datasets": []}, kind="collection",
                                    collection=entry["collection"])
        assert other.entry["build"] != entry["build"]
        (copy.parent / "data" / entry["name"]).write_bytes(other.content)
        page.goto(f"file://{copy}")
        _wait_rendered(page)
        text = page.locator('[data-testid="data-file-error"]').inner_text()
        assert entry["name"] in text and "another build" in text

    def test_the_plans_tab_loads_its_file_on_demand(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        selector = 'script[src*="requirements-plans"]'
        assert clean_page.locator(selector).count() == 0, "loaded before anyone asked"
        clean_page.locator("#plans-btn").click()
        clean_page.wait_for_selector("#plans-list .plans-entry")
        assert clean_page.locator(selector).count() == 1
        count = clean_page.locator("#plans-count").inner_text()
        assert re.search(r"of [1-9][\d,]* entries", count), count

    def test_a_cold_loaded_requirements_link_loads_on_demand(self, clean_page, built_dashboard_html):
        clean_page.goto(f"file://{built_dashboard_html.resolve()}?panel=requirements&req=REQ-DASH-291")
        clean_page.wait_for_selector('#requirements-panel-body .req-linked[data-req-id="REQ-DASH-291"]')
        assert "req=REQ-DASH-291" in clean_page.url

    def test_a_missing_requirements_and_plans_file_is_named_in_the_plans_tab(
            self, page, built_dashboard_html, tmp_path):
        copy = _copy_of_the_built_page(built_dashboard_html, tmp_path / "site")
        entry = _data_file(copy, "requirements-plans")
        (copy.parent / "data" / entry["name"]).unlink()
        page.goto(f"file://{copy}#/plans")
        _wait_rendered(page)
        error = page.wait_for_selector('#view [data-testid="data-file-error"]')
        assert entry["name"] in error.inner_text()
        assert page.locator("#plans-list").count() == 0

    def test_a_missing_requirements_and_plans_file_is_named_in_the_requirements_panel(
            self, page, built_dashboard_html, tmp_path):
        """post-build-review #268 T4: the script element's onerror path, which
        only a real browser takes - jsdom loads no <script src> at all."""
        copy = _copy_of_the_built_page(built_dashboard_html, tmp_path / "site")
        entry = _data_file(copy, "requirements-plans")
        (copy.parent / "data" / entry["name"]).unlink()
        page.goto(f"file://{copy}?panel=requirements")
        _wait_rendered(page)
        error = page.wait_for_selector('#requirements-panel-body [data-testid="data-file-error"]')
        text = error.inner_text()
        assert entry["name"] in text and "missing" in text, text
        assert "No requirements yet" not in page.locator("#requirements-panel-body").inner_text()

    def test_the_plans_heading_keeps_focus_once_its_file_has_loaded(self, clean_page, built_dashboard_html):
        """post-build-review #268: navigating to Plans focuses its heading, and
        the render that follows the on-demand load replaced that heading and
        dropped focus to the body, so the next Tab started from the top."""
        _goto(clean_page, built_dashboard_html)
        clean_page.locator("#plans-btn").click()
        clean_page.wait_for_selector("#plans-list .plans-entry")
        focused = clean_page.evaluate(
            "() => [document.activeElement.tagName, document.activeElement.textContent.trim()]")
        assert focused == ["H2", "Plans"], focused

    def test_the_agencies_tier_renders_within_its_budget_of_the_data_being_assembled(
            self, clean_page, built_dashboard_html):
        """REQ-DASH-226 criterion 13's 400ms, measured from the moment the
        data is assembled to the end of the first render, three loads; the
        time from navigation to assembled data is printed beside it."""
        timings = []
        for _ in range(3):
            clean_page.goto("about:blank")
            _goto(clean_page, built_dashboard_html)
            timings.append(clean_page.evaluate("""() => {
                const at = n => performance.getEntriesByName(n)[0].startTime;
                return {assembled: at('mothman:data-assembled'),
                        rendered: at('mothman:first-render') - at('mothman:data-assembled')};
            }"""))
        print(f"\nREQ-DASH-291 criterion 18: {timings}")
        assert all(t["rendered"] < 400 for t in timings), timings

    def test_the_first_view_answers_within_its_budget_of_navigation(
            self, clean_page, built_dashboard_html):
        """From NAVIGATION to the agencies tier on screen and the page
        answering, three loads, under 3 seconds; and the agency trends drawn
        under 6 (post-build-review #268 L1).

        The budget above ends at the first render and could not see the 8 to
        10 seconds that followed it. The trends were filled by a task queued
        straight after that render, which could run before the browser painted
        - so the reader saw nothing until every trend was drawn - and every
        trend re-read every check's `recorded_at` on the asset clock for every
        week back to 2023. The view's time is read BY THE PAGE, polled, so a
        main thread still busy cannot answer early. Generous on purpose: a
        fixed page answers in about half a second here and draws its trends in
        about three, and a guard that flakes is one somebody deletes."""
        url = f"file://{built_dashboard_html.resolve()}"
        timings = []
        for _ in range(3):
            clean_page.goto("about:blank")
            clean_page.goto(url, wait_until="commit")
            view = clean_page.wait_for_function(
                "() => document.querySelector('#agency-grid .card') && performance.now()",
                polling=50, timeout=60000).json_value()
            clean_page.wait_for_selector("#agency-grid[data-trends-drawn]", state="attached",
                                         timeout=60000)
            trends = clean_page.evaluate("() => performance.now()")
            timings.append({"view": round(view), "trends": round(trends)})
        print(f"\npost-build-review #268 L1, ms from navigation: {timings}")
        assert all(t["view"] < 3000 for t in timings), timings
        assert all(t["trends"] < 6000 for t in timings), timings


# --- REQ-DASH-293: a payload past the budget, in parts -------------------

@pytest.fixture(scope="class")
def a_page_built_in_parts(built_dashboard_html, tmp_path_factory):
    """The real build again, with the budget lowered so the real collections
    go past it - the same embed(), only the one constant changed."""
    from dashboard import data_files

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(data_files, "BUDGET_BYTES", 2 * data_files.MIB)
        return _embed_variant(built_dashboard_html, tmp_path_factory.mktemp("parts"))


class TestAPayloadPastTheBudgetIsWrittenInParts:
    """REQ-DASH-293 criteria 2, 3, 5 and 6, in a real browser over file://."""

    def test_the_page_reassembles_the_unsplit_payload(self, clean_page, a_page_built_in_parts,
                                                      built_dashboard_html):
        from dashboard import data_files
        from dashboard import embed_dashboard_data as edd

        files = data_files.page_manifest(a_page_built_in_parts.read_text())["files"]
        parted = {e["collection"] for e in files if e["kind"] == "collection" and e["parts"] > 1}
        assert parted, "no collection is past a 2 MiB budget - this test proves nothing"
        assert all((a_page_built_in_parts.parent / "data" / e["name"]).stat().st_size
                   <= 2 * data_files.MIB for e in files)
        clean_page.goto(f"file://{a_page_built_in_parts}")
        _wait_rendered(clean_page)
        from qa_tools.common import build_output

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv(build_output.OUT_DIR_ENV, str(built_dashboard_html.parent))
            unsplit = edd.collection_data()
        for collection in sorted(parted):
            got = clean_page.evaluate("(c) => COLLECTION_DATA[c]", collection)
            assert got == unsplit[collection], collection
        assert clean_page.locator('[data-testid="data-file-error"]').count() == 0

    def test_deleting_one_part_is_named_on_the_page(self, page, a_page_built_in_parts, tmp_path):
        from dashboard import data_files

        copy = _copy_of_the_built_page(a_page_built_in_parts, tmp_path / "site")
        files = data_files.page_manifest(copy.read_text())["files"]
        part = next(e for e in files if e["kind"] == "collection" and e["parts"] > 1 and e["part"] == 2)
        (copy.parent / "data" / part["name"]).unlink()
        page.goto(f"file://{copy}")
        _wait_rendered(page)
        text = page.locator('[data-testid="data-file-error"]').inner_text()
        assert part["name"] in text and "missing" in text
        others = [e["name"] for e in files if e["name"] != part["name"]]
        assert not any(name in text for name in others)


# --- REQ-DASH-292: a snapshot alone, and the split form the site serves ----

@pytest.fixture(scope="class")
def a_snapshot_of_the_built_page(built_dashboard_html, tmp_path_factory):
    """A real snapshot of the real built page, archived into a scratch
    snapshots directory, and the site prepare_deploy_site() makes of it."""
    import shutil

    from dashboard import snapshot_dashboard

    work = tmp_path_factory.mktemp("snapshot")
    copy = _copy_of_the_built_page(built_dashboard_html, work / "dashboard")
    archived = snapshot_dashboard.take_snapshot(html_path=copy, snapshots_dir=work / "snapshots")
    alone = work / "alone"
    alone.mkdir()
    import gzip

    with gzip.open(archived, "rb") as f:
        (alone / "snapshot.html").write_bytes(f.read())
    site = work / "_site"
    snapshot_dashboard.prepare_deploy_site(site, html_path=copy, snapshots_dir=work / "snapshots",
                                           fonts_dir=built_dashboard_html.parent / "fonts",
                                           vendor_dir=built_dashboard_html.parent / "vendor")
    split = site / "snapshots" / archived.with_suffix("").name
    yield {"alone": alone / "snapshot.html", "split": split, "site": site}
    shutil.rmtree(work, ignore_errors=True)


def _agencies_and_plans(page, url) -> dict:
    """What a reader sees of a snapshot: the agencies tier, the collections
    it holds and the Plans tab - and every file it asked for, and every
    console error, with any resource that failed named by its address."""
    requests, errors = [], []
    on_request = lambda r: requests.append(r.url)  # noqa: E731

    def on_console(msg):
        if msg.type == "error":
            errors.append((msg.text, (msg.location or {}).get("url", "")))

    page.on("request", on_request)
    page.on("console", on_console)
    page.on("pageerror", lambda exc: errors.append((str(exc), "")))
    try:
        page.goto("about:blank")
        page.goto(url)
        _wait_rendered(page)
        agencies = page.locator("#view").inner_text()
        collections = page.evaluate("() => Object.keys(COLLECTION_DATA)")
        page.locator("#plans-btn").click()
        page.wait_for_selector("#plans-list .plans-entry")
        plans = page.locator("#plans-count").inner_text()
    finally:
        page.remove_listener("request", on_request)
        page.remove_listener("console", on_console)
    return {"agencies": agencies, "collections": collections, "plans": plans,
            "data_requests": [u for u in requests if u.endswith(".js") and "/vendor/" not in u],
            "errors": errors, "requests": requests}


def _not_fonts_or_vendor(errors: list) -> list:
    """A snapshot carries its DATA, never fonts/ or vendor/ (Keith, 2026-10-25,
    post-build-review #268 E2: not inlined). On the site they now sit beside
    the snapshots (#268 (c)), so the split form is held to no console error at
    all. ALONE IN AN EMPTY DIRECTORY they cannot be there, the browser logs
    each as a failed resource, and the page falls back to a system font - so
    REQ-DASH-292 criterion 9's 'no console error' cannot hold for that case
    without inlining them, which Keith declined; that is back with him
    (#268). Until then this filter applies to the alone case only, told apart
    by the address that failed; every other console error still fails it."""
    return [(text, url) for text, url in errors
            if not (text.startswith("Failed to load resource")
                    and re.search(r"/(fonts|vendor)/[^/]+$", url))]


class TestASnapshotOpensAloneAndPublishesSplit:
    """REQ-DASH-292 criteria 2, 9 and 10, in a real browser."""

    def test_a_snapshot_alone_in_an_empty_directory_renders_everything(
            self, page, a_snapshot_of_the_built_page):
        alone = a_snapshot_of_the_built_page["alone"]
        assert [p.name for p in alone.parent.iterdir()] == ["snapshot.html"]
        got = _agencies_and_plans(page, f"file://{alone}")
        assert got["collections"] == [c.id for c in _registry.all_collections()]
        assert page.locator('[data-testid="data-file-error"]').count() == 0
        assert re.search(r"of [1-9][\d,]* entries", got["plans"]), got["plans"]
        assert got["data_requests"] == [], "a snapshot asked for a sibling data file"
        assert any(u.startswith("file://") for u in got["requests"]), "requests were not seen at all"
        assert _not_fonts_or_vendor(got["errors"]) == []

    def test_the_split_form_renders_identically_within_the_budget(
            self, page, a_snapshot_of_the_built_page):
        from dashboard import data_files

        split = a_snapshot_of_the_built_page["split"]
        files = data_files.page_manifest(split.read_text())["files"]
        folder = split.parent / (split.name[: -len(".html")] + ".data")
        sizes = [(folder / e["name"]).stat().st_size for e in files]
        assert sizes and all(s <= data_files.BUDGET_BYTES for s in sizes), sizes
        alone = _agencies_and_plans(page, f"file://{a_snapshot_of_the_built_page['alone']}")
        served = _agencies_and_plans(page, f"file://{split}")
        assert sorted(u.rsplit("/", 1)[1] for u in served["data_requests"]) == \
            sorted(e["name"] for e in files), "the split form loads each of its files"
        keys = ("agencies", "collections", "plans")
        assert {k: served[k] for k in keys} == {k: alone[k] for k in keys}
        # FONTS AND THE PLAYER ARE BESIDE THE SNAPSHOTS ON THE SITE (Keith,
        # 2026-10-25, #268 (c)), so nothing is filtered here: no console
        # error at all, and the fonts were actually asked for and found.
        assert served["errors"] == []
        assert any("/snapshots/fonts/" in u for u in served["requests"]), served["requests"]


class TestNotInTheAgreementOnThePage:
    """REQ-PIPE-270 criterion 9, the page half: a dataset page says why a
    cross-table check left out of the run on show - because a table it reads
    is not part of the agreement for the run's period - did not run.

    Against the real built page: the corpus's own early Child Protection
    supplies, whose Assigned worker references read a Case Workers that joins
    the agreement later, carry it. Found from the build's notInAgreement list
    rather than named, so the test follows the corpus."""

    CP_AGENCY = "child-protection-family-support"

    def _left_out(self, page) -> list[dict]:
        return page.evaluate("""() => {
            const cp = COLLECTION_DATA["child-protection"];
            return (cp.datasets || []).flatMap(d=> (d.notInAgreement || []).map(e=> {
                const runs = d.runs || [];
                const i = runs.findIndex(r=> r.run_id === e.runId);
                return {...e, datasetId: d.id, runDate: i >= 0 ? runs[i].run_date : null,
                        nextRunDate: i >= 0 && i + 1 < runs.length ? runs[i + 1].run_date : null};
            }));
        }""")

    def _section(self, page, built, dataset_id, on):
        _goto(page, built, state={"tier": "dataset", "agencyId": self.CP_AGENCY,
                                  "collectionId": "child-protection", "datasetId": dataset_id},
              in_place_on=on)
        return page.locator('.scope-section[data-scope="cross-table"] .not-in-agreement')

    def test_the_run_on_show_says_which_checks_it_left_out_and_why(
            self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        left = self._left_out(clean_page)
        assert left, "the corpus has no check left out for the agreement - nothing to show"
        first = left[0]
        assert first["runDate"], first
        mine = [e for e in left if e["runId"] == first["runId"]]
        block = self._section(clean_page, built_dashboard_html, first["datasetId"],
                              first["runDate"])
        assert block.count() == 1, "the cross-table section says nothing about the left-out checks"
        rows = block.locator(".nia-row")
        assert rows.count() == len(mine)
        assert sorted(rows.evaluate_all("els => els.map(e => e.dataset.checkId)")) == \
            sorted(e["checkId"] for e in mine)
        whys = rows.locator(".why").all_inner_texts()
        reason = mine[0]["reason"]
        assert whys == [reason[0].upper() + reason[1:] + "."] * len(mine), whys
        # NEITHER RED NOR A RESULT: no status pill on a left-out row, and the
        # check is not among the section's result rows.
        assert block.locator(".pill").count() == 0
        listed = clean_page.locator('.scope-section[data-scope="cross-table"] button.scope-check')
        keys = listed.evaluate_all("els => els.map(e => e.dataset.check)")
        assert not ({e["checkId"].rsplit(".", 2)[-2] + "." + e["checkId"].rsplit(".", 1)[-1]
                     for e in mine} & set(keys)), keys
        assert "neither red nor a result" in block.inner_text()

    def test_a_later_run_that_ran_them_says_nothing(self, clean_page, built_dashboard_html):
        _goto(clean_page, built_dashboard_html)
        left = self._left_out(clean_page)
        assert left, "the corpus has no check left out for the agreement - nothing to show"
        later = [e for e in left if e["nextRunDate"]
                 and not any(o["runDate"] == e["nextRunDate"] and o["datasetId"] == e["datasetId"]
                             for o in left)]
        assert later, left
        e = later[0]
        assert self._section(clean_page, built_dashboard_html, e["datasetId"],
                             e["nextRunDate"]).count() == 0


class TestAnUnsettledApplicationNeverReachesThePage:
    """REQ-PIPE-267 criterion 12, the page half: the results a gate
    application's re-evaluations record reach the dataset page only once the
    application SETTLES, and an ABANDONED application's never.

    Through the real chain: a Child Protection history driven through the
    real lifecycle (tests/gate_support.py - the four tools' evaluation stood
    in for, everything else real) in a database of this test's own, so a
    package gate re-evaluates Notifications' Client reference for Clients v2
    against Notifications v1 in a readers-only run; that run's application is
    then left unsettled or abandoned, the results file and dashboard data are
    built from the database by the real builders, and the page is embedded
    and opened in a real browser. The settled case is the control, so the
    test can fail."""

    CLIENTS = {"tier": "dataset", "agencyId": "child-protection-family-support",
               "collectionId": "child-protection", "datasetId": "cp-clients"}
    V1 = {"cp_clients": "C1", "cp_notifications": "N1", "cp_investigations": "I1",
          "cp_placements": "P1", "cp_carers": "K1", "cp_case_workers": "W1"}

    def _page_for(self, how, *, private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch,
                  built_dashboard_html):
        from gate_support import CP, Scenario, install_fake_tools, own_red, pin_replacement_setting

        from pipeline import build_dashboard_data as bdd
        from qa_tools.common import gate, qa_store, supply_db
        from qa_tools.tools import results_history

        # THIS TEST'S OWN DATABASE IS THE `test` ENVIRONMENT'S, where this
        # module's autouse fixture says the deployment's; _embed_variant
        # reads the deployment again for what reports/ does not carry.
        from qa_tools.common import environments
        monkeypatch.setenv(environments.ENVIRONMENT_ENV, "test")
        sc = Scenario(root=tmp_path / "scenario", raw_dir=Path(cp_raw_dir))
        install_fake_tools(monkeypatch, sc)
        pin_replacement_setting(monkeypatch)
        sc.deliver("2024-07-25T10:00:00+08:00", self.V1)
        sc.process()
        sc.rules.append(own_red("N2"))
        v2 = sc.deliver("2024-08-05T10:00:00+08:00",
                        {"cp_clients": "C2", "cp_notifications": "N2"})
        sc.process()
        (rerun,) = [r for r in sc.runs(v2["C2"]) if r["scope"] == "readers"]
        key = rerun["run_key"]
        if how != gate.SETTLED:
            with supply_db.connect(label="pytest") as conn:
                app = gate.start(conn, collection_id=CP, period="2024-Q3", entry=gate.RECHECK)
                if how == gate.ABANDONED:
                    gate.abandon(conn, app)
                conn.execute(f'UPDATE "{qa_store.SCHEMA}".run SET gate_application = ? '
                             "WHERE run_key = ?", [app, key])

        results = tmp_path / "results.json"
        monkeypatch.setattr(results_history, "results_path", lambda _cid: str(results))
        monkeypatch.setattr(bdd, "results_path", lambda _cid: str(results))
        results_history.build_results_from_history(CP)
        coll = _registry.by_id(CP)
        reports = {coll.dashboard_file: bdd.build(CP),
                   coll.results_file: json.loads(results.read_text())}
        page = _embed_variant(built_dashboard_html, tmp_path / "site", reports=reports)
        return page, key

    def _seen(self, page, key) -> dict:
        return page.evaluate("""(key) => {
            const raw = rawRealDatasetById("cp-clients");
            const cp = DATA.agencies.flatMap(a=>a.collections).find(c=>c.id==="child-protection");
            const ds = cp.datasets.find(d=>d.id==="cp-clients");
            const inHistory = cols => cols.flatMap(c=>(c.checks||[]).flatMap(ck=>
                [...(ck.history||[]), ...(ck.superseded||[])]
                    .filter(h=> h.run_id === key)
                    .map(h=> `${ck.key} @ ${h.recorded_at || h.run_date}`)));
            const everywhere = Object.values(COLLECTION_DATA).flatMap(e=> e.datasets || [])
                .flatMap(d=> inHistory(d.columns || []));
            return {raw: inHistory(raw.columns || []), shown: inHistory(ds.columns || []),
                    everywhere};
        }""", key)

    @pytest.mark.parametrize("how", ["settled", "unsettled", "abandoned"])
    def test_only_a_settled_application_reaches_the_dataset_page(
            self, how, clean_page, built_dashboard_html, private_supply_dsn, cp_raw_dir,
            tmp_path, monkeypatch):
        from qa_tools.common import gate

        state = {"settled": gate.SETTLED, "unsettled": None, "abandoned": gate.ABANDONED}[how]
        page, key = self._page_for(state, private_supply_dsn=private_supply_dsn,
                                   cp_raw_dir=cp_raw_dir, tmp_path=tmp_path,
                                   monkeypatch=monkeypatch,
                                   built_dashboard_html=built_dashboard_html)
        # TODAY, THE PAGE'S DEFAULT: the re-evaluation is recorded when it ran,
        # on the real clock, whatever the scenario's receipt instants say.
        _goto(clean_page, page, state=self.CLIENTS)
        seen = self._seen(clean_page, key)
        if how == "settled":
            assert seen["raw"] and seen["shown"], (
                "the control: a settled application's re-evaluation is on the page", seen)
        else:
            assert seen["everywhere"] == [], (
                f"an {how} application's re-evaluation reached the page", seen["everywhere"])
            assert seen["shown"] == []


# ---- A Child Protection scenario's page, as at each of its dates --------------

CP_AGENCY = "child-protection-family-support"


def _cp_state(dataset_id: str) -> dict:
    return {"tier": "dataset", "agencyId": CP_AGENCY, "collectionId": "child-protection",
            "datasetId": dataset_id}


class _CpPages:
    """A Child Protection history driven through the REAL per-arrival lifecycle
    (tests/gate_support.py - each tool's evaluation stood in for, everything
    else real) in this test's own database, ON A PINNED CLOCK so every gate
    decision and re-check is stamped at the scenario's own instants and the
    page can be read as at each of them; then built by the real builders and
    embedded as a variant of this worker's page. `page()` may be called after
    each step: each call is its own build."""

    def __init__(self, *, tmp_path, monkeypatch, cp_raw_dir, built):
        from gate_support import Scenario, install_fake_tools, pin_replacement_setting

        from qa_tools.common import environments

        monkeypatch.setenv(environments.ENVIRONMENT_ENV, "test")
        self.tmp_path, self.monkeypatch, self.built = tmp_path, monkeypatch, built
        self.sc = Scenario(root=tmp_path / "scenario", raw_dir=Path(cp_raw_dir))
        install_fake_tools(monkeypatch, self.sc)
        pin_replacement_setting(monkeypatch)
        self.builds = 0

    def at(self, instant: str) -> None:
        """Now is `instant` - as replay_clock's simulated clock would make it."""
        from qa_tools.common import asset_time

        self.monkeypatch.setenv(asset_time.PINNED_NOW_VARIABLE, instant)

    def reject(self, supply: str, period: str, at: str) -> None:
        from qa_tools.common import hierarchy, rejection, supply_db, supply_files

        self.at(at)
        dataset_id = supply.split("@", 1)[0]
        ds = hierarchy.dataset(dataset_id)
        with supply_db.connect(label="pytest-reject") as conn:
            rejection.reject(conn, agency_id=ds.agency_id, collection_id=ds.collection_id,
                             dataset_id=dataset_id, supply=supply,
                             physical_tables=supply_files.tables_in(
                                 conn, dataset_id, supply, supply_db.STAGING_SCHEMA),
                             actor="fixture@example.org", reason="test: turned down",
                             effective_at=at, from_slot=period)

    def page(self) -> Path:
        from pipeline import build_dashboard_data as bdd
        from qa_tools.tools import results_history

        self.builds += 1
        out = self.tmp_path / f"build-{self.builds}"
        out.mkdir()
        results = out / "results.json"
        self.monkeypatch.setattr(results_history, "results_path", lambda _cid: str(results))
        self.monkeypatch.setattr(bdd, "results_path", lambda _cid: str(results))
        results_history.build_results_from_history("child-protection")
        coll = _registry.by_id("child-protection")
        reports = {coll.dashboard_file: bdd.build("child-protection"),
                   coll.results_file: json.loads(results.read_text())}
        return _embed_variant(self.built, out / "site", reports=reports)


@pytest.fixture
def cp_pages(private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch, built_dashboard_html):
    return _CpPages(tmp_path=tmp_path, monkeypatch=monkeypatch, cp_raw_dir=cp_raw_dir,
                    built=built_dashboard_html)


def _first_time_q4(pages: _CpPages) -> None:
    """2024-Q4 holding Case Workers, Carers, Investigations and Placements in
    the warehouse, no Clients or Notifications ever supplied (tests/
    test_package_gate.py's first_time, on the pinned clock)."""
    from test_package_gate import first_time

    pages.at("2024-10-25T10:30:00+08:00")
    first_time(pages.sc)


def _s2_strict(pages: _CpPages) -> dict:
    """S2 strict as re-cast (REQ-PIPE-267, V4-Q1 = A): Clients v2 red on its own
    data is held back, so Notifications v2's Client reference cannot run and
    Notifications v2 is held back with it."""
    from gate_support import own_red

    _first_time_q4(pages)
    pages.sc.rules.append(own_red("C2"))
    pages.at("2024-11-03T10:30:00+08:00")
    got = pages.sc.deliver("2024-11-03T10:00:00+08:00",
                           {"cp_clients": "C2", "cp_notifications": "N2"})
    pages.sc.process()
    return got


def _shown(page, selector: str) -> list[dict]:
    return page.evaluate("""(sel) => [...document.querySelectorAll(sel)].map(e => ({
        text: e.textContent.replace(/\\s+/g, " ").trim(),
        attrs: Object.fromEntries([...e.attributes].map(a => [a.name, a.value])),
        links: [...e.querySelectorAll("a")].map(a => ({text: a.textContent, href: a.href})),
        top: e.getBoundingClientRect().top}))""", selector)


class TestAnotherTableCouldNotBeRead:
    """REQ-DASH-204 criterion 12: a dataset turned red because another table it
    reads could not be read says so at the top of its page, naming that table
    and what clears it - against the deployment's TS-80 and fixture histories
    driven through the real lifecycle."""

    READERS = ("cp-notifications", "cp-investigations", "cp-placements")

    #: (arrival day, period, the day after it was re-evaluated) for TS-42 and
    #: TS-80, and how many of each reader's checks read the Client Register.
    PAIRS = (("2019-11-01", "2019-Q4", "2019-11-29"), ("2020-11-01", "2020-Q4", "2020-11-02"))
    NEED = {"cp-notifications": 3, "cp-investigations": 6, "cp-placements": 3}

    def test_a_reader_shows_one_line_while_the_pair_is_open_and_none_after(
            self, clean_page, built_dashboard_html):
        """TS-42 and TS-80 (criteria 12 and 13): on the pair's arrival day
        each of the contested Client Register's three readers shows ONE line
        naming it - though three or six of its checks read it - worded as the
        register entries quote it, with links that keep the date on show; the
        Client Register's own notice ends 'Affects' naming the three; and once
        the readers are re-evaluated, no line at all."""
        for day, period, after in self.PAIRS:
            for reader, n in self.NEED.items():
                _goto(clean_page, built_dashboard_html, state=_cp_state(reader), in_place_on=day)
                (notice,) = _shown(clean_page, "[data-no-promoted]")
                lines = _shown(clean_page, "[data-no-promoted] .np-line")
                assert len(lines) == 1, (reader, lines)
                assert lines[0]["attrs"]["data-np-dataset"] == "cp-clients"
                assert lines[0]["text"] == (
                    f"No promoted Client Register for {period}. {n} of this supply's checks need "
                    f"it, so they could not run. That is not a fault in this supply's own data. "
                    f"They run again by themselves once a {period} Client Register supply is "
                    f"promoted."), (reader, lines)
                assert notice["attrs"].get("role") == "status"
                assert lines[0]["links"] and all(
                    f"in-place-on={day}" in a["href"] and "/dataset/cp-clients" in a["href"]
                    for a in lines[0]["links"]), lines[0]["links"]
                _goto(clean_page, built_dashboard_html, state=_cp_state(reader), in_place_on=after)
                assert _shown(clean_page, "[data-no-promoted]") == [], (reader, after)
            _goto(clean_page, built_dashboard_html, state=_cp_state("cp-clients"), in_place_on=day)
            (affects,) = _shown(clean_page, "[data-blocked] [data-affects-readers]")
            assert affects["text"].startswith("Affects ")
            assert {a["text"] for a in affects["links"]} == {"Notifications", "Investigations",
                                                             "Placements"}
            assert _shown(clean_page, "[data-no-promoted]") == [], "never on the causing page"

    def test_the_package_form_turned_down_on_notifications_page(self, clean_page, cp_pages):
        """S2 strict as re-cast: Notifications' page shows the package form
        naming the held-back Client Register, carrying data-no-promoted, and
        says nothing needs deciding on it; after Clients v2 is rejected it reads
        'was turned down' and a person is needed - judged as at the date on
        show, so the day before the rejection still reads 'was held back'."""
        got = _s2_strict(cp_pages)
        cp_pages.reject(got["C2"], "2024-Q4", "2024-11-05T10:00:00+08:00")
        page = cp_pages.page()
        n = _cp_state("cp-notifications")

        _goto(clean_page, page, state=n, in_place_on="2024-11-04")
        (line,) = _shown(clean_page, "[data-no-promoted] .np-line")
        assert line["text"] == (
            "No promoted Client Register for 2024-Q4. The Client Register received with this "
            "supply (10:00am Sunday, 3 November 2024) was held back, so 3 of this supply's checks "
            "could not run. That is not a fault in this supply's own data. They run again by "
            "themselves once a 2024-Q4 Client Register supply is promoted."), line
        (verdict,) = _shown(clean_page, ".verdict-of")
        assert verdict["text"].startswith("Nothing needs deciding on this supply"), verdict
        assert "Awaiting a decision" not in verdict["text"]
        held = _shown(clean_page, "[data-held-back]")
        if held:
            assert held[0]["top"] < line["top"], "after any REQ-DASH-275 notice"
        assert clean_page.locator(".view-head .pill.red").count() >= 1, "the red stays"

        _goto(clean_page, page, state=n, in_place_on="2024-11-05")
        (line,) = _shown(clean_page, "[data-no-promoted] .np-line")
        assert ("The Client Register received with this supply (10:00am Sunday, 3 November "
                "2024) was turned down, so 3 of this supply's checks could not run.") in line["text"]
        assert "held back" not in line["text"]
        (verdict,) = _shown(clean_page, ".verdict-of")
        assert verdict["text"].startswith("Awaiting a decision"), verdict
        assert verdict["text"].endswith(
            "The Client Register file received with it was turned down; this supply now needs "
            "its own decision."), verdict

    def test_a_replaced_partner_reads_has_been_replaced(self, clean_page, cp_pages):
        """S2 strict as re-cast, then a Clients v3 that supersedes Clients v2 and
        whose own run stops before it can re-check Notifications v2: the line
        reads 'has been replaced by the one received <instant>'."""
        got = _s2_strict(cp_pages)
        cp_pages.sc.crash.add(("soda", "cp_clients__20241107"))
        cp_pages.at("2024-11-07T10:30:00+08:00")
        cp_pages.sc.deliver("2024-11-07T10:00:00+08:00", {"cp_clients": "C3"})
        cp_pages.sc.process()
        assert cp_pages.sc.failures, "precondition: Clients v3's run stopped"
        assert "supersede" in cp_pages.sc.actions(got["C2"]), "precondition: v2 superseded"
        page = cp_pages.page()
        _goto(clean_page, page, state=_cp_state("cp-notifications"), in_place_on="2024-11-07")
        (line,) = _shown(clean_page, "[data-no-promoted] .np-line")
        assert ("The Client Register received with this supply (10:00am Sunday, 3 November "
                "2024) has been replaced by the one received 10:00am Thursday, 7 November 2024, "
                "so 3 of this supply's checks could not run.") in line["text"], line
        assert "was held back" not in line["text"]

    def test_a_partner_not_due_yet_and_then_overdue(self, clean_page, cp_pages):
        """Notifications v2 alone on 30 October, Clients due 9:00am 1 November:
        Notifications' page shows the line, its red unchanged, and the Client
        Register's page the muted 'Not due until' line naming its readers; the
        collection shows the quiet row note and ONE card line for the Client
        Register. On 2 November Clients is overdue, which has no item of its own
        in the terminal's queue: the verdict line says a person can decide."""
        _first_time_q4(cp_pages)
        cp_pages.at("2024-10-30T10:30:00+08:00")
        cp_pages.sc.deliver("2024-10-30T10:00:00+08:00", {"cp_notifications": "N2"})
        cp_pages.sc.process()
        page = cp_pages.page()

        _goto(clean_page, page, state=_cp_state("cp-notifications"), in_place_on="2024-10-30")
        lines = _shown(clean_page, "[data-no-promoted] .np-line")
        assert [ln["attrs"]["data-np-dataset"] for ln in lines] == ["cp-clients"], lines
        assert lines[0]["text"].startswith("No promoted Client Register for 2024-Q4. 3 of this "
                                           "supply's checks need it")
        assert clean_page.locator(".view-head .pill.red").count() >= 1

        _goto(clean_page, page, state=_cp_state("cp-clients"), in_place_on="2024-10-30")
        (muted,) = _shown(clean_page, "[data-not-due-yet]")
        assert muted["text"].startswith("Not due until 9:00am Friday, 1 November 2024 — the "), muted
        assert muted["text"].endswith("are waiting on it"), muted
        assert "Notifications" in {a["text"] for a in muted["links"]}
        assert "late-open-note" in muted["attrs"]["class"]
        assert all("in-place-on=2024-10-30" in a["href"] for a in muted["links"])

        _goto(clean_page, page, state={"tier": "agency", "agencyId": CP_AGENCY},
              in_place_on="2024-10-30")
        notes = _shown(clean_page, ".no-promoted-note")
        assert any(n["text"] == "No promoted Client Register for 2024-Q4" for n in notes), notes
        # ONE LINE PER CAUSING TABLE: the Client Register, which its three
        # readers wait on (Investigations also waits on Notifications, whose v2
        # is not in the warehouse - a second cause, a second line).
        markers = {m["attrs"]["data-no-promoted-marker"]: m["text"]
                   for m in _shown(clean_page, "[data-no-promoted-marker]")}
        assert markers["cp-clients"].endswith("No promoted Client Register: holds 3 datasets red"), \
            markers
        assert "Placements" not in markers["cp-clients"], "never each reader on the card"
        assert len(_shown(clean_page, '[data-no-promoted-marker="cp-clients"]')) == 1

        _goto(clean_page, page, state=_cp_state("cp-notifications"), in_place_on="2024-11-02")
        (verdict,) = _shown(clean_page, ".verdict-of")
        assert "could not run because Client Register for 2024-Q4 is overdue" in verdict["text"], \
            verdict
        assert "A person can decide on this supply, or wait for that supply to be promoted." \
            in verdict["text"]
        assert "Nothing needs deciding" not in verdict["text"]
        _goto(clean_page, page, state=_cp_state("cp-clients"), in_place_on="2024-11-02")
        assert _shown(clean_page, "[data-not-due-yet]") == []

    def test_the_owed_re_check_has_its_own_wording(self, clean_page, cp_pages):
        """2024-Q3 holding v1 of every table; a Clients v2 whose run stops
        before it checks anything is promoted by a person, so the Notifications
        in the warehouse owes a re-check against it that has not run: its line
        says so (criterion 7) - never 'No promoted'."""
        from test_package_gate import established

        cp_pages.at("2024-07-25T10:30:00+08:00")
        established(cp_pages.sc)
        cp_pages.sc.crash.add(("dbt", "cp_clients__20240805"))
        cp_pages.at("2024-08-05T10:30:00+08:00")
        c2 = cp_pages.sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2"})["C2"]
        cp_pages.sc.process()
        assert cp_pages.sc.failures, "precondition: Clients v2's run stopped"
        cp_pages.at("2024-08-06T10:30:00+08:00")
        cp_pages.sc.promote_by_hand(c2, "2024-Q3", at="2024-08-06T10:00:00+08:00")
        assert cp_pages.sc.owed("reevaluate"), "precondition: the knock-on is owed, not run"
        page = cp_pages.page()
        _goto(clean_page, page, state=_cp_state("cp-notifications"), in_place_on="2024-08-06")
        (line,) = _shown(clean_page, "[data-no-promoted] .np-line")
        assert line["text"] == (
            "Not yet re-checked against the Client Register promoted 10:00am Tuesday, 6 August "
            "2024. 3 of this supply's checks read it; the re-check runs on the next processing "
            "pass."), line
        assert "No promoted" not in line["text"]
        _goto(clean_page, page, state=_cp_state("cp-notifications"), in_place_on="2024-08-05")
        assert _shown(clean_page, "[data-no-promoted]") == [], "nothing owed the day before"


def _s1(pages: _CpPages, *, red: bool = False) -> dict:
    """S1 (REQ-PIPE-267): 2024-Q3 holding v1 of every table, then a zip of
    Clients v2 and a Notifications v2 red on its own data. Green: Clients v2 is
    re-checked against Notifications v1 and promoted. Red: that re-check fails
    and Clients v2 is held back too."""
    from gate_support import cross_red, own_red
    from test_package_gate import established

    pages.at("2024-07-25T10:30:00+08:00")
    v1 = established(pages.sc)
    pages.sc.rules.append(own_red("N2"))
    if red:
        pages.sc.rules.append(cross_red("cp-notifications", "cp_clients",
                                        when={"cp_clients": "C2", "cp_notifications": "N1"}))
    pages.at("2024-08-05T10:30:00+08:00")
    v2 = pages.sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2", "cp_notifications": "N2"})
    pages.sc.process()
    return {**v1, **v2}


def _grid(page) -> dict:
    """The cross-table grid as a reader sees it: its column headings and, per
    row, its name, tables, each cell's text and its pill."""
    return page.evaluate("""() => {
        const g = document.querySelector('.scope-section[data-scope="cross-table"] .xt-grid');
        if(!g) return null;
        const t = e => e ? e.textContent.replace(/\\s+/g, " ").trim() : null;
        return {
          heads: [...g.querySelectorAll('.xt-head span')].map(t).filter(Boolean),
          rows: [...g.querySelectorAll('.xt-row')].map(r => ({
            name: t(r.querySelector('.nm')), between: t(r.querySelector('.bt')),
            staged: t(r.querySelector('.xt-cell[data-view="staged"]')),
            warehouse: t(r.querySelector('.xt-cell[data-view="warehouse"]')),
            empty: [...r.querySelectorAll('.xt-cell[data-empty]')].map(c => c.dataset.view),
            pill: t(r.querySelector('.xt-pill')),
            aria: r.getAttribute('aria-label') || "",
            links: r.querySelectorAll('a').length})),
          key: t(g.querySelector('.xt-key'))};
    }""")


def _row(grid: dict, name: str, between: str | None = None) -> dict:
    found = [r for r in grid["rows"] if r["name"] == name and (between is None or r["between"] == between)]
    assert len(found) == 1, (name, between, grid["rows"])
    return found[0]


class TestWarehouseAndStagingViews:
    """REQ-DASH-272 criterion 24: a page awaiting a decision gives the
    warehouse's status, and its cross-table checks show each result against
    what's staged and against what's in the warehouse - one row per check,
    against fixture histories driven through the real lifecycle on a pinned
    clock and built by the real builders."""

    N, C = _cp_state("cp-notifications"), _cp_state("cp-clients")

    def test_s1_green_the_clause_the_caption_and_s4(self, clean_page, cp_pages):
        """S1 green: Notifications' page reads 'Awaiting a decision' for v2 and
        says the supply in the warehouse is v1 and Green, with its pill; the
        grid is captioned as the waiting supply's results. S4: the Client
        Register's page, its v2 promoted after Notifications v2's hold-back,
        reads Green with one result column and no result from Notifications
        v2's run; and at 375px every row's pill is inside the viewport and
        each stacked result names its view."""
        got = _s1(cp_pages)
        assert cp_pages.sc.holder("cp-clients", "2024-Q3") == got["C2"], "precondition"
        page = cp_pages.page()

        _goto(clean_page, page, state=self.N, in_place_on="2024-08-05")
        (verdict,) = _shown(clean_page, ".verdict-of")
        assert verdict["text"].startswith("Awaiting a decision"), verdict
        assert ("The supply in place in the warehouse is the one received 10:00am Thursday, 25 "
                "July 2024, and is Green.") in verdict["text"], verdict
        (clause,) = _shown(clean_page, ".verdict-of [data-wh-clause]")
        assert clause["attrs"]["data-wh-clause"] == "green"
        assert clean_page.locator(".verdict-of [data-wh-clause] .pill.green .ico").count() == 1, \
            "the status in the legend's own word and icon, never colour alone"
        (caption,) = _shown(clean_page, "[data-xt-caption]")
        assert caption["text"] == ("Results for the supply received 10:00am Monday, 5 August "
                                   "2024, awaiting a decision")
        grid = _grid(clean_page)
        assert grid["key"].endswith("The marks are dbt, Soda and datacontract-cli, in that "
                                    "order; · means that tool has no such check. Select a check "
                                    "for each tool's full result."), grid["key"]
        assert all(r["links"] == 0 for r in grid["rows"]), "no link inside a row's button"

        _goto(clean_page, page, state=self.C, in_place_on="2024-08-05")
        # S4 READS GREEN ON WHAT THIS HISTORY DECIDES: the cross-table section
        # and every row. (The page's own pill also reads the deployment's
        # blockers, which a variant page embeds from the deployment.)
        head = clean_page.locator('.scope-section[data-scope="cross-table"] .head .pill')
        assert head.inner_text().strip() == "Green", "S4: Clients reads Green"
        grid = _grid(clean_page)
        assert all(r["pill"] == "Green" for r in grid["rows"]), grid["rows"]
        assert grid["heads"] == ["Check", "Against what's in the warehouse"], grid["heads"]
        assert not any(r["empty"] for r in grid["rows"]), "no column of dashes"
        assert not any("5 August" in (r["warehouse"] or "") for r in grid["rows"]
                       if r["between"] == "Notifications → Client Register"), \
            "S4: nothing of Notifications v2's run counts on the Client Register's page"
        ref = _row(grid, "Client reference", "Notifications → Client Register")
        assert ref["warehouse"].startswith("In the warehouse: Pass ✓ ✓ ✓"), ref
        assert "Notifications received Thursday, 25 July 2024" in ref["warehouse"], ref
        # THE HISTORY ROWS (criterion 20): Clients v2 promoted by the rule after
        # a re-check against the warehouse; v1 promoted with its delivery.
        rows = [r["text"] for r in _shown(clean_page, "[data-promoted-with]")]
        assert ("Promoted 10:30am Monday, 5 August 2024 by the rule, re-checked against the "
                "Notifications in place in the warehouse (received 10:00am Thursday, 25 July 2024) "
                "because the Notifications received with it was held back.") in rows, rows
        _goto(clean_page, page, state=self.N, in_place_on="2024-08-05")
        rows = [r["text"] for r in _shown(clean_page, "[data-promoted-with]")]
        assert any(r.startswith("Promoted 10:30am Thursday, 25 July 2024 with the ")
                   and r.endswith(" and 3 more, by the rule") for r in rows), rows

        clean_page.set_viewport_size({"width": 375, "height": 800})
        _goto(clean_page, page, state=self.N, in_place_on="2024-08-05")
        boxes = clean_page.evaluate("""() => [...document.querySelectorAll('.xt-row')].map(r => {
            const p = r.querySelector('.xt-pill').getBoundingClientRect();
            const cells = [...r.querySelectorAll('.xt-cell')].filter(c => c.offsetParent !== null)
                .map(c => c.textContent.replace(/\\s+/g, " ").trim());
            return {left: p.left, right: p.right, width: window.innerWidth, cells}; })""")
        assert boxes and all(0 <= b["left"] and b["right"] <= b["width"] for b in boxes), boxes
        assert all(c.startswith(("Staged:", "In the warehouse:")) for b in boxes
                   for c in b["cells"]), boxes
        assert all(b["cells"] for b in boxes), "an empty view is omitted, never a bare dash"

    def test_s6_a_dual_row_held_back_against_the_warehouse(self, clean_page, cp_pages):
        """S6: Investigations v2 red on its own data is held back, so
        Notifications v2's Escalation completeness is re-checked against
        Investigations v1 and fails: ONE row, Pass against what's staged and
        Fail '— why it is held back' against what's in the warehouse, a Red
        pill, and both full sentences in its accessible name."""
        from gate_support import cross_red, own_red
        from test_package_gate import established

        cp_pages.at("2024-07-25T10:30:00+08:00")
        established(cp_pages.sc)
        cp_pages.sc.rules += [own_red("I2"), cross_red("cp-notifications", "cp_investigations",
                                                       when={"cp_investigations": "I1"})]
        cp_pages.at("2024-08-05T10:30:00+08:00")
        cp_pages.sc.deliver("2024-08-05T10:00:00+08:00", {
            "cp_clients": "C2", "cp_notifications": "N2", "cp_investigations": "I2"})
        cp_pages.sc.process()
        page = cp_pages.page()
        _goto(clean_page, page, state=self.N, in_place_on="2024-08-05")
        grid = _grid(clean_page)
        row = _row(grid, "Escalation completeness")
        assert row["staged"] == ("Staged: Pass ✓ ✓ ✓ Investigations received Monday, 5 August "
                                 "2024"), row
        assert row["warehouse"] == ("In the warehouse: Fail ✗ ✗ ✗ Investigations received "
                                    "Thursday, 25 July 2024 — why it is held back"), row
        assert row["pill"] == "Red", row
        assert ("Read against the Investigations supply received 10:00am Monday, 5 August 2024, "
                "not in place in the warehouse yet") in row["aria"], row["aria"]
        assert ("against the Investigations in place in the warehouse (received 10:00am Thursday, "
                "25 July 2024): the Investigations received with this supply was held back.") \
            in row["aria"], row["aria"]
        # THE PANEL: each tool's full result, the names real links.
        clean_page.locator(".xt-row", has_text="Escalation completeness").first.click()
        clean_page.wait_for_selector("[data-xt-tools]")
        tools = _shown(clean_page, "[data-xt-tools] .xt-tool")
        assert [t["attrs"]["data-tool"] for t in tools] == ["dbt", "soda", "datacontract"], tools
        assert all(any("in-place-on=2024-08-05" in a["href"] for a in t["links"]) for t in tools)

    def test_staggered_a_result_whose_partner_left_is_in_neither_cell(self, clean_page, cp_pages):
        """Dashboard UX v4 B1: Notifications v2 at 09:00 read against Clients
        v1; Clients v2 at 09:05 promoted alone. Notifications v2's page shows
        its 09:00 result in neither cell, its 09:05 result in the warehouse
        cell, and the 09:00 one in the panel's history 'since replaced in the
        warehouse'."""
        from gate_support import own_red
        from test_package_gate import established

        cp_pages.at("2024-07-25T10:30:00+08:00")
        established(cp_pages.sc)
        cp_pages.sc.rules.append(own_red("N2"))
        cp_pages.at("2024-08-05T09:01:00+08:00")
        cp_pages.sc.deliver("2024-08-05T09:00:00+08:00", {"cp_notifications": "N2"})
        cp_pages.sc.process()
        cp_pages.at("2024-08-05T09:06:00+08:00")
        c2 = cp_pages.sc.deliver("2024-08-05T09:05:00+08:00", {"cp_clients": "C2"})["C2"]
        cp_pages.sc.process()
        assert cp_pages.sc.holder("cp-clients", "2024-Q3") == c2, "precondition"
        page = cp_pages.page()
        _goto(clean_page, page, state=self.N, in_place_on="2024-08-05")
        row = _row(_grid(clean_page), "Client reference", "Notifications → Client Register")
        assert row["warehouse"].startswith("In the warehouse: Pass"), row
        assert "Client Register received Monday, 5 August 2024" in row["warehouse"], row
        assert "25 July" not in (row["staged"] or "") + (row["warehouse"] or ""), \
            "the 09:00 result read Clients v1, since replaced: in neither cell"
        clean_page.locator(".xt-row", has_text="Client reference").first.click()
        clean_page.wait_for_selector("[data-xt-tools]")
        options = clean_page.locator("#check-compare-select option").all_inner_texts()
        assert any("since replaced in the warehouse by the one received 9:05am Monday, 5 August "
                   "2024" in o for o in options), options

    def test_staggered_order_b_red_shows_both_cells(self, clean_page, cp_pages):
        """Staggered Order B red: Clients v2 at 09:00 fails Client reference
        against Notifications v1; Notifications v2 at 09:05 is red on its own
        data. The Client Register's row shows both cells, the warehouse one
        ending '— why it is held back' though that result came from its own
        09:00 arrival."""
        from gate_support import cross_red, own_red
        from test_package_gate import established

        cp_pages.at("2024-07-25T10:30:00+08:00")
        established(cp_pages.sc)
        cp_pages.sc.rules += [own_red("N2"), cross_red(
            "cp-notifications", "cp_clients", when={"cp_clients": "C2", "cp_notifications": "N1"})]
        cp_pages.at("2024-08-05T09:01:00+08:00")
        cp_pages.sc.deliver("2024-08-05T09:00:00+08:00", {"cp_clients": "C2"})
        cp_pages.sc.process()
        cp_pages.at("2024-08-05T09:06:00+08:00")
        cp_pages.sc.deliver("2024-08-05T09:05:00+08:00", {"cp_notifications": "N2"})
        cp_pages.sc.process()
        page = cp_pages.page()
        _goto(clean_page, page, state=self.C, in_place_on="2024-08-05")
        row = _row(_grid(clean_page), "Client reference", "Notifications → Client Register")
        assert row["staged"] and row["staged"].startswith("Staged:"), row
        assert row["warehouse"].startswith("In the warehouse: Fail ✗ ✗ ✗"), row
        assert row["warehouse"].endswith("— why it is held back"), row
        assert row["pill"] == "Red", row

    def test_the_owed_re_check_and_a_rejection(self, clean_page, cp_pages):
        """The owed re-check (criterion 10): a Clients v2 whose run stopped is
        promoted by a person, and the Notifications in the warehouse reads
        'Not yet re-checked' in the warehouse cell, noting the promotion. And
        after a rejection (criterion 19): S1's waiting Notifications v2 turned
        down, its page reads the in-warehouse supply's verdict."""
        from test_package_gate import established

        cp_pages.at("2024-07-25T10:30:00+08:00")
        established(cp_pages.sc)
        cp_pages.sc.crash.add(("dbt", "cp_clients__20240805"))
        cp_pages.at("2024-08-05T10:30:00+08:00")
        c2 = cp_pages.sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2"})["C2"]
        cp_pages.sc.process()
        cp_pages.at("2024-08-06T10:30:00+08:00")
        cp_pages.sc.promote_by_hand(c2, "2024-Q3", at="2024-08-06T10:00:00+08:00")
        page = cp_pages.page()
        _goto(clean_page, page, state=self.N, in_place_on="2024-08-06")
        row = _row(_grid(clean_page), "Client reference", "Notifications → Client Register")
        assert row["warehouse"] == ("In the warehouse: Not yet re-checked Client Register "
                                    "promoted Tuesday, 6 August 2024"), row
        assert ("Not yet re-checked against the Client Register promoted 10:00am Tuesday, 6 "
                "August 2024; the re-check runs on the next processing pass.") in row["aria"]

    def test_after_a_rejection_the_page_reads_the_warehouse(self, clean_page, cp_pages):
        got = _s1(cp_pages)
        cp_pages.reject(got["N2"], "2024-Q3", "2024-08-07T10:00:00+08:00")
        page = cp_pages.page()
        _goto(clean_page, page, state=self.N, in_place_on="2024-08-06")
        assert _shown(clean_page, ".verdict-of")[0]["attrs"]["data-verdict-of"] == "awaiting"
        _goto(clean_page, page, state=self.N, in_place_on="2024-08-07")
        (verdict,) = _shown(clean_page, ".verdict-of")
        assert verdict["attrs"]["data-verdict-of"] == "promoted", verdict
        assert "received 10:00am Thursday, 25 July 2024" in verdict["text"], verdict
