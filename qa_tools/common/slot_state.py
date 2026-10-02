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

#: The states that need a person, and so the ones the default
#: `needs-action` ticket policy opens a ticket for (criterion 21).
#: PROMOTED and NOT_YET_DUE are the two that do not: one is finished and
#: the other has not started.
NEEDS_ACTION = frozenset({
    OVERDUE, NEVER_SUPPLIED, AWAITING_DECISION, RETURNED, HELD, REJECTED,
})

#: What a person can do about each. Criterion 9 asks for the responses
#: to be NAMED on the ticket, and naming is all this does - the
#: reconciler offers no buttons, because a route that does nothing is
#: worse than no route.
RESPONSES = {
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

    @property
    def needs_action(self) -> bool:
        return self.state in NEEDS_ACTION

    @property
    def responses(self) -> tuple[str, ...]:
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


def _state_from_decision(latest) -> tuple[str, str | None]:
    """The state a decision leaves a slot in, and the supply it names."""
    action, supply, _stands_on = latest
    if action in (decision_log.PROMOTE, decision_log.REFILE):
        return PROMOTED, supply
    if action == decision_log.REJECT:
        return REJECTED, supply
    if action == decision_log.SUBSTITUTE:
        return SUBSTITUTED, supply
    if action == decision_log.INHERIT:
        return INHERITED, supply
    if action == decision_log.INHERIT_REFUSED:
        # The rule tried and had nothing to stand on. The period is as
        # empty as it was, so the schedule decides what to say about it.
        return "", None
    # A demote or a re-file OUT leaves it empty and a person involved.
    return RETURNED, supply


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

    latest = decision_log.latest_for_slot(conn, dataset_id, slot.name)
    if latest:
        state, supply = _state_from_decision(latest)
        if state:
            return SlotState(
                dataset_id=dataset_id, period=slot.name, state=state,
                supply=supply, stands_on=latest[2],
                decided_by=_decider(conn, dataset_id, slot.name, state),
                reason=_reason(conn, dataset_id, slot.name))

    filed = filings.get(slot.name)
    if held:
        return SlotState(dataset_id=dataset_id, period=slot.name, state=HELD,
                          supply=(filed or {}).get("supply_id"))
    if filed:
        return SlotState(dataset_id=dataset_id, period=slot.name,
                          state=AWAITING_DECISION, supply=filed.get("supply_id"))

    if slots_mod.is_overdue(slot, now, filled=False):
        return SlotState(dataset_id=dataset_id, period=slot.name,
                          state=OVERDUE if ever_delivered else NEVER_SUPPLIED)
    return SlotState(dataset_id=dataset_id, period=slot.name, state=NOT_YET_DUE)


def _decider(conn, dataset_id: str, slot: str, state: str) -> str | None:
    """Who decided, where a person did.

    None for anything a RULE did - an automatic promotion, an
    inheritance - because naming the rule as though it were a person
    puts a decision on somebody who never made one.
    """
    rows = conn.execute(
        f"SELECT actor, actor_kind FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND (to_slot = ? OR from_slot = ?) "
        "ORDER BY effective_at DESC, id DESC LIMIT 1",
        [dataset_id, slot, slot]).fetchall()
    if not rows:
        return None
    actor, kind = rows[0]
    return actor if kind == decision_log.PERSON else None


def _reason(conn, dataset_id: str, slot: str) -> str:
    rows = conn.execute(
        f"SELECT reason FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND (to_slot = ? OR from_slot = ?) "
        "ORDER BY effective_at DESC, id DESC LIMIT 1",
        [dataset_id, slot, slot]).fetchall()
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
        filings = {f["slot"]: f for f in filing.filings_of(entry.dataset_id)
                    if f.get("slot")}
        ever = bool(filing.filings_of(entry.dataset_id))
        for slot in dataset_slots:
            out.append(state_of(conn, dataset_id=entry.dataset_id, slot=slot,
                                 now=now, filings=filings, ever_delivered=ever))
    return out
