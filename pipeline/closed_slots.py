"""Every period that closed with no supply, and the instants that decide
what it reads as on any date (REQ-DASH-133 criteria 9 and 10).

THE INSTANTS TRAVEL, NOT THE RULE - the same decision pipeline/
slot_timeline.py records for what a slot held. Whether a slot has CLOSED
is REQ-PIPE-131's rule (the next calendar period's claim window opening),
and the page must never re-derive it: this embeds each slot's closing
instant, and the page only compares it with the instant on show.

ONLY SLOTS THAT WERE A GAP WHEN THEY CLOSED, OR HAVE CHANGED SINCE: a
slot held or filed at its close and untouched since was never a gap, and a
daily feed's thousand ordinary slots would otherwise ride along to say so.
A slot emptied AFTER its close - de-substituted, demoted, re-filed out -
is included, because it is a gap from that instant on.

For each, the page reads, as at a date D:
  - not yet closed (closesAt > D)            -> not a gap yet
  - held at D (its last change by D)         -> not a gap
  - a supply filed by D that nobody rejected -> not a gap (it is waiting)
  - a filed supply rejected after D          -> not a gap yet (waiting)
  - a mark by D, after the last change by D -> not supplied (accepted)
  - otherwise                               -> closed, no supply (red)

RECORDED QA METADATA ONLY: the schedule (configuration), qa.decision
(promotions, substitutions, marks) and qa.filing. Nothing here reads a
schema holding supply rows.
"""
from __future__ import annotations

from datetime import datetime

from qa_tools.common import decision_log, supply_db


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def for_dataset(dataset_id: str, conn: supply_db.SupplyConnection | None = None,
                now: datetime | None = None) -> list[dict]:
    """[{period, index, closesAt, changes, filedAt, marks, rejected}] for
    every closed slot of this dataset that was a gap at its close OR has
    changed since - oldest first. `index` is the slot's position in the
    dataset's own schedule, so the page can group CONSECUTIVE gaps
    (criterion 7) without the calendar.

    `changes` is every change to what the slot HOLDS, [{at, held}], from
    qa.slot_holds via pipeline/slot_timeline.py - the one statement of
    which decisions fill and which empty. The first cut recorded only the
    first fill, so a period filled and then emptied again read as filled
    for ever (delivery-critic #105). `marks` is every mark that it was
    not supplied; one stands only until the slot next changes."""
    from qa_tools.common import asset_time, supply_holds
    from qa_tools.common import slots as slots_mod

    from pipeline import slot_timeline

    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:closed-slots") as opened:
            return for_dataset(dataset_id, opened, now)
    now = now or asset_time.now()
    try:
        own = slots_mod.slots_for_dataset(
            dataset_id, until=slots_mod.claimable_until(dataset_id, now.date()))
    except (ValueError, KeyError, FileNotFoundError):
        return []
    # WHAT WAS FILED TO EACH SLOT, by each supply's own receipt
    # (qa.supply_receipt, REQ-PIPE-144).
    filed: dict[str, list[tuple[str, str]]] = {}
    for slot, supply, at in conn.execute(
            "SELECT f.slot, f.supply_id, min(r.received_instant) FROM qa.filing f "
            "JOIN qa.supply_receipt r ON r.dataset_id = f.dataset_id "
            "AND r.supply_id = f.supply_id "
            "WHERE f.dataset_id = ? AND f.slot IS NOT NULL "
            "GROUP BY f.slot, f.supply_id ORDER BY 3", [dataset_id]).fetchall():
        filed.setdefault(slot, []).append((supply, _iso(at)))
    # A REJECTED SUPPLY LEAVES ITS PERIOD EMPTY (REQ-DASH-133 criterion 1's
    # exception, REQ-PIPE-153 criterion 9): from the rejection on, its
    # filing no longer counts, and the period says what happened to it.
    rejected: dict[str, dict] = {}
    superseded: set[str] = set()
    marks: dict[str, list[dict]] = {}
    for action, to_slot, effective_at, actor, reason, supply in conn.execute(
            f"SELECT action, to_slot, effective_at, actor, reason, supply "
            f"FROM {decision_log.TABLE} WHERE dataset_id = ? AND action IN (?, ?) "
            "ORDER BY effective_at, id",
            [dataset_id, decision_log.REJECT, decision_log.MARK_NOT_SUPPLIED]).fetchall():
        if action == decision_log.REJECT and supply:
            rejected.setdefault(supply, {"at": _iso(effective_at), "actor": actor,
                                         "reason": reason or ""})
        elif action == decision_log.MARK_NOT_SUPPLIED and to_slot:
            marks.setdefault(to_slot, []).append(
                {"at": _iso(effective_at), "actor": actor, "reason": reason or ""})
    # A SUPERSEDED SUPPLY IS NOT WAITING (REQ-PIPE-118): the newer version
    # that superseded it is filed to the same period and is what waits.
    from qa_tools.common import supersession

    for _, supplies in filed.items():
        for supply, _at in supplies:
            if supersession.is_superseded(conn, dataset_id, supply):
                superseded.add(supply)
    changes: dict[str, list[dict]] = {}
    for entry in slot_timeline.for_dataset(dataset_id, conn):
        changes.setdefault(entry["slot"], []).append(
            {"at": entry["at"], "held": entry["supply"] is not None})
    failed_keys = _failed_load_keys(conn, dataset_id)
    out = []
    for index, slot in enumerate(own):
        if slot.closes_at is None or slot.closes_at > now:
            continue
        closes = slot.closes_at
        own_changes = changes.get(slot.name, [])
        live = [at for supply, at in filed.get(slot.name, [])
                if supply not in rejected and supply not in superseded]
        gone = [(supply, at) for supply, at in filed.get(slot.name, []) if supply in rejected]
        filed_first = min(live) if live else None
        at_close = [c for c in own_changes if datetime.fromisoformat(c["at"]) <= closes]
        held_at_close = bool(at_close) and at_close[-1]["held"]
        changed_since = any(datetime.fromisoformat(c["at"]) > closes for c in own_changes)
        filed_by_close = filed_first and datetime.fromisoformat(filed_first) <= closes
        if (held_at_close or filed_by_close) and not changed_since and not gone:
            continue
        rej = None
        if gone and not live:
            supply, received = gone[-1]
            rej = {**rejected[supply], "supply": supply, "receivedAt": received,
                   "failedLoad": supply_holds.arrival_key_of(supply) in failed_keys}
        out.append({"period": slot.name, "index": index, "closesAt": closes.isoformat(),
                    "changes": own_changes, "filedAt": filed_first,
                    "marks": marks.get(slot.name, []), "rejected": rej})
    return out


def _failed_load_keys(conn, dataset_id: str) -> set[str]:
    """Arrival keys of this dataset's staged tables whose latest load
    record says they could not be loaded (REQ-PIPE-060) - recorded QA
    metadata, never the table itself."""
    from qa_tools.common import load_log

    keys: set[str] = set()
    for physical, entry in load_log.latest_by_table(conn=conn).items():
        if entry.dataset_id == dataset_id and not entry.loaded:
            split = supply_db.split_staged(physical)
            if split:
                keys.add(split[1])
    return keys
