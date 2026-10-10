"""Each dataset has its own arrival history (REQ-PIPE-034).

Built against real committed delivery records written by the real
delivery log, not hand-rolled dicts: the claim is about what this
repo's own history says, and a fixture shaped by hand would test the
fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_tools.common import arrival_history, delivery, delivery_log, load_log

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def logs(clean_delivery_log):
    """An empty delivery log on this worker's own database.

    It was a temporary DIRECTORY until REQ-PIPE-089 moved the record
    into the database; the name stays because every test here passes
    it straight through, and what it means - "the log these records go
    into" - has not changed.
    """
    return clean_delivery_log


def _drop(tmp_path, logs, name, files, when, sequence):
    """One real delivery, recognised and recorded the real way."""
    from qa_tools.common import arrivals

    deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
    folder = deliveries / name
    folder.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    for filename in files:
        (folder / filename).write_text("a\n1\n")
    delivery.write_receipts(name, when, receipts, files=files, sequence=sequence)
    d = delivery.read_delivery(name, deliveries, receipts)
    delivery_log.record(d, arrivals.recognise(d), conn=logs)
    return d


class TestADatasetsTimelineIsItsOwn:
    """Criteria 1, 6, 7 and 9."""

    def test_one_datasets_arrival_does_not_imply_anothers(self, tmp_path, logs):
        _drop(tmp_path, logs, "monday", ["cp_clients.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        assert len(arrival_history.arrivals_of("cp-clients", conn=logs)) == 1
        assert arrival_history.arrivals_of("cp-carers", conn=logs) == [], (
            "cp_carers was not in that delivery - a dataset that did not arrive must not "
            "gain a phantom arrival from sharing a directory with one that did")

    def test_each_arrival_carries_its_own_identifier_and_instant(self, tmp_path, logs):
        _drop(tmp_path, logs, "monday", ["cp_clients.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        [entry] = arrival_history.arrivals_of("cp-clients", conn=logs)
        assert entry.dataset_id == "cp-clients"
        assert entry.supply_id.startswith("cp-clients@")
        assert entry.received_at == "2026-01-01T09:00:00+08:00"

    def test_datasets_in_one_collection_need_no_shared_identifier(self, tmp_path, logs):
        """Criterion 7. Six tables in one delivery get six ids."""
        _drop(tmp_path, logs, "monday",
               ["cp_clients.csv", "cp_carers.csv", "cp_placements.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        ids = {arrival_history.arrivals_of(d, conn=logs)[0].supply_id
               for d in ("cp-clients", "cp-carers", "cp-placements")}
        assert len(ids) == 3, f"these three share an identifier: {ids}"

    def test_the_history_names_no_other_dataset(self, tmp_path, logs):
        """Criterion 9 - a delivery of three contributes exactly one
        arrival here, and says nothing about the other two."""
        _drop(tmp_path, logs, "monday",
               ["cp_clients.csv", "cp_carers.csv", "cp_placements.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        found = arrival_history.arrivals_of("cp-clients", conn=logs)
        assert len(found) == 1
        assert "carers" not in json.dumps(found[0].__dict__)


class TestTheSharedDeliveryIsStillRecorded:
    """Criterion 8, and it is the half a per-dataset view would lose."""

    def test_a_whole_collection_delivery_stays_distinguishable(self, tmp_path, logs):
        _drop(tmp_path, logs, "together",
               ["cp_clients.csv", "cp_carers.csv", "cp_placements.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        assert arrival_history.delivery_companions("together", conn=logs) == (
            "cp-carers", "cp-clients", "cp-placements")

    def test_coincidental_arrivals_are_not_one_delivery(self, tmp_path, logs):
        _drop(tmp_path, logs, "one", ["cp_clients.csv"], "2026-01-01T09:00:00+08:00", 1)
        _drop(tmp_path, logs, "two", ["cp_carers.csv"], "2026-01-01T09:05:00+08:00", 2)
        assert arrival_history.delivery_companions("one", conn=logs) == ("cp-clients",)
        assert arrival_history.delivery_companions("two", conn=logs) == ("cp-carers",)


class TestTheMostRecentArrival:
    """Criteria 2 and 5."""

    def test_it_is_the_newest_by_receipt(self, tmp_path, logs):
        for n, (when, seq) in enumerate([("2026-01-01T09:00:00+08:00", 1),
                                          ("2026-03-01T09:00:00+08:00", 2),
                                          ("2026-02-01T09:00:00+08:00", 3)], start=1):
            _drop(tmp_path, logs, f"drop-{n}", ["cp_clients.csv"], when, seq)
        assert arrival_history.last_arrived("cp-clients", conn=logs).received_at \
            == "2026-03-01T09:00:00+08:00"

    def test_a_supply_that_could_not_be_loaded_is_still_the_latest_arrival(
            self, tmp_path, logs, clean_load_log):
        """Criterion 2, and the reason this is not derived from the
        warehouse: a supplier sending garbage on Tuesday has NO table
        anywhere, so a catalogue-derived timeline would show Monday and
        the bad file would be invisible."""
        _drop(tmp_path, logs, "monday", ["cp_clients.csv"], "2026-01-01T09:00:00+08:00", 1)
        _drop(tmp_path, logs, "tuesday", ["cp_clients.csv"], "2026-01-02T09:00:00+08:00", 2)

        load_log.record("tuesday", "cp-clients", "cp_clients__20260102", load_log.FAILED,
                         "2026-01-02T09:05:00+08:00", reason="not a CSV")

        latest = arrival_history.last_arrived("cp-clients", conn=logs)
        assert latest.delivery == "tuesday"
        assert arrival_history.load_outcome(
            latest.supply_id, "cp-clients", "tuesday") == load_log.FAILED
        assert load_log.loaded_tables() == frozenset(), "no table exists for it"

    def test_nothing_recorded_means_none_rather_than_an_error(self, logs):
        assert arrival_history.last_arrived("cp-clients", conn=logs) is None


class TestPromotedIsNotAnswered:
    """Criterion 3, absent on purpose.

    The derivation signed off with it reads the warehouse catalogue,
    which this requirement's own reasoning forbids for the arrived side
    and forbids here for the same reason. Recorded as a defect after
    sign-off; its real source arrives in batch 4.
    """

    def test_it_never_reports_an_arrival_as_promoted(self, tmp_path, logs):
        _drop(tmp_path, logs, "monday", ["cp_clients.csv"], "2026-01-01T09:00:00+08:00", 1)
        assert arrival_history.last_arrived("cp-clients", conn=logs) is not None
        assert arrival_history.last_promoted("cp-clients", conn=logs) is None, (
            "answering the promoted question with the latest ARRIVAL is the exact "
            "conflation this requirement splits apart, and it reads fine until a red "
            "supply arrives")


class TestItCostsLessThanTheWholeHistory:
    """The non-functional constraint, measured rather than asserted.

    IT USED TO COUNT FILE OPENS. `_load()` was a reverse-sorted glob
    and `last_arrived()` stopped at the first delivery carrying the
    dataset, so the bound was real and countable: one open out of
    twelve. REQ-PIPE-089 made the records rows, and an early exit out
    of a list the database has already built saves parsing and nothing
    else - so the measurement had to move with the mechanism, or it
    would have gone on passing while measuring nothing.

    What it measures now is that the whole-log reader is NOT USED,
    which is the honest form of the same claim: the bound is a WHERE
    on this dataset plus a LIMIT, and anything reaching for
    `delivery_log.records()` has abandoned it.
    """

    @staticmethod
    def _watch_whole_log_reads(monkeypatch):
        from qa_tools.common import delivery_log as module

        reads = {"n": 0}
        real = module.records

        def counting(*args, **kwargs):
            reads["n"] += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(module, "records", counting)
        return reads

    def test_finding_the_latest_does_not_read_the_whole_log(
            self, tmp_path, logs, monkeypatch):
        for n in range(1, 13):
            _drop(tmp_path, logs, f"drop-{n:02d}", ["cp_clients.csv"],
                   f"2026-01-{n:02d}T09:00:00+08:00", n)

        reads = self._watch_whole_log_reads(monkeypatch)
        found = arrival_history.last_arrived("cp-clients", conn=logs)

        assert found.delivery == "drop-12"
        assert reads["n"] == 0, (
            "last_arrived() read the entire delivery log. Built eagerly this was 60 of "
            "60 records against the real log; the bound has to be in the query, not in "
            "a loop that stops early over a list already fetched in full.")

    def test_a_dataset_that_has_not_supplied_recently_costs_no_more(
            self, tmp_path, logs, monkeypatch):
        """The case the old bound handled WORST and this one does not.

        Under the file version the cost was "deliveries since this
        dataset last supplied", so a dataset quiet for a year walked a
        year of records. An index on the dataset does not care how long
        ago it was.
        """
        _drop(tmp_path, logs, "old", ["cp_clients.csv"], "2026-01-01T09:00:00+08:00", 1)
        for n in range(2, 8):
            _drop(tmp_path, logs, f"newer-{n}", ["cp_carers.csv"],
                   f"2026-01-{n:02d}T09:00:00+08:00", n)

        reads = self._watch_whole_log_reads(monkeypatch)
        found = arrival_history.last_arrived("cp-clients", conn=logs)

        assert found.delivery == "old"
        assert reads["n"] == 0, "a quiet dataset still cost a walk of the whole log"

    def test_one_datasets_history_never_fetches_anothers(self, tmp_path, logs):
        """The same bound on the whole-history question rather than the
        latest-arrival one."""
        _drop(tmp_path, logs, "mine", ["cp_clients.csv"], "2026-01-01T09:00:00+08:00", 1)
        for n in range(2, 6):
            _drop(tmp_path, logs, f"theirs-{n}", ["cp_carers.csv"],
                   f"2026-01-{n:02d}T09:00:00+08:00", n)

        from qa_tools.common import delivery_log as module
        fetched = module.records_carrying("cp-clients", conn=logs)
        assert [r["delivery"] for r in fetched] == ["mine"], (
            "records_carrying() returned deliveries that did not carry this dataset - "
            "the filter has to be in the query")


class TestTheWholeCorpusStillReadsBack:
    """Birth Registrations is the control: one table, one dataset, and
    a run of arrivals proves this generalises rather than
    special-casing Child Protection.

    IT USED TO ASSERT ON THE COMMITTED TREE - 42 recorded arrivals for
    Birth Registrations, 18 for each Child Protection dataset, read out
    of `delivery_log/` via the `real_committed_history` fixture. That
    corpus was state in the repository, which REQ-PIPE-089 removes, so
    the test builds its own. The claim was never about those particular
    numbers; it was that a long history reads back per dataset, with
    unique supply ids and no bleed between datasets.
    """

    @staticmethod
    def _corpus(tmp_path, logs, drops):
        for n in range(1, drops + 1):
            _drop(tmp_path, logs, f"extract-{n:02d}",
                   # Birth Registrations' real arrival pattern wants the
                   # date in the filename; an undated one is correctly
                   # recognised as nothing and warned about.
                   [f"birth_registrations_2026-01-{n:02d}.csv", "cp_clients.csv",
                    "cp_carers.csv", "cp_placements.csv"],
                   f"2026-01-{n:02d}T09:00:00+08:00", n)

    def test_one_dataset_has_its_own_unbroken_timeline(self, tmp_path, logs):
        self._corpus(tmp_path, logs, 20)
        found = arrival_history.arrivals_of("birth-registrations", conn=logs)
        assert len(found) == 20, f"{len(found)} arrivals, expected 20"
        assert all(a.dataset_id == "birth-registrations" for a in found)
        assert len({a.supply_id for a in found}) == len(found), "supply ids must be unique"

    def test_datasets_sharing_every_delivery_keep_their_own_ids(self, tmp_path, logs):
        self._corpus(tmp_path, logs, 20)
        counts = {d: arrival_history.arrivals_of(d, conn=logs)
                   for d in ("cp-clients", "cp-carers", "cp-placements")}
        assert {len(v) for v in counts.values()} == {20}
        ids = [v[0].supply_id for v in counts.values()]
        assert len(set(ids)) == 3, f"three datasets share one identifier: {ids}"
