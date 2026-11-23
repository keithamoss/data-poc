"""A supply for a dataset with no calendar is filed to no period, never held
for placing, and checked when it arrives (REQ-PIPE-434).

THE DEFECT THIS STARTED FROM (plans/running-thoughts.md #141, confirmed by
the delivery-architect at filing.py's slot lookup): `NoCalendarAgreed` is not
a ValueError, so `file_arrivals()`'s handlers missed it and it escaped
filing; and past that the supply would have been HELD as waiting for a
person to place it, so no tool checked it.

Driven through the real `filing.file_arrivals()` and the real arrival
recogniser over a delivery on disk, against a fixture asset - the real
daily asset with its datasets replaced, as tests/test_no_calendar.py does,
for the reason that module records.
"""
from __future__ import annotations

import pytest

import agreement_split
from asset_model import assignment, delivery as delivery_tree
from qa_tools.common import delivery, filing, supply_db, supply_holds


NEVER = {"id": "one-off-extract", "name": "A Project Extract",
         "table": "one_off_extract", "no_calendar": "never",
         "arrival_pattern": r"one_off_extract\.csv"}
NOT_YET = {"id": "cp-referrals", "name": "Referrals", "table": "cp_referrals",
           "no_calendar": "not-yet-agreed", "arrival_pattern": r"cp_referrals\.csv"}
AGREED = {"id": "birth-registrations", "name": "Birth Registrations",
          "table": "birth_registrations",
          "arrival_pattern": r"birth_registrations_[^/]+\.csv"}


def _asset_with(datasets, tmp_path, monkeypatch):
    doc = agreement_split.merged_view(agreement_split.REAL_CONTRACT_DIR)
    agency = doc["hierarchy"]["agencies"][0]
    agency["collections"] = [{
        "id": "civil-registration", "name": "Civil Registration", "short": "bdm",
        "run_prefix": "run_",
        "contract": "registry-services/bdm-birth-registrations-contract.yaml",
        "delivery_boundary": "directory", "datasets": datasets}]
    doc["hierarchy"]["agencies"] = [agency]
    return agreement_split.repoint(monkeypatch, tmp_path / "asset", doc)


def _arrivals(tmp_path, files, when="2026-02-01T09:00:00+08:00"):
    """One delivery on disk, received and recorded, then recognised - as the
    batch does it before filing."""
    from asset_model import arrivals
    from qa_tools.common import delivery_log

    deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
    folder = deliveries / "monday"
    folder.mkdir(parents=True)
    receipts.mkdir(parents=True)
    for name in files:
        (folder / name).write_text("a\n1\n")
    delivery.write_receipts("monday", when, receipts, files=files, sequence=1)
    for d in delivery_tree.list_deliveries(deliveries, receipts):
        delivery_log.record(d, arrivals.recognise(d))
    found = arrivals.arrivals_for("civil-registration", "run_", deliveries, receipts)
    assert found, "the fixture must produce an arrival, or this proves nothing"
    return found


@pytest.fixture
def clean(private_supply_dsn):
    return private_supply_dsn


class TestItIsFiledToNoPeriod:
    """Criterion 1."""

    @pytest.mark.parametrize("dataset", [NEVER, NOT_YET], ids=["never", "not-yet-agreed"])
    def test_the_arrival_is_recorded_with_no_slot(self, dataset, clean, tmp_path, monkeypatch):
        _asset_with([AGREED, dataset], tmp_path, monkeypatch)
        found = _arrivals(tmp_path, [f"{dataset['table']}.csv"])

        written = filing.file_arrivals(found)   # raised NoCalendarAgreed before the fix

        (decided,) = written
        assert decided.dataset_id == dataset["id"]
        assert decided.slot is None
        assert decided.branch == assignment.NO_PERIOD
        (record,) = filing.filings_of(dataset["id"])
        assert record["slot"] is None
        assert record["branch"] == assignment.NO_PERIOD
        assert filing.period_of(dataset["id"], found[0].received_at) is None

    def test_a_second_pass_files_nothing(self, clean, tmp_path, monkeypatch):
        _asset_with([AGREED, NEVER], tmp_path, monkeypatch)
        found = _arrivals(tmp_path, ["one_off_extract.csv"])
        assert filing.file_arrivals(found)
        assert filing.file_arrivals(found) == []

    def test_an_agreed_dataset_beside_it_is_filed_as_ever(self, clean, tmp_path, monkeypatch):
        _asset_with([AGREED, NEVER], tmp_path, monkeypatch)
        found = _arrivals(tmp_path, ["one_off_extract.csv",
                                     "birth_registrations_2026-02-01.csv"])
        by_id = {a.dataset_id: a for a in filing.file_arrivals(found)}
        assert by_id["one-off-extract"].slot is None
        # The ordinary rule decides it (whichever branch the fixture's dates
        # give), never the no-period filing.
        assert by_id["birth-registrations"].branch in (
            assignment.OPEN_UNFILLED, assignment.RESUPPLY, assignment.HELD)


class TestItIsNeverHeldForAPerson:
    """Criterion 2: there is no period a person could choose."""

    def test_no_hold_is_raised(self, clean, tmp_path, monkeypatch):
        _asset_with([AGREED, NEVER], tmp_path, monkeypatch)
        (decided,) = filing.file_arrivals(_arrivals(tmp_path, ["one_off_extract.csv"]))
        assert not decided.is_held
        with supply_db.connect(label="test-no-period-hold") as conn:
            assert not supply_holds.outstanding(conn, dataset_id="one-off-extract")


class TestItIsCheckedWhenItArrives:
    """Criterion 3: staged, filed, then checked in the same pass, against a
    run view of the NEWEST version of each no-calendar table.

    Through the real per-arrival lifecycle (arrival_lifecycle.process with
    orchestrate.steps), the real staging and the real filing and overlay. The
    run step itself is stood in for at its entry point, so what it is handed
    - the run's resolved views - is what is asserted; the promotion gate is
    REQ-PIPE-435's (criterion 7), so it is stood in for too."""

    BDM_NEVER = {"id": "birth-registrations", "name": "Birth Registrations",
                 "table": "birth_registrations", "no_calendar": "never",
                 "arrival_pattern": r"birth_registrations_[^/]+\.csv"}

    def _deliver(self, tmp_path, name, when, sequence):
        from asset_model import arrivals
        from qa_tools.common import delivery_log

        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        folder = deliveries / name
        folder.mkdir(parents=True)
        receipts.mkdir(parents=True, exist_ok=True)
        filename = f"birth_registrations_{name}.csv"
        (folder / filename).write_text("registration_id,child_family_name\nBR0001,SMITH\n")
        delivery.write_receipts(name, when, receipts, files=[filename], sequence=sequence)
        for d in delivery_tree.list_deliveries(deliveries, receipts):
            delivery_log.record(d, arrivals.recognise(d))
        found = arrivals.arrivals_for("civil-registration", "run_", deliveries, receipts)
        (arrival,) = [a for a in found if a.delivery_name == name]
        return arrival, folder / filename

    def test_each_arrival_is_checked_against_the_newest_version(
            self, clean, tmp_path, monkeypatch):
        from qa_tools.common import arrival_lifecycle, sample_data
        from qa_tools.tools import orchestrate, stage

        _asset_with([self.BDM_NEVER], tmp_path, monkeypatch)
        checked = []

        def run_one(collection_id, entry, run_timestamp, run_by, *args, **kw):
            with supply_db.connect(read_only=True, label="test-no-period-run") as conn:
                checked.append((entry["run_id"],
                                dict(supply_db.resolution_for(conn, entry["run_id"]).resolved)))
            return []

        monkeypatch.setattr(orchestrate, "run_one", run_one)
        monkeypatch.setattr(orchestrate, "promote_after", lambda *a, **k: None)

        staged = []
        for name, when, seq in (("first", "2026-02-01T09:00:00+08:00", 1),
                                ("second", "2026-02-03T09:00:00+08:00", 2)):
            arrival, csv = self._deliver(tmp_path, name, when, seq)
            staged.append(stage.stage_table("civil-registration", arrival.run_id,
                                            "birth_registrations", str(csv),
                                            received_at=arrival.received_at))
            arrival_lifecycle.process(arrival, steps=orchestrate.steps("civil-registration"),
                                      among=[arrival], run_timestamp=when, run_by="a test")

        assert all(staged), "both files must actually stage, or this proves nothing"
        with supply_db.connect(read_only=True, label="test-no-period-run") as conn:
            landed = {r[0] for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
                [sample_data.SCHEMA]).fetchall()}
        assert set(staged) <= landed, "a no-calendar supply stages into the sample schema"
        assert [resolved.get("birth_registrations") for _run, resolved in checked] == staged, (
            "each run must be checked, and read the newest version staged when it ran")


class TestNoScheduleArithmeticIsDone:
    """Criterion 4: no lateness is judged for it - the filing's arrival
    classification is empty, never `unfiled` (which reads as a supply that
    should have had a period)."""

    def test_its_filing_carries_no_classification(self, clean, tmp_path, monkeypatch):
        _asset_with([AGREED, NEVER], tmp_path, monkeypatch)
        filing.file_arrivals(_arrivals(tmp_path, ["one_off_extract.csv"]))
        (record,) = filing.filings_of("one-off-extract")
        assert record["classification"] is None


class TestNoScheduleIsAskedOfIt:
    """Criterion 4, at the readers that would ask: the claim window the gate's
    effective instant is taken from, the runway and schedule-ended warnings,
    and the slots the dashboard calls missing. None raises NoCalendarAgreed,
    and none reports the dataset as failing for want of a calendar."""

    def test_the_gate_s_effective_instant_asks_no_claim_window(
            self, clean, tmp_path, monkeypatch):
        from qa_tools.tools import orchestrate

        _asset_with([NEVER], tmp_path, monkeypatch)
        (arrival,) = _arrivals(tmp_path, ["one_off_extract.csv"])
        assert orchestrate._claim_window("civil-registration", arrival) is None
        assert orchestrate.effective_at_of("civil-registration", arrival)   # raised before

    def test_no_runway_or_schedule_ended_warning_names_it(self, tmp_path, monkeypatch):
        from datetime import date

        from qa_tools.common import runway

        _asset_with([AGREED, NEVER, NOT_YET], tmp_path, monkeypatch)
        on = date(2026, 2, 1)
        assert "one-off-extract" not in runway.exhausted_datasets(on)
        assert "cp-referrals" not in runway.exhausted_datasets(on)
        lines = " ".join(runway.warning_lines(on))
        assert "one-off-extract" not in lines and "cp-referrals" not in lines

    def test_it_has_no_slots_to_be_missing(self, tmp_path, monkeypatch):
        from pipeline import period_slots

        _asset_with([AGREED, NEVER], tmp_path, monkeypatch)
        assert period_slots.for_dataset("one-off-extract") is None


#: The daily asset's configuration is the fixture's base.
pytestmark = pytest.mark.asset("daily")
