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


def test_get_run_by_returns_a_lambda_service_identity_when_running_in_lambda(monkeypatch):
    """plans/running-thoughts.md #5 Thread B - a real Lambda invocation
    has no .git checkout at all, so this must never fall through to the
    git-config path (which would raise MissingGitIdentityError for the
    wrong reason - there's no human running it, not a missing config)."""
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "bdm-ingest-handler")
    assert get_run_by() == "aws-lambda:bdm-ingest-handler"


def test_lambda_identity_is_checked_before_ever_shelling_out_to_git(monkeypatch):
    """Real proof, not just an assertion on the return value: git config
    is never even invoked when the Lambda env var is set - a real repo
    with no user.email configured would otherwise raise, which this test
    would catch if the check order regressed."""
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "cp-ingest-handler")

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("git config should never be invoked when running in Lambda")

    monkeypatch.setattr("subprocess.run", _fail_if_called)
    assert get_run_by() == "aws-lambda:cp-ingest-handler"
