"""Mark a closed period as not supplied, and read the mark back
(REQ-PIPE-132 criteria 4 to 10).

A SLOT THAT CLOSED WITH NOTHING IN IT CAN NO LONGER BE FILLED
AUTOMATICALLY: a file arriving now is filed to the open period, not to
this one (REQ-PIPE-131). So a person has three things they can do about
it - substitute an earlier period's supply, re-file a late file into it,
or accept that it was not supplied - and this module is the third.

IT CHANGES NO DATA AND DOES NOT FILL THE SLOT (criterion 7). It is a
decision-log entry that annotates the slot: qa.slot_holds lists only the
decisions that change what a slot holds, so a mark is invisible there by
construction (criterion 8), and a later re-file or substitution simply
supersedes it in what the slot reads as, the mark staying in history.

ONLY A CLOSED, UNFILLED SLOT may be marked (criterion 6). While a slot is
open a file arriving for it is still filed there, and a mark could not
stop that; a slot with a supply awaiting a decision is waiting for a
person to decide THAT supply, not for an acceptance that none came
(criterion 3).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from qa_tools.common import decision_log, supply_db


@dataclass(frozen=True)
class Mark:
    """A person's acceptance that a period was not supplied."""

    dataset_id: str
    period: str
    actor: str
    reason: str
    effective_at: str
    decision_id: int


def _slot(dataset_id: str, period: str, at: datetime):
    from qa_tools.common import slots as slots_mod

    return next((s for s in slots_mod.slots_for_dataset(
        dataset_id, until=slots_mod.claimable_until(dataset_id, at.date()))
        if s.name == period), None)


def marked(conn: supply_db.SupplyConnection, dataset_id: str, period: str,
           as_at: str | None = None) -> Mark | None:
    """The mark this period carries as at `as_at` (or now), or None.

    A MARK STANDS ONLY UNTIL THE SLOT IS NEXT CHANGED: a mark recorded
    BEFORE the latest decision that changed the slot - a later re-file or
    substitution, say - is history, and the slot reads as that decision
    says.
    """
    rows = conn.execute(
        f"SELECT id, actor, reason, effective_at FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND action = ? AND to_slot = ? "
        "AND (CAST(? AS timestamptz) IS NULL OR effective_at <= CAST(? AS timestamptz)) "
        "ORDER BY effective_at DESC, id DESC LIMIT 1",
        [dataset_id, decision_log.MARK_NOT_SUPPLIED, period, as_at, as_at]).fetchall()
    if not rows:
        return None
    decision_id, actor, reason, effective_at = rows[0]
    h = decision_log.held(conn, dataset_id, period, as_at=as_at)
    if h and h.decision_id is not None:
        changed = conn.execute(
            f"SELECT effective_at, id FROM {decision_log.TABLE} WHERE id = ?",
            [h.decision_id]).fetchall()
        if changed and (changed[0][0], changed[0][1]) > (effective_at, decision_id):
            return None
        if h.held_as is not None:
            return None
    return Mark(dataset_id=dataset_id, period=period, actor=actor, reason=reason or "",
                effective_at=effective_at.isoformat() if hasattr(effective_at, "isoformat")
                else str(effective_at), decision_id=decision_id)


def mark(conn: supply_db.SupplyConnection, *, agency_id: str, collection_id: str,
         dataset_id: str, period: str, actor: str, reason: str,
         effective_at: str) -> int:
    """Record that a closed, unfilled period was not supplied. Refuses,
    naming the fix as a command a person can paste, where the slot is not
    closed and unfilled (criterion 6)."""
    from qa_tools.common import asset_time, filing

    at = asset_time.parse_instant(effective_at, "effective_at")
    slot = _slot(dataset_id, period, at)
    if slot is None:
        raise decision_log.DecisionRefused(
            f"{period} is not a period {dataset_id} owes a supply for, so there is "
            f"nothing to mark. `mothman schedule show --dataset {dataset_id}` lists "
            f"the periods it does owe.")
    from qa_tools.common import slots as slots_mod

    if not slots_mod.is_closed(slot, at):
        raise decision_log.DecisionRefused(
            f"{period} is still open for {dataset_id}: a file arriving now would "
            f"still be filed to it, and marking it could not stop that. Wait until "
            f"it closes, or substitute it: `mothman supply decide --operation "
            f"substitute --dataset {dataset_id} --period {period} --stands-on <period>`.")
    h = decision_log.held(conn, dataset_id, period)
    if h and h.held_as is not None:
        # THE UNDO THAT MATCHES HOW IT IS HELD (delivery-critic #105): a
        # substituted or inherited period is undone by removing the
        # indirection, never by demoting the supply it stands on.
        undo = {decision_log.SUBSTITUTED: "de-substitute",
                decision_log.INHERITED: "un-inherit"}.get(h.held_as)
        command = (f"`mothman supply decide --operation {undo} --dataset {dataset_id} "
                   f"--period {period} --reason '<why>'`" if undo else
                   f"`mothman supply decide --operation demote --dataset {dataset_id} "
                   f"--period {period} --supply {h.holder} --reason '<why>'`")
        raise decision_log.DecisionRefused(
            f"{period} is {h.held_as} for {dataset_id}, so it is answered. To take "
            f"that back out: {command}.")
    # ANY SUPPLY FILED HERE THAT NOBODY REJECTED is waiting for a decision
    # (criteria 3 and 6) - including a resupply filed after an earlier
    # supply was rejected, which the first cut let through because a
    # decision existed (delivery-critic #105). Each command is pasteable.
    from qa_tools.common import slot_state

    awaiting = [f for f in filing.filings_of(dataset_id) if f.get("slot") == period
                and not slot_state._rejected(conn, dataset_id, f.get("supply_id"))]
    if awaiting:
        supply = awaiting[-1].get("supply_id")
        raise decision_log.DecisionRefused(
            f"{period} has a supply waiting for a decision ({supply}), so it is not "
            f"unsupplied - decide that supply instead: `mothman supply decide "
            f"--operation promote --dataset {dataset_id} --period {period} "
            f"--supply {supply} --reason '<why>'`, or the same with `--operation "
            f"reject`.")
    decision = decision_log.Decision(
        agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
        action=decision_log.MARK_NOT_SUPPLIED, supply="", actor=actor,
        actor_kind=decision_log.PERSON, effective_at=effective_at, to_slot=period,
        reason=reason)
    with decision_log.apply_decision(conn, decision) as entry_id:
        return entry_id
