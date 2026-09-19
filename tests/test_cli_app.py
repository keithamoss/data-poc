"""Tests for cli/app.py - the mothman root command and TUI main menu
(plans/tooling.md #1). Drives the menu functions by monkeypatching
cli.common.select/confirm (the same seam tests/test_cli_bdm.py's own
generate-synthetic-data tests already use) rather than needing a real
pty - scripts/dev/tui_screenshot.py's own real-terminal capture is what
covers genuine end-to-end interactive rendering."""
from __future__ import annotations

from click.testing import CliRunner

import cli.app as app
import cli.bdm as bdm
import cli.common as common

_runner = CliRunner()


def test_bare_mothman_with_no_real_terminal_fails_with_a_clear_message():
    """CliRunner's own stdin/stdout aren't real terminals under pytest -
    this exercises the real, unmocked require_tty() guard, not a stub."""
    result = _runner.invoke(app.cli, [])
    assert result.exit_code != 0
    assert "real interactive terminal" in result.output


def test_qa_menu_picks_the_only_dataset_and_calls_run_qa_interactive(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: "Birth Registrations")
    called = []
    monkeypatch.setattr(bdm, "run_qa_interactive", lambda: called.append(True))

    app._qa_menu()

    assert called == [True]


def test_qa_menu_back_choice_does_not_run_anything(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: None)

    def _fail_if_called():
        raise AssertionError("Back must not run the QA flow")
    monkeypatch.setattr(bdm, "run_qa_interactive", _fail_if_called)

    app._qa_menu()  # must not raise


def test_generate_menu_first_run_skips_confirmation_and_generates(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: "Birth Registrations")
    monkeypatch.setattr(bdm, "manifest_exists", lambda: False)
    generated = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: generated.append(True))

    def _fail_if_called(*a, **k):
        raise AssertionError("should not prompt when there's nothing to overwrite yet")
    monkeypatch.setattr(common, "confirm", _fail_if_called)

    app._generate_menu()

    assert generated == [True]


def test_generate_menu_existing_manifest_respects_a_declined_confirmation(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: "Birth Registrations")
    monkeypatch.setattr(bdm, "manifest_exists", lambda: True)
    monkeypatch.setattr(common, "confirm", lambda *a, **k: False)

    def _fail_if_called():
        raise AssertionError("must not regenerate when the operator declines")
    monkeypatch.setattr(bdm, "generate_synthetic_data", _fail_if_called)

    app._generate_menu()  # must not raise


def test_main_menu_loop_exits_cleanly_on_back(monkeypatch, capsys):
    monkeypatch.setattr(common, "select", lambda *a, **k: None)
    app._main_menu_loop()
    assert "Goodbye" in capsys.readouterr().out


def test_main_menu_loop_routes_qa_choice_then_exits(monkeypatch):
    calls = iter([app._MAIN_MENU_QA, None])
    monkeypatch.setattr(common, "select", lambda *a, **k: next(calls))
    routed = []
    monkeypatch.setattr(app, "_qa_menu", lambda: routed.append("qa"))

    app._main_menu_loop()

    assert routed == ["qa"]


def test_main_menu_loop_routes_generate_choice_then_exits(monkeypatch):
    calls = iter([app._MAIN_MENU_GENERATE, None])
    monkeypatch.setattr(common, "select", lambda *a, **k: next(calls))
    routed = []
    monkeypatch.setattr(app, "_generate_menu", lambda: routed.append("generate"))

    app._main_menu_loop()

    assert routed == ["generate"]
