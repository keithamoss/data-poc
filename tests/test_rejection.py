"""REQ-PIPE-076 - rejection and un-decide are a person's decisions.

"...so that staging is a work list rather than a graveyard." The queue
an operator looks at should hold supplies nobody has decided on, which
means a decided supply has to LEAVE it - and stay gone.

THE BAR ON AUTOMATIC PROMOTION IS THE SUBTLE PART, and criteria 11 and
12 pin exactly how far it reaches. It attaches to the SUPPLY a person
decided on - not the slot, not the period, not the dataset - and it
lasts for that supply's life. Get it too wide and emptying a slot by
hand quietly disables automation for that dataset forever; too narrow
and the next run promotes the very supply somebody just rejected.
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import promotion, qa_store, rejection, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-28T10:00:00+08:00"
LATER = "2026-09-28T14:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-rejection") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    return f"cp-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def period():
    return f"2099-R{uuid.uuid4().hex[:6]}"


def a_staged_table(conn, logical: str = "clients") -> str:
    physical = f"{logical}__a{uuid.uuid4().hex[:8]}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    return physical


def tables_in(conn, schema: str) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
        [schema]).fetchall()
    return {r[0] for r in rows}


class TestRejectingMovesItOutOfTheQueue:
    """Criteria 1, 2 and 10."""

    def test_the_table_lands_in_the_rejected_schema(self, conn, dataset, period):
        table = a_staged_table(conn)
        rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=WHEN, reason="duplicate extract", from_slot=period)
        assert table in tables_in(conn, supply_db.REJECTED_SCHEMA)

    def test_and_leaves_staging(self, conn, dataset, period):
        table = a_staged_table(conn)
        rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=WHEN, reason="duplicate extract", from_slot=period)
        assert table not in tables_in(conn, supply_db.STAGING_SCHEMA), \
            "staging is a work list, not a graveyard"

    def test_a_GREEN_supply_can_be_rejected(self, conn, dataset, period):
        """Criterion 2. A person may know something the checks cannot -
        the supplier sent last quarter's file again, and it passes."""
        table = a_staged_table(conn)
        rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=WHEN, from_slot=period,
                         reason="supplier resent last quarter's file")
        assert dl.decisions_for(conn, dataset)[0]["action"] == dl.REJECT


class TestOnlyAPersonRejects:
    """Criterion 3."""

    def test_an_automatic_rejection_is_refused(self, conn, dataset, period):
        table = a_staged_table(conn)
        with pytest.raises(Exception, match="person|rule"):
            rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                             dataset_id=dataset, supply=table, physical_tables=[table],
                             actor="some-rule", actor_kind=dl.RULE,
                             effective_at=WHEN, reason="looked wrong", from_slot=period)

    def test_and_nothing_moved(self, conn, dataset, period):
        table = a_staged_table(conn)
        with pytest.raises(Exception):
            rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                             dataset_id=dataset, supply=table, physical_tables=[table],
                             actor="some-rule", actor_kind=dl.RULE,
                             effective_at=WHEN, reason="looked wrong", from_slot=period)
        assert table in tables_in(conn, supply_db.STAGING_SCHEMA)


class TestTheBarOnAutomaticPromotion:
    """Criteria 7, 11 and 12 - how far a person's decision reaches."""

    def test_a_decided_supply_is_barred(self, conn, dataset, period):
        table = a_staged_table(conn)
        rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=WHEN, reason="duplicate", from_slot=period)
        assert rejection.decided_by_a_person(conn, dataset, table) is True

    def test_a_DIFFERENT_supply_of_the_same_dataset_is_NOT_barred(self, conn, dataset, period):
        """Criterion 11, and the expensive way to get this wrong: attach
        the bar to the dataset and one rejection disables automation for
        that feed forever."""
        rejected = a_staged_table(conn)
        rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=rejected,
                         physical_tables=[rejected], actor="keith",
                         effective_at=WHEN, reason="duplicate", from_slot=period)
        later = a_staged_table(conn)
        assert rejection.decided_by_a_person(conn, dataset, later) is False

    def test_an_AUTOMATIC_decision_does_not_bar_anything(self, conn, dataset, period):
        """The bar is about a PERSON having looked. A rule promoting a
        supply must not stop a rule promoting it again after a demote."""
        table = a_staged_table(conn)
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=table, period=period,
                          physical_tables=[table], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        assert rejection.decided_by_a_person(conn, dataset, table) is False

    def test_the_bar_survives_a_later_automatic_decision(self, conn, dataset, period):
        """Criterion 12 - not cleared on a later run, a resupply, or with
        time."""
        table = a_staged_table(conn)
        rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=WHEN, reason="duplicate", from_slot=period)
        assert rejection.decided_by_a_person(conn, dataset, table) is True
        # Something else happens for the same dataset, later.
        other = a_staged_table(conn)
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=other, period=period,
                          physical_tables=[other], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=LATER)
        assert rejection.decided_by_a_person(conn, dataset, table) is True


class TestRejectingAPromotedSupplyTakesOneDecision:
    """Criterion 4 - and the person does not have to demote it first.

    Making them would be asking for two entries to describe one
    intention: "not this one" is a single thing to have decided."""

    def test_the_slot_is_left_unfilled(self, conn, dataset, period):
        table = a_staged_table(conn)
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=table, period=period,
                          physical_tables=[table], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        assert dl.promoted_into(conn, dataset, period) == table
        rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=LATER, from_slot=period,
                         reason="wrong quarter's file, spotted after promotion",
                         promoted=True)
        assert dl.promoted_into(conn, dataset, period) is None

    def test_and_it_is_ONE_decision_not_two(self, conn, dataset, period):
        table = a_staged_table(conn)
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=table, period=period,
                          physical_tables=[table], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        before = len(dl.decisions_for(conn, dataset))
        rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=LATER, from_slot=period,
                         reason="wrong quarter's file", promoted=True)
        assert len(dl.decisions_for(conn, dataset)) == before + 1


class TestDemoteReturnsItToTheQueue:
    """Criterion 5. The refusal while a LATER period stands on this
    supply is REQ-PIPE-084 criterion 11's and is not built here - 084 is
    a separate requirement in a later sprint."""

    def test_the_table_goes_back_to_staging(self, conn, dataset, period):
        table = a_staged_table(conn)
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=table, period=period,
                          physical_tables=[table], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        rejection.demote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=LATER, from_slot=period,
                         reason="want another look before this counts")
        assert table in tables_in(conn, supply_db.STAGING_SCHEMA)

    def test_and_the_slot_is_unfilled(self, conn, dataset, period):
        table = a_staged_table(conn)
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=table, period=period,
                          physical_tables=[table], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        rejection.demote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=LATER, from_slot=period,
                         reason="want another look")
        assert dl.promoted_into(conn, dataset, period) is None

    def test_a_demoted_supply_does_NOT_promote_itself_again(self, conn, dataset, period):
        """The point of criterion 5 read with criterion 7: it comes back
        to the PERSON, not to the next automatic run."""
        table = a_staged_table(conn)
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=table, period=period,
                          physical_tables=[table], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        rejection.demote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=LATER, from_slot=period,
                         reason="want another look")
        may, why = promotion.should_promote(
            status="green", slot_filled=False, held_without_slot=False,
            has_active_checks=True,
            decided_by_a_person=rejection.decided_by_a_person(conn, dataset, table))
        assert may is False and "person" in why.lower()


class TestTellingAnUndecidedSupplyFromAReturnedOne:
    """Criterion 6."""

    def test_an_untouched_supply_is_awaiting_a_decision(self, conn, dataset):
        table = a_staged_table(conn)
        assert rejection.staged_state(conn, dataset, table) == "awaiting-decision"

    def test_a_returned_one_says_so(self, conn, dataset, period):
        table = a_staged_table(conn)
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=table, period=period,
                          physical_tables=[table], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        rejection.demote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=LATER, from_slot=period,
                         reason="want another look")
        assert rejection.staged_state(conn, dataset, table) == "returned-by-a-person"


class TestARedSupplyNobodyDecidedOnStaysPut:
    """Criterion 8 - red is not the same as rejected, and only a person
    rejects. A red supply sitting in staging is the queue doing its job."""

    def test_it_is_still_in_staging(self, conn, dataset):
        table = a_staged_table(conn)
        assert table in tables_in(conn, supply_db.STAGING_SCHEMA)
        assert table not in tables_in(conn, supply_db.REJECTED_SCHEMA)

    def test_and_reads_as_awaiting_a_decision(self, conn, dataset):
        table = a_staged_table(conn)
        assert rejection.staged_state(conn, dataset, table) == "awaiting-decision"


class TestAReversalKeepsBothEntries:
    """Criterion 9 - the log is append-only, so a reversal is a new
    entry rather than an edit. Verified rather than assumed."""

    def test_both_the_rejection_and_its_reversal_are_kept(self, conn, dataset, period):
        table = a_staged_table(conn)
        rejection.reject(conn, agency_id=AGENCY, collection_id=COLLECTION,
                         dataset_id=dataset, supply=table, physical_tables=[table],
                         actor="keith", effective_at=WHEN, from_slot=period,
                         reason="thought it was a duplicate")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=table, period=period,
                          physical_tables=[table], actor="keith",
                          actor_kind=dl.PERSON, effective_at=LATER,
                          reason="it was not a duplicate after all",
                          from_schema=supply_db.REJECTED_SCHEMA)
        actions = [e["action"] for e in dl.decisions_for(conn, dataset)]
        assert dl.REJECT in actions and dl.PROMOTE in actions
        assert len(actions) == 2, "a reversal is a new entry, never an edit"
