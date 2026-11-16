"""Staging, the checks, the gate, promotion and the dashboard build read
nothing under an asset's synthetic/ folder (REQ-GEN-370 criterion 3) - the
daily asset, Birth Registrations' first two generated deliveries.

The harness and what its audit hook sees and does not are in
tests/synthetic_unread_support.py; it excuses no read since REQ-GEN-381.
Twice: with a synthetic/ folder holding one real scripted decision - which the
batch pass, given no player, neither reads nor plays (REQ-PIPE-383) - and with
the folder removed. The second overlaps REQ-PIPE-385 criterion 1, which
owns the whole of that case (imports blocked, every gate, the commands
refused); this shows only what criterion 3 names.
"""
from __future__ import annotations

import pytest

import synthetic_unread_support as support


@pytest.fixture(scope="module")
def runs(tmp_path_factory, worker_id, daily_history):
    return support.runs("civil-registration", "birth-registrations", tmp_path_factory,
                        worker_id, daily_history)


class TestTheDailyAssetReadsNothingThere(support.Checks):
    pass


#: The data asset this module's tests act for (C11, Keith 2026-11-02).
pytestmark = pytest.mark.asset("daily")
