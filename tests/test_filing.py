"""Where each supply was filed, recorded once (REQ-PIPE-062).

The assignment RULE is tested in tests/test_assignment.py, against real
sequences. This covers the record: written once, never re-derived, and
kept strictly apart from whether a slot is FILLED.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import assignment, filing

PERTH = timezone(timedelta(hours=8))


@pytest.fixture
def filings(tmp_path):
    return tmp_path / "filings"


def _assignment(supply_id="cp-clients@2026", slot="2026-Q1",
                 branch=assignment.ON_TIME, dataset_id="cp-clients"):
    return assignment.Assignment(
        dataset_id=dataset_id, supply_id=supply_id, slot=slot, branch=branch,
        considered=(slot,) if slot else ())


class TestWrittenOnceAndNeverReDerived:
    """Criterion 10."""

    def test_a_second_run_leaves_an_existing_filing_alone(self, filings):
        first = filing.record(_assignment(), filings)
        assert first is not None
        before = first.read_text()

        # A later run would derive a DIFFERENT answer, because the slot
        # state has moved on. It must not write.
        again = filing.record(
            _assignment(slot="2026-Q4", branch=assignment.RESUPPLY), filings)
        assert again is None
        assert first.read_text() == before, (
            "re-deriving silently undoes a human's re-file and makes history move "
            "under a reader")

    def test_the_stored_filing_keeps_the_branch_it_was_decided_by(self, filings):
        filing.record(_assignment(branch=assignment.OLDEST_CLAIMABLE), filings)
        stored = filing.filing_for("cp-clients", "cp-clients@2026", filings)
        assert stored["branch"] == assignment.OLDEST_CLAIMABLE
        assert stored["considered"] == ["2026-Q1"], (
            "recomputing this later is NOT equivalent - the slot state it was decided "
            "against has moved on")

    def test_an_unfiled_supply_reads_as_none_rather_than_erroring(self, filings):
        assert filing.filing_for("cp-clients", "never-seen", filings) is None


class TestFiledIsNotFilled:
    """The distinction that keeps the forward cascade out.

    The rejected 14:00 supply in this requirement's own worked example
    IS filed against Monday. If that counted as filling Monday, the
    16:00 resupply would be pushed to Tuesday and every supply after it
    would be off by one, permanently.
    """

    def test_filing_a_supply_does_not_fill_its_slot(self, filings):
        filing.record(_assignment(slot="2026-Q1"), filings)
        assert filing.filings_of("cp-clients", filings)[0]["slot"] == "2026-Q1"
        assert filing.filled_slots("cp-clients", filings) == frozenset(), (
            "only a PROMOTION fills a slot - an arrival does not, a staged supply does "
            "not, and a rejected one certainly does not")

    def test_the_cascade_that_would_follow_if_it_did(self, filings):
        """Run as the real sequence, so the consequence is visible
        rather than argued."""
        from qa_tools.common.schedule import Period
        from qa_tools.common.slots import Slot

        def slot(day):
            due = datetime(2026, 6, day, 12, tzinfo=PERTH)
            return Slot(dataset_id="d", period=Period(name=f"{day:02d}", date=due.date()),
                         due_at=due, grace=timedelta(hours=1),
                         claim_opens_at=due - timedelta(hours=6))

        slots = [slot(d) for d in range(1, 4)]
        at = datetime(2026, 6, 1, 20, tzinfo=PERTH)

        # What the real rule does, with nothing promoted.
        real = assignment.assign("d", "s3", at, slots, filing.filled_slots("d", filings))
        assert real.slot == "01"

        # What it would do if a FILING counted as a fill.
        wrong = assignment.assign("d", "s3", at, slots, frozenset({"01"}))
        assert wrong.slot == "01" and wrong.branch == assignment.RESUPPLY


class TestADatasetsFilingsAreItsOwn:
    def test_they_are_read_from_that_datasets_own_directory(self, filings):
        filing.record(_assignment(dataset_id="cp-clients",
                                   supply_id="cp-clients@1"), filings)
        filing.record(_assignment(dataset_id="cp-carers",
                                   supply_id="cp-carers@1"), filings)
        assert len(filing.filings_of("cp-clients", filings)) == 1
        assert len(filing.filings_of("cp-carers", filings)) == 1
        assert filing.filings_of("cp-placements", filings) == []

    def test_a_supplier_id_with_odd_characters_becomes_a_usable_path(self, filings):
        written = filing.record(_assignment(supply_id="cp-clients@2026#2"), filings)
        assert written is not None and written.is_file()
        assert json.loads(written.read_text())["supply_id"] == "cp-clients@2026#2"


class TestFilingRealArrivals:
    """The entry point the orchestrators call, against real arrivals.

    IT BUILDS ITS OWN DELIVERIES rather than reading data/deliveries/,
    and that is not a stylistic preference - it is the difference
    between green and red. data/ is GITIGNORED, so a freshly-cloned CI
    runner has none at all: the first version of these tests read the
    real tree, passed here, and failed on the runner for four
    consecutive pushes with "expected one filing per CP dataset, got
    0". CLAUDE.md records this exact trap, and it was walked into
    anyway.
    """

    @staticmethod
    def _delivery(tmp_path, name, files, when, sequence):
        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        folder = deliveries / name
        folder.mkdir(parents=True, exist_ok=True)
        receipts.mkdir(parents=True, exist_ok=True)
        for filename in files:
            (folder / filename).write_text("a\n1\n")
        (receipts / f"{name}.json").write_text(json.dumps(
            {"delivery": name, "received_at": when, "sequence": sequence}))
        return deliveries, receipts

    def _arrivals(self, tmp_path, collection="child-protection", prefix="cp_run_"):
        from qa_tools.common import arrivals

        deliveries, receipts = self._delivery(
            tmp_path, "monday",
            ["cp_clients.csv", "cp_carers.csv", "cp_placements.csv",
             "cp_notifications.csv", "cp_investigations.csv", "cp_case_workers.csv"],
            "2026-02-01T09:00:00+08:00", 1)
        return arrivals.arrivals_for(collection, prefix, deliveries, receipts)

    def test_every_dataset_in_a_delivery_is_filed_separately(self, filings, tmp_path):
        found = self._arrivals(tmp_path)
        assert found, "the fixture must actually produce an arrival, or this proves nothing"
        written = filing.file_arrivals(found, filings)
        assert len(written) == 6, f"expected one filing per CP dataset, got {len(written)}"
        assert len({a.dataset_id for a in written}) == 6
        assert len({a.supply_id for a in written}) == 6, "each dataset needs its own id"

    def test_a_second_pass_files_nothing(self, filings, tmp_path):
        found = self._arrivals(tmp_path)
        assert filing.file_arrivals(found, filings)
        assert filing.file_arrivals(found, filings) == [], (
            "criterion 10 - a supply already filed is left alone on every later run")

    def test_a_red_supply_is_filed_on_the_same_terms(self, filings, tmp_path):
        """Criterion 11. A supply never promoted still carries where it
        was filed - "arrived three weeks late AND was bad" is what
        belongs on the record."""
        from qa_tools.common import arrivals

        deliveries, receipts = self._delivery(
            tmp_path, "bdm-drop", ["birth_registrations_2026-02-01.csv"],
            "2026-02-01T09:00:00+08:00", 1)
        found = arrivals.arrivals_for("civil-registration", "run_", deliveries, receipts)
        assert found, "the fixture must actually produce an arrival"
        written = filing.file_arrivals(found, filings)
        assert written and all(a.slot is not None for a in written), (
            "a supply must be filed before it is checked")
