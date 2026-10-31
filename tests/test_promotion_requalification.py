"""REQ-PIPE-075 criteria 16 and 17 - when a promotion needs QA re-running.

Criterion 16: promoting into the period the QA was ALREADY run against
does not re-run it. Criterion 17: promoting or re-filing into a
DIFFERENT period does, and re-evaluates the cross-table checks that read
the moved table.

WHY THIS IS A REAL RULE AND NOT BOOKKEEPING: a check's verdict is a
statement about a supply READ ALONGSIDE a particular period's other
tables. Move the supply to a different period and it sits beside
different tables, so a referential check that passed against August's
carers says nothing about May's. Re-running is not caution; the old
verdict is about a different question.

The pair is deliberately tested together, because the failure mode is
getting the boundary wrong in one direction - re-running everything
always (which makes promotion cost a QA run, the thing criterion 13
separates) or never (which leaves a verdict attached to data it was
never computed against).
"""
from __future__ import annotations

from qa_tools.common import promotion


class TestPromotingIntoTheSamePeriodDoesNotReRun:
    """Criterion 16."""

    def test_no_re_run(self):
        assert promotion.needs_requalification(
            qa_ran_against="2026-Q2", promoted_into="2026-Q2") is False

    def test_and_that_is_true_however_the_promotion_was_raised(self):
        # A person's promotion and the rule's reach the same answer:
        # the question is about the PERIOD, not about who asked.
        for actor_kind in ("person", "rule"):
            assert promotion.needs_requalification(
                qa_ran_against="2026-Q2", promoted_into="2026-Q2",
                actor_kind=actor_kind) is False


class TestPromotingIntoADifferentPeriodDoesReRun:
    """Criterion 17."""

    def test_it_re_runs(self):
        assert promotion.needs_requalification(
            qa_ran_against="2026-Q1", promoted_into="2026-Q2") is True

    def test_an_unknown_qa_period_re_runs_rather_than_assuming(self):
        """The safe direction. Not knowing what the verdict was computed
        against is not evidence that it still applies."""
        assert promotion.needs_requalification(
            qa_ran_against=None, promoted_into="2026-Q2") is True


class TestWhichCrossTableChecksHaveToBeReEvaluated:
    """Criterion 17's second half - 'the cross-table checks that read
    it', which is answerable from the check definitions rather than
    needing a new record."""

    def test_a_check_that_reads_the_moved_table_is_included(self):
        reads = {"xt1": ["cp_placements", "cp_carers"], "xt2": ["cp_clients"]}
        assert promotion.checks_reading("cp_carers", reads=reads) == {"xt1"}

    def test_a_check_that_does_not_read_it_is_left_alone(self):
        reads = {"xt1": ["cp_placements", "cp_clients"]}
        assert promotion.checks_reading("cp_carers", reads=reads) == set()

    def test_several_checks_reading_it_all_come_back(self):
        reads = {"xt1": ["cp_carers"], "xt2": ["cp_carers", "cp_clients"],
                 "xt3": ["cp_placements"]}
        assert promotion.checks_reading("cp_carers", reads=reads) == {"xt1", "xt2"}

    def test_nothing_declared_means_nothing_to_re_evaluate(self):
        assert promotion.checks_reading("cp_carers", reads={}) == set()
