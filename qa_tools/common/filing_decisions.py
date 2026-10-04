"""One implementation of every filing decision, whoever raises it
(REQ-GHUB-082 criterion 13).

THERE ARE TWO OPERATOR ROUTES - a GitHub ticket and the terminal - and
criterion 3 says they SHALL write an identical entry and SHALL NOT give
either an operation the other lacks. That is not something two
implementations can be held to; it is something ONE implementation makes
true, with each route as an adapter that decides only who is asking and
what they asked for.

WHAT AN ADAPTER DOES, therefore, is small on purpose: identify the
person, read the operation and its arguments, call `apply`, and render
what comes back. Everything a decision MEANS - who may raise it, whether
it needs a reason, whether the filing rules permit it, whether it would
change anything at all, and what to say when it would not - lives here,
once. Criterion 24 says the two routes must never disagree about what is
permitted; there is only one place for them to agree.

THE JUDGEMENT IS NOT HERE, and that is deliberate (criterion 20). It is
in decision_log._judge(), inside the transaction that appends the entry,
because whether a slot is already filled is a fact about other rows and
a caller who checked a moment ago may be wrong by now. This module
refuses what it can answer without the log - an unknown actor, a missing
reason, an operation nobody offers - and lets the log refuse the rest at
the instant it matters.

A NO-OP IS NOT A REFUSAL (criterion 26). Promoting a supply already
promoted into that slot, de-substituting a period that holds no
substitution, un-inheriting one that never inherited: each of those is
an operator arriving at a state that already holds, which happens
constantly when two people look at the same ticket. Reporting it as a
failure teaches them to ignore failures.
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import (decision_log, hierarchy, inheritance, people,
                             promotion, rejection, substitution, supply_db)

#: The eight operations criterion 1 names, and the vocabulary both
#: routes speak. They are the decision log's own action names rather
#: than a second set mapped onto them - a route's word for something
#: should be the word the log records, or a reader has to translate.
PROMOTE = decision_log.PROMOTE
REJECT = decision_log.REJECT
DEMOTE = decision_log.DEMOTE
REFILE = decision_log.REFILE
SUBSTITUTE = decision_log.SUBSTITUTE
DE_SUBSTITUTE = decision_log.DE_SUBSTITUTE
INHERIT = decision_log.INHERIT
UN_INHERIT = decision_log.UN_INHERIT
#: The ninth (REQ-PIPE-132 criterion 4): accept that a closed period was
#: not supplied. Period-scoped, person only, changes no data.
MARK_NOT_SUPPLIED = decision_log.MARK_NOT_SUPPLIED
#: The tenth (REQ-PIPE-122 criterion 13): acknowledge an amber supply
#: promoted under promote-and-acknowledge. Supply-scoped, person only,
#: reason required, changes no data.
ACKNOWLEDGE = decision_log.ACKNOWLEDGE

OPERATIONS = (PROMOTE, REJECT, DEMOTE, REFILE, SUBSTITUTE, DE_SUBSTITUTE,
              INHERIT, UN_INHERIT, MARK_NOT_SUPPLIED, ACKNOWLEDGE)

#: The four that act on a SUPPLY - "what do I do with this thing that
#: arrived" - and so belong in the queue of supplies awaiting a decision
#: (criterion 16).
SUPPLY_SCOPED = (PROMOTE, REJECT, DEMOTE, REFILE, ACKNOWLEDGE)

#: The four that act on a PERIOD - how it is filled when a supply for it
#: never came. None of them answers a question about an arriving supply,
#: which is why criterion 31 puts them somewhere else entirely.
PERIOD_SCOPED = (SUBSTITUTE, DE_SUBSTITUTE, INHERIT, UN_INHERIT, MARK_NOT_SUPPLIED)

#: Which operations destroy something a reader depends on, and so need
#: an explicit confirmation on every route (criteria 9 and 28, and
#: REQ-PIPE-099 criterion 10). The TUI confirms EVERYTHING (criterion
#: 28); these are the ones the underlying operation refuses without it,
#: so a route that forgot to ask is refused rather than obeyed.
NEEDS_CONFIRMATION = (REFILE, DE_SUBSTITUTE, UN_INHERIT)


class NotOffered(Exception):
    """An operation neither route offers.

    SEPARATE FROM DecisionRefused because the answers differ: a refusal
    means "this decision is not permitted and here is why", which an
    operator can act on, and this means "that is not a thing", which is
    usually a typo in a comment.
    """


@dataclass(frozen=True)
class Request:
    """What somebody asked for, before anybody has decided whether it is
    allowed.

    FROZEN, and carrying the ACTOR RECORD rather than a name, so that
    the actor written into the log is the one that was identified rather
    than a string that travelled alongside. Criterion 4's "SHALL NOT
    accept an actor stated in the body" is enforced by the GitHub
    adapter having nowhere to put one.
    """

    operation: str
    dataset_id: str
    actor: dict
    reason: str
    #: The period the decision concerns. Every operation names one:
    #: which slot a supply is promoted into, rejected out of, or which
    #: period is being substituted or inherited.
    period: str | None = None
    #: A re-file's destination, and nothing else's.
    to_period: str | None = None
    #: The supply being acted on, where the operation acts on one.
    supply: str | None = None
    #: The period a substitution stands on.
    stands_on: str | None = None
    confirmed: bool = False

    @property
    def actor_name(self) -> str:
        return people.actor_name(self.actor)


@dataclass(frozen=True)
class Outcome:
    """What happened, in the terms both routes report in.

    `changed` IS THE FIELD THAT MATTERS. A decision that changed nothing
    because the log already recorded that outcome is a success with
    `changed=False` - never a refusal (criterion 26) - and a route that
    tells an operator "already done" is telling them something true and
    useful. `ticket_reconciler` is only called where something changed,
    for the same reason REQ-GHUB-109 gave: a ticket that says something
    new, or says nothing.
    """

    operation: str
    dataset_id: str
    period: str | None
    changed: bool
    message: str


def offered(operation: str) -> str:
    """The operation, or a refusal naming what is on offer.

    THE SAME EIGHT ON BOTH ROUTES (criterion 3's second half), which is
    a property of there being one list rather than a promise two
    adapters make.
    """
    if operation not in OPERATIONS:
        raise NotOffered(
            f"{operation!r} is not a filing decision. The {len(OPERATIONS)} are: "
            f"{', '.join(OPERATIONS)}.")
    return operation


def _reason(request: Request) -> str:
    """Criterion 10: a PERSON raising a decision gives a reason, and is
    refused without one.

    UNCONDITIONALLY, which is stricter than the decision log's own rule
    - that one asks for a reason where somebody will ask why a year
    later, and lets a routine automatic promotion go without. This is
    about a person: they are here, they are deciding something, and the
    cost of a sentence is nothing against a log entry nobody can
    explain.
    """
    reason = (request.reason or "").strip()
    if not reason:
        raise decision_log.DecisionRefused(
            f"a {request.operation} needs a reason. You are deciding this on "
            f"purpose, and somebody will ask why - this log is where they "
            f"will look.")
    return reason


def _confirmation(request: Request) -> None:
    """Criteria 9 and 28: the destructive ones are confirmed explicitly.

    REFUSED HERE AS WELL AS BY THE OPERATION, so a route that forgot to
    ask gets the same answer wherever it forgot. The operations below
    take `confirmed` as a required argument for the same reason: a
    prompt inside a function is skipped by the first caller that is not
    a terminal.
    """
    if request.operation in NEEDS_CONFIRMATION and not request.confirmed:
        raise decision_log.DecisionRefused(
            f"a {request.operation} needs an explicit confirmation. It changes "
            f"what a period resolves to for everybody reading it.")


def _already(conn, request: Request) -> str | None:
    """The sentence to say where this decision would change nothing, or
    None (criterion 26).

    ASKED OF THE LOG, never of the catalogue, for the reason every other
    question in this system is: a view in a schema says an object
    exists, not what put it there or whether somebody has since removed
    the indirection and left the object behind.
    """
    period = request.period
    if period is None:
        return None
    holds = decision_log.held(conn, request.dataset_id, period)

    if request.operation == PROMOTE:
        if decision_log.promoted_into(conn, request.dataset_id, period) == request.supply:
            return (f"{request.supply} is already promoted into {period}. "
                    f"Nothing to do.")
    elif request.operation == SUBSTITUTE:
        current = substitution.substituted(conn, request.dataset_id, period)
        if current is not None and current.stands_on == request.stands_on:
            return (f"{period} already stands on {request.stands_on}, by a "
                    f"substitution somebody already recorded. Nothing to do.")
    elif request.operation == INHERIT:
        if inheritance.inherited(conn, request.dataset_id, period) is not None:
            return f"{period} already inherits. Nothing to do."
    elif request.operation == DE_SUBSTITUTE:
        if substitution.substituted(conn, request.dataset_id, period) is None:
            return (f"{period} holds no substitution for {request.dataset_id}. "
                    f"Either it was never substituted or somebody has already "
                    f"removed it.")
    elif request.operation == MARK_NOT_SUPPLIED:
        from qa_tools.common import not_supplied

        already = not_supplied.marked(conn, request.dataset_id, period)
        if already is not None:
            return (f"{period} is already marked as not supplied for "
                    f"{request.dataset_id}, by {already.actor}. Nothing to do.")
    elif request.operation == UN_INHERIT:
        if inheritance.inherited(conn, request.dataset_id, period) is None:
            # NOT where it holds a SUBSTITUTION - that is a real
            # refusal, because the two are identical in SQL and opposite
            # in meaning and the operator has asked to undo the wrong
            # one. inheritance.un_inherit() says so in those words.
            if not (holds and holds.held_as == decision_log.SUBSTITUTED):
                return (f"{period} holds no inheritance for "
                        f"{request.dataset_id}. Nothing to do.")
    return None


def _apply_one(conn, request: Request, reason: str, *, effective_at: str) -> None:
    """Dispatch to the operation that owns this decision's effect.

    EVERY ONE OF THESE ALREADY EXISTS, and nothing here re-implements
    any of them. That is what makes this a single implementation rather
    than a third place a promotion could be defined: the module that
    owns the warehouse change owns it, and this decides only which one
    is being asked for.
    """
    entry = hierarchy.dataset(request.dataset_id)
    common = {"agency_id": entry.agency_id, "collection_id": entry.collection_id,
              "dataset_id": request.dataset_id, "actor": request.actor_name,
              "reason": reason, "effective_at": effective_at}

    if request.operation == PROMOTE:
        promotion.promote(
            conn, supply=request.supply, period=request.period,
            physical_tables=_staged(conn, entry.table, request.supply),
            actor_kind=decision_log.PERSON, **common)
    elif request.operation == REJECT:
        rejection.reject(
            conn, supply=request.supply, from_slot=request.period,
            physical_tables=_staged(conn, entry.table, request.supply),
            promoted=_is_promoted(conn, request), **common)
    elif request.operation == DEMOTE:
        rejection.demote(
            conn, supply=request.supply, from_slot=request.period,
            physical_tables=_promoted_tables(conn, entry.table, request), **common)
    elif request.operation == SUBSTITUTE:
        substitution.substitute(
            conn, logical_table=entry.table, period=request.period,
            stands_on=request.stands_on, supply=request.supply, **common)
    elif request.operation == DE_SUBSTITUTE:
        substitution.de_substitute(
            conn, logical_table=entry.table, period=request.period,
            confirmed=True, **common)
    elif request.operation == INHERIT:
        inheritance.inherit_one(
            conn, dataset_id=request.dataset_id, period=request.period,
            actor=request.actor_name, reason=reason, effective_at=effective_at)
    elif request.operation == MARK_NOT_SUPPLIED:
        from qa_tools.common import not_supplied

        not_supplied.mark(
            conn, agency_id=entry.agency_id, collection_id=entry.collection_id,
            dataset_id=request.dataset_id, period=request.period,
            actor=request.actor_name, reason=reason, effective_at=effective_at)
    elif request.operation == ACKNOWLEDGE:
        # CHANGES NO DATA (REQ-PIPE-122 criterion 15): one entry, nothing
        # moved. Whether it is owed is the log's to judge, inside the
        # transaction (criterion 14).
        with decision_log.apply_decision(conn, decision_log.Decision(
                agency_id=entry.agency_id, collection_id=entry.collection_id,
                dataset_id=request.dataset_id, action=decision_log.ACKNOWLEDGE,
                supply=request.supply, actor=request.actor_name,
                actor_kind=decision_log.PERSON, effective_at=effective_at,
                to_slot=request.period, reason=reason)):
            pass
    elif request.operation == UN_INHERIT:
        inheritance.un_inherit(
            conn, dataset_id=request.dataset_id, period=request.period,
            actor=request.actor_name, reason=reason, effective_at=effective_at,
            confirmed=True)
    else:
        # REFILE, and it is UNBUILT rather than forgotten. The other
        # seven each have a module that owns their warehouse change;
        # filing.refile() moves the FILING RECORD and writes no
        # decision-log entry at all, and what should happen to a
        # PROMOTED supply's tables when it is re-filed belongs to
        # REQ-PIPE-079's wiring. Inventing it in this dispatcher would
        # put the answer in the one place nobody would look for it.
        raise NotOffered(
            f"{request.operation} is one of the eight and its effect is not "
            f"built yet: filing.refile() moves the filing record and writes "
            f"no decision-log entry. What happens to a promoted supply's "
            f"tables on a re-file is REQ-PIPE-079's wiring. The other seven "
            f"operations work.")


def _staged(conn, logical: str, supply: str) -> list[str]:
    """The physical tables this supply has in staging."""
    arrival = (supply or "").rsplit("@", 1)[-1]
    found = supply_db.candidates_in(
        conn, supply_db.STAGING_SCHEMA, [logical], arrival=arrival).get(logical) or []
    return list(found)


def _promoted_tables(conn, logical: str, request: Request) -> list[str]:
    """The physical tables a period holds for this dataset."""
    from qa_tools.common import period_schema

    return list(period_schema.promoted_in(
        conn, request.period, [logical]).get(logical) or [])


def _is_promoted(conn, request: Request) -> bool:
    return decision_log.promoted_into(
        conn, request.dataset_id, request.period) == request.supply


def _refuse_promoting_what_never_loaded(conn, request: Request) -> None:
    """REQ-PIPE-153 criterion 6: a supply whose current load record is
    FAILED cannot be promoted, on any route. Promotion moves the tables it
    is given - none - and would record a period filled by a supply nothing
    can read. Refused naming the failed load and its recorded reason, and
    before anything is written."""
    if request.operation != PROMOTE or "@" not in (request.supply or ""):
        return
    from qa_tools.common import load_log

    key = request.supply.rsplit("@", 1)[1].split("#", 1)[0]
    try:
        table = hierarchy.dataset(request.dataset_id).table
    except hierarchy.UnknownDatasetError:
        return
    for physical, record in load_log.latest_by_table(conn=conn).items():
        parts = supply_db.split_staged(physical)
        if (parts and parts[0] == table and parts[1] == key
                and record.dataset_id == request.dataset_id and not record.loaded):
            why = record.reason or "no reason was recorded"
            raise decision_log.DecisionRefused(
                f"{request.supply} could not be loaded ({why}), so there is nothing "
                f"to promote. Reject it, or fix the fault and reprocess the delivery. "
                f"Nothing was recorded.")


def apply(request: Request, *, effective_at: str, conn=None) -> Outcome:
    """Raise one filing decision, from whichever route.

    THE ORDER IS THE REQUIREMENT read in sequence: is this a thing
    (criterion 3), may this person do it (6, 14), did they say why (10),
    did they confirm it (9, 28), would it change anything (26), and only
    then the effect - whose own judgement, inside the transaction, is
    criteria 20 and 21.

    THE TICKET IS RECONCILED BY REQ-PIPE-083's OWN PASS (criterion 8),
    not by anything composed here. A decision taken in the terminal
    appears on its ticket the same way one raised on the ticket does,
    said once and in the same words - which is a property of there being
    one writer rather than a promise two of them keep.
    """
    offered(request.operation)
    if not request.actor:
        raise people.UnknownActor(
            "a filing decision needs an identified person. Nobody raised this.")
    reason = _reason(request)
    _confirmation(request)

    if conn is None:
        with supply_db.connect(label="mothman:filing-decision") as opened:
            return apply(request, effective_at=effective_at, conn=opened)

    _refuse_promoting_what_never_loaded(conn, request)
    already = _already(conn, request)
    if already is not None:
        return Outcome(operation=request.operation, dataset_id=request.dataset_id,
                        period=request.period, changed=False, message=already)

    _apply_one(conn, request, reason, effective_at=effective_at)
    return Outcome(
        operation=request.operation, dataset_id=request.dataset_id,
        period=request.period, changed=True,
        message=(f"{request.operation} recorded for {request.dataset_id} "
                 f"{request.period or ''}".strip() + f", by {request.actor_name}."))


def reconcile_after(outcome: Outcome, collection_id: str) -> None:
    """Bring the slot's ticket up to date, through REQ-PIPE-083's pass.

    ONLY WHERE SOMETHING CHANGED. A no-op leaves the log exactly as the
    last pass found it, so the pass would correctly find nothing changed
    and say nothing - running it would be work to produce silence.

    NEVER FAILS THE DECISION. The entry is committed by the time this
    runs; an unreachable ticket service is a ticket that is a pass
    behind, which the next pass fixes, and losing the decision over it
    would be the wrong trade in the wrong direction.
    """
    if not outcome.changed:
        return
    from qa_tools.common import ticket_reconciler

    try:
        ticket_reconciler.report(ticket_reconciler.after_runs(collection_id))
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"note: the decision is recorded; its ticket could not be "
              f"reconciled ({type(exc).__name__}: {exc}). The next pass will "
              f"pick it up.")
