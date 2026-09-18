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

`const AS_OF_OFFSET_DAYS` used to be re-embedded here too, from
`contract/data-asset.yaml` (Thread C, plans/publishing-and-history.md) -
removed entirely 2026-09-17 (plans/qa-pipeline.md Phase 5j), replaced
by real per-dataset cadence config living in each dataset's own ODCS
contract (`slaProperties:`, read by pipeline/cadence.py and already
folded into REAL_BIRTH_REG_DATA/REAL_CP_DATA's own `sla.cadence` field
by the two build_*_dashboard_data.py scripts above - nothing left for
this script to separately embed).

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

And `const RELEASE_NOTES` (item 62, plans/qa-pipeline.md - Phase 5h) -
"what changed about the PoC/tool itself over time," a genuinely
different feed from CHANGELOG_FEED above (that one is data-QA-activity,
built from qa_results/; this one is the tool's own development
history). Deliberately NOT derived from qa_results/ or real git commit
messages - Keith's own call was a hand-maintained file (../CHANGELOG.md,
repo root), edited alongside real work, so a human curates what's
presentable rather than every commit surfacing verbatim. This script's
only job is parsing that file's Keep-a-Changelog-style markdown into
something renderable (dashboard/changelog_md.py's parse_changelog()) -
same "placeholder here, real data only in the built output" treatment
as everything else on this page.

And `const REQUIREMENTS` (item 75, plans/qa-pipeline.md - 2026-09-18) -
a live requirements register (real user stories, MoSCoW priority,
implementation status, real CI-enforced test linkage), scoped via
AskUserQuestion at Keith's own request. Same hand-maintained-file
pattern as RELEASE_NOTES, but structured YAML (../requirements.yaml,
repo root) rather than prose markdown - Keith's own explicit choice
here, unlike CHANGELOG.md's. Parsed by dashboard/requirements_yaml.py's
parse_requirements(); schema/linkage enforcement is a SEPARATE CI gate
(qa_tools/common/validate_requirements.py), not this script's job.

And `const TICKET_STATUS` (item 76's UI-integration follow-up,
plans/qa-pipeline.md, 2026-09-18, scoped via AskUserQuestion) - a
dataset_id -> {number, url, title, updated_at} mapping for every
currently-open real GitHub Issue the ticketing MVP (qa_tools/common/
ticket_sync.py) has opened, shown as a small badge on each dataset's own
tile. Unlike every other const above, this one's real source data is
NOT a file this script reads directly - it's a real `gh issue list`
call only `.github/workflows/deploy-pages.yml` can make (a real GitHub
API call needs a real token; this script has no token of its own and
must stay callable locally with none). That workflow writes the raw `gh`
JSON to OPEN_TICKETS_JSON below before calling this script; qa_tools/
common/ticket_status.py's parse_open_tickets() (a pure function, no
`gh`/network access here either) reshapes it. Locally (./run_pipeline.sh,
no real token, no such file) this embeds an empty {} rather than
failing - graceful degradation, not a hard requirement for every build.

And `const GITHUB_LINKS` (running-thoughts.md #8, "deep links from the
dashboard back into GitHub", 2026-09-18, scoped via AskUserQuestion) -
`{checks: {check_id: url}, agencies: {agencyId: url}, datasets:
{datasetId: url}}`, built by qa_tools/common/github_links.py (a check's
own real source file + line, found by a plain text scan for its
check_id's own literal value - verified against all 3 real check-
definition formats this repo uses; a dataset/agency's own qa_tools/
<bdm|cp>/ folder). Every link is pinned to THIS build's own commit SHA
(qa_tools.common.github_links.current_commit_sha() - GITHUB_SHA in a
real Actions run, `git rev-parse HEAD` locally) rather than a moving
branch, so it always shows exactly what a check looked like when this
dashboard was published, same reproducibility stance as everything else
this script embeds.

And `const ACCEPTANCES` (running-thoughts.md #6, "read-only tension:
accepting/rejecting amber supplies", 2026-09-18, scoped via two
AskUserQuestion rounds) - `{dataset_id: {run_id: {accepted_by,
accepted_at, comment_url}}}`, a real human's `/accept` comment on that
dataset's own QA ticket, matched to the real run it applies to purely
by comment timestamp against that run's own real arrival window
(qa_tools/common/acceptance_sync.py - no run_id ever typed by anyone).
Same real-source-not-a-file-this-script-reads-directly treatment as
TICKET_STATUS above, for the same reason (a real `gh` call needs a real
token this script doesn't have): `.github/workflows/deploy-pages.yml`
writes the raw `gh issue view` output for every real qa-ticket issue to
QA_COMMENTS_JSON below (via `python3 -m qa_tools.common.acceptance_sync`,
the one real `gh`-calling boundary), and this script calls
acceptance_sync.build_acceptances() (pure, no `gh`/network here either)
to turn it into the final embed. Empty {} locally with no such file,
same graceful degradation as TICKET_STATUS.

And `const ASSIGNMENTS` (running-thoughts.md #2, "data-asset-level
people/roles config", 2026-09-18, scoped via AskUserQuestion) -
`{agencies: {agencyId: [...]}, datasets: {datasetId: [...]}}`, real
people assigned to each real scope (qa_tools/common/people.py's own
dataset-then-agency resolution - contract/people.yaml is a real,
committed file this script CAN read directly, unlike OPEN_TICKETS_JSON/
QA_COMMENTS_JSON - no `gh`/token needed, so no CI-only raw-fetch step
for this one). Each record's real `email` field
(people.py's own richer shape, needed by ticket_sync.py's `--assignee`
resolution) is stripped before embedding - this repo is public (Keith's
own call, CLAUDE.md), and a person's email has no reason to be baked
into a publicly-deployed static page just because their name/GitHub
username already is.

And `const LEADERBOARD` (running-thoughts.md #3, "gamification MVP",
2026-09-18, scoped via two AskUserQuestion rounds) - a real per-person,
per-dataset "current not-red streak" (qa_tools/common/leaderboard.py's
own build_leaderboard()), sorted by streak descending. CI-safe like
ASSIGNMENTS above (committed qa_results/ + already-built dashboard JSON
+ contract/people.yaml - no `gh`/token, no CI-only raw-fetch step). The
already-loaded REAL_BIRTH_REG_DATA/REAL_CP_DATA payloads (captured into
`real_data` in the TARGETS loop above) are reused directly rather than
re-reading those same two files a second time. Same public-page privacy
rule as ASSIGNMENTS: only people with a real contract/people.yaml entry
ever appear, by name/nickname - a bare `run_by` email is never shown.

This only replaces those eleven consts - the rest of the dashboard (its
CSS, the rendering code, the other 14 illustrative datasets, and the
separate SNAPSHOT_MANIFEST const dashboard/snapshot_dashboard.py owns)
is copied through unchanged from the template.
"""
from __future__ import annotations
import json
import os
import re

from dashboard.changelog_md import parse_changelog
from dashboard.requirements_yaml import parse_requirements
from qa_tools.common.acceptance_sync import build_acceptances
from qa_tools.common.changelog import build_changelog
from qa_tools.common.github_links import build_check_source_links, build_folder_links, current_commit_sha
from qa_tools.common.leaderboard import build_leaderboard
from qa_tools.common.people import PEOPLE_YAML, assignees_for, parse_people_config
from qa_tools.common.ticket_status import parse_open_tickets
from qa_tools.common.ticket_sync import DATASET_AGENCY

ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATE_HTML = os.path.join(os.path.dirname(__file__), "qa-reporting-dashboard.template.html")
DASHBOARD_HTML = os.path.join(os.path.dirname(__file__), "qa-reporting-dashboard.html")
CHANGELOG_MD = os.path.join(ROOT, "CHANGELOG.md")
REQUIREMENTS_YAML = os.path.join(ROOT, "requirements.yaml")
OPEN_TICKETS_JSON = os.path.join(ROOT, "reports", "open_tickets.json")
QA_COMMENTS_JSON = os.path.join(ROOT, "reports", "qa_comments.json")

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

    real_data = {}  # const_name -> already-loaded dict, reused below by the LEADERBOARD step
    for const_name, data_json_path in TARGETS:
        with open(data_json_path) as f:
            data = json.load(f)
        real_data[const_name] = data
        real_json = json.dumps(data, separators=(",", ":"))
        html = _replace_const(html, const_name, real_json)
        print(f"Re-embedded {len(real_json)} bytes of real data into {const_name}")

    changelog_feed = _build_changelog_feed()
    html = _replace_const(html, "CHANGELOG_FEED", json.dumps(changelog_feed, separators=(",", ":")))
    print(f"Re-embedded CHANGELOG_FEED = {len(changelog_feed)} entries")

    release_notes = parse_changelog(CHANGELOG_MD)
    html = _replace_const(html, "RELEASE_NOTES", json.dumps(release_notes, separators=(",", ":")))
    print(f"Re-embedded RELEASE_NOTES = {len(release_notes['entries'])} dated entries")

    requirements = parse_requirements(REQUIREMENTS_YAML)
    html = _replace_const(html, "REQUIREMENTS", json.dumps(requirements, separators=(",", ":")))
    print(f"Re-embedded REQUIREMENTS = {len(requirements)} requirements")

    if os.path.exists(OPEN_TICKETS_JSON):
        with open(OPEN_TICKETS_JSON) as f:
            raw_issues = json.load(f)
    else:
        raw_issues = []
    ticket_status = parse_open_tickets(raw_issues)
    html = _replace_const(html, "TICKET_STATUS", json.dumps(ticket_status, separators=(",", ":")))
    print(f"Re-embedded TICKET_STATUS = {len(ticket_status)} open ticket(s)"
          + ("" if os.path.exists(OPEN_TICKETS_JSON) else " (no reports/open_tickets.json - local build, embedding empty)"))

    sha = current_commit_sha()
    github_links = {"checks": build_check_source_links(sha=sha), **build_folder_links(sha=sha)}
    html = _replace_const(html, "GITHUB_LINKS", json.dumps(github_links, separators=(",", ":")))
    print(f"Re-embedded GITHUB_LINKS = {len(github_links['checks'])} check link(s) at commit {sha[:12]}")

    if os.path.exists(QA_COMMENTS_JSON):
        with open(QA_COMMENTS_JSON) as f:
            raw_tickets = json.load(f)
    else:
        raw_tickets = []
    acceptances = build_acceptances(raw_tickets)
    html = _replace_const(html, "ACCEPTANCES", json.dumps(acceptances, separators=(",", ":")))
    print(f"Re-embedded ACCEPTANCES = {sum(len(v) for v in acceptances.values())} accepted run(s) across {len(acceptances)} dataset(s)"
          + ("" if os.path.exists(QA_COMMENTS_JSON) else " (no reports/qa_comments.json - local build, embedding empty)"))

    def _public(record: dict) -> dict:
        return {k: v for k, v in record.items() if k != "email"}

    people_config = parse_people_config(PEOPLE_YAML)
    dataset_assignments = {}
    for dataset_id, agency_id in DATASET_AGENCY.items():
        records = assignees_for(dataset_id, agency_id, people_config)
        if records:
            dataset_assignments[dataset_id] = [_public(r) for r in records]
    assignments = {
        "agencies": {agency_id: [_public(r) for r in records] for agency_id, records in people_config["agency_assignments"].items()},
        "datasets": dataset_assignments,
    }
    html = _replace_const(html, "ASSIGNMENTS", json.dumps(assignments, separators=(",", ":")))
    print(f"Re-embedded ASSIGNMENTS = {len(assignments['agencies'])} agency/{len(assignments['datasets'])} dataset assignment(s)")

    dataset_jsons = {real_data["REAL_BIRTH_REG_DATA"]["id"]: real_data["REAL_BIRTH_REG_DATA"]}
    for ds in real_data["REAL_CP_DATA"]["datasets"]:
        dataset_jsons[ds["id"]] = ds
    leaderboard_rows = build_leaderboard(dataset_jsons, people_config)
    html = _replace_const(html, "LEADERBOARD", json.dumps(leaderboard_rows, separators=(",", ":")))
    print(f"Re-embedded LEADERBOARD = {len(leaderboard_rows)} real streak row(s)")

    with open(DASHBOARD_HTML, "w") as f:
        f.write(html)


if __name__ == "__main__":
    embed()
