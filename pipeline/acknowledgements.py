"""Which promoted amber supplies were acknowledged, for the dashboard
(REQ-PIPE-122 criterion 21, carrying forward what REQ-QAC-017 asked of its
per-run accept).

THE INSTANTS TRAVEL, NOT THE RULE - the same decision as
pipeline/slot_timeline.py and pipeline/closed_slots.py. For each amber
supply promoted under promote-and-acknowledge this embeds when it was
promoted, when (if ever) a person acknowledged it, and when (if ever) it
left its period - after which the acknowledgement lapsed rather than stayed
outstanding (criterion 16). The page compares those with the date on show.

RECORDED QA METADATA ONLY: qa.decision. Keyed by the RUN that checked the
supply, through slot_timeline's one mapping from a supply to its run, so
the badge sits on the supply-history row it describes.
"""
from __future__ import annotations

from qa_tools.common import decision_log, supply_db


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _acknowledged(row) -> dict:
    """An acknowledgement as the page shows it: the person by NAME
    (REQ-PIPE-147 criterion 7, REQ-GEN-135 criterion 12)."""
    from qa_tools.common import people

    actor, reason, at = row
    return {"actor": people.display_name(actor), "reason": reason or "", "at": _iso(at)}


def for_dataset(dataset_id: str,
                conn: supply_db.SupplyConnection | None = None) -> dict[str, dict]:
    """{run_id: {supply, period, promotedAt, acknowledged, lapsedAt}}."""
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:acknowledgements") as opened:
            return for_dataset(dataset_id, opened)
    from pipeline import slot_timeline

    out: dict[str, dict] = {}
    promotions = conn.execute(
        f"SELECT supply, to_slot, effective_at FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND acknowledgement_owed ORDER BY effective_at, id",
        [dataset_id]).fetchall()
    if not promotions:
        return out
    timeline = slot_timeline.for_dataset(dataset_id, conn)
    for supply, slot, promoted_at in promotions:
        run_id = slot_timeline._run_for(conn, dataset_id, supply)
        if not run_id:
            continue
        ack = conn.execute(
            f"SELECT actor, reason, effective_at FROM {decision_log.TABLE} "
            "WHERE dataset_id = ? AND action = ? AND supply = ? AND to_slot = ? "
            "ORDER BY effective_at, id LIMIT 1",
            [dataset_id, decision_log.ACKNOWLEDGE, supply, slot]).fetchall()
        promoted = _iso(promoted_at)
        # WHEN IT LEFT ITS PERIOD: the first change to the slot after this
        # promotion that no longer names this supply.
        lapsed = next((e["at"] for e in timeline
                       if e["slot"] == slot and e["at"] > promoted
                       and e["supply"] != supply), None)
        out[run_id] = {
            "supply": supply, "period": slot, "promotedAt": promoted,
            "acknowledged": _acknowledged(ack[0]) if ack else None,
            "lapsedAt": lapsed,
        }
    return out
