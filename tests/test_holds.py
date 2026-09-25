"""qa_tools/common/holds.py - two files for one dataset are held, never
chosen between (REQ-PIPE-059).

Every rule for picking one is a guess dressed as a policy, and each
fails silently: take the newest and you drop the one a supplier will
later say they sent; take the largest and you drop a correction; take
the lexically last and you have picked by alphabet. Merging is worse -
a supply is one table VERSION, and concatenating two manufactures a
supply that never arrived.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import duckdb
import pytest

from qa_tools.common import arrivals, delivery, delivery_log, holds, supply_db

WHEN = datetime(2026, 8, 25, 6, 0, tzinfo=timezone(timedelta(hours=8)))


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
    deliveries.mkdir(); receipts.mkdir()
    monkeypatch.setattr(delivery, "DELIVERIES_DIR", deliveries)
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", receipts)
    return deliveries, receipts


def _drop(dirs, name, files, when=WHEN):
    deliveries, receipts = dirs
    folder = deliveries / name
    folder.mkdir()
    for filename, body in files.items():
        (folder / filename).write_text(body)
    (receipts / f"{name}.json").write_text(
        json.dumps({"received_at": when.isoformat()}))
    return folder


def _recognise(dirs, name):
    [d] = [x for x in delivery.list_deliveries(*dirs) if x.name == name]
    with pytest.warns(UserWarning):
        return d, arrivals.recognise(d)


class TestItRefusesToChoose:
    def test_two_files_for_one_dataset_are_held(self, dirs):
        _drop(dirs, "split", {"cp_clients.csv": "a\n1\n",
                               "cp_clients_2.csv": "a\n2\n"})
        # The second name must also match the pattern for this to be a
        # hold rather than an unrecognised artefact - so use a dataset
        # whose real pattern admits both.
        _d, found = _recognise(dirs, "split")
        assert "cp_clients_2.csv" in found.unmatched, (
            "cp_clients's real pattern matches exactly one filename, which is "
            "what makes this shape currently unreachable for Child Protection")

    def test_a_dataset_matching_two_files_is_held(self, dirs):
        """Birth Registrations' pattern carries a placeholder, so two
        dated extracts in one delivery is reachable for real."""
        _drop(dirs, "catch-up", {"birth_registrations_2026-08-01.csv": "a\n1\n",
                                  "birth_registrations_2026-08-02.csv": "a\n2\n"})
        _d, found = _recognise(dirs, "catch-up")
        [hold] = holds.holds_in(found)
        assert hold.dataset_id == "birth-registrations"
        assert hold.files == ("birth_registrations_2026-08-01.csv",
                               "birth_registrations_2026-08-02.csv")

    def test_the_arrival_says_which_datasets_are_held(self, dirs):
        _drop(dirs, "catch-up", {"birth_registrations_2026-08-01.csv": "a\n1\n",
                                  "birth_registrations_2026-08-02.csv": "a\n2\n"})
        with pytest.warns(UserWarning):
            [arrival] = arrivals.arrivals_for("civil-registration", "run_", *dirs)
        assert arrival.held == frozenset({"birth-registrations"})

    def test_path_for_still_refuses_rather_than_guessing(self, dirs):
        """The refusal was always right; what was wrong is that it
        arrived as an exception and took the run with it."""
        _drop(dirs, "catch-up", {"birth_registrations_2026-08-01.csv": "a\n1\n",
                                  "birth_registrations_2026-08-02.csv": "a\n2\n"})
        with pytest.warns(UserWarning):
            [arrival] = arrivals.arrivals_for("civil-registration", "run_", *dirs)
        with pytest.raises(delivery.DeliveryFormatError, match="silently drop"):
            arrival.path_for("birth-registrations")


class TestOneHoldDoesNotStopTheRest:
    """Criterion 2, and it is the difference between a handled state
    and an exception."""

    def test_every_other_dataset_in_the_delivery_is_still_attributed(self, dirs):
        _drop(dirs, "mixed", {"cp_clients.csv": "a\n1\n",
                               "cp_carers.csv": "a\n1\n",
                               "cp_carers_extra.csv": "a\n2\n"})
        _d, found = _recognise(dirs, "mixed")
        assert found.by_dataset["cp-clients"] == ("cp_clients.csv",)

    def test_a_held_delivery_does_not_stop_a_healthy_one(self, dirs):
        _drop(dirs, "healthy", {"birth_registrations_2026-08-01.csv": "a\n1\n"})
        _drop(dirs, "held", {"birth_registrations_2026-09-01.csv": "a\n1\n",
                              "birth_registrations_2026-09-02.csv": "a\n2\n"},
              when=WHEN + timedelta(days=1))
        with pytest.warns(UserWarning):
            found = arrivals.arrivals_for("civil-registration", "run_", *dirs)
        assert [a.delivery_name for a in found] == ["healthy", "held"]
        assert found[0].held == frozenset()


class TestBothFilesAreStagedAndNeitherIsReadable:
    """Keith, 2026-09-24: a held supply IS LOADED into staging and is
    NOT QA'd. Both halves load so the material to resolve the hold with
    is there; no view resolves the logical name, so nothing can read
    it - which enforces "not QA'd" by the mechanism rather than by
    remembering."""

    def test_two_files_stage_as_two_physical_tables(self):
        assert supply_db.staged_table("t", "r", "a.csv") \
            != supply_db.staged_table("t", "r", "b.csv")

    def test_neither_resolves_to_the_logical_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv(supply_db.SUPPLY_DB_ENV, str(tmp_path / "s.duckdb"))
        conn = supply_db.connect()
        supply_db.ensure_schemas(conn)
        for filename in ("a.csv", "b.csv"):
            physical = supply_db.staged_table("birth_registrations", "run_001", filename)
            conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" '
                          "AS SELECT 1 AS id")
        res = supply_db.create_run_views(conn, "run_001", supply_db.candidates_in(
            conn, supply_db.STAGING_SCHEMA, ["birth_registrations"], run_id="run_001"))
        assert res.resolved == {}
        assert len(res.ambiguous["birth_registrations"]) == 2
        with pytest.raises(duckdb.CatalogException):
            conn.execute(f'SELECT * FROM "{res.schema}"."birth_registrations"')
        conn.close()

    def test_staging_the_second_file_does_not_overwrite_the_first(self, tmp_path, monkeypatch):
        """The failure the hold exists to prevent, reintroduced one
        layer down: one physical name for both files loses one of them
        and the hold has nothing left to resolve WITH."""
        monkeypatch.setenv(supply_db.SUPPLY_DB_ENV, str(tmp_path / "s.duckdb"))
        conn = supply_db.connect()
        supply_db.ensure_schemas(conn)
        for filename, rows in (("a.csv", 1), ("b.csv", 7)):
            physical = supply_db.staged_table("t", "run_001", filename)
            conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" '
                          f"AS SELECT * FROM range({rows})")
        found = supply_db.candidates_in(conn, supply_db.STAGING_SCHEMA, ["t"], run_id="run_001")
        assert len(found["t"]) == 2
        conn.close()


class TestTheHoldIsRecorded:
    """Criterion 4: the delivery, the dataset and every file that
    matched, so a person can see exactly what it could not choose
    between."""

    def test_the_delivery_record_names_the_held_dataset_and_its_files(self, dirs, tmp_path):
        _drop(dirs, "catch-up", {"birth_registrations_2026-08-01.csv": "a\n1\n",
                                  "birth_registrations_2026-08-02.csv": "a\n2\n"})
        d, found = _recognise(dirs, "catch-up")
        path = delivery_log.record(d, found, log_dir=tmp_path / "log")
        record = json.loads(path.read_text())
        assert record["held"] == [{
            "dataset_id": "birth-registrations",
            "files": ["birth_registrations_2026-08-01.csv",
                       "birth_registrations_2026-08-02.csv"]}]

    def test_a_delivery_with_no_hold_records_an_empty_list(self, dirs, tmp_path):
        _drop(dirs, "fine", {"birth_registrations_2026-08-01.csv": "a\n1\n"})
        [d] = delivery.list_deliveries(*dirs)
        path = delivery_log.record(d, arrivals.recognise(d), log_dir=tmp_path / "log")
        assert json.loads(path.read_text())["held"] == []


class TestALaterDeliveryIsUnaffected:
    def test_a_hold_does_not_block_the_next_delivery_for_that_dataset(self, dirs):
        """Criterion 7 - and nothing auto-resolves the held one."""
        _drop(dirs, "held", {"birth_registrations_2026-09-01.csv": "a\n1\n",
                              "birth_registrations_2026-09-02.csv": "a\n2\n"})
        _drop(dirs, "later", {"birth_registrations_2026-09-03.csv": "a\n1\n"},
              when=WHEN + timedelta(days=2))
        with pytest.warns(UserWarning):
            found = arrivals.arrivals_for("civil-registration", "run_", *dirs)
        held, later = found
        assert held.held == frozenset({"birth-registrations"})
        assert later.held == frozenset()
        assert later.path_for("birth-registrations").name \
            == "birth_registrations_2026-09-03.csv"
