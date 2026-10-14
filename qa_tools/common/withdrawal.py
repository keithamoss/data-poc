"""Withdrawing an acknowledgement or a mark as not supplied (REQ-PIPE-166).

A WITHDRAWAL IS ITS OWN ENTRY naming the entry withdrawn by its id, in the
decision table's `caused_by_decision` (criterion 2); the entry withdrawn is
never deleted or altered, so the log reads what was recorded and then what
was taken back. Every reader of the annotation asks this module, or the
`NOT EXISTS` it builds, whether the entry still stands (criterion 11).

ON THE SAME TERMS AS WITHDRAWING AN EXCUSE (REQ-PIPE-161 criterion 8): any
identified person, with a reason.
"""
from __future__ import annotations

from qa_tools.common import decision_log


def not_withdrawn(alias: str = "d", as_at_param: bool = True) -> str:
    """A SQL condition: the entry `alias` has no withdrawal (as at the next
    parameter, an instant or NULL) - the one definition every reader uses."""
    when = (" AND (CAST(? AS timestamptz) IS NULL OR w.effective_at <= CAST(? AS timestamptz))"
            if as_at_param else "")
    return (f"NOT EXISTS (SELECT 1 FROM {decision_log.TABLE} w WHERE w.caused_by_decision = "
            f"{alias}.id AND w.action IN ('{decision_log.WITHDRAW_ACKNOWLEDGEMENT}', "
            f"'{decision_log.WITHDRAW_NOT_SUPPLIED}'){when})")


def standing_acknowledgement(conn, dataset_id: str, supply: str, slot: str,
                             as_at: str | None = None):
    """(id, actor, reason, effective_at) of the acknowledgement standing for
    this supply in this period as at `as_at` - the NEWEST not withdrawn
    (criterion 17) - or None."""
    rows = conn.execute(
        f"SELECT d.id, d.actor, d.reason, d.effective_at FROM {decision_log.TABLE} d "
        "WHERE d.dataset_id = ? AND d.action = ? AND d.supply = ? AND d.to_slot = ? "
        "AND (CAST(? AS timestamptz) IS NULL OR d.effective_at <= CAST(? AS timestamptz)) "
        f"AND {not_withdrawn('d')} "
        "ORDER BY d.effective_at DESC, d.id DESC LIMIT 1",
        [dataset_id, decision_log.ACKNOWLEDGE, supply, slot, as_at, as_at,
         as_at, as_at]).fetchall()
    return rows[0] if rows else None


def target(conn, decision) -> int | None:
    """The id of the standing entry this withdrawal withdraws, or None."""
    if decision.action == decision_log.WITHDRAW_ACKNOWLEDGEMENT:
        found = standing_acknowledgement(conn, decision.dataset_id, decision.supply or "",
                                         decision.to_slot)
        return found[0] if found else None
    from qa_tools.common import not_supplied

    mark = not_supplied.marked(conn, decision.dataset_id, decision.to_slot)
    return mark.decision_id if mark else None


def why_not(conn, decision) -> str | None:
    """None where `decision` withdraws the standing entry it names; otherwise
    why not (criterion 5)."""
    if decision.action == decision_log.WITHDRAW_ACKNOWLEDGEMENT and not decision.supply:
        return ("withdrawing an acknowledgement names no supply - say which supply's "
                "acknowledgement to withdraw. Nothing was recorded.")
    found = target(conn, decision)
    if found is None:
        if decision.action == decision_log.WITHDRAW_ACKNOWLEDGEMENT:
            return (f"{decision.supply} has no acknowledgement standing in "
                    f"{decision.to_slot} to withdraw - it was never acknowledged there, or "
                    f"its acknowledgement was already withdrawn. Nothing was recorded.")
        return (f"{decision.to_slot} carries no mark as not supplied for "
                f"{decision.dataset_id} to withdraw - it was never marked, the mark was "
                f"already withdrawn, or a later decision has since filled the period. Nothing "
                f"was recorded.")
    if decision.caused_by_decision != found:
        return (f"the entry named ({decision.caused_by_decision}) is not the one standing "
                f"({found}). Nothing was recorded.")
    return None


def record(conn, *, operation: str, agency_id: str, collection_id: str, dataset_id: str,
           period: str, supply: str | None, actor: str, reason: str,
           effective_at: str) -> int:
    """The withdrawal, naming the standing entry by its id (criterion 2). In
    the caller's transaction; refused by the log where nothing stands."""
    probe = decision_log.Decision(
        agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
        action=operation, supply=supply or "", actor=actor,
        actor_kind=decision_log.PERSON, effective_at=effective_at, to_slot=period,
        reason=reason)
    found = target(conn, probe)
    if found is None:
        raise decision_log.DecisionRefused(why_not(conn, probe))
    from dataclasses import replace

    with decision_log.apply_decision(conn, replace(probe, caused_by_decision=found)) as wid:
        return wid


def _when(at) -> str:
    """An instant on the asset clock - from a datetime or its isoformat
    (a mark carries the string; post-build-review #193 F2)."""
    from datetime import datetime

    from qa_tools.common import asset_time

    if isinstance(at, str):
        try:
            at = datetime.fromisoformat(at)
        except ValueError:
            return at
    when = asset_time.localise(at) if hasattr(at, "tzinfo") else at
    return when.strftime("%-d %b %Y %H:%M") if hasattr(when, "strftime") else str(when)


def consequence_words(conn, request) -> list[str]:
    """What the person confirms (criterion 14): the entry withdrawn - who
    recorded it, when and why - its public consequence, and that it can be
    recorded again. Refuses, before anything is asked, where nothing stands
    (criterion 5)."""
    from qa_tools.common import acknowledgement, not_supplied, people

    probe = decision_log.Decision(
        agency_id="", collection_id="", dataset_id=request.dataset_id,
        action=request.operation, supply=request.supply or "", actor="",
        actor_kind=decision_log.PERSON, effective_at="", to_slot=request.period, reason="")
    if target(conn, probe) is None:
        raise decision_log.DecisionRefused(why_not(conn, probe))
    if request.operation == decision_log.WITHDRAW_ACKNOWLEDGEMENT:
        _id, actor, reason, at = standing_acknowledgement(
            conn, request.dataset_id, request.supply, request.period)
        # STILL IN ITS PERIOD, OR LAPSED (#193 F3): only a supply its period
        # still holds owes an acknowledgement again (criterion 4).
        still_held = acknowledgement._promotion(
            conn, request.dataset_id, request.supply, request.period, None) is not None
        follows = (f"{request.supply} needs a person again - it awaits acknowledgement."
                   if still_held else
                   f"{request.supply} is no longer in {request.period}, so it owes no "
                   f"acknowledgement - the withdrawal only corrects the record.")
        return [f"It withdraws the acknowledgement {people.display_name(actor)} recorded "
                f"{_when(at)}: \"{reason or ''}\".",
                f"The page stops showing it from now; it stays in the supply's history; and "
                f"{follows}",
                "An acknowledgement can be recorded again."]
    mark = not_supplied.marked(conn, request.dataset_id, request.period)
    return [f"It withdraws the mark as not supplied {people.display_name(mark.actor)} recorded "
            f"{_when(mark.effective_at)}: \"{mark.reason}\".",
            f"{request.period} reads overdue or never supplied again, and its ticket reopens.",
            "A mark as not supplied can be recorded again."]
