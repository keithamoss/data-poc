"""A person's promote goes only into the period the supply is filed to
(post-build-review #173, fix 1; Keith, 2026-10-13: "there should be no way
to move things into a period and then skip doing checks").

A supply's QA runs against the period it is FILED to, so promoting it
anywhere else - or promoting one filed nowhere - puts data into a period
nothing checked it against. Judged in decision_log, so every door (the
terminal, the flags, a GitHub comment, scripted playback) gets it.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

import filing_support
from qa_tools.common import (assignment, decision_log as dl, filing_decisions as fd,
                              hierarchy, inheritance, people, qa_store, schedule, supply_db)

WHEN = "2026-09-29T09:00:00+08:00"
REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-promote-requires-filing") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def actor():
    return people.person_by_email(REAL_PERSON)


@pytest.fixture
def dataset():
    return hierarchy.dataset("cp-carers")


@pytest.fixture
def periods(monkeypatch):
    tag = uuid.uuid4().hex[:6]
    names = (f"2099-P{tag}", f"2099-Q{tag}")
    order = {names[0]: date(2099, 1, 1), names[1]: date(2099, 4, 1)}
    for mod in (schedule, inheritance.schedule):
        monkeypatch.setattr(mod, "date_of", lambda name, ds: order.get(name))
    return names


def _staged(conn, dataset):
    arrival = uuid.uuid4().hex[:10]
    physical = f"{dataset.table}__{arrival}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    return f"{dataset.dataset_id}@{arrival}"


def _file(dataset, supply, slot):
    filing_support.file(assignment.Assignment(
        dataset_id=dataset.dataset_id, supply_id=supply, slot=slot,
        branch=assignment.HELD if slot is None else assignment.OPEN_UNFILLED,
        considered=(slot,) if slot else (),
        received_at=datetime(2099, 1, 1, 2, tzinfo=timezone.utc)))


def _promote(conn, dataset, actor, supply, period):
    return fd.apply(fd.Request(operation=fd.PROMOTE, dataset_id=dataset.dataset_id,
                                actor=actor, reason="looked at it", period=period,
                                supply=supply), effective_at=WHEN, conn=conn)


class TestAPromotionGoesOnlyWhereTheSupplyIsFiled:

    def test_a_held_supply_is_refused_naming_its_way_out(self, conn, dataset, actor, periods):
        first, _ = periods
        supply = _staged(conn, dataset)
        _file(dataset, supply, None)
        with pytest.raises(dl.DecisionRefused, match="held") as refused:
            _promote(conn, dataset, actor, supply, first)
        assert "reject" in str(refused.value).lower()
        assert dl.promoted_into(conn, dataset.dataset_id, first) != supply

    def test_a_supply_never_filed_is_refused(self, conn, dataset, actor, periods):
        first, _ = periods
        supply = _staged(conn, dataset)
        with pytest.raises(dl.DecisionRefused, match="not filed"):
            _promote(conn, dataset, actor, supply, first)

    def test_a_supply_filed_elsewhere_is_told_to_re_file_it(self, conn, dataset, actor, periods):
        first, second = periods
        supply = _staged(conn, dataset)
        _file(dataset, supply, first)
        with pytest.raises(dl.DecisionRefused, match=f"filed to {first}") as refused:
            _promote(conn, dataset, actor, supply, second)
        assert "re-file" in str(refused.value)

    def test_its_own_period_is_allowed(self, conn, dataset, actor, periods):
        first, _ = periods
        supply = _staged(conn, dataset)
        _file(dataset, supply, first)
        assert _promote(conn, dataset, actor, supply, first).changed
        assert dl.promoted_into(conn, dataset.dataset_id, first) == supply
