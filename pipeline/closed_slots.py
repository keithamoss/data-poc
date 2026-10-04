"""Every period that closed with no supply, and the instants that decide
what it reads as on any date (REQ-DASH-133 criteria 9 and 10).

THE INSTANTS TRAVEL, NOT THE RULE - the same decision pipeline/
slot_timeline.py records for what a slot held. Whether a slot has CLOSED
is REQ-PIPE-131's rule (the next calendar period's claim window opening),
and the page must never re-derive it: this embeds each slot's closing
instant, and the page only compares it with the instant on show.

ONLY SLOTS THAT WERE A GAP WHEN THEY CLOSED: unfilled, with nothing filed
to them, at their closing instant. A slot filled or filed before it closed
was never a gap, and a daily feed's thousand ordinary slots would
otherwise ride along to say so.

For each, the page reads, as at a date D:
  - not yet closed (closesAt > D)            -> not a gap yet
  - filled or filed by D                    -> not a gap any more
  - a filed supply rejected after D          -> not a gap yet (waiting)
  - marked as not supplied by D             -> not supplied (accepted)
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
    """[{period, index, closesAt, filledAt, filedAt, markedAt, mark}] for
    every slot of this dataset that was a gap when it closed, oldest first.
    `index` is the slot's position in the dataset's own schedule, so the
    page can group CONSECUTIVE gaps (criterion 7) without the calendar."""
    from qa_tools.common import asset_time
    from qa_tools.common import slots as slots_mod

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
    # (qa.supply_receipt, REQ-PIPE-144) - a file received before the slot
    # closed means the slot was not a gap then.
    filed: dict[str, list[tuple[str, str]]] = {}
    for slot, supply, at in conn.execute(
            "SELECT f.slot, f.supply_id, min(r.received_instant) FROM qa.filing f "
            "JOIN qa.supply_receipt r ON r.dataset_id = f.dataset_id "
            "AND r.supply_id = f.supply_id "
            "WHERE f.dataset_id = ? AND f.slot IS NOT NULL "
            "GROUP BY f.slot, f.supply_id ORDER BY 3", [dataset_id]).fetchall():
        filed.setdefault(slot, []).append((supply, _iso(at)))
    decisions = conn.execute(
        f"SELECT action, to_slot, effective_at, actor, reason, supply FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? ORDER BY effective_at, id", [dataset_id]).fetchall()
    filled_at: dict[str, str] = {}
    marks: dict[str, dict] = {}
    # A REJECTED SUPPLY LEAVES ITS PERIOD EMPTY (REQ-DASH-133 criterion 1's
    # exception, REQ-PIPE-153 criterion 9): from the rejection on, its
    # filing no longer counts, and the period says what happened to it
    # rather than that nothing came.
    rejected: dict[str, dict] = {}
    for action, to_slot, effective_at, actor, reason, supply in decisions:
        if action == decision_log.REJECT and supply:
            rejected.setdefault(supply, {"at": _iso(effective_at), "actor": actor,
                                         "reason": reason or ""})
        if not to_slot:
            continue
        if action in (decision_log.PROMOTE, decision_log.REFILE, decision_log.SUBSTITUTE,
                      decision_log.INHERIT):
            filled_at.setdefault(to_slot, _iso(effective_at))
        elif action == decision_log.MARK_NOT_SUPPLIED:
            marks.setdefault(to_slot, {"at": _iso(effective_at), "actor": actor,
                                       "reason": reason or ""})
    failed_keys = _failed_load_keys(conn, dataset_id)
    out = []
    for index, slot in enumerate(own):
        if slot.closes_at is None or slot.closes_at > now:
            continue
        closes = slot.closes_at
        filled = filled_at.get(slot.name)
        live = [at for supply, at in filed.get(slot.name, []) if supply not in rejected]
        gone = [(supply, at) for supply, at in filed.get(slot.name, []) if supply in rejected]
        filed_first = min(live) if live else None
        if filled and datetime.fromisoformat(filled) <= closes:
            continue
        if filed_first and datetime.fromisoformat(filed_first) <= closes:
            continue
        rej = None
        if gone and not live:
            supply, received = gone[-1]
            from qa_tools.common import supply_holds

            rej = {**rejected[supply], "supply": supply, "receivedAt": received,
                   "failedLoad": supply_holds.arrival_key_of(supply) in failed_keys}
        mark = marks.get(slot.name)
        out.append({"period": slot.name, "index": index, "closesAt": closes.isoformat(),
                    "filledAt": filled, "filedAt": filed_first,
                    "markedAt": mark["at"] if mark else None, "mark": mark,
                    "rejected": rej})
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
