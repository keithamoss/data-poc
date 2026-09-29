"""REQ-PIPE-075 - a slot is filled only by a recorded promotion.

The spine of the supply model: a green or amber supply promotes itself
into an empty slot, everything else waits for a person, and a slot counts
as filled only where a promotion says so.

WHAT THESE TESTS PIN, beyond the obvious happy path, is the ORDERING and
the MOVE - the two things that are easy to build the other way round and
expensive to discover later:

  - criterion 9: the decision-log entry is written only AFTER the tables
    are durably in the period schema, so an interrupted promotion is
    repeated rather than skipped. Written the other way, a crash between
    the two leaves a log saying a supply was promoted and a period schema
    that does not hold it - and nothing would ever retry, because the log
    says it is done.
  - criterion 15: promotion MOVES the tables out of staging rather than
    copying them, so staging holds only supplies nobody has decided on.
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import period_schema, promotion, qa_store, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-28T10:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-promotion") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    """A dataset id nothing else in the suite has decided anything about."""
    return f"cp-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def period():
    """A period of this test's own, so its schema cannot collide."""
    return f"2099-T{uuid.uuid4().hex[:6]}"


def a_staged_table(conn, logical: str) -> str:
    """One real staged table, named the way the loader names them."""
    physical = f"{logical}__a{uuid.uuid4().hex[:8]}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    conn.execute(f'INSERT INTO "{supply_db.STAGING_SCHEMA}"."{physical}" VALUES (1)')
    return physical


def tables_in(conn, schema: str) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
        [schema]).fetchall()
    return {r[0] for r in rows}


class TestPromotionMovesRatherThanCopies:
    """Criterion 15."""

    def test_the_table_is_in_the_period_schema_afterwards(self, conn, dataset, period):
        physical = a_staged_table(conn, "clients")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=physical, period=period,
                          physical_tables=[physical], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        assert physical in tables_in(conn, period_schema.period_schema(period))

    def test_and_is_GONE_from_staging(self, conn, dataset, period):
        """The half that is easy to get wrong. A copy would pass the test
        above and leave staging holding a supply somebody has decided on,
        which is exactly what criterion 15 forbids."""
        physical = a_staged_table(conn, "clients")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=physical, period=period,
                          physical_tables=[physical], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        assert physical not in tables_in(conn, supply_db.STAGING_SCHEMA)

    def test_the_rows_survive_the_move(self, conn, dataset, period):
        physical = a_staged_table(conn, "clients")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=physical, period=period,
                          physical_tables=[physical], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        schema = period_schema.period_schema(period)
        assert conn.execute(f'SELECT count(*) FROM "{schema}"."{physical}"').fetchall()[0][0] == 1


class TestTheEntryIsWrittenLast:
    """Criterion 9 - so an interrupted promotion repeats rather than skips."""

    def test_a_failure_moving_the_tables_leaves_NO_decision(self, conn, dataset, period):
        # A table that does not exist cannot be moved, which is the
        # cheapest way to make the move fail for real rather than by
        # patching something out.
        with pytest.raises(Exception):
            promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                              dataset_id=dataset, supply="ghost__aaaaaaaa",
                              period=period, physical_tables=["ghost__aaaaaaaa"],
                              actor="promotion-gate", actor_kind=dl.RULE, effective_at=WHEN)
        assert dl.decisions_for(conn, dataset) == [], \
            "an entry written before the move would say a supply is promoted that is not"

    def test_so_the_slot_is_still_unfilled_and_the_promotion_can_be_retried(
            self, conn, dataset, period):
        with pytest.raises(Exception):
            promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                              dataset_id=dataset, supply="ghost__aaaaaaaa",
                              period=period, physical_tables=["ghost__aaaaaaaa"],
                              actor="promotion-gate", actor_kind=dl.RULE, effective_at=WHEN)
        assert dl.promoted_into(conn, dataset, period) is None


class TestPromotingTwiceChangesNothing:
    """Criterion 10."""

    def test_the_second_promotion_adds_no_entry(self, conn, dataset, period):
        physical = a_staged_table(conn, "clients")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=physical, period=period,
                          physical_tables=[physical], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        before = len(dl.decisions_for(conn, dataset))
        again = promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                                  dataset_id=dataset, supply=physical, period=period,
                                  physical_tables=[physical], actor="promotion-gate",
                                  actor_kind=dl.RULE, effective_at=WHEN)
        assert again is False, "a repeat promotion reports that it changed nothing"
        assert len(dl.decisions_for(conn, dataset)) == before


class TestASlotIsFilledOnlyByAPromotion:
    """Criterion 6, and the reason filing.filled_slots() has been a
    deliberate stub returning nothing since it was written."""

    def test_an_unfilled_slot_reads_as_unfilled(self, conn, dataset, period):
        assert promotion.filled_slots(conn, dataset) == frozenset()

    def test_a_promoted_slot_reads_as_filled(self, conn, dataset, period):
        physical = a_staged_table(conn, "clients")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=physical, period=period,
                          physical_tables=[physical], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        assert promotion.filled_slots(conn, dataset) == frozenset({period})

    def test_it_comes_from_the_LOG_rather_than_the_catalogue(self, conn, dataset, period):
        """Criterion 6 says so in as many words. A table sitting in a
        period schema that no decision promoted is not a filled slot -
        it is a table somebody put there, and reading the catalogue
        would call it filled."""
        schema = period_schema.ensure_period_schema(conn, period)
        conn.execute(f'CREATE TABLE "{schema}"."clients__aimposter" (id integer)')
        assert promotion.filled_slots(conn, dataset) == frozenset()


class TestThePeriodComesFromTheFiling:
    """Criterion 8 - promote into exactly the period the filing names,
    never re-derived at promotion time.

    Re-deriving would mean a supply filed on Monday against one period
    could land in another, because the rule that derives it reads a
    calendar that may since have gained a version. The filing is the
    decision that was made; promotion carries it out."""

    def test_it_promotes_into_the_period_it_is_given(self, conn, dataset, period):
        physical = a_staged_table(conn, "clients")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=physical, period=period,
                          physical_tables=[physical], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        assert dl.promoted_into(conn, dataset, period) == physical

    def test_and_takes_no_calendar_or_clock_to_work_one_out(self):
        """Pinned by SIGNATURE rather than by behaviour, because the way
        this criterion gets broken is somebody adding a convenience that
        derives the period when the caller did not pass one."""
        import inspect
        params = inspect.signature(promotion.promote).parameters
        assert params["period"].default is inspect.Parameter.empty, \
            "a defaultable period is a period something will derive"


class TestOneDatasetsFailureDoesNotStopTheOthers:
    """Criterion 11."""

    def test_the_others_are_still_promoted(self, conn, period):
        good_a, good_b = f"cp-{uuid.uuid4().hex[:12]}", f"cp-{uuid.uuid4().hex[:12]}"
        bad = f"cp-{uuid.uuid4().hex[:12]}"
        table_a, table_b = a_staged_table(conn, "clients"), a_staged_table(conn, "carers")
        work = [
            dict(dataset_id=good_a, supply=table_a, physical_tables=[table_a]),
            dict(dataset_id=bad, supply="ghost__deadbeef",
                 physical_tables=["ghost__deadbeef"]),
            dict(dataset_id=good_b, supply=table_b, physical_tables=[table_b]),
        ]
        promoted, failures = promotion.promote_each(
            conn, work, agency_id=AGENCY, collection_id=COLLECTION, period=period,
            actor="promotion-gate", actor_kind=dl.RULE, effective_at=WHEN)
        assert set(promoted) == {good_a, good_b}, \
            "a failure in the middle must not strand the datasets after it"

    def test_and_the_failure_is_REPORTED_rather_than_swallowed(self, conn, period):
        bad = f"cp-{uuid.uuid4().hex[:12]}"
        _, failures = promotion.promote_each(
            conn, [dict(dataset_id=bad, supply="ghost__deadbeef",
                        physical_tables=["ghost__deadbeef"])],
            agency_id=AGENCY, collection_id=COLLECTION, period=period,
            actor="promotion-gate", actor_kind=dl.RULE, effective_at=WHEN)
        assert bad in failures
        assert failures[bad], "a reported failure says something about itself"

    def test_a_failed_dataset_is_not_left_half_promoted(self, conn, period):
        bad = f"cp-{uuid.uuid4().hex[:12]}"
        promotion.promote_each(
            conn, [dict(dataset_id=bad, supply="ghost__deadbeef",
                        physical_tables=["ghost__deadbeef"])],
            agency_id=AGENCY, collection_id=COLLECTION, period=period,
            actor="promotion-gate", actor_kind=dl.RULE, effective_at=WHEN)
        assert dl.promoted_into(conn, bad, period) is None


class TestAPersonPromotesOneSupplyAtATime:
    """Criterion 14 - no operation promotes several supplies on one
    decision. Each supply gets its own entry, with its own reason, so the
    log can answer 'why was THIS one promoted' a year later."""

    def test_promoting_several_writes_an_entry_EACH(self, conn, period):
        one, two = f"cp-{uuid.uuid4().hex[:12]}", f"cp-{uuid.uuid4().hex[:12]}"
        t1, t2 = a_staged_table(conn, "clients"), a_staged_table(conn, "carers")
        promotion.promote_each(
            conn, [dict(dataset_id=one, supply=t1, physical_tables=[t1]),
                   dict(dataset_id=two, supply=t2, physical_tables=[t2])],
            agency_id=AGENCY, collection_id=COLLECTION, period=period,
            actor="keith", actor_kind=dl.PERSON, effective_at=WHEN,
            reason="both were checked by hand")
        assert len(dl.decisions_for(conn, one)) == 1
        assert len(dl.decisions_for(conn, two)) == 1

    def test_and_each_entry_carries_the_reason(self, conn, period):
        one = f"cp-{uuid.uuid4().hex[:12]}"
        t1 = a_staged_table(conn, "clients")
        promotion.promote_each(
            conn, [dict(dataset_id=one, supply=t1, physical_tables=[t1])],
            agency_id=AGENCY, collection_id=COLLECTION, period=period,
            actor="keith", actor_kind=dl.PERSON, effective_at=WHEN,
            reason="checked by hand")
        assert dl.decisions_for(conn, one)[0]["reason"] == "checked by hand"


class TestFilingSeesPromotedSlots:
    """Criterion 6, wired through to the caller that actually needs it.

    filing.filled_slots() has been a stub returning nothing since it was
    written, with a docstring saying "so, nothing yet" - because only a
    promotion fills a slot and promotion did not exist. It does now, and
    until this is wired the assignment rule believes every slot is
    unfilled, which is how 102 of 108 supplies once landed on 2023-Q1.
    """

    def test_it_reports_a_promoted_slot(self, conn, dataset, period):
        from qa_tools.common import filing
        physical = a_staged_table(conn, "clients")
        promotion.promote(conn, agency_id=AGENCY, collection_id=COLLECTION,
                          dataset_id=dataset, supply=physical, period=period,
                          physical_tables=[physical], actor="promotion-gate",
                          actor_kind=dl.RULE, effective_at=WHEN)
        assert period in filing.filled_slots(dataset)

    def test_and_still_reports_nothing_for_a_dataset_with_no_promotion(self, dataset):
        from qa_tools.common import filing
        assert filing.filled_slots(dataset) == frozenset()
