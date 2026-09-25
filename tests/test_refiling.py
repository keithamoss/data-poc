"""An arrival verdict follows its filing, and is never a frozen fact
(REQ-PIPE-067).

A supply reported late purely because it was MISFILED was never
actually late. Leaving that verdict in place for the sake of
immutability is the one place this design would knowingly say something
untrue, so the verdict moves when the filing does.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import arrival_classification as classify_mod
from qa_tools.common import assignment, filing
from qa_tools.common.schedule import Period
from qa_tools.common.slots import Slot

PERTH = timezone(timedelta(hours=8))

ARRIVED = datetime(2026, 7, 25, 9, tzinfo=PERTH)

SLOTS = {
    "2026-Q2": Slot(dataset_id="d", period=Period(name="2026-Q2", date=datetime(2026, 5, 1).date()),
                     due_at=datetime(2026, 5, 1, 12, tzinfo=PERTH), grace=timedelta(hours=1),
                     claim_opens_at=datetime(2026, 4, 25, 12, tzinfo=PERTH)),
    "2026-Q3": Slot(dataset_id="d", period=Period(name="2026-Q3", date=datetime(2026, 8, 1).date()),
                     due_at=datetime(2026, 8, 1, 12, tzinfo=PERTH), grace=timedelta(hours=1),
                     claim_opens_at=datetime(2026, 7, 25, 12, tzinfo=PERTH)),
}


def _slot_by_name(name):
    return SLOTS.get(name)


@pytest.fixture
def filings(tmp_path):
    directory = tmp_path / "filings"
    filing.record(assignment.Assignment(
        dataset_id="d", supply_id="s", slot="2026-Q2",
        branch=assignment.OLDEST_CLAIMABLE, considered=("2026-Q2",)), directory)
    return directory


class TestTheVerdictFollowsTheFiling:
    """Criteria 1 and 2."""

    def test_a_misfiled_supply_reads_late_before_it_is_moved(self, filings):
        got = filing.classification_of("d", "s", ARRIVED, _slot_by_name, filings)
        assert got == classify_mod.LATE, (
            "the fixture must start from the wrong answer, or the test below proves "
            "nothing")

    def test_and_stops_reading_late_once_it_is_filed_correctly(self, filings):
        filing.refile("d", "s", "2026-Q3", refiling_id="dec-1", filings_dir=filings)
        got = filing.classification_of("d", "s", ARRIVED, _slot_by_name, filings)
        assert got == classify_mod.EARLY, (
            "the record must never keep a verdict everybody knows to be untrue")

    def test_the_verdict_is_not_stored_as_a_frozen_fact(self, filings):
        """Criterion 2, asserted structurally: nothing writes a
        classification into the filing record, so there is nothing that
        could go stale."""
        import json
        record = json.loads(
            filing.path_for("d", "s", filings).read_text())
        assert "classification" not in record and "arrival_status" not in record


class TestTheArrivalInstantDoesNotMove:
    """Criterion 3 - when we received something is a FACT; which period
    it was for is a DECISION, and only the second is being changed."""

    def test_refiling_changes_the_slot_and_nothing_about_the_arrival(self, filings):
        before = filing.filing_for("d", "s", filings)
        updated = filing.refile("d", "s", "2026-Q3", refiling_id="dec-1", filings_dir=filings)
        assert updated["slot"] == "2026-Q3"
        assert updated["supply_id"] == before["supply_id"]
        # The verdict is recomputed from the SAME instant.
        assert filing.classification_of("d", "s", ARRIVED, _slot_by_name, filings) \
            == classify_mod.EARLY


class TestItIsTraceableToTheRefiling:
    """Criterion 5, and the reason it is built now rather than deferred:
    the failure named at sign-off is five of six criteria built and the
    sixth quietly skipped as un-buildable."""

    def test_the_recomputation_carries_a_reference_to_what_caused_it(self, filings):
        updated = filing.refile("d", "s", "2026-Q3", refiling_id="dec-42",
                                 reason="supplier confirmed it was Q3",
                                 filings_dir=filings)
        assert updated[filing.REFILING_REFERENCE] == "dec-42"
        assert updated["refiled_from"] == "2026-Q2"
        assert updated["refiling_reason"] == "supplier confirmed it was Q3"

    def test_the_reference_is_required_rather_than_optional(self):
        """It dangles until the decision log exists in sprint 12 - but
        an optional reference is one that gets left out, and then
        nothing can ever be traced."""
        import inspect
        signature = inspect.signature(filing.refile)
        assert signature.parameters["refiling_id"].default is inspect.Parameter.empty

    def test_a_refile_is_one_act_rather_than_a_demote_and_a_promote(self, filings):
        """Under the composed version a re-file appears in the decision
        log as TWO entries, and a reader a year later has to infer they
        were one act."""
        updated = filing.refile("d", "s", "2026-Q3", refiling_id="dec-1", filings_dir=filings)
        assert updated["refiled_from"] == "2026-Q2" and updated["slot"] == "2026-Q3", (
            "one record carrying both the from-slot and the to-slot - 'why is this "
            "supply in Q3?' must have a single answer")


class TestAnUnchangedFilingIsNotRecomputed:
    """Criterion 6."""

    def test_refiling_to_the_same_slot_does_nothing(self, filings):
        assert filing.refile("d", "s", "2026-Q2", refiling_id="dec-1",
                              filings_dir=filings) is None

    def test_an_unfiled_supply_cannot_be_refiled(self, filings):
        assert filing.refile("d", "never-filed", "2026-Q3", refiling_id="dec-1",
                              filings_dir=filings) is None

    def test_the_record_is_untouched_by_a_no_op_refile(self, filings):
        before = filing.path_for("d", "s", filings).read_text()
        filing.refile("d", "s", "2026-Q2", refiling_id="dec-1", filings_dir=filings)
        assert filing.path_for("d", "s", filings).read_text() == before


class TestItIsLocalToTheSupplyThatMoved:
    """The non-functional constraint: a design needing the history
    replayed to answer this stops being usable once a daily feed has
    years behind it."""

    def test_another_supplys_filing_is_untouched(self, filings):
        filing.record(assignment.Assignment(
            dataset_id="d", supply_id="other", slot="2026-Q2",
            branch=assignment.ON_TIME, considered=("2026-Q2",)), filings)
        filing.refile("d", "s", "2026-Q3", refiling_id="dec-1", filings_dir=filings)
        assert filing.filing_for("d", "other", filings)["slot"] == "2026-Q2"

    def test_it_reads_one_record_rather_than_the_whole_history(self):
        """Checked against the executable BODY, not the whole source -
        a first version of this grepped the docstring too and failed on
        the word "for" inside a sentence."""
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(filing.classification_of)))
        body = tree.body[0].body
        if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]          # drop the docstring
        code = "\n".join(ast.unparse(node) for node in body)
        assert "filings_of(" not in code, (
            "answering one supply's verdict must not walk a dataset's history")
        assert not any(isinstance(n, (ast.For, ast.While))
                        for node in body for n in ast.walk(node)), (
            "a loop here means the cost grows with history, which is what the "
            "non-functional constraint forbids")
