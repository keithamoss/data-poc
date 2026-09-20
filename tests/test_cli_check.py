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

    def fake_run(argv, cwd=None):
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
                        lambda argv, cwd=None: _Result(0))
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
