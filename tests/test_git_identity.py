"""Tests for qa_tools/common/git_identity.py - the changelog feature's
attribution field (plans/publishing-and-history.md Phase 3, 2026-09-16).
Real subprocess calls against a real temp git repo, not mocked - the
whole point being to exercise the actual "git config user.email" call
and its failure mode."""
from __future__ import annotations

import subprocess

import pytest

from qa_tools.common.git_identity import MissingGitIdentityError, get_run_by


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_get_run_by_returns_the_configured_email(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "keith@example.com")
    monkeypatch.chdir(tmp_path)

    assert get_run_by() == "keith@example.com"


def test_get_run_by_raises_when_email_is_not_configured(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    # deliberately no `git config user.email` - and isolate from any real
    # global/system config that might otherwise supply one.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MissingGitIdentityError):
        get_run_by()


def test_get_run_by_raises_when_email_is_set_but_empty(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MissingGitIdentityError):
        get_run_by()
