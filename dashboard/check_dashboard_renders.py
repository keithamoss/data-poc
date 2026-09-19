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
REAL_BIRTH_REG_DATA/REAL_CP_DATA/SNAPSHOT_MANIFEST consts are still
placeholders (null/null/[]). See buildBirthRegistrations()'s/
buildChildProtectionDatasets()'s own comment in the template for the
fallback mechanism (genDataset(), the same illustrative-mock generator
the other 14 non-real datasets already use) this check verifies.

Doesn't build anything itself - run this after the full rebuild
(qa_tools.bdm/cp.build_results_from_history, pipeline.
build_dashboard_data/build_cp_dashboard_data, dashboard.
embed_dashboard_data) has already produced the file. Needs Playwright's
Chromium already available (see pyproject.toml's dev dependency group).

Run as `python3 -m dashboard.check_dashboard_renders`.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from dashboard.embed_dashboard_data import TARGETS

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
    """Each `const <NAME> = {...};` block actually parses as JSON - the
    exact same single-line regex embed_dashboard_data.py itself uses to
    find and replace these lines, reused here rather than re-derived, so
    the two never drift apart on what "the embedded data line" means."""
    html = DASHBOARD_PATH.read_text()
    errors = []
    for const_name, _data_path in TARGETS:
        pattern = re.compile(rf"const {const_name} = (.*?);\n")
        match = pattern.search(html)
        if not match:
            errors.append(f"{const_name}: no embedded const found in the built HTML")
            continue
        try:
            json.loads(match.group(1))
        except json.JSONDecodeError as e:
            errors.append(f"{const_name}: embedded data isn't valid JSON - {e}")
    return errors


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
