"""A person's promote goes only into the period the supply is filed to
(post-build-review #173, fix 1; Keith, 2026-10-13: "there should be no way
to move things into a period and then skip doing checks").

A supply's QA runs against the period it is FILED to, so promoting it
anywhere else - or promoting one filed nowhere - puts data into a period
nothing checked it against. Judged in filing_decisions, the one implementation every person's door
shares (the terminal, the flags, a GitHub comment, scripted playback).

Fix 2 of the same item: nor before its checks have run AGAINST that filing -
refused while a re-check is owed, or when no run of its own checks has
completed since it was last filed.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

import filing_support
import attempt_support
from qa_tools.common import (assignment, decision_log as dl, filing, filing_decisions as fd,
                              hierarchy, inheritance, people, qa_store, recheck, schedule,
                              supply_db)

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


def _checked(conn, dataset, supply):
    """A completed run of the supply's own checks, as its arrival leaves."""
    run_key = f"pytest-run-{uuid.uuid4().hex[:10]}"
    qa_store.record_run(conn, run_key=run_key, agency_id=dataset.agency_id,
                        collection_id=dataset.collection_id,
                        run_timestamp="2099-01-01T10:00:00+08:00", run_by=REAL_PERSON,
                        environment="sandbox")
    qa_store.set_run_purpose(conn, run_key, dataset_id=dataset.dataset_id, supply_id=supply)
    attempt_support.opened(conn, run_key)
    qa_store.complete_run(conn, run_key)
    return run_key


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
        _checked(conn, dataset, supply)
        assert _promote(conn, dataset, actor, supply, first).changed
        assert dl.promoted_into(conn, dataset.dataset_id, first) == supply


class TestNotBeforeItsChecksHaveRunAgainstThatFiling:
    """Fix 2 (L2): a re-filed or settled supply's re-check is owed until it
    runs, and its verdicts until then are the OLD period's."""

    def test_refused_while_a_re_check_is_owed(self, conn, dataset, actor, periods):
        first, _ = periods
        supply = _staged(conn, dataset)
        _file(dataset, supply, first)
        _checked(conn, dataset, supply)
        recheck.owe(conn, dataset_id=dataset.dataset_id, supply_id=supply, load_id=1)
        with pytest.raises(dl.DecisionRefused, match="re-check") as refused:
            _promote(conn, dataset, actor, supply, first)
        assert "mothman pipeline process" in str(refused.value)
        assert dl.promoted_into(conn, dataset.dataset_id, first) != supply

    def test_refused_with_no_completed_run_since_it_was_filed(
            self, conn, dataset, actor, periods):
        first, _ = periods
        supply = _staged(conn, dataset)
        _file(dataset, supply, first)
        with pytest.raises(dl.DecisionRefused, match="no run of its checks"):
            _promote(conn, dataset, actor, supply, first)

    def test_a_run_from_before_its_latest_filing_does_not_count(
            self, conn, dataset, actor, periods):
        """The run checked it against where it USED to be filed."""
        first, second = periods
        supply = _staged(conn, dataset)
        _file(dataset, supply, first)
        _checked(conn, dataset, supply)
        (delivery,) = conn.execute(
            f"SELECT delivery FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
            [dataset.dataset_id, supply]).fetchall()[0]
        filing_support.place(conn, dataset.dataset_id, supply, second, delivery)
        with pytest.raises(dl.DecisionRefused, match="no run of its checks"):
            _promote(conn, dataset, actor, supply, second)

    def test_refused_before_the_reason_is_asked(self, conn, dataset, actor, periods):
        first, _ = periods
        supply = _staged(conn, dataset)
        _file(dataset, supply, first)
        with pytest.raises(dl.DecisionRefused, match="no run of its checks"):
            fd.consequences(conn, fd.Request(
                operation=fd.PROMOTE, dataset_id=dataset.dataset_id, actor=actor,
                reason="", period=first, supply=supply))
