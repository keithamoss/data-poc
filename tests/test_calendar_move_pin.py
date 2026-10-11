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
        after = (_from_the_pinned_start(now[dataset_id], before)
                 if dataset_id in _EARLIER_DAYS_ADDED else now[dataset_id])
        assert after.get("no_calendar") == before.get("no_calendar"), dataset_id
        assert after.get("periods") == before.get("periods"), (
            f"{dataset_id}: its periods changed - "
            f"{_first_difference(before.get('periods'), after.get('periods'))}")
        assert after.get("slots") == before.get("slots"), (
            f"{dataset_id}: its slots changed - "
            f"{_first_difference(before.get('slots'), after.get('slots'))}")


# The only dataset whose history was lengthened backwards. Every other
# dataset is compared whole, so an earlier period appearing on one of them
# still fails (post-build-review #156).
_EARLIER_DAYS_ADDED = {"birth-registrations"}


def _from_the_pinned_start(after: dict, before: dict) -> dict:
    """`after` with any period or slot BEFORE the pinned history's first one
    left out. EARLIER DAYS MAY BE ADDED, and nothing that existed may change:
    REQ-GEN-185 (Keith, 2026-10-11) added ten days of Birth Registrations
    before 2026-08-24 as an earlier version, which rewrites no period or slot
    the move produced - the property this pin guards. Never re-captured to
    pass (tests/calendar_move_pin.py's own rule)."""
    out = dict(after)
    for key in ("periods", "slots"):
        pinned, now = before.get(key), after.get(key)
        if pinned and now:
            first = pinned[0][0]
            out[key] = [e for e in now if e[0] >= first]
    return out


def _first_difference(before, after):
    for i, (b, a) in enumerate(zip(before or [], after or [])):
        if b != a:
            return f"entry {i}: was {b}, now {a}"
    return f"{len(before or [])} entries before, {len(after or [])} now"
