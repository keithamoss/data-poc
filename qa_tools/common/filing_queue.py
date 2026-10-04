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

from dataclasses import dataclass
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
                   slot_state.RETURNED, slot_state.NOT_SUPPLIED_ACCEPTED)


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


#: A supply that arrived and could not be loaded (REQ-PIPE-153 criterion
#: 5). Listed in the queue ITSELF rather than through its slot's state:
#: slot_state keeps one filed supply per slot, so a failed resupply of a
#: filled slot would never be reached that way.
COULD_NOT_LOAD = "could-not-be-loaded"

#: Said beside reject, never offered as a control - it is a thing a
#: person does outside this tool.
REPROCESS = "fix the fault and reprocess the delivery"


def could_not_load(conn: supply_db.SupplyConnection,
                   collection_id: str) -> list[slot_state.SlotState]:
    """Every open failed load in this collection whose supply was FILED to
    a period - as a queue entry offering reject (criteria 1 and 5).

    A failed load filed to no period is left to the held-supply route
    (criterion 12): the decision log has no slot to record a rejection
    against.
    """
    from qa_tools.common import dataset_blockers, filing, hierarchy, load_log

    # A REFUSED FILE OF A CONTESTED PAIR is the contest's to report
    # (REQ-PIPE-115 criterion 27), here as in the outstanding items.
    in_contest = dataset_blockers.refused_in_a_contest(conn)
    out = []
    for record in load_log.failures(conn=conn):
        if (record.dataset_id, record.physical) in in_contest:
            continue
        try:
            entry = hierarchy.dataset(record.dataset_id)
        except hierarchy.UnknownDatasetError:
            continue
        parts = supply_db.split_staged(record.physical)
        if entry.collection_id != collection_id or not parts:
            continue
        period = filing.period_for_key(record.dataset_id, parts[1])
        if not period:
            continue
        out.append(slot_state.SlotState(
            dataset_id=record.dataset_id, period=period, state=COULD_NOT_LOAD,
            supply=f"{record.dataset_id}@{parts[1]}",
            reason=record.reason or "no reason was recorded"))
    return out


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
    failed = could_not_load(conn, collection_id)
    unloadable = {(f.dataset_id, arrival_key_of(f.supply)) for f in failed}
    states = [s for s in slot_state.states_for(conn, collection_id, now=now)
              if s.state in WITH_A_SUPPLY
              and (s.dataset_id, arrival_key_of(s.supply or "")) not in unloadable]
    return sorted(states + failed, key=lambda s: (s.period, s.dataset_id))


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


@dataclass(frozen=True)
class Gap:
    """Consecutive CLOSED, unfilled, unmarked periods of one dataset, as
    one item (REQ-PIPE-132 criterion 11, REQ-DASH-133 criterion 7) - so
    seventeen missed days are one line, not seventeen."""

    dataset_id: str
    periods: tuple[str, ...]
    state: str

    @property
    def count(self) -> int:
        return len(self.periods)

    def describe(self) -> str:
        # A DAILY FEED'S SLOT IS A DAY, and reads as the page writes one
        # (REQ-DASH-071's display standard) - never ISO, which the queue
        # carries verbatim onto the dashboard.
        daily = all(_is_day(p) for p in self.periods)
        unit = "day" if daily else "period"
        what = unit if self.count == 1 else f"{unit}s"
        name = _day_text if daily else str
        span = (name(self.periods[0]) if self.count == 1
                else f"{name(self.periods[0])} to {name(self.periods[-1])}")
        return f"{self.count} {what} with no supply, {span}"


def _is_day(period: str) -> bool:
    from datetime import date

    try:
        date.fromisoformat(period)
    except ValueError:
        return False
    return len(period) == 10


def _day_text(period: str) -> str:
    from datetime import date

    d = date.fromisoformat(period)
    return f"{d:%A}, {d.day} {d:%B} {d.year}"


def group_gaps(states) -> list[Gap]:
    """Closed, unfilled, unmarked slot states grouped into runs of
    consecutive periods per dataset. `states` is in each dataset's slot
    order (states_for() returns them so); a slot in between that is not a
    gap breaks the run."""
    out: list[Gap] = []
    run: list = []

    def flush():
        if run:
            out.append(Gap(dataset_id=run[0].dataset_id,
                           periods=tuple(s.period for s in run), state=run[0].state))
            run.clear()

    for s in states:
        is_gap = s.closed and s.state in WITHOUT_A_SUPPLY + (slot_state.REJECTED,
                                                             slot_state.RETURNED)
        if is_gap and run and run[0].dataset_id == s.dataset_id:
            run.append(s)
            continue
        flush()
        if is_gap:
            run.append(s)
    flush()
    return out


def closed_gaps(conn: supply_db.SupplyConnection, collection_id: str, *,
                now: datetime | None = None) -> list[Gap]:
    """Every closed, unfilled, unmarked period in a collection, grouped."""
    return group_gaps(slot_state.states_for(conn, collection_id, now=now))


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
    if state.state == COULD_NOT_LOAD:
        # REJECT ONLY (REQ-PIPE-153 criteria 5 and 6): promoting it is
        # refused on every route, and the other response - fix and
        # reprocess - is a thing a person does, named beside it.
        return (filing_decisions.REJECT,), ()
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

    if state.state == slot_state.NOT_SUPPLIED_ACCEPTED:
        # Accepted - and a late file can still be re-filed in, or an
        # earlier supply stood on, either of which supersedes the mark.
        period_scoped: tuple[str, ...] = (filing_decisions.SUBSTITUTE,)
    elif state.closed:
        # A CLOSED, UNFILLED PERIOD (REQ-PIPE-132 criteria 5 and 12):
        # substitute it, or accept it as not supplied. A late file is
        # re-filed into it from that FILE's own slot.
        period_scoped = (filing_decisions.SUBSTITUTE, filing_decisions.INHERIT,
                         filing_decisions.MARK_NOT_SUPPLIED)
    elif state.state == slot_state.SUBSTITUTED:
        period_scoped = (filing_decisions.DE_SUBSTITUTE,)
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
