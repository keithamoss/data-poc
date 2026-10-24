"""Filing a supply in a test, now that a filing must link to a real
delivery record (REQ-PIPE-144 criteria 10 and 18).

`file()` writes the delivery and the supply's own delivery_file row - its
receipt being the assignment's `received_at` - and then files through the
real `filing.record()`, so a test exercises the same refusal and the same
receipt view production does.
"""
from __future__ import annotations

from datetime import datetime, timezone

import attempt_support
from qa_tools.common import filing, qa_store, supply_db

_DEFAULT_RECEIPT = datetime(2020, 1, 1, tzinfo=timezone.utc)


def ensure_delivery(name: str, dataset_id: str, received_at: datetime | None,
                    filename: str | None = None) -> None:
    """A delivery record carrying one file for `dataset_id`, idempotently."""
    at = received_at or _DEFAULT_RECEIPT
    with supply_db.connect(label="pytest:filing-support") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".delivery (name, received_at, received_instant) '
            "VALUES (?, ?, ?) ON CONFLICT (name) DO NOTHING", [name, at.isoformat(), at])
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".delivery_file (delivery, filename, dataset_id, '
            "received_at, received_instant, received_from, receipt_sequence) "
            "VALUES (?, ?, ?, ?, ?, 'our-clock', 0) ON CONFLICT (delivery, filename) DO NOTHING",
            [name, filename or f"{dataset_id}.csv", dataset_id, at.isoformat(), at])


def file(assignment, delivery: str | None = None) -> bool:
    """filing.record(), with the delivery it links to recorded first."""
    name = delivery or f"pytest-{assignment.dataset_id}-{assignment.supply_id}"
    ensure_delivery(name, assignment.dataset_id, assignment.received_at)
    return filing.record(assignment, name)


def place(conn, dataset_id: str, supply_id: str, slot: str, delivery: str,
          branch: str = "pytest") -> None:
    """Make `slot` this supply's CURRENT filing, the append-only way
    (REQ-PIPE-141 NFR 3): the rule's row once, then - where a test moves
    it - a newer row, as a re-file would add. `refiled_by` -1 marks a
    test's move, so no real decision is implied."""
    from qa_tools.common import filing

    conn.execute(
        f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, delivery) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (dataset_id, supply_id) WHERE refiled_by IS NULL "
        "DO NOTHING", [dataset_id, supply_id, slot, branch, delivery])
    current = conn.execute(
        f"SELECT slot, delivery FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, supply_id]).fetchall()
    if current and tuple(current[0]) != (slot, delivery):
        conn.execute(
            f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, delivery, "
            "refiled_by) VALUES (?, ?, ?, ?, ?, -1)",
            [dataset_id, supply_id, slot, branch, delivery])


def forget(conn, where: str, params=()) -> None:
    """Remove a test's own filings. qa.filing refuses DELETE (REQ-PIPE-141
    NFR 3), so this runs with triggers off for the one statement - a test's
    tidy-up, never a thing production code does."""
    from qa_tools.common import filing

    with conn.raw.transaction():
        conn.execute("SET LOCAL session_replication_role = replica")
        conn.execute(f"DELETE FROM {filing.TABLE} WHERE {where}", list(params))


def filed(conn, dataset_id: str, supply_id: str, slot: str | None) -> None:
    """File `supply_id` to `slot` before a test promotes it: a person's promote
    goes only into the period the supply is filed to (post-build-review
    #173), so a fixture that promotes as a person files first, as the real
    pipeline does before any check runs."""
    delivery = f"pytest-{dataset_id}-{supply_id}"
    ensure_delivery(delivery, dataset_id, None)
    place(conn, dataset_id, supply_id, slot, delivery)
    checked(conn, dataset_id, supply_id)


def checked(conn, dataset_id: str, supply_id: str) -> str:
    """A completed run of the supply's own checks, as its arrival leaves one:
    a person promotes only what has been checked since it was last filed
    (post-build-review #173 fix 2)."""
    import uuid

    from qa_tools.common import hierarchy, qa_store

    ds = hierarchy.dataset(dataset_id)
    run_key = f"pytest-run-{uuid.uuid4().hex[:12]}"
    qa_store.record_run(conn, run_key=run_key, agency_id=ds.agency_id,
                        collection_id=ds.collection_id,
                        run_timestamp="2099-01-01T10:00:00+08:00", run_by="pytest",
                        environment="sandbox")
    qa_store.set_run_purpose(conn, run_key, dataset_id=dataset_id, supply_id=supply_id)
    attempt_support.opened(conn, run_key)
    qa_store.complete_run(conn, run_key)
    return run_key
