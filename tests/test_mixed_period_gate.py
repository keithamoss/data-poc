"""A delivery spanning two PERIODS is checked and never auto-promoted
(REQ-PIPE-077, Thread H's TS-33a and TS-33b).

TS-33b IS THE IMPORTANT HALF, and this module is ordered to say so.
The gate's condition is tables landing in different PERIODS, not
different SLOTS - and slots are per-table, so Child Protection's
ordinary six-table delivery already spans six slots. An implementation
keyed on slots passes the positive case and fails the negative one,
blocking auto-promotion on every healthy multi-table delivery. Without
the negative case the bug ships, because the positive case alone looks
like it works.

So the negative case comes first here, deliberately.
"""
from __future__ import annotations

import pytest

from qa_tools.common import promotion


def a_supply(**over):
    """A supply that WOULD promote itself, so each test changes one thing."""
    fields = dict(status="green", slot_filled=False, held_without_slot=False,
                  has_active_checks=True, decided_by_a_person=False,
                  delivery_spans_periods=False)
    fields.update(over)
    return fields


def a_delivery(*periods, dataset_prefix="cp"):
    """One delivery's supplies, one per dataset, filed to these periods."""
    return [{"dataset_id": f"{dataset_prefix}-{i}", "supply": f"s{i}",
             "period": period, "physical_tables": [f"t{i}"]}
            for i, period in enumerate(periods, start=1)]


class TestANormalDeliveryDoesNotTripTheGate:
    """TS-33b, and the half that catches the likely bug.

    Six tables, six SLOTS, one PERIOD. This is every healthy Child
    Protection delivery.
    """

    def test_six_slots_in_one_period_still_promote(self):
        promote, why = promotion.should_promote(
            **a_supply(delivery_spans_periods=False))
        assert promote is True, why

    def test_the_gate_reads_periods_not_slots(self):
        """Six datasets, six slots, ONE period - the condition must be
        false. A slot-keyed implementation returns True here."""
        supplies = a_delivery(*(["2026-Q1"] * 6))
        assert promotion.spans_periods(supplies) is False

    def test_a_single_supply_delivery_never_spans(self):
        assert promotion.spans_periods(a_delivery("2026-Q1")) is False

    def test_an_empty_delivery_never_spans(self):
        assert promotion.spans_periods([]) is False


class TestADeliverySpanningPeriodsIsWithheld:
    """TS-33a - August's cp_clients alongside November's
    cp_notifications. Different tables, so the duplicate-file hold
    never fires and each is assigned independently."""

    def test_two_periods_span(self):
        assert promotion.spans_periods(a_delivery("2026-Q1", "2026-Q2")) is True

    def test_nothing_in_it_promotes_automatically(self):
        promote, why = promotion.should_promote(
            **a_supply(delivery_spans_periods=True))
        assert promote is False
        assert why, "a refusal always says why"

    def test_it_says_why_in_terms_an_operator_can_act_on(self):
        _, why = promotion.should_promote(**a_supply(delivery_spans_periods=True))
        assert "period" in why.lower()

    @pytest.mark.parametrize("status", ["green", "amber"])
    def test_whatever_the_verdict_was(self, status):
        promote, _ = promotion.should_promote(
            **a_supply(status=status, delivery_spans_periods=True))
        assert promote is False

    def test_a_red_supply_still_reports_the_red_first(self):
        """The refusal reported should be the one worth acting on
        first - a red verdict is the thing to fix, where a delivery's
        shape is merely why today's attempt stopped."""
        _, why = promotion.should_promote(
            **a_supply(status="red", delivery_spans_periods=True))
        assert "red" in why.lower()


class TestASupplyWithNoPeriodDoesNotMakeADeliverySpan:
    """A held supply has no period at all, and `None` is not a period.

    Counting it would make every delivery containing one hold look like
    a catch-up drop, which is a different problem with a different
    remedy - and would fire this gate on the one shape REQ-PIPE-059
    already handles.
    """

    def test_one_period_plus_a_held_supply_does_not_span(self):
        supplies = a_delivery("2026-Q1", None, "2026-Q1")
        assert promotion.spans_periods(supplies) is False

    def test_two_real_periods_still_span_alongside_a_held_one(self):
        supplies = a_delivery("2026-Q1", None, "2026-Q2")
        assert promotion.spans_periods(supplies) is True

    def test_nothing_but_held_supplies_does_not_span(self):
        assert promotion.spans_periods(a_delivery(None, None)) is False


class TestItCostsNothingToEvaluate:
    """NFR 3 - a set comparison over a delivery's own filings, needing
    no data access."""

    def test_it_reads_no_database(self):
        """The signature is the proof: it takes the supplies the caller
        already has and nothing else."""
        import inspect

        params = inspect.signature(promotion.spans_periods).parameters
        assert list(params) == ["supplies"]


AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-30T08:00:00+08:00"


@pytest.fixture
def conn(private_supply_dsn):
    """A database of this test's own.

    The queue producer this exercises asks a GLOBAL question - every
    withheld promotion in the log - so a worker-shared database lets
    any other module falsify it. The same lesson `test_outstanding.py`
    records after nine of its tests went red on a populated
    deployment.
    """
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="test-mixed-period") as c:
        qa_store.ensure_schema(c)
        yield c


def a_run(conn, *periods):
    """Run the promotion step over one delivery filed to these periods."""
    supplies = [
        {"dataset_id": d, "supply": f"{d}@2026", "period": p,
         "physical_tables": [f"{d.replace('-', '_')}__2026"]}
        for d, p in zip(("cp-clients", "cp-notifications", "cp-carers"), periods)]
    return promotion.after_run(
        conn, agency_id=AGENCY, collection_id=COLLECTION, supplies=supplies,
        results=[], reads={}, actor="the-rule",
        actor_kind="rule", effective_at=WHEN), supplies


class TestTheGateRecordsWhatItDid:
    """Criterion 6 - in the decision log, with the RULE as the actor."""

    def test_it_writes_one_entry_per_withheld_supply(self, conn):
        from qa_tools.common import decision_log as dl

        a_run(conn, "2026-Q1", "2026-Q2")
        rows = conn.execute(
            f"SELECT dataset_id, to_slot, actor_kind, reason FROM {dl.TABLE} "
            "WHERE action = ? ORDER BY dataset_id",
            [dl.PROMOTION_WITHHELD]).fetchall()
        assert len(rows) == 2

    def test_the_actor_is_the_rule_and_never_a_person(self, conn):
        """Naming a person would put a decision on somebody who never
        made one - `slot_state._decider()` depends on the distinction."""
        from qa_tools.common import decision_log as dl

        a_run(conn, "2026-Q1", "2026-Q2")
        kinds = {r[0] for r in conn.execute(
            f"SELECT actor_kind FROM {dl.TABLE} WHERE action = ?",
            [dl.PROMOTION_WITHHELD]).fetchall()}
        assert kinds == {dl.RULE}

    def test_every_entry_names_every_period_the_delivery_touched(self, conn):
        from qa_tools.common import decision_log as dl

        a_run(conn, "2026-Q1", "2026-Q2")
        for (reason,) in conn.execute(
                f"SELECT reason FROM {dl.TABLE} WHERE action = ?",
                [dl.PROMOTION_WITHHELD]).fetchall():
            assert "2026-Q1" in reason and "2026-Q2" in reason

    def test_a_normal_delivery_records_nothing(self, conn):
        """TS-33b again, one layer up."""
        from qa_tools.common import decision_log as dl

        a_run(conn, "2026-Q1", "2026-Q1", "2026-Q1")
        assert conn.execute(
            f"SELECT count(*) FROM {dl.TABLE} WHERE action = ?",
            [dl.PROMOTION_WITHHELD]).fetchall()[0][0] == 0

    def test_a_withheld_entry_must_name_a_period(self, conn):
        from qa_tools.common import decision_log as dl

        with pytest.raises(dl.DecisionRefused, match="names the period"):
            with dl.apply_decision(conn, dl.Decision(
                    agency_id=AGENCY, collection_id=COLLECTION,
                    dataset_id="cp-clients", action=dl.PROMOTION_WITHHELD,
                    supply="s1", actor="the-rule", actor_kind=dl.RULE,
                    effective_at=WHEN, from_slot="2026-Q1",
                    reason="because")):
                pass

    def test_a_withheld_entry_must_say_why(self, conn):
        """It is the only record that the rule looked and declined."""
        from qa_tools.common import decision_log as dl

        with pytest.raises(dl.DecisionRefused, match="needs a reason"):
            with dl.apply_decision(conn, dl.Decision(
                    agency_id=AGENCY, collection_id=COLLECTION,
                    dataset_id="cp-clients", action=dl.PROMOTION_WITHHELD,
                    supply="s1", actor="the-rule", actor_kind=dl.RULE,
                    effective_at=WHEN, to_slot="2026-Q1")):
                pass


class TestItReachesTheQueue:
    """Criterion 4 - among the items awaiting a person, NAMING THE
    PERIODS. "This delivery was odd" sends somebody to reassemble the
    delivery themselves."""

    def test_the_withheld_supplies_are_in_the_queue(self, conn, tmp_path):
        from qa_tools.common import outstanding

        a_run(conn, "2026-Q1", "2026-Q2")
        found = outstanding.survey(observations_dir=tmp_path)
        mine = [i for i in found.items if i.kind == outstanding.WITHHELD_PROMOTION]
        assert len(mine) == 2

    def test_each_item_names_the_periods_involved(self, conn, tmp_path):
        from qa_tools.common import outstanding

        a_run(conn, "2026-Q1", "2026-Q2")
        mine = [i for i in outstanding.survey(observations_dir=tmp_path).items
                if i.kind == outstanding.WITHHELD_PROMOTION]
        for item in mine:
            assert "2026" in item.detail, item.detail

    def test_it_is_blocking_and_needs_action(self, conn, tmp_path):
        from qa_tools.common import outstanding

        a_run(conn, "2026-Q1", "2026-Q2")
        [one, *_] = [i for i in outstanding.survey(observations_dir=tmp_path).items
                     if i.kind == outstanding.WITHHELD_PROMOTION]
        assert one.blocking is True
        assert one.severity == outstanding.NEEDS_ACTION

    def test_it_says_what_a_person_can_do(self, conn, tmp_path):
        from qa_tools.common import outstanding

        a_run(conn, "2026-Q1", "2026-Q2")
        [one, *_] = [i for i in outstanding.survey(observations_dir=tmp_path).items
                     if i.kind == outstanding.WITHHELD_PROMOTION]
        assert one.responses


class TestAPersonIsNeverPrevented:
    """Criterion 5 - the gate stops AUTOMATION, not an operator."""

    def test_a_person_can_promote_a_withheld_supply(self, conn):
        from qa_tools.common import decision_log as dl

        _, supplies = a_run(conn, "2026-Q1", "2026-Q2")
        mine = supplies[0]
        with dl.apply_decision(conn, dl.Decision(
                agency_id=AGENCY, collection_id=COLLECTION,
                dataset_id=mine["dataset_id"], action=dl.PROMOTE,
                supply=mine["supply"], actor="keith@example.gov.au",
                actor_kind=dl.PERSON, effective_at=WHEN,
                to_slot=mine["period"])) as entry_id:
            assert entry_id

    def test_the_gate_never_appears_in_a_persons_way(self):
        """The gate is a parameter of the AUTOMATIC path only, which is
        the structural form of criterion 5 - a person's route does not
        call it at all."""
        import inspect

        from qa_tools.common import decision_log as dl

        source = inspect.getsource(dl.apply_decision)
        assert "spans_periods" not in source
        assert "delivery_spans_periods" not in source
