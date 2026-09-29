"""Where one expected supply has got to (REQ-PIPE-083 criteria 6-9).

THE ORDER IS WHAT THESE PIN. A decision outranks a filing and a filing
outranks the clock: a slot with a promoted supply is not overdue however
late it was, and a slot with a supply awaiting a decision is waiting for
a PERSON rather than for a supplier. Asking the clock first is how a
queue tells somebody to chase a file that is sitting in front of them.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from qa_tools.common import asset_time
from qa_tools.common import decision_log as dl
from qa_tools.common import promotion, qa_store, slot_state, slots, supply_db
from qa_tools.common.schedule import Period

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-29T09:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-slot-state") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    return f"cp-{uuid.uuid4().hex[:12]}"


def _slot(dataset_id, name, due_at):
    return slots.Slot(
        dataset_id=dataset_id,
        period=Period(name=name, date=due_at.date()),
        due_at=due_at, grace=timedelta(hours=6),
        claim_opens_at=due_at - timedelta(days=30))


@pytest.fixture
def due_yesterday(dataset):
    now = asset_time.now()
    return _slot(dataset, f"2099-{uuid.uuid4().hex[:6]}", now - timedelta(days=1))


@pytest.fixture
def due_next_month(dataset):
    now = asset_time.now()
    return _slot(dataset, f"2099-{uuid.uuid4().hex[:6]}", now + timedelta(days=30))


def _state(conn, dataset, slot, **over):
    kwargs = dict(dataset_id=dataset, slot=slot, now=asset_time.now(),
                  filings={}, ever_delivered=True)
    kwargs.update(over)
    return slot_state.state_of(conn, **kwargs)


def _promote(conn, dataset, slot_name):
    arrival = uuid.uuid4().hex[:10]
    physical, supply = f"carers__{arrival}", f"{dataset}@{arrival}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    promotion.promote(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
        supply=supply, period=slot_name, physical_tables=[physical],
        actor="Keith", actor_kind=dl.PERSON, effective_at=WHEN)
    return supply


class TestTheClockDecidesOnlyWhereNothingElseHas:
    def test_a_slot_not_yet_due_is_quiet(self, conn, dataset, due_next_month):
        got = _state(conn, dataset, due_next_month)
        assert got.state == slot_state.NOT_YET_DUE
        assert got.needs_action is False

    def test_a_slot_past_its_grace_with_nothing_filed_is_overdue(
            self, conn, dataset, due_yesterday):
        got = _state(conn, dataset, due_yesterday)
        assert got.state == slot_state.OVERDUE
        assert got.needs_action is True

    def test_a_dataset_that_has_never_delivered_at_all_says_so(
            self, conn, dataset, due_yesterday):
        """Criterion 8, and it is a different conversation from a
        supplier who usually delivers and missed one."""
        got = _state(conn, dataset, due_yesterday, ever_delivered=False)
        assert got.state == slot_state.NEVER_SUPPLIED


class TestAFilingOutranksTheClock:
    def test_a_filed_supply_nobody_decided_on_waits_for_a_PERSON(
            self, conn, dataset, due_yesterday):
        got = _state(conn, dataset, due_yesterday,
                      filings={due_yesterday.name: {"supply_id": f"{dataset}@1"}})
        assert got.state == slot_state.AWAITING_DECISION
        assert got.supply == f"{dataset}@1"

    def test_it_is_not_reported_overdue(self, conn, dataset, due_yesterday):
        """The failure this stops: a queue telling somebody to chase a
        file that is sitting in front of them."""
        got = _state(conn, dataset, due_yesterday,
                      filings={due_yesterday.name: {"supply_id": f"{dataset}@1"}})
        assert got.state != slot_state.OVERDUE

    def test_a_held_supply_says_which_file_is_the_question(
            self, conn, dataset, due_yesterday):
        got = _state(conn, dataset, due_yesterday, held=True,
                      filings={due_yesterday.name: {"supply_id": f"{dataset}@1"}})
        assert got.state == slot_state.HELD
        assert "which file is the supply" in " ".join(got.responses)


class TestADecisionOutranksBoth:
    def test_a_promoted_slot_is_answered_however_late_it_was(
            self, conn, dataset, due_yesterday):
        supply = _promote(conn, dataset, due_yesterday.name)
        got = _state(conn, dataset, due_yesterday)
        assert got.state == slot_state.PROMOTED
        assert got.supply == supply
        assert got.needs_action is False

    def test_a_rejected_supply_reads_as_rejected(self, conn, dataset,
                                                  due_yesterday):
        from qa_tools.common import rejection
        supply = _promote(conn, dataset, due_yesterday.name)
        rejection.reject(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            supply=supply, physical_tables=[], actor="Keith",
            reason="wrong extract", effective_at=WHEN,
            from_slot=due_yesterday.name, promoted=True)
        got = _state(conn, dataset, due_yesterday)
        assert got.state == slot_state.REJECTED
        assert got.needs_action is True

    def test_a_demoted_supply_reads_as_returned_by_a_person(
            self, conn, dataset, due_yesterday):
        from qa_tools.common import rejection
        supply = _promote(conn, dataset, due_yesterday.name)
        rejection.demote(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            supply=supply, physical_tables=[], actor="Keith",
            reason="wrong file", effective_at=WHEN, from_slot=due_yesterday.name)
        got = _state(conn, dataset, due_yesterday)
        assert got.state == slot_state.RETURNED

    def test_it_names_who_decided_where_a_person_did(self, conn, dataset,
                                                      due_yesterday):
        _promote(conn, dataset, due_yesterday.name)
        assert _state(conn, dataset, due_yesterday).decided_by == "Keith"

    def test_it_names_nobody_where_a_RULE_decided(self, conn, dataset,
                                                   due_yesterday):
        """Naming the rule as though it were a person puts a decision on
        somebody who never made one."""
        arrival = uuid.uuid4().hex[:10]
        physical, supply = f"carers__{arrival}", f"{dataset}@{arrival}"
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
        conn.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
        promotion.promote(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            supply=supply, period=due_yesterday.name, physical_tables=[physical],
            actor="pipeline", actor_kind=dl.RULE, effective_at=WHEN)
        assert _state(conn, dataset, due_yesterday).decided_by is None


class TestTheTicketKeyIsStable:
    """Criterion 3, and criterion 2 rests on it: a later run has to find
    the SAME ticket, and a key carrying anything that changes between
    runs opens a second one instead."""

    def test_it_is_the_dataset_and_the_period_and_nothing_else(
            self, conn, dataset, due_yesterday):
        got = _state(conn, dataset, due_yesterday)
        assert got.key == f"{dataset}/{due_yesterday.name}"

    def test_it_does_not_change_when_the_state_does(self, conn, dataset,
                                                     due_yesterday):
        before = _state(conn, dataset, due_yesterday).key
        _promote(conn, dataset, due_yesterday.name)
        assert _state(conn, dataset, due_yesterday).key == before


class TestEveryStateNamesItsResponses:
    """Criterion 9. Naming is all this does - the reconciler offers no
    buttons, because a route that does nothing is worse than none."""

    def test_every_state_that_needs_action_offers_at_least_one(self):
        for state in slot_state.NEEDS_ACTION:
            assert slot_state.RESPONSES.get(state), state

    def test_a_finished_slot_offers_none(self):
        assert slot_state.RESPONSES[slot_state.PROMOTED] == ()
        assert slot_state.RESPONSES[slot_state.NOT_YET_DUE] == ()

    def test_every_state_has_an_entry(self):
        """A state with no entry renders an empty list of responses,
        which reads as "nothing you can do" rather than as an oversight
        - so a new state added without one is a silent gap.

        THE STATES ARE LISTED RATHER THAN DERIVED. The first version of
        this test collected them with a clever comprehension over the
        module's uppercase names, and a mixed `and`/`or` in it made the
        set wrong in a way that still passed. A list somebody has to
        edit is the point: adding a state should make this test fail
        until its responses are written."""
        for state in (slot_state.NOT_YET_DUE, slot_state.OVERDUE,
                       slot_state.NEVER_SUPPLIED, slot_state.AWAITING_DECISION,
                       slot_state.RETURNED, slot_state.HELD,
                       slot_state.PROMOTED, slot_state.REJECTED,
                       slot_state.SUBSTITUTED, slot_state.INHERITED):
            assert state in slot_state.RESPONSES, state
