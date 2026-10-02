"""A supply received by hand is an arrival like any other
(REQ-PIPE-103, criteria 1 and 8).

WHAT THIS IS REALLY CHECKING. Not that a file gets copied somewhere -
that the thing that comes back is a RUN ID RECOGNITION ASSIGNED,
indistinguishable downstream from a delivery that arrived on its own.
Every alternative considered (see qa_tools/common/hand_filing.py's own
docstring) fails exactly there, which is why these assert on the run
id and on the receipt rather than on the directory.
"""
from __future__ import annotations

import pytest

from qa_tools.common import arrivals, asset_time, delivery, hand_filing


@pytest.fixture
def tree(tmp_path):
    """An empty deliveries tree, so a filed supply is arrival number
    one and its run id is predictable without depending on this
    repository's own committed history."""
    return tmp_path / "deliveries", tmp_path / "receipts"


def _csv(tmp_path, name: str, rows: int = 2) -> str:
    path = tmp_path / name
    path.write_text("registration_id,child_family_name\n"
                    + "".join(f"R{i},Smith\n" for i in range(rows)))
    return str(path)


class TestFilingGivesARealArrival:
    def test_a_filed_supply_gets_its_run_id_from_recognition(self, tmp_path, tree):
        deliveries, receipts = tree
        path = _csv(tmp_path, "birth_registrations_2026-09-20.csv")

        filed = hand_filing.file_supply(
            [path], "civil-registration", "run_",
            deliveries_dir=deliveries, receipts_dir=receipts)

        # The staged table's spelling at our receipt instant
        # (REQ-PIPE-105), never a position in a list.
        found = arrivals.arrivals_for("civil-registration", "run_",
                                       deliveries_dir=deliveries, receipts_dir=receipts)
        assert [a.run_id for a in found] == [filed.run_id]
        assert filed.run_id == (
            f"birth_registrations__{asset_time.arrival_key(filed.received_at)}")
        assert found[0].delivery_name == filed.delivery_name

    def test_the_receipt_is_our_clock_and_is_written_outside_the_delivery(
            self, tmp_path, tree):
        """We know when WE received it, never when it was sent - and the
        receipt is ours, so a supplier has no path to write it."""
        deliveries, receipts = tree
        when = asset_time.parse_instant("2099-04-05T06:07:08+08:00", "test")

        filed = hand_filing.file_supply(
            [_csv(tmp_path, "birth_registrations_2099-04-05.csv")],
            "civil-registration", "run_", received_at=when,
            deliveries_dir=deliveries, receipts_dir=receipts)

        assert delivery.read_receipt(filed.delivery_name, receipts_dir=receipts) == when
        assert not list((deliveries / filed.delivery_name).glob("*.json"))

    def test_it_reaches_the_delivery_log_now_not_at_the_next_pipeline_run(
            self, tmp_path, tree, _committed_history_is_off_limits):
        """The observation this requirement started from: "without
        deliveries being logged it would impact what's shown in the
        dashboard, right?" The delivery log is what the dashboard's
        arrival history is built from, and a hand-received supply that
        had to wait for an unrelated command to appear there would be
        the same gap one step smaller."""
        from qa_tools.common import delivery_log

        deliveries, receipts = tree
        filed = hand_filing.file_supply(
            [_csv(tmp_path, "birth_registrations_2026-09-20.csv")],
            "civil-registration", "run_",
            deliveries_dir=deliveries, receipts_dir=receipts)

        logged = [r["delivery"] for r in delivery_log.records()]
        assert filed.delivery_name in logged, logged

    def test_the_file_is_stored_byte_for_byte(self, tmp_path, tree):
        """A delivery holds what the supplier sent. Decoding and
        re-encoding would quietly normalise a BOM or a line ending we
        were meant to notice."""
        deliveries, receipts = tree
        path = tmp_path / "birth_registrations_2026-09-20.csv"
        original = b"\xef\xbb\xbfregistration_id\r\nR1\r\n"
        path.write_bytes(original)

        filed = hand_filing.file_supply(
            [str(path)], "civil-registration", "run_",
            deliveries_dir=deliveries, receipts_dir=receipts)

        assert (deliveries / filed.delivery_name / path.name).read_bytes() == original
        # AND `paths` POINTS AT THAT COPY, not at what the operator
        # typed - the check must read the file the record describes.
        assert filed.paths == (str(deliveries / filed.delivery_name / path.name),)

    def test_a_folder_of_files_is_ONE_delivery(self, tmp_path, tree):
        """They arrived together, and a delivery is the transport unit.
        One delivery per file would invent DELIVERIES that never
        happened - but each file is its own ARRIVAL (REQ-PIPE-105
        criterion 1), and arrivals_of() gives back all of them."""
        deliveries, receipts = tree
        paths = [_csv(tmp_path, n) for n in ("cp_clients.csv", "cp_case_workers.csv")]

        filed = hand_filing.file_supply(
            paths, "child-protection", "cp_run_",
            deliveries_dir=deliveries, receipts_dir=receipts)

        key = asset_time.arrival_key(filed.received_at)
        found = hand_filing.arrivals_of(filed, "child-protection", "cp_run_",
                                        deliveries_dir=deliveries, receipts_dir=receipts)
        assert [a.run_id for a in found] == [f"cp_case_workers__{key}", f"cp_clients__{key}"]
        assert filed.run_id == found[0].run_id
        assert len(list((deliveries / filed.delivery_name).iterdir())) == 2
        assert len(list(deliveries.iterdir())) == 1

    def test_a_filed_supply_sorts_after_everything_already_recorded(self, tmp_path, tree):
        """This requirement's second non-functional constraint - filing
        must never renumber committed history. Run ids stopped being
        positional on 2026-10-02 (REQ-PIPE-105), which makes this hold
        by construction; the test now proves the earlier arrival's id is
        untouched rather than that the new one counted past it."""
        deliveries, receipts = tree
        delivery.write_delivery(
            "already-here", {"birth_registrations_2026-01-01.csv": "registration_id\nR0\n"},
            received_at=asset_time.parse_instant("2026-01-01T00:00:00+08:00", "test"),
            deliveries_dir=deliveries, receipts_dir=receipts)

        before = [a.run_id for a in arrivals.arrivals_for(
            "civil-registration", "run_", deliveries_dir=deliveries, receipts_dir=receipts)]
        filed = hand_filing.file_supply(
            [_csv(tmp_path, "birth_registrations_2026-09-20.csv")],
            "civil-registration", "run_",
            deliveries_dir=deliveries, receipts_dir=receipts)
        after = [a.run_id for a in arrivals.arrivals_for(
            "civil-registration", "run_", deliveries_dir=deliveries, receipts_dir=receipts)]

        assert after == before + [filed.run_id], "filing renumbered an arrival already recorded"


class TestAnUnplaceableFileIsRefused:
    """Keith's own call, 2026-09-27, over renaming the file to fit or
    filing it unplaceable. A run's identity comes from recognising its
    files by name, so a file we cannot place has no run to be."""

    def test_a_name_no_pattern_claims_is_refused(self, tmp_path, tree):
        deliveries, receipts = tree
        with pytest.raises(hand_filing.CannotFile) as exc:
            hand_filing.file_supply(
                [_csv(tmp_path, "Births Jan.csv")], "civil-registration", "run_",
                deliveries_dir=deliveries, receipts_dir=receipts)
        assert "Births Jan.csv" in str(exc.value)
        assert "TRIAL" in str(exc.value), \
            "the refusal must name the way forward, not just the problem"

    def test_nothing_is_written_when_filing_is_refused(self, tmp_path, tree):
        """Before anything is written, not after. A receipt is a claim
        about when we received something - never written speculatively
        and cleaned up afterwards."""
        deliveries, receipts = tree
        with pytest.raises(hand_filing.CannotFile):
            hand_filing.file_supply(
                [_csv(tmp_path, "extract (3).csv")], "civil-registration", "run_",
                deliveries_dir=deliveries, receipts_dir=receipts)
        assert not deliveries.exists() or not list(deliveries.iterdir())
        assert not receipts.exists() or not list(receipts.iterdir())

    def test_one_bad_name_refuses_the_whole_delivery(self, tmp_path, tree):
        """They arrived together, so filing the half we can read would
        record a delivery that is missing a file nobody would know to
        look for."""
        deliveries, receipts = tree
        paths = [_csv(tmp_path, "cp_clients.csv"), _csv(tmp_path, "notes.txt")]
        with pytest.raises(hand_filing.CannotFile) as exc:
            hand_filing.file_supply(paths, "child-protection", "cp_run_",
                                     deliveries_dir=deliveries, receipts_dir=receipts)
        assert "notes.txt" in str(exc.value)
        assert not deliveries.exists() or not list(deliveries.iterdir())


class TestTheDeliveryNameIsOurs:
    def test_two_supplies_of_the_same_filename_do_not_collide(self, tmp_path, tree):
        """Two people checking their own copy of
        `birth_registrations_2026-09-20.csv` is an ordinary Tuesday, and
        write_delivery refuses a directory that already exists."""
        deliveries, receipts = tree
        path = _csv(tmp_path, "birth_registrations_2026-09-20.csv")
        first = hand_filing.file_supply(
            [path], "civil-registration", "run_",
            received_at=asset_time.parse_instant("2099-01-01T01:00:00+08:00", "t"),
            deliveries_dir=deliveries, receipts_dir=receipts)
        second = hand_filing.file_supply(
            [path], "civil-registration", "run_",
            received_at=asset_time.parse_instant("2099-01-01T01:00:01+08:00", "t"),
            deliveries_dir=deliveries, receipts_dir=receipts)
        assert first.delivery_name != second.delivery_name

    def test_it_is_recognisable_in_a_listing_as_hand_filed(self, tmp_path, tree):
        deliveries, receipts = tree
        filed = hand_filing.file_supply(
            [_csv(tmp_path, "birth_registrations_2026-09-20.csv")],
            "civil-registration", "run_",
            deliveries_dir=deliveries, receipts_dir=receipts)
        assert filed.delivery_name.startswith(hand_filing.HAND_FILED_PREFIX)
