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
def logs(tmp_path):
    return tmp_path / "delivery_log"


def _drop(tmp_path, logs, name, files, when, sequence):
    """One real delivery, recognised and recorded the real way."""
    from qa_tools.common import arrivals

    deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
    folder = deliveries / name
    folder.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    for filename in files:
        (folder / filename).write_text("a\n1\n")
    (receipts / f"{name}.json").write_text(json.dumps(
        {"delivery": name, "received_at": when, "sequence": sequence}))
    d = delivery.read_delivery(name, deliveries, receipts)
    delivery_log.record(d, arrivals.recognise(d), logs)
    return d


class TestADatasetsTimelineIsItsOwn:
    """Criteria 1, 6, 7 and 9."""

    def test_one_datasets_arrival_does_not_imply_anothers(self, tmp_path, logs):
        _drop(tmp_path, logs, "monday", ["cp_clients.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        assert len(arrival_history.arrivals_of("cp-clients", logs)) == 1
        assert arrival_history.arrivals_of("cp-carers", logs) == [], (
            "cp_carers was not in that delivery - a dataset that did not arrive must not "
            "gain a phantom arrival from sharing a directory with one that did")

    def test_each_arrival_carries_its_own_identifier_and_instant(self, tmp_path, logs):
        _drop(tmp_path, logs, "monday", ["cp_clients.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        [entry] = arrival_history.arrivals_of("cp-clients", logs)
        assert entry.dataset_id == "cp-clients"
        assert entry.supply_id.startswith("cp-clients@")
        assert entry.received_at == "2026-01-01T09:00:00+08:00"

    def test_datasets_in_one_collection_need_no_shared_identifier(self, tmp_path, logs):
        """Criterion 7. Six tables in one delivery get six ids."""
        _drop(tmp_path, logs, "monday",
               ["cp_clients.csv", "cp_carers.csv", "cp_placements.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        ids = {arrival_history.arrivals_of(d, logs)[0].supply_id
               for d in ("cp-clients", "cp-carers", "cp-placements")}
        assert len(ids) == 3, f"these three share an identifier: {ids}"

    def test_the_history_names_no_other_dataset(self, tmp_path, logs):
        """Criterion 9 - a delivery of three contributes exactly one
        arrival here, and says nothing about the other two."""
        _drop(tmp_path, logs, "monday",
               ["cp_clients.csv", "cp_carers.csv", "cp_placements.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        found = arrival_history.arrivals_of("cp-clients", logs)
        assert len(found) == 1
        assert "carers" not in json.dumps(found[0].__dict__)


class TestTheSharedDeliveryIsStillRecorded:
    """Criterion 8, and it is the half a per-dataset view would lose."""

    def test_a_whole_collection_delivery_stays_distinguishable(self, tmp_path, logs):
        _drop(tmp_path, logs, "together",
               ["cp_clients.csv", "cp_carers.csv", "cp_placements.csv"],
               "2026-01-01T09:00:00+08:00", 1)
        assert arrival_history.delivery_companions("together", logs) == (
            "cp-carers", "cp-clients", "cp-placements")

    def test_coincidental_arrivals_are_not_one_delivery(self, tmp_path, logs):
        _drop(tmp_path, logs, "one", ["cp_clients.csv"], "2026-01-01T09:00:00+08:00", 1)
        _drop(tmp_path, logs, "two", ["cp_carers.csv"], "2026-01-01T09:05:00+08:00", 2)
        assert arrival_history.delivery_companions("one", logs) == ("cp-clients",)
        assert arrival_history.delivery_companions("two", logs) == ("cp-carers",)


class TestTheMostRecentArrival:
    """Criteria 2 and 5."""

    def test_it_is_the_newest_by_receipt(self, tmp_path, logs):
        for n, (when, seq) in enumerate([("2026-01-01T09:00:00+08:00", 1),
                                          ("2026-03-01T09:00:00+08:00", 2),
                                          ("2026-02-01T09:00:00+08:00", 3)], start=1):
            _drop(tmp_path, logs, f"drop-{n}", ["cp_clients.csv"], when, seq)
        assert arrival_history.last_arrived("cp-clients", logs).received_at \
            == "2026-03-01T09:00:00+08:00"

    def test_a_supply_that_could_not_be_loaded_is_still_the_latest_arrival(
            self, tmp_path, logs):
        """Criterion 2, and the reason this is not derived from the
        warehouse: a supplier sending garbage on Tuesday has NO table
        anywhere, so a catalogue-derived timeline would show Monday and
        the bad file would be invisible."""
        _drop(tmp_path, logs, "monday", ["cp_clients.csv"], "2026-01-01T09:00:00+08:00", 1)
        _drop(tmp_path, logs, "tuesday", ["cp_clients.csv"], "2026-01-02T09:00:00+08:00", 2)

        processing = tmp_path / "processing_log"
        load_log.record("tuesday", "cp-clients", "cp_clients__20260102", load_log.FAILED,
                         "2026-01-02T09:05:00+08:00", reason="not a CSV", log_dir=processing)

        latest = arrival_history.last_arrived("cp-clients", logs)
        assert latest.delivery == "tuesday"
        assert arrival_history.load_outcome(
            latest.supply_id, "cp-clients", "tuesday", processing) == load_log.FAILED
        assert load_log.loaded_tables(processing) == frozenset(), "no table exists for it"

    def test_nothing_recorded_means_none_rather_than_an_error(self, logs):
        assert arrival_history.last_arrived("cp-clients", logs) is None


class TestPromotedIsNotAnswered:
    """Criterion 3, absent on purpose.

    The derivation signed off with it reads the warehouse catalogue,
    which this requirement's own reasoning forbids for the arrived side
    and forbids here for the same reason. Recorded as a defect after
    sign-off; its real source arrives in batch 4.
    """

    def test_it_never_reports_an_arrival_as_promoted(self, tmp_path, logs):
        _drop(tmp_path, logs, "monday", ["cp_clients.csv"], "2026-01-01T09:00:00+08:00", 1)
        assert arrival_history.last_arrived("cp-clients", logs) is not None
        assert arrival_history.last_promoted("cp-clients", logs) is None, (
            "answering the promoted question with the latest ARRIVAL is the exact "
            "conflation this requirement splits apart, and it reads fine until a red "
            "supply arrives")


class TestItCostsLessThanTheWholeHistory:
    """The non-functional constraint, measured rather than asserted."""

    def test_finding_the_latest_stops_at_the_first_delivery_carrying_it(
            self, tmp_path, logs):
        for n in range(1, 13):
            _drop(tmp_path, logs, f"drop-{n:02d}", ["cp_clients.csv"],
                   f"2026-01-{n:02d}T09:00:00+08:00", n)

        opened = {"n": 0}
        real = Path.read_text

        def counting(self, *args, **kwargs):
            if self.suffix == ".json" and "delivery_log" in str(self):
                opened["n"] += 1
            return real(self, *args, **kwargs)

        Path.read_text = counting
        try:
            arrival_history.last_arrived("cp-clients", logs)
        finally:
            Path.read_text = real

        assert opened["n"] == 1, (
            f"opened {opened['n']} of 12 records to find the newest arrival of a dataset "
            f"that is in the newest delivery. Built eagerly this was 60 of 60 against the "
            f"real log - the early exit has to be real, not described.")

    def test_it_walks_only_back_to_that_datasets_own_last_supply(self, tmp_path, logs):
        """A dataset that has not supplied recently costs more, and
        that is the right bound: deliveries since IT last supplied,
        never total history."""
        _drop(tmp_path, logs, "old", ["cp_clients.csv"], "2026-01-01T09:00:00+08:00", 1)
        for n in range(2, 8):
            _drop(tmp_path, logs, f"newer-{n}", ["cp_carers.csv"],
                   f"2026-01-{n:02d}T09:00:00+08:00", n)

        opened = {"n": 0}
        real = Path.read_text

        def counting(self, *args, **kwargs):
            if self.suffix == ".json" and "delivery_log" in str(self):
                opened["n"] += 1
            return real(self, *args, **kwargs)

        Path.read_text = counting
        try:
            found = arrival_history.last_arrived("cp-clients", logs)
        finally:
            Path.read_text = real

        assert found.delivery == "old"
        assert opened["n"] == 7, f"walked {opened['n']} records, expected all 7"


class TestAgainstTheRealCommittedHistory:
    """Birth Registrations is the control: one table, one dataset, and
    its committed runs prove this generalises rather than
    special-casing Child Protection.

    Asks for the REAL committed trees by name - conftest redirects them
    for every other test, to stop a run writing into or pruning project
    history.
    """

    def test_birth_registrations_has_its_own_unbroken_timeline(self, real_committed_history):
        found = arrival_history.arrivals_of("birth-registrations")
        assert len(found) == 42, f"{len(found)} arrivals, expected the committed 42"
        assert all(a.dataset_id == "birth-registrations" for a in found)
        assert len({a.supply_id for a in found}) == len(found), "supply ids must be unique"

    def test_each_cp_dataset_has_the_same_count_and_its_own_ids(self, real_committed_history):
        counts = {d: arrival_history.arrivals_of(d)
                   for d in ("cp-clients", "cp-carers", "cp-placements")}
        assert {len(v) for v in counts.values()} == {18}
        ids = [v[0].supply_id for v in counts.values()]
        assert len(set(ids)) == 3, f"three datasets share one identifier: {ids}"
