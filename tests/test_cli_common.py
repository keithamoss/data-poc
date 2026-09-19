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


def test_select_returns_none_on_ctrl_c_or_esc(monkeypatch):
    """questionary returns None itself on Ctrl-C/Esc - treated the same
    as an explicit Back, not as an error."""
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


def test_path_prompt_returns_none_on_ctrl_c_or_esc(monkeypatch):
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


def test_promote_copies_the_tmp_run_into_the_real_qa_results_tree(tmp_path):
    tmp_root = tmp_path / "tmp_qa_results"
    run_dir = tmp_root / "agency-x" / "dataset-y" / "run_001"
    run_dir.mkdir(parents=True)
    (run_dir / "dataset_stats.json").write_text('{"raw_output": {}}')

    fake_real_qa_results = tmp_path / "real_qa_results"
    common_module_qa_results = common.QA_RESULTS_DIR
    try:
        common.QA_RESULTS_DIR = fake_real_qa_results
        dst = common.promote(str(tmp_root), "agency-x", "dataset-y", "run_001")
    finally:
        common.QA_RESULTS_DIR = common_module_qa_results

    assert dst == fake_real_qa_results / "agency-x" / "dataset-y" / "run_001"
    assert (dst / "dataset_stats.json").exists()


def test_new_tmp_results_dir_returns_a_real_fresh_empty_directory():
    d = common.new_tmp_results_dir()
    try:
        assert os.path.isdir(d)
        assert os.listdir(d) == []
    finally:
        shutil.rmtree(d, ignore_errors=True)
