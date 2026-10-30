"""Each offset group's inheritances are made when that group first files
to a period (REQ-PIPE-323).

Child Protection files at files_go_to_period 1, Emergency Department at 0:
Child Protection's filing on a round opens the period a whole round before
Emergency Department's first filing to it, so an inheritance made then
would stand on an Emergency Department supply a round staler than it
should. The rule's own tests below state the groups and the schedule's
answer (as tests/test_inheritance.py does), so they prove the RULE; the
round arithmetic of the time route is proved against the real calendar.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import (hierarchy, inheritance, period_schema, qa_store, schedule,
                             supply_db)
from tests.test_inheritance import _promote_into, narrow

WHEN = "2026-09-29T09:00:00+08:00"
REASON = "a fictional pause in Emergency Department's supply"
ED = "ed-presentations"
CP = "cp-clients"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-offset-groups") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def periods():
    tag = uuid.uuid4().hex[:6]
    return (f"2099-A{tag}", f"2099-B{tag}", f"2099-M{tag}")


@pytest.fixture
def two_groups(monkeypatch, periods):
    """ED owes nothing in the second period; Child Protection is group 1
    and Emergency Department group 0 in it."""
    first, second, middle = periods
    monkeypatch.setattr(inheritance.schedule, "not_expected_periods",
                        lambda ds: {second: REASON} if ds == ED else {})
    order = {first: date(2099, 1, 1), middle: date(2099, 2, 1), second: date(2099, 4, 1)}
    monkeypatch.setattr(inheritance.schedule, "date_of", lambda name, ds: order.get(name))
    narrow(monkeypatch, [hierarchy.dataset(ED), hierarchy.dataset(CP)])
    monkeypatch.setattr(inheritance, "offset_group",
                        lambda ds, period: 1 if ds.startswith("cp-") else 0)


def _view_rows(conn, period, table):
    schema = period_schema.period_schema(period)
    found = conn.execute("SELECT 1 FROM information_schema.views WHERE table_schema = ? "
                         "AND table_name = ?", [schema, table]).fetchall()
    if not found:
        return None
    return [r[0] for r in conn.execute(f'SELECT id FROM "{schema}"."{table}"').fetchall()]


def _groups(conn, period):
    return conn.execute(f"SELECT files_go_to_period, collection_id, route FROM "
                        f"{inheritance.GROUP_TABLE} WHERE period = ? ORDER BY 1",
                        [period]).fetchall()


class TestEachGroupInheritsAtItsOwnFirstFiling:
    """Criteria 1, 2, 5 and 7."""

    def test_a_group_1_filing_does_not_inherit_a_group_0_dataset(self, conn, periods,
                                                                 two_groups):
        first, second, middle = periods
        _promote_into(conn, hierarchy.dataset(ED), first)
        assert period_schema.open_period(conn, second, opened_by="the filing of cp-x",
                                         dataset_id=CP, route="filing", caused_by="cp-x")
        assert _view_rows(conn, second, hierarchy.dataset(ED).table) is None
        assert _groups(conn, second) == [(1, "child-protection", "filing")]

    def test_group_0_inherits_the_supply_promoted_in_between(self, conn, periods,
                                                             two_groups):
        first, second, middle = periods
        ed = hierarchy.dataset(ED)
        _promote_into(conn, ed, first)
        period_schema.open_period(conn, second, opened_by="the filing of cp-x",
                                  dataset_id=CP, route="filing")
        # A NEWER Emergency Department supply, promoted after Child
        # Protection opened the period - the one its group should stand on.
        newer = _promote_into(conn, ed, middle)
        conn.execute(f'INSERT INTO "{period_schema.period_schema(middle)}"."{ed.table}" '
                     "VALUES (5)")
        assert inheritance.make_group(conn, second, offset=0,
                                      collection_id="emergency-department",
                                      route="claim window opened", effective_at=WHEN)
        assert sorted(_view_rows(conn, second, ed.table)) == [3, 5]
        [(stands_on,)] = conn.execute(
            f"SELECT stands_on FROM {dl.TABLE} WHERE dataset_id = ? AND to_slot = ? "
            "AND action = 'inherit'", [ED, second]).fetchall()
        assert stands_on == middle, newer
        assert _groups(conn, second) == [(0, "emergency-department", "claim window opened"),
                                         (1, "child-protection", "filing")]

    def test_each_group_is_made_once(self, conn, periods, two_groups):
        first, second, middle = periods
        _promote_into(conn, hierarchy.dataset(ED), first)
        assert inheritance.make_group(conn, second, offset=0, collection_id="x",
                                      route="filing", effective_at=WHEN)
        assert not inheritance.make_group(conn, second, offset=0, collection_id="y",
                                          route="re-file", effective_at=WHEN)
        assert _groups(conn, second) == [(0, "x", "filing")]


def test_one_offset_everywhere_behaves_as_before(conn, periods, two_groups, monkeypatch):
    """Criterion 4: every collection at one offset - the first filing makes
    every inheritance, exactly as REQ-PIPE-271 does."""
    first, second, middle = periods
    monkeypatch.setattr(inheritance, "offset_group", lambda ds, period: 0)
    _promote_into(conn, hierarchy.dataset(ED), first)
    period_schema.open_period(conn, second, opened_by="the filing of cp-x",
                              dataset_id=CP, route="filing")
    assert _view_rows(conn, second, hierarchy.dataset(ED).table) == [3]


class TestTheTimeRoute:
    """Criterion 3 against the real calendar: at the first arrival after the
    claim window of the 1 November 2015 round opens, Emergency Department's
    group owes its 2015-Q4 inheritances, and Child Protection's its 2016-Q1."""

    AT = datetime(2015, 11, 1, 1, tzinfo=timezone.utc)

    def test_both_groups_are_due_for_the_periods_their_rounds_fill(self):
        due = inheritance.groups_due("child-protection", self.AT, recorded=set())
        assert ("2015-Q4", 0) in due and ("2016-Q1", 1) in due
        assert ("2016-Q1", 0) not in due

    def test_a_group_already_recorded_is_not_due_again(self):
        due = inheritance.groups_due("emergency-department", self.AT,
                                     recorded={("2015-Q4", 0)})
        assert ("2015-Q4", 0) not in due

    def test_nothing_is_due_before_the_window_opens(self):
        early = datetime(2015, 10, 1, tzinfo=timezone.utc)
        assert ("2015-Q4", 0) not in inheritance.groups_due("child-protection", early,
                                                             recorded=set())

    def test_a_calendar_whose_collections_share_one_offset_owes_nothing_by_time(self):
        """Criterion 4: Birth Registrations' calendar has one collection."""
        at = datetime(2026, 7, 1, tzinfo=timezone(timedelta(hours=8)))
        assert inheritance.groups_due("civil-registration", at, recorded=set()) == []


def test_the_not_owed_reason_names_the_round(monkeypatch):
    """Criterion 9: cp-case-workers is owed nothing in 2024-Q1 because it
    supplies only in the February and August rounds - never 'in February
    and August' of a quarter dated 1 February."""
    skipped, reason = inheritance._does_not_participate("cp-case-workers", "2024-Q1")
    assert skipped
    assert "supplies only in the February and August rounds" in reason
    assert schedule.round_of("2024-Q1", "cp-case-workers") == date(2023, 11, 1)
