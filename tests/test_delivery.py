"""Tests for qa_tools/common/delivery.py - the on-disk delivery format
(REQ-GEN-043).

The format's whole value is that it asserts ONLY what physically
happened - these files landed together, at this instant - so most of
what matters here is what it REFUSES to believe. A supplier-declared
manifest is what plans/supply-model.md Thread B rejected, and a format
that quietly reads one back is that rejection undone by a back door.

Uses tmp_path throughout, deliberately: this module writes real
directories, and the real data/deliveries/ tree is gitignored build
output that tests must not depend on the state of.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import delivery

PERTH = timezone(timedelta(hours=8))
WHEN = datetime(2026, 8, 24, 14, 36, 3, tzinfo=PERTH)


@pytest.fixture
def dirs(tmp_path):
    """A deliveries directory and a receipts directory that is NOT
    inside it - which is the boundary the whole format rests on."""
    return tmp_path / "deliveries", tmp_path / "receipts"


def _write(dirs, name="BDM_20260824", files=None, when=WHEN):
    d, r = dirs
    return delivery.write_delivery(name, files or {"birth_registrations.csv": "a,b\n1,2\n"},
                                    received_at=when, deliveries_dir=d, receipts_dir=r)


class TestTheBoundaryIsADirectory:
    def test_one_delivery_is_one_directory(self, dirs):
        path = _write(dirs)
        assert path.is_dir()
        assert path.name == "BDM_20260824"

    def test_the_boundary_is_visible_without_opening_any_file(self, dirs):
        """Criterion 1. A real transport gives you one prefix, one
        session, one folder drop - so the boundary has to be legible
        from a listing, not reconstructed from file contents."""
        d, _ = dirs
        _write(dirs, "first")
        _write(dirs, "second", {"cp_clients.csv": "x\n"})
        assert sorted(p.name for p in d.iterdir()) == ["first", "second"]

    def test_several_datasets_arriving_together_are_ONE_delivery(self, dirs):
        """Criterion 11. Child Protection's six tables land as one
        extract; six deliveries would be six arrivals that never
        happened."""
        path = _write(dirs, "dcp-extract-aug", {
            f"cp_{t}.csv": "a\n1\n" for t in
            ("clients", "notifications", "investigations", "placements", "carers", "case_workers")})
        assert len(list(path.iterdir())) == 6
        assert len(delivery.list_deliveries(*dirs)) == 1

    def test_a_delivery_with_no_files_is_refused(self, dirs):
        d, r = dirs
        with pytest.raises(delivery.DeliveryFormatError, match="ARRIVAL"):
            delivery.write_delivery("empty", {}, WHEN, deliveries_dir=d, receipts_dir=r)

    def test_a_delivery_is_flat_not_a_tree(self, dirs):
        d, r = dirs
        with pytest.raises(delivery.DeliveryFormatError, match="path separator"):
            delivery.write_delivery("x", {"sub/a.csv": "1"}, WHEN, deliveries_dir=d, receipts_dir=r)


class TestDeliveryNamesMeanNothing:
    @pytest.mark.parametrize("name", [
        "BDM_20260824", "dcp-extract-aug", "upload_final_v2", "2026Q3",
        "a7f3c1e2-9b4d-4e8a-91cf-3d2b5a6c7e8f", "Aug Extract (final)",
    ])
    def test_any_shape_of_supplier_name_is_accepted(self, dirs, name):
        """Criterion 15, and the reason is a TESTING argument rather
        than a modelling one: if we name the drop ourselves, delivery
        recognition passes by parsing a name we wrote, which proves
        nothing."""
        assert _write(dirs, name).is_dir()

    @pytest.mark.parametrize("bad", [
        "2026-08-24T14:36:03+08:00",   # an ISO instant contains colons
        "a/b", "a\\b", "q?", 'say"what', "pipe|d", "",
    ])
    def test_a_name_that_would_break_a_checkout_is_refused(self, dirs, bad):
        """Arbitrary is not unconstrained. This repo gets run on other
        people's machines as part of evaluating the PoC, and a colon is
        illegal in a path on Windows - which is also one reason the
        receipt instant lives in a file rather than a directory name."""
        with pytest.raises(delivery.DeliveryFormatError):
            _write(dirs, bad)

    def test_deliveries_are_ordered_by_OUR_receipt_not_by_their_name(self, dirs):
        """A name is a supplier's naming habit, so ordering by it would
        be inventing a sequence out of nothing."""
        _write(dirs, "zzz-first", when=datetime(2026, 1, 1, tzinfo=PERTH))
        _write(dirs, "aaa-second", when=datetime(2026, 6, 1, tzinfo=PERTH))
        assert [d.name for d in delivery.list_deliveries(*dirs)] == ["zzz-first", "aaa-second"]


class TestTheReceiptRecordIsOurs:
    def test_it_is_written_outside_the_delivery(self, dirs):
        """Criterion 12/13. The delivery area is the supplier's; the
        receipt area is ours."""
        d, r = dirs
        path = _write(dirs)
        assert (r / "BDM_20260824.json").exists()
        assert not any(p.name.startswith("receipt") for p in path.iterdir())

    def test_it_carries_its_utc_offset(self, dirs):
        d, r = dirs
        _write(dirs)
        record = json.loads((r / "BDM_20260824.json").read_text())
        assert record["received_at"].endswith("+08:00")
        assert delivery.read_receipt("BDM_20260824", r) == WHEN

    def test_a_receipts_directory_inside_the_deliveries_directory_is_refused(self, dirs):
        """The boundary, enforced rather than documented: a receipts
        directory a supplier can write into is not ours."""
        d, _ = dirs
        with pytest.raises(delivery.DeliveryFormatError, match="no path to write"):
            delivery.write_delivery("x", {"a.csv": "1"}, WHEN,
                                     deliveries_dir=d, receipts_dir=d / "receipts")

    def test_a_missing_receipt_is_an_error_not_a_fallback_to_mtime(self, dirs):
        """An arrival we have no record of receiving is a gap to notice.
        Falling back to a file's modification time would hide exactly
        the thing worth seeing - and would also collapse a whole
        generated history onto the seconds it was written in."""
        d, r = dirs
        _write(dirs)
        (r / "BDM_20260824.json").unlink()
        with pytest.raises(delivery.DeliveryFormatError, match="modification time"):
            delivery.read_delivery("BDM_20260824", d, r)


class TestNothingInsideADeliveryIsBelieved:
    def test_a_receipt_lookalike_inside_a_delivery_is_ignored_and_reported(self, dirs):
        """Criterion 14, and the sharpest one. The moment the receipt
        time lives in a file rather than somewhere only we control, a
        supplier writing a file of that name is setting OUR clock."""
        d, r = dirs
        _write(dirs, files={"birth_registrations.csv": "a\n1\n",
                             "receipt.json": '{"received_at": "1999-01-01T00:00:00+00:00"}'})
        got = delivery.read_delivery("BDM_20260824", d, r)
        assert got.received_at == WHEN, "the supplier's file must not have set our clock"
        assert "receipt.json" not in got.files, "it must not even be readable as a data file"
        assert any("setting our own clock" in a for a in got.anomalies)

    @pytest.mark.parametrize("name", [
        "receipt.json", "_receipt.json", "received_at.json", "RECEIPT.YAML",
        "arrival.json", "transport_record.json",
    ])
    def test_a_lookalike_is_matched_loosely_because_nobody_would_use_our_exact_name(self, dirs, name):
        d, r = dirs
        _write(dirs, files={"birth_registrations.csv": "a\n1\n", name: "{}"})
        got = delivery.read_delivery("BDM_20260824", d, r)
        assert name not in got.files
        assert got.anomalies

    def test_a_supplier_declared_manifest_is_ignored_and_reported(self, dirs):
        """Criterion 4. A supplier saying which period their data is for
        is a judgment we would have to trust and cannot enforce across a
        varied supplier base - which is what Thread B rejected."""
        d, r = dirs
        _write(dirs, files={"birth_registrations.csv": "a\n1\n",
                             "manifest.json": '{"period": "2026-Q3", "slot": "slot_009"}'})
        got = delivery.read_delivery("BDM_20260824", d, r)
        assert "manifest.json" not in got.files
        assert any("what this delivery is for" in a for a in got.anomalies)

    def test_an_ignored_artefact_is_excluded_from_files_not_merely_flagged(self, dirs):
        """Excluded rather than flagged on purpose: a caller iterating
        `files` cannot then read one by accident, which a flag beside
        the list would not prevent."""
        d, r = dirs
        _write(dirs, files={"real.csv": "a\n1\n", "manifest.json": "{}", "receipt.json": "{}"})
        got = delivery.read_delivery("BDM_20260824", d, r)
        assert got.files == ("real.csv",)
        assert len(got.anomalies) == 2

    def test_a_clean_delivery_reports_no_anomalies(self, dirs):
        """The other direction, so the checks above cannot pass by
        flagging everything."""
        d, r = dirs
        _write(dirs, files={"birth_registrations.csv": "a\n1\n", "readme.txt": "notes"})
        got = delivery.read_delivery("BDM_20260824", d, r)
        assert got.anomalies == ()
        assert got.files == ("birth_registrations.csv", "readme.txt")


class TestTheAwkwardDeliveriesRecognitionMustHandle:
    """Criteria 8, 9 and 10 - things real suppliers really do, which
    delivery recognition has to be tested against rather than assumed
    away."""

    def test_two_files_matching_one_datasets_pattern(self, dirs):
        d, r = dirs
        _write(dirs, files={"cp_clients.csv": "a\n1\n", "cp_clients_part2.csv": "a\n2\n"})
        assert len(delivery.read_delivery("BDM_20260824", d, r).files) == 2

    def test_a_file_matching_no_pattern_including_one_that_is_not_tabular(self, dirs):
        d, r = dirs
        _write(dirs, files={"birth_registrations.csv": "a\n1\n",
                             "covering_note.pdf": b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"})
        got = delivery.read_delivery("BDM_20260824", d, r)
        assert "covering_note.pdf" in got.files, "reported, not swallowed"
        assert got.anomalies == (), "a covering note is normal, not anomalous"

    def test_a_file_that_cannot_be_parsed_as_the_format_its_name_claims(self, dirs):
        d, r = dirs
        _write(dirs, files={"birth_registrations.csv": "<html><body>504 Gateway Timeout</body></html>"})
        got = delivery.read_delivery("BDM_20260824", d, r)
        assert got.files == ("birth_registrations.csv",)
        assert (got.path / "birth_registrations.csv").read_text().startswith("<html>")

    def test_binary_content_round_trips_unchanged(self, dirs):
        d, r = dirs
        blob = bytes(range(256))
        _write(dirs, files={"extract.parquet": blob})
        assert (delivery.read_delivery("BDM_20260824", d, r).path / "extract.parquet").read_bytes() == blob


class TestTwoArrivalsCanNeverShareADirectory:
    """A real bug, found by counting rather than by reading
    (2026-09-23). The two generators each kept their own set of taken
    names and wrote into one shared directory, so a Birth Registrations
    drop and a Child Protection drop both landed as
    `2026-08-corrected`: 60 arrivals became 59 directories and two
    unrelated deliveries were silently merged.

    Silent is the word that matters. Nothing failed, no count was
    checked, and the merged directory looked like an ordinary delivery
    holding seven files.
    """

    def test_writing_over_an_existing_delivery_is_refused(self, dirs):
        _write(dirs, "2026-08-corrected")
        with pytest.raises(delivery.DeliveryFormatError, match="silently merge"):
            _write(dirs, "2026-08-corrected", {"cp_clients.csv": "a\n1\n"})

    def test_the_refusal_leaves_the_first_delivery_untouched(self, dirs):
        d, r = dirs
        _write(dirs, "shared", {"birth_registrations.csv": "first\n"})
        with pytest.raises(delivery.DeliveryFormatError):
            _write(dirs, "shared", {"cp_clients.csv": "second\n"})
        got = delivery.read_delivery("shared", d, r)
        assert got.files == ("birth_registrations.csv",)

    def test_existing_names_are_readable_so_a_writer_can_avoid_them(self, dirs):
        """The fix itself: uniqueness is global to the directory, not
        to whatever produced it, so a second writer has to be able to
        see what a first one already wrote."""
        d, _ = dirs
        assert delivery.existing_delivery_names(d) == set()
        _write(dirs, "one")
        _write(dirs, "two", {"cp_clients.csv": "a\n"})
        assert delivery.existing_delivery_names(d) == {"one", "two"}
