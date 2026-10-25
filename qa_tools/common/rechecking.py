"""A person's re-check of a supply (REQ-PIPE-164): what may be re-checked,
the refusal where it may not, and recording it with the owed re-check it
causes. The run itself is recheck.py's - the one executor (REQ-PIPE-140).

ONLY A SUPPLY FILED AND WAITING, OR FILED AND PROMOTED (criterion 10; Keith,
2026-10-14, 164-B): a held, rejected or superseded supply is refused, naming
the decision that would bring it back to where it can be re-checked. Nor one
file of an open contested pair (criterion 22 - filing_decisions refuses those
before this is asked), nor a dataset the agreement backstop refuses
(criterion 23).
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import decision_log

WAITING = "waiting"
PROMOTED = "promoted"


@dataclass(frozen=True)
class Standing:
    """Where a re-checkable supply is: its filed period, and whether it is
    waiting there or promoted into it."""

    period: str
    state: str


def _flag(operation: str, dataset_id: str, period: str, supply: str) -> str:
    return (f"  mothman supply decide --operation {operation} --dataset {dataset_id} "
            f"--period {period} --supply {supply} --reason '<why>'")


def standing(conn, dataset_id: str, supply: str, period: str | None = None) -> Standing:
    """Where this supply may be re-checked, or DecisionRefused saying why it
    may not and what would bring it back - nothing recorded either way."""
    from qa_tools.common import filing, filing_decisions, refiling, supersession, supply_holds

    rows = conn.execute(
        f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, supply]).fetchall()
    if not rows:
        raise decision_log.DecisionRefused(
            f"{supply} is not filed to any period of {dataset_id}, so there is nothing to "
            f"re-check. `mothman supply queue` lists what is waiting. Nothing was recorded.")
    where = rows[0][0]
    if where is None:
        held = supply_holds.hold_on(conn, dataset_id, supply)
        raise decision_log.DecisionRefused(
            f"{supply} is held - it is filed to no period - so there is no period to "
            f"re-check it against. Nothing was recorded.\n"
            + filing_decisions.held_responses(dataset_id, supply, held))
    if supersession.is_superseded(conn, dataset_id, supply):
        raise decision_log.DecisionRefused(
            f"{supply} is superseded, so it is out of {where}'s queue and is not re-checked "
            f"there. Bring it back first, then re-check it. Nothing was recorded.\n"
            + _flag("un-supersede", dataset_id, where, supply))
    if (supersession._rejected(conn, dataset_id, supply)
            and not refiling._since_unrejected(conn, dataset_id, supply)):
        raise decision_log.DecisionRefused(
            f"{supply} is rejected, so it is not re-checked: its table is out of staging. "
            f"Promoting it is the decision that brings it back - then it can be re-checked. "
            f"Nothing was recorded.\n" + _flag("promote", dataset_id, where, supply))
    if period is not None and period != where:
        raise decision_log.DecisionRefused(
            f"{supply} is filed to {where}, not {period}, and is re-checked where it is "
            f"filed. Nothing was recorded.\n" + _flag("re-check", dataset_id, where, supply))
    if decision_log.promoted_into(conn, dataset_id, where) == supply:
        return Standing(where, PROMOTED)
    if not filing_decisions._staged(conn, dataset_id, supply):
        raise decision_log.DecisionRefused(
            f"{supply} has no table in staging - it could not be loaded - so there is "
            f"nothing to re-check. Reject it, or fix the fault and reprocess the delivery. "
            f"Nothing was recorded.")
    return Standing(where, WAITING)


def refuse_a_backstopped_dataset(conn, dataset_id: str) -> None:
    """Criterion 23: REQ-PIPE-173's own finding for the dataset, its
    paste-ready fix, and that the re-check can be raised again once the
    correction is declared - as REQ-PIPE-163 criterion 35 says for a
    placement."""
    from qa_tools.common import agreement_drift

    try:
        refused = agreement_drift.refusal_for(conn, dataset_id)
    except Exception:  # noqa: BLE001 - an unevaluable backstop refuses nothing
        refused = None
    if refused is None:
        return
    raise decision_log.DecisionRefused(
        f"{dataset_id}'s judged past changed without a declared correction, so nothing is "
        f"re-checked for it until that is put right. Nothing was recorded.\n"
        + refused.message()
        + "\nThe re-check can be raised again once the correction is declared.")


def record(conn, *, agency_id: str, collection_id: str, dataset_id: str, supply: str,
           period: str, actor: str, reason: str, effective_at: str) -> int:
    """The re-check decision and the owed re-check it causes, in the
    caller's transaction (criteria 2 and 3) - nothing run here. Returns the
    owed re-check's id."""
    from qa_tools.common import recheck

    with decision_log.apply_decision(conn, decision_log.Decision(
            agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
            action=decision_log.RECHECK, supply=supply, actor=actor,
            actor_kind=decision_log.PERSON, effective_at=effective_at,
            to_slot=period, reason=reason)) as decision_id:
        return recheck.owe(conn, dataset_id=dataset_id, supply_id=supply,
                           decision_id=decision_id)


#: Worse is further down this list (criterion 15).
_RANK = {"green": 0, "amber": 1, "red": 2}


def is_worse(promoted_on: str | None, now: str | None) -> bool:
    """Whether `now` is worse than the verdict a supply was promoted on, by
    this module's one ranking (criterion 15); False where either is unknown."""
    return promoted_on in _RANK and now in _RANK and _RANK[now] > _RANK[promoted_on]


def promoted_on(conn, dataset_id: str, period: str) -> str | None:
    """The status the supply holding `period` was promoted on, or None."""
    holds = decision_log.held(conn, dataset_id, period)
    if not holds or holds.held_as != decision_log.PROMOTED:
        return None
    rows = conn.execute(f"SELECT promoted_status FROM {decision_log.TABLE} WHERE id = ?",
                        [holds.decision_id]).fetchall()
    return rows[0][0] if rows else None


@dataclass(frozen=True)
class Worse:
    """A promoted supply whose re-check came back worse than the verdict it
    was promoted on, with nobody having acknowledged or demoted it since
    (criterion 15)."""

    dataset_id: str
    supply: str
    period: str
    #: The promote decision's recorded promoted_status.
    promoted_on: str
    now: str
    #: The re-check that found it.
    recheck_id: int
    recheck_at: str


def worse_than_promoted(conn, dataset_id: str | None = None,
                        supply: str | None = None) -> list[Worse]:
    """Every promoted supply re-checked worse than it was promoted on, and
    not since acknowledged (REQ-PIPE-122 criterion 14 as amended by this
    requirement's criterion 21) or demoted - in which case the period no
    longer holds it. One query for the candidates: only supplies a person
    has ever re-checked can be on the list."""
    from qa_tools.common import recheck, supply_status

    # THE NEWEST RE-CHECK THAT HAS RUN (post-build-review #199 F8, Keith
    # 2026-10-15): what it found stands until a newer re-check says otherwise,
    # as _manifest reads it - one still owed does not take the supply off the
    # list. Until any has run, its verdict is from before them (#192 F2).
    rows = conn.execute(
        f"SELECT DISTINCT ON (d.dataset_id, d.supply) d.dataset_id, d.supply, d.to_slot, d.id, "
        f"d.effective_at FROM {decision_log.TABLE} d WHERE d.action = ? "
        "AND (?::text IS NULL OR d.dataset_id = ?) AND (?::text IS NULL OR d.supply = ?) "
        f"AND EXISTS (SELECT 1 FROM {recheck.TABLE} o WHERE o.caused_by_decision = d.id "
        "AND o.cleared_at IS NOT NULL) "
        "ORDER BY d.dataset_id, d.supply, d.id DESC",
        [decision_log.RECHECK, dataset_id, dataset_id, supply, supply]).fetchall()
    out = []
    for ds, held_supply, period, recheck_id, at in rows:
        holds = decision_log.held(conn, ds, period)
        if not holds or holds.held_as != decision_log.PROMOTED or holds.holder != held_supply:
            continue
        (promote_id, promoted_on), = conn.execute(
            f"SELECT id, promoted_status FROM {decision_log.TABLE} WHERE id = ?",
            [holds.decision_id]).fetchall()
        if promoted_on not in _RANK or promote_id > recheck_id:
            continue
        # A STANDING ACKNOWLEDGEMENT SINCE (REQ-PIPE-166 criterion 9): one
        # withdrawn lists it again.
        from qa_tools.common import withdrawal

        acknowledged = conn.execute(
            f"SELECT 1 FROM {decision_log.TABLE} d WHERE d.action = ? AND d.dataset_id = ? "
            f"AND d.supply = ? AND d.to_slot = ? AND d.id > ? AND "
            f"{withdrawal.not_withdrawn('d', as_at_param=False)} LIMIT 1",
            [decision_log.ACKNOWLEDGE, ds, held_supply, period, recheck_id]).fetchall()
        if acknowledged:
            continue
        try:
            now = supply_status.status(conn, ds, held_supply)
        except Exception:  # noqa: BLE001 - an unreadable verdict is not "worse"
            continue
        if now == "red" and supply_status.red_only_for_recheck_owed(conn, ds, held_supply):
            # AN OWED RE-CHECK IS NEVER 'RE-CHECKED WORSE' (REQ-PIPE-276
            # criterion 14; #113): it clears by itself on the next pass.
            continue
        if is_worse(promoted_on, now):
            out.append(Worse(ds, held_supply, period, promoted_on, now, recheck_id,
                             at.isoformat() if hasattr(at, "isoformat") else str(at)))
    return out


def worse_for(conn, dataset_id: str, supply: str, period: str) -> Worse | None:
    """This supply's entry on that list, in that period, or None - read for
    every promoted slot a state is worked out for, so asked about the one
    supply: a supply never re-checked costs one lookup."""
    return next((w for w in worse_than_promoted(conn, dataset_id, supply)
                 if w.supply == supply and w.period == period), None)
