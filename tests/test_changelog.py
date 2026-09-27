"""Tests for qa_tools/common/changelog.py - "who published what, when".

IT USED TO DRIVE A REAL TEMP GIT REPO, because the mechanism worth
testing was the git-history walk: a run's `run_by`/`run_timestamp` came
from committed file content, and its `commit_sha`/`committed_at` had to
be resolved by walking the branch those files actually landed on.

REQ-PIPE-089 removed that walk, and the reason is worth keeping rather
than inferring from the diff. Results are not committed any longer, so
there is no commit to be rebased and no gap between running QA and
publishing it - a result is visible the moment its run completes.
`completed_at` IS the "when did this land" answer, recorded by the run
itself, and nothing downstream can rewrite it.

WHAT WAS LOST, so it is a choice rather than a discovery: `commit_sha`
is gone from every event, and the feed can no longer distinguish "QA'd
on Monday, published on Thursday". That gap was an artefact of results
travelling through git.

THE CLAIM THAT SURVIVES, and it is the one that mattered: grouping is
by (agency, dataset, run_timestamp) rather than by commit, so two
datasets QA'd in one go stay two events. The scenario that motivated it
is kept below, with the commit removed from it.
"""
from __future__ import annotations

import pytest

from qa_tools.common import changelog
from qa_tools.common.qa_results_writer import finish_run, open_run, write_qa_result


@pytest.fixture(autouse=True)
def history(clean_qa_history):
    """An empty QA history per test - what `tmp_path` used to give.

    IT ALSO TOOK `tmp_path` UNTIL REQ-PIPE-089'S LAST PHASE, and the
    reason is worth keeping as a caution rather than deleting with the
    parameter: `write_qa_result` wrote FILES as well as rows, and its
    default results directory was the real committed one, so two of
    these tests wrote `qa_results/agency-a/` into project history before
    anybody noticed. The session guard in conftest covers the delivery
    log, the processing log, observations and filings, and never covered
    qa_results/. There are no files to misdirect now; a test that starts
    writing somewhere real again will have the same lack of a guard.
    """
    return clean_qa_history


def _event(agency, collection, run_id, when, run_by):
    """One recorded QA event, written and completed the real way."""
    open_run(agency, collection, run_id, when, run_by)
    write_qa_result(agency, collection, run_id, when, "dataset_stats",
                     {"arrival_record": {"run_id": run_id}}, run_by=run_by)
    finish_run(run_id)


def test_build_changelog_resolves_run_by_and_run_timestamp():
    _event("agency-a", "dataset-a", "run_01", "2026-01-01T09:00:00+00:00",
           "keith@example.com")

    events = changelog.build_changelog("agency-a", "dataset-a")

    assert len(events) == 1
    event = events[0]
    assert event["agency"] == "agency-a"
    assert event["dataset"] == "dataset-a"
    assert event["run_timestamp"] == "2026-01-01T09:00:00+00:00"
    assert event["run_by"] == "keith@example.com"
    assert event["committed_at"] is not None, \
        "an event with no landing time cannot be placed on a feed"


def test_build_changelog_keeps_separate_datasets_apart():
    """The exact scenario that motivated grouping by (agency, dataset,
    run_timestamp) rather than by commit: someone QAs two datasets in
    one go. Each dataset's changelog must show only its own event.

    The commit that used to carry both is gone; the grouping rule it
    was protecting against is not, because two runs can still be
    minutes apart in one sitting.
    """
    _event("agency-a", "birth-registrations", "run_01", "2026-01-01T09:00:00+00:00",
           "keith@example.com")
    _event("agency-b", "child-protection", "cp_run_01", "2026-01-01T09:05:00+00:00",
           "colleague@example.com")

    bdm_events = changelog.build_changelog("agency-a", "birth-registrations")
    cp_events = changelog.build_changelog("agency-b", "child-protection")

    assert [e["run_timestamp"] for e in bdm_events] == ["2026-01-01T09:00:00+00:00"]
    assert bdm_events[0]["run_by"] == "keith@example.com"
    assert [e["run_timestamp"] for e in cp_events] == ["2026-01-01T09:05:00+00:00"]
    assert cp_events[0]["run_by"] == "colleague@example.com"


def test_build_changelog_orders_events_across_several_runs():
    _event("agency-a", "dataset-a", "run_01", "2026-01-01T09:00:00+00:00",
           "keith@example.com")
    _event("agency-a", "dataset-a", "run_02", "2026-01-08T09:00:00+00:00",
           "colleague@example.com")

    events = changelog.build_changelog("agency-a", "dataset-a")

    assert [e["run_timestamp"] for e in events] == [
        "2026-01-01T09:00:00+00:00", "2026-01-08T09:00:00+00:00"]
    assert [e["run_by"] for e in events] == [
        "keith@example.com", "colleague@example.com"]
    assert all(e["committed_at"] is not None for e in events)


def test_an_unfinished_run_is_not_on_the_feed():
    """A run that never completed has not published anything, so it has
    no place on a "who published what" feed - which is criterion 13
    holding at one more reader rather than a special case here."""
    open_run("agency-a", "dataset-a", "run_01", "2026-01-01T09:00:00+00:00",
             "keith@example.com")
    write_qa_result("agency-a", "dataset-a", "run_01", "2026-01-01T09:00:00+00:00",
                     "dataset_stats", {"arrival_record": {}},
                     run_by="keith@example.com")

    assert changelog.build_changelog("agency-a", "dataset-a") == []


def test_the_commit_walk_is_gone():
    """RETIRED MECHANISM, asserted rather than assumed.

    The walk was a real performance hazard, documented at length in
    CLAUDE.md: one `git show` per commit touching the subtree, diffing
    each commit's entire changed tree - 225 MB and 5.3 M lines of diff
    output for one dataset's twelve commits, growing with both commit
    count and diff size. Two fixes got it to 0.7s. A column needs none,
    and this is here so nobody reintroduces the walk without noticing
    they are undoing that.
    """
    source = open(changelog.__file__).read()
    for name in ("git log", "git show", "subprocess", "commit_sha"):
        assert name not in source.split('"""', 2)[2], \
            f"{name!r} is back in changelog.py's code"
