"""The Mental Health collection's weekly participation on the daily asset, from
configuration alone - the unit tests behind TS-116 and TS-117 (REQ-GEN-351; the
register's first standing obligation, plans/supply-model.md).

Service Contacts owes one supply a week, on Mondays (participates [Monday],
REQ-QAC-350, REQ-PIPE-346). A Monday's slot closes when Tuesday's claim window
opens, so a supply received on the Tuesday finds no slot open and is held for a
person (REQ-PIPE-131 criterion 10); a Monday with no supply is still owed, so it
reads 'No supply' rather than standing on last week's; and the six days after
each Monday owe nothing, so each stands on its supply (REQ-PIPE-098).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from asset_model import assignment, slots

DS = "mental-health-contacts"


def _slots():
    from generator.anchor_date import get_anchor_date

    return slots.slots_for_dataset(DS, until=get_anchor_date())


def _a_recent_monday():
    owed = _slots()
    assert len(owed) >= 10, "test precondition - ten weeks of Mondays"
    return owed, owed[-3]


def test_it_owes_only_mondays():
    owed, _monday = _a_recent_monday()
    assert {s.round_date.weekday() for s in owed} == {0}, [s.name for s in owed]


def test_ts117_a_supply_on_the_tuesday_is_held_not_filed():
    owed, monday = _a_recent_monday()
    tuesday_0815 = monday.due_at - timedelta(hours=10) + timedelta(days=1, hours=8, minutes=15)
    got = assignment.assign(DS, "s", tuesday_0815, owed, frozenset({monday.name}))
    assert got.slot is None and got.branch == assignment.HELD, got.describe()


def test_ts117_mondays_own_supply_fills_it():
    owed, monday = _a_recent_monday()
    got = assignment.assign(DS, "s", monday.due_at - timedelta(minutes=105), owed, frozenset())
    assert got.slot == monday.name and got.branch == assignment.OPEN_UNFILLED


def test_ts116_a_missed_monday_is_owed_not_inherited():
    from qa_tools.common import inheritance

    _owed, monday = _a_recent_monday()
    assert inheritance._does_not_participate(DS, monday.name) == (False, "")


@pytest.mark.parametrize("days_on", range(1, 7))
def test_the_six_days_after_a_monday_stand_on_its_supply(days_on):
    from qa_tools.common import inheritance

    _owed, monday = _a_recent_monday()
    day = (monday.round_date + timedelta(days=days_on)).isoformat()
    skipped, reason = inheritance._does_not_participate(DS, day)
    assert skipped, (day, reason)
    assert "Monday" in reason, reason


pytestmark = pytest.mark.asset("daily")
