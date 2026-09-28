"""Rejection and un-decide - a person's decisions (REQ-PIPE-076).

"...so that staging is a work list rather than a graveyard." The queue
an operator looks at should hold supplies nobody has decided on, which
means a decided supply has to LEAVE it and stay gone.

NOTHING HERE HAPPENS AUTOMATICALLY, and that is criterion 3 rather than
a house style. A rule may decline to promote; only a person may reject.
The difference matters because rejection is the one decision that says
a supplier's file will not be used, and somebody has to own that.

THE BAR ON AUTOMATIC PROMOTION IS THE SUBTLE PART. Once a person has
decided anything about a supply, automation defers to them for that
supply's life (criteria 7 and 12) - but the bar attaches to the SUPPLY,
never to the slot, the period or the dataset (criterion 11). Attach it
one level wider and a single rejection quietly disables automation for
that feed forever; one level narrower and the next run promotes the
very supply somebody just rejected.
"""
from __future__ import annotations

from collections.abc import Sequence

from qa_tools.common import decision_log, supply_db


class NotAPersonsDecision(RuntimeError):
    """Raised where a rule tries to make a decision only a person may."""


def reject(conn: supply_db.SupplyConnection, *,
           agency_id: str,
           collection_id: str,
           dataset_id: str,
           supply: str,
           physical_tables: Sequence[str],
           actor: str,
           effective_at: str,
           reason: str,
           from_slot: str,
           actor_kind: str = decision_log.PERSON) -> None:
    """Move this supply to the rejected schema and record the decision.

    `from_slot` IS REQUIRED, not optional, because the decision log
    refuses an entry that names no period: "a decision needs at least
    one slot - which period it acts on". A rejection acts on the slot
    the supply was filed to, and leaves it unfilled.

    ONE DECISION even where the supply was promoted (criterion 4): the
    person says "not this one", and making them demote it first would be
    asking for a second decision to describe one intention. `from_slot`
    carries the slot it is leaving, so the entry says the slot is now
    unfilled without a separate entry saying so.

    The move and the entry are ONE TRANSACTION, on the same reasoning as
    promotion: neither can be observed without the other.
    """
    if actor_kind != decision_log.PERSON:
        # Criterion 3, refused here rather than left to the log, so the
        # message names the actual rule rather than a generic refusal.
        raise NotAPersonsDecision(
            "only a person rejects a supply - a rule may decline to promote one, "
            "but saying a supplier's file will not be used is somebody's decision "
            f"to own (actor_kind was {actor_kind!r})")

    schema = supply_db.REJECTED_SCHEMA
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    decision = decision_log.Decision(
        agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
        action=decision_log.REJECT, supply=supply, actor=actor,
        actor_kind=actor_kind, effective_at=effective_at,
        from_slot=from_slot, reason=reason)
    with decision_log.apply_decision(conn, decision):
        for physical in physical_tables:
            supply_db.move_table(conn, physical, supply_db.STAGING_SCHEMA, schema)


def decided_by_a_person(conn: supply_db.SupplyConnection,
                        dataset_id: str, supply: str) -> bool:
    """Whether a PERSON has recorded any decision about this supply.

    Criteria 7, 11 and 12 in one question, and the scope is the whole
    point: this asks about ONE SUPPLY. A rejection of last quarter's
    file says nothing about this quarter's, and a slot a person emptied
    is still open to the next supply that carries no decision of its
    own.

    It also asks only about PEOPLE. A rule's own promotion must not bar
    a rule from promoting again after a demote, or automation would
    disable itself by working.

    Nothing expires. The bar lasts for the life of the supply it was
    recorded against - not cleared on a later run, a resupply, or with
    time - which falls out of reading an append-only log rather than
    needing to be enforced.
    """
    rows = conn.execute(
        f"SELECT 1 FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND supply = ? AND actor_kind = ? LIMIT 1",
        [dataset_id, supply, decision_log.PERSON]).fetchall()
    return bool(rows)
