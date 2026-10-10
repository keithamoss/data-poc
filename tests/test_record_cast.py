"""Tests for scripts/dev/record_cast.py's real pty recording loop.

Dev-only tooling, but it produced a real, shipped artifact - the
committed dashboard/demos/qa_wizard.cast the published dashboard's Demo
tab plays - so a bug here is visible to everyone who opens the site.
That is exactly what happened (plans/dashboard.md #13's follow-up):
every CPR (cursor-position-request) was answered with a constant
ESC[1;1R, so prompt_toolkit believed it was always at the top-left,
re-rendered each prompt from row 0 and erased the splash screen and
every answered line above it. A viewer saw an unreadable orange flash.
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "record_cast", Path(__file__).resolve().parents[1] / "scripts" / "dev" / "record_cast.py")
record_cast = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(record_cast)


def _decoded(events) -> str:
    return "".join(text for _, text in events)


# A real child process: print three lines, ask the terminal where the
# cursor is, then print whatever answer came back so the test can assert
# on it. Nothing mocked - this exercises the genuine pty round trip.
_CPR_PROBE_CHILD = (
    "import sys,termios,tty;"
    "sys.stdout.write('one\\r\\ntwo\\r\\nthree\\r\\n');sys.stdout.flush();"
    "tty.setraw(sys.stdin.fileno());"
    "sys.stdout.write('\\x1b[6n');sys.stdout.flush();"
    "buf='';\n"
    "while not buf.endswith('R'): buf += sys.stdin.read(1)\n"
    "sys.stdout.write('GOT'+buf.replace(chr(27),'ESC')+'\\r\\n');sys.stdout.flush()"
)


def test_cursor_position_requests_are_answered_with_the_real_row():
    """Three lines printed leaves the cursor on row 4 (1-indexed), column
    1 - so that, not a constant ESC[1;1R, is what a real terminal would
    reply. Fails against the pre-fix recorder, which always said 1;1."""
    events = record_cast.record(
        [sys.executable, "-c", _CPR_PROBE_CHILD],
        record_cast.parse_steps(["wait:GOT:10"]),
        cols=80, rows=24, settle_delay=0.1, final_idle_timeout=0.5)
    out = _decoded(events)
    assert "GOTESC[4;1R" in out, out[-400:]


def test_a_scripted_pause_keeps_recording_rather_than_ending_the_session():
    events = record_cast.record(
        [sys.executable, "-c", "import sys,time;sys.stdout.write('hello\\r\\n');sys.stdout.flush();"
                                "time.sleep(0.6);sys.stdout.write('later\\r\\n');sys.stdout.flush()"],
        record_cast.parse_steps(["wait:hello", "pause:1.2"]),
        cols=80, rows=24, settle_delay=0.05, final_idle_timeout=0.3)
    assert "later" in _decoded(events)


def test_parse_steps_rejects_a_non_numeric_pause():
    with pytest.raises(ValueError, match="pause needs a number"):
        record_cast.parse_steps(["pause:soon"])
