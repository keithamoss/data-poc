"""REQ-PIPE-059's delivery-level hold is RETIRED (REQ-PIPE-105 criterion
6, as Keith amended it 2026-10-02).

Two files for one dataset in ONE arrival used to raise a hold: nothing
filed, nothing checked, a work item asking a person which file was the
supply. Criterion 6 replaces that with CONTESTED - the supply is filed
like any other, so its period is known; its own checks do not run and it
is not promoted; and anything reading it as context falls back to the
period's promoted version (criterion 8). One mechanism for one situation,
rather than two kept in step for ever.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from qa_tools.common import filing, supply_db, supply_holds


def _two_files_one_arrival():
    files = {"cp-clients": ["cp_clients.csv", "cp_clients (2).csv"]}
    return SimpleNamespace(
        run_id="cp_clients__202302010100000000", delivery_name="two-files",
        received_at=datetime(2023, 2, 1, 1, tzinfo=timezone.utc),
        files_by_dataset=files, held=frozenset(files))


def test_no_delivery_level_kind_remains():
    """REJECTED leaving the kind defined and unable to fire - the shape
    this project otherwise flags as a defect (REQ-PIPE-105's decision)."""
    assert supply_holds.KINDS == (supply_holds.ASSIGNMENT_RULE,)
    assert not hasattr(supply_holds, "DELIVERY_LEVEL")


def test_two_files_raise_no_hold_and_are_filed(private_supply_dsn):
    arrival = _two_files_one_arrival()
    filing.file_arrivals([arrival])
    with supply_db.connect(label="test-hold-retired") as conn:
        assert not supply_holds.outstanding(conn, dataset_id="cp-clients")
    assert filing.period_of("cp-clients", arrival.received_at), \
        "a contested supply is still filed, so its period is known"


def test_the_promotion_gate_sees_it_as_contested(private_supply_dsn):
    arrival = _two_files_one_arrival()
    filing.file_arrivals([arrival])
    with supply_db.connect(label="test-hold-retired") as conn:
        supply_db.ensure_schemas(conn)
        for ordinal in (1, 2):
            conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}".'
                         f'"cp_clients__202302010100000000__{ordinal}" (v int)')
        (supply,) = filing.supplies_of(conn, arrival)
    assert supply["contested"] is True
    assert "held" not in supply
