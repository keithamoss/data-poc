"""The promotion panel's answers as at an instant (REQ-DASH-197, REQ-DASH-198).

A PAST DATE ASKS A PAST QUESTION. The panel compares what was promoted
with what had arrived, and the qualifier says what a period stood on;
both used to be answered as at the build, so a past view warned about
files that had not arrived yet and named periods that had not happened.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

import filing_support
from qa_tools.common import assignment, promotion_state, qa_store, schedule, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-promotion-as-at") as c:
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


def _at(month, day=1, hour=9):
    return datetime(2099, month, day, hour, tzinfo=timezone.utc)


def _file(dataset_id, supply_id, slot, received_at):
    filing_support.file(assignment.Assignment(
        dataset_id=dataset_id, supply_id=supply_id, slot=slot,
        branch=assignment.OPEN_UNFILLED, considered=(slot,) if slot else (),
        received_at=received_at))


class TestALaterReFileDoesNotMakeAnOlderSupplyTheLatestArrival:
    """Criterion 3, written first against today's state_for(): the
    architect suspected the latest arrival was taken from the newest
    filing ROW, which a re-file of an older supply writes last."""

    def test_the_newer_supply_stays_the_latest_arrival(self, conn, dataset, periods):
        first, second, _ = periods
        older, newer = f"{dataset}@1", f"{dataset}@2"
        _file(dataset, older, first, _at(1))
        _file(dataset, newer, second, _at(2))
        # The older supply is re-filed AFTER the newer one arrived: a new
        # filing row, written last.
        filing_support.place(conn, dataset, older, second,
                             f"pytest-{dataset}-{older}")
        state = promotion_state.state_for(dataset, conn)
        assert state.arrived_supply == newer


def _stage(conn, physical):
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"."{physical}" '
                 "(id integer)")


def _table_for(supply_id):
    """UNIQUE TO THIS TEST'S DATASET (post-build-review #167): named from the
    supply's suffix alone, two tests on one worker both rejecting an `@2`
    collided on `rejected.carers__2`, so the suite failed only when it shared
    workers. The dataset id is a fresh uuid per test."""
    dataset, suffix = supply_id.split("@")
    tail = dataset.rsplit("-", 1)[-1]
    return f"carers__{tail}_" + suffix.replace("-", "_").replace("#", "_")


def _promote(conn, dataset_id, supply, period, at):
    from qa_tools.common import decision_log as dl
    from qa_tools.common import promotion
    physical = _table_for(supply)
    _stage(conn, physical)
    promotion.promote(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset_id,
        supply=supply, period=period, physical_tables=[physical], actor="tester",
        actor_kind=dl.PERSON, effective_at=at.isoformat())


def _reject(conn, dataset_id, supply, period, at):
    from qa_tools.common import rejection
    _stage(conn, _table_for(supply))
    rejection.reject(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset_id,
        supply=supply, physical_tables=[_table_for(supply)], actor="Keith",
        reason="wrong extract", effective_at=at.isoformat(), from_slot=period)


class TestAPastInstantSeesOnlyWhatHadHappened:
    """Criteria 1, 2 and 4: nothing filed, promoted or decided after the
    instant reaches its answer."""

    def test_a_supply_filed_after_the_instant_is_not_the_latest_arrival(
            self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 2))
        _file(dataset, f"{dataset}@2", second, _at(3))
        before = promotion_state.state_for(dataset, conn, as_at=_at(2))
        assert before.arrived_supply == f"{dataset}@1"
        assert before.differs is False
        assert promotion_state.state_for(dataset, conn).arrived_supply == f"{dataset}@2"

    def test_a_later_rejection_reads_as_awaiting_before_it(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 2))
        _file(dataset, f"{dataset}@2", second, _at(3))
        _reject(conn, dataset, f"{dataset}@2", second, _at(5))
        at_four = promotion_state.state_for(dataset, conn, as_at=_at(4))
        assert at_four.why_not == promotion_state.AWAITING_DECISION
        assert promotion_state.state_for(dataset, conn).why_not == promotion_state.REJECTED

    def test_the_promoted_supply_is_the_one_promoted_by_then(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 2))
        _file(dataset, f"{dataset}@2", second, _at(3))
        _promote(conn, dataset, f"{dataset}@2", second, _at(4))
        assert promotion_state.state_for(
            dataset, conn, as_at=_at(3, 2)).promoted_supply == f"{dataset}@1"
        assert promotion_state.state_for(
            dataset, conn, as_at=_at(4, 2)).promoted_supply == f"{dataset}@2"


class TestPromotionTimeNotReceiptOrder:
    """Criterion 1: the panel's promoted supply is the one most recently
    PROMOTED; at one instant, the later period."""

    def test_an_older_supply_promoted_later_is_the_promoted_one(
            self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _file(dataset, f"{dataset}@2", second, _at(3))
        _promote(conn, dataset, f"{dataset}@2", second, _at(4))
        _promote(conn, dataset, f"{dataset}@1", first, _at(5))
        state = promotion_state.state_for(dataset, conn, as_at=_at(6))
        assert state.promoted_supply == f"{dataset}@1"

    def test_two_promotions_at_one_instant_take_the_later_period(
            self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _file(dataset, f"{dataset}@2", second, _at(3))
        _promote(conn, dataset, f"{dataset}@2", second, _at(4))
        _promote(conn, dataset, f"{dataset}@1", first, _at(4))
        state = promotion_state.state_for(dataset, conn, as_at=_at(6))
        assert state.promoted_period == second


class TestALatestArrivalPromotedIntoItsOwnPeriod:
    """Criterion 6: the latest arrival WAS promoted - into its own period -
    and a supply promoted later into another period is what downstream reads
    most recently. Not 'not promoted', which it was."""

    def test_it_is_its_own_reason(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _file(dataset, f"{dataset}@2", second, _at(3))
        _promote(conn, dataset, f"{dataset}@2", second, _at(4))
        _promote(conn, dataset, f"{dataset}@1", first, _at(5))
        state = promotion_state.state_for(dataset, conn, as_at=_at(6))
        assert state.arrived_supply == f"{dataset}@2"
        assert state.why_not == promotion_state.PROMOTED_ELSEWHERE
        assert first in state.explanation


class TestEveryReasonHasBothTenses:
    """Criterion 19: present and past side by side, so the page never
    re-tenses a sentence itself."""

    def test_each_reason_carries_two_different_sentences(self):
        for code, pair in promotion_state.WHY_NOT.items():
            assert len(pair) == 2, code
            present, past = pair
            assert present and past and present != past, code


class TestAnOpenContestIsItsOwnReason:
    """Criterion 4: two files for one table, named by their filenames, open
    until a decision settles it."""

    def test_two_files_awaiting_a_settlement(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 2))
        pair = f"{dataset}@{_key(_at(3))}#1"
        delivery = f"pytest-{dataset}-pair"
        filing_support.ensure_delivery(delivery, dataset, _at(3), filename="a.csv")
        filing_support.ensure_delivery(delivery, dataset, _at(3, 1, 10), filename="b.csv")
        from qa_tools.common import filing
        filing.record(assignment.Assignment(
            dataset_id=dataset, supply_id=pair, slot=second,
            branch=assignment.OPEN_UNFILLED, considered=(second,),
            received_at=_at(3)), delivery)
        state = promotion_state.state_for(dataset, conn, as_at=_at(4))
        assert state.arrived_supply == pair
        assert state.why_not == promotion_state.TWO_FILES
        assert state.arrived_files == ("a.csv", "b.csv")


def _key(at):
    from qa_tools.common import asset_time
    return asset_time.arrival_key(at)


class TestTheQualifierIsAboutThePeriodOnShow:
    """REQ-DASH-198 criteria 1 and 2: a stand-in as at the instant, for the
    named period - never the newest stand-in at the build."""

    def _substitute(self, conn, dataset, period, stands_on, supply, at):
        from qa_tools.common import substitution
        substitution.substitute(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            logical_table="carers", period=period, stands_on=stands_on,
            supply=supply, actor="Keith", reason="no extract is coming",
            effective_at=at.isoformat())

    def test_a_later_stand_in_is_not_seen_before_it(self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 2))
        self._substitute(conn, dataset, second, first, f"{dataset}@1", _at(4))
        assert promotion_state.standing_in(conn, dataset, as_at=_at(3)) is None
        assert promotion_state.standing_in(conn, dataset, as_at=_at(5)).period == second

    def test_a_stand_in_for_another_period_is_not_this_periods(
            self, conn, dataset, periods):
        first, second, _ = periods
        _file(dataset, f"{dataset}@1", first, _at(1))
        _promote(conn, dataset, f"{dataset}@1", first, _at(1, 2))
        self._substitute(conn, dataset, second, first, f"{dataset}@1", _at(4))
        assert promotion_state.standing_in(conn, dataset, period=first) is None
        assert promotion_state.standing_in(conn, dataset, period=second).stands_on == first
