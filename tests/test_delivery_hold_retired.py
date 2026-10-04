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
        files_by_dataset=files, contested=frozenset(files))


def test_no_delivery_level_kind_remains():
    """REJECTED leaving the kind defined and unable to fire - the shape
    this project otherwise flags as a defect (REQ-PIPE-105's decision)."""
    assert supply_holds.KINDS == (supply_holds.ASSIGNMENT_RULE,)
    assert not hasattr(supply_holds, "DELIVERY_LEVEL")


def _recorded(arrival):
    """The delivery record a filing links to (REQ-PIPE-144 criterion 10)."""
    import filing_support
    for i, name in enumerate(arrival.files_by_dataset["cp-clients"]):
        filing_support.ensure_delivery(arrival.delivery_name, "cp-clients",
                                       arrival.received_at, filename=name)
    return arrival


def test_two_files_raise_no_hold_and_are_filed(private_supply_dsn):
    arrival = _recorded(_two_files_one_arrival())
    filing.file_arrivals([arrival])
    with supply_db.connect(label="test-hold-retired") as conn:
        assert not supply_holds.outstanding(conn, dataset_id="cp-clients")
    assert filing.period_of("cp-clients", arrival.received_at), \
        "a contested supply is still filed, so its period is known"


def test_the_promotion_gate_sees_it_as_contested(private_supply_dsn):
    arrival = _recorded(_two_files_one_arrival())
    filing.file_arrivals([arrival])
    with supply_db.connect(label="test-hold-retired") as conn:
        supply_db.ensure_schemas(conn)
        for ordinal in (1, 2):
            conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}".'
                         f'"cp_clients__202302010100000000__{ordinal}" (v int)')
        (supply,) = filing.supplies_of(conn, arrival)
    assert supply["contested"] is True
    assert "held" not in supply


def test_the_contested_list_is_derived_not_stored(private_supply_dsn):
    """REQ-PIPE-144 criteria 25-27: qa.delivery has no `contested` column
    (the in-place `held` -> `contested` rename this replaced went with it -
    an older schema is rebuilt, not migrated), and the delivery log still
    returns the list, from the delivery_contested view."""
    from qa_tools.common import delivery_log, qa_store

    arrival = _recorded(_two_files_one_arrival())
    with supply_db.connect(label="test-contested-view") as conn:
        cols = {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = 'delivery'", [qa_store.SCHEMA]).fetchall()}
        (record,) = [r for r in delivery_log.records(conn) if r["delivery"] == arrival.delivery_name]
    assert "contested" not in cols
    assert record["contested"] == [
        {"dataset_id": "cp-clients", "files": ["cp_clients (2).csv", "cp_clients.csv"]}]
