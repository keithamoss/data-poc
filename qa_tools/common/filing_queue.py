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
                 slot_state.TWO_FILES, slot_state.REJECTED,
                 slot_state.AMBER_WAITING, slot_state.AWAITING_ACKNOWLEDGEMENT)

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
                   slot_state.RETURNED, slot_state.NOT_SUPPLIED_ACCEPTED,
                   slot_state.AWAITING_ACKNOWLEDGEMENT)


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

#: ANOTHER VERSION WAITING IN A PROMOTED PERIOD (Keith, 2026-10-05,
#: post-build-review #112) - a newer file for a period already answered.
#: Listed in the queue itself for the same reason as the state above: the
#: slot's own state is "promoted", so the waiting file was reachable only
#: through `supply decide`'s flags. Promoting it supersedes the holder,
#: behind the warning REQ-PIPE-128 criterion 6 requires.
ANOTHER_VERSION_WAITING = "another-version-waiting"

#: Said beside reject, never offered as a control - it is a thing a
#: person does outside this tool.
REPROCESS = "fix the fault and reprocess the delivery"

#: A promoted supply whose re-check came back worse than the verdict it was
#: promoted on (REQ-PIPE-164 criterion 15): its own heading in the queue,
#: 'Promoted, then re-checked <verdict>', in place of the slot's plain
#: awaiting-acknowledgement - which is what it reads as everywhere else.
RECHECKED_WORSE = "promoted-then-rechecked"

#: A version of the period's table a newer one, or a person, set aside
#: (REQ-GHUB-229 criterion 5) - listed among a period's supplies, never in
#: the queue: it waits on nobody. Its one offer is bringing it back.
SUPERSEDED = "superseded"

#: An opened period its dataset owes nothing for, carrying nothing forward -
#: its inheritance was refused (REQ-PIPE-098 criterion 10). Listed in the
#: period door beside the slots (REQ-PIPE-280 criterion 1); never a slot.
CARRIES_NOTHING = "carries-nothing-forward"

#: A listed supply no check read (REQ-GHUB-229 criterion 4), and one whose
#: recorded results could not be read (criterion 11) - said, never guessed.
NO_VERDICT = "no verdict recorded"
VERDICT_UNREADABLE = "verdict could not be read"


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
    every = slot_state.states_for(conn, collection_id, now=now)
    states = [s for s in every
              if s.state in WITH_A_SUPPLY
              and (s.dataset_id, arrival_key_of(s.supply or "")) not in unloadable]
    over = [s for s in waiting_over_promoted(conn, every)
            if (s.dataset_id, arrival_key_of(s.supply or "")) not in unloadable]
    behind = waiting_behind(conn, every, unloadable)
    states = _rechecked_worse(conn, collection_id, states)
    # AN OPEN PAIR LEADS (REQ-PIPE-194 criterion 4): nothing about the
    # dataset is checked until it is settled.
    return sorted(states + failed + over + behind,
                  key=lambda s: (s.state != slot_state.TWO_FILES, s.period, s.dataset_id))


def _rechecked_worse(conn, collection_id: str,
                     states: list[slot_state.SlotState]) -> list[slot_state.SlotState]:
    """Each promoted supply re-checked worse, under its own heading
    (criterion 15): naming its period, the verdict it was promoted on, the
    new one and the re-check that found it."""
    from dataclasses import replace

    from qa_tools.common import rechecking

    # ONLY A SLOT AWAITING ACKNOWLEDGEMENT CAN BE ONE (acknowledgement.owed),
    # so with none there is nothing to read.
    if not any(s.state == slot_state.AWAITING_ACKNOWLEDGEMENT for s in states):
        return states
    # ASKED ONLY ABOUT THE SLOTS IT COULD BE (post-build-review #192 F6) -
    # never the whole asset's list on every render.
    out = []
    for s in states:
        w = (rechecking.worse_for(conn, s.dataset_id, s.supply, s.period)
             if s.state == slot_state.AWAITING_ACKNOWLEDGEMENT and s.supply else None)
        if w is None:
            out.append(s)
            continue
        out.append(replace(s, state=RECHECKED_WORSE, reason=(
            f"Promoted, then re-checked {w.now}: {w.supply} in {w.period} was promoted on "
            f"{w.promoted_on}, and the re-check recorded {w.recheck_at[:16].replace('T', ' ')} "
            f"(decision {w.recheck_id}) came back {w.now}. It stays promoted until a person "
            f"demotes it, or acknowledges its new verdict with a reason.")))
    return out


def waiting_over_promoted(conn: supply_db.SupplyConnection,
                          states: list[slot_state.SlotState]) -> list[slot_state.SlotState]:
    """A queue item for each version still waiting in a period that
    already holds a promoted supply (ANOTHER_VERSION_WAITING)."""
    from qa_tools.common import supersession

    out = []
    for s in states:
        if s.state not in (slot_state.PROMOTED, slot_state.AWAITING_ACKNOWLEDGEMENT):
            continue
        for waiting in supersession.waiting_in(conn, s.dataset_id, s.period,
                                               besides=s.supply):
            out.append(slot_state.SlotState(
                dataset_id=s.dataset_id, period=s.period, state=ANOTHER_VERSION_WAITING,
                supply=waiting,
                reason=f"{s.period} holds {s.supply}; promoting this one supersedes it"))
    return out


def waiting_behind(conn: supply_db.SupplyConnection, states: list[slot_state.SlotState],
                   unloadable: set) -> list[slot_state.SlotState]:
    """A queue item for each loadable version still waiting in a period whose
    slot speaks for another supply (REQ-GHUB-229 criterion 14).

    THE CASE IT EXISTS FOR: a good supply waiting, then a resupply that could
    not be loaded. The slot speaks for its latest live filing - the failed
    one - which the queue lists as could-not-be-loaded, and the good supply
    was in no entry at all. A promoted period's waiting versions are
    waiting_over_promoted's; an open pair blocks the rest of its period
    (REQ-PIPE-194 criterion 4), so neither is asked here.
    """
    from qa_tools.common import supersession

    out = []
    for s in states:
        # AND A PERIOD STANDING ON ANOTHER'S SUPPLY (#201 F3): a supply filed
        # there waits on a person as much as one filed to an empty period.
        if s.state not in WITH_A_SUPPLY + (slot_state.SUBSTITUTED, slot_state.INHERITED) \
                or s.state in (slot_state.TWO_FILES, slot_state.AWAITING_ACKNOWLEDGEMENT):
            continue
        for waiting in supersession.waiting_in(conn, s.dataset_id, s.period,
                                               besides=s.supply):
            if (s.dataset_id, arrival_key_of(waiting)) in unloadable:
                continue
            out.append(slot_state.SlotState(
                dataset_id=s.dataset_id, period=s.period, supply=waiting,
                state=(slot_state.AMBER_WAITING
                       if slot_state._amber_waiting(conn, s.dataset_id, waiting)
                       else slot_state.AWAITING_DECISION)))
    return out


@dataclass(frozen=True)
class FiledSupply:
    """One supply filed to a period, where it stands, and its verdict
    (REQ-GHUB-229 criteria 4 and 5). `state` is the supply's OWN - so
    operations_for gives what that supply offers (criterion 7) - and its
    reason carries what the words need: who rejected it, what superseded
    it, why it could not be loaded."""

    state: slot_state.SlotState
    verdict: str


def filed_counts(conn: supply_db.SupplyConnection,
                 dataset_id: str | None = None) -> dict[tuple[str, str], int]:
    """{(dataset, period): supplies filed to it} - the count the period
    picker and 'Where every period stands' both show (criteria 3 and 15).
    One query, from the filings alone."""
    rows = conn.execute(
        "SELECT dataset_id, slot, count(*) FROM qa.filing_current WHERE slot IS NOT NULL "
        "AND (?::text IS NULL OR dataset_id = ?) GROUP BY dataset_id, slot",
        [dataset_id, dataset_id]).fetchall()
    return {(ds, slot): int(n) for ds, slot, n in rows}


def _verdict(conn, dataset_id: str, supply: str, reads, *, period: str | None = None) -> str:
    """green/amber/red from the recorded results, or said that there is
    none, or that they could not be read - never a verdict it did not read
    (criterion 11). In a period's list, THAT period's reading
    (post-build-review #266 S5, Keith Q3 = A): a supply standing in several
    periods is read against the one listed."""
    from qa_tools.common import supply_status

    try:
        got = supply_status.status(conn, dataset_id, supply, reads=reads,
                                   view=supply_status.View(period=period))
    except Exception:  # noqa: BLE001 - criterion 11: said, and the supply still listed
        return VERDICT_UNREADABLE
    return got or NO_VERDICT


def _latest_by(conn, dataset_id: str, supply: str, action: str):
    """(actor, effective_at) of this supply's latest `action` entry, or None."""
    from qa_tools.common import decision_log

    rows = conn.execute(
        f"SELECT actor, effective_at FROM {decision_log.TABLE} WHERE dataset_id = ? "
        "AND supply = ? AND action = ? ORDER BY effective_at DESC, id DESC LIMIT 1",
        [dataset_id, supply, action]).fetchall()
    return rows[0] if rows else None


def supplies_in(conn: supply_db.SupplyConnection,
                slot: slot_state.SlotState) -> list[FiledSupply]:
    """Every supply filed to this slot's period, oldest receipt first and the
    decided ones after the rest, each in its own state (REQ-GHUB-229 criteria 1, 4, 5 and 12).

    THE ONE FUNCTION the period door and the REQ-GHUB-165 parity test both
    call (criterion 12). It reads the filings, the decision log, the load
    log and the recorded QA results - never a supply row (criterion 17).

    THE ORDER IS THE POINT, as in slot_state.state_of: an open pair first,
    then what was decided about a supply (rejected, superseded), then what
    the load log knows (could not be loaded), and only then whether it is
    the slot's own supply or waiting beside it.
    """
    from qa_tools.common import (decision_log, display_time, hierarchy, promotion,
                                 supersession, supply_files)

    ds, period = slot.dataset_id, slot.period
    rows = conn.execute(
        "SELECT f.supply_id FROM qa.filing_current f LEFT JOIN qa.supply_receipt r "
        "ON r.dataset_id = f.dataset_id AND r.supply_id = f.supply_id "
        "WHERE f.dataset_id = ? AND f.slot = ? "
        "ORDER BY r.received_instant NULLS LAST, f.supply_id", [ds, period]).fetchall()
    failed = {arrival_key_of(f.supply): f.reason
              for f in could_not_load(conn, hierarchy.dataset(ds).collection_id)
              if f.dataset_id == ds and f.period == period}
    # THE SUPPLY IN PLACE, from the log rather than from the slot's state
    # (post-build-review #201 F1 and F2): an open pair over a promoted period
    # reads TWO_FILES, and a supply rejected then promoted carries a reject.
    h = decision_log.held(conn, ds, period)
    in_place = h.holder if h and h.held_as == decision_log.PROMOTED else None
    reads = promotion._declared_reads()
    out = []
    for (supply,) in rows:
        own = None
        contest = supply_files.open_contest(conn, ds, supply)
        if contest is not None:
            own = slot_state.SlotState(dataset_id=ds, period=period, supply=supply,
                                       state=slot_state.TWO_FILES,
                                       files=tuple(contest.files))
        elif supply == in_place:
            own = (slot if supply == slot.supply and slot.state in (
                       slot_state.PROMOTED, slot_state.AWAITING_ACKNOWLEDGEMENT)
                   else _in_place(conn, ds, period, supply))
            if own.state == slot_state.AWAITING_ACKNOWLEDGEMENT:
                (own,) = _rechecked_worse(conn, "", [own])
        elif (by := _latest_by(conn, ds, supply, decision_log.REJECT)) is not None:
            own = slot_state.SlotState(
                dataset_id=ds, period=period, supply=supply, state=slot_state.REJECTED,
                decided_by=by[0],
                reason=f"by {by[0]}, {display_time.format_instant(by[1])}")
        elif supersession.is_superseded(conn, ds, supply):
            newer = supersession.superseded_by(conn, ds, supply)
            by = _latest_by(conn, ds, supply, decision_log.SUPERSEDE)
            at = supersession._receipt(conn, ds, newer) if newer else None
            # A TIME A PERSON READS, never the arrival key (#201 F6).
            own = slot_state.SlotState(
                dataset_id=ds, period=period, supply=supply, state=SUPERSEDED,
                reason=(f"by the supply that arrived {display_time.format_instant(at)}"
                        if at else "by a newer supply" if newer
                        else f"set aside by {by[0]}" if by else "set aside"))
        elif arrival_key_of(supply) in failed:
            own = slot_state.SlotState(dataset_id=ds, period=period, supply=supply,
                                       state=COULD_NOT_LOAD,
                                       reason=failed[arrival_key_of(supply)])
        elif supply == slot.supply and slot.state != slot_state.TWO_FILES:
            own = slot
        elif in_place:
            own = slot_state.SlotState(
                dataset_id=ds, period=period, supply=supply, state=ANOTHER_VERSION_WAITING,
                reason=f"{period} holds {in_place}; promoting this one supersedes it")
        else:
            own = slot_state.SlotState(
                dataset_id=ds, period=period, supply=supply,
                state=(slot_state.AMBER_WAITING
                       if slot_state._amber_waiting(conn, ds, supply)
                       else slot_state.AWAITING_DECISION))
        out.append(FiledSupply(state=own, verdict=_verdict(conn, ds, supply, reads, period=period)))
    # THE DECIDED ONES LAST (Keith, 2026-10-15, signing off): rejected and
    # superseded supplies are listed with the rest, after those still in play.
    return sorted(out, key=lambda e: e.state.state in (slot_state.REJECTED, SUPERSEDED))


def _in_place(conn, dataset_id: str, period: str, supply: str) -> slot_state.SlotState:
    """The promoted supply's own state where the slot speaks for another
    (#201): promoted, or awaiting acknowledgement where one is owed."""
    from qa_tools.common import acknowledgement

    owed = acknowledgement.owed(conn, dataset_id, period) == supply
    return slot_state.SlotState(
        dataset_id=dataset_id, period=period, supply=supply,
        state=slot_state.AWAITING_ACKNOWLEDGEMENT if owed else slot_state.PROMOTED)


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
    from qa_tools.common import supply_files

    return supply_files.staging_key_of(supply)


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
    # THE KEY IS THE SECOND SEGMENT (REQ-PIPE-193 criterion 13): a pair's
    # table ends in its ordinal, `cp_clients__<key>__2`.
    keys = {parts[1] for parts in (supply_db.split_staged(str(r[0])) for r in rows) if parts}
    if not keys:
        return []
    return [s for s in awaiting(conn, collection_id, now=now)
            if s.supply and arrival_key_of(s.supply) in keys]


def excuse_offers(conn, state: slot_state.SlotState) -> tuple[str, ...]:
    """Excuse lateness where this slot's current supply classifies as late
    and is not excused; withdraw the excuse where it is (REQ-PIPE-161
    criterion 10). Separate from operations_for because punctuality is a
    recorded fact read from the database, not part of the slot's state."""
    from qa_tools.common import excuse

    if not state.supply or state.state == COULD_NOT_LOAD:
        # A FAILED LOAD IS OFFERED REJECT ALONE (REQ-GHUB-229 criterion 16,
        # REQ-PIPE-153 criteria 5 and 6) - its punctuality is not the question.
        return ()
    if excuse.in_force(conn, state.dataset_id, state.supply) is not None:
        return (filing_decisions.WITHDRAW_EXCUSE,)
    if excuse.why_not_excusable(conn, state.dataset_id, state.supply, state.period) is None:
        return (filing_decisions.EXCUSE_LATENESS,)
    return ()


def acknowledgement_offers(conn, state: slot_state.SlotState) -> tuple[str, ...]:
    """Withdraw the acknowledgement where this slot's supply carries one
    standing (REQ-PIPE-166 criterion 6) - read from the recorded decisions,
    as excuse_offers reads an excuse."""
    from qa_tools.common import withdrawal

    if not state.supply or not state.period:
        return ()
    found = withdrawal.standing_acknowledgement(conn, state.dataset_id, state.supply,
                                                state.period)
    return (filing_decisions.WITHDRAW_ACKNOWLEDGEMENT,) if found else ()


def supersede_offers(conn, state: slot_state.SlotState) -> tuple[str, ...]:
    """Un-supersede wherever filing_decisions.apply would accept it
    (REQ-GHUB-165 criterion 1): a superseded version of the dataset's table
    in this period that was not rejected since, and no other version
    waiting there (REQ-PIPE-120 criterion 5) - read on the caller's
    connection, as excuse_offers reads punctuality. Never only on a slot
    whose supply was rejected: after a newer file or an automatic
    replacement superseded one, that was the only way back."""
    if not state.period:
        return ()
    back = superseded_to_bring_back(conn, state)
    if state.state == SUPERSEDED:
        # A LISTED SUPERSEDED VERSION (REQ-GHUB-229 criterion 7): offered
        # bringing back only where THIS one could come back.
        back = [v for v in back if v["supply"] == state.supply]
    return (filing_decisions.UN_SUPERSEDE,) if back else ()


def superseded_to_bring_back(conn, state: slot_state.SlotState) -> list[dict]:
    """The superseded versions un-supersede could bring back into this
    period now - none while another version waits there."""
    from qa_tools.common import supersession

    if supersession.waiting_in(conn, state.dataset_id, state.period):
        return []
    return [v for v in supersession.superseded_in(conn, state.dataset_id, state.period)
            if not supersession._rejected(conn, state.dataset_id, v["supply"])]


@dataclass(frozen=True)
class HeldRow:
    """One held supply in the queue (REQ-PIPE-163 criteria 10 and 17): its
    dataset and receipt in place of a period, why it was held in the hold's
    own reason, and - for a pair held whole - both its files, counted once."""

    dataset_id: str
    dataset_name: str
    supply: str
    received_at: datetime | None
    received_text: str
    why: str
    schedule_ended: bool
    files: tuple[str, ...] = ()
    #: Held because its dataset is refused by the agreement backstop
    #: (REQ-PIPE-173) - it files itself once that is put right.
    agreement_refused: bool = False
    #: Received while its dataset is turned off (REQ-PIPE-179 criterion 34):
    #: listed quietly, apart, and not counted as waiting on a decision.
    turned_off: bool = False


@dataclass(frozen=True)
class TurnedOffGroup:
    """One dataset's supplies received while turned off - ONE ROW PER
    DATASET (REQ-PIPE-179 criterion 34 and its SCALE NFR: a supplier still
    sending daily files adds one row, not 365 a year)."""

    dataset_id: str
    dataset_name: str
    rows: tuple[HeldRow, ...]

    @property
    def line(self) -> str:
        from qa_tools.common import asset_time

        dated = [r.received_at for r in self.rows if r.received_at is not None]
        earliest = (f", earliest {asset_time.localise(min(dated)).strftime('%-d %B %Y')}"
                    if dated else "")
        return f"{self.dataset_id} - {len(self.rows)} received while turned off{earliest}"


def turned_off_groups(held) -> list[TurnedOffGroup]:
    """The held rows received while turned off, one group per dataset, in
    dataset order - each group's supplies oldest receipt first."""
    by: dict[str, list[HeldRow]] = {}
    for row in held:
        if row.turned_off:
            by.setdefault(row.dataset_id, []).append(row)
    return [TurnedOffGroup(ds, rows[0].dataset_name, tuple(rows))
            for ds, rows in sorted(by.items())]


def held_operations(row: HeldRow) -> tuple[str, ...]:
    """What the door offers on a held supply (REQ-PIPE-163 criteria 10 and
    22): place and reject - nothing on a hold labelled schedule ended, which
    the rule files once dates cover it."""
    if row.schedule_ended or row.agreement_refused:
        # Both file themselves once configuration is put right (#188 D9).
        return ()
    return (filing_decisions.PLACE, filing_decisions.REJECT)


def held_in(conn: supply_db.SupplyConnection, collection_id: str) -> list[HeldRow]:
    """Every supply the assignment rule holds in this collection, oldest
    receipt first. One row per supply - a pair held whole is one supply."""
    from qa_tools.common import display_time, hierarchy, supersession, supply_files
    from qa_tools.common import supply_holds

    datasets = {d.dataset_id: d for d in hierarchy.datasets_in_collection(collection_id)}
    rows = []
    for h in supply_holds.outstanding(conn):
        if h.dataset_id not in datasets or h.kind != supply_holds.ASSIGNMENT_RULE:
            continue
        at = supersession._receipt(conn, h.dataset_id, h.supply_id)
        contest = supply_files.open_contest(conn, h.dataset_id, h.supply_id)
        rows.append(HeldRow(
            dataset_id=h.dataset_id, dataset_name=datasets[h.dataset_id].dataset_name,
            supply=h.supply_id, received_at=at,
            received_text=display_time.format_instant(at) if at else "an unknown time",
            why=h.describe(), schedule_ended=h.schedule_ended,
            agreement_refused=h.agreement_refused, turned_off=h.turned_off,
            files=tuple(contest.files) if contest is not None else ()))
    return sorted(rows, key=lambda r: (r.received_at is None, r.received_at or 0, r.supply))


def operations_for(state: slot_state.SlotState) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(supply-scoped, period-scoped) - what is worth offering on this slot.

    DERIVED FROM THE STATE rather than listed per screen, so the queue,
    the period view and the after-a-run offer cannot drift apart. What
    is offered is not what is permitted: the log decides that at the
    instant the entry is appended (criterion 20), and this only decides
    what to show.
    """
    supply_scoped: tuple[str, ...] = ()
    if state.state == SUPERSEDED:
        # Bringing it back is read from the log (supersede_offers). Or moving
        # it to the period it belongs to, which ends the supersession
        # (supersession._latest) - the parity test found the flags record it.
        return (filing_decisions.REFILE,), ()
    if state.state == ANOTHER_VERSION_WAITING:
        # PROMOTE OVER, behind the warning; or set it aside.
        # ...or move it to the period it belongs to (REQ-GHUB-165 parity).
        return (filing_decisions.PROMOTE, filing_decisions.REJECT,
                filing_decisions.SUPERSEDE, filing_decisions.REFILE,
                filing_decisions.RECHECK), ()
    if state.state == RECHECKED_WORSE:
        # REQ-PIPE-164 criterion 15: take it out, or record that it stays - then
        # what every promoted supply offers, and re-check last (criterion 26).
        return (filing_decisions.ACKNOWLEDGE, filing_decisions.DEMOTE,
                filing_decisions.REFILE, filing_decisions.REJECT,
                filing_decisions.RECHECK), ()
    if state.state == slot_state.TWO_FILES:
        # AN OPEN PAIR IS SETTLED, AND NOTHING ELSE (REQ-PIPE-194 criterion 4):
        # 'settle' and 'reject both' are both choose-file - the TUI words the
        # second - and no other operation is offered on any door.
        return (filing_decisions.CHOOSE_FILE,), ()
    if state.state == COULD_NOT_LOAD:
        # REJECT ONLY (REQ-PIPE-153 criteria 5 and 6): promoting it is
        # refused on every route, and the other response - fix and
        # reprocess - is a thing a person does, named beside it.
        return (filing_decisions.REJECT,), ()
    if state.supply:
        if state.state == slot_state.AWAITING_ACKNOWLEDGEMENT:
            # REQ-PIPE-122 criterion 13: answered, and owed a look - so
            # acknowledging comes first, beside taking it back out.
            supply_scoped = (filing_decisions.ACKNOWLEDGE, filing_decisions.DEMOTE,
                             filing_decisions.REFILE, filing_decisions.REJECT,
                             filing_decisions.RECHECK)
        elif state.state == slot_state.PROMOTED:
            # Already answered. What is left is taking it back out, moving
            # it somewhere else, or saying it is not fit after all - a
            # rejection needs no demotion first (REQ-PIPE-075 criterion 4;
            # REQ-GHUB-165's parity test found the door did not offer it).
            supply_scoped = (filing_decisions.DEMOTE, filing_decisions.REFILE,
                             filing_decisions.REJECT, filing_decisions.RECHECK)
        elif state.state == slot_state.REJECTED:
            # Rejected, and nothing replaced it. Promoting it anyway is
            # a real thing an operator does after a second look.
            # ...or bringing back a version a newer one superseded, once
            # the newer one has been rejected (REQ-PIPE-120 criterion 5).
            # (Un-supersede is offered by supersede_offers, wherever a
            # superseded version could come back - REQ-GHUB-165 criterion 1.)
            supply_scoped = (filing_decisions.PROMOTE, filing_decisions.REFILE)
        else:
            # SUPERSEDE IS OFFERED ON A WAITING SUPPLY (REQ-PIPE-120
            # criterion 1): set it aside without rejecting it.
            supply_scoped = (filing_decisions.PROMOTE, filing_decisions.REJECT,
                             filing_decisions.REFILE, filing_decisions.SUPERSEDE)
            # RE-CHECK, LAST - after the decisions that settle it (REQ-PIPE-164
            # criteria 11 and 26) - on a supply filed and waiting.
            if state.state in (slot_state.AWAITING_DECISION, slot_state.RETURNED,
                               slot_state.AMBER_WAITING):
                supply_scoped += (filing_decisions.RECHECK,)

    if state.state == slot_state.NOT_SUPPLIED_ACCEPTED:
        # Accepted - and a late file can still be re-filed in, or an
        # earlier supply stood on, either of which supersedes the mark.
        # Or the mark withdrawn, beside it (REQ-PIPE-166 criterion 6).
        period_scoped: tuple[str, ...] = (filing_decisions.SUBSTITUTE,
                                          filing_decisions.WITHDRAW_NOT_SUPPLIED)
    elif state.closed:
        # A CLOSED, UNFILLED PERIOD (REQ-PIPE-132 criteria 5 and 12):
        # substitute it, or accept it as not supplied. A late file is
        # re-filed into it from that FILE's own slot.
        period_scoped = (filing_decisions.SUBSTITUTE, filing_decisions.INHERIT,
                         filing_decisions.MARK_NOT_SUPPLIED)
    elif state.state == slot_state.SUBSTITUTED:
        period_scoped = (filing_decisions.DE_SUBSTITUTE,)
    elif state.state == slot_state.INHERITED:
        # CARRY-FORWARD BESIDE UN-INHERIT (REQ-PIPE-280 criterion 1): the way to
        # re-point an inheritance without a gap.
        period_scoped = (filing_decisions.CARRY_FORWARD, filing_decisions.UN_INHERIT)
    elif state.state == CARRIES_NOTHING:
        # A PERIOD OWING NOTHING THAT CARRIES NOTHING (REQ-PIPE-280 criterion 1):
        # the one operation REQ-PIPE-271's warning names.
        period_scoped = (filing_decisions.CARRY_FORWARD,)
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
    # ONE LINE PER PERIOD (REQ-GHUB-229 criterion 3): a version waiting in a
    # promoted period is reached through supplies_in, listed under its
    # period, and no longer a second line for the same period here.
    return sorted(states, key=lambda s: (s.period, s.dataset_id), reverse=True)
