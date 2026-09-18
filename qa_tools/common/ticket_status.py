"""
Reshapes real `gh issue list` output (every currently-open real GitHub
Issue this project's own ticketing MVP - qa_tools/common/ticket_sync.py,
item 76, plans/qa-pipeline.md - opened) into a dataset_id -> ticket dict
the dashboard can embed directly. A pure function, deliberately separate
from ticket_sync.py itself (which does the real writes - creating/
commenting on issues) - this module only ever reads a list of issue
dicts already fetched elsewhere; it never calls `gh` itself.

Scoped via AskUserQuestion with Keith, 2026-09-18: badge shown on each
dataset's own tile (Tier 2 + Tier 3), sourced by embedding this at
DASHBOARD BUILD TIME (dashboard/embed_dashboard_data.py, via a new
`.github/workflows/deploy-pages.yml` step that runs a real, read-only
`gh issue list --label qa-ticket --state open --json ...` - `issues:
read` only, no `contents: write`, no commit-back) rather than a live
client-side call to GitHub's API from the visitor's browser - keeps the
same "placeholder here, real data only in the built output, no live
external dependency at render time" treatment CHANGELOG_FEED/
REQUIREMENTS/RELEASE_NOTES already use, and avoids unauthenticated
GitHub API rate limits / CORS as a new runtime dependency this dashboard
doesn't otherwise have.

Keying: each real ticket carries a `dataset:<id>` label (ticket_sync.py's
own `_dataset_label()`) alongside the shared `qa-ticket` one - the same
real dataset ids used throughout the dashboard JSON (`birth-
registrations`, `cp-clients`, etc.), so no separate lookup/mapping is
needed here.
"""
from __future__ import annotations


def parse_open_tickets(raw_issues: list[dict]) -> dict[str, dict]:
    """dataset_id -> {number, url, title, updated_at} for every open
    qa-ticket issue in raw_issues (the real `gh issue list --json
    number,title,url,labels,updatedAt` output, already parsed from
    JSON). An issue missing a `dataset:<id>` label is skipped rather than
    raising - only this project's own ticket_sync.py ever attaches the
    `qa-ticket` label in the first place, but a human could always edit
    labels on a real GitHub Issue by hand, and a dashboard build
    shouldn't crash over that."""
    result: dict[str, dict] = {}
    for issue in raw_issues:
        labels = [label["name"] for label in issue.get("labels", [])]
        dataset_id = next((label.split(":", 1)[1] for label in labels if label.startswith("dataset:")), None)
        if dataset_id is None:
            continue
        result[dataset_id] = {
            "number": issue["number"],
            "url": issue["url"],
            "title": issue["title"],
            "updated_at": issue.get("updatedAt"),
        }
    return result
