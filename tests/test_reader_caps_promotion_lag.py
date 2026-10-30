"""A supply another collection's checks read is promoted, in a replay, before
that reader's delivery for the same period arrives (REQ-GEN-334 criterion 12,
Keith 2026-10-30: cap the lag, generically).

The invented replay lag never runs past the next receipt of the SAME dataset
(post-build-review #117 D5); it also never runs past the next receipt of a
delivery from a collection whose checks read this dataset's table, for the
same period - so the linkage product reads Emergency Department's supply
promoted. A reader's delivery for ANOTHER period (Child Protection's next
quarter arriving the day a linkage product for this one does) caps nothing.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from qa_tools.common import promotion

ED_AT = datetime(2026, 5, 1, 7, 30, tzinfo=UTC)
LP_AT = datetime(2026, 5, 1, 10, 15, tzinfo=UTC)


@pytest.fixture
def world(monkeypatch):
    from qa_tools.common import arrivals, filing, supply_db

    class _C:
        def execute(self, *a):
            return SimpleNamespace(fetchall=lambda: [(None,)])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(supply_db, "connect", lambda **kw: _C())
    trees = {"emergency-department": [SimpleNamespace(
                 received_at=ED_AT, files_by_dataset={"ed-presentations": ()})],
             "linkage-products": [SimpleNamespace(
                 received_at=LP_AT, files_by_dataset={"linkage-keys": ()})],
             "child-protection": []}
    monkeypatch.setattr(arrivals, "arrivals_for",
                        lambda coll, prefix, *a, **k: trees.get(coll, []))
    periods = {"ed-presentations": "2026-Q2"}
    monkeypatch.setattr(filing, "period_of", lambda ds, at: periods.get(ds))
    return SimpleNamespace(trees=trees, periods=periods)


def _arrival(dataset_id, at):
    return SimpleNamespace(received_at=at, files_by_dataset={dataset_id: ()}, run_id="r")


def test_a_readers_delivery_for_the_same_period_caps_the_lag(world, monkeypatch):
    from qa_tools.common import slots

    monkeypatch.setattr(slots, "period_claimed_at",
                        lambda ds, at, agreement=None: "2026-Q2")
    assert promotion.next_receipt(_arrival("ed-presentations", ED_AT)) == LP_AT


def test_a_readers_delivery_for_another_period_caps_nothing(world, monkeypatch):
    from qa_tools.common import slots

    monkeypatch.setattr(slots, "period_claimed_at",
                        lambda ds, at, agreement=None: "2026-Q1")
    assert promotion.next_receipt(_arrival("ed-presentations", ED_AT)) is None


def test_the_lag_ends_before_the_readers_receipt(world, monkeypatch):
    from qa_tools.common import slots

    monkeypatch.setattr(slots, "period_claimed_at",
                        lambda ds, at, agreement=None: "2026-Q2")
    took = promotion.effective_at_for(
        ED_AT, now=datetime(2030, 1, 1, tzinfo=UTC), seed="r",
        before=promotion.next_receipt(_arrival("ed-presentations", ED_AT)))
    assert ED_AT <= took < LP_AT


class TestThePeriodAReceiptClaims:
    """slots.period_claimed_at: the period whose slot's claim window holds the
    instant, from configuration."""

    def test_a_linkage_receipt_on_a_round_claims_that_rounds_own_period(self):
        from qa_tools.common import slots

        assert slots.period_claimed_at("linkage-keys", LP_AT) == "2026-Q2"

    def test_a_child_protection_receipt_claims_the_next_period(self):
        from qa_tools.common import slots

        assert slots.period_claimed_at("cp-clients", ED_AT) == "2026-Q3"
