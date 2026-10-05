"""REQ-PIPE-131 criterion 16 (Keith, 2026-10-05; post-build-review #93):
an authored calendar's last slot closes, so a file arriving after the
calendar runs out is held rather than filed years backward."""
from __future__ import annotations

from datetime import date, datetime, timezone

from qa_tools.common import slots


def _last_slot():
    return slots.slots_for_dataset("cp-clients", until=date(2031, 1, 1))[-1]


def test_the_last_slot_closes():
    last = _last_slot()
    assert last.closes_at is not None


def test_it_stays_open_as_long_as_the_period_before_it():
    every = slots.slots_for_dataset("cp-clients", until=date(2031, 1, 1))
    before, last = every[-2], every[-1]
    assert last.closes_at - last.claim_opens_at == last.claim_opens_at - before.claim_opens_at


def test_a_2030_file_finds_no_open_slot():
    at = datetime(2030, 6, 1, 1, tzinfo=timezone.utc)
    assert not any(slots.is_open(s, at)
                   for s in slots.slots_for_dataset("cp-clients", until=date(2031, 1, 1)))
