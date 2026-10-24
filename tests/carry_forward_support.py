"""A quarter Case Workers sits out, for the opening, warning and carry-forward
tests (REQ-PIPE-271, REQ-PIPE-280).

THE SCHEDULE'S ANSWER IS STATED, as tests/test_inheritance.py states it: three
private periods of this worker's own, Q2 and Q3 owed a Case Workers supply and
Q4 owed none, dated in that order, and Case Workers the only dataset the
opening considers - so what one test opens no other test reads. Everything
else is real: the supplies are real staged tables promoted through
promotion.promote, the period is opened through the one mechanism, and the
decisions go through the decision log.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import hierarchy, promotion, qa_store, schedule, supply_db

CASE_WORKERS = "cp-case-workers"
#: Its name, as every sentence says a dataset (Keith, 2026-10-24, K1).
NAME = "Case Workers"
REASON = "Case Workers is delivered in February and August only"
#: The Notifications check that reads cp_case_workers - a real declared read.
ASSIGNED_WORKER = ("data-asset-1.child-protection-family-support.child-protection."
                   "cp-notifications.assigned_worker_id.relationships_dbt")
KEYS = {"agency_id": "child-protection-family-support", "collection_id": "child-protection"}


@dataclass
class World:
    q2: str
    q3: str
    q4: str

    @property
    def dataset(self):
        return hierarchy.dataset(CASE_WORKERS)


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-carry-forward") as c:
        qa_store.ensure_schema(c)
        supply_db.ensure_schemas(c)
        yield c


@pytest.fixture
def world(monkeypatch) -> World:
    tag = uuid.uuid4().hex[:6]
    w = World(q2=f"2099-{tag}-Q2", q3=f"2099-{tag}-Q3", q4=f"2099-{tag}-Q4")
    order = {w.q2: date(2099, 4, 1), w.q3: date(2099, 7, 1), w.q4: date(2099, 10, 1)}
    real_not_expected, real_date_of = schedule.not_expected_periods, schedule.date_of
    monkeypatch.setattr(
        schedule, "not_expected_periods",
        lambda ds, *a, **k: ({w.q4: REASON} if ds == CASE_WORKERS
                             else real_not_expected(ds, *a, **k)))
    # CASE WORKERS' OWN PERIODS ARE ONLY THESE THREE: a real one another module
    # on this worker promoted into (2026-Q1, say) is no candidate to inherit,
    # so "nothing earlier" is true whatever else the worker's log holds.
    monkeypatch.setattr(schedule, "date_of",
                        lambda name, ds=None: order.get(name) if ds == CASE_WORKERS
                        else order.get(name) or real_date_of(name, ds))
    # hierarchy.all_datasets is NOT narrowed, as test_inheritance.py narrows it:
    # it is read through caches the real run step keeps, and a narrowed list
    # leaked into a later real run's overlay. Every other dataset takes part
    # in these private periods, so the opening inherits nothing else anyway.
    return w


def promote(conn, period: str, at: str, *, dataset_id: str = CASE_WORKERS,
            actor_kind: str = dl.RULE) -> str:
    """A real staged table for `dataset_id`, promoted into `period`; returns
    its supply id."""
    entry = hierarchy.dataset(dataset_id)
    key = "2099" + uuid.uuid4().int.__str__()[:16]
    supply = f"{dataset_id}@{key}"
    physical = f"{entry.table}__{key}"
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    conn.execute(f'INSERT INTO "{supply_db.STAGING_SCHEMA}"."{physical}" VALUES (7)')
    promotion.promote(conn, **KEYS, dataset_id=dataset_id, supply=supply, period=period,
                      physical_tables=[physical], actor="pytest",
                      actor_kind=actor_kind, effective_at=at)
    return supply


def view_reads(conn, period: str) -> str | None:
    """The physical table the period's cp_case_workers view reads, or None
    where there is no view."""
    from qa_tools.common import period_schema

    rows = conn.execute(
        "SELECT view_definition FROM information_schema.views WHERE table_schema = ? "
        "AND table_name = 'cp_case_workers'",
        [period_schema.period_schema(period)]).fetchall()
    return rows[0][0] if rows else None


def entries(conn, period: str, *actions: str) -> list[dict]:
    return [e for e in dl.decisions_for(conn, CASE_WORKERS)
            if e["to_slot"] == period and (not actions or e["action"] in actions)]
