"""A check that could not read a table says so and why (REQ-PIPE-105
criterion 13; REQ-PIPE-079 criteria 4 and 14-16)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from qa_tools.common import period_schema, supply_db, unrunnable

P = "data-asset-1.child-protection-family-support.child-protection"
PLACEMENTS_READS_CLIENTS = f"{P}.cp-placements.cp_client_id.relationships_dbt"
PLACEMENTS_READS_CARERS = f"{P}.cp-placements.carer_id.relationships_dbt"
NOTIFICATIONS_READS_CLIENTS = f"{P}.cp-notifications.cp_client_id.relationships_dbt"
READS = {PLACEMENTS_READS_CLIENTS: ["cp_clients"],
         PLACEMENTS_READS_CARERS: ["cp_carers"],
         NOTIFICATIONS_READS_CLIENTS: ["cp_clients"]}
AS_AT = datetime(2026, 2, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def states(monkeypatch):
    """Stand in for the slot state, which has its own tests."""
    table = {}
    monkeypatch.setattr(unrunnable, "supply_state",
                        lambda conn, dataset_id, period, as_at: table.get(dataset_id))
    return table


def _run(res, own_table="cp_placements", own_dataset="cp-placements"):
    return unrunnable.results_for(
        None, run_id="r", run_timestamp="t", own_table=own_table, own_dataset=own_dataset,
        period="2026-Q1", resolution=res, reads=READS, as_at=AS_AT)


def _res(**kw):
    return supply_db.Resolution(run_id="r", schema="s", **kw)


def test_a_check_in_scope_reading_a_missing_table_is_recorded_red_and_named(states):
    states["cp-clients"] = period_schema.STAGED_AWAITING_DECISION
    out = _run(_res(resolved={"cp_placements": "x"}, absent=["cp_clients"]))
    assert [(r["check_id"], r["status"], r["unrunnable_table"]) for r in out] == [
        (PLACEMENTS_READS_CLIENTS, "fail", "cp_clients")]
    assert "awaiting a decision" in out[0]["unrunnable_reason"]
    assert "did not fail" in out[0]["unrunnable_reason"]


def test_not_yet_due_is_no_data_rather_than_red(states):
    states["cp-clients"] = period_schema.NOT_YET_DUE
    (r,) = _run(_res(resolved={"cp_placements": "x"}, absent=["cp_clients"]))
    assert r["status"] == "nodata"


def test_another_datasets_check_is_out_of_scope_unless_it_reads_this_table(states):
    """The notifications check reads cp_clients, not cp_placements - it is
    the notifications run's to report, not this one's."""
    out = _run(_res(resolved={"cp_placements": "x"}, absent=["cp_clients"]))
    assert NOTIFICATIONS_READS_CLIENTS not in {r["check_id"] for r in out}


def test_a_held_table_is_left_to_held_blast_radius(states):
    out = _run(_res(resolved={"cp_placements": "x"}, held={"cp_clients": "y"}))
    assert out == []


def test_a_contested_sibling_is_reported_too(states):
    states["cp-carers"] = period_schema.STAGED_AWAITING_DECISION
    out = _run(_res(resolved={"cp_placements": "x"}, ambiguous={"cp_carers": ["a", "b"]}))
    assert [r["check_id"] for r in out] == [PLACEMENTS_READS_CARERS]


def test_a_contested_own_table_records_nothing_under_its_own_run(states):
    """REQ-PIPE-115 criteria 6 and 16: its own checks are not run, and a
    sibling's check reading it is recorded in THAT sibling's run - never
    under the run of the contested supply it reads. (This used to report
    the siblings' checks here.)"""
    out = _run(_res(ambiguous={"cp_clients": ["a", "b"]}),
               own_table="cp_clients", own_dataset="cp-clients")
    assert out == []


class TestContestedOutranksTheSlotReasons:
    """REQ-PIPE-115 criteria 14 and 15."""

    @pytest.mark.parametrize("slot_reason", [period_schema.PAST_DUE,
                                             period_schema.NOT_YET_DUE,
                                             period_schema.STAGED_AWAITING_DECISION, None])
    def test_a_contested_sibling_reads_contested_whatever_its_slot_says(self, states,
                                                                       slot_reason):
        states["cp-carers"] = slot_reason
        (r,) = _run(_res(resolved={"cp_placements": "x"},
                         ambiguous={"cp_carers": ["a", "b"]}))
        assert r["unrunnable_code"] == period_schema.CONTESTED
        assert r["status"] == "fail"
        assert "two files claim cp_carers" in r["unrunnable_reason"]


def test_nothing_missing_means_nothing_recorded(states):
    assert _run(_res(resolved={"cp_placements": "x", "cp_clients": "y"})) == []


NOTIFICATIONS_READS_WORKERS = f"{P}.cp-notifications.assigned_worker_id.relationships_dbt"
PLACEMENTS_READS_BOTH = f"{P}.cp-placements.carer_client.cross_dbt"


class TestOneRecordPerCheck:
    """A run records ONE result per check (tests/test_history_rekey.py
    holds the built history to it). Found on the first bootstrap under
    REQ-PIPE-131, which is the first to produce real holds: case workers'
    supply was held, cp-notifications' own table was staged awaiting a
    decision, and the notifications->workers check got a `held` record
    AND an `unrunnable` one - two results for one check in one run."""

    def test_a_check_reading_a_held_table_is_left_wholly_to_held_blast_radius(
            self, states, monkeypatch):
        monkeypatch.setattr(unrunnable, "supply_state",
                            lambda *a: period_schema.STAGED_AWAITING_DECISION)
        out = unrunnable.results_for(
            None, run_id="r", run_timestamp="t", own_table="cp_case_workers",
            own_dataset="cp-case-workers", period="2024-Q3",
            resolution=_res(absent=["cp_notifications"],
                            held={"cp_case_workers": "w"}),
            reads={NOTIFICATIONS_READS_WORKERS: ["cp_case_workers"]}, as_at=AS_AT)
        assert out == [], "held_blast_radius already records this check"

    def test_a_check_reading_two_missing_tables_gets_one_record(self, states):
        states["cp-clients"] = period_schema.STAGED_AWAITING_DECISION
        states["cp-carers"] = period_schema.STAGED_AWAITING_DECISION
        out = unrunnable.results_for(
            None, run_id="r", run_timestamp="t", own_table="cp_placements",
            own_dataset="cp-placements", period="2026-Q1",
            resolution=_res(resolved={"cp_placements": "x"},
                            absent=["cp_clients", "cp_carers"]),
            reads={PLACEMENTS_READS_BOTH: ["cp_clients", "cp_carers"]}, as_at=AS_AT)
        assert [r["check_id"] for r in out] == [PLACEMENTS_READS_BOTH]


class TestCouldNotBeLoadedOutranksEverything:
    """REQ-DASH-148 criterion 6."""

    def test_a_sibling_refused_in_this_arrival_says_so(self, states, monkeypatch):
        from types import SimpleNamespace

        from qa_tools.common import load_log

        states["cp-carers"] = period_schema.PAST_DUE
        monkeypatch.setattr(load_log, "latest_by_table", lambda *a, **k: {"x": SimpleNamespace(
            physical="cp_carers__202601010600000000", dataset_id="cp-carers", loaded=False)})
        (r,) = unrunnable.results_for(
            None, run_id="cp_placements__202601010600000000", run_timestamp="t",
            own_table="cp_placements", own_dataset="cp-placements", period="2026-Q1",
            resolution=_res(resolved={"cp_placements": "x"}, absent=["cp_carers"]),
            reads=READS, as_at=AS_AT)
        assert r["unrunnable_code"] == period_schema.COULD_NOT_LOAD
        assert "could not be loaded" in r["unrunnable_reason"]
