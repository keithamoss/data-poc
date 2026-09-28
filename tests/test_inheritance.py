"""A period nobody owed a supply for, filled by the rule (REQ-PIPE-098).

NO DATASET DECLARES `not_expected` TODAY, so every test here states the
schedule's answer rather than reading it from `contract/data-asset.yaml`.
That is a real limitation and it is stated rather than hidden: these
prove the RULE, not that the configuration exercises it. Making a real
instance is a domain claim about a supplier's obligations - that a
dataset genuinely is not due in some period - and belongs with Keith
and the generator's scenario register, not here.

Stated at the top because this project has just been bitten by the
opposite habit: `outstanding._from_closed_slots()` sat behind a guard
that made it unreachable, carried two faults for weeks, and ran for the
first time on the night the guard stopped holding
(plans/post-build-review.md #63).
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import (hierarchy, inheritance, period_schema, promotion,
                             qa_store, schedule, supply_db)

WHEN = "2026-09-29T09:00:00+08:00"
REASON = "carers are supplied annually, so no quarterly file is due"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-inheritance") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def annual():
    """A REAL dataset, so hierarchy and its table name are real."""
    return hierarchy.dataset("cp-carers")


@pytest.fixture
def periods():
    tag = uuid.uuid4().hex[:6]
    return (f"2099-A{tag}", f"2099-B{tag}")


@pytest.fixture
def owes_nothing(monkeypatch, annual, periods):
    """The schedule says this dataset does not participate in the SECOND
    period, with a reason, and dates the two in order."""
    _, second = periods
    monkeypatch.setattr(schedule, "not_expected_periods",
                        lambda ds: {second: REASON} if ds == annual.dataset_id else {})
    monkeypatch.setattr(inheritance.schedule, "not_expected_periods",
                        lambda ds: {second: REASON} if ds == annual.dataset_id else {})
    from datetime import date
    order = {periods[0]: date(2099, 1, 1), periods[1]: date(2099, 4, 1)}
    monkeypatch.setattr(inheritance.schedule, "date_of",
                        lambda name, ds: order.get(name))
    monkeypatch.setattr(inheritance.hierarchy, "all_datasets", lambda: [annual])


def _promote_into(conn, dataset, period):
    physical = f"{dataset.table}__{uuid.uuid4().hex[:10]}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    conn.execute(f'INSERT INTO "{supply_db.STAGING_SCHEMA}"."{physical}" VALUES (3)')
    promotion.promote(
        conn, agency_id=dataset.agency_id, collection_id=dataset.collection_id,
        dataset_id=dataset.dataset_id, supply=physical, period=period,
        physical_tables=[physical], actor="tester", actor_kind=dl.PERSON,
        effective_at=WHEN)
    return physical


class TestOpeningAPeriodIsARecordedEvent:
    """Criteria 3 and 4."""

    def test_the_first_open_says_so_and_the_second_does_not(self, conn, periods):
        first, _ = periods
        assert period_schema.open_period(conn, first, opened_by="Keith") is True
        assert period_schema.open_period(conn, first, opened_by="Keith") is False

    def test_it_is_a_fact_rather_than_the_schema_being_present(self, conn, periods):
        """The schema alone cannot tell a period opened a second ago
        from one opened last year whose schema was dropped and rebuilt -
        and the second would inherit all over again, from what is
        current NOW rather than from what was current then."""
        first, _ = periods
        period_schema.ensure_period_schema(conn, first)
        assert period_schema.opened(conn, first) is False
        period_schema.open_period(conn, first, opened_by="Keith")
        assert period_schema.opened(conn, first) is True

    def test_a_first_promotion_opens_it_too(self, conn, annual, periods):
        first, _ = periods
        _promote_into(conn, annual, first)
        assert period_schema.opened(conn, first) is True

    def test_a_period_can_exist_before_anything_arrives(self, conn, periods):
        """Criterion 4's "SHALL NOT require an arrival"."""
        _, second = periods
        period_schema.open_period(conn, second, opened_by="Keith")
        schema = period_schema.period_schema(second)
        found = conn.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = ?",
            [schema]).fetchall()
        assert found and period_schema.opened(conn, second)

    def test_who_opened_it_is_recorded(self, conn, periods):
        first, _ = periods
        period_schema.open_period(conn, first, opened_by="Keith")
        row = conn.execute(
            f'SELECT opened_by FROM "{qa_store.SCHEMA}".period WHERE name = ?',
            [first]).fetchall()[0]
        assert row[0] == "Keith"


class TestADatasetThatOwesNothingInheritsWhatIsCurrent:
    """Criteria 1, 5, 6, 8, 15 and 16."""

    def test_the_period_resolves_to_the_earlier_supplys_rows(
            self, conn, annual, periods, owes_nothing):
        first, second = periods
        _promote_into(conn, annual, first)
        period_schema.open_period(conn, second, opened_by="rule")

        schema = period_schema.period_schema(second)
        rows = conn.execute(f'SELECT id FROM "{schema}"."{annual.table}"').fetchall()
        assert [r[0] for r in rows] == [3]

    def test_it_is_a_view_and_the_rows_follow_the_supply(
            self, conn, annual, periods, owes_nothing):
        """Criterion 15, proven the way REQ-PIPE-084's is: insert after
        the fact and watch it come through."""
        first, second = periods
        physical = _promote_into(conn, annual, first)
        period_schema.open_period(conn, second, opened_by="rule")

        source = period_schema.period_schema(first)
        conn.execute(f'INSERT INTO "{source}"."{physical}" VALUES (4)')
        schema = period_schema.period_schema(second)
        rows = conn.execute(
            f'SELECT id FROM "{schema}"."{annual.table}" ORDER BY id').fetchall()
        assert [r[0] for r in rows] == [3, 4]

    def test_the_rule_is_the_actor_and_the_schedules_reason_is_recorded(
            self, conn, annual, periods, owes_nothing):
        first, second = periods
        _promote_into(conn, annual, first)
        period_schema.open_period(conn, second, opened_by="rule")

        # SCOPED TO THIS PERIOD. The decision log accumulates across a
        # module's tests on one worker database, so a query by dataset
        # alone picks up whatever the previous test inherited.
        row = conn.execute(
            f"SELECT actor_kind, actor, stands_on, reason FROM {dl.TABLE} "
            "WHERE dataset_id = ? AND action = ? AND to_slot = ?",
            [annual.dataset_id, dl.INHERIT, second]).fetchall()[0]
        assert row == (dl.RULE, inheritance.RULE_ACTOR, first, REASON)

    def test_a_participating_dataset_inherits_nothing(
            self, conn, annual, periods, owes_nothing):
        """Criterion 5: non-participation comes from the schedule, never
        from a supply simply being absent."""
        first, _ = periods
        _promote_into(conn, annual, first)
        # `first` is a period the dataset DOES participate in, and it has
        # nothing staged beyond that one promotion.
        assert inheritance.inherited(conn, annual.dataset_id, first) is None


class TestNothingToStandOnIsRefusedRatherThanFabricated:
    """Criteria 9 and 10."""

    def test_no_view_is_created(self, conn, annual, periods, owes_nothing):
        _, second = periods
        period_schema.open_period(conn, second, opened_by="rule")
        schema = period_schema.period_schema(second)
        found = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [schema]).fetchall()
        assert (annual.table,) not in found, "an empty table is a lie with a schema on it"

    def test_the_refusal_is_recorded_with_the_rule_as_the_actor(
            self, conn, annual, periods, owes_nothing):
        _, second = periods
        period_schema.open_period(conn, second, opened_by="rule")
        rows = conn.execute(
            f"SELECT actor_kind, supply, reason FROM {dl.TABLE} "
            "WHERE dataset_id = ? AND action = ? AND to_slot = ?",
            [annual.dataset_id, dl.INHERIT_REFUSED, second]).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == dl.RULE
        assert rows[0][1] is None, "the thing it could not find IS a supply"
        assert "no earlier promoted supply" in rows[0][2]

    def test_it_is_surfaced_for_somebody_to_see(self, conn, annual, periods,
                                                owes_nothing):
        _, second = periods
        period_schema.open_period(conn, second, opened_by="rule")
        found = [r for r in inheritance.refusals(conn) if r.period == second]
        assert found and found[0].dataset_id == annual.dataset_id


class TestItPointsOnlyAtARealPromotedTable:
    """Criterion 14, and the chain it stops."""

    def test_it_never_inherits_from_a_period_that_is_itself_inherited(
            self, conn, annual, periods, owes_nothing, monkeypatch):
        first, second = periods
        _promote_into(conn, annual, first)
        period_schema.open_period(conn, second, opened_by="rule")

        # A THIRD period, which owes nothing either. The only thing
        # `second` holds is the inherited view, so the newest PROMOTED
        # table is still `first`'s - never `second`'s view.
        from datetime import date
        third = f"{second}-z"
        monkeypatch.setattr(inheritance.schedule, "not_expected_periods",
                             lambda ds: {second: REASON, third: REASON})
        order = {first: date(2099, 1, 1), second: date(2099, 4, 1),
                  third: date(2099, 7, 1)}
        monkeypatch.setattr(inheritance.schedule, "date_of",
                             lambda name, ds: order.get(name))
        period_schema.open_period(conn, third, opened_by="rule")

        got = inheritance.inherited(conn, annual.dataset_id, third)
        assert got is not None and got.stands_on == first


class TestInheritanceIsNotSubstitution:
    """Criterion 12, and criterion 7's consequence."""

    def test_they_are_different_actions(self):
        assert dl.INHERIT != dl.SUBSTITUTE

    def test_an_inherited_period_is_not_a_filled_slot(
            self, conn, annual, periods, owes_nothing):
        """Criterion 7: the dataset does not participate, so nothing was
        owed and there is no slot to fill. Counting it would make
        "filled" mean both "a supply arrived" and "none was ever due"."""
        first, second = periods
        _promote_into(conn, annual, first)
        period_schema.open_period(conn, second, opened_by="rule")
        assert second not in promotion.filled_slots(conn, annual.dataset_id)
        assert first in promotion.filled_slots(conn, annual.dataset_id)


class TestOpeningOnePeriodLeavesOthersAlone:
    """Criterion 13."""

    def test_the_earlier_period_still_resolves_to_its_own_supply(
            self, conn, annual, periods, owes_nothing):
        first, second = periods
        physical = _promote_into(conn, annual, first)
        period_schema.open_period(conn, second, opened_by="rule")
        assert promotion.newest_promoted(conn, annual.dataset_id, first) == physical


class TestASupplyArrivingIntoAnInheritedPeriodWaitsForAPerson:
    """Criterion 17, and it needs its own refusal rather than riding on
    the filled-slot one.

    A SUBSTITUTED period counts as filled (REQ-PIPE-084 criterion 4), so
    a supply arriving into one is already refused by "the slot is
    already filled". An INHERITED period is deliberately NOT filled -
    nothing was owed - so without this the rule would promote straight
    over the inherited view and nobody would be asked.
    """

    def test_automation_does_not_promote_into_it(self, conn, annual, periods,
                                                  owes_nothing):
        first, second = periods
        _promote_into(conn, annual, first)
        period_schema.open_period(conn, second, opened_by="rule")

        ok, why = promotion.should_promote(
            status="green", slot_filled=False, held_without_slot=False,
            has_active_checks=True,
            inherited=inheritance.inherited(conn, annual.dataset_id, second) is not None)
        assert ok is False
        assert "nothing was owed" in why

    def test_the_gate_says_which_state_it_is_refusing_for(self, conn):
        _, why = promotion.should_promote(
            status="green", slot_filled=False, held_without_slot=False,
            has_active_checks=True, inherited=True)
        assert "already filled" not in why, \
            "an inherited period is not a filled slot, and saying so would be wrong"

    def test_an_ordinary_period_is_unaffected(self, conn):
        assert promotion.should_promote(
            status="green", slot_filled=False, held_without_slot=False,
            has_active_checks=True, inherited=False) == (True, None)


class TestInheritingRunsNoChecks:
    """Criterion 11: the inherited period's results are the ones the run
    that earned them recorded, and nothing produces a second set."""

    def test_no_run_is_opened(self, conn, annual, periods, owes_nothing):
        first, second = periods
        _promote_into(conn, annual, first)
        before = conn.execute(
            f'SELECT count(*) FROM "{qa_store.SCHEMA}".run').fetchall()[0][0]
        period_schema.open_period(conn, second, opened_by="rule")
        after = conn.execute(
            f'SELECT count(*) FROM "{qa_store.SCHEMA}".run').fetchall()[0][0]
        assert after == before

    def test_no_check_result_is_written(self, conn, annual, periods, owes_nothing):
        first, second = periods
        _promote_into(conn, annual, first)
        before = conn.execute(
            f'SELECT count(*) FROM "{qa_store.SCHEMA}".check_result').fetchall()[0][0]
        period_schema.open_period(conn, second, opened_by="rule")
        after = conn.execute(
            f'SELECT count(*) FROM "{qa_store.SCHEMA}".check_result').fetchall()[0][0]
        assert after == before


class TestASupplyAnInheritedPeriodStandsOnCannotMove:
    """The gap the sprints gate pointed at on 2026-09-28.

    REQ-PIPE-084 criterion 11 refuses to demote, reject or re-file a
    supply while a later period STANDS ON it, and it was built asking
    only about substitutions. An inherited period stands on one just as
    hard - demote the supply and the inherited view points at a table
    that is no longer there - so the question has to cover both.

    This is also what unblocks REQ-PIPE-076 criterion 5's proviso, which
    was deferred to REQ-PIPE-084 and REQ-PIPE-098 precisely because
    neither existed to make a period stand on anything.
    """

    def test_demoting_it_is_refused_and_names_the_period(
            self, conn, annual, periods, owes_nothing):
        first, second = periods
        physical = _promote_into(conn, annual, first)
        period_schema.open_period(conn, second, opened_by="rule")
        assert inheritance.inherited(conn, annual.dataset_id, second) is not None

        decision = dl.Decision(
            agency_id=annual.agency_id, collection_id=annual.collection_id,
            dataset_id=annual.dataset_id, action=dl.DEMOTE, supply=physical,
            actor="Keith", actor_kind=dl.PERSON, effective_at=WHEN,
            from_slot=first, reason="changed my mind")
        with pytest.raises(dl.DecisionRefused) as exc:
            with dl.apply_decision(conn, decision):
                pass
        assert second in str(exc.value)

    def test_a_supply_nothing_stands_on_still_moves(self, conn, annual, periods):
        first, _ = periods
        physical = _promote_into(conn, annual, first)
        decision = dl.Decision(
            agency_id=annual.agency_id, collection_id=annual.collection_id,
            dataset_id=annual.dataset_id, action=dl.DEMOTE, supply=physical,
            actor="Keith", actor_kind=dl.PERSON, effective_at=WHEN,
            from_slot=first, reason="changed my mind")
        with dl.apply_decision(conn, decision):
            pass
        assert dl.promoted_into(conn, annual.dataset_id, first) is None
