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

import re
import subprocess

import pytest
from click.testing import CliRunner

import cli.check as check_cli

_runner = CliRunner()


class _Result:
    def __init__(self, returncode: int):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


@pytest.fixture
def record(monkeypatch):
    """Records every gate invoked, and lets a test choose exit codes."""
    calls: list[list[str]] = []
    codes: dict[str, int] = {}

    def fake_run(argv, cwd=None, env=None, **_captured):
        calls.append(argv)
        return _Result(codes.get(argv[0], 0))

    monkeypatch.setattr(check_cli.subprocess, "run", fake_run)
    monkeypatch.setattr(check_cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    # The tree is read with git; a gate run here records gates, not git.
    monkeypatch.setattr(check_cli, "_tree_state", lambda: "HEAD abc1234 (clean)")
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
    assert calls[-1][:3] == ["uv", "run", "pytest"]


def test_no_pytest_skips_only_the_python_suite(record):
    calls, _ = record
    result = _runner.invoke(check_cli.check_command, ["--no-pytest"])
    assert result.exit_code == 0, result.output
    assert not any(c[:3] == ["uv", "run", "pytest"] for c in calls)
    assert ["npm", "test", "--silent"] in calls
    assert len(calls) == len(check_cli._GATES) - 1


def test_the_cheap_gate_checks_the_plans_index(record):
    """running-thoughts #81: CLAUDE.md's commit rule B re-runs only
    `--no-pytest` after a plans edit, and a stale plans/INDEX.md is the
    thing a plans edit most often breaks - it was checked only inside
    pytest, so the cheap gate passed over it."""
    calls, _ = record
    _runner.invoke(check_cli.check_command, ["--no-pytest"])
    assert ["uv", "run", "mothman", "dashboard", "plans-index", "--check"] in calls


def test_a_missing_toolchain_is_reported_as_not_run_rather_than_passed(monkeypatch):
    """A fresh container has no node_modules until `npm ci` is run. The
    dangerous outcome is not the failure, it is a green summary that
    quietly covered one suite fewer than it claims to."""
    monkeypatch.setattr(check_cli.subprocess, "run",
                        lambda argv, cwd=None, env=None: _Result(0))
    monkeypatch.setattr(check_cli.shutil, "which",
                        lambda name: None if name == "npm" else f"/usr/bin/{name}")
    monkeypatch.setattr(check_cli, "_tree_state", lambda: "HEAD abc1234 (clean)")
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


class TestTheDocsGate:
    """REQ-TEST-253 (Keith, 2026-10-16): a documentation-only change is
    gated by the checks it can affect, in seconds."""

    DOCS = {"plans", "requirements", "sprints", "changelog", "feedback", "scenarios",
            "scenario map", "premise", "yamllint", "provisional"}

    @pytest.fixture
    def only_docs_changed(self, monkeypatch):
        monkeypatch.setattr(check_cli, "_changed_paths",
                            lambda: ["plans/morning-reports.md", "requirements.yaml"])

    def test_it_runs_exactly_the_docs_gates(self, record, only_docs_changed):
        calls, _ = record
        result = _runner.invoke(check_cli.check_command, ["--docs"])
        assert result.exit_code == 0, result.output
        ran = {label for label, argv, *_ in check_cli._GATES if argv in calls}
        assert ran == self.DOCS
        assert len(calls) == len(self.DOCS)

    def test_it_refuses_a_change_outside_the_docs(self, record, monkeypatch):
        calls, _ = record
        monkeypatch.setattr(check_cli, "_changed_paths",
                            lambda: ["plans/x.md", "cli/check.py", "contract/calendar.yaml"])
        result = _runner.invoke(check_cli.check_command, ["--docs"])
        assert result.exit_code != 0
        assert "cli/check.py" in result.output and "contract/calendar.yaml" in result.output
        assert "--no-pytest" in result.output
        assert calls == []

    def test_it_says_what_it_ran(self, record, only_docs_changed):
        result = _runner.invoke(check_cli.check_command, ["--docs"])
        assert "documentation" in result.output

    def test_a_failing_docs_gate_fails_the_command_and_shows_its_output(
            self, monkeypatch, only_docs_changed):
        """Run side by side, a failure must still be shown in full."""
        class Out:
            def __init__(self, code, text):
                self.returncode, self.stdout, self.stderr = code, text, ""

        def fake_run(argv, cwd=None, env=None, **_):
            if "plans-index" in argv:
                return Out(1, "plans/INDEX.md is out of date\n")
            return Out(0, "")
        monkeypatch.setattr(check_cli.subprocess, "run", fake_run)
        monkeypatch.setattr(check_cli.shutil, "which", lambda name: f"/usr/bin/{name}")
        result = _runner.invoke(check_cli.check_command, ["--docs"])
        assert result.exit_code != 0
        assert "plans/INDEX.md is out of date" in result.output
        assert "1 gate(s) failed: plans" in result.output

    def test_it_cannot_be_combined_with_only(self, record, only_docs_changed):
        result = _runner.invoke(check_cli.check_command, ["--docs", "--only", "ruff"])
        assert result.exit_code != 0


def test_every_gate_reports_its_own_time(record):
    """REQ-TEST-253 criterion 6: so a slow gate is visible the day it
    becomes slow."""
    result = _runner.invoke(check_cli.check_command, ["--only", "ruff"])
    assert re.search(r"ruff.*\d+(\.\d)?s", result.output), result.output


def test_yamllint_lints_only_what_git_tracks():
    """REQ-TEST-253 criterion 4: 169 of 206 files it linted were gitignored
    browser snapshots in .playwright-mcp/."""
    import yaml as _yaml
    from pathlib import Path
    cfg = _yaml.safe_load((Path(__file__).resolve().parent.parent / ".yamllint").read_text())
    assert ".gitignore" in (cfg.get("ignore-from-file") or [])


class TestTheProvisionalGate:
    """REQ-TEST-374: unanswered `PROVISIONAL` choices in built requirements
    are a warning, in the docs tier, never a failure."""

    def _gate(self):
        return next(g for g in check_cli._GATES if g[0] == "provisional")

    def test_it_is_a_gate_that_can_warn(self):
        label, argv, _why, can_warn = self._gate()
        assert can_warn
        assert argv[-1] == "validate-provisional"

    def test_it_is_in_the_docs_tier(self):
        assert "provisional" in check_cli._DOCS_GATES

    def test_its_baseline_may_change_under_docs(self):
        assert check_cli._outside_docs(["provisional-baseline.yaml"]) == []

    def test_a_warning_from_it_passes_the_command(self, record):
        calls, codes = record
        codes["uv"] = check_cli.WARNING_EXIT
        result = _runner.invoke(check_cli.check_command, ["--only", "provisional"])
        assert result.exit_code == 0, result.output
        assert "passed, with a warning" in result.output


class TestTheFullGateIsTheWholeSuitesRecord:
    """REQ-TEST-375 criteria 9 and 10: push CI runs only the critical set, so
    the full gate enforces the coverage floor and prints the line a commit
    message carries."""

    def test_the_python_suite_runs_with_coverage_and_its_floor(self, record):
        calls, _ = record
        result = _runner.invoke(check_cli.check_command, [])
        assert result.exit_code == 0, result.output
        pytest_argv = calls[-1]
        for package in check_cli.COVERAGE_PACKAGES:
            assert f"--cov={package}" in pytest_argv
        # The floor is pyproject's, so nothing may override it to zero here.
        assert not any(a.startswith("--cov-fail-under") for a in pytest_argv)
        assert check_cli._fail_under() is not None

    def test_it_prints_one_paste_ready_result_line(self, record):
        result = _runner.invoke(check_cli.check_command, [])
        assert "Paste into the commit message:" in result.output
        [line] = [ln for ln in result.output.splitlines()
                  if ln.startswith("Full gate (mothman check):")]
        assert "every gate passed" in line

    def test_a_partial_gate_prints_no_result_line(self, record):
        result = _runner.invoke(check_cli.check_command, ["--no-pytest"])
        assert "Full gate (mothman check):" not in result.output

    def test_the_line_reads_its_counts_from_pytests_own_report(self, tmp_path):
        junit = tmp_path / "junit.xml"
        junit.write_text('<testsuites><testsuite tests="10" failures="1" errors="1" '
                         'skipped="2"/></testsuites>')
        assert check_cli._pytest_counts(junit) == (6, 2, 2)
        assert check_cli._pytest_counts(tmp_path / "absent.xml") is None

    def test_the_line_names_counts_coverage_time_and_tree(self):
        line = check_cli.result_line(tree="HEAD abc1234 (clean)", tree_after="HEAD abc1234 (clean)",
                                     counts=(6240, 0, 0), coverage=94.123, floor=92,
                                     elapsed=1357, failed_gates=[])
        assert line == ("Full gate (mothman check): every gate passed; 6240 passed, 0 failed, "
                        "0 skipped; coverage 94.12% (floor 92%); 22m37s; HEAD abc1234 (clean)")

    def test_it_never_claims_more_than_ran(self):
        line = check_cli.result_line(tree="tree a", tree_after="tree b", counts=None,
                                     coverage=None, floor=92, elapsed=5,
                                     failed_gates=["pytest"], not_run=["npm test"])
        assert "FAILED: pytest" in line and "not run (no toolchain): npm test" in line
        assert "pytest wrote no report" in line and "coverage not measured" in line
        assert "TREE CHANGED DURING THE RUN" in line

    def test_the_tree_it_names_is_the_one_a_commit_would_have(self, tmp_path, monkeypatch):
        """Through a scratch index, in a real repository: clean names HEAD,
        dirty names the tree id a commit of everything would have, and the
        real index is left alone."""
        import subprocess

        def git(*args, strip=True):
            out = subprocess.check_output(["git", *args], cwd=tmp_path, text=True)
            return out.strip() if strip else out

        git("init", "-q")
        git("config", "user.email", "t@example.invalid")
        git("config", "user.name", "t")
        (tmp_path / "a.txt").write_text("a\n")
        git("add", "a.txt")
        git("commit", "-qm", "one")
        monkeypatch.setattr(check_cli, "ROOT", tmp_path)
        assert check_cli._tree_state() == f"HEAD {git('rev-parse', '--short', 'HEAD')} (clean)"
        (tmp_path / "a.txt").write_text("changed\n")
        (tmp_path / "b.txt").write_text("new\n")
        state = check_cli._tree_state()
        assert git("status", "--porcelain", strip=False) == " M a.txt\n?? b.txt\n", \
            "the real index was touched"
        git("add", "-A")
        assert state.startswith(f"tree {git('write-tree')[:10]} (HEAD ")
        assert "+ 2 uncommitted paths" in state

    def test_a_tree_git_cannot_read_is_said_rather_than_crashing_the_gate(self, tmp_path,
                                                                          monkeypatch):
        monkeypatch.setattr(check_cli, "ROOT", tmp_path)  # not a repository
        assert check_cli._tree_state().startswith("tree unknown")
