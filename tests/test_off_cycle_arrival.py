"""A supply arriving off-cycle is checked and waits for a person
(REQ-PIPE-077, amended and retitled 2026-10-02).

WHAT THIS REPLACED, and why the whole condition changed rather than
its effect. The requirement was "a delivery whose tables land in
different PERIODS runs QA and never auto-promotes", and it withheld
EVERY supply in such a delivery. Measured against the real corpus it
fired on nine of sixty deliveries, and all nine were one
partial-participation dataset riding along in a quarterly drop - so
five healthy tables waited on a person each time because a sixth was
not due.

Keith settled it 2026-10-02: once every file is its own arrival there
is no delivery unit to withhold, so a delivery MAY span periods and
the existing rules handle it. What genuinely needs a person is the
OFF-CYCLE ARRIVAL itself - and that is a fact about one dataset's
participation, readable from configuration, needing no delivery and
no comparison with its siblings.

THE OLD CONDITION COULD NOT NAME ITS OWN TARGET, which is the clearest
argument against it: given five supplies in Q2 and one in Q1, nothing
said which was the odd one out except counting, and counting has no
answer on a three-three split.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import promotion

AWST = timezone(timedelta(hours=8))
AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-10-02T08:00:00+08:00"

#: cp-case-workers is the worked example of partial participation -
#: `delivery_months: [February, August]`, so it has Q1 and Q3 slots and
#: no Q2 or Q4. cp-clients is ordinary quarterly.
PARTIAL = "cp-case-workers"
QUARTERLY = "cp-clients"


def a_supply(**over):
    """A supply that WOULD promote itself, so each test changes one thing."""
    fields = dict(status="green", slot_filled=False, held_without_slot=False,
                  has_active_checks=True, decided_by_a_person=False,
                  arrived_off_cycle=False)
    fields.update(over)
    return fields


class TestWhetherAnArrivalIsOffCycle:
    """The condition itself, read from configuration alone."""

    def test_a_partial_dataset_arriving_in_a_period_it_skips_is_off_cycle(self):
        off, period = promotion.arrived_off_cycle(
            PARTIAL, datetime(2023, 5, 1, 9, tzinfo=AWST))
        assert off is True
        assert period == "2023-Q2", "it should name the period it arrived in"

    def test_the_same_dataset_arriving_in_a_period_it_participates_in_is_not(self):
        off, period = promotion.arrived_off_cycle(
            PARTIAL, datetime(2023, 8, 1, 9, tzinfo=AWST))
        assert off is False and period == "2023-Q3"

    @pytest.mark.parametrize("month,period", [(2, "2023-Q1"), (5, "2023-Q2"),
                                               (8, "2023-Q3"), (11, "2023-Q4")])
    def test_a_fully_participating_dataset_is_never_off_cycle(self, month, period):
        off, named = promotion.arrived_off_cycle(
            QUARTERLY, datetime(2023, month, 1, 9, tzinfo=AWST))
        assert off is False and named == period

    def test_it_reads_the_period_the_supply_ARRIVED_in_not_where_it_is_filed(self):
        """The distinction the whole amendment turns on. A May arrival
        of cp-case-workers FILES to 2023-Q1, because that is its own
        current slot - but it ARRIVED in Q2, which is the period it
        does not participate in, and that is what makes it odd."""
        off, period = promotion.arrived_off_cycle(
            PARTIAL, datetime(2023, 5, 1, 9, tzinfo=AWST))
        assert off is True and period == "2023-Q2"

    def test_mid_period_arrivals_resolve_to_that_period(self):
        off, period = promotion.arrived_off_cycle(
            PARTIAL, datetime(2023, 6, 15, 9, tzinfo=AWST))
        assert off is True and period == "2023-Q2"

    def test_before_the_calendar_begins_is_not_off_cycle(self):
        """No period has opened, so there is no period it is not
        participating in. Refusing a supply for arriving before the
        calendar starts would be inventing a rule."""
        off, period = promotion.arrived_off_cycle(
            PARTIAL, datetime(2023, 1, 15, 9, tzinfo=AWST))
        assert off is False and period == ""

    def test_a_dataset_the_tree_does_not_know_is_not_off_cycle(self):
        """A gate must not take a run down over an id it cannot place -
        the blast-radius rule this area applies everywhere."""
        off, _ = promotion.arrived_off_cycle(
            "nothing-like-this", datetime(2023, 5, 1, 9, tzinfo=AWST))
        assert off is False


class TestAnOffCycleSupplyIsCheckedAndWithheld:
    """Criterion 1 - QA runs, automation stands back."""

    def test_it_does_not_promote(self):
        promote, why = promotion.should_promote(**a_supply(arrived_off_cycle=True))
        assert promote is False and why

    def test_it_says_why_in_terms_an_operator_can_act_on(self):
        _, why = promotion.should_promote(**a_supply(arrived_off_cycle=True))
        assert "not due" in why.lower() or "off-cycle" in why.lower()

    @pytest.mark.parametrize("status", ["green", "amber"])
    def test_whatever_the_verdict_was(self, status):
        promote, _ = promotion.should_promote(
            **a_supply(status=status, arrived_off_cycle=True))
        assert promote is False

    def test_a_red_supply_still_reports_the_red_first(self):
        """The refusal reported is the one worth acting on first."""
        _, why = promotion.should_promote(
            **a_supply(status="red", arrived_off_cycle=True))
        assert "red" in why.lower()


class TestNoOtherSupplyIsWithheldOnAccountOfIt:
    """The whole point of the amendment, and the half the old
    requirement got wrong."""

    def test_an_on_cycle_supply_promotes_normally(self):
        promote, why = promotion.should_promote(**a_supply(arrived_off_cycle=False))
        assert promote is True, why

    def test_the_gate_is_a_fact_about_ONE_supply(self):
        """Structural: the predicate takes a dataset and an instant, and
        nothing about any other supply. A delivery cannot be passed to
        it, so a sibling cannot influence it."""
        import inspect

        params = list(inspect.signature(promotion.arrived_off_cycle).parameters)
        assert params == ["dataset_id", "at"]

    def test_spans_periods_is_gone(self):
        """A delivery MAY span periods now, and nothing withholds it for
        that - so the predicate that used to decide it should not
        survive to be called by mistake."""
        assert not hasattr(promotion, "spans_periods")
