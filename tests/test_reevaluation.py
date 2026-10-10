"""REQ-PIPE-079 criteria 6 and 7 - what a newly arrived table sets off.

Criterion 6: when a table arrives that a cross-table check READS,
re-evaluate that check WITHIN THE SAME PERIOD ONLY. Criterion 7: name,
on the re-evaluated result, the arrival that caused it.

WHY "THE SAME PERIOD ONLY" IS THE WHOLE OF CRITERION 6. A cross-table
check compares tables that belong together, and "together" means one
period. August's carers arriving says nothing about May's placements -
re-running May's check because August arrived would produce a fresh
verdict computed from unchanged data, which is worse than not running
it: it looks like news.

WHY CRITERION 7 EXISTS. A result that changed without anybody touching
that dataset is a mystery to whoever reads it next. Naming the arrival
turns "this went red overnight" into "this went red when carers
arrived", which is the difference between a question and an answer.
"""
from __future__ import annotations

from qa_tools.common import reevaluation

READS = {
    "xt-carers-placements": ["cp_carers", "cp_placements"],
    "xt-clients-notifications": ["cp_clients", "cp_notifications"],
    "xt-all-three": ["cp_carers", "cp_clients", "cp_placements"],
}


class TestWhichChecksAreSetOff:
    """Criterion 6's first half."""

    def test_a_check_that_reads_the_arriving_table(self):
        plan = reevaluation.plan(table="cp_carers", period="2026-Q2", reads=READS)
        assert plan.check_ids == {"xt-carers-placements", "xt-all-three"}

    def test_a_check_that_does_not_read_it_is_untouched(self):
        plan = reevaluation.plan(table="cp_carers", period="2026-Q2", reads=READS)
        assert "xt-clients-notifications" not in plan.check_ids

    def test_a_table_nothing_reads_sets_nothing_off(self):
        plan = reevaluation.plan(table="cp_orphan", period="2026-Q2", reads=READS)
        assert plan.check_ids == set()
        assert plan.is_empty is True


class TestItNeverLeavesThePeriod:
    """Criterion 6's second half, and the part worth pinning hardest."""

    def test_the_plan_names_exactly_one_period(self):
        plan = reevaluation.plan(table="cp_carers", period="2026-Q2", reads=READS)
        assert plan.period == "2026-Q2"

    def test_two_arrivals_in_different_periods_do_not_merge(self):
        q1 = reevaluation.plan(table="cp_carers", period="2026-Q1", reads=READS)
        q2 = reevaluation.plan(table="cp_carers", period="2026-Q2", reads=READS)
        assert q1.period != q2.period
        assert q1.check_ids == q2.check_ids, \
            "the same checks are set off - what differs is the period they run in"


class TestTheResultSaysWhatCausedIt:
    """Criterion 7."""

    def test_the_arrival_is_named_on_the_result(self):
        record = reevaluation.mark({"check_id": "xt-all-three", "status": "red"},
                                    caused_by="cp_carers__a1b2c3d4")
        assert record[reevaluation.CAUSED_BY] == "cp_carers__a1b2c3d4"

    def test_the_rest_of_the_record_is_untouched(self):
        record = reevaluation.mark({"check_id": "xt-all-three", "status": "red"},
                                    caused_by="cp_carers__a1b2c3d4")
        assert record["check_id"] == "xt-all-three"
        assert record["status"] == "red"

    def test_it_does_not_mutate_what_it_was_given(self):
        """A writer that edits its caller's record is how one result's
        provenance ends up on the next one."""
        original = {"check_id": "xt-all-three", "status": "red"}
        reevaluation.mark(original, caused_by="cp_carers__a1b2c3d4")
        assert reevaluation.CAUSED_BY not in original

    def test_the_key_is_one_the_results_writer_carries_through(self):
        """qa_store.write_results puts any key it does not recognise into
        the `extra` jsonb column, so criterion 7 needs no new column -
        but only while the name stays off the known-column list."""
        from qa_tools.common import qa_store

        assert reevaluation.CAUSED_BY not in qa_store._RESULT_COLUMNS
        assert reevaluation.CAUSED_BY not in qa_store._KEY_COLUMNS
