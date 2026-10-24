"""
Phase 3's CI gate step (plans/publishing-and-history.md Thread A):
verifies the just-built dashboard/qa-reporting-dashboard.html is
structurally sound (both embedded JSON blobs actually parse) and
renders cleanly in a real headless browser (zero console errors, and
the main drill-down view actually populated with content) - an
automated, permanent version of the same Playwright check this
project's own sessions have run by hand throughout.

Also checks dashboard/qa-reporting-dashboard.template.html itself
renders cleanly, with zero console errors, straight off disk -
Keith's explicit requirement, 2026-09-16 (the same day the template/
build-output split landed): opening the raw template (before
embed_dashboard_data.py has ever run - a real path a contributor can
hit, not just a hypothetical) must not crash just because its
COLLECTION_DATA/SNAPSHOT_MANIFEST consts are still placeholders
(null/[]).

Doesn't build anything itself - run this after the full rebuild
(qa_tools.tools.results_history, pipeline.build_dashboard_data,
dashboard.embed_dashboard_data) has already produced the file. Needs Playwright's
Chromium already available (see pyproject.toml's dev dependency group).

Run as `python3 -m dashboard.check_dashboard_renders`.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_PATH = ROOT / "dashboard" / "qa-reporting-dashboard.html"
TEMPLATE_PATH = ROOT / "dashboard" / "qa-reporting-dashboard.template.html"

# Normal Playwright resolution (needs `uv run playwright install chromium`
# once - see pyproject.toml's dev dependency group) works on a real
# contributor machine or a real CI runner. Some sandboxed dev
# environments pre-install a Chromium build at a fixed, version-pinned
# path instead that Playwright's own default channel lookup won't find
# (a real, confirmed gap, 2026-09-19, found by `claude/playwright-mcp-
# verify-b2t4nb` hitting exit 1 in a genuinely fresh sandbox - this
# sandbox's installed `chromium_headless_shell-1194` didn't match what
# the pinned Playwright package expected, `-1234`). `PLAYWRIGHT_
# CHROMIUM_PATH` remains a real, explicit escape hatch when set - but
# now falls back automatically to `/opt/pw-browsers/chromium`, this
# environment's own documented, version-independent symlink (see this
# session's own environment notes: "launch with executablePath:
# '/opt/pw-browsers/chromium' instead of downloading" - a stable path
# that survives the pinned browser build being bumped, unlike hardcoding
# a version number), when that env var is unset AND the symlink actually
# exists - so a fresh sandbox doesn't need the env var set by hand at
# all. Falls through to Playwright's own default resolution (empty
# kwargs) when neither applies - a real contributor machine or CI
# runner, where this sandbox-specific path doesn't exist.
_SANDBOX_CHROMIUM_SYMLINK = "/opt/pw-browsers/chromium"


def _resolve_chromium_path() -> str | None:
    explicit = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if explicit:
        return explicit
    if os.path.exists(_SANDBOX_CHROMIUM_SYMLINK):
        return _SANDBOX_CHROMIUM_SYMLINK
    return None


_CHROMIUM_PATH = _resolve_chromium_path()


def _check_embedded_json() -> list[str]:
    """The built page's COLLECTION_DATA is all there and is what its list
    says - read through dashboard/data_files.py's one reader
    (REQ-DASH-291 criteria 13 and 14), which takes the page's data from its
    sibling files, its inline blocks or, for a page built before the split,
    the const itself. So the gate and the build cannot disagree on what "the
    page's data" is, and a missing file, or one whose SHA-256 differs from
    the page's list, fails here before any browser is started."""
    from dashboard import data_files
    from qa_tools import collections

    found = data_files.read_page(DASHBOARD_PATH.read_text(), DASHBOARD_PATH.parent)
    if found.problems:
        return [f"COLLECTION_DATA: {p}" if not p.startswith("COLLECTION_DATA") else p
                for p in found.problems]
    data = found.collections
    # EVERY REGISTERED COLLECTION IS IN IT (REQ-DASH-244 criterion 9) -
    # the list from the registry, never a second one here.
    return [f"COLLECTION_DATA: no entry for collection {c.id!r}"
            for c in collections.all_collections() if c.id not in (data or {})]


async def _check_render(html_path: Path, label: str) -> list[str]:
    console_errors: list[str] = []
    async with async_playwright() as p:
        launch_kwargs = {"executable_path": _CHROMIUM_PATH} if _CHROMIUM_PATH else {}
        browser = await p.chromium.launch(**launch_kwargs)
        page = await browser.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))
        await page.goto(f"file://{html_path.resolve()}")
        await page.wait_for_timeout(2000)

        # "key UI elements actually render", not just "no console errors" -
        # #view is where the whole drill-down UI mounts; empty means the
        # page loaded but the app itself never actually rendered anything.
        view_html = await page.locator("#view").inner_html()
        if not view_html.strip():
            console_errors.append("#view is empty after load - the dashboard app never rendered")
        # A page that rendered its missing-file error rendered no tier at all
        # (REQ-DASH-291 criterion 14), whatever the console says.
        if await page.locator('[data-testid="data-file-error"]').count():
            console_errors.append("the page shows its data-file error: "
                                  + (await page.locator('[data-testid="data-file-error"]').inner_text()))

        # EVERY DATASET, not just the landing page
        # (plans/post-build-review.md #43). This gate is cited as "what
        # would catch a throw reaching a viewer", and for a long time it
        # could not: it loaded the front door and stopped, while three
        # of seven dataset pages threw an uncaught TypeError on
        # drill-down. Proven blind before this was written - the bug was
        # reintroduced into a built copy and the gate still reported
        # zero console errors.
        #
        # Routes come from the page's own DATA and its own
        # stateToHash(), so a dataset added later is covered without
        # anybody remembering to add it here, and the gate can never
        # visit a route the app would not build.
        routes = await page.evaluate("""() => {
            // `typeof DATA`, not `window.DATA`: a top-level `const`
            // creates a global BINDING but not a window property, so
            // window.DATA is undefined while DATA itself is fine. The
            // first version tested window.DATA, got nothing, and
            // enumerated zero routes - the second no-op in a row while
            // extending this gate.
            if(typeof DATA === "undefined" || !DATA || !DATA.agencies) return [];
            const out = [];
            DATA.agencies.forEach(ag => {
                out.push(stateToHash({tier:"agency", agencyId:ag.id}));
                ag.collections.forEach(col => col.datasets.forEach(ds =>
                    out.push(stateToHash({tier:"dataset", agencyId:ag.id,
                                           collectionId:col.id, datasetId:ds.id}))));
            });
            return out;
        }""")
        # A REAL LOAD PER ROUTE, not an assignment to location.hash.
        # The first version of this did the latter and was a no-op: the
        # app listens for `popstate`, which a programmatic hash
        # assignment does not fire, so the gate "visited" nine routes
        # without re-rendering once and still reported zero errors.
        # Caught by re-proving it against the reintroduced bug rather
        # than trusting the change - which is the same
        # a-check-that-never-runs-looks-like-success shape this gate was
        # being extended to close.
        #
        # A full load is also what a person opening a shared deep link
        # actually does, so it exercises the initial-state resolution
        # path as well as the render.
        for route in routes:
            await page.goto(f"file://{html_path.resolve()}{route}")
            await page.wait_for_timeout(400)
            body = await page.locator("#view").inner_html()
            if not body.strip():
                console_errors.append(f"#view is empty at {route}")

        await browser.close()
    return [f"{label} render check: {e}" for e in console_errors]


def main() -> int:
    if not DASHBOARD_PATH.exists():
        print(f"FAILED: {DASHBOARD_PATH} doesn't exist - run the build pipeline first.", file=sys.stderr)
        return 1
    if not TEMPLATE_PATH.exists():
        print(f"FAILED: {TEMPLATE_PATH} doesn't exist.", file=sys.stderr)
        return 1

    errors = _check_embedded_json()
    errors += asyncio.run(_check_render(DASHBOARD_PATH, "built output"))
    errors += asyncio.run(_check_render(TEMPLATE_PATH, "template"))

    if errors:
        print(f"dashboard render check FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("dashboard render check OK - embedded data valid, zero console errors, #view populated "
          "(built output AND template both verified).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
