"""REQ-GEN-370 criterion 3 on the quarterly asset - Emergency Department's
first two generated deliveries, whose asset's synthetic/ folder also holds
synthetic_inputs.yaml. Same harness and checks as the daily module
(tests/synthetic_unread_support.py)."""
from __future__ import annotations

import pytest

import synthetic_unread_support as support


@pytest.fixture(scope="module")
def runs(tmp_path_factory, worker_id, quarterly_history):
    return support.runs("emergency-department", "ed-presentations", tmp_path_factory,
                        worker_id, quarterly_history)


class TestTheQuarterlyAssetReadsNothingThere(support.Checks):
    pass


#: The data asset this module's tests act for (C11, Keith 2026-11-02).
pytestmark = pytest.mark.asset("quarterly")
