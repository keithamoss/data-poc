"""REQ-PIPE-075 criteria 1-5 and 12 - what promotes itself, and what waits.

The gate is a PURE FUNCTION over facts the caller already has, which is
deliberate and is why it can be tested like this. Deciding whether to
promote and finding out what a supply's verdict was are different jobs;
`decision_log.Decision` already makes the same split for `supply_is_red`,
for the same reason - a module that goes browsing for its own inputs is
a module you cannot ask a hypothetical question of.

Every refusal carries a REASON, because "not promoted" with no
explanation is the state an operator has to escalate, and the reason is
what the ticket and the terminal both end up showing.
"""
from __future__ import annotations

import pytest

from qa_tools.common import promotion


def a_supply(**over):
    """A supply that WOULD promote itself, so each test changes one thing."""
    fields = dict(status="green", slot_filled=False, held_without_slot=False,
                  has_active_checks=True, decided_by_a_person=False)
    fields.update(over)
    return fields


class TestGreenOrAmberPromotesItself:
    """Criterion 1."""

    @pytest.mark.parametrize("status", ["green", "amber"])
    def test_it_promotes(self, status):
        promote, why = promotion.should_promote(**a_supply(status=status))
        assert promote is True
        assert why is None


class TestRedWaitsForAPerson:
    """Criterion 3."""

    def test_it_does_not_promote(self):
        promote, why = promotion.should_promote(**a_supply(status="red"))
        assert promote is False

    def test_and_says_why_in_terms_an_operator_can_act_on(self):
        _, why = promotion.should_promote(**a_supply(status="red"))
        assert why and "red" in why.lower()


class TestAFilledSlotIsNeverOverwritten:
    """Criterion 4 - whatever the supply's own status."""

    @pytest.mark.parametrize("status", ["green", "amber", "red"])
    def test_it_does_not_promote_into_a_filled_slot(self, status):
        """Whatever the status - which is the whole of criterion 4."""
        promote, why = promotion.should_promote(
            **a_supply(status=status, slot_filled=True))
        assert promote is False
        assert why, "a refusal always says why"

    @pytest.mark.parametrize("status", ["green", "amber"])
    def test_and_the_filled_slot_is_the_reason_given_where_it_is_the_binding_one(
            self, status):
        """Only where nothing else would have stopped it. A red supply
        into a filled slot is reported as red - see the ordering tests,
        which pin that deliberately."""
        _, why = promotion.should_promote(**a_supply(status=status, slot_filled=True))
        assert "filled" in why.lower()


class TestASupplyWithNoConfidentSlotIsLeftAlone:
    """Criterion 5 - not promoted, and not arrival-classified either."""

    def test_it_does_not_promote(self):
        promote, why = promotion.should_promote(**a_supply(held_without_slot=True))
        assert promote is False
        assert why and "slot" in why.lower()

    def test_and_the_caller_is_told_not_to_classify_it(self):
        assert promotion.may_arrival_classify(held_without_slot=True) is False
        assert promotion.may_arrival_classify(held_without_slot=False) is True


class TestACheckFreeTableCannotPromoteItself:
    """Criterion 12 - zero ACTIVE checks is ineligible, not 'green'.

    The dangerous direction: a table nobody wrote a check for computes as
    green by having no failures, and would otherwise promote itself on
    the strength of nothing having been asked of it.
    """

    def test_it_does_not_promote(self):
        promote, why = promotion.should_promote(**a_supply(has_active_checks=False))
        assert promote is False
        assert why and "check" in why.lower()

    def test_even_though_its_status_reads_green(self):
        promote, _ = promotion.should_promote(
            **a_supply(status="green", has_active_checks=False))
        assert promote is False

    def test_the_reason_is_the_silence_rather_than_the_missing_verdict(self):
        """status_of() returns None where nothing contributed, which is
        exactly the check-free case - so the two arrive together and the
        gate has to report the useful one.

        "Its status is None rather than green or amber" sends an
        operator looking for a failing check. There is no check. If
        nothing was asked, there is no answer to report, so the silence
        outranks the missing verdict.
        """
        _, why = promotion.should_promote(
            **a_supply(status=None, has_active_checks=False))
        assert "None" not in why
        assert "ACTIVE checks" in why


class TestAutomationDefersToAPersonPermanently:
    """REQ-PIPE-076 criterion 7, which this gate has to honour even though
    that requirement is built separately: once a person has decided
    anything about a supply, automation never promotes it afterwards."""

    def test_it_does_not_promote(self):
        promote, why = promotion.should_promote(**a_supply(decided_by_a_person=True))
        assert promote is False
        assert why and "person" in why.lower()


class TestTheReasonsAreOrderedSoTheMostUsefulOneWins:
    """Several refusals can apply at once. Which one an operator is told
    matters: 'the slot is filled' is actionable, 'it is red' is the thing
    they would fix first."""

    def test_red_is_reported_ahead_of_a_filled_slot(self):
        _, why = promotion.should_promote(
            **a_supply(status="red", slot_filled=True))
        assert "red" in why.lower()
