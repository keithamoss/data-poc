"""A period nobody supplied, standing on an earlier real one (REQ-PIPE-084).

WHAT THESE PIN is the difference between a substitution and a silent
default, because the code for the two is nearly identical and only one
of them is acceptable. Every path here requires a person, a chosen
period, and a reason; every refusal says which of those is missing.

The other half is criterion 11, which is enforced somewhere these tests
do not call: the DECISION LOG refuses to demote, reject or re-file a
supply while a later period stands on it. That is deliberate - the
person demoting a supply is not thinking about a substitution made six
months ago, so the guard has to live where every decision passes rather
than where substitutions are made.
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import period_schema, qa_store, substitution, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-29T09:00:00+08:00"
WHY = "the supplier confirmed no extract will be sent for this quarter"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-substitution") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    return f"cp-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def periods():
    """Three periods of this test's own, so their schemas cannot collide."""
    tag = uuid.uuid4().hex[:6]
    return (f"2099-A{tag}", f"2099-B{tag}", f"2099-C{tag}")


def _promote_into(conn, dataset_id, period, *, status_red=False):
    """A real promoted table in that period, by the ordinary route."""
    from qa_tools.common import promotion

    physical = f"tbl__{uuid.uuid4().hex[:10]}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    conn.execute(f'INSERT INTO "{supply_db.STAGING_SCHEMA}"."{physical}" VALUES (7)')
    promotion.promote(
        conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset_id,
        supply=physical, period=period, physical_tables=[physical],
        actor="tester", actor_kind=dl.PERSON, effective_at=WHEN,
        reason="a reason" if status_red else None, supply_is_red=status_red)
    return physical


def _substitute(conn, dataset_id, *, period, stands_on, supply, logical="carers",
                **over):
    kwargs = dict(agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset_id,
                  logical_table=logical, period=period, stands_on=stands_on,
                  supply=supply, actor="Keith", reason=WHY, effective_at=WHEN)
    kwargs.update(over)
    return substitution.substitute(conn, **kwargs)


class TestAPeriodStandsOnAnEarlierRealSupply:
    """Criteria 1, 3 and 4."""

    def test_the_period_resolves_to_the_earlier_supplys_rows(self, conn, dataset, periods):
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply)

        schema = period_schema.period_schema(second)
        rows = conn.execute(f'SELECT id FROM "{schema}"."carers"').fetchall()
        assert [r[0] for r in rows] == [7]

    def test_it_answers_to_the_tables_logical_name(self, conn, dataset, periods):
        """Criterion 3: whatever queries the period by the logical name
        gets the indirection, without knowing it is there."""
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply,
                    logical="carers")
        schema = period_schema.period_schema(second)
        found = conn.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema = ?", [schema]).fetchall()
        assert ("carers", "VIEW") in found

    def test_the_slot_counts_as_filled(self, conn, dataset, periods):
        """Criterion 4. The period answers, so nothing should treat it as
        owed and the next arrival for it lands on a filled slot."""
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply)
        from qa_tools.common import promotion
        assert second in promotion.filled_slots(conn, dataset)

    def test_a_red_supply_may_be_stood_on(self, conn, dataset, periods):
        """Criterion 1's "of any status". A period that held a red supply
        held one, and the person confirming it is the point."""
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first, status_red=True)
        sub = _substitute(conn, dataset, period=second, stands_on=first, supply=supply)
        assert sub.stands_on == first


class TestItIsAViewAndNotACopy:
    """Criterion 2, and the reason: a copy is a second physical truth
    that drifts from the one it was taken from."""

    def test_the_rows_follow_the_supply(self, conn, dataset, periods):
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply)

        source = period_schema.period_schema(first)
        conn.execute(f'INSERT INTO "{source}"."{supply}" VALUES (8)')
        schema = period_schema.period_schema(second)
        rows = conn.execute(f'SELECT id FROM "{schema}"."carers" ORDER BY id').fetchall()
        assert [r[0] for r in rows] == [7, 8], \
            "a copy would still read 7 alone, which is the drift this avoids"


class TestTheDecisionIsRecorded:
    """Criterion 5: the operator, the period pointed at, and a reason."""

    def test_all_three_are_in_the_log(self, conn, dataset, periods):
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply)
        row = conn.execute(
            f"SELECT actor, actor_kind, stands_on, to_slot, reason FROM {dl.TABLE} "
            "WHERE dataset_id = ? AND action = ?",
            [dataset, dl.SUBSTITUTE]).fetchall()[0]
        assert row == ("Keith", dl.PERSON, first, second, WHY)

    def test_a_substitution_without_a_reason_is_refused(self, conn, dataset, periods):
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first)
        with pytest.raises(substitution.SubstitutionRefused, match="needs a reason"):
            _substitute(conn, dataset, period=second, stands_on=first,
                        supply=supply, reason="  ")

    def test_it_is_never_recorded_as_a_rule(self, conn, dataset, periods):
        """Criterion 1's "never by default", expressed as an absent
        parameter: there is no actor_kind to pass."""
        import inspect
        assert "actor_kind" not in inspect.signature(substitution.substitute).parameters


class TestItRefusesWhereThereIsNothingSoundToStandOn:
    """Criteria 7, 15, 16 and 18."""

    def test_no_earlier_promoted_supply_is_refused_and_says_why(self, conn, dataset,
                                                                 periods):
        first, second, _ = periods
        with pytest.raises(substitution.SubstitutionRefused,
                            match="holds no promoted supply"):
            _substitute(conn, dataset, period=second, stands_on=first, supply="nothing")

    def test_a_period_already_holding_a_real_supply_is_refused(self, conn, dataset,
                                                                periods):
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first)
        _promote_into(conn, dataset, second)
        with pytest.raises(substitution.SubstitutionRefused,
                            match="already resolves to a real supply"):
            _substitute(conn, dataset, period=second, stands_on=first, supply=supply)

    def test_it_never_stands_on_a_period_that_is_itself_substituted(self, conn, dataset,
                                                                     periods):
        """Criterion 16, and the failure it stops: a chain of
        indirections whose bottom nobody can see."""
        first, second, third = periods
        supply = _promote_into(conn, dataset, first)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply)
        with pytest.raises(substitution.SubstitutionRefused, match="is itself"):
            _substitute(conn, dataset, period=third, stands_on=second, supply=supply)

    def test_a_period_nothing_is_owed_for_is_refused_and_names_inheritance(
            self, conn, dataset, periods):
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first)
        with pytest.raises(substitution.SubstitutionRefused, match="INHERITED"):
            _substitute(conn, dataset, period=second, stands_on=first,
                        supply=supply, participates=False)

    def test_standing_on_a_supply_that_period_does_not_hold_is_refused(
            self, conn, dataset, periods):
        first, second, _ = periods
        _promote_into(conn, dataset, first)
        with pytest.raises(substitution.SubstitutionRefused, match="resolves to"):
            _substitute(conn, dataset, period=second, stands_on=first,
                        supply="some_other_table")


class TestDeSubstituting:
    """Criteria 9 and 13."""

    def _standing(self, conn, dataset, periods):
        first, second, _ = periods
        supply = _promote_into(conn, dataset, first)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply)
        return first, second, supply

    def _remove(self, conn, dataset, period, **over):
        kwargs = dict(agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
                      logical_table="carers", period=period, actor="Keith",
                      reason="the real extract arrived", effective_at=WHEN,
                      confirmed=True)
        kwargs.update(over)
        return substitution.de_substitute(conn, **kwargs)

    def test_the_period_stops_resolving(self, conn, dataset, periods):
        _, second, _ = self._standing(conn, dataset, periods)
        self._remove(conn, dataset, second)
        schema = period_schema.period_schema(second)
        found = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [schema]).fetchall()
        assert ("carers",) not in found

    def test_the_slot_is_left_unfilled(self, conn, dataset, periods):
        from qa_tools.common import promotion
        _, second, _ = self._standing(conn, dataset, periods)
        self._remove(conn, dataset, second)
        assert second not in promotion.filled_slots(conn, dataset)

    def test_it_is_recorded_with_the_operator_and_a_reason(self, conn, dataset, periods):
        _, second, _ = self._standing(conn, dataset, periods)
        self._remove(conn, dataset, second)
        row = conn.execute(
            f"SELECT actor, actor_kind, from_slot, reason FROM {dl.TABLE} "
            "WHERE dataset_id = ? AND action = ?",
            [dataset, dl.DE_SUBSTITUTE]).fetchall()[0]
        assert row == ("Keith", dl.PERSON, second, "the real extract arrived")

    def test_it_refuses_without_an_explicit_confirmation(self, conn, dataset, periods):
        _, second, _ = self._standing(conn, dataset, periods)
        with pytest.raises(substitution.SubstitutionRefused, match="confirmation"):
            self._remove(conn, dataset, second, confirmed=False)

    def test_removing_one_that_is_not_there_is_refused_rather_than_silent(
            self, conn, dataset, periods):
        _, second, _ = periods
        with pytest.raises(substitution.SubstitutionRefused, match="no indirection"):
            self._remove(conn, dataset, second)

    def test_one_period_at_a_time(self, conn, dataset, periods):
        """Criterion 9, expressed as a signature: there is no way to pass
        several periods, which is how somebody empties a year meaning to
        empty a quarter."""
        import inspect
        params = inspect.signature(substitution.de_substitute).parameters
        assert "period" in params and "periods" not in params


class TestASupplySomethingStandsOnCannotMove:
    """Criterion 11, enforced by the decision log rather than here."""

    def _two_standing(self, conn, dataset, periods):
        first, second, third = periods
        supply = _promote_into(conn, dataset, first)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply)
        _substitute(conn, dataset, period=third, stands_on=first, supply=supply,
                    logical="placements")
        return first, supply

    @pytest.mark.parametrize("action", [dl.DEMOTE, dl.REJECT, dl.REFILE])
    def test_the_decision_is_refused(self, conn, dataset, periods, action):
        first, supply = self._two_standing(conn, dataset, periods)
        decision = dl.Decision(
            agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            action=action, supply=supply, actor="Keith", actor_kind=dl.PERSON,
            effective_at=WHEN, from_slot=first, to_slot=periods[2],
            reason="changed my mind")
        with pytest.raises(dl.DecisionRefused, match="stand on it"):
            with dl.apply_decision(conn, decision):
                pass

    def test_it_names_every_blocking_period(self, conn, dataset, periods):
        """Told about one, an operator de-substitutes it and hits the
        next - which is why the criterion asks for all of them."""
        first, supply = self._two_standing(conn, dataset, periods)
        decision = dl.Decision(
            agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            action=dl.DEMOTE, supply=supply, actor="Keith", actor_kind=dl.PERSON,
            effective_at=WHEN, from_slot=first, reason="changed my mind")
        with pytest.raises(dl.DecisionRefused) as exc:
            with dl.apply_decision(conn, decision):
                pass
        assert periods[1] in str(exc.value) and periods[2] in str(exc.value)

    def test_a_reversed_substitution_no_longer_blocks_it(self, conn, dataset, periods):
        """CURRENTLY standing on, not ever. Counting a period somebody
        already de-substituted would make the supply permanently stuck."""
        first, supply = self._two_standing(conn, dataset, periods)
        for period, logical in ((periods[1], "carers"), (periods[2], "placements")):
            substitution.de_substitute(
                conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
                logical_table=logical, period=period, actor="Keith",
                reason="no longer needed", effective_at=WHEN, confirmed=True)
        assert dl.periods_standing_on(conn, dataset, supply) == ()


class TestOnePeriodsDecisionLeavesOthersAlone:
    """Criterion 12."""

    def test_substituting_one_period_does_not_change_another(self, conn, dataset,
                                                              periods):
        first, second, third = periods
        supply = _promote_into(conn, dataset, first)
        other = _promote_into(conn, dataset, third)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply)
        from qa_tools.common import promotion
        assert promotion.newest_promoted(conn, dataset, third) == other

    def test_de_substituting_one_leaves_another_standing(self, conn, dataset, periods):
        first, second, third = periods
        supply = _promote_into(conn, dataset, first)
        _substitute(conn, dataset, period=second, stands_on=first, supply=supply)
        _substitute(conn, dataset, period=third, stands_on=first, supply=supply,
                    logical="placements")
        substitution.de_substitute(
            conn, agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            logical_table="carers", period=second, actor="Keith",
            reason="the real extract arrived", effective_at=WHEN, confirmed=True)
        assert substitution.substituted(conn, dataset, third) is not None
        assert substitution.substituted(conn, dataset, second) is None
