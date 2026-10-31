"""Tests for generator/anchor_date.py - the fixed date this project's
generated history is built around (REQ-GEN-042).

This file's own first test used to assert the OPPOSITE of what it
asserts now, and the reversal is the requirement. It read
`test_defaults_to_real_wall_clock_today` and pinned
`get_anchor_date() == date.today()` - which is the behaviour that made
two regenerations on two consecutive days produce two complete
histories that accumulated rather than replacing one another. Measured:
the "352 committed runs" this project quoted for weeks was really 176,
each appearing twice under delivery dates one day apart.
"""
from __future__ import annotations

import subprocess
from datetime import date

from generator import anchor_date
from generator.anchor_date import ANCHOR_DATE, get_anchor_date


def test_the_anchor_is_a_committed_constant_not_todays_date(monkeypatch):
    monkeypatch.delenv("GENERATOR_ANCHOR_DATE", raising=False)
    assert get_anchor_date() == ANCHOR_DATE
    assert isinstance(ANCHOR_DATE, date)


def test_it_gives_the_same_answer_whatever_day_it_is_run(monkeypatch):
    """The criterion, stated directly: re-running on a different
    calendar day with unchanged configuration must produce an identical
    history. A generator whose "today" moves cannot."""
    monkeypatch.delenv("GENERATOR_ANCHOR_DATE", raising=False)

    class _FrozenDate(date):
        @classmethod
        def today(cls):
            return date(2099, 12, 31)

    monkeypatch.setattr(anchor_date, "date", _FrozenDate)
    assert get_anchor_date() == ANCHOR_DATE


def test_the_anchor_is_not_in_the_future(monkeypatch):
    """A guard against a bumped anchor nobody checked - dates after
    today would make every freshness check in the repo read as a
    supply that has not happened yet."""
    monkeypatch.delenv("GENERATOR_ANCHOR_DATE", raising=False)
    today = subprocess.run(["date", "-u", "+%Y-%m-%d"], capture_output=True,
                            text=True, check=True).stdout.strip()
    assert ANCHOR_DATE <= date.fromisoformat(today), (
        f"ANCHOR_DATE {ANCHOR_DATE} is in the future")


def test_honours_the_override_env_var(monkeypatch):
    """Kept for the one case that still needs it - reproducing a past
    regeneration byte-for-byte to verify a change is behaviour-
    preserving. It is no longer how the normal path gets its date."""
    monkeypatch.setenv("GENERATOR_ANCHOR_DATE", "2026-03-15")
    assert get_anchor_date() == date(2026, 3, 15)
