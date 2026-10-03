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


def test_a_contested_own_table_reports_only_checks_that_read_it(states):
    """Its own checks are withheld (REQ-PIPE-079 criterion 13), so only a
    sibling's check reading it is in scope."""
    out = _run(_res(ambiguous={"cp_clients": ["a", "b"]}),
               own_table="cp_clients", own_dataset="cp-clients")
    assert {r["check_id"] for r in out} == {PLACEMENTS_READS_CLIENTS,
                                            NOTIFICATIONS_READS_CLIENTS}


def test_nothing_missing_means_nothing_recorded(states):
    assert _run(_res(resolved={"cp_placements": "x", "cp_clients": "y"})) == []
