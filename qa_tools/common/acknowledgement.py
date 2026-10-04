"""Whether a promoted amber supply owes an acknowledgement, and whether it
has one (REQ-PIPE-122 criteria 11 and 13 to 16).

OWED BY WHAT THE PROMOTION RECORDED, never by the setting in force now
(criterion 5): a promotion taken under promote-and-acknowledge carries that
value on its own decision-log entry (`acknowledgement_owed`, derived in the
table from the recorded value), and a later change to the setting changes
nothing about it.

LAPSED, NOT OUTSTANDING, ONCE THE SUPPLY LEAVES ITS PERIOD (criterion 16):
an acknowledgement is owed only while the supply is still what that period
holds. Superseded, demoted, rejected or re-filed - qa.slot_holds stops
naming it and the debt goes with it, with nothing to clear.

AN ACKNOWLEDGEMENT CHANGES NOTHING (criterion 15): it is a decision-log
entry that annotates the slot, read here and by nobody that resolves a
period.
"""
from __future__ import annotations

from qa_tools.common import decision_log, supply_db


def _promotion(conn, dataset_id: str, supply: str, slot: str, as_at: str | None):
    """The decision that put `supply` into `slot`, if it is still there."""
    h = decision_log.held(conn, dataset_id, slot, as_at=as_at)
    if not h or h.held_as != decision_log.PROMOTED or h.holder != supply:
        return None
    rows = conn.execute(
        f"SELECT id, effective_at, acknowledgement_owed, amber_setting FROM "
        f"{decision_log.TABLE} WHERE id = ?", [h.decision_id]).fetchall()
    return rows[0] if rows else None


def acknowledged_by(conn, dataset_id: str, supply: str, slot: str,
                    as_at: str | None = None) -> dict | None:
    """The acknowledgement this promotion has, or None."""
    rows = conn.execute(
        f"SELECT actor, reason, effective_at FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND action = ? AND supply = ? AND to_slot = ? "
        "AND (CAST(? AS timestamptz) IS NULL OR effective_at <= CAST(? AS timestamptz)) "
        "ORDER BY effective_at, id LIMIT 1",
        [dataset_id, decision_log.ACKNOWLEDGE, supply, slot, as_at, as_at]).fetchall()
    if not rows:
        return None
    actor, reason, at = rows[0]
    return {"actor": actor, "reason": reason or "",
            "at": at.isoformat() if hasattr(at, "isoformat") else str(at)}


def why_not_owed(conn: supply_db.SupplyConnection, dataset_id: str, supply: str,
                 slot: str | None) -> str | None:
    """None where `supply` owes an acknowledgement in `slot`; otherwise the
    reason it does not, in words a person can act on (criterion 14)."""
    if not slot:
        return "no period was named"
    found = _promotion(conn, dataset_id, supply, slot, None)
    if found is None:
        from qa_tools.common import slot_state

        if slot_state._amber_waiting(conn, dataset_id, supply):
            # THE CASE A LEAD IS LIKELIEST TO HIT (#107): "it's amber, I've
            # looked" - under hold the answer is to promote it.
            return (f"it is amber and waiting under the amber setting 'hold', not promoted - "
                    f"to accept it, promote it: `mothman supply decide --operation promote "
                    f"--dataset {dataset_id} --period {slot} --supply {supply} "
                    f"--reason '<why>'`")
        from qa_tools.common import hierarchy

        collection = hierarchy.dataset(dataset_id).collection_id
        return (f"it is not the supply promoted into {slot} - an acknowledgement is "
                f"for a promoted amber supply, and only while it is still in its period. "
                f"`mothman supply slots --collection {collection} --dataset {dataset_id}` "
                f"shows what {slot} holds")
    _, _, owed, setting = found
    if not owed:
        if setting is None:
            return ("it was not promoted as an amber supply under promote-and-acknowledge "
                    "- either it was not amber, or a person promoted it")
        return f"it was promoted under the amber setting '{setting}', which asks for none"
    done = acknowledged_by(conn, dataset_id, supply, slot)
    if done:
        return (f"it is already acknowledged, by {done['actor']} at {done['at']} - "
                f"`mothman supply decisions --dataset {dataset_id}` shows it")
    return None


def owed(conn: supply_db.SupplyConnection, dataset_id: str, slot: str,
         as_at: str | None = None) -> str | None:
    """The supply in `slot` that owes an acknowledgement as at `as_at`, or
    None - including where one was owed and has lapsed (criterion 16)."""
    h = decision_log.held(conn, dataset_id, slot, as_at=as_at)
    if not h or h.held_as != decision_log.PROMOTED:
        return None
    found = _promotion(conn, dataset_id, h.holder, slot, as_at)
    if not found or not found[2]:
        return None
    if acknowledged_by(conn, dataset_id, h.holder, slot, as_at):
        return None
    return h.holder
