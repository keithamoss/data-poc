"""Tests for generator/anchor_date.py and asset_model/history_anchor.py - the
date a generated history runs up to (REQ-GEN-042; REQ-GEN-404 and REQ-GEN-405).

This file's first test once asserted the OPPOSITE of REQ-GEN-042: it pinned
`get_anchor_date() == date.today()`, the behaviour that made two regenerations
on consecutive days accumulate two histories. Then the anchor was a committed
constant a person bumped. Since REQ-GEN-404 it is an INPUT, given by the caller
and recorded with the history - the fixed test anchor unless asked otherwise.
"""
from __future__ import annotations

import concurrent.futures
from datetime import date, datetime, timezone

import pytest

from asset_model import assets, history_anchor
from generator import anchor_date
from generator.anchor_date import FIXED_TEST_ANCHOR, get_anchor_date

LATER = date(2026, 11, 13)


def test_the_fixed_test_anchor_is_2026_09_25():
    """REQ-GEN-405 criterion 1: one named constant, the old ANCHOR_DATE, so no
    pin built on it moves."""
    assert FIXED_TEST_ANCHOR == date(2026, 9, 25) == history_anchor.FIXED_TEST_ANCHOR


def test_with_nothing_installed_it_is_the_fixed_anchor_whatever_the_day(monkeypatch):
    """REQ-GEN-405 criterion 2: a generation the suite makes uses the fixed
    anchor on any wall-clock date."""
    monkeypatch.setenv("MOTHMAN_PINNED_NOW", "2099-12-31T12:00:00+00:00")
    assert get_anchor_date() == FIXED_TEST_ANCHOR


def test_the_installed_anchor_is_read_at_call_time():
    """REQ-GEN-404 criteria 1, 2 and 10: a provider imported before the anchor
    is installed generates for the one installed later."""
    import sys

    from generator import collections

    provider = collections.provider("child-protection")
    module = sys.modules[type(provider).__module__]
    fixed_start = module.generated_periods()[0].round.date
    with history_anchor.anchored(LATER):
        assert get_anchor_date() == LATER
        assert module.generated_periods()[0].round.date > fixed_start
    assert get_anchor_date() == FIXED_TEST_ANCHOR


def _the_anchor_there():
    return get_anchor_date()


def test_a_spawned_process_reads_the_installed_anchor():
    """REQ-GEN-404 criterion 10: handed through assets.handoff()."""
    import multiprocessing

    with history_anchor.anchored(LATER):
        with concurrent.futures.ProcessPoolExecutor(
                max_workers=1, mp_context=multiprocessing.get_context("spawn"),
                initializer=assets.adopt, initargs=assets.handoff()) as pool:
            assert pool.submit(_the_anchor_there).result(timeout=120) == LATER


def test_the_retired_variable_refuses_rather_than_going_quiet(monkeypatch):
    """REQ-GEN-404 criterion 9."""
    monkeypatch.setenv("GENERATOR_ANCHOR_DATE", "2026-03-15")
    with pytest.raises(anchor_date.AnchorRefused, match="--anchor"):
        get_anchor_date()


class TestAnAnchorIsRefusedBeforeAnythingIsWritten:
    """REQ-GEN-404 criterion 7 (SR6)."""

    TODAY = date(2026, 11, 16)

    def test_not_a_date(self):
        with pytest.raises(anchor_date.AnchorRefused, match="not a date"):
            anchor_date.validate("2026-13-01", today=self.TODAY)

    def test_after_today(self):
        with pytest.raises(anchor_date.AnchorRefused) as caught:
            anchor_date.validate("2026-11-17", today=self.TODAY)
        said = str(caught.value)
        assert "2026-11-17 is after today, 2026-11-16 on" in said
        assert ("A history cannot be generated up to a day that has not happened. "
                "Nothing was written.") in said

    def test_before_the_fixed_anchor(self):
        with pytest.raises(anchor_date.AnchorRefused, match="2026-09-25"):
            anchor_date.validate("2026-09-24", today=self.TODAY)

    def test_from_the_fixed_anchor_to_today_is_allowed(self):
        assert anchor_date.validate("2026-09-25", today=self.TODAY) == FIXED_TEST_ANCHOR
        assert anchor_date.validate("2026-11-16", today=self.TODAY) == self.TODAY


class TestTheAnchorFile:
    """REQ-GEN-404 criterion 3, REQ-GEN-406 criterion 3's resolver."""

    def test_written_and_read_back(self, tmp_path):
        at = tmp_path / history_anchor.FILE
        history_anchor.write(LATER, at)
        assert at.read_text() == "2026-11-13\n"
        assert history_anchor.recorded(at) == LATER

    def test_offsets_fall_back_to_the_fixed_anchor_only_under_test_and_ci(
            self, monkeypatch, tmp_path):
        """REQ-GEN-404 criterion 12."""
        monkeypatch.setattr(history_anchor, "path", lambda: tmp_path / "absent")
        # A HISTORY WAS GENERATED HERE, whatever this checkout holds: with no
        # delivery tree the fixed anchor is the answer everywhere (#431), so
        # the refusal below is only reachable where one exists - which a
        # fresh clone, a worktree and CI do not have (post-build-review #471).
        monkeypatch.setattr(history_anchor, "_generated", lambda: True)
        for env in ("test", "ci"):
            monkeypatch.setenv("MOTHMAN_ENVIRONMENT", env)
            assert history_anchor.for_offsets() == FIXED_TEST_ANCHOR
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        with pytest.raises(history_anchor.AnchorUnknown, match="mothman pipeline bootstrap"):
            history_anchor.for_offsets()
        history_anchor.write(LATER, tmp_path / "absent")
        assert history_anchor.for_offsets() == LATER
        with history_anchor.anchored(FIXED_TEST_ANCHOR):
            assert history_anchor.for_offsets() == FIXED_TEST_ANCHOR


def test_asset_today_is_on_the_assets_clock(monkeypatch):
    """REQ-GEN-405 criterion 3: 23:30 UTC on the 15th is the 16th in Perth."""
    monkeypatch.setenv("MOTHMAN_PINNED_NOW", datetime(2026, 11, 15, 23, 30,
                                                      tzinfo=timezone.utc).isoformat())
    assert anchor_date.asset_today() == date(2026, 11, 16)


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
