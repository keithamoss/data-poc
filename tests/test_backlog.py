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

from qa_tools.common import backlog, delivery


@dataclass(frozen=True)
class _Arrival:
    name: str
    received_at: str
    sequence: int


def _a(name, instant, sequence):
    return _Arrival(name=name, received_at=instant, sequence=sequence)


@pytest.fixture
def marker(tmp_path):
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
        seen = [json.loads(p.read_text())["sequence"] for p in sorted(receipts.glob("*.json"))]
        assert sorted(seen) == [1, 2, 3, 4, 5], (
            "a sequence must be total - two receipts sharing one puts the order back in the "
            "hands of whatever the sort does")

    def test_a_receipt_without_a_sequence_cannot_be_ordered(self, tmp_path):
        """Not defaulted to zero: that would put every pre-sequence
        receipt in one place and hand the tie back to a listing."""
        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        delivery.write_delivery("drop", {"birth_registrations_x.csv": "a\n1\n"},
                                 "2026-02-01T09:00:00+08:00", deliveries, receipts)
        path = receipts / "drop.json"
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
        path = receipts / "drop.json"
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
    """Criteria 6, 7 and 8."""

    def test_a_run_with_no_marker_is_owed_everything(self, marker):
        arrivals = [_a("a", "2026-01-01T09:00:00+08:00", 1),
                     _a("b", "2026-02-01T09:00:00+08:00", 2)]
        assert backlog.read_marker(marker) is None
        assert backlog.pending(arrivals, None) == arrivals

    def test_it_processes_everything_since_the_marker_not_just_the_newest(self, marker):
        """The failure this prevents is a platform one: GitHub holds
        only ONE pending run per concurrency group, so three rapid
        triggers silently lose the middle one."""
        arrivals = [_a(n, f"2026-0{i}-01T09:00:00+08:00", i)
                     for i, n in enumerate(["a", "b", "c", "d"], start=1)]
        backlog.advance(backlog.Position.of(arrivals[0]), marker)
        owed = backlog.pending(arrivals, backlog.read_marker(marker))
        assert [x.name for x in owed] == ["b", "c", "d"]

    def test_the_marker_advances_only_past_what_finished(self, marker):
        arrivals = [_a(n, f"2026-0{i}-01T09:00:00+08:00", i)
                     for i, n in enumerate(["a", "b", "c"], start=1)]
        # A run that finishes 'a', reaches 'b' and dies.
        backlog.advance(backlog.Position.of(arrivals[0]), marker)
        owed = backlog.pending(arrivals, backlog.read_marker(marker))
        assert [x.name for x in owed] == ["b", "c"], (
            "an optimistically-advanced marker turns a crash into a silently skipped supply")

    def test_the_next_run_resumes_in_the_same_order(self, marker):
        arrivals = [_a(n, f"2026-0{i}-01T09:00:00+08:00", i)
                     for i, n in enumerate(["a", "b", "c", "d"], start=1)]
        for entry in arrivals[:2]:
            backlog.advance(backlog.Position.of(entry), marker)
        first = [x.name for x in backlog.pending(arrivals, backlog.read_marker(marker))]
        second = [x.name for x in backlog.pending(arrivals, backlog.read_marker(marker))]
        assert first == second == ["c", "d"]

    def test_the_marker_never_moves_backwards(self, marker):
        late = _a("late", "2026-01-01T09:00:00+08:00", 1)
        newer = _a("newer", "2026-06-01T09:00:00+08:00", 9)
        backlog.advance(backlog.Position.of(newer), marker)
        backlog.advance(backlog.Position.of(late), marker)
        assert backlog.read_marker(marker) == backlog.Position.of(newer), (
            "re-processing an older arrival is legitimate; undoing the high-water mark is not")

    def test_an_unreadable_marker_means_start_from_the_beginning(self, marker):
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("{not json")
        assert backlog.read_marker(marker) is None, (
            "re-processing something already done is idempotent; skipping something never done "
            "is a lost supply")

    def test_the_marker_is_not_read_as_a_load_record(self, tmp_path):
        """It lives inside the processing log's tree, and load_log's
        own glob must not pick it up."""
        from qa_tools.common import load_log

        log_dir = tmp_path / "processing_log"
        log_dir.mkdir()
        load_log.record("d1", "cp-clients", "cp_clients__2026", load_log.LOADED,
                         "2026-09-25T09:00:00+08:00", log_dir=log_dir)
        backlog.advance(backlog.Position("2026-09-25T09:00:00+08:00", 1),
                         log_dir / "marker" / "position.json")
        assert [r.physical for r in load_log.records(log_dir)] == ["cp_clients__2026"]


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

    def test_it_is_still_written_to_the_committed_delivery_log(self, tmp_path, monkeypatch):
        from qa_tools.common import arrivals, delivery_log, slots

        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        delivery.write_delivery("drop", {"cp_clients.csv": "a\n1\n"},
                                 "2026-02-01T09:00:00+08:00", deliveries, receipts)
        monkeypatch.setattr(slots, "is_owed_supplies", lambda dataset_id: False)

        d = delivery.read_delivery("drop", deliveries, receipts)
        log_dir = tmp_path / "delivery_log"
        assert delivery_log.record(d, arrivals.recognise(d), log_dir) is not None
        written = delivery_log.records(log_dir)
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
    """The bug: a global marker advanced over ONE collection's arrivals.

    Birth Registrations' newest arrival is seven weeks past Child
    Protection's in the real data, so whichever orchestrator ran first
    pushed the shared marker past every outstanding Child Protection
    arrival. Latent only because nothing reads the marker for control
    flow yet - and a committed record making an untrue claim is worse
    than a slow one.
    """

    def test_it_stops_at_the_first_delivery_that_is_not_staged(self, tmp_path):
        processed = {"first", "second"}
        deliveries = [_a("first", "2026-01-01T09:00:00+08:00", 1),
                       _a("second", "2026-02-01T09:00:00+08:00", 2),
                       _a("third", "2026-03-01T09:00:00+08:00", 3),
                       _a("fourth", "2026-04-01T09:00:00+08:00", 4)]
        marker = tmp_path / "position.json"
        backlog.advance_through(deliveries, lambda d: d.name in processed, marker)
        assert backlog.read_marker(marker) == backlog.Position.of(deliveries[1])

    def test_it_does_not_jump_a_gap(self, tmp_path):
        """A marker claims EVERYTHING before it is finished, so it
        cannot skip one that is not - the second of four failing means
        the next run is owed all three again."""
        deliveries = [_a(n, f"2026-0{i}-01T09:00:00+08:00", i)
                       for i, n in enumerate(["a", "b", "c", "d"], start=1)]
        marker = tmp_path / "position.json"
        backlog.advance_through(deliveries, lambda d: d.name != "b", marker)
        assert backlog.read_marker(marker) == backlog.Position.of(deliveries[0])
        owed = backlog.pending(deliveries, backlog.read_marker(marker))
        assert [x.name for x in owed] == ["b", "c", "d"]

    def test_advance_past_staged_reads_the_global_list_not_one_collection(self):
        """Asserted on the source, because the failure is a wrong
        committed value rather than an exception: this must take no
        per-collection arrival list at all."""
        import inspect

        signature = inspect.signature(backlog.advance_past_staged)
        assert list(signature.parameters) == ["path"], (
            "taking a collection's own arrivals is what skipped the other collection's - "
            "the input has to be the global delivery list")
        assert "survey()" in inspect.getsource(backlog.advance_past_staged)
