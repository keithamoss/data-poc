"""The promotion panel's and the qualifier's change points (REQ-DASH-197
criteria 10, 11, 21 and 22; REQ-DASH-198 criteria 3, 5, 13 and 14).

THE WALK IS HELD AGAINST THE READERS. pipeline/promotion_timeline.py
answers every date from what it read once; promotion_state answers one
instant at a time in SQL. Each change point is checked against the SQL
answer at its own instant - including a history where promotion order
and receipt order diverge - so the walk cannot quietly become a second
rule.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

import filing_support
from pipeline import promotion_timeline, slot_timeline
from qa_tools.common import (asset_time, assignment, promotion_state, qa_store,
                              schedule, supply_db)
from qa_tools.common import decision_log as dl

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-promotion-timeline") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    return f"cp-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def periods(monkeypatch):
    tag = uuid.uuid4().hex[:6]
    names = [f"2099-{n}{tag}" for n in "ABC"]
    dates = {n: date(2099, 1 + i * 2, 1) for i, n in enumerate(names)}
    monkeypatch.setattr(schedule, "date_of", lambda name, ds: dates.get(name))
    return names


def _at(month, day=1, hour=2):
    return datetime(2099, month, day, hour, tzinfo=timezone.utc)


def _file(dataset_id, supply_id, slot, received_at):
    filing_support.file(assignment.Assignment(
        dataset_id=dataset_id, supply_id=supply_id, slot=slot,
        branch=assignment.OPEN_UNFILLED, considered=(slot,) if slot else (),
        received_at=received_at))


def _table_for(supply_id):
    return "carers__" + supply_id.split("@")[-1]


def _promote(conn, dataset_id, supply, period, at):
    from qa_tools.common import promotion
    physical = _table_for(supply)
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"."{physical}" '
                 "(id integer)")
    promotion.promote(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset_id,
        supply=supply, period=period, physical_tables=[physical], actor="tester",
        actor_kind=dl.PERSON, effective_at=at.isoformat())


def _substitute(conn, dataset, period, stands_on, supply, at):
    from qa_tools.common import substitution
    substitution.substitute(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
        logical_table="carers", period=period, stands_on=stands_on, supply=supply,
        actor="Keith", reason="no extract is coming", effective_at=at.isoformat())


def _de_substitute(conn, dataset, period, at):
    from qa_tools.common import substitution
    substitution.de_substitute(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
        logical_table="carers", period=period, actor="Keith",
        reason="the real extract arrived", effective_at=at.isoformat(), confirmed=True)


def _timeline(conn, dataset):
    return promotion_timeline.for_dataset(
        dataset, slot_timeline.for_dataset(dataset, conn=conn), conn=conn)


def _sql_answer(conn, dataset, on):
    end = asset_time.end_of_day(date.fromisoformat(on))
    st = promotion_state.state_for(dataset, conn, as_at=end)
    return (st.promoted_supply, st.promoted_period, st.arrived_supply,
            st.arrived_period, st.why_not, list(st.arrived_files))


def _point_answer(p):
    promoted, arrived = p["promoted"] or {}, p["arrived"] or {}
    return (promoted.get("supply"), promoted.get("period"), arrived.get("supply"),
            arrived.get("period"), p["whyNot"], arrived.get("files") or [])


def _assert_agrees(conn, dataset, got):
    assert got["points"], "precondition: the history has change points"
    for p in got["points"]:
        assert _point_answer(p) == _sql_answer(conn, dataset, p["on"]), p["on"]
    for e in got["standing"]:
        end = asset_time.end_of_day(date.fromisoformat(e["on"]))
        si = promotion_state.standing_in(conn, dataset, as_at=end, period=e["period"])
        assert (si.as_record() if si else None) == e["standingIn"], (e["on"], e["period"])


class TestEveryChangePointAgreesWithTheReaders:
    """Criterion 22, on a history in which promotion order and receipt
    order diverge - the case the walk is likeliest to get wrong."""

    def test_promotion_order_and_receipt_order_diverge(self, conn, dataset, periods):
        first, second, third = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _file(dataset, f"{dataset}@2", second, _at(3))
        _promote(conn, dataset, f"{dataset}@2", second, _at(4))
        _promote(conn, dataset, f"{dataset}@1", first, _at(5))
        _file(dataset, f"{dataset}@3", third, _at(6))
        got = _timeline(conn, dataset)
        _assert_agrees(conn, dataset, got)
        # The older supply, promoted later, is what downstream reads.
        assert promotion_timeline.at(got["points"], "2099-05-20")["promoted"]["supply"] \
            == f"{dataset}@1"

    def test_the_newest_change_point_is_today_state(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 2))
        _file(dataset, f"{dataset}@2", second, _at(3))
        newest = _timeline(conn, dataset)["points"][-1]
        now = promotion_state.state_for(dataset, conn)
        assert _point_answer(newest)[:5] == (now.promoted_supply, now.promoted_period,
                                             now.arrived_supply, now.arrived_period,
                                             now.why_not)


class TestOnlyChangesAreEmbedded:
    """Criteria 11 and 21: a change point only where the answer differs, at
    most one per asset day, so the size grows with decisions and filings,
    never with the dates a reader can pick."""

    def test_at_most_one_point_per_day_and_none_repeated(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 1, 5))
        _file(dataset, f"{dataset}@2", second, _at(3))
        _promote(conn, dataset, f"{dataset}@2", second, _at(3, 1, 6))
        points = _timeline(conn, dataset)["points"]
        days = [p["on"] for p in points]
        assert len(days) == len(set(days))
        bare = [_point_answer(p) for p in points]
        assert all(a != b for a, b in zip(bare, bare[1:]))

    def test_a_change_that_reverts_the_same_day_embeds_nothing(
            self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(2))
        _substitute(conn, dataset, second, first, f"{dataset}@1", _at(4, 1, 3))
        _de_substitute(conn, dataset, second, _at(4, 1, 5))
        assert _timeline(conn, dataset)["standing"] == []


class TestEachPointNamesTheDecisionsThatProducedIt:
    """Criterion 9: each with its effective and recorded instants, so the
    page can tell a decision recorded after the date on show."""

    def test_a_promotion_is_carried_on_its_day(self, conn, dataset, periods):
        first, _, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(2))
        point = promotion_timeline.at(_timeline(conn, dataset)["points"], "2099-02-01")
        actions = [d["action"] for d in point["decisions"]]
        assert dl.PROMOTE in actions
        assert all(d["at"] and d["recordedAt"] for d in point["decisions"])


class TestAStandInIsPerPeriodAndSaysHowItEnded:
    """REQ-DASH-198 criteria 1, 3 and 14."""

    def test_removed(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(2))
        _substitute(conn, dataset, second, first, f"{dataset}@1", _at(4))
        _de_substitute(conn, dataset, second, _at(6))
        got = _timeline(conn, dataset)
        _assert_agrees(conn, dataset, got)
        opened = [e for e in got["standing"] if e["standingIn"]]
        assert len(opened) == 1
        assert opened[0]["period"] == second
        assert opened[0]["since"] == {"how": "removed", "on": "2099-06-01"}
        # Where its drill lands: the day the supply it stands on was promoted.
        assert opened[0]["earnedOn"] == "2099-02-01"

    def test_replaced(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(2))
        _substitute(conn, dataset, second, first, f"{dataset}@1", _at(4))
        _de_substitute(conn, dataset, second, _at(6))
        _file(dataset, f"{dataset}@2", second, _at(6))
        _promote(conn, dataset, f"{dataset}@2", second, _at(6, 1, 3))
        opened = [e for e in _timeline(conn, dataset)["standing"] if e["standingIn"]]
        assert opened[0]["since"]["how"] == "replaced"


class TestTheBootstrappedHistoryAgreesWithTheReaders:
    """Criterion 22 on the deployment's real history, every dataset."""

    def test_every_dataset(self, deployment_history):
        from qa_tools.common import hierarchy
        with supply_db.connect(read_only=True, label="test-promotion-timeline") as c:
            ids = [d.dataset_id for d in hierarchy.all_datasets()]
            assert ids, "precondition: the hierarchy names datasets"
            seen = 0
            for dataset in ids:
                got = promotion_timeline.for_dataset(
                    dataset, slot_timeline.for_dataset(dataset, conn=c), conn=c)
                if got["points"]:
                    seen += 1
                    _assert_agrees(c, dataset, got)
            assert seen, "precondition: the bootstrapped history has change points"


class TestTheWalkCoversEveryReason:
    """The critic's coverage gaps (post-build-review #165): an open contest
    and a supersession, held against the SQL readers like every other point."""

    def test_an_open_contest(self, conn, dataset, periods):
        from qa_tools.common import filing
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 1, 5))
        when = _at(3)
        pair = f"{dataset}@{asset_time.arrival_key(when)}#1"
        delivery = f"pytest-{dataset}-pair"
        filing_support.ensure_delivery(delivery, dataset, when, filename="a.csv")
        filing_support.ensure_delivery(delivery, dataset, _at(3, 1, 3), filename="b.csv")
        filing.record(assignment.Assignment(
            dataset_id=dataset, supply_id=pair, slot=second, branch=assignment.OPEN_UNFILLED,
            considered=(second,), received_at=when), delivery)
        got = _timeline(conn, dataset)
        _assert_agrees(conn, dataset, got)
        assert got["points"][-1]["whyNot"] == promotion_state.TWO_FILES

    def test_a_supersession(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 1, 5))
        _file(dataset, f"{dataset}@2", second, _at(3))
        # The decision alone, which is all either reader reads: supersession's
        # own route resolves the dataset in the hierarchy and moves tables.
        with dl.apply_decision(conn, dl.Decision(
                agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
                action=dl.SUPERSEDE, supply=f"{dataset}@2", actor="Keith",
                actor_kind=dl.PERSON, effective_at=_at(4).isoformat(), from_slot=second,
                reason="set aside")):
            pass
        got = _timeline(conn, dataset)
        _assert_agrees(conn, dataset, got)
        assert got["points"][-1]["whyNot"] == promotion_state.SUPERSEDED
