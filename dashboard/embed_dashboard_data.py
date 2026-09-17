"""
Builds dashboard/qa-reporting-dashboard.html from dashboard/qa-reporting-
dashboard.template.html (2026-09-16, Keith's call - plans/publishing-
and-history.md): reads the committed, hand-edited template, regenerates
the `const REAL_BIRTH_REG_DATA = {...};` and `const REAL_CP_DATA =
{...};` lines from reports/birth_registrations_dashboard.json and
reports/child_protection_dashboard.json (pipeline/build_dashboard_
data.py's/build_cp_dashboard_data.py's output), and writes the result
to the real, viewable HTML - gitignored, never committed, rebuilt fresh
by CI on every push and locally by ./run_pipeline.sh. Run this last,
after orchestrate.py/orchestrate_cp.py and the two build_*_dashboard_
data.py scripts, whenever the pipeline is regenerated.

Also re-embeds `const AS_OF_OFFSET_DAYS` from `contract/data-asset.yaml`
(Thread C, plans/publishing-and-history.md) - the one genuinely
data-asset-level (not per-dataset) config value the as-of viewing
feature needs, read the same way check_id's `data-asset-1` placeholder
already is.

And `const CHANGELOG_FEED` (Phase 5a, Thread A, plans/publishing-and-
history.md) - the global "who published what, when" activity feed,
built by calling qa_tools.common.changelog.build_changelog() directly
(a pure function of committed qa_results/ + real git history, same
"safe to run in CI" status as everything else this script touches - no
live data/DuckDB access) for each of the two real dataset scopes
(Birth Registrations, Child Protection's collection-level scope - NOT
once per CP table, since a real CP run QAs and commits all 6 tables
together as one event), merged, sorted newest-published-first, and
capped to CHANGELOG_DEPTH entries. This is the reason this script now
runs as `python3 -m dashboard.embed_dashboard_data` rather than a bare
`python3 dashboard/embed_dashboard_data.py` - the bare form puts only
`dashboard/` on sys.path, not the repo root, so `import qa_tools...`
would fail; `-m` (from the repo root, which every caller already `cd`s
to first) puts the repo root on sys.path instead, same as every other
cross-package script in this repo already runs.

This only replaces those four consts - the rest of the dashboard (its
CSS, the rendering code, the other 14 illustrative datasets, and the
separate SNAPSHOT_MANIFEST const dashboard/snapshot_dashboard.py owns)
is copied through unchanged from the template.
"""
from __future__ import annotations
import json
import os
import re

import yaml

from qa_tools.common.changelog import build_changelog

ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATE_HTML = os.path.join(os.path.dirname(__file__), "qa-reporting-dashboard.template.html")
DASHBOARD_HTML = os.path.join(os.path.dirname(__file__), "qa-reporting-dashboard.html")
DATA_ASSET_YAML = os.path.join(ROOT, "contract", "data-asset.yaml")

TARGETS = [
    ("REAL_BIRTH_REG_DATA", os.path.join(ROOT, "reports", "birth_registrations_dashboard.json")),
    ("REAL_CP_DATA", os.path.join(ROOT, "reports", "child_protection_dashboard.json")),
]

# (agency, dataset-or-collection id, display label) - the same two real
# scopes TARGETS above embeds, just identified the way qa_results/'s own
# directory layout (and build_changelog()'s own signature) needs them,
# not the reshaped-JSON-file layout TARGETS uses.
CHANGELOG_SOURCES = [
    ("registry-services", "birth-registrations", "Birth Registrations"),
    ("child-protection-family-support", "child-protection", "Child Protection"),
]

# "Something like the last 20-50 entries" (plans/publishing-and-
# history.md's own Thread A write-up left the exact number open) - 30,
# the middle of that range, picked here rather than left further open;
# trivial to change later if it turns out wrong once there's enough
# real history to judge by.
CHANGELOG_DEPTH = 30


def _build_changelog_feed() -> list[dict]:
    feed = []
    for agency, dataset, label in CHANGELOG_SOURCES:
        for entry in build_changelog(agency, dataset):
            feed.append({**entry, "label": label})
    # Newest-published-first ("recent activity", not "oldest first" -
    # build_changelog()'s own return order - its docstring explicitly
    # leaves re-sorting to the UI). committed_at is the "recent
    # activity" feed's actual subject (plans/publishing-and-history.md:
    # "who's committed/pushed what dataset's QA recently") - run_timestamp
    # stays on each entry for the UI to show alongside it, not as the
    # sort key.
    feed.sort(key=lambda e: e["committed_at"] or "", reverse=True)
    return feed[:CHANGELOG_DEPTH]


def _replace_const(html: str, const_name: str, value_json: str) -> str:
    new_line = f"const {const_name} = {value_json};\n"
    pattern = re.compile(rf"const {const_name} = .*?;\n")
    # a lambda replacement (not a plain string) so backslash sequences
    # already inside the JSON (e.g. "—") are never reinterpreted as
    # regex backreferences by re.sub
    html, n = pattern.subn(lambda _m: new_line, html, count=1)
    if n != 1:
        raise RuntimeError(
            f"Could not find exactly one 'const {const_name} = ...;' line to replace "
            f"(found {n}) - has the dashboard's structure changed?"
        )
    return html


def embed() -> None:
    with open(TEMPLATE_HTML) as f:
        html = f.read()

    for const_name, data_json_path in TARGETS:
        with open(data_json_path) as f:
            data = json.load(f)
        real_json = json.dumps(data, separators=(",", ":"))
        html = _replace_const(html, const_name, real_json)
        print(f"Re-embedded {len(real_json)} bytes of real data into {const_name}")

    with open(DATA_ASSET_YAML) as f:
        data_asset = yaml.safe_load(f)
    offset_days = data_asset["as_of_offset_days"]
    html = _replace_const(html, "AS_OF_OFFSET_DAYS", json.dumps(offset_days))
    print(f"Re-embedded AS_OF_OFFSET_DAYS = {offset_days}")

    changelog_feed = _build_changelog_feed()
    html = _replace_const(html, "CHANGELOG_FEED", json.dumps(changelog_feed, separators=(",", ":")))
    print(f"Re-embedded CHANGELOG_FEED = {len(changelog_feed)} entries")

    with open(DASHBOARD_HTML, "w") as f:
        f.write(html)


if __name__ == "__main__":
    embed()
