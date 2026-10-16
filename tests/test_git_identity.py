"""Tests for qa_tools/common/git_identity.py - the changelog feature's
attribution field (plans/publishing-and-history.md Phase 3, 2026-09-16).
Real subprocess calls against a real temp git repo, not mocked - the
whole point being to exercise the actual "git config user.email" call
and its failure mode."""
from __future__ import annotations

import subprocess

import pytest

from qa_tools.common import git_identity
from qa_tools.common.git_identity import MissingGitIdentityError, get_run_by


#: THE SERVICE VARIABLES ARE CLEARED FOR EVERY TEST IN THIS MODULE, and it
#: is not tidiness - it is a real CI-only failure, 2026-09-28. `get_run_by()`
#: checks for a Lambda and then for a GitHub Actions runner BEFORE it shells
#: out to git, deliberately, so the three tests that assert the LOCAL git
#: path passed on a laptop and failed on the runner, where GITHUB_ACTIONS is
#: set by the runner itself. The tests were asserting about an environment
#: they did not control.
#:
#: Cleared here rather than in each of them, because the next test written
#: about the local path would be written on a laptop too - and would go red
#: only in CI, which is the slowest place to find anything.
@pytest.fixture(autouse=True)
def _no_service_runtime(monkeypatch):
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


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


class TestAGitHubActionsRunnerAttributesToTheWorkflow:
    """REQ-PIPE-105's own CI fallout, and the same reasoning the Lambda
    branch already carries.

    An Actions runner has a real `.git` checkout and no `git config
    user.email`, so the local path failed there - for a reason that has
    nothing to do with a person forgetting to configure git, because there
    is no person. Found by the runner going red, not by reading.
    """

    def test_it_names_the_repository_and_the_workflow(self, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("GITHUB_REPOSITORY", "keithamoss/data-poc")
        monkeypatch.setenv("GITHUB_WORKFLOW", "Run test suite")
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        assert git_identity.get_run_by() == \
            "github-actions:keithamoss/data-poc@Run test suite"

    def test_it_never_shells_out_to_git_there(self, monkeypatch):
        """The order is load-bearing rather than tidy: a runner DOES have a
        checkout, so a developer's global config leaking into the image
        would otherwise attribute a CI run to whoever was configured."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
        monkeypatch.setenv("GITHUB_WORKFLOW", "w")
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

        def _never(*a, **k):
            raise AssertionError("shelled out to git on an Actions runner")

        monkeypatch.setattr(git_identity.subprocess, "run", _never)
        assert git_identity.get_run_by().startswith("github-actions:")

    def test_a_lambda_still_wins_over_an_actions_variable(self, monkeypatch):
        """Both can be set at once in a test environment, and only one of
        them can be true of a real runtime. Lambda first, because that is
        the narrower claim."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "cp-ingest-handler")
        assert git_identity.get_run_by() == "aws-lambda:cp-ingest-handler"

    def test_a_partial_actions_environment_still_attributes(self, monkeypatch):
        """It does not raise. A real CI run taken down over a missing label
        is worse than an attribution that says "github-actions" and names
        what it could - and there is still no human being invented."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        monkeypatch.delenv("GITHUB_WORKFLOW", raising=False)
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        got = git_identity.get_run_by()
        assert got.startswith("github-actions:")
        assert "unknown-repository" in got

    def test_a_developers_machine_is_unaffected(self, monkeypatch):
        """GITHUB_ACTIONS is set by the runner and by nothing else, so a
        local run still goes to the git identity - and still raises where
        that is missing, which is the rule this must not weaken."""
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        monkeypatch.setattr(git_identity.subprocess, "run",
                             lambda *a, **k: _Result(0, "keith@example.gov.au\n"))
        assert git_identity.get_run_by() == "keith@example.gov.au"


class _Result:
    def __init__(self, returncode, stdout):
        self.returncode, self.stdout = returncode, stdout
