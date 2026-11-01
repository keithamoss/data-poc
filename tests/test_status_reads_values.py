"""REQ-TEST-360 criteria 2 and 3: no behaviour hangs on worded status text.

Each place that used to decide something by reading a status WORD - a
reason's substring, a line's first word, the text before a colon - is moved
onto a status VALUE or a structured refusal kind. Every test here was written
first and seen failing against the reworded text (Pass / Warn / Fail,
REQ-DASH-359): rewording promotion.py's refusal, root_cause's overdue line or
the re-checked-worse reason silently changed what the old code did.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qa_tools.common import promotion


def _gate(status, **kw):
    args = dict(status=status, slot_filled=False, held_without_slot=False,
                has_active_checks=True)
    args.update(kw)
    return promotion.should_promote(**args)


class TestTheGateSaysWhyAsAKind:
    """knock_on._fails_the_rules, promotion.judge and gate._record_holdback
    decide by the refusal's KIND, never by its words (criterion 3)."""

    def test_a_failing_supply_fails_the_rules_whatever_the_words(self):
        from qa_tools.common import knock_on

        ok, why = _gate("red")
        assert not ok
        assert why.kind == promotion.FAILING
        assert "red" not in why.split()
        assert knock_on._fails_the_rules(why)

    def test_warning_under_hold_fails_the_rules(self):
        from qa_tools.common import knock_on

        ok, why = _gate("amber", amber_setting=promotion.AMBER_HOLD)
        assert not ok and why.kind == promotion.WARN_HOLD
        assert knock_on._fails_the_rules(why)

    def test_a_filled_slot_does_not(self):
        from qa_tools.common import knock_on

        ok, why = _gate("green", slot_filled=True)
        assert not ok and why.kind == promotion.SLOT_FILLED
        assert not knock_on._fails_the_rules(why)

    def test_a_reason_with_no_kind_does_not(self):
        """A held-back reason (gate.held_back_words) is plain text: it is not
        the supply failing the rules, as before."""
        from qa_tools.common import knock_on

        assert not knock_on._fails_the_rules("Held back: something else entirely")

    def test_judge_records_the_waiting_note_by_kind(self, monkeypatch):
        """promotion.py's own comparison (was `why == AMBER_WAITING_REASON`):
        a WARN_HOLD refusal worded differently still records the note."""
        recorded = []
        monkeypatch.setattr(promotion, "should_promote", lambda **k: (
            False, promotion.Refusal("reworded: waits for a person", promotion.WARN_HOLD)))
        monkeypatch.setattr(promotion, "_record_amber_waiting",
                            lambda conn, **k: recorded.append(k))
        _judge(monkeypatch, status="amber")
        assert len(recorded) == 1

    def test_judge_records_nothing_for_another_kind(self, monkeypatch):
        recorded = []
        monkeypatch.setattr(promotion, "should_promote", lambda **k: (
            False, promotion.Refusal(promotion.AMBER_WAITING_REASON, promotion.SLOT_FILLED)))
        monkeypatch.setattr(promotion, "_record_amber_waiting",
                            lambda conn, **k: recorded.append(k))
        _judge(monkeypatch, status="amber")
        assert recorded == []

    def test_the_gate_records_the_waiting_note_by_kind(self, monkeypatch):
        """gate.py's own comparison (was `why == promotion.AMBER_WAITING_REASON`)."""
        from qa_tools.common import gate

        recorded, refused = [], []
        monkeypatch.setattr(gate, "_red_only_for_want_of", lambda m: [])
        monkeypatch.setattr(gate, "_amber", lambda ds, at: None)
        monkeypatch.setattr(promotion, "_record_amber_waiting",
                            lambda conn, **k: recorded.append(k))
        monkeypatch.setattr(promotion, "_record_refused", lambda conn, **k: refused.append(k))
        member = SimpleNamespace(
            dataset_id="cp-carers", supply="cp-carers@1", item={"period": "2099-Q1"},
            received=None, out=("own", promotion.Judged(why=promotion.Refusal(
                "reworded: waits for a person", promotion.WARN_HOLD))))
        gate._record_holdback(None, 1, member, [member], "2026-11-01T09:00:00+08:00")
        assert len(recorded) == 1 and refused == []


def _judge(monkeypatch, *, status):
    from qa_tools.common import (amber_setting, decision_log, inheritance, rejection,
                                 supersession)

    monkeypatch.setattr(supersession, "is_superseded", lambda *a: False)
    monkeypatch.setattr(amber_setting, "resolve", lambda *a: amber_setting.Resolved(
        promotion.AMBER_HOLD, amber_setting.COLLECTION, "2023-01-01"))
    monkeypatch.setattr(decision_log, "held", lambda *a: None)
    monkeypatch.setattr(promotion, "filled_slots", lambda *a: frozenset())
    monkeypatch.setattr(inheritance, "inherited", lambda *a: None)
    monkeypatch.setattr(rejection, "decided_by_a_person", lambda *a: False)
    item = {"dataset_id": "cp-carers", "supply": "cp-carers@1", "period": "2099-Q1",
            "physical_tables": ["cp_carers__1"]}
    return promotion.judge(None, item, status, results=[], reads={},
                           effective_at="2026-11-01T09:00:00+08:00", barred={},
                           agency_id="child-protection-family-support",
                           collection_id="child-protection")


class TestTheOutcomeCarriesValueAndWords:
    """Criterion 2: (dataset_id, status value or None, words, result)."""

    def test_the_field_order_is_pinned(self):
        from cli import lifecycle_report

        assert lifecycle_report.ReGated._fields == ("dataset_id", "status", "words", "result")

    def test_knock_ons_entries_lead_with_the_same_four(self):
        from qa_tools.common import knock_on

        assert knock_on.Regated._fields[:4] == ("dataset_id", "status", "words", "result")

    def test_a_plain_phrase_travels_with_no_value(self):
        from cli import lifecycle_report

        lines = lifecycle_report.outcome_lines([
            lifecycle_report.ReGated("cp-a", None, "no verdict", "still waiting for a person"),
            lifecycle_report.ReGated("cp-b", "red", "failing", "still held back")])
        assert lines == ["- cp-b: failing, still held back",
                         "- cp-a: no verdict, still waiting for a person"]


class TestTheReportSortsByValue:
    """lifecycle_report.outcome_lines' sort (:284) and 'more' pointer (:288)
    by the status value, so REQ-PIPE-276 criterion 10's failing-first order
    holds whatever the words say."""

    def test_failing_lines_come_first(self):
        from cli import lifecycle_report

        lines = lifecycle_report.outcome_lines([
            lifecycle_report.ReGated("cp-a", "green", "passing", "promoted by the rule"),
            lifecycle_report.ReGated("cp-b", "red", "failing - could not run: x", "still held back")])
        assert lines[0].startswith("- cp-b: failing - could not run")

    def test_a_truncated_failing_line_points_to_the_queue(self):
        from cli import lifecycle_report

        many = [lifecycle_report.ReGated(f"cp-{i}", "red", "failing", "still held back")
                for i in range(lifecycle_report._NAMED + 2)]
        (line,) = lifecycle_report.outcome_lines(many, more="see the queue")
        assert line.endswith(" - see the queue")


class TestTheOverdueReasonHasNoStatusWord:
    """filing_tui.py :1205 took root_cause._overdue_words and stripped 'red
    because '; root_cause now gives the reason without its status word."""

    def test_a_supply_beneath_an_overdue_slot(self):
        from cli import filing_tui
        from qa_tools.common import period_schema, root_cause

        root = root_cause.Root(kind="slot", dataset_id="cp-clients", period="2024-Q4",
                               reason=period_schema.PAST_DUE)
        b = SimpleNamespace(traced=SimpleNamespace(root=root), reason="",
                            state=SimpleNamespace(period="2024-Q4"))
        words = filing_tui._beneath_words(b, "cp-clients")
        assert "could not run: cp-clients for 2024-Q4 is overdue; its checks run again" in words
        assert "because" not in words

    def test_the_queue_line_still_says_failing_because(self):
        from qa_tools.common import period_schema, root_cause

        root = root_cause.Root(kind="slot", dataset_id="cp-clients", period="2024-Q4",
                               reason=period_schema.PAST_DUE)
        assert root_cause._overdue_words(root) == (
            "failing because cp-clients for 2024-Q4 is overdue; its checks run again "
            "once one is promoted")


class TestTheReCheckedWorseStateCarriesItsVerdict:
    """filing_tui.py :1251 (and listed_words) cut the heading from the
    reason at its first colon; the state carries its verdict value."""

    @pytest.mark.parametrize("verdict,heading", [
        ("red", "Promoted, then failing on re-check"),
        ("amber", "Promoted, then warning on re-check")])
    def test_the_queue_heading_is_read_from_the_verdict(self, verdict, heading):
        from cli import filing_tui
        from qa_tools.common import filing_queue, slot_state

        label = filing_tui._label(slot_state.SlotState(
            dataset_id="cp-carers", period="2099-x", state=filing_queue.RECHECKED_WORSE,
            supply="cp-carers@1", verdict=verdict, reason="came back at 12:15: worse"))
        assert f"({heading})" in label

    def test_the_listed_line_too(self):
        from cli import filing_tui
        from qa_tools.common import filing_queue

        words = filing_tui.listed_words(SimpleNamespace(state=SimpleNamespace(
            state=filing_queue.RECHECKED_WORSE, verdict="red", reason="x: y", files=())))
        assert words == "in place in the warehouse - promoted, then failing on re-check"
