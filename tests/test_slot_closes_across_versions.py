"""A slot's closing instant across a calendar's version boundary
(REQ-PIPE-131 criteria 1-2; delivery-critic findings, overnight sprint 3b).

Probed against a small synthetic calendar written to a temporary config,
so the real asset's dates cannot move these answers.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

import agreement_split
from qa_tools.common import hierarchy, slots

PERTH = timezone(timedelta(hours=8))


@pytest.fixture
def calendar(tmp_path, monkeypatch):
    def use(versions, extra=None):
        # 09:00, no grace, no override - the timing under test is the
        # calendar's (agreement_split's default participation).
        ds = {"id": "d", "name": "D", "table": "t", "calendar": "c", **(extra or {})}
        agreement_split.repoint(monkeypatch, tmp_path, {
            "data_asset_id": "data-asset-1",
            "calendars": [{"name": "c", "versions": versions}],
            "hierarchy": {"agencies": [{"id": "a", "name": "A", "collections": [
                {"id": "col", "name": "Col", "contract": "c.yaml", "datasets": [ds]}]}]}},
            base={})

    yield use
    agreement_split.clear_caches()
    hierarchy._load.cache_clear()


AUTHORED_THEN_DAILY = [
    {"effective_from": "2023-01-01", "changelog": ["i"], "claim_window": "14d",
     "dates": [{"period": "2024-Q1", "date": "2024-02-01"},
               {"period": "2024-Q2", "date": "2024-05-01"}]},
    {"effective_from": "2024-06-01", "changelog": ["2024-06-01: daily"],
     "claim_window": "4h", "cadence": {"rule": "daily"}}]


@pytest.mark.parametrize("until", [date(2024, 5, 10), date(2024, 5, 30)])
def test_the_last_authored_slot_closes_when_the_cadence_rule_begins(calendar, until):
    """Found by the critic: generated with `until` before the switch, the
    last authored slot had NO closing instant - the period after it is the
    cadence rule's first day, beyond `until` + 1 day."""
    calendar(AUTHORED_THEN_DAILY)
    q2 = slots.slots_for_dataset("d", until=until)[-1]
    assert q2.name == "2024-Q2"
    assert q2.closes_at == datetime(2024, 6, 1, 5, 0, tzinfo=PERTH)


def test_a_claim_window_change_closes_with_the_next_periods_own_window(calendar):
    calendar([
        {"effective_from": "2023-01-01", "changelog": ["i"], "claim_window": "14d",
         "dates": [{"period": "2024-Q1", "date": "2024-02-01"}]},
        {"effective_from": "2027-01-01", "changelog": ["2027-01-01: x"], "claim_window": "7d",
         "dates": [{"period": "2027-Q1", "date": "2027-02-01"}]}])
    first = slots.slots_for_dataset("d")[0]
    assert first.closes_at == datetime(2027, 1, 25, 9, 0, tzinfo=PERTH)


def test_a_datasets_own_dates_close_at_its_next_own_date(calendar):
    calendar(AUTHORED_THEN_DAILY[:1],
             {"dates": [{"period": "own-1", "date": "2024-03-01"},
                        {"period": "own-2", "date": "2024-09-01"}]})
    own1 = slots.slots_for_dataset("d")[0]
    assert own1.closes_at == datetime(2024, 8, 18, 9, 0, tzinfo=PERTH)
