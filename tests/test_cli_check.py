"""Tests for cli/check.py - `mothman check` (2026-09-20).

Keith's ask was to make `npm test` something that gets run by default
rather than something to remember, and to do it WITHOUT a maintained
list of which files trigger which suite ("I don't want to maintain file
lists and so forth. That's messy"). So what actually needs testing here
is not any one gate - each already has its own suite - but the
properties that make a single command a working answer to that: every
gate runs even when an earlier one fails, the JS suite really is one of
them, and a failure is reported rather than swallowed.

The real subprocesses are monkeypatched out. Running the true gates
here would mean a test that runs the whole test suite, which cannot
work, and it would test the gates rather than this module."""
from __future__ import annotations

import subprocess

import pytest
from click.testing import CliRunner

import cli.check as check_cli

_runner = CliRunner()


class _Result:
    def __init__(self, returncode: int):
        self.returncode = returncode


@pytest.fixture
def record(monkeypatch):
    """Records every gate invoked, and lets a test choose exit codes."""
    calls: list[list[str]] = []
    codes: dict[str, int] = {}

    def fake_run(argv, cwd=None, env=None):
        calls.append(argv)
        return _Result(codes.get(argv[0], 0))

    monkeypatch.setattr(check_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(check_cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    return calls, codes


def test_the_js_suite_is_one_of_the_gates(record):
    """The whole point of the command. If `npm test` is not in here,
    it is back to being a separate thing to remember."""
    calls, _ = record
    result = _runner.invoke(check_cli.check_command, [])
    assert result.exit_code == 0, result.output
    assert ["npm", "test", "--silent"] in calls


def test_every_gate_runs_even_after_one_fails(record):
    """Fixing four things you were told about at once is one pass;
    finding them one command at a time is four."""
    calls, codes = record
    codes["uv"] = 1
    result = _runner.invoke(check_cli.check_command, [])
    assert result.exit_code != 0
    assert ["npm", "test", "--silent"] in calls, \
        "a failing Python gate must not stop the JS suite from running"
    assert len(calls) == len(check_cli._GATES)


def test_a_failing_gate_is_named_not_just_counted(record):
    _, codes = record
    codes["npm"] = 1
    result = _runner.invoke(check_cli.check_command, [])
    assert result.exit_code != 0
    assert "npm test" in result.output


def test_the_python_suite_goes_last(record):
    """Cheapest-first, so the fast gates report while the slow one is
    still ahead of you."""
    calls, _ = record
    _runner.invoke(check_cli.check_command, [])
    assert calls[-1] == ["uv", "run", "pytest"]


def test_no_pytest_skips_only_the_python_suite(record):
    calls, _ = record
    result = _runner.invoke(check_cli.check_command, ["--no-pytest"])
    assert result.exit_code == 0, result.output
    assert ["uv", "run", "pytest"] not in calls
    assert ["npm", "test", "--silent"] in calls
    assert len(calls) == len(check_cli._GATES) - 1


def test_a_missing_toolchain_is_reported_as_not_run_rather_than_passed(monkeypatch):
    """A fresh container has no node_modules until `npm ci` is run. The
    dangerous outcome is not the failure, it is a green summary that
    quietly covered one suite fewer than it claims to."""
    monkeypatch.setattr(check_cli.subprocess, "run",
                        lambda argv, cwd=None, env=None: _Result(0))
    monkeypatch.setattr(check_cli.shutil, "which",
                        lambda name: None if name == "npm" else f"/usr/bin/{name}")
    result = _runner.invoke(check_cli.check_command, [])
    assert "not installed" in result.output
    # Rich wraps at the terminal width, so match on a short fragment
    # rather than the whole sentence - and assert the contradiction that
    # the first version of this really printed, "Incomplete..." followed
    # immediately by "Every gate passed."
    assert "Incomplete" in result.output
    assert "Every gate passed" not in result.output


def test_it_really_is_wired_into_the_root_command():
    """`mothman check` has to be reachable as a real subcommand - a
    command nobody can invoke is not a convention."""
    from cli.app import cli
    assert "check" in cli.commands


def test_real_subprocess_module_is_used(monkeypatch):
    """Guards the monkeypatch targets above: if this module stopped
    calling subprocess.run directly, every test here would pass while
    testing nothing."""
    assert check_cli.subprocess is subprocess


# --- post-build-review #23 -------------------------------------------
#
# `mothman check` had exactly three outcomes - passed / not installed /
# FAILED - all derived from a return code. The low-runway warning
# printed eight gates above the table, the schedule gate returned 0, the
# row read green `passed` and the closing line said "Every gate passed."
#
# The critic attributed that to scroll distance. That is the smaller
# half: the structural half is that this module had NO WARNING STATE TO
# RENDER, so a gate could not report one even if it wanted to.
#
# The constraint the build had to respect (Keith, 2026-09-25) is that a
# warning must NOT change the exit code. REQ-PIPE-053's own reasoning is
# that a non-fatal warning which fails a build gets disabled, "and then
# it is not there for the one that mattered".


class TestAGateCanSayPassedWithSomethingToKnow:
    def test_a_warning_shows_as_its_own_outcome_not_as_passed(self, record):
        calls, codes = record
        codes["uv"] = check_cli.WARNING_EXIT
        result = _runner.invoke(check_cli.check_command, ["--only", "schedule"])
        assert "warning" in result.output.lower()
        assert "Every gate passed" not in result.output

    def test_a_warning_does_not_fail_the_command(self, record):
        """The whole point. A warning that fails a build gets turned
        off, and then it is not there for the one that mattered."""
        calls, codes = record
        codes["uv"] = check_cli.WARNING_EXIT
        result = _runner.invoke(check_cli.check_command, ["--only", "schedule"])
        assert result.exit_code == 0, result.output

    def test_the_sentinel_is_only_read_from_gates_that_opted_in(self, record):
        """A gate that has no warning state must never have a real
        failure re-read as one. The sentinel is interpreted per gate,
        not globally, so a collision cannot turn red into yellow - the
        false-green direction."""
        calls, codes = record
        codes["npm"] = check_cli.WARNING_EXIT
        result = _runner.invoke(check_cli.check_command, ["--only", "npm test"])
        assert result.exit_code != 0
        assert "FAILED" in result.output

    def test_the_gate_is_told_it_may_report_one(self, monkeypatch):
        """A gate cannot emit the sentinel unprompted - CI runs the same
        command directly as its own step, and a non-zero exit there is a
        failed step. So the runner opts in, and CI simply does not."""
        seen = {}

        def fake_run(argv, cwd=None, env=None):
            seen[argv[0]] = (env or {}).get(check_cli.WARNING_EXIT_VAR)
            return _Result(0)

        monkeypatch.setattr(check_cli.subprocess, "run", fake_run)
        monkeypatch.setattr(check_cli.shutil, "which", lambda name: f"/usr/bin/{name}")
        _runner.invoke(check_cli.check_command, ["--only", "schedule"])
        assert seen["uv"] == str(check_cli.WARNING_EXIT)

    def test_a_gate_without_a_warning_state_is_not_told(self, monkeypatch):
        """The other half of the opt-in: npm has no warning state, so
        it is never handed the variable and can never emit the
        sentinel in the first place."""
        seen = {}

        def fake_run(argv, cwd=None, env=None):
            seen[argv[0]] = env
            return _Result(0)

        monkeypatch.setattr(check_cli.subprocess, "run", fake_run)
        monkeypatch.setattr(check_cli.shutil, "which", lambda name: f"/usr/bin/{name}")
        _runner.invoke(check_cli.check_command, ["--only", "npm test"])
        assert seen["npm"] is None

    def test_the_variable_is_not_left_in_this_process(self, monkeypatch):
        """It changes a gate's exit code, so leaking it into the rest of
        the session would make an unrelated later run report a warning
        as a failure. Handed to the child only, never exported here."""
        import os

        monkeypatch.setattr(check_cli.subprocess, "run",
                             lambda argv, cwd=None, env=None: _Result(0))
        monkeypatch.setattr(check_cli.shutil, "which", lambda name: f"/usr/bin/{name}")
        _runner.invoke(check_cli.check_command, ["--only", "schedule"])
        assert check_cli.WARNING_EXIT_VAR not in os.environ
