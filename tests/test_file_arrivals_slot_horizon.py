"""file_arrivals() builds each dataset's slots ONCE per call - and under
REQ-PIPE-131 a stale list is not merely incomplete, it is WRONG: its last
slot now closes, so a later arrival in the same call fell past it and was
HELD, where a fresh list files it to its own open day (delivery-critic,
overnight sprint 3b, finding 3). Before REQ-PIPE-131 the same stale list
filed it backward instead. Latent in production - every caller passes one
receipt instant per call - but the function's contract takes a list.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from qa_tools.common import assignment, filing

PERTH = timezone(timedelta(hours=8))


def _arrival(day: int):
    at = datetime(2026, 9, day, 14, 0, tzinfo=PERTH)
    return SimpleNamespace(
        run_id=f"birth_registrations__2026090{day}", delivery_name=f"d{day}",
        received_at=at, files_by_dataset={"birth-registrations": ["br.csv"]},
        contested=frozenset())


def test_a_later_arrival_in_the_same_call_files_to_its_own_open_day(private_supply_dsn):
    import filing_support

    first, later = _arrival(1), _arrival(3)
    for a in (first, later):
        filing_support.ensure_delivery(a.delivery_name, "birth-registrations", a.received_at)
    written = filing.file_arrivals([first, later])
    by_supply = {a.supply_id: a for a in written}
    late = next(a for a in by_supply.values() if a.received_at == later.received_at)
    assert late.branch == assignment.OPEN_UNFILLED and late.slot == "2026-09-03", late
