"""Re-filing a supply: back to staging under a new filing for its new
period, where it is checked and the normal gate decides (REQ-PIPE-141).

ONE JUDGEMENT FOR THE MOVE AND ITS WARNING (REQ-GHUB-142 criterion 2):
`plan()` works out every consequence, and both `apply()` and the warning
both routes show are built from it - so what a person confirms is what
happens.

WHAT A RE-FILE DOES, in one transaction (NFR 1):
  - a NEW filing of the supply to the target period, the old one kept as
    history (criteria 1 and 2) - qa.filing is append-only;
  - out of the old period through the one move-out path, its stamped name
    restored, the old slot left unfilled (criterion 3) - or out of the
    old period's superseded schema, or left in staging (criterion 4);
  - every unaccepted version waiting in staging for the target period
    superseded by it, whatever its receipt (criterion 6), each its own
    rule-actor entry;
  - ONE decision-log entry naming both periods and one reason (criterion
    16), and the supply's QA owed again (REQ-PIPE-140 criterion 7).
The QA run is a separate step (NFR 1), so a run that breaks is retried
without re-doing the re-file. A promoted version in the target period is
left where it is until the re-filed supply is promoted (criterion 9); a
substitution there likewise (criterion 13).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qa_tools.common import decision_log, supply_db


@dataclass(frozen=True)
class Displaced:
    """A version the re-file supersedes in the target period."""
    supply: str
    received: str


@dataclass(frozen=True)
class Plan:
    dataset_id: str
    supply: str
    table: str
    from_period: str | None
    to_period: str
    #: Promoted in its old period - so leaving takes that period's answer.
    promoted: bool
    #: Superseded in its old period - so it comes from that period's
    #: superseded schema rather than staging.
    superseded: bool
    received: str
    displaced: list[Displaced] = field(default_factory=list)
    #: What the target period holds now, which stays until the re-filed
    #: supply is promoted (criteria 9 and 13) - for the warning.
    target_holds: str | None = None
    target_held_as: str | None = None


def plan(conn, *, dataset_id: str, supply: str, to_period: str) -> Plan:
    """Every consequence of re-filing `supply` into `to_period`, or a
    DecisionRefused naming what must come first (criteria 5, 10-12)."""
    from qa_tools.common import filing, hierarchy, supersession

    rows = conn.execute(
        f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, supply]).fetchall()
    if not rows:
        raise decision_log.DecisionRefused(
            f"{supply} is not filed for {dataset_id}, so there is nothing to re-file. "
            f"`mothman supply queue` lists what is waiting.")
    from_period = rows[0][0]
    if not from_period:
        # A HELD SUPPLY IS PLACED, NOT RE-FILED (#114, minor): it has no
        # period to leave, and the decision log refused it later with a
        # message about two slots.
        raise decision_log.DecisionRefused(
            f"{supply} is filed to no period - it is held, waiting to be placed - so there "
            f"is nothing to re-file it from. Place it instead; `mothman supply queue` "
            f"shows how.")
    if from_period == to_period:
        raise decision_log.DecisionRefused(f"{supply} is already filed to {to_period}.")
    if "#" in supply.rsplit("@", 1)[-1]:
        # Criterion 11: the contest is per arrival.
        raise decision_log.DecisionRefused(
            f"{supply} is one file of a contested pair. The contest is per arrival, so "
            f"moving one file would not end it - resolve the contest first, by saying "
            f"which file is the supply.")
    if supersession._rejected(conn, dataset_id, supply) and not _since_unrejected(
            conn, dataset_id, supply):
        # Criterion 10.
        raise decision_log.DecisionRefused(
            f"{supply} was rejected. Reverse the rejection first - promote it back into "
            f"{from_period} - and re-file it after:\n"
            f"  mothman supply decide --operation promote --dataset {dataset_id} "
            f"--period {from_period} --supply {supply} --reason '<why>'")
    h = decision_log.held(conn, dataset_id, to_period)
    if h and h.held_as == decision_log.INHERITED:
        # Criterion 12.
        raise decision_log.DecisionRefused(
            f"Nothing was expected from {dataset_id} for {to_period}: it is inherited. "
            f"Un-inherit it first, then re-file:\n"
            f"  mothman supply decide --operation un-inherit --dataset {dataset_id} "
            f"--period {to_period} --reason '<why>' --yes")
    promoted = bool(from_period) and decision_log.promoted_into(
        conn, dataset_id, from_period) == supply
    if promoted:
        # Criterion 5 - every blocking period, and what unblocks each.
        decision_log.refuse_if_stood_on(conn, dataset_id, supply, decision_log.REFILE)
    displaced = [Displaced(s, _received(conn, dataset_id, s))
                 for s in supersession.waiting_in(conn, dataset_id, to_period, besides=supply)]
    return Plan(
        dataset_id=dataset_id, supply=supply, table=hierarchy.dataset(dataset_id).table,
        from_period=from_period, to_period=to_period, promoted=promoted,
        superseded=supersession.is_superseded(conn, dataset_id, supply),
        received=_received(conn, dataset_id, supply), displaced=displaced,
        target_holds=h.holder if h and h.held_as else None,
        target_held_as=h.held_as if h else None)


def apply(conn, p: Plan, *, agency_id: str, collection_id: str, actor: str, reason: str,
          effective_at: str) -> int:
    """Carry a plan out, in one transaction. Returns the owed re-check's id."""
    from qa_tools.common import filing, period_tables, recheck, supersession

    with decision_log.decision_transaction(conn):
        # JUDGED AGAIN UNDER THE LOCK (REQ-GHUB-142 criterion 4; post-build-
        # review #114, D4): the plan the person confirmed was worked out
        # before it, so a version filed into the target since, or a
        # promotion either side, would go unnamed in what they saw. Both
        # slots, in a fixed order so two re-files cannot deadlock.
        for slot in sorted(filter(None, {p.from_period, p.to_period})):
            decision_log.lock_slot(conn, p.dataset_id, slot)
        now = plan(conn, dataset_id=p.dataset_id, supply=p.supply, to_period=p.to_period)
        if _what_it_does(now) != _what_it_does(p):
            raise decision_log.DecisionRefused(
                f"What re-filing {p.supply} would do has changed since it was worked "
                f"out - something was filed or decided for {p.dataset_id} meanwhile. "
                f"Nothing was done; ask again to see the consequences as they stand now.")
        with decision_log.apply_decision(conn, decision_log.Decision(
                agency_id=agency_id, collection_id=collection_id, dataset_id=p.dataset_id,
                action=decision_log.REFILE, supply=p.supply, actor=actor,
                actor_kind=decision_log.PERSON, effective_at=effective_at,
                from_slot=p.from_period, to_slot=p.to_period, reason=reason)) as entry_id:
            if p.promoted:
                # THE ONE MOVE-OUT PATH (criterion 3, NFR 4).
                if period_tables.take_out(conn, period=p.from_period, logical=p.table,
                                          supply=p.supply,
                                          to_schema=supply_db.STAGING_SCHEMA) is None:
                    raise decision_log.DecisionRefused(
                        f"{p.from_period} has no {p.table} for {p.supply}, which the "
                        f"decision log says it holds - nothing was done.")
            elif p.superseded:
                source = supersession.superseded_schema(p.from_period)
                for physical in _tables_in(conn, source, p):
                    supply_db.move_table(conn, physical, source, supply_db.STAGING_SCHEMA)
            filing.refile(conn, p.dataset_id, p.supply, p.to_period, decision_id=entry_id)
            owed_id = recheck.owe(conn, dataset_id=p.dataset_id, supply_id=p.supply,
                                  decision_id=entry_id)
        # RE-FILE WINS over versions waiting in the target (criterion 6),
        # each its own rule-actor entry, in this same transaction.
        for d in p.displaced:
            supersession.supersede_by_rule(
                conn, agency_id=agency_id, collection_id=collection_id,
                dataset_id=p.dataset_id, supply=d.supply, period=p.to_period, by=p.supply,
                effective_at=effective_at,
                reason=f"{p.supply} was re-filed into {p.to_period} in its place")
    return owed_id


def _what_it_does(p: Plan) -> tuple:
    """The parts of a plan a person confirms - what leaves, from where, and
    what it displaces."""
    return (p.from_period, p.promoted, p.superseded,
            tuple(sorted(d.supply for d in p.displaced)))


def _tables_in(conn, schema: str, p: Plan) -> list[str]:
    from qa_tools.common import supply_holds

    key = supply_holds.arrival_key_of(p.supply)
    return list(supply_db.candidates_in(conn, schema, [p.table], arrival=key).get(p.table)
                or [])


def _received(conn, dataset_id: str, supply: str) -> str:
    from qa_tools.common import supersession

    at = supersession._receipt(conn, dataset_id, supply)
    return at.isoformat() if at else ""


def _since_unrejected(conn, dataset_id: str, supply: str) -> bool:
    """Whether a promotion has reversed the rejection since."""
    rows = conn.execute(
        f"SELECT action FROM {decision_log.TABLE} WHERE dataset_id = ? AND supply = ? "
        "AND action IN (?, ?) ORDER BY effective_at DESC, id DESC LIMIT 1",
        [dataset_id, supply, decision_log.REJECT, decision_log.PROMOTE]).fetchall()
    return bool(rows) and rows[0][0] == decision_log.PROMOTE
