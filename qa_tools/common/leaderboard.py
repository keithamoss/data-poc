"""
Real per-person, per-dataset "streak of clean ticket resolutions"
leaderboard (running-thoughts.md #3, redesigned 2026-09-18 - the
automation-tension follow-up raised the same day, after item #5 Thread
B's own future AWS/S3-event-triggered vision surfaced a real problem
with the ORIGINAL design below: once QA *running* itself is automated,
there's no human left to credit for a "not-red run streak" - `run_by`
has nothing to attach to. Scoped with Keith via two more AskUserQuestion
rounds on top of the original two: the human role SHIFTS rather than
disappearing ("I think it shifts") - what's worth celebrating once
running is automated is "resolving red to green", which - per ticket_
sync.py's own repeated, load-bearing design principle ("closing it is
always a human decision, never automatic") - maps onto whoever actually
CLOSES a real GitHub QA ticket, the one action in this whole system
already guaranteed to require a person, regardless of whether the QA run
that opened it was ever triggered by one. Metric shape is "streak of
clean resolutions" (Keith's own final answer, after asking for the
question to be re-explained in more concrete terms): a person's own last
N ticket closes in a row that were never reopened - same STREAK feel as
the original design, just counting ticket resolutions instead of runs.

Superseded original design (kept only in git history, `git log -p` on
this file - running-thoughts.md #3's own entry has the full account):
walked each person's own chronological RUN sequence per dataset
(qa_results_reader + dataset_status.status_by_run()), counting backward
from their most recent run until a red one, amber not breaking it. Fully
replaced, not kept alongside - Keith's own explicit call ("redesign the
leaderboard now", overriding this session's own "recommended: defer"
default).

Real-fetch/pure-parse split, same convention as ticket_status.py/
acceptance_sync.py: fetch_ticket_resolution()/fetch_all_ticket_
resolutions() are the one real `gh` boundary - `gh issue view --json
number,labels` (for the real `dataset:<id>` label, same as acceptance_
sync.py's own grouping) PLUS a real call to GitHub's classic Issue
Events API (`gh api repos/{owner}/{repo}/issues/{n}/events`) for the one
thing `gh issue view` can never expose: WHO closed/reopened a ticket.
Verified for real against this project's own live repo, 2026-09-18 (no
`gh` CLI available in this sandbox, so verified via a direct authenticated
REST call instead, using the same GITHUB_TOKEN a real Actions job already
gets): the endpoint is reachable with that token, returns a real JSON
array with `event`/`actor.login`/`created_at` per entry - confirmed on a
real `labeled` event against this repo's own issue #2 (none of this
project's 7 real tickets has been closed yet, so a real `closed`/
`reopened` event itself is still unobserved - but `event`/`actor`/
`created_at` is GitHub's own long-documented, stable shape for every
event type on this endpoint, not something specific to `labeled`).
build_resolution_episodes()/compute_resolution_streaks()/
build_leaderboard() are pure functions over already-fetched data,
independently testable with plain dict fixtures, no `gh`/network here.

Same CI-safe-but-needs-a-token treatment as TICKET_STATUS/ACCEPTANCES
(dashboard/embed_dashboard_data.py's own docstring) - unlike the
original design (which never needed `gh` at all, only committed qa_
results/ + already-built dashboard JSON), this one now DOES need a real
raw-fetch step in .github/workflows/deploy-pages.yml, same shape as
qa_tools.common.acceptance_sync's own QA_COMMENTS_JSON step.

Identity now comes from a real GitHub LOGIN (the actor who closed the
ticket), never an email - a ticket-close event has no email attached at
all. Resolved against contract/people.yaml's own `github:` field (the
same field ticket_sync.py's own --assignee resolution already uses),
not the `email:` key the original design matched on. Same public-page
privacy rule as before: only people with a real people.yaml entry ever
appear, by name/nickname.
"""
from __future__ import annotations

import json
import os
import subprocess

from qa_tools.common.acceptance_sync import list_ticket_numbers
from qa_tools.common.people import assignees_for


def _run_gh(args: list[str]) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout


def fetch_ticket_resolution(owner: str, repo: str, issue_number: int) -> dict:
    """Real {number, labels, events} for one real qa-ticket issue -
    `labels` from `gh issue view` (for dataset:<id> grouping, same shape
    acceptance_sync.py's own fetch_ticket_comments() already uses);
    `events` the real closed/reopened history from GitHub's classic
    Issue Events API, filtered down to just those two event types and
    just the fields build_resolution_episodes() actually needs
    (`event`, the real actor login, `created_at`) - the raw payload
    carries a lot more (full user objects, commit refs, label colors)
    that has no use here.

    Real bug hit on this project's own first live `gh api` run
    (2026-09-18): `per_page` MUST be passed as a query string on the
    path, never via `-f`/`-F` - `gh api` silently switches an otherwise-
    GET request to POST the moment any `-f`/`-F` param is given (unless
    `-X GET` is also passed explicitly), and POSTing to this read-only
    endpoint fails with a real 415. Confirmed directly against this
    repo's own real issue #8 while diagnosing (a plain GET with
    `?per_page=100` in the URL returns 200; the same call via `-f`
    returns 415) - see `tests/test_leaderboard.py`'s own regression test
    for this exact real gh CLI gotcha."""
    meta = json.loads(_run_gh([
        "issue", "view", str(issue_number), "--repo", f"{owner}/{repo}",
        "--json", "number,labels",
    ]))
    raw_events = json.loads(_run_gh([
        "api", f"repos/{owner}/{repo}/issues/{issue_number}/events?per_page=100",
    ]))
    meta["events"] = [
        {
            "event": e["event"],
            "actor": (e.get("actor") or {}).get("login", "unknown"),
            "created_at": e["created_at"],
        }
        for e in raw_events
        if e.get("event") in ("closed", "reopened")
    ]
    return meta


def fetch_all_ticket_resolutions(owner: str, repo: str) -> list[dict]:
    """Every real qa-ticket issue this project has ever opened (open AND
    closed - list_ticket_numbers() already covers both, same as
    acceptance_sync.py's own use of it) with its own real close/reopen
    history attached."""
    return [fetch_ticket_resolution(owner, repo, n) for n in list_ticket_numbers(owner, repo)]


def build_resolution_episodes(raw_tickets: list[dict]) -> dict[str, list[dict]]:
    """{dataset_id: [{closed_by, closed_at, clean}, ...]} in real
    chronological order across EVERY real ticket that dataset has ever
    had (a dataset can accumulate more than one separate ticket over
    time - ticket_sync.py's own find_open_ticket() only ever reopens the
    CURRENTLY open one; once a ticket's closed, the next red/amber event
    opens a brand new issue rather than reopening the old one, so a
    dataset's own resolution history can legitimately span several real
    issue numbers). Each real `closed` event is one resolution episode,
    credited to whoever actually closed it (a real GitHub login);
    `clean` is False only when THAT SAME issue was later reopened -
    GitHub's own events for one issue always alternate open/closed, so
    checking whether the very next event is a `reopened` is sufficient,
    no windowing needed. A ticket missing a real `dataset:<id>` label is
    skipped (same defensive treatment acceptance_sync.py's own build_
    acceptances() already applies)."""
    by_dataset: dict[str, list[dict]] = {}
    for ticket in raw_tickets:
        labels = [label["name"] for label in ticket.get("labels", [])]
        dataset_id = next((label.split(":", 1)[1] for label in labels if label.startswith("dataset:")), None)
        if dataset_id is None:
            continue
        events = sorted(ticket.get("events", []), key=lambda e: e["created_at"])
        episodes = []
        for i, event in enumerate(events):
            if event["event"] != "closed":
                continue
            reopened_next = i + 1 < len(events) and events[i + 1]["event"] == "reopened"
            episodes.append({
                "closed_by": event["actor"],
                "closed_at": event["created_at"],
                "clean": not reopened_next,
            })
        if episodes:
            by_dataset.setdefault(dataset_id, []).extend(episodes)

    for episodes in by_dataset.values():
        episodes.sort(key=lambda ep: ep["closed_at"])
    return by_dataset


def compute_resolution_streaks(episodes: list[dict]) -> dict[str, dict]:
    """{github_login: {"streak": n, "last_closed_at": ...}} - each real
    person's own CURRENT streak of clean resolutions on one dataset:
    walk their own chronological sequence of real closes (skipping over
    anyone else's interleaved closes entirely - those neither extend nor
    break this person's own streak, same "own sequence only" treatment
    the original run-based design already used), counting backward from
    their own most recent close until hitting one that was later
    reopened. Only people with a streak of at least 1 appear."""
    by_person: dict[str, list[dict]] = {}
    for episode in episodes:
        by_person.setdefault(episode["closed_by"], []).append(episode)

    streaks: dict[str, dict] = {}
    for person, person_episodes in by_person.items():
        streak = 0
        last_closed_at = None
        for episode in reversed(person_episodes):
            if not episode["clean"]:
                break
            if last_closed_at is None:
                last_closed_at = episode["closed_at"]
            streak += 1
        if streak:
            streaks[person] = {"streak": streak, "last_closed_at": last_closed_at}
    return streaks


def build_leaderboard(raw_tickets: list[dict], people_config: dict, dataset_agency: dict[str, str]) -> list[dict]:
    """[{dataset_id, name, nickname, github, streak}, ...], sorted by
    streak descending - the real, publicly-embeddable rows dashboard/
    embed_dashboard_data.py's own LEADERBOARD const uses directly.
    `raw_tickets` is fetch_all_ticket_resolutions()'s own real,
    already-fetched shape. `dataset_agency` is qa_tools.common.
    ticket_sync's own real DATASET_AGENCY mapping - the same one
    dashboard/embed_dashboard_data.py's ASSIGNMENTS embed already
    resolves against.

    2026-09-19 (Keith's own explicit ask, after seeing an empty
    leaderboard on a real page with real people already in contract/
    people.yaml - correct behaviour at the time, since nobody had
    closed a real ticket yet, but not what he wanted to see): every
    real person currently ASSIGNED to a dataset (qa_tools.common.
    people.assignees_for(), same dataset-then-agency resolution the
    "Owned by" badge already uses) now appears for that dataset at
    streak=0 if they have no real clean-resolution streak yet, rather
    than the leaderboard only ever showing people who've already closed
    at least one ticket. A person with a real streak who ISN'T (or is
    no longer) assigned to that dataset still appears too, resolved
    against contract/people.yaml's `github:` field same as before - a
    real streak someone actually earned doesn't get erased by a later
    org-chart change, and unlike the roster rows above, still requires
    a matching people.yaml `github:` entry (a ticket-close event only
    ever carries a GitHub login, never an email)."""
    github_to_person = {p["github"]: p for p in people_config["people"].values() if p.get("github")}
    by_dataset = build_resolution_episodes(raw_tickets)

    rows = []
    for dataset_id in sorted(set(dataset_agency) | set(by_dataset)):
        streaks = compute_resolution_streaks(by_dataset.get(dataset_id, []))
        roster = assignees_for(dataset_id, dataset_agency.get(dataset_id), people_config)
        credited = set()
        roster_seen = set()
        for assignee in roster:
            github_login = assignee.get("github")
            # A person can hold more than one real role on the same
            # scope (contract/people.yaml: Keith himself is both `qa`
            # and `manager` for registry-services) - assignees_for()
            # returns one raw record per role, so without this dedupe
            # they'd get one leaderboard row per role rather than one
            # per person. Real bug found live via a Playwright
            # screenshot of the built leaderboard panel (2026-09-19):
            # "#1 - K$" and "#2 - K$" both for Birth Registrations.
            identity = github_login or assignee.get("name")
            if identity in roster_seen:
                continue
            roster_seen.add(identity)
            streak = streaks.get(github_login, {}).get("streak", 0) if github_login else 0
            rows.append({
                "dataset_id": dataset_id,
                "name": assignee.get("name"),
                "nickname": assignee.get("nickname"),
                "github": github_login,
                "streak": streak,
            })
            if github_login:
                credited.add(github_login)
        for github_login, info in streaks.items():
            if github_login in credited:
                continue
            person = github_to_person.get(github_login)
            if person is None:
                continue
            rows.append({
                "dataset_id": dataset_id,
                "name": person.get("name"),
                "nickname": person.get("nickname"),
                "github": github_login,
                "streak": info["streak"],
            })
    rows.sort(key=lambda r: r["streak"], reverse=True)
    return rows


def main() -> None:
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
    print(json.dumps(fetch_all_ticket_resolutions(owner, repo)))


if __name__ == "__main__":
    main()
