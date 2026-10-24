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

import filing_support
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


def _refile(dataset_id, supply_id, to_slot, decision_id=1):
    """A re-file as REQ-PIPE-141 makes one: a new filing, on a connection."""
    from qa_tools.common import supply_db

    with supply_db.connect(label="test-refile") as conn:
        return filing.refile(conn, dataset_id, supply_id, to_slot, decision_id=decision_id)


def _slot_by_name(name):
    return SLOTS.get(name)


@pytest.fixture
def filings(supply_dsn):
    """One misfiled supply, in this worker's own empty filing table.

    A TABLE since REQ-PIPE-104, where this used to be a temporary
    directory. The assertions below are unchanged; what changed is that
    isolation comes from the worker's own database, and `supply_id="s"`
    is exactly the kind of id that would otherwise collide across tests.
    """
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="test-clean-filings") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing CASCADE')
        filing_support.file(assignment.Assignment(
            dataset_id="d", supply_id="s", slot="2026-Q2",
            branch=assignment.OPEN_UNFILLED, considered=("2026-Q2",)))
        yield conn


class TestTheVerdictFollowsTheFiling:
    """Criteria 1 and 2."""

    def test_a_misfiled_supply_reads_late_before_it_is_moved(self, filings):
        got = filing.classification_of("d", "s", ARRIVED, _slot_by_name)
        assert got == classify_mod.LATE, (
            "the fixture must start from the wrong answer, or the test below proves "
            "nothing")

    def test_and_stops_reading_late_once_it_is_filed_correctly(self, filings):
        _refile("d", "s", "2026-Q3")
        got = filing.classification_of("d", "s", ARRIVED, _slot_by_name)
        assert got == classify_mod.EARLY, (
            "the record must never keep a verdict everybody knows to be untrue")

    def test_the_verdict_is_not_stored_as_a_frozen_fact(self, filings):
        """Criterion 2: no verdict is held against a filing with no
        receipt to judge, so there is nothing that could go stale. (The
        classification column IS the recorded verdict where there is a
        receipt - REQ-PIPE-080 - and a re-file rewrites it.)"""
        record = filing.filing_for("d", "s")
        assert record["classification"] is None and "arrival_status" not in record


class TestTheArrivalInstantDoesNotMove:
    """Criterion 3 - when we received something is a FACT; which period
    it was for is a DECISION, and only the second is being changed."""

    def test_refiling_changes_the_slot_and_nothing_about_the_arrival(self, filings):
        before = filing.filing_for("d", "s")
        updated = _refile("d", "s", "2026-Q3")
        assert updated["slot"] == "2026-Q3"
        assert updated["supply_id"] == before["supply_id"]
        # The verdict is recomputed from the SAME instant.
        assert filing.classification_of("d", "s", ARRIVED, _slot_by_name) \
            == classify_mod.EARLY


class TestItIsTraceableToTheRefiling:
    """Criterion 5, and the reason it is built now rather than deferred:
    the failure named at sign-off is five of six criteria built and the
    sixth quietly skipped as un-buildable."""

    def test_the_trace_is_not_kept_on_the_filing(self, filings):
        """REQ-PIPE-144 criterion 8: a re-file's from-period, to-period and
        reason belong to its decision-log entry (REQ-PIPE-074 criterion 9,
        REQ-PIPE-141), never on the filing - a second copy of a decision's
        facts is one that can disagree with the log."""
        _refile("d", "s", "2026-Q3")
        stored = filing.filing_for("d", "s")
        assert stored["slot"] == "2026-Q3"
        assert not {"refiled_by", "refiled_from", "refiling_reason"} & set(stored)

    def test_the_reference_is_required_rather_than_optional(self):
        """It dangles until the decision log exists in sprint 12 - but
        an optional reference is one that gets left out, and then
        nothing can ever be traced."""
        import inspect
        signature = inspect.signature(filing.refile)
        assert signature.parameters["decision_id"].default is inspect.Parameter.empty

    def test_a_refile_is_one_act_rather_than_a_demote_and_a_promote(self, filings):
        """Under the composed version a re-file appears in the decision
        log as TWO entries, and a reader a year later has to infer they
        were one act."""
        _refile("d", "s", "2026-Q3")
        stored = filing.filing_for("d", "s")
        assert stored["slot"] == "2026-Q3" and stored["branch"] == "refiled-by-a-person"

    def test_a_refile_keeps_its_delivery_link(self, filings):
        """REQ-PIPE-144 criterion 17: a re-filed supply still says which
        delivery it came from, so it is never refused for want of one."""
        before = filing.filing_for("d", "s")["delivery"]
        _refile("d", "s", "2026-Q3")
        assert before and filing.filing_for("d", "s")["delivery"] == before


class TestAnUnchangedFilingIsNotRecomputed:
    """Criterion 6."""

    def test_refiling_to_the_same_slot_does_nothing(self, filings):
        assert _refile("d", "s", "2026-Q2") is None

    def test_an_unfiled_supply_cannot_be_refiled(self, filings):
        assert _refile("d", "never-filed", "2026-Q3") is None

    def test_the_record_is_untouched_by_a_no_op_refile(self, filings):
        before = filing.filing_for("d", "s")
        _refile("d", "s", "2026-Q2")
        assert filing.filing_for("d", "s") == before


class TestItIsLocalToTheSupplyThatMoved:
    """The non-functional constraint: a design needing the history
    replayed to answer this stops being usable once a daily feed has
    years behind it."""

    def test_another_supplys_filing_is_untouched(self, filings):
        filing_support.file(assignment.Assignment(
            dataset_id="d", supply_id="other", slot="2026-Q2",
            branch=assignment.OPEN_UNFILLED, considered=("2026-Q2",)))
        _refile("d", "s", "2026-Q3")
        assert filing.filing_for("d", "other")["slot"] == "2026-Q2"

    def test_it_reads_one_record_rather_than_the_whole_history(self, filings, monkeypatch):
        """Counted, not grepped, as test_assignment's slot bisection is:
        with a long history filed for the dataset, answering one supply's
        verdict reads one filing row and resolves one slot."""
        for n in range(60):
            filing_support.file(assignment.Assignment(
                dataset_id="d", supply_id=f"history-{n:03d}", slot="2026-Q2",
                branch=assignment.OPEN_UNFILLED, considered=("2026-Q2",)))

        rows_read = []
        real_connect = filing._connect

        class Counting:
            def __init__(self, conn):
                self._conn = conn

            def __enter__(self):
                self._conn.__enter__()
                return self

            def __exit__(self, *exc):
                return self._conn.__exit__(*exc)

            def execute(self, *args, **kwargs):
                return CountedCursor(self._conn.execute(*args, **kwargs))

        class CountedCursor:
            def __init__(self, cursor):
                self._cursor = cursor

            def fetchall(self):
                rows = self._cursor.fetchall()
                rows_read.append(len(rows))
                return rows

            def fetchone(self):
                row = self._cursor.fetchone()
                rows_read.append(0 if row is None else 1)
                return row

        monkeypatch.setattr(filing, "_connect", lambda label: Counting(real_connect(label)))
        resolved = []

        got = filing.classification_of(
            "d", "s", ARRIVED, lambda name: resolved.append(name) or _slot_by_name(name))

        assert got == classify_mod.LATE
        assert sum(rows_read) == 1, (
            f"{sum(rows_read)} filing rows read for one supply's verdict - the cost "
            f"grows with history, which the non-functional constraint forbids")
        assert resolved == ["2026-Q2"]
