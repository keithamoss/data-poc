"""Tests for cli/common.py - the mothman CLI's shared TUI helpers
(plans/tooling.md #1): the non-TTY guard, confirm-by-default+--yes, the
back-navigation-aware select(), and the tmp-dir-first Promote pattern."""
from __future__ import annotations
import os
import shutil

import pytest

import cli.common as common


def test_require_tty_raises_when_stdin_or_stdout_is_not_a_real_terminal(monkeypatch):
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(common.sys.stdout, "isatty", lambda: True)
    with pytest.raises(common.NotInteractive) as exc:
        common.require_tty("mothman bdm qa --run-id <id>")
    assert "mothman bdm qa --run-id <id>" in str(exc.value)


def test_require_tty_passes_when_both_streams_are_real_terminals(monkeypatch):
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(common.sys.stdout, "isatty", lambda: True)
    common.require_tty("irrelevant")  # must not raise


def test_select_returns_none_on_back(monkeypatch):
    monkeypatch.setattr(common, "require_tty", lambda hint: None)
    monkeypatch.setattr(common.questionary, "select",
                         lambda *a, **k: type("Q", (), {"ask": lambda self: common.BACK})())
    assert common.select("pick one", ["a", "b"], flag_hint="x") is None


def test_select_returns_none_when_questionary_signals_cancellation(monkeypatch):
    """This mocks questionary.select() to simulate a `None` answer (what
    it returns for real on Ctrl-C - the only real cancellation key it
    binds, plans/tooling.md #9, 2026-09-19) and checks common.select()'s
    own pass-through logic treats that the same as an explicit Back, not
    an error. It does NOT exercise real questionary key-binding
    behaviour itself - a real, live pty-driven check of that (confirming
    Ctrl-C really does return None, and Escape genuinely does not) was
    done manually via scripts/dev/tui_drive.py while investigating
    plans/tooling.md #9; not duplicated here as an automated test, since
    that would mean either a slow, fixture-heavy real-pty test in a unit
    suite that otherwise mocks this entirely, or coupling this test to
    questionary's own internal key-binding implementation."""
    monkeypatch.setattr(common, "require_tty", lambda hint: None)
    monkeypatch.setattr(common.questionary, "select",
                         lambda *a, **k: type("Q", (), {"ask": lambda self: None})())
    assert common.select("pick one", ["a", "b"], flag_hint="x") is None


def test_select_returns_the_real_choice(monkeypatch):
    monkeypatch.setattr(common, "require_tty", lambda hint: None)
    captured = {}

    def fake_select(message, choices, style=None):
        captured["choices"] = choices
        return type("Q", (), {"ask": lambda self: "a"})()
    monkeypatch.setattr(common.questionary, "select", fake_select)

    assert common.select("pick one", ["a", "b"], flag_hint="x") == "a"
    assert captured["choices"] == ["a", "b", common.BACK]  # Back always appended


def test_path_prompt_returns_none_when_questionary_signals_cancellation(monkeypatch):
    """Same real caveat as test_select_returns_none_when_questionary_
    signals_cancellation above - a mocked `None` answer (real Ctrl-C
    behaviour), not a live exercise of questionary's own key bindings."""
    monkeypatch.setattr(common, "require_tty", lambda hint: None)
    monkeypatch.setattr(common.questionary, "path",
                         lambda *a, **k: type("Q", (), {"ask": lambda self: None})())
    assert common.path_prompt("pick a file", flag_hint="x") is None


def test_path_prompt_returns_none_on_a_blank_answer(monkeypatch):
    monkeypatch.setattr(common, "require_tty", lambda hint: None)
    monkeypatch.setattr(common.questionary, "path",
                         lambda *a, **k: type("Q", (), {"ask": lambda self: ""})())
    assert common.path_prompt("pick a file", flag_hint="x") is None


def test_path_prompt_returns_the_real_answer(monkeypatch):
    monkeypatch.setattr(common, "require_tty", lambda hint: None)
    monkeypatch.setattr(common.questionary, "path",
                         lambda *a, **k: type("Q", (), {"ask": lambda self: "/some/file.csv"})())
    assert common.path_prompt("pick a file", flag_hint="x") == "/some/file.csv"


def test_confirm_yes_flag_bypasses_the_prompt_entirely(monkeypatch):
    def _fail_if_called(*a, **k):
        raise AssertionError("yes=True must never touch require_tty or questionary")
    monkeypatch.setattr(common, "require_tty", _fail_if_called)
    monkeypatch.setattr(common.questionary, "confirm", _fail_if_called)
    assert common.confirm("Promote?", yes=True) is True


def test_confirm_without_yes_requires_a_real_terminal(monkeypatch):
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: False)
    with pytest.raises(common.NotInteractive):
        common.confirm("Promote?", yes=False)


def test_confirm_without_yes_asks_and_returns_the_real_answer(monkeypatch):
    monkeypatch.setattr(common, "require_tty", lambda hint: None)
    monkeypatch.setattr(common.questionary, "confirm",
                         lambda *a, **k: type("Q", (), {"ask": lambda self: True})())
    assert common.confirm("Promote?", yes=False) is True


def test_promote_copies_every_scope_of_the_run_into_the_real_tree(tmp_path):
    """A run is SEVERAL directories since REQ-PIPE-038 - one per
    dataset it wrote a result for, plus `_raw`. Copying one of them
    promotes a run that looks complete and is missing most of itself.
    """
    from qa_tools.common import tables_read

    tmp_root = tmp_path / "tmp_qa_results"
    collection = tmp_root / "agency-x" / "collection-y"
    for scope, filename in [(tables_read.RAW_SCOPE, "dataset_stats.json"),
                             ("dataset-a", "soda.json"),
                             ("dataset-b", "soda.json"),
                             (tables_read.CROSS_TABLE_SCOPE, "soda.json")]:
        run_dir = collection / scope / "run_001"
        run_dir.mkdir(parents=True)
        (run_dir / filename).write_text('{"raw_output": {}}')
    # Another run's directory, which must NOT be dragged along.
    (collection / "dataset-a" / "run_002").mkdir(parents=True)
    (collection / "dataset-a" / "run_002" / "soda.json").write_text("{}")

    fake_real_qa_results = tmp_path / "real_qa_results"
    common_module_qa_results = common.QA_RESULTS_DIR
    try:
        common.QA_RESULTS_DIR = fake_real_qa_results
        dst = common.promote(str(tmp_root), "agency-x", "collection-y", "run_001")
    finally:
        common.QA_RESULTS_DIR = common_module_qa_results

    promoted = fake_real_qa_results / "agency-x" / "collection-y"
    assert dst == promoted / tables_read.RAW_SCOPE / "run_001"
    assert (dst / "dataset_stats.json").exists()
    assert (promoted / "dataset-a" / "run_001" / "soda.json").exists()
    assert (promoted / "dataset-b" / "run_001" / "soda.json").exists()
    assert (promoted / tables_read.CROSS_TABLE_SCOPE / "run_001" / "soda.json").exists()
    assert not (promoted / "dataset-a" / "run_002").exists()


def test_new_tmp_results_dir_returns_a_real_fresh_empty_directory():
    d = common.new_tmp_results_dir()
    try:
        assert os.path.isdir(d)
        assert os.listdir(d) == []
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _promoted_run_dir(tmp_path, n_files: int = 5):
    dst = tmp_path / "qa_results" / "agency-x" / "dataset-y" / "run_001"
    dst.mkdir(parents=True)
    for i in range(n_files):
        (dst / f"tool_{i}.json").write_text("{}")
    return dst


def test_report_promoted_states_the_real_file_count_and_destination(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: False)
    common.report_promoted(_promoted_run_dir(tmp_path))
    out = capsys.readouterr().out
    assert "Promoted" in out
    assert "5 result files" in out
    assert "run_001" in out
    # The real "you still have to push this" follow-up has to survive the
    # move into a panel - it's the whole point of the message.
    assert "commit and push" in out


def test_report_promoted_waits_for_a_keypress_in_a_real_terminal(tmp_path, monkeypatch):
    """Keith's own ask (2026-09-19): a confirmed Promote must not bump the
    user straight back to the main menu."""
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(common.sys.stdout, "isatty", lambda: True)
    asked = []
    monkeypatch.setattr(common.questionary, "press_any_key_to_continue",
                         lambda *a, **k: type("Q", (), {"ask": lambda self: asked.append(True)})())
    common.report_promoted(_promoted_run_dir(tmp_path))
    assert asked == [True]


def test_report_promoted_never_blocks_when_stdout_is_not_a_terminal(tmp_path, monkeypatch):
    """A piped/scripted run must never hang on a keypress that can't come."""
    monkeypatch.setattr(common.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(common.sys.stdout, "isatty", lambda: False)

    def _explode(*a, **k):
        raise AssertionError("must not prompt when stdout isn't a terminal")

    monkeypatch.setattr(common.questionary, "press_any_key_to_continue", _explode)
    common.report_promoted(_promoted_run_dir(tmp_path))
