"""Staging, the checks, the gate, promotion and the dashboard build read
nothing under an asset's synthetic/ folder (REQ-GEN-370 criterion 3) - the
daily asset, Birth Registrations' first two generated deliveries.

The harness, what its audit hook sees and does not, and the one read
REQ-GEN-381 owns are in tests/synthetic_unread_support.py. Twice: with a
synthetic/ folder holding one real scripted decision, played under watch, and
with the folder removed. The second overlaps REQ-PIPE-385 criterion 1, which
owns the whole of that case (imports blocked, every gate, the commands
refused); this shows only what criterion 3 names.
"""
from __future__ import annotations

import pytest

import synthetic_unread_support as support


@pytest.fixture(scope="module")
def runs(tmp_path_factory, worker_id):
    return support.runs("civil-registration", "birth-registrations", tmp_path_factory,
                        worker_id)


class TestTheDailyAssetReadsNothingThere(support.Checks):
    pass


#: The data asset this module's tests act for (C11, Keith 2026-11-02).
pytestmark = pytest.mark.asset("daily")
