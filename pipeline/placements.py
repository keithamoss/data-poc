"""Every supply a PERSON placed into a period, for the dashboard (REQ-DASH-175).

A placement is recorded as a person's re-file from no period (REQ-PIPE-163
criterion 2): the decision log's own record, read here and nowhere else. The
rule's re-file from no period - a held supply filed once configuration
covered it, or by a confirmed correction - is not a placement and is left
out (criterion 9).

THE ANSWERS TRAVEL, NOT THE RULE: who, when and why, the period, and whether
that period was closed or not yet open when the supply arrived - worked out
from the slot's own instants (REQ-PIPE-131), never in the page.

RECORDED QA METADATA ONLY (criterion 8): qa.decision and qa.supply_receipt.
"""
from __future__ import annotations

from qa_tools.common import decision_log, supply_db


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def placed_in(action: str, actor_kind: str, from_slot, to_slot) -> str | None:
    """The period a decision PLACED its supply into - a person's re-file from
    no period (REQ-PIPE-163 criterion 2) - or None for any other decision,
    the rule's re-file from no period included (REQ-DASH-175 criteria 7, 9)."""
    if action == decision_log.REFILE and actor_kind == decision_log.PERSON and not from_slot:
        return to_slot
    return None


def when_received(slot, received_at) -> str | None:
    """'closed' or 'not-yet-open' where the slot was so at `received_at`,
    else None (criterion 2)."""
    if slot is None or received_at is None:
        return None
    if slot.closes_at is not None and slot.closes_at <= received_at:
        return "closed"
    if slot.claim_opens_at > received_at:
        return "not-yet-open"
    return None


def for_dataset(dataset_id: str,
                conn: supply_db.SupplyConnection | None = None) -> dict[str, dict]:
    """{supply: {period, at, actor, reason, when, runId, until}} for each
    supply a person placed - the newest placement where there is more than
    one; `until` is when a later re-file moved it out, else None."""
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:placements") as opened:
            return for_dataset(dataset_id, opened)
    from qa_tools.common import people, slots

    from pipeline import slot_timeline

    out: dict[str, dict] = {}
    rows = conn.execute(
        f"SELECT d.supply, d.to_slot, d.effective_at, d.actor, d.reason, r.received_instant "
        f"FROM {decision_log.TABLE} d LEFT JOIN qa.supply_receipt r "
        "ON r.dataset_id = d.dataset_id AND r.supply_id = d.supply "
        "WHERE d.dataset_id = ? AND d.action = ? AND d.actor_kind = ? AND d.from_slot IS NULL "
        "AND d.supply IS NOT NULL AND d.to_slot IS NOT NULL ORDER BY d.effective_at, d.id",
        [dataset_id, decision_log.REFILE, decision_log.PERSON]).fetchall()
    for supply, period, at, actor, reason, received in rows:
        # slot_named answers None for a period no calendar knows, so nothing
        # needs catching here (post-build-review #196 F6): a real failure
        # should surface, not quietly drop the closed / not-yet-open line.
        slot = slots.slot_named(dataset_id, period)
        out[supply] = {"period": period, "at": _iso(at), "actor": people.display_name(actor),
                       "reason": reason or "", "when": when_received(slot, received),
                       "runId": slot_timeline._run_for(conn, dataset_id, supply),
                       "until": _moved_out(conn, dataset_id, supply, period, at)}
    return out


def _moved_out(conn, dataset_id: str, supply: str, period: str, at) -> str | None:
    """The instant a later re-file moved the supply out of the period it was
    placed in, or None while it is still there (post-build-review #196 F4) -
    an answer the page compares with the date on show, so the tag still
    reads on every date before the move."""
    row = conn.execute(
        f"SELECT min(effective_at) FROM {decision_log.TABLE} WHERE dataset_id = ? AND supply = ? "
        "AND action = ? AND from_slot = ? AND effective_at > ?",
        [dataset_id, supply, decision_log.REFILE, period, at]).fetchone()
    return _iso(row[0]) if row and row[0] is not None else None
