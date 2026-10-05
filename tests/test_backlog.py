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
    """REQ-PIPE-089 criteria 18-20: the stored marker is DROPPED, and the
    same question is answered by asking what was recorded.

    KEITH'S CALL, 2026-09-27: "let's ditch it and just derive from load
    records - that's much easier now it's all going to be in a
    database." Deriving is strictly safer: a stored marker advanced past
    an arrival that was reached but not finished turns a crash into a
    silently skipped supply. There is nothing to advance here.

    ASKED OF THE PROCESSING PASS since 2026-10-06 (Keith, post-build-review
    #120 Q5). REQ-PIPE-151 criterion 18 had made backlog.unprocessed() read
    the pass's own definition - checked AND gated, or held - after which it
    had no caller and was a second door into the same rule, so it was
    deleted. These are its tests, asked of processing_pass.unprocessed().
    Two of the old ones did not survive the move, because the thing they
    pinned no longer exists to go wrong: an arrival is now ONE dataset's
    file (arrivals.arrivals_for), so there is no "covering note and
    nothing else" arrival and no arrival spanning two collections.
    """

    WHEN = __import__("datetime").datetime(2099, 1, 1,
                                           tzinfo=__import__("datetime").timezone.utc)

    @classmethod
    def _arrival(cls, n, dataset="cp-clients", table="cp_clients"):
        from datetime import timedelta
        from types import SimpleNamespace

        return SimpleNamespace(run_id=f"{table}__{n}", received_at=cls.WHEN + timedelta(hours=n),
                               files_by_dataset={dataset: (f"{table}.csv",)})

    @staticmethod
    def _done(monkeypatch, *arrivals, gated=True, held=False, checked=True):
        from qa_tools.common import processing_pass

        rec = processing_pass.Recorded()
        for a in arrivals:
            if checked:
                rec.completed_runs.add(a.run_id)
            if gated:
                rec.gated.add(processing_pass.supply_of(a))
            if held:
                rec.held.add(processing_pass.supply_of(a))
        calls = {"n": 0}

        def recorded(conn):
            calls["n"] += 1
            return rec
        monkeypatch.setattr(processing_pass, "recorded", recorded)
        return calls

    @staticmethod
    def _owed(arrivals):
        from qa_tools.common import processing_pass

        return [a.run_id for a in processing_pass.unprocessed(arrivals, conn=object())]

    def test_an_arrival_checked_and_gated_is_processed(self, monkeypatch):
        a = self._arrival(1)
        self._done(monkeypatch, a)
        assert self._owed([a]) == []

    def test_a_held_supply_counts_as_gated(self, monkeypatch):
        a = self._arrival(1)
        self._done(monkeypatch, a, gated=False, held=True)
        assert self._owed([a]) == []

    def test_checked_but_not_gated_is_still_owed(self, monkeypatch):
        a = self._arrival(1)
        self._done(monkeypatch, a, gated=False)
        assert self._owed([a]) == [a.run_id]

    def test_gated_but_never_checked_is_still_owed(self, monkeypatch):
        """Criterion 20: a run that never completed is owed, whatever else
        was recorded about its supply - the crash a marker would skip."""
        a = self._arrival(1)
        self._done(monkeypatch, a, checked=False)
        assert self._owed([a]) == [a.run_id]

    def test_a_gap_does_not_hide_the_arrivals_after_it(self, monkeypatch):
        one, two, three = (self._arrival(n) for n in (1, 2, 3))
        self._done(monkeypatch, one, three)
        assert self._owed([one, two, three]) == [two.run_id]

    def test_everything_not_yet_processed_is_owed_not_just_the_newest(self, monkeypatch):
        """Criterion 6: GitHub holds only ONE pending run per concurrency
        group, so three rapid triggers silently lose the middle one."""
        found = [self._arrival(n) for n in (1, 2, 3, 4)]
        self._done(monkeypatch, found[0])
        assert self._owed(found) == [a.run_id for a in found[1:]]

    def test_the_answer_is_stable_across_repeated_asks(self, monkeypatch):
        found = [self._arrival(n) for n in (1, 2, 3)]
        self._done(monkeypatch, found[0])
        assert self._owed(found) == self._owed(found) == [a.run_id for a in found[1:]]

    def test_the_whole_answer_is_one_read(self, monkeypatch):
        """Criterion 19's cost bound: one read, not one per arrival."""
        calls = self._done(monkeypatch)
        self._owed([self._arrival(n) for n in range(20)])
        assert calls["n"] == 1

    def test_backlog_no_longer_answers_it(self):
        """Keith, 2026-10-06: one definition of processed, not two."""
        assert not hasattr(backlog, "unprocessed")


class TestTheStoredMarkerIsGone:
    """Criterion 18, asserted rather than assumed: a mechanism removed
    in one place and left in another is worse than either."""

    def test_nothing_reads_or_writes_a_marker(self):
        source = open(backlog.__file__).read()
        for name in ("MARKER_PATH", "read_marker", "advance_through",
                     "advance_past_staged", "processing_log"):
            assert name not in source, f"{name} survived the marker's removal"
