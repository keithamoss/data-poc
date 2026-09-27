"""Tests for cli/common.py - the mothman CLI's shared TUI helpers
(plans/tooling.md #1): the non-TTY guard, confirm-by-default+--yes, the
back-navigation-aware select(), and the record-or-trial decision.

The "tmp-dir-first Promote pattern" this used to cover is gone with
REQ-PIPE-089 - see test_report_recorded_* and test_decide_record_* below
for what replaced it and why."""
from __future__ import annotations

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


def test_report_recorded_states_the_real_count_and_says_nothing_is_published(
        capsys, monkeypatch):
    """WHAT THIS REPLACED. `report_promoted()` said how many FILES had
    landed in the committed tree and where. There is no tree and there
    are no files (REQ-PIPE-089), so the count is of recorded results -
    but the affordance survived the change, because Keith asked for it
    by name: "after the user confirms promotion of results, they should
    get a success message rather than being bumped straight back to the
    menu". This is the most consequential action in the tool and it must
    not look like the end of a no-op.
    """
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    common.report_recorded("run_042", 137)
    out = capsys.readouterr().out
    assert "137" in out
    assert "run_042" in out


def test_report_recorded_no_longer_tells_anyone_to_commit_and_push(capsys, monkeypatch):
    """The sentence it used to end with - "commit and push qa_results/
    yourself to publish. That push is what triggers the real CI rebuild"
    - is false twice over now: there is nothing to commit, and a git
    push is not what publishes (REQ-PIPE-092). Asserted rather than
    assumed, because a stale instruction in a success panel is exactly
    the kind of thing that survives a refactor and misleads someone
    months later."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    common.report_recorded("run_042", 1)
    out = capsys.readouterr().out
    assert "commit" not in out.lower()
    assert "push" not in out.lower()


def test_report_recorded_waits_for_a_keypress_in_a_real_terminal(monkeypatch):
    pressed = []
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(common.questionary, "press_any_key_to_continue",
                        lambda *a, **k: type("A", (), {"ask": lambda self: pressed.append(True)})())
    common.report_recorded("run_042", 3)
    assert pressed == [True]


def test_report_recorded_never_blocks_when_stdout_is_not_a_terminal(monkeypatch):
    """The scriptable paths must not hang waiting for a keypress nobody
    is there to give."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    def _never(*a, **k):
        raise AssertionError("asked for a keypress with no terminal to answer it")

    monkeypatch.setattr(common.questionary, "press_any_key_to_continue", _never)
    common.report_recorded("run_042", 3)


def test_decide_record_takes_the_flags_answer_without_asking(monkeypatch):
    """`--commit`/`--trial` stop the prompt entirely rather than
    pre-filling it, so a scripted caller never needs a terminal."""
    def _never(*a, **k):
        raise AssertionError("prompted despite having been told the answer")

    monkeypatch.setattr(common, "confirm", _never)
    assert common.decide_record("run_01", keep=True) is True
    assert common.decide_record("run_01", keep=False) is False


def test_decide_record_defaults_to_a_trial_with_no_terminal_and_no_flag(monkeypatch, capsys):
    """The two wrong answers are not equally wrong. A trial that should
    have been recorded costs a re-run; a recorded run that should not
    have been is a verdict in a dataset's permanent quality history that
    nobody chose."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    assert common.decide_record("run_01", keep=None) is False
    assert "TRIAL" in capsys.readouterr().out


def test_decide_record_asks_before_the_run_rather_than_after(monkeypatch):
    """REQ-PIPE-089 criterion 8. It used to be asked afterwards, as
    "promote this run?", which worked only because the results sat in a
    throwaway directory until somebody accepted them. Asserted on the
    WORDING because that is what a user reads: the question has to be
    about what will happen, not about what already did."""
    asked = []
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(common, "confirm", lambda q, **k: asked.append(q) or True)
    common.decide_record("run_07", keep=None)
    assert asked and "run_07" in asked[0]
    assert "promote" not in asked[0].lower()
