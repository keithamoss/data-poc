"""REQ-PIPE-105 criterion 7 - newest wins, by PROMOTION time.

"...apply 'newest wins' only to PROMOTED supplies, and decide which is
newest by PROMOTION time rather than by arrival time."

TWO CLAIMS, AND THE SECOND IS THE ONE THAT CHANGES BEHAVIOUR.
period_schema.newest() orders by the ARRIVAL key parsed out of a
physical table name, which is the right answer to a different question.
Arrival order and promotion order come apart the moment a person is
involved: a supply that arrived on Tuesday and was held for a decision
until Friday is NEWER, as the period sees it, than one that arrived on
Wednesday and promoted itself immediately. The period holds what was
decided into it, in the order it was decided.

Deciding by arrival would silently prefer the Wednesday file - a
version nobody chose - over the one somebody actually looked at and
promoted.
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import promotion, qa_store, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-newest-promoted") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    return f"cp-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def period():
    return f"2099-N{uuid.uuid4().hex[:6]}"


def a_staged_table(conn, arrival_key: str) -> str:
    """A staged table whose physical name carries a given arrival key."""
    physical = f"clients__{arrival_key}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    return physical


class TestNewestMeansMostRecentlyPROMOTED:

    def test_the_later_promotion_wins_even_though_it_arrived_first(
            self, conn, dataset, period):
        """The case that separates the two orderings, and the reason
        this criterion exists: a supply held for a decision and promoted
        late is what the period holds."""
        arrived_first = a_staged_table(conn, "a20260201000000")
        arrived_second = a_staged_table(conn, "a20260202000000")

        # The one that arrived SECOND promotes first.
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=arrived_second, period=period,
                          physical_tables=[arrived_second], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at="2026-02-02T09:00:00+08:00")
        # The one that arrived FIRST was held, and promotes later.
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=arrived_first, period=period,
                          physical_tables=[arrived_first], actor="keith",
                          actor_kind=dl.PERSON, effective_at="2026-02-05T09:00:00+08:00",
                          reason="checked by hand, this is the one we want")

        assert promotion.newest_promoted(conn, dataset, period) == arrived_first

    def test_and_arrival_order_would_have_given_the_other_answer(self, conn):
        """Pinned so the difference is not theoretical. period_schema's
        own newest() is the arrival-ordered answer, and it is still the
        right answer to its own question."""
        from qa_tools.common import period_schema

        assert period_schema.newest(["clients__a20260201000000",
                                     "clients__a20260202000000"]) == \
            "clients__a20260202000000"

    def test_a_period_nothing_was_promoted_into_has_no_newest(self, conn, dataset, period):
        assert promotion.newest_promoted(conn, dataset, period) is None

    def test_a_single_promotion_is_its_own_newest(self, conn, dataset, period):
        only = a_staged_table(conn, "a20260201000000")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=only, period=period,
                          physical_tables=[only], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at="2026-02-01T09:00:00+08:00")
        assert promotion.newest_promoted(conn, dataset, period) == only


class TestItOnlyEverConsidersPromotedSupplies:
    """The criterion's first half - newest-wins applies to PROMOTED
    supplies only. A staged one has not been chosen by anybody."""

    def test_a_staged_supply_is_not_a_candidate(self, conn, dataset, period):
        promoted = a_staged_table(conn, "a20260201000000")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=promoted, period=period,
                          physical_tables=[promoted], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at="2026-02-01T09:00:00+08:00")
        # Newer by arrival, but nobody promoted it.
        a_staged_table(conn, "a20260209000000")
        assert promotion.newest_promoted(conn, dataset, period) == promoted
