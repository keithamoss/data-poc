"""MOTHMAN_PINNED_NOW: the asset clock read as one fixed instant
(REQ-TEST-239 criterion 16, Keith 2026-10-16).

The equivalence harness pins it so that two captures built hours or days
apart agree on everything the build works out from "now" - which slots
have closed, what is still awaiting, how long a supply has waited."""
from __future__ import annotations

from datetime import datetime

import pytest

from qa_tools.common import asset_time


@pytest.fixture
def synthetic(monkeypatch):
    def declare(value: bool):
        monkeypatch.setattr(asset_time, "declared_synthetic", lambda: value)
    return declare


def test_the_clock_reads_the_pinned_instant(monkeypatch, synthetic):
    synthetic(True)
    monkeypatch.setenv("MOTHMAN_PINNED_NOW", "2026-10-16T12:00:00+08:00")
    got = asset_time.now()
    assert got == datetime.fromisoformat("2026-10-16T12:00:00+08:00")
    assert got.tzinfo is not None
    assert got.utcoffset() == asset_time.zone_now().utcoffset(got)


def test_without_the_variable_the_clock_is_the_wall_clock(monkeypatch, synthetic):
    synthetic(True)
    monkeypatch.delenv("MOTHMAN_PINNED_NOW", raising=False)
    before = datetime.now().astimezone()
    got = asset_time.now()
    assert before <= got <= datetime.now().astimezone()


def test_a_real_asset_refuses_a_pinned_clock_naming_the_variable(monkeypatch, synthetic):
    synthetic(False)
    monkeypatch.setenv("MOTHMAN_PINNED_NOW", "2026-10-16T12:00:00+08:00")
    with pytest.raises(asset_time.PinnedClockRefused, match="MOTHMAN_PINNED_NOW"):
        asset_time.now()


def test_a_naive_pinned_instant_is_refused(monkeypatch, synthetic):
    synthetic(True)
    monkeypatch.setenv("MOTHMAN_PINNED_NOW", "2026-10-16T12:00:00")
    with pytest.raises(asset_time.NaiveTimestampError):
        asset_time.now()

