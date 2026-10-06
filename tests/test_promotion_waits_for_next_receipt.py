"""Both orchestrators cap a replayed promotion at the next receipt
(REQ-PIPE-081, Keith's #117 D5) - post-build-review #122 found no test
failed if `before=next_receipt(...)` was dropped from either call site.

Driven through each real promote_after(), with the gate and the knock-on
stubbed: the instant it hands the promotion must land before the next
file of the same dataset arrived, never after it."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
import qa_tools.cp.orchestrate_cp as orchestrate_cp
from qa_tools.common import knock_on, promotion

RECEIVED = datetime(2023, 4, 3, 9, 0, tzinfo=timezone.utc)
NEXT = RECEIVED + timedelta(seconds=30)


@pytest.mark.parametrize("module", [orchestrate_bdm, orchestrate_cp], ids=["bdm", "cp"])
def test_the_promotion_lands_before_the_next_receipt(module, monkeypatch):
    stamped = []
    monkeypatch.setattr(promotion, "next_receipt", lambda arrival: NEXT)
    monkeypatch.setattr(promotion, "after_runs",
                        lambda arrivals, got, **k: stamped.append(k["effective_at"]))
    monkeypatch.setattr(promotion, "report", lambda *a, **k: None)
    monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: None)
    # A run id whose seeded lag is far longer than thirty seconds, so the
    # cap is what keeps it before the next receipt.
    arrival = SimpleNamespace(received_at=RECEIVED, run_id="run_lag_probe")
    assert promotion.effective_at_for(RECEIVED, seed="run_lag_probe") > NEXT, (
        "test precondition - the uncapped lag must reach past the next receipt")
    module.promote_after(arrival, [], "t@example.com")
    [effective] = stamped
    at = datetime.fromisoformat(effective)
    assert RECEIVED <= at < NEXT
