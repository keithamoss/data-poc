"""REQ-PIPE-110 criterion 20, NFRs 3 and 4: the configuration in force on
the day of the move produces exactly the periods, slots and instants it
produced before the move. The record is tests/fixtures/calendar_move_pin.json,
captured by tests/calendar_move_pin.py BEFORE contract/calendar.yaml
existed. Arrival verdicts are pinned separately, by the arrival-semantics
golden after a rebuild (tests/test_asset_time_semantics.py)."""
from __future__ import annotations

import json

from calendar_move_pin import PIN, capture


def test_every_dataset_computes_what_it_did_before_the_move():
    pinned = json.loads(PIN.read_text())
    now = capture()
    assert set(now) == set(pinned), "the datasets themselves changed"
    for dataset_id, before in pinned.items():
        after = now[dataset_id]
        assert after.get("no_calendar") == before.get("no_calendar"), dataset_id
        assert after.get("periods") == before.get("periods"), (
            f"{dataset_id}: its periods changed - "
            f"{_first_difference(before.get('periods'), after.get('periods'))}")
        assert after.get("slots") == before.get("slots"), (
            f"{dataset_id}: its slots changed - "
            f"{_first_difference(before.get('slots'), after.get('slots'))}")


def _first_difference(before, after):
    for i, (b, a) in enumerate(zip(before or [], after or [])):
        if b != a:
            return f"entry {i}: was {b}, now {a}"
    return f"{len(before or [])} entries before, {len(after or [])} now"
