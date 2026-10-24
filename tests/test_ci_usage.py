"""`mothman github ci-usage` (REQ-TEST-260 criteria 6 and 9): billable
GitHub Actions minutes, computed the way GitHub bills them - each job's
duration rounded UP to a whole minute - from recorded API responses, with
no network access.

The arithmetic is a pure function over the runs and jobs the API returns,
so the fake sits at the one real I/O boundary (`_run_gh`, as
tests/test_ticket_sync.py does) and the command's own parsing, counting
and scaling are what run for real.
"""
from __future__ import annotations

import json

from click.testing import CliRunner

from qa_tools.common import ci_usage

RUNS = [
    # Two pushes to test.yml, the first superseded (cancelled) by the second.
    {"id": 1, "name": "Run test suite", "path": ".github/workflows/test.yml", "event": "push",
     "status": "completed", "conclusion": "cancelled", "head_sha": "aaa1"},
    {"id": 2, "name": "Run test suite", "path": ".github/workflows/test.yml", "event": "push",
     "status": "completed", "conclusion": "success", "head_sha": "bbb2"},
    # A manual dispatch of the same workflow: a run, not a push.
    {"id": 3, "name": "Run test suite", "path": ".github/workflows/test.yml",
     "event": "workflow_dispatch", "status": "completed", "conclusion": "success",
     "head_sha": "bbb2"},
    # The validator on the same two pushes.
    {"id": 4, "name": "Validate committed configuration",
     "path": ".github/workflows/validate-config.yml", "event": "push",
     "status": "completed", "conclusion": "success", "head_sha": "aaa1"},
    {"id": 5, "name": "Validate committed configuration",
     "path": ".github/workflows/validate-config.yml", "event": "push",
     "status": "completed", "conclusion": "success", "head_sha": "bbb2"},
]

JOBS = {
    # 61s rounds up to 2 billable minutes; a cancelled job still bills what it used.
    1: [{"name": "test", "conclusion": "cancelled",
         "started_at": "2026-10-18T06:00:00Z", "completed_at": "2026-10-18T06:01:01Z"},
        # Cancelled before it started: no completion time, bills nothing.
        {"name": "coverage", "conclusion": "cancelled", "started_at": None, "completed_at": None}],
    2: [{"name": "test", "conclusion": "success",
         "started_at": "2026-10-18T06:10:00Z", "completed_at": "2026-10-18T06:20:00Z"},
        {"name": "js-tests", "conclusion": "success",
         "started_at": "2026-10-18T06:10:00Z", "completed_at": "2026-10-18T06:11:30Z"}],
    3: [{"name": "test", "conclusion": "success",
         "started_at": "2026-10-18T07:00:00Z", "completed_at": "2026-10-18T07:05:00Z"}],
    4: [{"name": "validate", "conclusion": "success",
         "started_at": "2026-10-18T06:00:00Z", "completed_at": "2026-10-18T06:00:40Z"}],
    5: [{"name": "validate", "conclusion": "success",
         "started_at": "2026-10-18T06:10:00Z", "completed_at": "2026-10-18T06:10:50Z"}],
}


def test_a_job_bills_whole_minutes_rounded_up_and_an_unstarted_job_bills_nothing():
    assert ci_usage.billable_minutes(JOBS[1]) == 2
    assert ci_usage.billable_minutes(JOBS[2]) == 10 + 2
    assert ci_usage.billable_minutes([{"started_at": None, "completed_at": None}]) == 0


def test_the_summary_counts_runs_cancellations_pushes_and_minutes_per_workflow():
    summary = ci_usage.summarise(RUNS, JOBS, days=7)
    by_name = {w.workflow: w for w in summary.workflows}
    test = by_name["Run test suite"]
    assert (test.runs, test.cancelled, test.pushes, test.minutes) == (3, 1, 2, 2 + 12 + 5)
    validate = by_name["Validate committed configuration"]
    assert (validate.runs, validate.cancelled, validate.pushes, validate.minutes) == (2, 0, 2, 2)
    assert summary.total.minutes == 21
    # Pushes are counted once across workflows: two commits were pushed.
    assert summary.total.pushes == 2


def test_the_figure_is_scaled_to_a_thirty_day_month_against_the_allowance():
    summary = ci_usage.summarise(RUNS, JOBS, days=7)
    assert summary.monthly_minutes == round(21 * 30 / 7)
    assert summary.allowance == 2000
    assert summary.fits is True
    heavy = ci_usage.summarise(RUNS, {k: [{"started_at": "2026-10-18T06:00:00Z",
                                           "completed_at": "2026-10-18T10:00:00Z"}]
                                      for k in JOBS}, days=1)
    assert heavy.monthly_minutes == 5 * 240 * 30
    assert heavy.fits is False


def test_the_command_reads_the_api_through_gh_and_reports_the_month(monkeypatch):
    """`mothman github ci-usage --days 7`, driven end to end against a fake at
    the gh boundary that answers the two API calls the command makes."""
    import cli.github as github_cli

    calls: list[list[str]] = []

    def fake_gh(args: list[str]) -> str:
        calls.append(args)
        path = args[1]
        if path.startswith("repos/o/r/actions/runs?"):
            return json.dumps({"workflow_runs": RUNS})
        if path.startswith("repos/o/r/actions/runs/"):
            run_id = int(path.split("/")[5])
            return json.dumps({"jobs": JOBS[run_id]})
        raise AssertionError(f"unexpected gh invocation: {args}")

    monkeypatch.setattr(ci_usage, "_run_gh", fake_gh)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    result = CliRunner().invoke(github_cli.github_group, ["ci-usage", "--days", "7"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "Run test suite" in out and "Validate committed configuration" in out
    assert "21" in out and "2,000" in out
    assert "90" in out, out  # 21 minutes in 7 days scales to 90 a month
    # One runs call, then one jobs call per run.
    assert len(calls) == 1 + len(RUNS)
    assert all(a[0] == "api" for a in calls)
