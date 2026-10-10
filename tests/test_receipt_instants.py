"""Every file its own receipt instant (REQ-GEN-044 criteria 12-14).

Keith, 2026-10-02: about 80% of multi-file deliveries land at one instant,
as if unzipped together; the rest trickle in, every file within 10
minutes of the first, in a varied order; one receipt per FILE; and all of
it deterministic from the seed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from generator import receipt_instants as ri
from qa_tools.common import arrivals, delivery

FIRST = datetime(2026, 2, 1, 1, tzinfo=timezone.utc)
SIX = [f"{t}.csv" for t in ("cp_carers", "cp_case_workers", "cp_clients",
                              "cp_investigations", "cp_notifications", "cp_placements")]


def _many(n=500):
    return [ri.instants_for(SIX, FIRST, f"delivery-{i}") for i in range(n)]


class TestTheMix:
    def test_about_eighty_percent_land_together(self):
        together = sum(1 for got in _many() if isinstance(got, datetime))
        assert 0.74 <= together / 500 <= 0.86, together

    def test_a_trickle_stays_inside_ten_minutes_of_its_first_file(self):
        for got in _many():
            if isinstance(got, dict):
                assert min(got.values()) == FIRST
                assert max(got.values()) - FIRST <= timedelta(minutes=10)
                assert len(set(got.values())) == len(SIX), "trickled files never share an instant"
                assert set(got) == set(SIX)

    def test_the_order_datasets_arrive_in_varies(self):
        """Criterion 14 - not the same dataset first every time."""
        firsts = {min(got, key=got.get) for got in _many() if isinstance(got, dict)}
        assert len(firsts) > 3, firsts

    def test_it_is_deterministic_from_the_seed(self):
        assert _many(50) == _many(50)

    def test_a_one_file_delivery_has_nothing_to_spread(self):
        assert all(ri.instants_for(["x.csv"], FIRST, f"d{i}") == FIRST for i in range(50))


class TestOneReceiptPerFile:
    @pytest.fixture
    def dirs(self, tmp_path):
        return tmp_path / "deliveries", tmp_path / "receipts"

    def test_each_file_gets_its_own_receipt_and_its_own_arrival(self, dirs):
        deliveries, receipts = dirs
        when = {"cp_clients.csv": FIRST + timedelta(minutes=7),
                "cp_carers.csv": FIRST}
        delivery.write_delivery("trickle", {f: "a\n1\n" for f in when},
                                 received_at=when, deliveries_dir=deliveries,
                                 receipts_dir=receipts)

        assert sorted(p.name for p in (receipts / "trickle").iterdir()) == [
            "cp_carers.csv.json", "cp_clients.csv.json"]
        d = delivery.read_delivery("trickle", deliveries, receipts)
        assert d.received_at == FIRST, "a delivery arrived when its FIRST file did"
        found = arrivals.arrivals_for("child-protection", "cp_run_", deliveries, receipts)
        assert [(a.run_id, a.received_at) for a in found] == [
            ("cp_carers__202602010100000000", FIRST),
            ("cp_clients__202602010107000000", FIRST + timedelta(minutes=7))]
        assert found[0].sequence < found[1].sequence

    def test_one_instant_for_all_is_the_archive_case(self, dirs):
        deliveries, receipts = dirs
        delivery.write_delivery("zip", {f: "a\n1\n" for f in SIX[:2]}, received_at=FIRST,
                                 deliveries_dir=deliveries, receipts_dir=receipts)
        found = arrivals.arrivals_for("child-protection", "cp_run_", deliveries, receipts)
        assert {a.received_at for a in found} == {FIRST}
        assert len({a.sequence for a in found}) == 2, "the sequence still orders a shared instant"

    def test_a_file_with_no_instant_is_refused(self, dirs):
        deliveries, receipts = dirs
        with pytest.raises(delivery.DeliveryFormatError, match="no receipt instant"):
            delivery.write_delivery("half", {"a.csv": "x", "b.csv": "y"},
                                     received_at={"a.csv": FIRST},
                                     deliveries_dir=deliveries, receipts_dir=receipts)

    def test_an_old_one_per_delivery_receipt_says_to_regenerate(self, dirs):
        deliveries, receipts = dirs
        (deliveries / "old").mkdir(parents=True)
        (deliveries / "old" / "cp_clients.csv").write_text("a\n1\n")
        receipts.mkdir(parents=True)
        (receipts / "old.json").write_text('{"received_at": "2026-02-01T01:00:00+00:00", "sequence": 1}')
        with pytest.raises(delivery.ReceiptOrderError, match="regenerate"):
            delivery.read_delivery("old", deliveries, receipts)
