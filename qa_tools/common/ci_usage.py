"""`mothman github ci-usage`: the GitHub Actions minutes this repository is
billing, measured the way GitHub bills them (REQ-TEST-260 criterion 6).

WHY A COMMAND: a private repository on the free plan gets 2,000 Actions
minutes a MONTH, and the flip to private (REQ-DOCS-259) waits on a measured
week that fits. The figure has to be checkable in one command, by anyone,
every month after as well - a number in a requirement goes stale the way
CLAUDE.md's CI timing table did.

HOW GITHUB BILLS: each job's duration is rounded UP to a whole minute,
cancelled jobs bill the minutes they used, and a job that never started
bills nothing. Runs of every conclusion count, because every one of them
was paid for. The arithmetic here is a pure function over the API's own
runs and jobs, so it is tested against recorded responses with no network
(criterion 9); `_run_gh` is the one I/O boundary, exactly as
qa_tools/common/ticket_sync.py's is.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

#: GitHub's free-plan allowance for a PRIVATE repository, minutes a month.
#: Public repositories are unmetered, which is why this matters only at the
#: flip (REQ-DOCS-259).
ALLOWANCE_MINUTES = 2000

#: What the plan calls a month, for scaling a measured window.
DAYS_IN_MONTH = 30


def _run_gh(args: list[str]) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True, check=True)
    return result.stdout


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def billable_minutes(jobs: list[dict]) -> int:
    """Each job rounded up to a whole minute, as GitHub bills; a job with no
    start or no completion bills nothing, and a clock that reads backwards
    (seen on a job cancelled before it ran: completed_at before started_at)
    bills nothing rather than a negative minute."""
    total = 0
    for job in jobs:
        started, completed = _parse(job.get("started_at")), _parse(job.get("completed_at"))
        if started is None or completed is None:
            continue
        seconds = max(0.0, (completed - started).total_seconds())
        total += math.ceil(seconds / 60)
    return total


@dataclass
class WorkflowUsage:
    workflow: str
    runs: int = 0
    cancelled: int = 0
    pushes: int = 0
    minutes: int = 0
    _pushed: set = field(default_factory=set, repr=False, compare=False)


@dataclass
class Summary:
    days: int
    workflows: list[WorkflowUsage]
    total: WorkflowUsage
    monthly_minutes: int
    allowance: int

    @property
    def fits(self) -> bool:
        return self.monthly_minutes <= self.allowance


def summarise(runs: list[dict], jobs_by_run: dict[int, list[dict]], days: int,
              allowance: int = ALLOWANCE_MINUTES) -> Summary:
    """Per workflow and in total: runs, cancelled runs, pushes (distinct
    commits that arrived by a push event - a manual dispatch is a run, not a
    push) and billable minutes, plus the total scaled to a 30-day month."""
    by_name: dict[str, WorkflowUsage] = {}
    total = WorkflowUsage(workflow="total")
    for run in runs:
        usage = by_name.setdefault(run["name"], WorkflowUsage(workflow=run["name"]))
        minutes = billable_minutes(jobs_by_run.get(run["id"], []))
        for target in (usage, total):
            target.runs += 1
            target.minutes += minutes
            if run.get("conclusion") == "cancelled":
                target.cancelled += 1
            if run.get("event") == "push":
                target._pushed.add(run["head_sha"])
    for target in (*by_name.values(), total):
        target.pushes = len(target._pushed)
    monthly = round(total.minutes * DAYS_IN_MONTH / max(days, 1))
    return Summary(days=days, workflows=sorted(by_name.values(), key=lambda w: -w.minutes),
                   total=total, monthly_minutes=monthly, allowance=allowance)


def repository() -> str:
    """owner/repo, from GITHUB_REPOSITORY as the rest of `mothman github`
    reads it; refused plainly when unset rather than guessed from a remote."""
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repo or "/" not in repo:
        raise SystemExit("GITHUB_REPOSITORY is not set (owner/repo) - `mothman github ci-usage` "
                         "reads that repository's Actions runs and will not guess one.")
    return repo


def fetch(repo: str, days: int) -> tuple[list[dict], dict[int, list[dict]]]:
    """Every run created in the last `days` days, then each run's jobs."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs: list[dict] = []
    page = 1
    while True:
        out = _run_gh(["api", f"repos/{repo}/actions/runs?per_page=100&page={page}"
                              f"&created=>={since}"])
        batch = json.loads(out).get("workflow_runs", [])
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    jobs_by_run = {}
    for run in runs:
        out = _run_gh(["api", f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100"])
        jobs_by_run[run["id"]] = json.loads(out).get("jobs", [])
    return runs, jobs_by_run


def render(summary: Summary, repo: str) -> str:
    lines = [f"GitHub Actions usage for {repo}, last {summary.days} day(s):", ""]
    width = max([len(w.workflow) for w in summary.workflows] + [len("total")])
    lines.append(f"  {'workflow':<{width}}  runs  cancelled  pushes  billable minutes")
    for w in [*summary.workflows, summary.total]:
        lines.append(f"  {w.workflow:<{width}}  {w.runs:>4}  {w.cancelled:>9}  {w.pushes:>6}  "
                     f"{w.minutes:>16,}")
    verdict = "fits" if summary.fits else "does NOT fit"
    lines += ["", f"Scaled to a {DAYS_IN_MONTH}-day month: {summary.monthly_minutes:,} billable "
                  f"minutes against a private free allowance of {summary.allowance:,} - {verdict}."]
    return "\n".join(lines)


def main(days: int) -> None:
    repo = repository()
    runs, jobs_by_run = fetch(repo, days)
    print(render(summarise(runs, jobs_by_run, days), repo))
