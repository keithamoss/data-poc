"""Filing a supply in a test, now that a filing must link to a real
delivery record (REQ-PIPE-144 criteria 10 and 18).

`file()` writes the delivery and the supply's own delivery_file row - its
receipt being the assignment's `received_at` - and then files through the
real `filing.record()`, so a test exercises the same refusal and the same
receipt view production does.
"""
from __future__ import annotations

from datetime import datetime, timezone

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
