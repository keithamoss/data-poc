"""What each slot held, and when that changed (REQ-PIPE-081
criteria 1, 2, 3, 6 and 7).

THE QUESTION IS "WHAT WAS IN PLACE", NOT "WHAT HAD ARRIVED". The page
answers it today by filtering runs on their ARRIVAL date, which is a
different question wearing the same clothes: a supply that arrived in
June and was not promoted until August was not in place in June, and a
supply demoted in August was in place in June all the same.

THE ANSWERS ARE SHIPPED, NOT THE RULE, and that is the design decision
this module exists to carry. `decision_log.promoted_into(as_at=...)`
already resolves a slot correctly, but a static page cannot call it per
date - so the obvious move is to ship the decisions and let the page
apply the rule, which is a SECOND IMPLEMENTATION of it that can
disagree with the first. This project has been there: REQ-DASH-054
removed a JS port of the cadence rule for exactly this reason, and
CLAUDE.md records a day when four implementations of status existed and
one rendered a check with 14 violations green.

So what travels is a timeline of ANSWERS - what this slot resolved to
after each decision - and the page does a lookup rather than a
derivation.
"""
from __future__ import annotations

import pytest

from pipeline import slot_timeline
from qa_tools.common import decision_log, qa_store, supply_db

AGENCY, COLLECTION = "a", "c"


@pytest.fixture
def dataset():
    """A dataset id nothing else uses.

    ISOLATION BY KEY, NOT BY TRUNCATE, because `qa.decision` carries an
    append-only trigger that refuses one - "express a reversal as a new
    entry". That is the table behaving as designed, so the test bends
    rather than the table.
    """
    import uuid

    return f"d-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def clean(supply_dsn):
    with supply_db.connect(label="test-slot-timeline") as conn:
        qa_store.ensure_schema(conn)
        yield conn


def _decide(conn, dataset, action, *, supply, at, to_slot=None, from_slot=None,
            actor="somebody", kind=decision_log.PERSON, reason="because"):
    with decision_log.apply_decision(conn, decision_log.Decision(
        agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
        action=action, supply=supply, actor=actor, actor_kind=kind,
        effective_at=at, to_slot=to_slot, from_slot=from_slot, reason=reason)):
        pass


class TestWhatASlotResolvedTo:

    def test_a_promotion_puts_a_supply_in_place_from_its_effective_instant(self, clean, dataset):
        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        got = slot_timeline.for_dataset(dataset, conn=clean)
        assert [(e["slot"], e["supply"]) for e in got] == [("2026-Q1", "s1")]
        assert got[0]["at"].startswith("2026-02-01")

    def test_a_demotion_empties_it_WITHOUT_erasing_the_earlier_answer(self, clean, dataset):
        """Criterion 2, and the half that makes as-at-T worth having: in
        June the slot held s1, and an August demotion does not change
        that."""
        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        _decide(clean, dataset, decision_log.DEMOTE, supply="s1",
                at="2026-08-01T09:00:00+08:00", from_slot="2026-Q1")
        got = slot_timeline.for_dataset(dataset, conn=clean)
        assert [(e["slot"], e["supply"]) for e in got] == [
            ("2026-Q1", "s1"), ("2026-Q1", None)]

    def test_it_is_ordered_by_the_instant_the_decision_TOOK_EFFECT(self, clean, dataset):
        """Not by when it was recorded. A decision taken on Tuesday and
        recorded on Friday took effect on Tuesday - using the recorded
        instant answers "what did we know", which is a real question
        and not this one."""
        _decide(clean, dataset, decision_log.PROMOTE, supply="later-decision-earlier-effect",
                at="2026-01-01T09:00:00+08:00", to_slot="2026-Q1")
        _decide(clean, dataset, decision_log.PROMOTE, supply="earlier-decision-later-effect",
                at="2026-06-01T09:00:00+08:00", to_slot="2026-Q2")
        got = slot_timeline.for_dataset(dataset, conn=clean)
        assert [e["at"][:10] for e in got] == ["2026-01-01", "2026-06-01"]

    def test_a_rejection_empties_the_slot_too(self, clean, dataset):
        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        _decide(clean, dataset, decision_log.REJECT, supply="s1",
                at="2026-03-01T09:00:00+08:00", from_slot="2026-Q1")
        assert slot_timeline.for_dataset(dataset, conn=clean)[-1]["supply"] is None

    def test_a_refile_empties_one_slot_and_leaves_the_other_waiting(self, clean, dataset):
        """One decision, two slots. Since REQ-PIPE-141 a re-filed supply
        waits in its new period, checked again, so only the old slot
        changes - the new one is filled by the promotion that follows."""
        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        _decide(clean, dataset, decision_log.REFILE, supply="s1",
                at="2026-03-01T09:00:00+08:00", from_slot="2026-Q1", to_slot="2026-Q2")
        got = slot_timeline.for_dataset(dataset, conn=clean)
        after = {(e["slot"], e["supply"]) for e in got if e["at"].startswith("2026-03")}
        assert after == {("2026-Q1", None)}


class TestItNamesTheDecisionThatChangedAnEarlierAnswer:
    """Criterion 6 - saying an earlier date now shows something else is
    only useful if a reader can see WHICH decision did it."""

    def test_each_entry_carries_the_decision_that_produced_it(self, clean, dataset):
        # Promoted first: only the period's holder can be demoted (#113).
        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        _decide(clean, dataset, decision_log.DEMOTE, supply="s1",
                at="2026-08-01T09:00:00+08:00", from_slot="2026-Q1",
                actor="keith", reason="the extract was truncated")
        entry = slot_timeline.for_dataset(dataset, conn=clean)[-1]
        assert entry["action"] == decision_log.DEMOTE
        assert entry["actor"] == "keith"
        assert entry["reason"] == "the extract was truncated"
        assert entry["decision_id"]


class TestItAgreesWithTheRuleItShipsAnswersFor:
    """The guard that makes shipping answers safe. The page does a
    LOOKUP against this timeline; `promoted_into()` is the rule. If the
    two ever disagree the page is quietly wrong, so they are compared
    rather than trusted."""

    def test_every_instant_resolves_the_way_promoted_into_does(self, clean, dataset):
        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        _decide(clean, dataset, decision_log.DEMOTE, supply="s1",
                at="2026-05-01T09:00:00+08:00", from_slot="2026-Q1")
        _decide(clean, dataset, decision_log.PROMOTE, supply="s2",
                at="2026-07-01T09:00:00+08:00", to_slot="2026-Q1")

        for at in ("2026-01-01T00:00:00+08:00", "2026-03-01T00:00:00+08:00",
                   "2026-06-01T00:00:00+08:00", "2026-09-01T00:00:00+08:00"):
            by_rule = decision_log.promoted_into(clean, dataset, "2026-Q1", as_at=at)
            by_lookup = slot_timeline.in_place_on(
                slot_timeline.for_dataset(dataset, conn=clean), "2026-Q1", at)
            assert by_lookup == by_rule, f"disagreed at {at}"


class TestItReadsTheLogAndNothingElse:
    """Criterion 3. What a period resolved to as at T is a fact about
    decisions taken; the warehouse's current contents are the result of
    the newest one, so reading those answers "now" whatever T was."""

    def test_it_names_no_schema_that_holds_supply_rows(self):
        import ast
        import inspect

        # THE CODE, NOT THE PROSE. The module's own docstring explains
        # at length what it does NOT read, so a substring search over
        # the source finds every forbidden word and proves nothing -
        # the same false positive this project hit once already on
        # outstanding.py. Strings and names in the parsed tree are what
        # a query would actually be built from.
        tree = ast.parse(inspect.getsource(slot_timeline))
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue  # a bare docstring expression
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for forbidden in ("staging", "period_", "rejected"):
                    assert forbidden not in node.value, (
                        f"slot_timeline builds a string naming {forbidden!r}, "
                        f"which is about the warehouse's contents rather "
                        f"than the decisions taken")


class TestEachEntryCanBeTiedToItsRun:
    """The page needs to get from "this slot held supply X" to the run
    whose results it should show, and the supply id is not a run id.

    KEPT SEPARATE FROM for_dataset() ON PURPOSE. Criterion 3 says an
    "as at T" answer comes from the decision log alone, and that is
    what for_dataset() reads. The run lookup is a different recorded
    fact in a different table, so it is a different function - rather
    than quietly widening what the log-only one touches.
    """

    def test_it_adds_the_run_that_checked_each_supply(self, clean, dataset, monkeypatch):
        from pipeline import slot_timeline as st

        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        monkeypatch.setattr(st, "_run_for", lambda conn, d, supply: "run_042")

        got = st.with_runs(st.for_dataset(dataset, conn=clean), dataset, conn=clean)
        assert got[0]["run_id"] == "run_042"

    def test_an_emptied_slot_names_no_run(self, clean, dataset):
        from pipeline import slot_timeline as st

        # Promoted first: only the period's holder can be demoted (#113).
        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        _decide(clean, dataset, decision_log.DEMOTE, supply="s1",
                at="2026-08-01T09:00:00+08:00", from_slot="2026-Q1")
        got = st.with_runs(st.for_dataset(dataset, conn=clean), dataset, conn=clean)
        assert got[-1]["supply"] is None and got[-1]["run_id"] is None

    def test_a_supply_no_run_checked_is_not_an_error(self, clean, dataset):
        """A real state rather than a fault - a supply promoted by hand
        before any QA run read it has no run, and the entry is still
        the truth about what the slot held."""
        from pipeline import slot_timeline as st

        _decide(clean, dataset, decision_log.PROMOTE, supply="never-checked",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        got = st.with_runs(st.for_dataset(dataset, conn=clean), dataset, conn=clean)
        assert got[0]["supply"] == "never-checked" and got[0]["run_id"] is None


class TestTheTimelineIsTheViewsAnswers:
    """REQ-PIPE-130 criterion 9: what a slot held comes from qa.slot_holds,
    not from a rule restated here. The restatement read a withheld note as
    emptying the slot it names (post-build-review #84's shape, a fourth
    copy), so the page's "in place on" would have shown a filled period
    as empty from the moment automation stood back from a resupply."""

    def test_a_withheld_note_does_not_empty_the_slot(self, clean, dataset):
        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-01-01T00:00:00+08:00", to_slot="2026-Q1")
        _decide(clean, dataset, decision_log.PROMOTION_WITHHELD, supply="s2",
                at="2026-02-01T00:00:00+08:00", to_slot="2026-Q1",
                actor="promotion rule", kind=decision_log.RULE)
        timeline = slot_timeline.for_dataset(dataset, conn=clean)
        assert slot_timeline.in_place_on(
            timeline, "2026-Q1", "2026-03-01T00:00:00+08:00") == "s1"
        assert [e["supply"] for e in timeline] == ["s1"]


class TestEachSuppliesStateOverTime:
    """REQ-PIPE-081 criteria 1, 2 and 8 as amended 2026-10-05 (Keith): the
    page's verdict comes from the newest supply PROMOTED or AWAITING A
    DECISION on the date on show, and a withdrawn one - demoted, rejected,
    re-filed out or superseded - leaves the view. The answers travel: each
    supply's state after every decision about it; before the first, a
    filed supply is waiting."""

    def test_promoted_then_demoted_is_withdrawn_from_the_demote(self, clean, dataset):
        _decide(clean, dataset, decision_log.PROMOTE, supply="s1",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1")
        _decide(clean, dataset, decision_log.DEMOTE, supply="s1",
                at="2026-03-01T09:00:00+08:00", from_slot="2026-Q1")
        got = slot_timeline.supply_states(dataset, conn=clean)["s1"]
        assert [e["state"] for e in got] == ["promoted", "withdrawn"]
        assert got[1]["at"].startswith("2026-03-01")

    def test_a_withheld_note_leaves_it_waiting(self, clean, dataset):
        _decide(clean, dataset, decision_log.PROMOTION_WITHHELD, supply="s2",
                at="2026-02-01T09:00:00+08:00", to_slot="2026-Q1", kind=decision_log.RULE)
        assert "s2" not in slot_timeline.supply_states(dataset, conn=clean)

    def test_rejected_is_withdrawn(self, clean, dataset):
        _decide(clean, dataset, decision_log.REJECT, supply="s3",
                at="2026-02-01T09:00:00+08:00", from_slot="2026-Q1")
        assert [e["state"] for e in slot_timeline.supply_states(dataset, conn=clean)["s3"]] == \
            ["withdrawn"]

    def test_keyed_by_the_run_that_checked_each(self, clean, dataset, monkeypatch):
        from pipeline import slot_timeline as st

        _decide(clean, dataset, decision_log.REJECT, supply="s4",
                at="2026-02-01T09:00:00+08:00", from_slot="2026-Q1")
        monkeypatch.setattr(st, "_run_for", lambda conn, d, supply: "run_007")
        assert [e["state"] for e in st.run_states(dataset, conn=clean)["run_007"]] == ["withdrawn"]
