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


class TestTheNextReceiptIsKnownInAReplay:
    """REQ-TEST-159 records each delivery at its FIRST ARRIVAL, so in a replay
    the next delivery is not yet in the database when this one is promoted.
    The cap must still see it - from the arrivals the replay is reading - or
    an invented lag runs past the next supply and two versions show waiting
    at once (Keith's #117 D5), which is what the whole-bootstrap comparison
    caught: 29 promotions' effective_at moved past the next receipt."""

    def _tree(self, root, rows):
        import json

        for seq, (name, received) in enumerate(rows, start=1):
            (root / "deliveries" / name).mkdir(parents=True)
            (root / "receipts" / name).mkdir(parents=True)
            (root / "deliveries" / name / "cp_clients.csv").write_text(
                "client_id,given_name\n1,Ann\n")
            (root / "receipts" / name / "cp_clients.csv.json").write_text(json.dumps({
                "delivery": name, "file": "cp_clients.csv", "received_at": received,
                "received_from": "storage", "sequence": seq,
                "filed_by": {"kind": "automated"}}))

    def test_an_unrecorded_next_arrival_in_the_tree_caps_the_lag(
            self, tmp_path, monkeypatch, clean_delivery_log):
        from qa_tools.common import arrivals, delivery

        self._tree(tmp_path, [("Extract A", "2023-04-03T09:00:00+00:00"),
                              ("Extract B", "2023-04-03T09:00:30+00:00")])
        monkeypatch.setattr(delivery, "DELIVERIES_DIR", tmp_path / "deliveries")
        monkeypatch.setattr(delivery, "RECEIPTS_DIR", tmp_path / "receipts")
        first, second = arrivals.arrivals_for("child-protection", "")
        assert promotion.next_receipt(first) == second.received_at
        assert promotion.next_receipt(second) is None
