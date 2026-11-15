"""The pair helper's own guarantee: a FREE day is free (post-build-review #354).

`free_day` picks a random day for a test's pair, skipping days that already
hold a pair. A test database also keeps every period earlier tests OPENED, and
a test that asserts its settlement opened nothing then fails whenever the
random day lands next to one - which it did, once a merge reshuffled which
modules share a worker.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import carry_forward_support
from pair_support import free_day
from qa_tools.common import period_schema, qa_store

conn = carry_forward_support.conn

#: The data asset this module's tests act for (C11, Keith 2026-11-02).
pytestmark = pytest.mark.asset("daily")


def test_a_day_next_to_an_opened_period_is_not_free(conn):
    start = date(2031, 3, 1)
    nxt = (start + timedelta(days=1)).isoformat()
    period_schema.open_period(conn, nxt, opened_by="pytest",
                              effective_at="2031-03-01T09:00:00+08:00")
    try:
        with pytest.raises(AssertionError, match="no free day"):
            free_day(conn, start, span=1)
    finally:
        conn.execute(f'DELETE FROM "{qa_store.SCHEMA}".period WHERE name = ?', [nxt])
        conn.execute(f'DROP SCHEMA IF EXISTS "{period_schema.period_schema(nxt)}" CASCADE')
