"""Which commit the history-comparing gates compare against, locally
(plans/post-build-review.md #218).

A local run used to compare against HEAD~1 whenever CI's variable was unset.
Work committed locally as several checkpoints (CLAUDE.md's rule D) then hid
an edit in an earlier checkpoint from the gate - exactly the multi-commit
hole diff_base.py closed for CI - and the push went red on it.
"""
from __future__ import annotations

import subprocess

import pytest

from qa_tools.common import diff_base


def _git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout.strip()


def _commit(repo, name: str) -> str:
    (repo / f"{name}.txt").write_text(name)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com",
         "commit", "-q", "-m", name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.delenv(diff_base.ENV_VAR, raising=False)
    monkeypatch.delenv("PRE_COMMIT", raising=False)
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    monkeypatch.setattr(diff_base, "ROOT", work)
    return origin, work


class TestALocalRunComparesAgainstWhatThePushWillBeJudgedAgainst:

    def test_two_local_commits_ahead_compares_against_the_upstream(self, repo):
        origin, work = repo
        pushed = _commit(work, "pushed")
        _git(work, "remote", "add", "origin", str(origin))
        _git(work, "push", "-q", "-u", "origin", "main")
        _commit(work, "checkpoint-1")
        _commit(work, "checkpoint-2")
        assert diff_base.diff_base() == pushed

    def test_no_upstream_falls_back_to_the_previous_commit(self, repo):
        _, work = repo
        _commit(work, "one")
        _commit(work, "two")
        assert diff_base.diff_base() == diff_base.FALLBACK

    def test_ci_and_the_pre_commit_hook_are_unchanged(self, repo, monkeypatch):
        origin, work = repo
        first = _commit(work, "one")
        _git(work, "remote", "add", "origin", str(origin))
        _git(work, "push", "-q", "-u", "origin", "main")
        _commit(work, "two")
        monkeypatch.setenv(diff_base.ENV_VAR, first)
        assert diff_base.diff_base() == first
        monkeypatch.delenv(diff_base.ENV_VAR)
        monkeypatch.setenv("PRE_COMMIT", "1")
        assert diff_base.diff_base() == "HEAD"
