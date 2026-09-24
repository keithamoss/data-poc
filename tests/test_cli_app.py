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
import cli.cp as cp

_runner = CliRunner()


def test_bare_mothman_with_no_real_terminal_fails_with_a_clear_message():
    """CliRunner's own stdin/stdout aren't real terminals under pytest -
    this exercises the real, unmocked require_tty() guard, not a stub."""
    result = _runner.invoke(app.cli, [])
    assert result.exit_code != 0
    assert "real interactive terminal" in result.output


def test_qa_menu_picks_bdm_and_calls_its_run_qa_interactive(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: app._DATASET_BDM)
    called = []
    monkeypatch.setattr(bdm, "run_qa_interactive", lambda: called.append("bdm"))
    monkeypatch.setattr(cp, "run_qa_interactive", lambda: called.append("cp"))

    app._qa_menu()

    assert called == ["bdm"]


def test_qa_menu_picks_cp_and_calls_its_run_qa_interactive(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: app._DATASET_CP)
    called = []
    monkeypatch.setattr(bdm, "run_qa_interactive", lambda: called.append("bdm"))
    monkeypatch.setattr(cp, "run_qa_interactive", lambda: called.append("cp"))

    app._qa_menu()

    assert called == ["cp"]


def test_qa_menu_back_choice_does_not_run_anything(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: None)

    def _fail_if_called():
        raise AssertionError("Back must not run the QA flow")
    monkeypatch.setattr(bdm, "run_qa_interactive", _fail_if_called)
    monkeypatch.setattr(cp, "run_qa_interactive", _fail_if_called)

    app._qa_menu()  # must not raise


def test_generate_menu_first_run_skips_confirmation_and_generates(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: app._DATASET_BDM)
    monkeypatch.setattr(bdm, "manifest_exists", lambda: False)
    generated = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: generated.append(True))

    def _fail_if_called(*a, **k):
        raise AssertionError("should not prompt when there's nothing to overwrite yet")
    monkeypatch.setattr(common, "confirm", _fail_if_called)

    app._generate_menu()

    assert generated == [True]


def test_generate_menu_existing_manifest_respects_a_declined_confirmation(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: app._DATASET_BDM)
    monkeypatch.setattr(bdm, "manifest_exists", lambda: True)
    monkeypatch.setattr(common, "confirm", lambda *a, **k: False)

    def _fail_if_called():
        raise AssertionError("must not regenerate when the operator declines")
    monkeypatch.setattr(bdm, "generate_synthetic_data", _fail_if_called)

    app._generate_menu()  # must not raise


def test_generate_menu_picks_cp_and_generates_via_the_cp_module(monkeypatch):
    monkeypatch.setattr(common, "select", lambda *a, **k: app._DATASET_CP)
    monkeypatch.setattr(cp, "manifest_exists", lambda: False)
    generated = []
    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: generated.append(True))
    monkeypatch.setattr(cp, "raw_dir", lambda: "/fake/cp_raw")

    def _fail_if_called(*a, **k):
        raise AssertionError("should not prompt when there's nothing to overwrite yet")
    monkeypatch.setattr(common, "confirm", _fail_if_called)

    app._generate_menu()

    assert generated == [True]


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


class TestOneNounPerThing:
    """post-build-review #31, Keith's option (c), 2026-09-24.

    `--dataset` meant two different things across the CLI: a
    `click.Choice` of the collection shorthands `bdm`/`cp` in
    `pipeline run` and most of `debug`, and a real dataset id in
    `schedule show` and `debug changelog`. One flag name, two
    vocabularies, and `mothman supply` was about to have to pick a side.

    Both shorthands map one-to-one onto a real collection -
    `bdm` -> civil-registration, `cp` -> child-protection - so the
    older sites had the wrong noun, not the newer ones. Keith chose to
    reconcile it once, now, while there are six command groups and one
    user, against his own earlier reasoning that renames are how a CLI
    surface rots: that is about REPEATED renames, and this is one
    corrective one before anything else depends on it.

    A tree walk rather than a list of known call sites, so a future
    command cannot reintroduce the fork somewhere nobody thought to
    look.
    """

    SHORTHANDS = {"bdm", "cp"}

    def _options(self):
        from click import Choice, Group

        from cli.app import cli

        def walk(command, path):
            if isinstance(command, Group):
                for name, sub in command.commands.items():
                    yield from walk(sub, f"{path} {name}".strip())
                return
            for param in command.params:
                choices = set(param.type.choices) if isinstance(param.type, Choice) else set()
                for opt in param.opts:
                    yield path, opt, choices

        yield from walk(cli, "")

    def test_no_command_calls_a_collection_shorthand_a_dataset(self):
        offenders = [f"mothman {path} {opt}" for path, opt, choices in self._options()
                     if opt == "--dataset" and self.SHORTHANDS & choices]
        assert not offenders, (
            "these take a collection shorthand under a flag named --dataset, which means "
            f"something else elsewhere in the same CLI: {offenders}")

    def test_the_shorthands_live_under_one_flag_name(self):
        names = {opt for _path, opt, choices in self._options()
                 if self.SHORTHANDS & choices and opt.startswith("--")}
        assert names <= {"--collection"}, (
            f"the collection shorthands are spelled under more than one flag name: {sorted(names)}")

    def test_dataset_still_exists_for_things_that_really_are_datasets(self):
        """The reconciliation must not delete the correct usage along
        with the incorrect one."""
        dataset_flags = [path for path, opt, _c in self._options() if opt == "--dataset"]
        assert "schedule show" in dataset_flags
        assert "debug changelog" in dataset_flags
