"""Arrivals are processed in receipt order, and an interrupted run
loses nothing (REQ-PIPE-061).

The claim under test is an ORDERING and a RESUMPTION rule. The
ordering half is tested by constructing the tie the real data does not
have - all 60 committed receipts carry distinct instants today, so
criterion 3 is latent rather than live and a test over real data would
pass without exercising it at all.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass

import pytest

from qa_tools.common import backlog, delivery, load_log

def _receipt(receipts, name):
    """The one per-file receipt of a one-file delivery (REQ-GEN-044
    criterion 12): receipts are `<receipts>/<delivery>/<file>.json`."""
    (path,) = (receipts / name).glob("*.json")
    return path



@dataclass(frozen=True)
class _Arrival:
    name: str
    received_at: str
    sequence: int


def _a(name, instant, sequence):
    return _Arrival(name=name, received_at=instant, sequence=sequence)


@pytest.fixture
def marker(tmp_path):
    """Retired with the marker itself (REQ-PIPE-089 criterion 18) and
    kept only so the two retirement notes below read as belonging to
    this file rather than arriving from nowhere."""
    return tmp_path / "marker" / "position.json"


class TestReceiptOrderIsTheOnlyOrder:
    """Criteria 1, 2 and 3."""

    def test_deliveries_come_back_oldest_receipt_first(self, tmp_path):
        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        for name, instant in (("zulu", "2026-03-01T09:00:00+08:00"),
                               ("alpha", "2026-01-01T09:00:00+08:00"),
                               ("mike", "2026-02-01T09:00:00+08:00")):
            delivery.write_delivery(name, {"birth_registrations_x.csv": "a\n1\n"},
                                     instant, deliveries, receipts)
        got = [d.name for d in delivery.list_deliveries(deliveries, receipts)]
        assert got == ["alpha", "mike", "zulu"], (
            "ordered by OUR receipt instant, never by the supplier's own naming habits")

    def test_a_tie_breaks_on_receipt_write_order_not_on_name(self, tmp_path):
        """Criterion 3, and the bug it removes.

        `survey()` sorts by instant over a name-sorted directory
        listing, so before this a tie fell to the delivery's NAME -
        which REQ-PIPE-057 criterion 8 separately forbids. Here the
        file written SECOND sorts first by name, so the two rules
        disagree and the test can tell which one ran.
        """
        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        instant = "2026-02-01T09:00:00+08:00"
        for name in ("zulu", "alpha"):
            delivery.write_delivery(name, {"birth_registrations_x.csv": "a\n1\n"},
                                     instant, deliveries, receipts)
        got = [d.name for d in delivery.list_deliveries(deliveries, receipts)]
        assert got == ["zulu", "alpha"], (
            "the tie must break on the order the RECEIPTS were written - 'alpha' first would "
            "mean the order came from the directory listing")

    def test_every_receipt_gets_its_own_sequence(self, tmp_path):
        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        for i in range(5):
            delivery.write_delivery(f"drop-{i}", {"birth_registrations_x.csv": "a\n1\n"},
                                     "2026-02-01T09:00:00+08:00", deliveries, receipts)
        seen = [json.loads(p.read_text())["sequence"] for p in sorted(receipts.rglob("*.json"))]
        assert sorted(seen) == [1, 2, 3, 4, 5], (
            "a sequence must be total - two receipts sharing one puts the order back in the "
            "hands of whatever the sort does")

    def test_a_receipt_without_a_sequence_cannot_be_ordered(self, tmp_path):
        """Not defaulted to zero: that would put every pre-sequence
        receipt in one place and hand the tie back to a listing."""
        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        delivery.write_delivery("drop", {"birth_registrations_x.csv": "a\n1\n"},
                                 "2026-02-01T09:00:00+08:00", deliveries, receipts)
        path = _receipt(receipts, "drop")
        record = json.loads(path.read_text())
        del record["sequence"]
        path.write_text(json.dumps(record))
        with pytest.raises(delivery.ReceiptOrderError, match="sequence"):
            delivery.read_delivery("drop", deliveries, receipts)

    def test_that_refusal_is_not_reported_as_still_in_flight(self, tmp_path):
        """survey() catches DeliveryFormatError and calls it in flight.

        A receipt with no sequence is a COMPLETE arrival we cannot
        order, not an incomplete upload, and reporting it as in flight
        would hide it behind an ordinary operational state.
        """
        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        delivery.write_delivery("drop", {"birth_registrations_x.csv": "a\n1\n"},
                                 "2026-02-01T09:00:00+08:00", deliveries, receipts)
        path = _receipt(receipts, "drop")
        record = json.loads(path.read_text())
        del record["sequence"]
        path.write_text(json.dumps(record))
        with pytest.raises(delivery.ReceiptOrderError):
            delivery.survey(deliveries, receipts)


class TestTheOrderDoesNotDependOnPresentationOrder:
    """Criterion 5."""

    def test_the_same_arrivals_shuffled_produce_the_same_order(self):
        arrivals = [_a("a", "2026-01-01T09:00:00+08:00", 1),
                     _a("b", "2026-01-01T09:00:00+08:00", 2),
                     _a("c", "2026-02-01T09:00:00+08:00", 3),
                     _a("d", "2026-02-01T09:00:00+08:00", 4)]
        expected = [x.name for x in arrivals]
        rng = random.Random(7)
        for _ in range(20):
            shuffled = arrivals[:]
            rng.shuffle(shuffled)
            got = [x.name for x in sorted(shuffled, key=backlog.Position.of)]
            assert got == expected, (
                "everything in this repo is seeded, so regenerate-and-diff is how a refactor is "
                "proven behaviour-preserving - an order-dependent filing makes that meaningless")


class TestDrainingTheBacklog:
    """RETIRED BY REQ-PIPE-089 criterion 18, and kept as a note so the
    properties are findable rather than apparently dropped.

    Seven tests here drove the STORED MARKER: that a run with none was
    owed everything, that it advanced only past what finished, that it
    never moved backwards, that an unreadable one meant start from the
    beginning, and that it could not be mistaken for a load record.
    All five of those last describe a file that no longer exists.

    The two claims that were about PROCESSING rather than about the
    marker live in TestHowFarProcessingGotIsDerived below: everything
    not yet processed is owed, not just the newest arrival, and an
    arrival reached but not finished stays owed.
    """


class TestAnExhaustedScheduleStillAcceptsSupplies:
    """REQ-PIPE-061 criterion 9, which is also REQ-PIPE-053 criterion 7.

    The duplication is deliberate: 053 made the claim and this is the
    mechanism. It is the half of an exhausted schedule that is easy to
    get wrong in the dangerous direction - refusing to RECORD an
    arrival because nothing can file it yet means the backlog cannot
    drain correctly once dates are added, which is the whole promise
    053's hard failure rests on.
    """

    def test_an_arrival_is_recognised_whatever_the_schedule_says(self, tmp_path, monkeypatch):
        from qa_tools.common import arrivals, slots

        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        delivery.write_delivery("drop", {"cp_clients.csv": "a\n1\n"},
                                 "2026-02-01T09:00:00+08:00", deliveries, receipts)

        # Every dataset's schedule exhausted, which is what 053's hard
        # failure looks like from the filing layer's side.
        monkeypatch.setattr(slots, "is_owed_supplies", lambda dataset_id: False)

        found = arrivals.recognise(delivery.read_delivery("drop", deliveries, receipts))
        assert found.by_dataset.get("cp-clients") == ("cp_clients.csv",), (
            "recognition must not consult the schedule - an arrival nothing can FILE yet is "
            "still an arrival, and refusing to record it is how the backlog stops being "
            "drainable once dates are added")

    def test_it_is_still_written_to_the_delivery_log(
            self, tmp_path, monkeypatch, clean_delivery_log):
        from qa_tools.common import arrivals, delivery_log, slots

        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        delivery.write_delivery("drop", {"cp_clients.csv": "a\n1\n"},
                                 "2026-02-01T09:00:00+08:00", deliveries, receipts)
        monkeypatch.setattr(slots, "is_owed_supplies", lambda dataset_id: False)

        d = delivery.read_delivery("drop", deliveries, receipts)
        assert delivery_log.record(
            d, arrivals.recognise(d), conn=clean_delivery_log) is not None
        written = delivery_log.records(clean_delivery_log)
        assert [r["delivery"] for r in written] == ["drop"]
        assert written[0]["files"][0]["dataset_id"] == "cp-clients", (
            "what we thought it was is a RECOGNITION fact and does not depend on whether a slot "
            "exists to put it in")


class TestAPositionCannotBeInventedFromAMissingField:
    """The bug this removes was in the first version of this module,
    and nothing failed while it was there.

    `Position.of()` defaulted a missing `sequence` to zero, and
    `Arrival` did not carry one at all - so every arrival's position had
    sequence 0 and the tiebreak was silently absent at the one layer
    that uses it. A permissive default turned a missing field into a
    wrong answer.
    """

    def test_an_arrival_carries_its_receipts_sequence(self, tmp_path):
        from qa_tools.common import arrivals

        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        for name in ("first", "second"):
            delivery.write_delivery(name, {"cp_clients.csv": "a\n1\n"},
                                     "2026-02-01T09:00:00+08:00", deliveries, receipts)
        found = arrivals.arrivals_for("child-protection", "cp_run_", deliveries, receipts)
        assert [a.sequence for a in found] == [1, 2], (
            "an Arrival without its receipt's sequence cannot be ordered, and defaulting it "
            "gives every arrival the same position")

    def test_a_thing_with_no_sequence_is_refused_rather_than_defaulted(self):
        @dataclass(frozen=True)
        class _NoSequence:
            received_at: str

        with pytest.raises(AttributeError, match="sequence"):
            backlog.Position.of(_NoSequence(received_at="2026-02-01T09:00:00+08:00"))


class TestTheMarkerIsGloballyCorrect:
    """RETIRED BY REQ-PIPE-089 criterion 18, and this one is worth
    reading before anybody reintroduces a high-water mark.

    The bug it guarded: a GLOBAL marker advanced over ONE collection's
    arrivals. Birth Registrations' newest arrival was seven weeks past
    Child Protection's in the real data, so whichever orchestrator ran
    first pushed the shared marker past every outstanding Child
    Protection arrival. Latent only because nothing read the marker
    for control flow.

    It cannot recur, and not because of care. The question is now
    asked of each arrival on its own, so there is no shared position
    for one collection's progress to move on another's behalf. The
    surviving half of the claim - that a delivery spanning collections
    is not processed until BOTH halves have staged - is asserted in
    TestHowFarProcessingGotIsDerived below.
    """


class TestHowFarProcessingGotIsDerived:
    """REQ-PIPE-089 criteria 18-20: the stored marker is DROPPED, and
    the same question is answered by asking the load records.

    KEITH'S CALL, 2026-09-27: "let's ditch it and just derive from load
    records - that's much easier now it's all going to be in a
    database." The reason is sharper than convenience. The marker
    existed to AVOID A SCAN - over a file tree the only way to bound
    replay cost was to store the position - and in a database an
    indexed query over the load outcomes gives the same bound for
    nothing.

    AND DERIVING IS STRICTLY SAFER. A stored marker can disagree with
    the load records, and it fails in the dangerous direction:
    advanced past an arrival that was reached but not finished, it
    turns a crash into a silently skipped supply. There is nothing to
    advance and nothing to disagree.

    Found while removing it, and worth recording: the marker was
    WRITE-ONLY. Both orchestrators called `advance_past_staged()` after
    their fan-out and nothing in the pipeline ever read it back.
    """

    @staticmethod
    def _arrival(name, files):
        from types import SimpleNamespace
        return SimpleNamespace(name=name, files=tuple(files))

    def test_an_arrival_with_every_file_loaded_is_processed(self, clean_load_log):
        for physical in ("cp_clients__1", "cp_carers__1"):
            load_log.record("monday", "cp-clients", physical, load_log.LOADED,
                            "2026-09-01T09:00:00+08:00")
        assert backlog.unprocessed(
            [self._arrival("monday", ["cp_clients__1", "cp_carers__1"])]) == []

    def test_an_arrival_reached_but_not_finished_is_still_owed(self, clean_load_log):
        """Criterion 20, and the whole reason for deriving. A stored
        marker advanced optimistically over this arrival would turn a
        crash into a supply nobody ever looks at again."""
        load_log.record("monday", "cp-clients", "cp_clients__1", load_log.LOADED,
                        "2026-09-01T09:00:00+08:00")
        owed = backlog.unprocessed(
            [self._arrival("monday", ["cp_clients__1", "cp_carers__1"])])
        assert [a.name for a in owed] == ["monday"]

    def test_a_failed_load_leaves_the_arrival_owed(self, clean_load_log):
        load_log.record("monday", "cp-clients", "cp_clients__1", load_log.FAILED,
                        "2026-09-01T09:00:00+08:00", reason="not a CSV")
        owed = backlog.unprocessed([self._arrival("monday", ["cp_clients__1"])])
        assert [a.name for a in owed] == ["monday"]

    def test_an_arrival_that_attributed_nothing_is_not_owed_for_ever(self, clean_load_log):
        """A covering note and nothing else. There is nothing to stage
        and no load record will ever appear, so treating it as owed
        would block the queue permanently on a delivery that can never
        satisfy it."""
        assert backlog.unprocessed([self._arrival("just-a-note", [])]) == []

    def test_a_gap_does_not_hide_the_arrivals_after_it(self, clean_load_log):
        """The one place deriving BEATS the marker rather than matching
        it. A high-water mark had to stop at the first unfinished
        arrival, so one stuck supply made every later one look owed
        again - re-processing three to get past one. Asking each
        arrival its own question has no gap to stop at.
        """
        load_log.record("a", "cp-clients", "a__1", load_log.LOADED,
                        "2026-09-01T09:00:00+08:00")
        load_log.record("c", "cp-clients", "c__1", load_log.LOADED,
                        "2026-09-03T09:00:00+08:00")
        owed = backlog.unprocessed([
            self._arrival("a", ["a__1"]),
            self._arrival("b", ["b__1"]),
            self._arrival("c", ["c__1"])])
        assert [x.name for x in owed] == ["b"]

    def test_everything_not_yet_processed_is_owed_not_just_the_newest(
            self, clean_load_log):
        """Criterion 6, carried over from the retired marker tests. The
        failure it prevents is a platform one: GitHub holds only ONE
        pending run per concurrency group, so three rapid triggers
        silently lose the middle one. Draining needs no queueing
        guarantee from anybody."""
        load_log.record("a", "cp-clients", "a__1", load_log.LOADED,
                        "2026-01-01T09:00:00+08:00")
        owed = backlog.unprocessed([self._arrival(n, [f"{n}__1"])
                                    for n in ("a", "b", "c", "d")])
        assert [x.name for x in owed] == ["b", "c", "d"]

    def test_a_delivery_spanning_collections_waits_for_both_halves(
            self, clean_load_log):
        """The surviving half of the retired global-marker class. One
        delivery, two collections, and half of it staged: not
        processed, because half a delivery is not done."""
        load_log.record("both", "cp-clients", "cp_clients__1", load_log.LOADED,
                        "2026-01-01T09:00:00+08:00")
        owed = backlog.unprocessed(
            [self._arrival("both", ["cp_clients__1", "birth_registrations__1"])])
        assert [x.name for x in owed] == ["both"]

    def test_the_answer_is_stable_across_repeated_asks(self, clean_load_log):
        """The retired marker guaranteed this by being a stored
        high-water mark; a derivation has to be deterministic
        instead."""
        load_log.record("a", "cp-clients", "a__1", load_log.LOADED,
                        "2026-01-01T09:00:00+08:00")
        arrivals = [self._arrival(n, [f"{n}__1"]) for n in ("a", "b", "c")]
        first = [x.name for x in backlog.unprocessed(arrivals)]
        second = [x.name for x in backlog.unprocessed(arrivals)]
        assert first == second == ["b", "c"]

    def test_the_whole_answer_is_one_query(self, clean_load_log, monkeypatch):
        """Criterion 19's cost bound, which the marker existed to give
        and this has to give without it: one indexed read of the load
        outcomes, not one per arrival."""
        from qa_tools.common import load_log as module

        calls = {"n": 0}
        real = module.latest_by_table

        def counting(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        monkeypatch.setattr(module, "latest_by_table", counting)
        backlog.unprocessed([self._arrival(f"d{n}", [f"d{n}__1"]) for n in range(20)])
        assert calls["n"] == 1, (
            f"asked the load log {calls['n']} times for 20 arrivals - the bound has to "
            f"be one read, or the marker was buying something this does not")


class TestTheStoredMarkerIsGone:
    """Criterion 18, asserted rather than assumed: a mechanism removed
    in one place and left in another is worse than either."""

    def test_nothing_reads_or_writes_a_marker(self):
        source = open(backlog.__file__).read()
        for name in ("MARKER_PATH", "read_marker", "advance_through",
                     "advance_past_staged", "processing_log"):
            assert name not in source, f"{name} survived the marker's removal"
