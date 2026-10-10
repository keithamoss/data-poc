"""
Builds dashboard/qa-reporting-dashboard.html from dashboard/qa-reporting-
dashboard.template.html (2026-09-16, Keith's call - plans/publishing-
and-history.md): reads the committed, hand-edited template, regenerates
the `const REAL_BIRTH_REG_DATA = {...};` and `const REAL_CP_DATA =
{...};` lines from reports/birth_registrations_dashboard.json and
reports/child_protection_dashboard.json (pipeline/build_dashboard_
data.py's/build_cp_dashboard_data.py's output), and writes the result
to the real, viewable HTML - gitignored, never committed, rebuilt fresh
by CI on every push and locally by `mothman pipeline run`/`mothman
dashboard rebuild`. Run this last, after orchestrate_bdm.py/
orchestrate_cp.py and the two build_*_dashboard_data.py scripts,
whenever the pipeline is regenerated.

`const AS_OF_OFFSET_DAYS` used to be re-embedded here too, from
`contract/data-asset.yaml` (Thread C, plans/publishing-and-history.md) -
removed entirely 2026-09-17 (plans/qa-pipeline.md Phase 5j), replaced
by real per-dataset cadence config - each dataset's participation in
contract/calendar.yaml since REQ-PIPE-110 (the contracts' `slaProperties:`
before it), read by qa_tools/common/agreement.py's cadence() and already
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
messages - Keith's own call was a hand-maintained file (../CHANGELOG.yaml,
repo root), edited alongside real work, so a human curates what's
presentable rather than every commit surfacing verbatim. This script's
only job is parsing that file's Keep-a-Changelog-style markdown into
something renderable (dashboard/changelog_yaml.py's parse_changelog()) -
same "placeholder here, real data only in the built output" treatment
as everything else on this page.

And `const REQUIREMENTS` (item 75, plans/qa-pipeline.md - 2026-09-18) -
a live requirements register (real user stories, MoSCoW priority,
implementation status, real CI-enforced test linkage), scoped via
AskUserQuestion at Keith's own request. Same hand-maintained-file
pattern as RELEASE_NOTES, but structured YAML (../requirements.yaml,
repo root) rather than prose markdown - Keith's own explicit choice
here, like CHANGELOG.yaml's. Parsed by dashboard/requirements_yaml.py's
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
`gh`/network access here either) reshapes it. Locally (`mothman pipeline
run`/`mothman dashboard rebuild`, no real token, no such file) this
embeds an empty {} rather than failing - graceful degradation, not a
hard requirement for every build.

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

`const AMBER_DECISIONS` - REQ-QAC-017's per-run `/accept` and `/reject`
on an amber supply, matched to a run by comment timestamp - is GONE
(retired by REQ-PIPE-122 criterion 23, 2026-10-05). An acknowledgement
is a decision-log entry now, embedded per dataset by the dashboard
builders (pipeline/acknowledgements.py), so there is nothing for this
script to fetch or match.

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
2026-09-18, scoped via two AskUserQuestion rounds; REDESIGNED the same
day, running-thoughts.md #3's own automation-tension follow-up to item
#5 Thread B, scoped via two more AskUserQuestion rounds) - a real
per-person, per-dataset streak of CLEAN TICKET RESOLUTIONS (qa_tools/
common/leaderboard.py's own build_leaderboard()), sorted by streak
descending. No longer CI-safe without a token the way ASSIGNMENTS is -
same real-source-not-a-file-this-script-reads-directly treatment as
TICKET_STATUS above, for the same reason (a real `gh` call
needs a real token this script doesn't have): `.github/workflows/
deploy-pages.yml` writes the raw ticket close/reopen history for every
real qa-ticket issue to TICKET_RESOLUTIONS_JSON below (via `python3 -m
qa_tools.common.leaderboard`, that module's own real `gh` boundary), and
this script calls leaderboard.build_leaderboard() (pure, no `gh`/network
here either) to turn it into the final embed. Empty [] locally with no
such file, same graceful degradation as TICKET_STATUS. Same
public-page privacy rule as ASSIGNMENTS: only people with a real
contract/people.yaml entry ever appear, by name/nickname - resolved by
real GitHub LOGIN now (whoever closed the ticket), not by email.

And `const PLANS` (running-thoughts.md #10, "Plans" tab, 2026-09-18) -
`{items: [...], threads: [...]}`, this project's own
plans/*.md planning memory, parsed by dashboard/plans_md.py's
parse_plans() straight from the committed plans/ directory - same
"placeholder here, real data only in the built output" treatment as
RELEASE_NOTES/REQUIREMENTS above, and the same CI-safe, no-live-data
status as everything else this script embeds (plans/*.md are real,
committed markdown files, no `gh`/DuckDB access needed).

And `const OUTSTANDING` (REQ-DASH-070, 2026-09-25) - everything that
needs a person, from qa_tools/common/outstanding.py's survey() over
committed history alone (delivery_log/, processing_log/,
observations/in_flight/, filings/). Asset-level rather than per
collection, deliberately: computing it inside either
build_*_dashboard_data.py is how one queue would have become two,
which is the thing that requirement exists to prevent.

And `const DEMO_CAST` (plans/tooling.md #1 Phase 6, "Demo" tab,
2026-09-19) - the raw asciinema v2 `.cast` file content (plain text,
JSON-lines) from the real, committed dashboard/demos/qa_wizard.cast -
a real recording of the actual mothman CLI/TUI (scripts/dev/
record_cast.py), embedded as a plain string rather than fetched by the
player at runtime (avoids a real file:// CORS failure - see the
template's own const comment for the full reasoning). Empty/null
locally if the file hasn't been recorded yet, same graceful-degradation
treatment as everything else this script embeds.

This only replaces those thirteen consts - the rest of the dashboard (its
CSS, the rendering code, the other 14 illustrative datasets, and the
separate SNAPSHOT_MANIFEST const dashboard/snapshot_dashboard.py owns)
is copied through unchanged from the template.
"""
from __future__ import annotations
import json
import os
import re

from dashboard.changelog_yaml import parse_changelog
from dashboard.plans_md import parse_plans
from qa_tools.common.sprint_state import dependency_data
from dashboard.requirements_yaml import parse_requirements
from qa_tools.common import asset_time
from qa_tools.common import environments
from qa_tools.common import hierarchy
from qa_tools.common import outstanding
from qa_tools.common import scenario_map
from qa_tools.common import runway
from qa_tools.common import schedule
from qa_tools.common.changelog import build_changelog
from qa_tools.common.github_links import build_check_source_links, build_folder_links, current_commit_sha
from qa_tools.common.leaderboard import build_leaderboard
from qa_tools.common.people import PEOPLE_YAML, assignees_for, parse_people_config
from qa_tools.common.ticket_status import parse_open_tickets
from qa_tools.common.ticket_sync import DATASET_AGENCY

ROOT = os.path.join(os.path.dirname(__file__), "..")
TEMPLATE_HTML = os.path.join(os.path.dirname(__file__), "qa-reporting-dashboard.template.html")
DASHBOARD_HTML = os.path.join(os.path.dirname(__file__), "qa-reporting-dashboard.html")
CHANGELOG_YAML = os.path.join(ROOT, "CHANGELOG.yaml")
PLANS_DIR = os.path.join(ROOT, "plans")
DEMO_CAST_PATH = os.path.join(os.path.dirname(__file__), "demos", "qa_wizard.cast")
REQUIREMENTS_YAML = os.path.join(ROOT, "requirements.yaml")
OPEN_TICKETS_JSON = os.path.join(ROOT, "reports", "open_tickets.json")
TICKET_RESOLUTIONS_JSON = os.path.join(ROOT, "reports", "ticket_resolutions.json")

TARGETS = [
    ("REAL_BIRTH_REG_DATA", os.path.join(ROOT, "reports", "birth_registrations_dashboard.json")),
    ("REAL_CP_DATA", os.path.join(ROOT, "reports", "child_protection_dashboard.json")),
]

# (agency, collection, display label) - the same two real scopes TARGETS
# above embeds, identified the way qa_results/'s own directory layout
# (and build_changelog()'s own signature) needs them, not the
# reshaped-JSON-file layout TARGETS uses. Derived from the one hierarchy
# since REQ-QAC-039, which is also what made both scopes collection-level
# - Birth Registrations used to be listed here under its dataset id and
# labelled "Birth Registrations"; it is now its collection, labelled
# "Civil Registration", the same way Child Protection always was.
CHANGELOG_SOURCES = [
    (agency, collection, name)
    for agency, collection, name in sorted({
        (d.agency_id, d.collection_id, d.collection_name) for d in hierarchy.all_datasets()
    })
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
    # leaves re-sorting to the UI). published_at is the "recent
    # activity" feed's actual subject (plans/publishing-and-history.md:
    # "who's committed/pushed what dataset's QA recently") - run_timestamp
    # stays on each entry for the UI to show alongside it, not as the
    # sort key.
    feed.sort(key=lambda e: e["published_at"] or "", reverse=True)
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

    # HIERARCHY - REQ-QAC-039. The one statement of the
    # agency/collection/dataset tree, from contract/data-asset.yaml, so
    # the template does not carry a second one for the REAL agencies and
    # collections its real dataset tiles hang under. Its own literals
    # remain as the raw, unembedded template's illustrative fallback
    # (Keith, 2026-09-23) - the template has to render with no data at
    # all, so something has to be written there; what this removes is
    # the copy that anything a reader ever sees would use.
    tree: dict = {"agencies": []}
    for entry in hierarchy.all_datasets():
        ag = next((a for a in tree["agencies"] if a["id"] == entry.agency_id), None)
        if ag is None:
            ag = {"id": entry.agency_id, "name": entry.agency_name, "collections": []}
            tree["agencies"].append(ag)
        col = next((c for c in ag["collections"] if c["id"] == entry.collection_id), None)
        if col is None:
            col = {"id": entry.collection_id, "name": entry.collection_name, "datasets": []}
            ag["collections"].append(col)
        col["datasets"].append({"id": entry.dataset_id, "name": entry.dataset_name})
    html = _replace_const(html, "HIERARCHY", json.dumps(tree, separators=(",", ":")))

    # ASSET_TIMEZONES - REQ-PIPE-048, versioned by REQ-PIPE-112. So the page
    # answers "what day is it" on the asset's clock instead of the viewer's
    # - EVERY version (criterion 11), so a past date is read in the zone in
    # force on it, without asking a backend.
    zones = [{"effective_from": v.effective_from.isoformat(), "zone": v.zone.key}
             for v in asset_time.timezone_versions()]
    html = _replace_const(html, "ASSET_TIMEZONES", json.dumps(zones, separators=(",", ":")))
    print(f"Re-embedded ASSET_TIMEZONES = {', '.join(z['zone'] + ' from ' + z['effective_from'] for z in zones)}")

    # BUILT_AT - REQ-DASH-071 criterion 13. When THIS page was built,
    # which only the build knows. The masthead used to count seconds up
    # from a hardcoded 4, so what a reader saw was the age of their own
    # browser tab rather than the age of the data
    # (plans/post-build-review.md #60).
    built_at = asset_time.now()
    html = _replace_const(html, "BUILT_AT", json.dumps(built_at.isoformat()))
    print(f"Re-embedded BUILT_AT = {built_at.isoformat()}")

    # BUILD_PROVENANCE - REQ-PIPE-092 criteria 7 and 17. WHICH environment
    # built this page, and from WHICH commit.
    #
    # The build used to happen in exactly one place, so there was nothing
    # to confuse a page with. It happens wherever the database is
    # reachable now, which makes a production build and a developer's
    # build two different artifacts that look identical.
    #
    # BOTH HALVES TOLERATE ABSENCE, and differently. An environment is
    # unset on a checkout nobody has configured, which is ordinary - the
    # page then says only when it was built, as it always did. A commit is
    # unavailable when git is not there or the checkout is not a
    # repository, which is also ordinary in a container built from a
    # tarball. Neither is worth failing a build over; claiming a value for
    # either would be.
    # current_commit_sha() rather than a second rev-parse of our own - it
    # already prefers GITHUB_SHA and falls back to the working tree, and
    # two implementations of "which commit is this" would be two things to
    # keep in step. It RAISES where git is absent or the directory is not
    # a repository, which is ordinary in a container built from a tarball,
    # so absence is tolerated here rather than failing a build: the page
    # then says only when it was built, as it always did.
    try:
        commit = current_commit_sha()
    except Exception:
        commit = None
    provenance = {"environment": None, "commit": commit}
    env = environments.current_or_none()
    if env is not None:
        # `publishes` travels with it (REQ-DASH-094 criterion 3) so the
        # page can say "not production" without carrying a second copy of
        # which environment that is. The page must not have to know the
        # name of the published one - that is configuration, and it
        # changes per deployment.
        provenance["environment"] = {"id": env.id, "label": env.label,
                                     "publishes": bool(env.publishes)}
    html = _replace_const(html, "BUILD_PROVENANCE",
                           json.dumps(provenance, separators=(",", ":")))
    print(f"Re-embedded BUILD_PROVENANCE = {provenance['environment'] or 'unset'}, "
          f"commit {provenance['commit'] or 'unknown'}")
    print(f"Re-embedded HIERARCHY = {len(tree['agencies'])} agenc(ies), "
          f"{sum(len(a['collections']) for a in tree['agencies'])} collection(s), "
          f"{len(hierarchy.all_datasets())} dataset(s)")

    # SCHEDULE_RUNWAY - REQ-PIPE-053. Enough for the PAGE to answer
    # "has this dataset's schedule run out, as at the date the viewer
    # is looking at" without any data access at all. That independence
    # is the criterion rather than an optimisation: an exhausted
    # schedule stops the run that would otherwise have reported it, so
    # a dashboard that could only learn about it from results would go
    # quiet in exactly the case this exists to make loud.
    #
    # Only AUTHORED calendars appear. A cadence rule generates periods
    # for ever and can never run out, so including one would invite the
    # page to warn about something that cannot happen.
    schedule_runway = {"configFile": "contract/data-asset.yaml",
                        "defaultThreshold": runway.DEFAULT_WARNING_SLOTS,
                        "calendars": []}
    for cal in schedule.calendars():
        if cal.current.is_cadence_rule:
            continue
        periods = schedule.periods_for_calendar(cal.name)
        datasets = []
        for entry in hierarchy.all_datasets():
            try:
                if schedule.calendar_for_dataset(entry.dataset_id).name != cal.name:
                    continue
            except schedule.NoCalendarAgreed:
                # No calendar, so no runway on this one (REQ-PIPE-106
                # criterion 1). Nothing to warn about, and warning would
                # ask somebody to author dates for a schedule nobody has
                # agreed.
                continue
            owed = [p for p in schedule.periods_for_dataset(entry.dataset_id) if p.expected]
            # A dataset's OWN last period, not the calendar's. They
            # differ the moment a dataset participates in some months
            # and not others - cp-case-workers' last owed period is
            # 2027-Q3 while its calendar runs to 2027-Q4 - and naming
            # the calendar's would tell a reader their dataset ended
            # after a period it never had.
            # WHEN IT ENDS (REQ-DASH-155 criterion 6): the day its last slot
            # closes, so the page says "exhausted" on the day the pipeline
            # starts holding rather than about a period earlier. None where
            # the last slot never closes.
            try:
                ends = runway.schedule_ends_on(entry.dataset_id)
            except (ValueError, KeyError, FileNotFoundError):
                ends = owed[-1].date if owed else None
            datasets.append({"id": entry.dataset_id,
                              "dates": [p.date.isoformat() for p in owed],
                              "lastPeriod": owed[-1].name if owed else None,
                              "lastDate": owed[-1].date.isoformat() if owed else None,
                              "endsOn": ends.isoformat() if ends else None})
        schedule_runway["calendars"].append({
            "name": cal.name,
            "threshold": cal.runway_warning_slots or runway.DEFAULT_WARNING_SLOTS,
            "lastPeriod": periods[-1].name if periods else None,
            "lastDate": periods[-1].date.isoformat() if periods else None,
            "datasets": datasets,
        })
    html = _replace_const(html, "SCHEDULE_RUNWAY",
                           json.dumps(schedule_runway, separators=(",", ":")))

    # PERIOD_SEQUENCES - REQ-DASH-054. Every named calendar's period
    # sequence, and which calendar each dataset follows.
    #
    # WHY THE BROWSER NEEDS THIS AT ALL. The as-of picker lets a viewer
    # choose ANY date, and a static site has no backend to ask - so the
    # page had its own JS port of cycle_start(), which was genuinely
    # unavoidable while a schedule was a RULE. It stops being unavoidable
    # once a schedule is a LIST, because a list can be shipped. And it was
    # never sufficient: a port can compute a cadence rule and cannot
    # compute an AUTHORED date list, which is what the quarterly calendar
    # is - Feb/May/Aug/Nov, deliberately not calendar quarters. Asking the
    # browser "which quarter is 2025-06-14 in" for Child Protection could
    # not be answered at all.
    #
    # IT ENDS AT THE PRESENT AND EMBEDS NO PERIOD THAT HAS NOT BEGUN
    # (criterion 3, Keith's own question: "why would we be able to choose
    # a date in the future? nothing has happened yet, so why project
    # forward?"). The as-of picker asks about the PAST, so a date with
    # nothing behind it has no answer to give. That removes the horizon
    # question rather than answering it - there is no number to choose,
    # because the sequence simply stops at the period today falls in.
    #
    # THE CURRENT PERIOD IS INCLUDED: it has begun. Its start is behind us
    # and its end ahead, which is exactly the period a viewer asking about
    # today is in.
    #
    # A CONSEQUENCE TO KNOW: a sequence that ends "now" ends at BUILD
    # time, so on a daily calendar the newest pickable date is the date of
    # the last build. That is tolerable only because REQ-PIPE-092 rebuilds
    # on every publish - a deployment that stopped rebuilding would
    # quietly lose its most recent days from the picker, which is what the
    # page's own out-of-range message makes visible rather than silent.
    today = asset_time.now().date()
    sequences = {"calendars": {}, "datasetCalendar": {}}
    for cal in schedule.calendars():
        sequences["calendars"][cal.name] = [
            {"period": period.name, "date": period.date.isoformat()}
            for period in schedule.periods_for_calendar(cal.name, until=today)
        ]
    for entry in hierarchy.all_datasets():
        try:
            sequences["datasetCalendar"][entry.dataset_id] = \
                schedule.calendar_for_dataset(entry.dataset_id).name
        except schedule.NoCalendarAgreed:
            # REQ-PIPE-106's subject, and NOT an error: the picker simply
            # has no period arithmetic to do for this dataset. Narrowed
            # from a bare `except Exception` on 2026-09-28, when the
            # declaration gained an exception of its own - catching
            # everything here would also have swallowed a genuinely
            # misconfigured calendar, which is the one thing the schedule
            # gate exists to make loud.
            sequences["datasetCalendar"][entry.dataset_id] = None
    html = _replace_const(html, "PERIOD_SEQUENCES",
                           json.dumps(sequences, separators=(",", ":")))
    print("Re-embedded PERIOD_SEQUENCES = "
          + ", ".join(f"{name} {len(periods)} period(s)"
                       for name, periods in sequences["calendars"].items())
          + f", ending at {today.isoformat()}")

    # OUTSTANDING - REQ-DASH-070. Everything that needs a person, from
    # committed history alone, as ONE thing carrying ONE total.
    #
    # Read here rather than in either build_*_dashboard_data.py on
    # purpose: this is asset-level and spans both collections, and
    # computing it per-collection is how it would have become two
    # queues - which is the thing the requirement exists to prevent.
    # SCENARIO_MAP - REQ-DASH-046. Read from the COMMITTED SCENARIOS.md
    # and nothing else: the coordinates were written there by the
    # generator, which is the only thing that knows where a scenario
    # landed, and this build may open nothing under data/.
    scenario_entries = scenario_map.read_map_data()
    html = _replace_const(html, "SCENARIO_MAP",
                           json.dumps(scenario_entries, separators=(",", ":")))
    print(f"Re-embedded SCENARIO_MAP = {len(scenario_entries)} scenario(s), "
          f"{sum(1 for e in scenario_entries if e.get('coordinates'))} with coordinates")

    outstanding_now = outstanding.survey().as_record()
    html = _replace_const(html, "OUTSTANDING",
                           json.dumps(outstanding_now, separators=(",", ":")))
    print(f"Re-embedded OUTSTANDING = {outstanding_now['total']} item(s) "
          f"({outstanding_now['blockingCount']} blocking) across "
          f"{len(outstanding_now['byAgency'])} agenc(ies)")
    print(f"Re-embedded SCHEDULE_RUNWAY = {len(schedule_runway['calendars'])} authored "
          f"calendar(s), "
          f"{sum(len(c['datasets']) for c in schedule_runway['calendars'])} dataset(s)")

    changelog_feed = _build_changelog_feed()
    html = _replace_const(html, "CHANGELOG_FEED", json.dumps(changelog_feed, separators=(",", ":")))
    print(f"Re-embedded CHANGELOG_FEED = {len(changelog_feed)} entries")

    release_notes = parse_changelog(CHANGELOG_YAML)
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

    if os.path.exists(TICKET_RESOLUTIONS_JSON):
        with open(TICKET_RESOLUTIONS_JSON) as f:
            raw_ticket_resolutions = json.load(f)
    else:
        raw_ticket_resolutions = []
    leaderboard_rows = build_leaderboard(raw_ticket_resolutions, people_config, DATASET_AGENCY)
    html = _replace_const(html, "LEADERBOARD", json.dumps(leaderboard_rows, separators=(",", ":")))
    print(f"Re-embedded LEADERBOARD = {len(leaderboard_rows)} real streak row(s)"
          + ("" if os.path.exists(TICKET_RESOLUTIONS_JSON) else " (no reports/ticket_resolutions.json - local build, embedding empty)"))

    plans = parse_plans(PLANS_DIR)
    html = _replace_const(html, "PLANS", json.dumps(plans, separators=(",", ":")))
    print(f"Re-embedded PLANS = {len(plans['items'])} items, "
          f"{len(plans['threads'])} threads")

    # REQ-DOCS-073. Computed by the same function `mothman plans
    # dependencies` renders, never re-derived in the page's own JS -
    # see the template's own const comment for why that matters here.
    deps = dependency_data()
    html = _replace_const(html, "SPRINT_DEPENDENCIES",
                           json.dumps(deps, separators=(",", ":")))
    print(f"Re-embedded SPRINT_DEPENDENCIES = {len(deps['sprints'])} sprint(s) "
          f"in the graph, {len(deps['stale'])} deferral(s) worth re-testing")

    if os.path.exists(DEMO_CAST_PATH):
        with open(DEMO_CAST_PATH) as f:
            demo_cast_text = f.read()
        html = _replace_const(html, "DEMO_CAST", json.dumps(demo_cast_text))
        print(f"Re-embedded DEMO_CAST = {len(demo_cast_text)} bytes ({DEMO_CAST_PATH})")
    else:
        html = _replace_const(html, "DEMO_CAST", "null")
        print("Re-embedded DEMO_CAST = null (no dashboard/demos/qa_wizard.cast - not recorded yet)")

    with open(DASHBOARD_HTML, "w") as f:
        f.write(html)


if __name__ == "__main__":
    embed()
