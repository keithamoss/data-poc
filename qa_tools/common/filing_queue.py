"""What is waiting on a person, and what they may do about it
(REQ-GHUB-082 criteria 16, 17, 18 and 31).

ONE DEFINITION OF "AWAITING A PERSON", AND IT IS NOT THIS MODULE'S.
Criterion 16 says the standing queue SHALL derive from the same
definition REQ-PIPE-083's `needs-action` ticket policy uses, "never a
second one" - so this module FILTERS `slot_state.NEEDS_ACTION` and never
restates it. A second list would be a second answer, and the visible
symptom would be a ticket open for something the terminal says is done.

THE QUEUE IS THE SUPPLY-SHAPED PART OF THAT ONE SET. Two of the
needs-action states - overdue and never-supplied - are slots where
nothing has arrived, so there is no supply to promote, reject, demote or
re-file. They are real work and they are a different question: how a
period is filled when its supply never came, which is criterion 31's
four period-scoped operations reached by dataset and period. Splitting
the one set by "does this slot hold a supply" is a property of the
states themselves rather than a second policy.

WHAT A SLOT OFFERS IS DERIVED FROM ITS STATE, not from a menu somebody
maintains. `operations_for` answers it once so that the queue, the
period view and the offer made after a QA run cannot disagree about
what is possible - the same reason `filing_decisions` exists one layer
down for what is PERMITTED. This module says what is worth putting in
front of somebody; the decision log, inside the transaction, says what
is allowed (criteria 20 and 21). The two are different questions and
this one is allowed to be approximate: offering something the log then
refuses costs a clear refusal, and hiding something the log would have
allowed costs an operator who cannot do their job.

NOTHING HERE READS A SUPPLY ROW. Slot states come from the schedule, the
filings and the decision log, which is REQ-PIPE-083 criterion 7's rule
and the reason this can be asked cheaply and often.
"""
from __future__ import annotations

from datetime import datetime

from qa_tools.common import filing_decisions, qa_store, slot_state, supply_db

#: The states that hold a supply somebody has to decide about. Every one
#: of them is in `slot_state.NEEDS_ACTION` - this is a filter of that
#: set, asserted below rather than trusted.
WITH_A_SUPPLY = (slot_state.AWAITING_DECISION, slot_state.RETURNED,
                 slot_state.HELD, slot_state.REJECTED)

#: The needs-action states where nothing arrived, and so the ones the
#: period path answers rather than the supply queue.
WITHOUT_A_SUPPLY = (slot_state.OVERDUE, slot_state.NEVER_SUPPLIED)

assert set(WITH_A_SUPPLY) | set(WITHOUT_A_SUPPLY) == set(slot_state.NEEDS_ACTION), (
    "the queue must split slot_state.NEEDS_ACTION exactly - a state in "
    "neither half is a state nothing puts in front of anybody")


#: The states a slot can only be in because somebody or something
#: DECIDED it. The rest come from a filing or from the clock, and saying
#: "decided by a rule" about one of those would put a decision where
#: none was made - the same distinction criterion 34 draws between an
#: automatic inheritance and something a person chose.
FROM_A_DECISION = (slot_state.PROMOTED, slot_state.REJECTED,
                   slot_state.SUBSTITUTED, slot_state.INHERITED,
                   slot_state.RETURNED)


class LogUnreachable(Exception):
    """The decision log could not be read (REQ-GHUB-082 criterion 19).

    ITS OWN TYPE so that a caller cannot fall back by accident. The
    criterion forbids presenting "a committed export, a cached read or
    any other copy as the current filing state", and the way to make
    that structural is to have nothing to fall back TO: this is raised,
    the caller says so, and no filing state is shown at all. A stale
    answer about which period holds which supply is worse than no
    answer, because a person acts on it.
    """


def awaiting(conn: supply_db.SupplyConnection, collection_id: str, *,
             now: datetime | None = None) -> list[slot_state.SlotState]:
    """The standing queue: supplies waiting on a person (criterion 16).

    REACHABLE WITHOUT A QA RUN FIRST, which is the point of it. A person
    who has just sat down wants to know what is waiting, and until now
    the only way to find out was to run the checks over something and
    see what the flow said afterwards.

    WORST FIRST, so that thirty datasets' worth of queue opens on the
    thing that has been waiting longest rather than on whichever dataset
    sorts first alphabetically.
    """
    states = [s for s in slot_state.states_for(conn, collection_id, now=now)
              if s.state in WITH_A_SUPPLY]
    return sorted(states, key=lambda s: (s.period, s.dataset_id))


def periods_needing_a_person(conn: supply_db.SupplyConnection, collection_id: str, *,
                             now: datetime | None = None) -> list[slot_state.SlotState]:
    """Periods whose supply never came (criterion 31's own half).

    NOT PART OF THE QUEUE ABOVE, and the separation is the criterion
    rather than a layout preference: none of substitute, de-substitute,
    inherit or un-inherit answers "what do I do with this arriving
    supply", so offering them beside a supply invites somebody working
    an arrival to reach for one.
    """
    states = [s for s in slot_state.states_for(conn, collection_id, now=now)
              if s.state in WITHOUT_A_SUPPLY]
    return sorted(states, key=lambda s: (s.period, s.dataset_id))


def arrival_key_of(supply: str) -> str:
    """The arrival a supply id belongs to.

    `cp-carers@202605010100000000` and the physical table
    `cp_carers__202605010100000000` share this and nothing else -
    post-build-review #64's own lesson, which is that a supply id is not
    a table name and the only safe join between them is the key they
    both carry.
    """
    return (supply or "").rsplit("@", 1)[-1].split("#", 1)[0]


def from_run(conn: supply_db.SupplyConnection, collection_id: str, run_key: str, *,
             now: datetime | None = None) -> list[slot_state.SlotState]:
    """The part of the queue this run's own supply is in (criterion 17).

    THE RUN'S ARRIVAL COMES FROM THE TABLES IT READ, which is a fact the
    database already holds (`qa.tables_read`) rather than a walk of the
    delivery tree. A physical table name carries the arrival key, so the
    join back to a filed supply needs nothing on disk and cannot
    disagree with what the run actually looked at.

    AN EMPTY LIST IS THE ORDINARY ANSWER. Most runs leave nothing
    awaiting a decision - the supply was promoted by the rule, or this
    was a trial that recorded nothing at all.
    """
    rows = conn.execute(
        f'SELECT physical_table FROM "{qa_store.SCHEMA}".tables_read WHERE run_key = ?',
        [run_key]).fetchall()
    keys = {str(r[0]).rsplit("__", 1)[-1] for r in rows if "__" in str(r[0])}
    if not keys:
        return []
    return [s for s in awaiting(conn, collection_id, now=now)
            if s.supply and arrival_key_of(s.supply) in keys]


def operations_for(state: slot_state.SlotState) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(supply-scoped, period-scoped) - what is worth offering on this slot.

    DERIVED FROM THE STATE rather than listed per screen, so the queue,
    the period view and the after-a-run offer cannot drift apart. What
    is offered is not what is permitted: the log decides that at the
    instant the entry is appended (criterion 20), and this only decides
    what to show.
    """
    supply_scoped: tuple[str, ...] = ()
    if state.supply:
        if state.state == slot_state.PROMOTED:
            # Already answered. The only supply-shaped things left are
            # taking it back out and moving it somewhere else.
            supply_scoped = (filing_decisions.DEMOTE, filing_decisions.REFILE)
        elif state.state == slot_state.REJECTED:
            # Rejected, and nothing replaced it. Promoting it anyway is
            # a real thing an operator does after a second look.
            supply_scoped = (filing_decisions.PROMOTE, filing_decisions.REFILE)
        else:
            supply_scoped = (filing_decisions.PROMOTE, filing_decisions.REJECT,
                             filing_decisions.REFILE)

    if state.state == slot_state.SUBSTITUTED:
        period_scoped: tuple[str, ...] = (filing_decisions.DE_SUBSTITUTE,)
    elif state.state == slot_state.INHERITED:
        period_scoped = (filing_decisions.UN_INHERIT,)
    elif state.state == slot_state.PROMOTED:
        period_scoped = ()
    else:
        period_scoped = (filing_decisions.SUBSTITUTE, filing_decisions.INHERIT)
    return supply_scoped, period_scoped


def slots_of(conn: supply_db.SupplyConnection, collection_id: str, *,
             dataset_id: str | None = None,
             now: datetime | None = None) -> list[slot_state.SlotState]:
    """Every slot and where it stands (criterion 18).

    WHICHEVER ROUTE RECORDED EACH DECISION, which is the criterion's own
    emphasis and is free here: this reads the filing state the decision
    log resolves to, and the log does not record which surface raised an
    entry. A terminal that could only show its own decisions would be a
    terminal telling an operator a period is empty when somebody filled
    it from a ticket an hour ago.

    NEWEST PERIOD FIRST, because a reader opening this is asking about
    now and scrolling back.
    """
    states = slot_state.states_for(conn, collection_id, now=now)
    if dataset_id:
        states = [s for s in states if s.dataset_id == dataset_id]
    return sorted(states, key=lambda s: (s.period, s.dataset_id), reverse=True)
