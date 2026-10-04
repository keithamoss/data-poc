"""A filing always links to a real delivery record (REQ-PIPE-144 criteria
10, 11, 18 and 33) - the refusals, a hand-filed supply's link, and a trial
writing no filing at all. Added after the delivery-critic found these
untested (overnight sprint 4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import filing, supply_db
from qa_tools.common.assignment import Assignment

PERTH = timezone(timedelta(hours=8))


def _assignment(supply="cp-clients@x"):
    return Assignment(dataset_id="cp-clients", supply_id=supply, slot="2026-Q1",
                      branch="open-slot-unfilled", considered=("2026-Q1",),
                      received_at=datetime(2026, 2, 1, 9, tzinfo=PERTH))


class TestAFilingWithNoDeliveryIsRefused:

    @pytest.mark.parametrize("delivery", [None, ""])
    def test_no_delivery_at_all(self, private_supply_dsn, delivery):
        with pytest.raises(filing.FilingWithoutDelivery, match="no delivery to link"):
            filing.record(_assignment(), delivery)
        assert filing.filing_for("cp-clients", "cp-clients@x") is None

    def test_a_delivery_with_no_record(self, private_supply_dsn):
        with pytest.raises(filing.FilingWithoutDelivery, match="'ghost-delivery'"):
            filing.record(_assignment(), "ghost-delivery")
        assert filing.filing_for("cp-clients", "cp-clients@x") is None

    def test_the_database_refuses_it_too(self, private_supply_dsn):
        """The foreign key is the safety net behind the refusal."""
        import psycopg
        from qa_tools.common import qa_store

        with supply_db.connect(label="test-link") as conn:
            qa_store.ensure_schema(conn)
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                conn.execute(f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, branch, delivery) "
                             "VALUES ('cp-clients', 'cp-clients@y', 'open-slot-unfilled', 'nope')")


class TestAKeptSupplyLinksToItsDelivery:

    def test_a_hand_filed_supplys_filing_names_its_delivery(self, tmp_path, private_supply_dsn):
        from qa_tools.common import arrivals, hand_filing, schedule

        day = schedule.calendar("daily").current.effective_from + timedelta(days=3)
        path = tmp_path / f"birth_registrations_{day.isoformat()}.csv"
        path.write_text("a\n1\n")
        deliveries, receipts = tmp_path / "d", tmp_path / "r"
        filed = hand_filing.file_supply(
            [path], "civil-registration", "run_", stated_original={"*": "not-known"},
            route="file", filed_by="a@b.c", deliveries_dir=deliveries, receipts_dir=receipts)
        found = [a for a in arrivals.arrivals_for("civil-registration", "run_",
                                                  deliveries, receipts)
                 if a.delivery_name == filed.delivery_name]
        (written,) = filing.file_arrivals(found)
        assert filing.filing_for(written.dataset_id, written.supply_id)["delivery"] \
            == filed.delivery_name


class TestATrialWritesNoFiling:

    def test_a_trial_files_nothing(self, tmp_path, private_supply_dsn, monkeypatch):
        """Criterion 33: a trial never reaches filing, so no delivery
        record and no filing is written for it."""
        from cli import common
        from qa_tools.common import delivery, delivery_log

        monkeypatch.setattr(delivery, "DELIVERIES_DIR", tmp_path / "deliveries")
        path = tmp_path / "anything.csv"
        path.write_text("a\n1\n")
        filed = common.file_or_trial([str(path)], "civil-registration", "run_",
                                     keep=False, route="file")
        assert filed.delivery_name == "" and filed.received_at is None
        from qa_tools.common import qa_store

        with supply_db.connect(label="test-trial") as conn:
            # The trial wrote so little there was not even a schema; make
            # one so the absence can be asked about.
            qa_store.ensure_schema(conn)
            assert delivery_log.records(conn) == []
            assert conn.execute(f"SELECT count(*) FROM {filing.TABLE}").fetchall()[0][0] == 0
