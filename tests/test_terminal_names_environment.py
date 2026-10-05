"""The terminal says which environment it is acting against (REQ-TEST-114)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import questionary
from click.testing import CliRunner

from cli import common

ROOT = Path(__file__).resolve().parent.parent


class TestTheStatement:
    """Criteria 5, 6 and 7."""

    def test_a_non_publishing_environment_says_not_production(self, monkeypatch):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        assert common.environment_statement() == \
            "Environment: Claude Code sandbox (not production)"

    def test_production_says_its_label_and_nothing_else(self, monkeypatch):
        from qa_tools.common import environments

        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "production")
        label = environments.get("production").label
        assert common.environment_statement() == f"Environment: {label}"

    def test_the_label_comes_from_the_configuration_not_the_variable(self, monkeypatch):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "ci")
        assert common.environment_statement() == \
            "Environment: Continuous integration (not production)"

    def test_no_environment_states_nothing(self, monkeypatch):
        monkeypatch.delenv("MOTHMAN_ENVIRONMENT", raising=False)
        assert common.environment_statement() is None


class TestTheToolbar:
    """Criterion 1 - every questionary prompt type the TUI uses."""

    @pytest.mark.parametrize("make", [
        lambda: questionary.select("m", choices=["a", "b"]),
        lambda: questionary.text("m"),
        lambda: questionary.confirm("m"),
        lambda: questionary.path("m"),
    ])
    def test_every_prompt_carries_it(self, monkeypatch, make):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        question = common._with_environment_toolbar(make())
        last = question.application.layout.container.children[-1]
        text = "".join(fragment for _, fragment in last.content.content.text)
        assert "Environment: Claude Code sandbox (not production)" in text


class TestAConfirmationNamesTheEnvironment:
    """Criterion 4."""

    def test_the_ordinary_confirmation(self, monkeypatch):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        asked = []
        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        monkeypatch.setattr(common, "_ask", lambda q: asked.append(q) or True)
        monkeypatch.setattr(questionary, "confirm",
                            lambda message, **kw: message)
        assert common.confirm("Record promote?", yes=False)
        assert asked == ["[Claude Code sandbox (not production)] Record promote?"]

    def test_the_typed_confirmation_asks_for_the_id(self, monkeypatch):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "production")
        prompts = []
        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        monkeypatch.setattr(common, "_ask_text", lambda m: prompts.append(m) or "production")
        assert common.confirm_change("Record promote?", yes=True)
        assert "Type production to confirm" in prompts[0]


class TestAOneOffCommand:
    """Criteria 2 and 3."""

    def _run(self, *args):
        return subprocess.run([sys.executable, "-m", "cli.app", *args], cwd=ROOT,
                              capture_output=True, text=True, env={**os.environ},
                              timeout=120)

    def test_a_command_that_connects_states_it_on_standard_error(self):
        result = self._run("supply", "failures")
        assert result.returncode == 0, result.stderr
        assert result.stderr.splitlines()[0] == "Environment: Test suite (not production)"
        assert "Environment:" not in result.stdout

    def test_a_command_that_never_connects_says_nothing(self):
        result = self._run("env", "list")
        assert "Environment:" not in result.stderr


class TestTheTuiRefusesWithoutAnEnvironment:
    """Criterion 8."""

    def test_no_menu_without_one(self, monkeypatch):
        from cli import app

        monkeypatch.delenv("MOTHMAN_ENVIRONMENT", raising=False)
        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        shown = []
        monkeypatch.setattr(app, "_main_menu_loop", lambda: shown.append(True))
        result = CliRunner().invoke(app.cli, [])
        assert result.exit_code != 0 and "MOTHMAN_ENVIRONMENT" in result.output
        assert not shown
