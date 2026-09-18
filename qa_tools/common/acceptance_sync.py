"""
Matches a real `/accept` comment on a dataset's own QA ticket
(qa_tools/common/ticket_sync.py) to the real run it applies to -
running-thoughts.md #6 ("read-only tension: accepting/rejecting amber
supplies"), mechanism only, scoped via two AskUserQuestion rounds with
Keith: the write happens as a real comment on GitHub itself (this tool
stays read-only, never a button in the dashboard - there's no backend
to receive one), an accepted amber supply stays amber on the dashboard
(never silently reads as green - it just gets a visible acknowledgment
badge), and acceptance is per-run, not a standing decision (a NEW amber
arrival needs its own fresh `/accept`). The amber-GOVERNANCE question
itself (does amber always/sometimes/never need a decision at all) stays
parked in plans/conceptual-design.md Thread A - not resolved here.

No `run_id` needs typing or copying: every real run already has a real
arrival WINDOW - [this run's own arrived_date, the next run's
arrived_date) sourced straight from committed qa_results/ history
(qa_results_reader, no live data). A bare `/accept` comment is matched
to whichever run's window contains the comment's own real timestamp -
the human just has to comment while looking at the current state, not
know or type an identifier.

Same real-fetch/pure-match split as ticket_status.py/ticket_sync.py:
`fetch_all_ticket_comments()` is the one real `gh` boundary (list every
qa-ticket issue - OPEN AND CLOSED, since an acceptance on a now-closed
ticket must still resolve for real - then each one's own real comments);
`build_acceptances()`/`match_acceptances()` are pure functions over
already-fetched data, independently testable with plain dict fixtures,
no `gh`/network here at all.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

from qa_tools.common.qa_results_reader import QA_RESULTS_DIR, list_run_ids, read_dataset_stats
from qa_tools.common.ticket_sync import TICKET_LABEL

ACCEPT_RE = re.compile(r"^/accept\b", re.IGNORECASE)

# Every real dataset this MVP's ticketing covers, and which real
# qa_results/ (agency, dataset-or-collection) scope its own arrival
# history actually lives under. NOT always the same as the dataset_id
# itself: Child Protection's 6 real tables each get their own ticket
# (ticket_sync.py's own per-table scoping), but arrive together as ONE
# real collection delivery, so all 6 share the SAME real run history -
# qa_results/child-protection-family-support/child-protection/, not 6
# separate per-table directories. A plain dict, not derived from
# anything dynamic - same "just add the new entry" convention every
# other small real mapping in this project already uses (github_links.py's
# own AGENCY_QA_FOLDER/DATASET_QA_FOLDER, validate_check_lifecycle.py's
# _YAML_SOURCES).
QA_RESULTS_SCOPE_FOR_DATASET = {
    "birth-registrations": ("registry-services", "birth-registrations"),
    "cp-clients": ("child-protection-family-support", "child-protection"),
    "cp-notifications": ("child-protection-family-support", "child-protection"),
    "cp-investigations": ("child-protection-family-support", "child-protection"),
    "cp-placements": ("child-protection-family-support", "child-protection"),
    "cp-carers": ("child-protection-family-support", "child-protection"),
    "cp-case-workers": ("child-protection-family-support", "child-protection"),
}


def _run_windows_for_dataset(dataset_id: str, qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[tuple[str, date, date | None]]:
    """[(run_id, window_start, window_end_or_None), ...], oldest first,
    built purely from committed qa_results/ history - the same real
    `arrived_date` the dashboard's own supply-history table already
    groups by. The last run's own window end is None (open-ended - "any
    /accept from its own arrival onward, until a newer run exists").
    Two real runs sharing the same arrived_date (possible, not
    currently seen in this project's real history) resolve to whichever
    sorts first - an accepted real edge case for a PoC, not worth extra
    machinery to disambiguate."""
    scope = QA_RESULTS_SCOPE_FOR_DATASET.get(dataset_id)
    if scope is None:
        return []
    agency, dataset = scope
    entries: list[tuple[str, date]] = []
    for run_id in list_run_ids(agency, dataset, qa_results_dir):
        stats = read_dataset_stats(agency, dataset, run_id, qa_results_dir)
        if stats is None:
            continue
        entries.append((run_id, date.fromisoformat(stats["manifest_entry"]["arrived_date"])))
    entries.sort(key=lambda e: e[1])
    return [
        (run_id, start, entries[i + 1][1] if i + 1 < len(entries) else None)
        for i, (run_id, start) in enumerate(entries)
    ]


def match_acceptances(comments: list[dict], windows: list[tuple[str, date, date | None]]) -> dict[str, dict]:
    """{run_id: {accepted_by, accepted_at, comment_url}} for whichever
    real runs got a real `/accept` comment inside their own arrival
    window. Pure - no I/O. The FIRST (chronologically) matching comment
    for a given run wins if more than one person accepts the same run;
    a run with no matching comment simply doesn't appear (never a
    placeholder entry)."""
    result: dict[str, dict] = {}
    accept_comments = sorted(
        (c for c in comments if ACCEPT_RE.match((c.get("body") or "").strip())),
        key=lambda c: c["createdAt"],
    )
    for comment in accept_comments:
        created = datetime.fromisoformat(comment["createdAt"].replace("Z", "+00:00")).date()
        for run_id, start, end in windows:
            if created >= start and (end is None or created < end):
                result.setdefault(run_id, {
                    "accepted_by": (comment.get("author") or {}).get("login", "unknown"),
                    "accepted_at": comment["createdAt"],
                    "comment_url": comment.get("url"),
                })
                break
    return result


def build_acceptances(raw_tickets: list[dict], qa_results_dir: Path | str = QA_RESULTS_DIR) -> dict[str, dict]:
    """{dataset_id: {run_id: {...}}} - `raw_tickets` is the real,
    already-fetched `gh issue view --json number,labels,comments` output
    for every real qa-ticket issue (fetch_all_ticket_comments()'s own
    return shape). Pure - no gh/network here. A ticket missing a real
    `dataset:<id>` label is skipped (same defensive treatment
    ticket_status.py's own parse_open_tickets() already applies - only
    this project's own ticket_sync.py ever attaches that label, but a
    human could always hand-edit labels on a real issue)."""
    comments_by_dataset: dict[str, list[dict]] = {}
    for ticket in raw_tickets:
        labels = [label["name"] for label in ticket.get("labels", [])]
        dataset_id = next((label.split(":", 1)[1] for label in labels if label.startswith("dataset:")), None)
        if dataset_id is None:
            continue
        comments_by_dataset.setdefault(dataset_id, []).extend(ticket.get("comments", []))

    result: dict[str, dict] = {}
    for dataset_id, comments in comments_by_dataset.items():
        windows = _run_windows_for_dataset(dataset_id, qa_results_dir)
        matched = match_acceptances(comments, windows)
        if matched:
            result[dataset_id] = matched
    return result


# ---- Real gh fetch (the one I/O boundary in this module) --------------

def _run_gh(args: list[str]) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout


def list_ticket_numbers(owner: str, repo: str) -> list[int]:
    """Every real qa-ticket issue this project has ever opened - state
    `all`, not just open: a `/accept` comment on a ticket that's SINCE
    been closed (dataset permanently fixed, human closed it) must still
    resolve for real against that run's own history."""
    out = _run_gh([
        "issue", "list", "--repo", f"{owner}/{repo}",
        "--label", TICKET_LABEL, "--state", "all",
        "--json", "number", "--limit", "100",
    ])
    return [issue["number"] for issue in json.loads(out)]


def fetch_ticket_comments(owner: str, repo: str, issue_number: int) -> dict:
    out = _run_gh([
        "issue", "view", str(issue_number), "--repo", f"{owner}/{repo}",
        "--json", "number,labels,comments",
    ])
    return json.loads(out)


def fetch_all_ticket_comments(owner: str, repo: str) -> list[dict]:
    return [fetch_ticket_comments(owner, repo, n) for n in list_ticket_numbers(owner, repo)]


def main() -> None:
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
    print(json.dumps(fetch_all_ticket_comments(owner, repo)))


if __name__ == "__main__":
    main()
