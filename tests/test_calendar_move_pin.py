"""REQ-PIPE-110 criterion 20, NFRs 3 and 4: the configuration in force on
the day of the move produces exactly the periods, slots and instants it
produced before the move. The record is tests/fixtures/calendar_move_pin.json,
captured by tests/calendar_move_pin.py BEFORE contract/calendar.yaml
existed. Arrival verdicts are pinned separately, by the arrival-semantics
golden after a rebuild (tests/test_asset_time_semantics.py)."""
from __future__ import annotations

import json

from calendar_move_pin import PIN, UNTIL, capture


def test_every_dataset_computes_what_it_did_before_the_move():
    """ROUND BY ROUND (REQ-PIPE-321 criterion 14): a collection at
    files_go_to_period N fills the period N after each round, so each
    period and slot is named by the round it is due on - the name the pin
    recorded at 0 - and every instant must be what was pinned. The pin is
    never re-captured."""
    pinned = json.loads(PIN.read_text())
    now = capture(by_round=True)
    # A DATASET ADDED SINCE (Emergency Department's, REQ-QAC-231) has no
    # pinned past to keep, so the pin speaks for the datasets it holds: none
    # of them may be lost or renamed, and each computes what it did.
    assert pinned, "the pin holds no dataset - the comparison would prove nothing"
    assert set(pinned) <= set(now), "the datasets themselves changed"
    for dataset_id, before in pinned.items():
        after = (_from_the_pinned_start(now[dataset_id], before)
                 if dataset_id in _EARLIER_DAYS_ADDED else now[dataset_id])
        assert after.get("no_calendar") == before.get("no_calendar"), dataset_id
        before_periods = _without_rounds_filling_nothing(dataset_id, before.get("periods"),
                                                         after.get("periods"))
        assert after.get("periods") == before_periods, (
            f"{dataset_id}: its periods changed - "
            f"{_first_difference(before_periods, after.get('periods'))}")
        before_slots = _without_rounds_filling_nothing(dataset_id, before.get("slots"),
                                                       after.get("slots"))
        after_slots = after.get("slots")
        if dataset_id in _LATER_VERSION_ADDED:
            before_slots, after_slots = (_before_the_later_version(x, dataset_id)
                                         for x in (before_slots, after_slots))
        assert after_slots == before_slots, (
            f"{dataset_id}: its slots changed - "
            f"{_first_difference(before_slots, after_slots)}")


# A LATER VERSION ADDED SINCE, as a declared correction: TS-62's six-hour
# claim window for Birth Registrations from 2026-09-25 (REQ-GEN-205 criteria
# 24 and 25, which require a new version near the history's end). It moves
# that day's claim opening, and so the closing of the slot before it, which
# ends where the next claim window opens (REQ-PIPE-131). Every slot before
# that one is compared as pinned; the version itself is a new configuration,
# not the move rewriting the past.
_LATER_VERSION_ADDED = {"birth-registrations": "2026-09-25"}


def _before_the_later_version(entries, dataset_id):
    """The slots before the one whose closing the later version moves."""
    if not entries:
        return entries
    names = [e[0] for e in entries]
    cut = next((i for i, n in enumerate(names) if n >= _LATER_VERSION_ADDED[dataset_id]),
               len(names))
    return entries[:max(0, cut - 1)]


# The datasets whose history was lengthened backwards: Birth Registrations
# by REQ-GEN-185, and Child Protection's six by REQ-GEN-207's ten years
# (2013-2022, added as earlier versions, rewriting nothing pinned). Every
# other dataset is compared whole, so an earlier period appearing on one of
# them still fails (post-build-review #156).
_EARLIER_DAYS_ADDED = {
    "birth-registrations",
    "cp-carers", "cp-case-workers", "cp-clients",
    "cp-investigations", "cp-notifications", "cp-placements",
}


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



def _without_rounds_filling_nothing(dataset_id: str, pinned, now):
    """The pinned entries less the rounds that fill nothing now. At
    files_go_to_period N a round whose period N ahead the calendar gives no
    date - at 1, the last authored round, whose period is past the
    calendar's end - opens no slot and owes no period (REQ-PIPE-321
    criterion 8), so it cannot compare. Each one left out is checked to be
    exactly that, and no other."""
    from qa_tools.common import agreement, schedule

    if not pinned or now is None:
        return pinned
    have = {e[0] for e in now}
    sequence = {p.name: p for p in schedule.periods_for_calendar(
        schedule.calendar_for_dataset(dataset_id).name, until=UNTIL)}
    agr = agreement.current()
    for entry in pinned:
        if entry[0] in have:
            continue
        rnd = sequence.get(entry[0])
        n = (agr.files_go_to_period_for(dataset_id, rnd.date) or 0) if rnd else 0
        assert n and schedule.period_filled_by(dataset_id, rnd) is None, (
            f"{dataset_id}: the pinned round {entry[0]} is gone, and it is not a round whose "
            f"period {n} ahead is past the calendar's end")
    return [e for e in pinned if e[0] in have]
