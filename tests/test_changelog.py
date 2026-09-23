"""Tests for qa_tools/common/changelog.py - plans/publishing-and-
history.md Phase 3's changelog/activity-feed DATA logic (2026-09-16).
Uses a real temp git repo (not a mocked subprocess), same pattern as
tests/test_validate_check_lifecycle.py - the git-history-reading
mechanism (walking commits, reading each one's own diff) is exactly the
part worth testing for real."""
from __future__ import annotations

import subprocess

from qa_tools.common import changelog
from qa_tools.common.qa_results_writer import write_qa_result


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(tmp_path):
    repo = tmp_path
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit_qa_results(repo, message="qa results"):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def test_build_changelog_resolves_run_by_run_timestamp_and_commit_info(tmp_path):
    repo = _init_repo(tmp_path)
    qa_results_dir = repo / "qa_results"
    write_qa_result("agency-a", "dataset-a", "run_01", "2026-01-01T09:00:00+00:00",
                     "dataset_stats", {"arrival_record": {"run_id": "run_01"}},
                     run_by="keith@example.com", results_dir=qa_results_dir)
    _commit_qa_results(repo)
    expected_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                   capture_output=True, text=True, check=True).stdout.strip()

    events = changelog.build_changelog("agency-a", "dataset-a", qa_results_dir=qa_results_dir, repo_root=repo)

    assert len(events) == 1
    event = events[0]
    assert event["agency"] == "agency-a"
    assert event["dataset"] == "dataset-a"
    assert event["run_timestamp"] == "2026-01-01T09:00:00+00:00"
    assert event["run_by"] == "keith@example.com"
    assert event["commit_sha"] == expected_sha
    assert event["committed_at"] is not None


def test_build_changelog_keeps_separate_datasets_from_the_same_commit_apart(tmp_path):
    """The exact scenario that motivated grouping by (agency, dataset,
    run_timestamp) rather than by commit: someone QAs two datasets and
    commits both in one go. Each dataset's changelog must show only its
    own event, not the other's - even though both share a commit_sha."""
    repo = _init_repo(tmp_path)
    qa_results_dir = repo / "qa_results"
    write_qa_result("agency-a", "birth-registrations", "run_01", "2026-01-01T09:00:00+00:00",
                     "dataset_stats", {"arrival_record": {}}, run_by="keith@example.com",
                     results_dir=qa_results_dir)
    write_qa_result("agency-b", "child-protection", "cp_run_01", "2026-01-01T09:05:00+00:00",
                     "dataset_stats", {"arrival_record": {}}, run_by="colleague@example.com",
                     results_dir=qa_results_dir)
    _commit_qa_results(repo, "QA both datasets in one commit")

    bdm_events = changelog.build_changelog("agency-a", "birth-registrations",
                                            qa_results_dir=qa_results_dir, repo_root=repo)
    cp_events = changelog.build_changelog("agency-b", "child-protection",
                                           qa_results_dir=qa_results_dir, repo_root=repo)

    assert [e["run_timestamp"] for e in bdm_events] == ["2026-01-01T09:00:00+00:00"]
    assert bdm_events[0]["run_by"] == "keith@example.com"
    assert [e["run_timestamp"] for e in cp_events] == ["2026-01-01T09:05:00+00:00"]
    assert cp_events[0]["run_by"] == "colleague@example.com"
    # same commit landed both - the split is purely by dataset, not by commit
    assert bdm_events[0]["commit_sha"] == cp_events[0]["commit_sha"]


def test_build_changelog_finds_the_right_commit_across_multiple_regenerations(tmp_path):
    repo = _init_repo(tmp_path)
    qa_results_dir = repo / "qa_results"

    write_qa_result("agency-a", "dataset-a", "run_01", "2026-01-01T09:00:00+00:00",
                     "dataset_stats", {"arrival_record": {}}, run_by="keith@example.com",
                     results_dir=qa_results_dir)
    _commit_qa_results(repo, "first QA event")
    first_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                capture_output=True, text=True, check=True).stdout.strip()

    write_qa_result("agency-a", "dataset-a", "run_02", "2026-01-08T09:00:00+00:00",
                     "dataset_stats", {"arrival_record": {}}, run_by="colleague@example.com",
                     results_dir=qa_results_dir)
    _commit_qa_results(repo, "second QA event, a week later")
    second_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                                 capture_output=True, text=True, check=True).stdout.strip()

    events = changelog.build_changelog("agency-a", "dataset-a", qa_results_dir=qa_results_dir, repo_root=repo)

    assert [e["run_timestamp"] for e in events] == ["2026-01-01T09:00:00+00:00", "2026-01-08T09:00:00+00:00"]
    assert events[0]["commit_sha"] == first_sha
    assert events[0]["run_by"] == "keith@example.com"
    assert events[1]["commit_sha"] == second_sha
    assert events[1]["run_by"] == "colleague@example.com"
    # first_sha != second_sha above is the real assertion that each event
    # resolved to its own commit - committed_at isn't compared for
    # inequality here since two commits made back-to-back in a fast test
    # can legitimately land in the same wall-clock second.
    assert events[0]["committed_at"] is not None and events[1]["committed_at"] is not None
