"""Where one expected supply has got to (REQ-PIPE-083 criteria 6-8).

A SLOT IS ONE EXPECTED SUPPLY - this dataset, this period - and its
STATE is the answer to the only question a person watching a work queue
asks: has it turned up, and if so what happened to it. The ticket
reconciler exists to keep that answer in front of a team; this module is
where the answer is computed, once, so that the reconciler, the CLI and
the terminal all say the same thing.

DERIVED, NEVER RECORDED, and that is criterion 4's reconcile-rather-
than-react in its data form. Storing a slot's state would mean two
places that can disagree, and the stored one would be wrong from the
moment the next decision landed - the same reasoning
slots.is_overdue()'s own docstring gives for asking rather than
flagging.

FROM THE SCHEDULE, THE FILINGS AND THE DECISION LOG (criterion 7).
Those three between them know everything about a supply except what its
checks found, and never touch a row of it. The QA VERDICT is
deliberately NOT computed here - see verdict_for() below and this
module's note on the tension between criteria 6 and 7.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from qa_tools.common import decision_log, supply_db

#: Nothing has arrived and nothing is late yet. The ordinary state of
#: most slots most of the time, and the reason the default ticket
#: policy is `needs-action` rather than `all`.
NOT_YET_DUE = "not-yet-due"
#: Due, past its grace, and nothing filed to it.
OVERDUE = "overdue"
#: Overdue AND this dataset has never had a delivery at all - which is
#: criterion 8, and a different conversation from a supplier who
#: usually delivers and missed one.
NEVER_SUPPLIED = "never-supplied"
#: A supply is filed here and nobody has decided about it.
AWAITING_DECISION = "awaiting-decision"
#: A person looked at it and put it back.
RETURNED = "returned-by-a-person"
#: Filed here, but REQ-PIPE-059 could not tell which file is the supply.
HELD = "held"
#: A supply is promoted into it. The slot is answered.
PROMOTED = "promoted"
#: A person rejected the supply filed here, and nothing replaced it.
REJECTED = "rejected"
#: The period stands on an earlier one by a person's decision.
SUBSTITUTED = "substituted"
#: The period stands on an earlier one because nothing was owed.
INHERITED = "inherited"
#: A closed period a PERSON has accepted as not supplied (REQ-PIPE-132
#: criterion 9) - the one new state, because it records a decision. An
#: unmarked closed period stays OVERDUE or NEVER-SUPPLIED, qualified by
#: SlotState.closed (criterion 1).
NOT_SUPPLIED_ACCEPTED = "not-supplied-accepted"
#: AN AMBER SUPPLY THE RULE DID NOT PROMOTE BECAUSE ITS AMBER SETTING IS
#: hold (REQ-PIPE-122 criteria 10, 17 and 18). Its own state and its own
#: words, never "held" - that means a supply filed to no slot - and never
#: folded into AWAITING_DECISION, which is a red supply's.
AMBER_WAITING = "amber-waiting"
#: A PROMOTED amber supply whose promotion asked for an acknowledgement
#: that nobody has given (REQ-PIPE-122 criteria 11 and 17). The slot is
#: answered; a person still owes a look.
AWAITING_ACKNOWLEDGEMENT = "awaiting-acknowledgement"

#: The states that need a person, and so the ones the default
#: `needs-action` ticket policy opens a ticket for (criterion 21).
#: PROMOTED and NOT_YET_DUE are the two that do not: one is finished and
#: the other has not started.
NEEDS_ACTION = frozenset({
    OVERDUE, NEVER_SUPPLIED, AWAITING_DECISION, RETURNED, HELD, REJECTED,
    AMBER_WAITING, AWAITING_ACKNOWLEDGEMENT,
})

#: What a person can do about each. Criterion 9 asks for the responses
#: to be NAMED on the ticket, and naming is all this does - the
#: reconciler offers no buttons, because a route that does nothing is
#: worse than no route.
#: What a person can do about a period that CLOSED unfilled (REQ-PIPE-132
#: criterion 12) - each available on both routes - and what they must
#: know: a file arriving now goes to the open period, not to this one.
CLOSED_RESPONSES = ("substitute an earlier period's supply",
                    "mark it as not supplied",
                    "re-file a late file into it")
CLOSED_NOTE = "a file arriving now is filed to the open period, not to this one"

RESPONSES = {
    NOT_SUPPLIED_ACCEPTED: (),
    AMBER_WAITING: ("promote this supply", "reject it", "ask for a resupply"),
    AWAITING_ACKNOWLEDGEMENT: ("acknowledge it, with a reason",),
    OVERDUE: ("chase the supplier", "record the period as not supplied",
               "substitute an earlier period's supply"),
    NEVER_SUPPLIED: ("chase the supplier",
                      "check the schedule is the one that was agreed"),
    AWAITING_DECISION: ("promote this supply", "reject it", "ask for a resupply"),
    RETURNED: ("promote this supply", "reject it", "ask for a resupply"),
    HELD: ("say which file is the supply", "ask the supplier which to use"),
    REJECTED: ("ask for a resupply", "substitute an earlier period's supply"),
    PROMOTED: (),
    SUBSTITUTED: ("de-substitute this period",),
    INHERITED: (),
    NOT_YET_DUE: (),
}


@dataclass(frozen=True)
class SlotState:
    """One slot, and where its supply has got to."""

    dataset_id: str
    period: str
    state: str
    supply: str | None = None
    #: The period this one stands on, where it stands on one.
    stands_on: str | None = None
    #: Who decided, where a person did. None for anything a rule did.
    decided_by: str | None = None
    reason: str = ""
    #: CLOSED, derived and never recorded (REQ-PIPE-132 criteria 1 and 2):
    #: the next period's claim window has opened and nothing fills this
    #: one, so it can no longer be filled automatically.
    closed: bool = False

    @property
    def needs_action(self) -> bool:
        return self.state in NEEDS_ACTION

    @property
    def responses(self) -> tuple[str, ...]:
        if self.closed and self.state in (OVERDUE, NEVER_SUPPLIED, REJECTED, RETURNED):
            return CLOSED_RESPONSES
        return RESPONSES.get(self.state, ())

    @property
    def key(self) -> str:
        """The stable key a ticket is found by (criterion 3).

        ONE DATASET, ONE PERIOD, and nothing else in it - no run, no
        supply, no date. A later run has to find the SAME ticket, and a
        key carrying anything that changes between runs opens a second
        one instead.
        """
        return f"{self.dataset_id}/{self.period}"


def _state_from(h) -> tuple[str, str | None]:
    """The state qa.slot_holds leaves a slot in, and the supply it names.

    HOW THE SLOT IS HELD COMES FROM THE VIEW (REQ-PIPE-130 criterion 9),
    never from re-reading an action: a re-file OUT leaves 'refile' as the
    slot's last decision, and reading that as promoted is how an emptied
    period showed as promoted (delivery-critic, overnight sprint 2). Only
    for an EMPTY slot is the action read, to say how it was emptied.
    """
    if h.held_as == decision_log.PROMOTED:
        return PROMOTED, h.holder
    if h.held_as == decision_log.SUBSTITUTED:
        return SUBSTITUTED, h.holder
    if h.held_as == decision_log.INHERITED:
        return INHERITED, h.holder
    if h.action == decision_log.REJECT:
        return REJECTED, None
    # A demote, a re-file OUT, a de-substitution or an un-inheritance
    # leaves it empty and a person involved.
    return RETURNED, None


def _rejected(conn, dataset_id: str, supply: str) -> bool:
    """Whether this supply is no longer waiting: a person or the rule
    rejected it, or a newer version superseded it (REQ-PIPE-118)."""
    from qa_tools.common import supersession

    return bool(conn.execute(
        f"SELECT 1 FROM {decision_log.TABLE} WHERE dataset_id = ? AND supply = ? "
        "AND action = ? LIMIT 1", [dataset_id, supply, decision_log.REJECT]).fetchall()
    ) or supersession.is_superseded(conn, dataset_id, supply)


def filings_by_period(conn, dataset_id: str, filings: list[dict]) -> dict:
    """{period: the filing that speaks for it} for this dataset.

    THE LATEST LIVE FILING, NOT THE LATEST FILING (post-build-review
    #109, F3): after a newer supply was rejected and the older one brought
    back from superseded, the latest filing names the rejected one and the
    slot hid the supply actually waiting. Where every filing to a period
    is rejected or superseded the latest still speaks for it, so a period
    with a decided supply is never read as having had no delivery.
    """
    out: dict = {}
    for f in filings:
        slot = f.get("slot")
        if not slot:
            continue
        live = not _rejected(conn, dataset_id, f.get("supply_id") or "")
        current = out.get(slot)
        if current is None or live or not current[1]:
            out[slot] = (f, live)
    return {slot: f for slot, (f, _) in out.items()}


def _amber_waiting(conn, dataset_id: str, supply: str | None) -> bool:
    """Whether the rule stood back from this supply because it is amber
    and its setting was hold - read from what the rule RECORDED
    (REQ-PIPE-122 criterion 5), never from the setting in force now."""
    if not supply:
        return False
    return bool(conn.execute(
        f"SELECT 1 FROM {decision_log.TABLE} WHERE dataset_id = ? AND supply = ? "
        "AND action = ? AND amber_setting = 'hold' LIMIT 1",
        [dataset_id, supply, decision_log.PROMOTION_WITHHELD]).fetchall())


def state_of(conn: supply_db.SupplyConnection, *, dataset_id: str, slot,
             now: datetime, filings: dict, ever_delivered: bool,
             held: bool = False) -> SlotState:
    """Where this slot's supply has got to.

    `slot` is a slots.Slot; `filings` is {period: filing record} for
    this dataset, which the caller reads once rather than per slot.
    `ever_delivered` is criterion 8's second half - whether this dataset
    has had ANY delivery - and is passed in because it is one question
    about the dataset rather than one per slot.

    THE ORDER IS THE POINT. A decision outranks a filing, and a filing
    outranks the clock: a slot with a promoted supply is not overdue
    however late it was, and a slot with a supply awaiting a decision is
    waiting for a PERSON rather than for a supplier. Asking the clock
    first is how a queue tells somebody to chase a file that is sitting
    in front of them.
    """
    from qa_tools.common import slots as slots_mod

    # THE LAST DECISION THAT CHANGED THE SLOT, from qa.slot_holds
    # (REQ-PIPE-130 criterion 9) - not the last one naming it, which can
    # be about another supply or a refusal (post-build-review #84).
    h = decision_log.held(conn, dataset_id, slot.name)
    closed = slots_mod.is_closed(slot, now)
    if h:
        state, supply = _state_from(h)
        if supply is None:
            # An emptied slot names the supply that was taken out.
            supply = conn.execute(
                f"SELECT supply FROM {decision_log.TABLE} WHERE id = ?",
                [h.decision_id]).fetchall()[0][0]
        unfilled = h.held_as is None
        # A SUPPLY WAITING IN AN EMPTIED SLOT outranks the decision that
        # emptied it (REQ-PIPE-132 criterion 3; delivery-critic #105): a
        # resupply filed after a rejection is a supply awaiting a decision,
        # not a period with nothing in it, closed or not. A supply that was
        # itself demoted back out stays RETURNED, but is not a gap either -
        # it is still here, waiting on the person who put it back.
        waiting = filings.get(slot.name)
        waiting_supply = (waiting or {}).get("supply_id")
        if unfilled and waiting_supply and not _rejected(conn, dataset_id, waiting_supply):
            return SlotState(
                dataset_id=dataset_id, period=slot.name,
                # AN AMBER SUPPLY UNDER HOLD keeps its own state here too
                # (delivery-critic on REQ-PIPE-122, F1): this branch used to
                # say AWAITING_DECISION, the red supply's state.
                state=(state if waiting_supply == supply
                       else AMBER_WAITING if _amber_waiting(conn, dataset_id, waiting_supply)
                       else AWAITING_DECISION),
                supply=waiting_supply, decided_by=_decider(conn, h.decision_id),
                reason=_reason(conn, h.decision_id), closed=False)
        if state == PROMOTED:
            from qa_tools.common import acknowledgement

            if acknowledgement.owed(conn, dataset_id, slot.name) == supply:
                state = AWAITING_ACKNOWLEDGEMENT
        if unfilled and closed:
            accepted = _accepted(conn, dataset_id, slot.name)
            if accepted:
                return accepted
        return SlotState(
            dataset_id=dataset_id, period=slot.name, state=state,
            supply=supply, stands_on=h.stands_on if h.held_as else None,
            decided_by=_decider(conn, h.decision_id),
            reason=_reason(conn, h.decision_id), closed=unfilled and closed)

    filed = filings.get(slot.name)
    if held:
        return SlotState(dataset_id=dataset_id, period=slot.name, state=HELD,
                          supply=(filed or {}).get("supply_id"))
    if filed and not _rejected(conn, dataset_id, filed.get("supply_id") or ""):
        # AWAITING A DECISION, closed or not (REQ-PIPE-132 criterion 3): a
        # supply is here, so the period is not unsupplied. Not a superseded
        # one (post-build-review #109, F4), which is waiting on nobody.
        supply = filed.get("supply_id")
        return SlotState(dataset_id=dataset_id, period=slot.name,
                          state=AMBER_WAITING if _amber_waiting(conn, dataset_id, supply)
                          else AWAITING_DECISION, supply=supply)

    if slots_mod.is_overdue(slot, now, filled=False):
        if closed:
            accepted = _accepted(conn, dataset_id, slot.name)
            if accepted:
                return accepted
        return SlotState(dataset_id=dataset_id, period=slot.name,
                          state=OVERDUE if ever_delivered else NEVER_SUPPLIED,
                          closed=closed)
    return SlotState(dataset_id=dataset_id, period=slot.name, state=NOT_YET_DUE)


def _accepted(conn, dataset_id: str, period: str) -> SlotState | None:
    """NOT SUPPLIED (ACCEPTED), where a person marked this closed,
    unfilled slot (REQ-PIPE-132 criterion 9)."""
    from qa_tools.common import not_supplied

    m = not_supplied.marked(conn, dataset_id, period)
    if m is None:
        return None
    return SlotState(dataset_id=dataset_id, period=period, state=NOT_SUPPLIED_ACCEPTED,
                     decided_by=m.actor, reason=m.reason, closed=True)


def _decider(conn, decision_id) -> str | None:
    """Who decided, where a person did - from the decision that last
    CHANGED the slot.

    None for anything a RULE did - an automatic promotion, an
    inheritance - because naming the rule as though it were a person
    puts a decision on somebody who never made one.
    """
    if decision_id is None:
        return None
    rows = conn.execute(
        f"SELECT actor, actor_kind FROM {decision_log.TABLE} WHERE id = ?",
        [decision_id]).fetchall()
    if not rows:
        return None
    actor, kind = rows[0]
    return actor if kind == decision_log.PERSON else None


def _reason(conn, decision_id) -> str:
    if decision_id is None:
        return ""
    rows = conn.execute(
        f"SELECT reason FROM {decision_log.TABLE} WHERE id = ?",
        [decision_id]).fetchall()
    return (rows[0][0] or "") if rows else ""


def states_for(conn: supply_db.SupplyConnection, collection_id: str, *,
               now: datetime | None = None) -> list[SlotState]:
    """Every slot this collection is responsible for, and where each has
    got to (REQ-PIPE-083 criterion 13).

    EVERY SLOT, NOT ONLY THE ONES A RUN TOUCHED. The criterion says so,
    and the reason is the state that nothing touches: a slot nobody
    delivered for is exactly the one that needs a ticket, and a pass
    scoped to what just arrived can never see it. It is also what makes
    the three triggers give one answer (criterion 22) - a pass that
    looked at what a run touched would depend on which run called it.

    BOUNDED AT TODAY. A daily calendar generates periods without end, so
    there is no "every slot" without a bound - and a slot in the future
    cannot need anything, because nothing is late until it is due.

    A HELD SUPPLY HAS NO SLOT AND SO HAS NO TICKET, which is worth
    saying rather than leaving as an omission: REQ-PIPE-059 refuses to
    choose between two files for one dataset, so a held supply was never
    filed to a period, so there is no slot for a ticket to be about.
    They surface through REQ-PIPE-064's own aggregation instead, which
    counts them together for the reason a ticket each would fail at
    thirty datasets.
    """
    from qa_tools.common import asset_time, filing, hierarchy
    from qa_tools.common import slots as slots_mod

    now = now or asset_time.now()
    out: list[SlotState] = []
    for entry in hierarchy.datasets_in_collection(collection_id):
        try:
            # THE SAME BOUND FILING USES (post-build-review #73), and
            # it has to be the same one: once a supply can be FILED to
            # a slot whose window has opened but whose period has not
            # begun, it can be promoted into it - and a slot this list
            # stops short of is a filled slot the page cannot show. The
            # early supply would be accepted and then invisible.
            dataset_slots = slots_mod.slots_for_dataset(
                entry.dataset_id,
                until=slots_mod.claimable_until(entry.dataset_id, now.date()))
        except (ValueError, KeyError, FileNotFoundError) as exc:
            # The blast-radius rule this batch applies everywhere: one
            # dataset whose schedule cannot be built must not cost the
            # other twenty-nine their tickets.
            print(f"note: {entry.dataset_id} has no slots to reconcile "
                  f"({type(exc).__name__}: {exc}).")
            continue
        filings = filings_by_period(conn, entry.dataset_id, filing.filings_of(entry.dataset_id))
        ever = bool(filing.filings_of(entry.dataset_id))
        for slot in dataset_slots:
            out.append(state_of(conn, dataset_id=entry.dataset_id, slot=slot,
                                 now=now, filings=filings, ever_delivered=ever))
    return out
