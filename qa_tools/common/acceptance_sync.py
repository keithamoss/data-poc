"""
Matches a real `/accept` OR `/reject` comment on a dataset's own QA
ticket (qa_tools/common/ticket_sync.py) to the real run it applies to -
running-thoughts.md #6 ("read-only tension: accepting/rejecting amber
supplies"). `/accept` was built first, 2026-09-18, mechanism only, with
the amber-GOVERNANCE question itself (does amber always/sometimes/never
need a decision at all - plans/conceptual-design.md Thread A's own
parked three-option list) deliberately left unresolved. `/reject` was
added 2026-09-19, once Keith resolved that exact question via a real
`AskUserQuestion` round: option 3 - amber requires an explicit human
decision, per run, accept or reject. Thread A's own "Parked" note is
updated to record this as resolved, not duplicated here.

Both write the same way, scoped via `AskUserQuestion` for `/accept`
(2026-09-18) then confirmed/extended for `/reject` (2026-09-19): a real
comment on GitHub itself (this tool stays read-only, never a button in
the dashboard - there's no backend to receive one); no `run_id` needs
typing or copying (every real run already has a real arrival WINDOW -
[this run's own received_at, the next run's received_at) sourced
straight from committed qa_results/ history, qa_results_reader, no live
data - a bare `/accept`/`/reject` comment is matched to whichever run's
window contains the comment's own real timestamp); and the decision is
per-run, not standing (a NEW amber arrival needs its own fresh comment).
Where they differ, both by Keith's own explicit call: an ACCEPTED run's
pill stays amber (never silently reads as green) with a small
acknowledgment badge; a REJECTED run's pill *also* stays amber (Keith's
own call, 2026-09-19 - the smaller, safer option, symmetric with accept
rather than repainting the pill red) with its own rejection badge. If a
run's window somehow carries both an `/accept` and a `/reject` (someone
changes their mind, or two different people comment differently), the
MOST RECENT one (by real comment timestamp) wins, regardless of which
command it was - Keith's own explicit call, 2026-09-19.

Same real-fetch/pure-match split as ticket_status.py/ticket_sync.py:
`fetch_all_ticket_comments()` is the one real `gh` boundary (list every
qa-ticket issue - OPEN AND CLOSED, since a decision on a now-closed
ticket must still resolve for real - then each one's own real comments);
`build_decisions()`/`match_decisions()` are pure functions over
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

from qa_tools.common import hierarchy
from qa_tools.common.qa_results_reader import QA_RESULTS_DIR, list_run_ids, read_dataset_stats
from qa_tools.common.ticket_sync import TICKET_LABEL
from qa_tools.common import asset_time

ACCEPT_RE = re.compile(r"^/accept\b", re.IGNORECASE)
REJECT_RE = re.compile(r"^/reject\b", re.IGNORECASE)

# dataset -> the qa_results/ (agency, dataset-or-collection) scope its
# own arrival history lives under. NOT always the same as the dataset_id
# itself: Child Protection's 6 real tables each get their own ticket
# (ticket_sync.py's own per-table scoping) but arrive together as ONE
# real collection delivery, so all 6 share one run history. Since
# REQ-QAC-039 Birth Registrations does too, under its own collection -
# the asymmetry that used to make this map need spelling out by hand.
QA_RESULTS_SCOPE_FOR_DATASET = {d.dataset_id: d.qa_results_scope for d in hierarchy.all_datasets()}


def _run_windows_for_dataset(dataset_id: str, qa_results_dir: Path | str = QA_RESULTS_DIR) -> list[tuple[str, date, date | None]]:
    """[(run_id, window_start, window_end_or_None), ...], oldest first,
    built purely from committed qa_results/ history - the same real
    receipt instant the dashboard's own supply-history table already
    groups by. The last run's own window end is None (open-ended - "any
    /accept from its own arrival onward, until a newer run exists").

    Two real runs sharing the same receipt DATE turn out to be common in
    this project's own real committed history (a real bug found live,
    2026-09-19, while adding /reject test coverage: 352 real BDM runs,
    only 123 distinct dates - this project's own full pipeline
    regenerations tend to produce same-day original+resupply pairs).
    This module's own long-documented intent was "resolve to whichever
    sorts first", but a naive `entries[i+1]` end-date lookup actually
    gave the FIRST tied entry a zero-width [date, date) window - always
    empty, since `start <= created < end` can never hold when
    start==end - so a same-day comment silently fell through to the
    SECOND (or last, for 3+-way ties) entry instead, the opposite of the
    documented intent. Fixed by deduping to one window-owning entry per
    distinct date (the first, by this function's own `list_run_ids`
    iteration order) before computing window ends - a same-day comment
    now genuinely resolves to whichever run sorts first, and the other
    same-day run(s) are simply omitted from this list rather than given
    a window that could never match anything."""
    scope = QA_RESULTS_SCOPE_FOR_DATASET.get(dataset_id)
    if scope is None:
        return []
    agency, dataset = scope
    entries: list[tuple[str, date]] = []
    for run_id in list_run_ids(agency, dataset, qa_results_dir):
        stats = read_dataset_stats(agency, dataset, run_id, qa_results_dir)
        if stats is None:
            continue
        entries.append((run_id, asset_time.local_date(stats["arrival_record"]["received_at"])))
    entries.sort(key=lambda e: e[1])
    deduped: list[tuple[str, date]] = []
    seen_dates: set[date] = set()
    for run_id, start in entries:
        if start in seen_dates:
            continue
        seen_dates.add(start)
        deduped.append((run_id, start))
    return [
        (run_id, start, deduped[i + 1][1] if i + 1 < len(deduped) else None)
        for i, (run_id, start) in enumerate(deduped)
    ]


def _classify(comment: dict) -> str | None:
    """"accept"/"reject"/None for a real comment's own body - the two
    real commands this mechanism understands, or neither."""
    body = (comment.get("body") or "").strip()
    if ACCEPT_RE.match(body):
        return "accept"
    if REJECT_RE.match(body):
        return "reject"
    return None


def match_decisions(comments: list[dict], windows: list[tuple[str, date, date | None]]) -> dict[str, dict]:
    """{run_id: {decision: "accept"|"reject", decided_by, decided_at,
    comment_url}} for whichever real runs got a real `/accept` or
    `/reject` comment inside their own arrival window. Pure - no I/O.
    Comments are walked in real chronological order and each match
    OVERWRITES any earlier one for the same run, so the MOST RECENT
    comment always wins - whether that's a later `/accept` superseding
    an earlier one, or an `/accept` and a `/reject` on the same run
    (Keith's own explicit call, 2026-09-19: whichever happened last
    wins, regardless of which command it was). A run with no matching
    comment simply doesn't appear (never a placeholder entry)."""
    result: dict[str, dict] = {}
    decision_comments = sorted(
        ((c, _classify(c)) for c in comments if _classify(c) is not None),
        key=lambda pair: pair[0]["createdAt"],
    )
    for comment, decision in decision_comments:
        created = datetime.fromisoformat(comment["createdAt"].replace("Z", "+00:00")).date()
        for run_id, start, end in windows:
            if created >= start and (end is None or created < end):
                result[run_id] = {
                    "decision": decision,
                    "decided_by": (comment.get("author") or {}).get("login", "unknown"),
                    "decided_at": comment["createdAt"],
                    "comment_url": comment.get("url"),
                }
                break
    return result


def build_decisions(raw_tickets: list[dict], qa_results_dir: Path | str = QA_RESULTS_DIR) -> dict[str, dict]:
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
        matched = match_decisions(comments, windows)
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
