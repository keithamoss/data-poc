"""The queue's headlines name a dataset by its name, not its id (post-build-
review #493 nit): 'cp-case-workers has a supply nothing could place' and
'birth-registrations: 56 days with no supply' were 29 of the two pages' 50
items."""
import contextlib

import pytest

from qa_tools.common import delivery_log, filing_queue, outstanding, supply_holds

pytestmark = pytest.mark.asset("quarterly")


class _NoRows:
    def execute(self, *a, **k):
        return self

    def fetchall(self):
        return []


@pytest.fixture
def no_database(monkeypatch):
    monkeypatch.setattr(delivery_log, "_db", lambda conn=None: contextlib.nullcontext(_NoRows()))


def test_a_held_supply_is_named(monkeypatch, no_database):
    from datetime import datetime, timezone
    held = supply_holds.Held(dataset_id="cp-case-workers", supply_id="x", kind=supply_holds.ASSIGNMENT_RULE,
                             reason={"unavailable": []}, raised_by="rule", delivery="d1",
                             raised_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(supply_holds, "outstanding", lambda db: [held])
    [item] = outstanding._from_holds()
    assert item.headline == "Case Workers has a supply nothing could place", item.headline


def test_a_closed_unfilled_run_is_named(monkeypatch, no_database):
    monkeypatch.setattr(filing_queue, "closed_gaps", lambda db, collection_id: [
        filing_queue.Gap(dataset_id="cp-case-workers", periods=("2026-Q1",), state="closed")]
        if collection_id == "child-protection" else [])
    [item] = outstanding._from_unfilled_periods()
    assert item.headline.startswith("Case Workers: 1 period with no supply"), item.headline
