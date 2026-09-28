"""Promotion - the act that fills a slot (REQ-PIPE-075).

A supply reaches a period by being PROMOTED into it, and nothing else
fills a slot. An arrival does not, a staged supply does not, and a
rejected one certainly does not - `filing.filled_slots()` has been a
deliberate stub saying so since before this module existed.

TWO THINGS HERE ARE EASY TO BUILD THE OTHER WAY ROUND, and both are
criteria rather than preferences:

THE TABLES MOVE BEFORE THE ENTRY IS WRITTEN (criterion 9). An entry
written first would say a supply is promoted while the period schema
does not hold it, and - worse - nothing would ever retry, because the
log says it is done. Written in this order, an interruption leaves the
tables moved and no entry, so the next attempt repeats the promotion
and lands where it should. Repeating is cheap; skipping is silent.

PROMOTION MOVES, IT DOES NOT COPY (criterion 15). Staging then holds
only supplies nobody has decided on, which is what makes "what is
waiting for me" answerable by looking at it. PostgreSQL's ALTER TABLE
... SET SCHEMA is a real move and a catalogue-only one, so this costs
nothing even for a large table - see supply_db.move_table.

WHAT THIS MODULE DOES NOT DO, deliberately: decide WHETHER a supply
should be promoted. The automatic gate reads a QA verdict and this
module does not go browsing for one - the caller has it in hand, the
same division decision_log.Decision already makes for `supply_is_red`.
"""
from __future__ import annotations

from collections.abc import Sequence

from qa_tools.common import decision_log, period_schema, supply_db


def promote(conn: supply_db.SupplyConnection, *,
            agency_id: str,
            collection_id: str,
            dataset_id: str,
            supply: str,
            period: str,
            physical_tables: Sequence[str],
            actor: str,
            actor_kind: str,
            effective_at: str,
            reason: str | None = None,
            supply_is_red: bool = False) -> bool:
    """Move this supply's tables into `period` and record the decision.

    Returns True where it promoted, False where the supply was already
    promoted into this slot and there was nothing to do (criterion 10) -
    a repeat is an ordinary thing for a retry to hit, not an error.

    Raises whatever the move raises. That is the point of the ordering:
    a failure here leaves no entry, so the slot is still unfilled and
    the caller may try again.
    """
    # ALREADY DONE? Asked of the LOG rather than of the catalogue, for
    # the same reason filled_slots() does: a table in the schema that no
    # decision put there is not a promotion.
    if decision_log.promoted_into(conn, dataset_id, period) == supply:
        return False

    schema = period_schema.ensure_period_schema(conn, period)
    decision = decision_log.Decision(
        agency_id=agency_id,
        collection_id=collection_id,
        dataset_id=dataset_id,
        action=decision_log.PROMOTE,
        supply=supply,
        actor=actor,
        actor_kind=actor_kind,
        effective_at=effective_at,
        to_slot=period,
        reason=reason,
        supply_is_red=supply_is_red,
    )

    def move() -> None:
        for physical in physical_tables:
            supply_db.move_table(conn, physical, supply_db.STAGING_SCHEMA, schema)

    # ONE TRANSACTION, entry and move together - see this module's
    # docstring on why that is STRONGER than criterion 9's literal
    # ordering rather than a departure from it. decision_log's own
    # record_automatic() says the same in as many words: "anything that
    # touches the warehouse uses the context manager, so that the entry
    # and the change stay one transaction". This touches the warehouse.
    with decision_log.apply_decision(conn, decision):
        move()
    return True


def filled_slots(conn: supply_db.SupplyConnection, dataset_id: str) -> frozenset[str]:
    """Slots this dataset has a supply PROMOTED into (criterion 6).

    Derived from the decision log, never from the warehouse catalogue,
    and the criterion says so in as many words. A table sitting in a
    period schema that no decision promoted is a table somebody put
    there; calling that a filled slot would let a stray object decide
    whether a real supply may be promoted.

    Each slot is resolved through decision_log.promoted_into(), so a
    slot later emptied by a reject, a demote or a re-file OUT stops
    being filled without this having to know those rules itself.
    """
    rows = conn.execute(
        f"SELECT DISTINCT to_slot FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND to_slot IS NOT NULL", [dataset_id]).fetchall()
    return frozenset(
        slot for (slot,) in rows
        if decision_log.promoted_into(conn, dataset_id, slot) is not None)
