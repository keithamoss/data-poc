"""One waiting version per table per period: a newer file supersedes every
earlier unaccepted version (REQ-PIPE-118).

WHAT HAPPENS. When a file for a table is filed to a period, every EARLIER
version of that table filed to the same period that nobody has accepted -
not promoted, not rejected, whatever its verdict - moves to the SUPERSEDED
state before any check runs over the new file (criterion 1). Its tables
leave staging for that period's own `_superseded` schema (criterion 4),
nothing of it is deleted (criterion 9), and the move and its decision-log
entry are one transaction with the filing of the new file (NFR).

EARLIER MEANS RECEIVED EARLIER BY OUR OWN CLOCK (criteria 2 and 3), from
each supply's recorded receipt - never the order files happen to be
processed in, though the pipeline processes in receipt order anyway.

NOT A REJECTION (criterion 11): rejected means a person decided against a
supply; superseded means a later version of the same table for the same
period arrived, which says nothing about this one's quality. A PROMOTED
supply is never superseded here (criterion 12); REQ-PIPE-128 owns that.
A supply a person returned by a demote IS superseded like any other
(decision 13), and everything stays reversible under REQ-PIPE-120.

NO AUTOMATIC RULE BRINGS ONE BACK (criterion 14): the promotion gate asks
`is_superseded()` and refuses.
"""
from __future__ import annotations

from qa_tools.common import decision_log, period_schema, supply_db

#: The suffix a period's superseded schema takes after the period schema's
#: own name (criterion 4), so `period_2026_q2_superseded` sorts directly
#: after `period_2026_q2`.
SUFFIX = period_schema.SUPERSEDED_SUFFIX

#: The rule's own name in the decision log (criterion 10).
RULE_ACTOR = "supersession rule"


def superseded_schema(period: str) -> str:
    return period_schema.period_schema(period) + SUFFIX


def is_superseded_schema(schema: str) -> bool:
    return schema.startswith(period_schema.PERIOD_SCHEMA_PREFIX) and schema.endswith(SUFFIX)


def superseded_by(conn, dataset_id: str, supply: str) -> str | None:
    """The supply that superseded this one, where it stands superseded -
    the latest supersession of it not undone by a later un-supersede."""
    rows = conn.execute(
        f"SELECT action, superseded_by FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND supply = ? AND action IN (?, ?) "
        "ORDER BY effective_at DESC, id DESC LIMIT 1",
        [dataset_id, supply, decision_log.SUPERSEDE, decision_log.UN_SUPERSEDE]).fetchall()
    if not rows or rows[0][0] != decision_log.SUPERSEDE:
        return None
    return rows[0][1]


def is_superseded(conn, dataset_id: str, supply: str) -> bool:
    return superseded_by(conn, dataset_id, supply) is not None


def _receipt(conn, dataset_id: str, supply: str):
    rows = conn.execute(
        "SELECT received_instant FROM qa.supply_receipt WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, supply]).fetchall()
    return rows[0][0] if rows else None


def _rejected(conn, dataset_id: str, supply: str) -> bool:
    return bool(conn.execute(
        f"SELECT 1 FROM {decision_log.TABLE} WHERE dataset_id = ? AND supply = ? "
        "AND action = ? LIMIT 1", [dataset_id, supply, decision_log.REJECT]).fetchall())


def _ever_promoted_and_still_held(conn, dataset_id: str, supply: str, period: str) -> bool:
    h = decision_log.held(conn, dataset_id, period)
    return bool(h and h.held_as is not None and h.holder == supply)


def staged_tables(conn, dataset_id: str, supply: str) -> list[str]:
    """This supply's physical tables in staging."""
    from qa_tools.common import hierarchy, supply_holds

    logical = hierarchy.dataset(dataset_id).table
    key = supply_holds.arrival_key_of(supply)
    return list(supply_db.candidates_in(
        conn, supply_db.STAGING_SCHEMA, [logical], arrival=key).get(logical) or [])


def earlier_unaccepted(conn, dataset_id: str, period: str, newer: str) -> list[str]:
    """Every earlier version of this dataset's table filed to `period` that
    nobody has accepted, oldest first (criteria 1, 2 and 12)."""
    newer_at = _receipt(conn, dataset_id, newer)
    if newer_at is None:
        return []
    out = []
    for (supply,) in conn.execute(
            "SELECT supply_id FROM qa.filing WHERE dataset_id = ? AND slot = ? "
            "AND supply_id <> ?", [dataset_id, period, newer]).fetchall():
        at = _receipt(conn, dataset_id, supply)
        if at is None or at >= newer_at:
            continue
        if (_rejected(conn, dataset_id, supply) or is_superseded(conn, dataset_id, supply)
                or _ever_promoted_and_still_held(conn, dataset_id, supply, period)):
            continue
        out.append((at, supply))
    return [s for _, s in sorted(out)]


def supersede_earlier(conn, *, agency_id: str, collection_id: str, dataset_id: str,
                      period: str, newer: str, effective_at: str) -> list[str]:
    """Supersede every earlier unaccepted version of this table in `period`
    by `newer`. Returns the supplies superseded. Each is its own decision
    with the rule as actor, its tables moved in the same transaction
    (criterion 10); the caller wraps this with the filing."""
    done = []
    for supply in earlier_unaccepted(conn, dataset_id, period, newer):
        target = superseded_schema(period)
        tables = staged_tables(conn, dataset_id, supply)
        decision = decision_log.Decision(
            agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
            action=decision_log.SUPERSEDE, supply=supply, actor=RULE_ACTOR,
            actor_kind=decision_log.RULE, effective_at=effective_at, from_slot=period,
            reason=f"a newer version of this table for {period} arrived: {newer}",
            superseded_by=newer)
        with decision_log.apply_decision(conn, decision):
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{target}"')
            for physical in tables:
                supply_db.move_table(conn, physical, supply_db.STAGING_SCHEMA, target)
        done.append(supply)
    return done


def drop_if_empty(conn, period: str) -> bool:
    """Drop a period's superseded schema once its last table has left
    (criterion 5). Returns True where it dropped one."""
    target = superseded_schema(period)
    exists = conn.execute(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = ?", [target]).fetchall()
    if not exists:
        return False
    if conn.execute("SELECT 1 FROM information_schema.tables WHERE table_schema = ? LIMIT 1",
                    [target]).fetchall():
        return False
    conn.execute(f'DROP SCHEMA "{target}"')
    return True


# ---- a person's own decisions (REQ-PIPE-120) ------------------------------

def superseded_in(conn, dataset_id: str, period: str) -> list[dict]:
    """The superseded versions of this dataset's table for `period`, newest
    first - each with what superseded it (criterion 7)."""
    out = []
    for (supply,) in conn.execute(
            "SELECT f.supply_id FROM qa.filing f JOIN qa.supply_receipt r "
            "ON r.dataset_id = f.dataset_id AND r.supply_id = f.supply_id "
            "WHERE f.dataset_id = ? AND f.slot = ? ORDER BY r.received_instant DESC",
            [dataset_id, period]).fetchall():
        by = superseded_by(conn, dataset_id, supply)
        if by is not None:
            out.append({"supply": supply, "superseded_by": by,
                        "received": _receipt(conn, dataset_id, supply)})
    return out


def waiting_in(conn, dataset_id: str, period: str, *, besides: str | None = None) -> list[str]:
    """Versions of this table filed to `period` that are still WAITING -
    not promoted, rejected or superseded (criterion 5's refusal)."""
    out = []
    for (supply,) in conn.execute(
            "SELECT supply_id FROM qa.filing WHERE dataset_id = ? AND slot = ?",
            [dataset_id, period]).fetchall():
        if supply == besides:
            continue
        if (_rejected(conn, dataset_id, supply) or is_superseded(conn, dataset_id, supply)
                or _ever_promoted_and_still_held(conn, dataset_id, supply, period)):
            continue
        out.append(supply)
    return out


def supersede(conn, *, agency_id: str, collection_id: str, dataset_id: str, supply: str,
              period: str, actor: str, reason: str, effective_at: str) -> None:
    """A PERSON supersedes a waiting supply (criterion 2): its tables move to
    the period's superseded schema, with that person as actor."""
    from qa_tools.common import decision_log as dl

    if is_superseded(conn, dataset_id, supply):
        raise dl.DecisionRefused(f"{supply} is already superseded.")
    if _rejected(conn, dataset_id, supply):
        raise dl.DecisionRefused(f"{supply} was rejected; there is nothing waiting to supersede.")
    if _ever_promoted_and_still_held(conn, dataset_id, supply, period):
        raise dl.DecisionRefused(
            f"{supply} is promoted into {period}; superseding a promoted supply is "
            f"REQ-PIPE-128's, through promoting the one that replaces it.")
    target = superseded_schema(period)
    tables = staged_tables(conn, dataset_id, supply)
    with dl.apply_decision(conn, dl.Decision(
            agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
            action=dl.SUPERSEDE, supply=supply, actor=actor, actor_kind=dl.PERSON,
            effective_at=effective_at, from_slot=period, reason=reason)):
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{target}"')
        for physical in tables:
            supply_db.move_table(conn, physical, supply_db.STAGING_SCHEMA, target)


def un_supersede(conn, *, agency_id: str, collection_id: str, dataset_id: str, supply: str,
                 period: str, actor: str, reason: str, effective_at: str) -> None:
    """A PERSON returns a superseded supply to staging for its period
    (criterion 3), refused while another version of the table is waiting
    there (criterion 5). Its QA is owed again; the gate then applies as for
    a first arrival (criterion 4)."""
    from qa_tools.common import decision_log as dl
    from qa_tools.common import hierarchy, supply_holds

    if not supply:
        raise dl.DecisionRefused(
            "an un-supersede names which superseded version - there is no default. "
            "`mothman supply superseded` lists them.")
    if not is_superseded(conn, dataset_id, supply):
        raise dl.DecisionRefused(f"{supply} is not superseded, so there is nothing to bring back.")
    waiting = waiting_in(conn, dataset_id, period, besides=supply)
    if waiting:
        raise dl.DecisionRefused(
            f"{waiting[0]} is waiting for {period}, so {supply} cannot come back beside it - "
            f"reject or supersede {waiting[0]} first: `mothman supply decide --operation "
            f"reject --dataset {dataset_id} --period {period} --supply {waiting[0]} "
            f"--reason '<why>'`, or the same with `--operation supersede`.")
    source = superseded_schema(period)
    logical = hierarchy.dataset(dataset_id).table
    key = supply_holds.arrival_key_of(supply)
    tables = list(supply_db.candidates_in(conn, source, [logical], arrival=key).get(logical) or [])
    with dl.apply_decision(conn, dl.Decision(
            agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
            action=dl.UN_SUPERSEDE, supply=supply, actor=actor, actor_kind=dl.PERSON,
            effective_at=effective_at, from_slot=period, reason=reason)):
        for physical in tables:
            supply_db.move_table(conn, physical, source, supply_db.STAGING_SCHEMA)
    drop_if_empty(conn, period)
