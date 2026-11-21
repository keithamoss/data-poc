"""The Cancer collection's annual participation, from configuration alone -
the unit tests behind TS-114 and TS-115 (REQ-GEN-349; the register's first
standing obligation, plans/supply-model.md).

Cancer Notifications owes one supply a year, in the August round
(participates [August], REQ-QAC-348). Its slot closes when the next calendar
round's claim window opens, so a supply received on the November round's date
finds no slot open and is held for a person (REQ-PIPE-131 criterion 10), never
filed forward to a quarter it owes nothing in; and the three quarters after
each August owe nothing, so each stands on the August supply (REQ-PIPE-098).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from asset_model import assignment, schedule, slots

DS = "cancer-notifications"
PERTH = timezone(timedelta(hours=8))


def _slots():
    return slots.slots_for_dataset(DS, until=date(2026, 12, 31))


def test_it_owes_only_the_august_rounds():
    owed = _slots()
    assert len(owed) >= 10, "test precondition - a decade of August rounds"
    assert {s.round_date.month for s in owed} == {8}, [s.name for s in owed]


def test_ts114_a_supply_on_the_november_round_is_held_not_filed_forward():
    owed = _slots()
    august = next(s for s in owed if s.round_date.year == 2024)
    cal = schedule.calendar_for_dataset(DS).name
    on = next(p.date for p in schedule.periods_for_calendar(cal)
              if p.date.year == 2024 and p.date.month == 11)
    got = assignment.assign(DS, "s", datetime.combine(on, datetime.min.time(), PERTH)
                            + timedelta(hours=10), owed, frozenset({august.name}))
    assert got.slot is None and got.branch == assignment.HELD, got.describe()
    assert august.name in dict(got.unavailable), got.unavailable


def test_ts114_the_same_supply_in_august_fills_its_quarter():
    owed = _slots()
    august = next(s for s in owed if s.round_date.year == 2024)
    got = assignment.assign(DS, "s", august.due_at - timedelta(hours=1), owed, frozenset())
    assert got.slot == august.name and got.branch == assignment.OPEN_UNFILLED


@pytest.mark.parametrize("quarter", ["2025-Q4", "2026-Q1", "2026-Q2"])
def test_ts115_each_quarter_after_august_stands_on_its_supply(quarter):
    from qa_tools.common import inheritance

    skipped, reason = inheritance._does_not_participate(DS, quarter)
    assert skipped, reason
    assert "August" in reason, reason


def test_ts115_the_august_quarter_itself_is_owed():
    from qa_tools.common import inheritance

    assert inheritance._does_not_participate(DS, "2025-Q3") == (False, "")


pytestmark = pytest.mark.asset("quarterly")
