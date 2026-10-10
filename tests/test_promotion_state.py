"""What arrived versus what is promoted (REQ-DASH-056), from records.

THE DISTINCTION IS THE PRODUCT. A data engineer triaging a red dataset
cannot tell "their latest file is bad" from "the data everyone
downstream is using is bad", and those call for opposite responses -
the first is a supplier's problem with nothing changed for any reader,
the second is an incident.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

import filing_support
from qa_tools.common import decision_log as dl
from qa_tools.common import (assignment, promotion, promotion_state,
                              qa_store, rejection, schedule, supply_db)

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-29T09:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-promotion-state") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    return f"cp-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def periods(monkeypatch):
    tag = uuid.uuid4().hex[:6]
    names = [f"2099-{n}{tag}" for n in "AB"]
    dates = {n: date(2099, 1 + i * 2, 1) for i, n in enumerate(names)}
    monkeypatch.setattr(schedule, "date_of", lambda name, ds: dates.get(name))
    return names


def _file(dataset_id, supply_id, slot):
    """One recorded filing, by the ordinary route."""
    filing_support.file(assignment.Assignment(
        dataset_id=dataset_id, supply_id=supply_id, slot=slot,
        branch=assignment.OPEN_UNFILLED, considered=(slot,) if slot else ()))


def _stage(conn, physical):
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')


def _table_for(supply_id):
    """A SUPPLY ID IS NOT A TABLE NAME, and the two are deliberately
    different strings. `cp-carers@202608010100000000` is how filings and
    decisions name a supply; `cp_carers__202608010100000000` is what the
    warehouse can call a table, because dbt and Soda write the name into
    their own SQL unquoted. promote() takes both, and conflating them in
    a test is how the first version of this file failed."""
    return "carers__" + supply_id.split("@")[-1].replace("-", "_")


def _promote(conn, dataset_id, supply, period):
    physical = _table_for(supply)
    _stage(conn, physical)
    promotion.promote(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset_id,
        supply=supply, period=period, physical_tables=[physical], actor="tester",
        actor_kind=dl.PERSON, effective_at=WHEN)


class TestItIsQuietWhenTheyAgree:
    """Criterion 3, and it is the ordinary state of a healthy dataset -
    a section saying "these are the same" on thirty datasets is exactly
    the noise this requirement's own constraint forbids."""

    def test_differs_is_false_when_the_latest_arrival_is_promoted(
            self, conn, dataset, periods):
        first, _ = periods
        supply = f"{dataset}@1"
        _file(dataset, supply, first)
        _promote(conn, dataset, supply, first)
        state = promotion_state.state_for(dataset, conn)
        assert state.differs is False
        assert state.as_record()["differs"] is False

    def test_nothing_arrived_at_all_is_not_a_difference(self, conn, dataset):
        assert promotion_state.state_for(dataset, conn).differs is False


class TestItShowsBothWhenTheyDiffer:
    """Criteria 1 and 2."""

    def test_both_supplies_are_carried(self, conn, dataset, periods):
        first, second = periods
        promoted, arrived = f"{dataset}@1", f"{dataset}@2"
        _file(dataset, promoted, first)
        _promote(conn, dataset, promoted, first)
        _file(dataset, arrived, second)
        record = promotion_state.state_for(dataset, conn).as_record()
        assert record["differs"] is True
        assert record["promoted"]["supply"] == promoted
        assert record["arrived"]["supply"] == arrived

    def test_each_carries_its_own_period(self, conn, dataset, periods):
        first, second = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        _file(dataset, f"{dataset}@2", second)
        record = promotion_state.state_for(dataset, conn).as_record()
        assert record["promoted"]["period"] == first
        assert record["arrived"]["period"] == second


class TestItSaysWhyTheArrivalIsNotPromoted:
    """Criterion 4's three reasons, and they are three different next
    actions: wait, nothing to do, or go and fix the schedule."""

    def test_awaiting_a_decision(self, conn, dataset, periods):
        first, second = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        _file(dataset, f"{dataset}@2", second)
        state = promotion_state.state_for(dataset, conn)
        assert state.why_not == promotion_state.AWAITING_DECISION
        assert "nobody has decided" in state.explanation

    def test_rejected(self, conn, dataset, periods):
        first, second = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        arrived = f"{dataset}@2"
        _file(dataset, arrived, second)
        _stage(conn, _table_for(arrived))
        rejection.reject(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            supply=arrived, physical_tables=[_table_for(arrived)], actor="Keith",
            reason="wrong extract", effective_at=WHEN, from_slot=second)
        state = promotion_state.state_for(dataset, conn)
        assert state.why_not == promotion_state.REJECTED
        assert "rejected" in state.explanation

    def test_no_slot_could_be_claimed(self, conn, dataset, periods):
        first, _ = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        _file(dataset, f"{dataset}@2", None)
        state = promotion_state.state_for(dataset, conn)
        assert state.why_not == promotion_state.NO_SLOT
        assert "no slot" in state.explanation

    def test_superseded_by_a_later_supply_in_the_same_period(
            self, conn, dataset, periods):
        """Not one of the criterion's three by name, and it is a real
        fourth state: the arrival was filed to a period another supply
        has since been promoted into."""
        first, second = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        _file(dataset, f"{dataset}@2", second)
        _promote(conn, dataset, f"{dataset}@2", second)
        _file(dataset, f"{dataset}@3", second)
        state = promotion_state.state_for(dataset, conn)
        assert state.why_not == promotion_state.SUPERSEDED


class TestAPromotionSinceTakenBackOutIsNotPromoted:
    """A demote leaves the period holding nothing, and the page must not
    keep presenting the supply as what everyone downstream reads."""

    def test_the_promoted_side_goes_empty(self, conn, dataset, periods):
        first, _ = periods
        supply = f"{dataset}@1"
        _file(dataset, supply, first)
        _promote(conn, dataset, supply, first)
        rejection.demote(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            supply=supply, physical_tables=[], actor="Keith",
            reason="wrong file", effective_at=WHEN, from_slot=first)
        record = promotion_state.state_for(dataset, conn).as_record()
        assert record["promoted"] is None


class TestItReadsRecordsAndNeverSupplyRows:
    """Criterion 5, held the same way outstanding.py's own NFR is: the
    claim is about WHICH schema, not about whether a connection exists.

    A SHORTER LIST THAN outstanding.py's, and the difference is real
    rather than an oversight: this module legitimately says "rejected"
    and "promoted" as DECISIONS - they are two of the actions it reads
    out of the log - where those words in outstanding.py could only ever
    be schema names. What stays forbidden is every schema that holds the
    extract itself."""

    FORBIDDEN = ("staging", "period_", "sample")

    def test_it_names_no_schema_that_holds_supply_rows(self):
        import inspect
        source = inspect.getsource(promotion_state)
        named = [s for s in self.FORBIDDEN if s in source]
        assert not named, f"promotion_state.py names {named}"


class TestAPeriodStandingInOnAnEarlierOne:
    """REQ-DASH-085 and REQ-DASH-100's data side.

    The two are identical in SQL - a view in a period's schema pointing
    at an earlier promoted table - and mean opposite things about
    whether anybody failed. Keeping them apart is the whole point.
    """

    def _substitute(self, conn, dataset, period, stands_on, supply):
        from qa_tools.common import substitution
        substitution.substitute(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            logical_table="carers", period=period, stands_on=stands_on,
            supply=supply, actor="Keith",
            reason="the supplier confirmed no extract is coming", effective_at=WHEN)

    def test_a_period_holding_its_own_supply_stands_in_on_nothing(
            self, conn, dataset, periods):
        first, _ = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        assert promotion_state.state_for(dataset, conn).standing_in is None

    def test_a_substitution_reads_as_SUBSTITUTED_at_warning(
            self, conn, dataset, periods):
        first, second = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        self._substitute(conn, dataset, second, first, f"{dataset}@1")
        st = promotion_state.state_for(dataset, conn).standing_in
        assert st.kind == promotion_state.SUBSTITUTED
        assert st.level == "warning"
        assert st.by_a_person is True
        assert st.decided_by == "Keith"
        assert "no extract is coming" in st.reason

    def test_an_inheritance_reads_as_INHERITED_at_information(
            self, conn, dataset, periods):
        from qa_tools.common import inheritance
        first, second = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        entry = type("E", (), {"agency_id": AGENCY, "collection_id": COLLECTION,
                                "dataset_id": dataset})()
        inheritance._record(conn, entry, action=dl.INHERIT, supply=f"{dataset}@1",
                             period=second, stands_on=first,
                             reason="supplied annually, no quarterly file is due",
                             effective_at=WHEN)
        st = promotion_state.state_for(dataset, conn).standing_in
        assert st.kind == promotion_state.INHERITED
        assert st.level == "information"
        assert st.by_a_person is False

    def test_an_inheritance_names_nobody_as_its_decider(self, conn, dataset,
                                                         periods):
        """The rule is not a person, and recording it as one would put a
        decision on somebody who never made it."""
        from qa_tools.common import inheritance
        first, second = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        entry = type("E", (), {"agency_id": AGENCY, "collection_id": COLLECTION,
                                "dataset_id": dataset})()
        inheritance._record(conn, entry, action=dl.INHERIT, supply=f"{dataset}@1",
                             period=second, stands_on=first, reason="not due",
                             effective_at=WHEN)
        assert promotion_state.state_for(dataset, conn).standing_in.decided_by is None

    def test_a_removed_substitution_stops_standing_in(self, conn, dataset, periods):
        from qa_tools.common import substitution
        first, second = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        self._substitute(conn, dataset, second, first, f"{dataset}@1")
        substitution.de_substitute(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            logical_table="carers", period=second, actor="Keith",
            reason="the real extract arrived", effective_at=WHEN, confirmed=True)
        assert promotion_state.state_for(dataset, conn).standing_in is None

    def test_the_two_levels_are_distinct(self):
        """Criterion 7 of one and 11 of the other, asserted as one
        claim: a reader must be able to tell a person's decision about a
        missing supply from a dataset behaving as agreed."""
        levels = promotion_state.STANDING_IN_LEVEL
        assert levels[promotion_state.SUBSTITUTED] != levels[promotion_state.INHERITED]

    def test_the_record_carries_everything_the_page_needs(self, conn, dataset,
                                                           periods):
        first, second = periods
        _file(dataset, f"{dataset}@1", first)
        _promote(conn, dataset, f"{dataset}@1", first)
        self._substitute(conn, dataset, second, first, f"{dataset}@1")
        record = promotion_state.state_for(dataset, conn).as_record()["standingIn"]
        assert set(record) == {"kind", "level", "period", "standsOn", "supply",
                                "decidedBy", "reason", "byAPerson"}
