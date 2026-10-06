"""The decision log: who decided what happened to a supply, and when
(REQ-PIPE-091, carrying REQ-PIPE-074's content).

WHAT A FILING DECISION IS. A supply arrives, gets staged, gets checked -
and then somebody decides what the warehouse should actually use. Promote
it into a period, reject it, demote what is already there, or re-file it
into a different period than the one it landed in. Those four are the
decisions, and this is the one record of them.

WHY IT IS A TABLE AND NOT A COMMITTED TREE, which is the whole of this
requirement rather than a storage preference. The effect of a decision is
a change to the warehouse. Put the record somewhere else - files in git,
as REQ-PIPE-074 originally specified - and the two can be observed
apart: the promotion succeeds and the commit fails, or the reverse, and
the log then says something that never happened or fails to say something
that did. No amount of care fixes that, because there is no mechanism
that makes a git commit and a database write atomic. In the same
database, there is one: a transaction.

So `apply_decision()` is a CONTEXT MANAGER rather than a function taking
the entry, and that shape is the requirement. The caller's own warehouse
work happens inside the `with`, in the same transaction that wrote the
entry, and if it raises, the entry goes with it.

WHAT IS JUDGED, AND WHERE. Whether a decision is permitted depends on the
log as it stands - whether that slot already has a promoted supply, most
importantly - so the judgement happens INSIDE the transaction, after the
lock, against rows nothing else can be changing. Judging first and
writing second, outside a transaction, is the classic check-then-act
race, and the thing it would let through is exactly what the story names:
two people both told yes for the same slot.

THE LOCK IS ON THE SLOT, not on the supply, and the difference is the
failure being prevented. Two decisions about the SAME supply obviously
have to serialise (criterion 4). But two decisions about DIFFERENT
supplies competing for the same slot are the dangerous pair, and locking
on the supply would let them both through. So the key is the dataset and
the slot, and a decision naming two slots takes both, in sorted order -
unsorted, two concurrent re-files in opposite directions deadlock.

APPEND-ONLY IS THE DATABASE'S JOB, not this module's (criterion 5). See
qa_store's DDL: a trigger raises on UPDATE, DELETE and TRUNCATE, so the
guarantee holds against code that never imports this file. Nothing here
offers an edit or a delete either, but that is politeness rather than the
mechanism.

NO QUEUE, NO SPOOL, NO RETRY FILE (criterion 8). If the database is
unreachable the decision is refused and says so. This is a deliberate
loss of an offline promise REQ-PIPE-074 made, on Keith's own reasoning
(2026-09-26): a filing decision acts on the warehouse, so a decision
recorded while the warehouse was unreachable is a decision about nothing.
In production the engineer is inside the network where the database
lives, which makes it plausibly more reachable than GitHub was.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from qa_tools.common import qa_store, supply_db, supply_holds

TABLE = f'"{qa_store.SCHEMA}".decision'

#: The four filing decisions (REQ-PIPE-074 criterion 1). A re-file is one
#: of them rather than a demote-then-promote pair - see the DDL.
PROMOTE = "promote"
REJECT = "reject"
DEMOTE = "demote"
REFILE = "refile"

#: The two SUBSTITUTION decisions (REQ-PIPE-084). They are filing
#: decisions like the four above and live in the same log, because the
#: question they answer is the same one - what does this period resolve
#: to, and who said so - and a second log would be a second answer.
#:
#: WHAT MAKES THEM DIFFERENT IN SHAPE: a substitution acts on a period
#: rather than on a supply's position. `to_slot` is the period being
#: substituted, `supply` is the PROMOTED physical table it will resolve
#: to, and `stands_on` is the period that table lives in. A
#: de-substitution names only `from_slot`, the period whose indirection
#: is being removed, which is what leaves it unfilled.
SUBSTITUTE = "substitute"
DE_SUBSTITUTE = "de-substitute"

#: INHERITANCE (REQ-PIPE-098), and it is kept apart from substitution on
#: purpose (criterion 12). They look alike in SQL - both are a view in a
#: period's schema pointing at an earlier promoted table - and they mean
#: opposite things. A substitution says a supply was OWED and did not
#: come, and a person decided what to stand on. An inheritance says
#: nothing was owed at all, and the rule filled the period with what is
#: still current. Collapsing them would lose the distinction between a
#: supplier who missed a quarter and one who was never due.
INHERIT = "inherit"
#: An inheritance that could not complete, recorded rather than silent
#: (criterion 10). It is the one action with NO supply, because the
#: thing it could not find IS a supply.
INHERIT_REFUSED = "inherit-refused"
#: The operator action that takes an inheritance back out (REQ-PIPE-099
#: criteria 1 and 3). ALWAYS A PERSON'S - the rule inherits, and only a
#: person un-inherits, because what un-inheriting is FOR is freeing a
#: demotion, rejection or re-file the inheritance was blocking. A rule
#: that could undo its own inheritance would quietly remove the
#: obstacle that exists to make somebody look.
UN_INHERIT = "un-inherit"

#: A supply the off-cycle gate withheld from automatic promotion
#: (REQ-PIPE-077 criterion 6). NOTHING WRITES IT ANY MORE: REQ-PIPE-131
#: retired that gate (2026-10-04), because an arrival with no open period
#: is now HELD for a person before it is ever checked. It stays in the
#: vocabulary - and in the table's CHECK constraint - as the one example
#: of an entry that ANNOTATES a slot without changing it, which
#: qa.slot_holds and REQ-PIPE-132 criterion 8 are written against.
#:
#: ALWAYS A RULE'S, and it is the only
#: action here that records something NOT happening to a supply - the
#: same shape as `inherit-refused`, and for the same reason: a refusal
#: nobody recorded is indistinguishable from a rule that never ran.
#:
#: IT IS NOT A REJECTION. Nothing is decided about the supply, and a
#: person may still promote it (criterion 5). What it records is that
#: automation stood back and why.
PROMOTION_WITHHELD = "promotion-withheld"

#: A PERSON'S ACCEPTANCE THAT A CLOSED PERIOD WAS NOT SUPPLIED
#: (REQ-PIPE-132 criterion 4). It ANNOTATES a slot and never changes what
#: it holds (criteria 7 and 8): qa.slot_holds lists only the decisions
#: that change a slot, so this is ignored there by construction. The
#: operational, after-the-fact counterpart of `not_expected` in
#: configuration - that changes what was OWED; this records an obligation
#: that was owed and NOT MET, and stays in the record as such. Like
#: `inherit-refused` it names no supply, because what it is about is the
#: supply that never came.
MARK_NOT_SUPPLIED = "mark-not-supplied"

#: A PERSON'S ACKNOWLEDGEMENT THAT THEY LOOKED AT AN AMBER SUPPLY PROMOTED
#: UNDER promote-and-acknowledge (REQ-PIPE-122 criteria 13 to 16). It
#: ANNOTATES - it changes no data, re-runs nothing and changes nothing a
#: period resolves to (criterion 15), so qa.slot_holds ignores it by
#: construction, like a mark. A reason is required: the reason is what
#: makes it more than a click.
ACKNOWLEDGE = "acknowledge"

#: A LATER VERSION OF THE SAME TABLE FOR THE SAME PERIOD ARRIVED
#: (REQ-PIPE-118). The earlier, unaccepted version moves to its period's
#: `_superseded` schema; nothing is deleted, and it is NOT a rejection - it
#: says nothing about that version's quality. Recorded by the rule on
#: arrival, or by a person (REQ-PIPE-120); `superseded_by` names the newer
#: supply. It changes nothing a period HOLDS - only promoted, substituted
#: and inherited supplies are held, and a promoted one is never superseded
#: here - so qa.slot_holds ignores it by construction.
SUPERSEDE = "supersede"
#: A person brings a superseded supply back to staging (REQ-PIPE-120).
UN_SUPERSEDE = "un-supersede"

#: A RE-EVALUATION LEFT WAITING SUPPLIES FAILING (REQ-PIPE-121 criterion
#: 12): ONE record per causing decision, naming every such supply in its
#: reason and the decision in `caused_by_decision`, at the log's highest
#: prominence - a person must look. Rule only; changes no slot.
STILL_FAILING = "still-failing"
#: The gate looked at a supply and did not promote it (REQ-PIPE-151
#: criterion 3), naming why. A record and nothing more: it changes no slot,
#: answers no hold and is the evidence that the gate RAN on an arrival
#: (criterion 4) - which is how a processing pass knows an arrival is done
#: without keeping a marker of its own.
PROMOTION_REFUSED = "promotion-refused"

ACTIONS = (PROMOTE, REJECT, DEMOTE, REFILE, SUBSTITUTE, DE_SUBSTITUTE,
           INHERIT, INHERIT_REFUSED, UN_INHERIT, PROMOTION_WITHHELD,
           MARK_NOT_SUPPLIED, ACKNOWLEDGE, SUPERSEDE, UN_SUPERSEDE, STILL_FAILING,
           PROMOTION_REFUSED)

#: Actions that name no supply - each is about one that is not there, or
#: (STILL_FAILING) about several.
NO_SUPPLY = (INHERIT_REFUSED, MARK_NOT_SUPPLIED, STILL_FAILING)

#: The actions a RULE may take. Everything else is a person's, and
#: rejection.py and substitution.py enforce that by not offering an
#: actor_kind at all.
AUTOMATIC_ACTIONS = (PROMOTE, INHERIT, INHERIT_REFUSED, PROMOTION_WITHHELD, SUPERSEDE,
                     STILL_FAILING, PROMOTION_REFUSED)

#: The decisions that move a supply, and so are the ones criterion 11
#: refuses while a later period stands on it.
MOVES_A_SUPPLY = (REJECT, DEMOTE, REFILE, SUPERSEDE)

#: Entries that record automation standing back, and so never change what
#: a slot resolves to (post-build-review #84).
RECORDS_A_REFUSAL = (PROMOTION_WITHHELD, INHERIT_REFUSED, PROMOTION_REFUSED)

#: The decisions that make a period DEPEND on another period's supply.
#: BOTH of them, and the second was missed for an hour: an inherited
#: period stands on a supply just as hard as a substituted one - demote
#: the supply and the inherited view points at a table that is no longer
#: there. Found by the sprints gate noticing that REQ-PIPE-076's
#: deferral had had its blockers shipped.
STANDS_ON_A_SUPPLY = (SUBSTITUTE, INHERIT)

#: What kind of thing decided (REQ-PIPE-074 criteria 3 and 4).
PERSON = "person"
RULE = "rule"
ACTOR_KINDS = (PERSON, RULE)


class DecisionRefused(Exception):
    """A decision this log will not record, with the reason in the message.

    ONE EXCEPTION TYPE for every refusal, deliberately. The caller's
    response is the same in all of them - tell the operator what is
    wrong and do not touch the warehouse - and a hierarchy would invite
    catching one branch of it, which is how a refusal becomes a warning.
    """


@dataclass(frozen=True)
class Decision:
    """One filing decision, before it is judged.

    FROZEN, because a decision that can be edited between being judged
    and being written is a decision whose entry need not describe what
    was permitted.
    """

    agency_id: str
    collection_id: str
    dataset_id: str
    action: str
    supply: str
    actor: str
    actor_kind: str
    effective_at: str
    from_slot: str | None = None
    to_slot: str | None = None
    reason: str | None = None
    #: The period a SUBSTITUTION stands on (REQ-PIPE-084 criterion 5).
    #: Never `from_slot`, which means the period a supply is moving out
    #: of - see the column's own comment in qa_store.py.
    stands_on: str | None = None
    #: Whether the supply's own QA verdict was red. Carried on the
    #: decision rather than looked up here, because this module may not
    #: go browsing: the caller has the verdict in hand, and REQ-PIPE-074
    #: criterion 6 needs it to know whether a reason is required.
    supply_is_red: bool = False
    #: THE AMBER SETTING A RULE ACTED UNDER (REQ-PIPE-122 criterion 19):
    #: the resolved value, the level it came from and the version in
    #: effect. Recorded on every automatic promotion of an amber supply,
    #: and on the withheld note when the setting was hold, so the past is
    #: read from what was recorded and never recomputed (criterion 5).
    amber_setting: str | None = None
    amber_level: str | None = None
    amber_version: str | None = None
    #: The newer supply that superseded this one (REQ-PIPE-118 criterion 10).
    superseded_by: str | None = None
    #: The supply's status when it was promoted (REQ-PIPE-130 criterion 11).
    promoted_status: str | None = None
    #: The promoted supply a rule's promotion replaced, and the replacement
    #: setting it acted under (REQ-PIPE-123 criterion 5).
    replaces: str | None = None
    replacement_setting: str | None = None
    replacement_level: str | None = None
    replacement_version: str | None = None
    #: The decision a rule's STILL_FAILING record follows from
    #: (REQ-PIPE-121 criterion 12).
    caused_by_decision: int | None = None
    #: The supply whose promotion opened the period an INHERIT filled
    #: (REQ-TEST-150 criterion 6). None where a person opened it.
    caused_by_supply: str | None = None

    @property
    def slots(self) -> tuple[str, ...]:
        return tuple(s for s in (self.from_slot, self.to_slot) if s)


def _check_shape(decision: Decision) -> None:
    """Everything answerable without looking at the log.

    Checked here as well as by the column constraints, and the
    duplication is on purpose: a CHECK violation arrives as a psycopg
    error naming a constraint, which is the wrong thing to show an
    operator who simply left a field blank.
    """
    if decision.action not in ACTIONS:
        raise DecisionRefused(
            f"{decision.action!r} is not a filing decision - one of {', '.join(ACTIONS)}")
    if decision.actor_kind not in ACTOR_KINDS:
        raise DecisionRefused(
            f"{decision.actor_kind!r} is not an actor kind - one of "
            f"{', '.join(ACTOR_KINDS)}")
    # CRITERION 6, AND THE PART THAT MATTERS IS WHAT IT DOES NOT DO: it
    # does not fall back to the OS user, to a git identity, or to
    # "unknown". An unattributed decision is refused, full stop - the
    # same rule CLAUDE.md records for get_run_by().
    if not (decision.actor or "").strip():
        raise DecisionRefused(
            "a decision needs an actor - who or what decided this. There is no "
            "default and no 'unknown': record who it was, or do not record it.")
    if decision.action not in NO_SUPPLY and not (decision.supply or "").strip():
        raise DecisionRefused("a decision needs the supply it acts on")
    if decision.action == MARK_NOT_SUPPLIED:
        if (decision.supply or "").strip():
            raise DecisionRefused(
                "marking a period as not supplied names no supply - it records "
                "that none came.")
        if decision.actor_kind != PERSON:
            raise DecisionRefused(
                "only a person marks a period as not supplied - it accepts a "
                "missed obligation, which a rule must never do on its own.")
        if not decision.to_slot:
            raise DecisionRefused("marking as not supplied names the period it is about.")
        if not (decision.reason or "").strip():
            raise DecisionRefused(
                "marking a period as not supplied needs a reason - somebody will "
                "ask a year from now why nobody chased it.")
    if decision.action == ACKNOWLEDGE:
        if decision.actor_kind != PERSON:
            raise DecisionRefused(
                "only a person acknowledges an amber supply - it records that "
                "somebody looked, which a rule cannot do.")
        if not decision.to_slot:
            raise DecisionRefused(
                "an acknowledgement names the period the supply is promoted into.")
        if not (decision.reason or "").strip():
            raise DecisionRefused(
                "an acknowledgement needs a reason - what you looked at and why "
                "the amber is acceptable. That is what makes it more than a click.")
    if (decision.action == SUPERSEDE and decision.actor_kind == RULE
            and not (decision.superseded_by or "").strip()):
        raise DecisionRefused(
            "a supersession names the newer supply that superseded this one - "
            "without it nothing can say later what replaced it.")
    if decision.action in (SUPERSEDE, UN_SUPERSEDE) and not decision.from_slot:
        raise DecisionRefused(
            f"a {decision.action} names the period the supply was filed to.")
    if decision.action == INHERIT_REFUSED and (decision.supply or "").strip():
        raise DecisionRefused(
            "a refused inheritance names no supply - that is what it could not "
            "find. Recording one would say the opposite of what happened.")
    if not decision.slots and decision.action != PROMOTION_REFUSED:
        raise DecisionRefused(
            "a decision needs at least one slot - which period it acts on")
    if decision.action == REFILE and not (decision.from_slot and decision.to_slot):
        raise DecisionRefused(
            "a re-file names both slots: the one the supply is in and the one it "
            "is moving to. One entry, not a demotion followed by a promotion.")
    if decision.action == SUBSTITUTE and not (decision.to_slot and decision.stands_on):
        raise DecisionRefused(
            "a substitution names the period being substituted and the period it "
            "stands on. Without the second, nothing can say later what it "
            "depended on.")
    if decision.action == DE_SUBSTITUTE and not decision.from_slot:
        raise DecisionRefused(
            "a de-substitution names the period whose indirection is being "
            "removed, as the slot it empties.")
    if decision.action == INHERIT and not (decision.to_slot and decision.stands_on):
        raise DecisionRefused(
            "an inheritance names the period being filled and the period it "
            "takes the supply from.")
    if decision.action == PROMOTION_REFUSED and not (decision.reason or "").strip():
        raise DecisionRefused(
            "a refused promotion names why - it is the record that the gate ran "
            "and declined, and without a reason it says nothing.")
    if decision.action == PROMOTION_WITHHELD and not decision.to_slot:
        raise DecisionRefused(
            "a withheld promotion names the period the supply was filed to - "
            "that is the slot automation stood back from.")
    if decision.action == PROMOTION_WITHHELD and not (decision.reason or "").strip():
        raise DecisionRefused(
            "a withheld promotion needs a reason. It is the only record that "
            "the rule looked and declined, and a refusal with no explanation "
            "is indistinguishable from a rule that never ran.")
    if decision.action not in (SUBSTITUTE, INHERIT) and decision.stands_on:
        raise DecisionRefused(
            f"only a substitution or an inheritance stands on a period; "
            f"{decision.action!r} does not")


#: How a slot is held, as qa.slot_holds says (REQ-PIPE-130 criterion 9).
#: Readers ask this and never interpret a decision's action themselves.
PROMOTED = "promoted"
SUBSTITUTED = "substituted"
INHERITED = "inherited"


@dataclass(frozen=True)
class Held:
    """What one slot holds, from qa.slot_holds.

    `held_as` is PROMOTED, SUBSTITUTED, INHERITED or None for an empty
    slot; `holder` is the supply holding it (for a substitution or an
    inheritance, the supply it stands on); `decision_id` is the last
    decision that CHANGED the slot - what its state, its reason and who
    decided it are read from; `action` is that decision's action, which
    for an EMPTY slot says how it was emptied (a reject, a demote, a
    re-file out) and is meaningless otherwise; `stands_on` is the period
    an indirection points at.
    """

    held_as: str | None
    holder: str | None
    decision_id: int
    action: str
    stands_on: str | None

    @property
    def filled(self) -> bool:
        return self.held_as in (PROMOTED, SUBSTITUTED)


def held(conn: supply_db.SupplyConnection, dataset_id: str, slot: str,
         as_at: str | None = None) -> Held | None:
    """What this slot holds, as at an instant, or None where no decision
    has ever changed it.

    READ FROM `qa.slot_holds`, THE ONE DEFINITION OF WHAT A SLOT HOLDS
    (REQ-PIPE-130 criteria 8 and 9) - the rule, and why it is the rule,
    is written beside the SQL and nowhere else. `as_at` is about
    `effective_at`, never `recorded_at`: what the warehouse held at that
    moment, not what we knew then.
    """
    return held_all(conn, dataset_id, as_at).get(slot)


def held_all(conn: supply_db.SupplyConnection, dataset_id: str,
             as_at: str | None = None) -> dict[str, Held]:
    """`held()` for every slot of one dataset, in one read."""
    rows = conn.execute(
        f'SELECT h.slot, h.held_as, h.holder, h.decision_id, d.action, d.stands_on '
        f'FROM "{qa_store.SCHEMA}".slot_holds(?, ?) h JOIN {TABLE} d ON d.id = h.decision_id',
        [dataset_id, as_at]).fetchall()
    return {slot: Held(held_as=held_as, holder=holder, decision_id=decision_id,
                       action=action, stands_on=stands_on)
            for slot, held_as, holder, decision_id, action, stands_on in rows}


def promoted_into(conn: supply_db.SupplyConnection, dataset_id: str, slot: str,
                   as_at: str | None = None) -> str | None:
    """The supply this slot resolves to, as at an instant (criterion 9):
    the holder of a promoted or substituted slot, None otherwise. From
    qa.slot_holds - see held()."""
    h = held(conn, dataset_id, slot, as_at)
    return h.holder if h and h.filled else None


def periods_standing_on(conn: supply_db.SupplyConnection, dataset_id: str,
                         supply: str) -> tuple[str, ...]:
    """Every period that CURRENTLY resolves to this supply by substitution.

    REQ-PIPE-084 criterion 11's question, and the reason it is asked of
    the log rather than of the catalogue: a view in a period schema
    tells you a view exists, not whether somebody has since removed the
    indirection and left the object behind.

    CURRENTLY, not ever. A period that was substituted onto this supply
    and has since been de-substituted does not block anything, and
    counting it would make a supply permanently undeletable on the
    strength of a decision somebody already reversed.
    """
    return tuple(slot for slot, _how in _standing_on(conn, dataset_id, supply))


#: How a blocking period is cleared, by how it came to stand on the
#: supply (REQ-GHUB-082 criterion 25). The remedy differs, and telling
#: an operator the wrong one sends them to a route that will refuse
#: them: a SUBSTITUTED period is de-substituted, because a person chose
#: it; an INHERITED one is un-inherited, because the rule did.
UNBLOCKED_BY = {SUBSTITUTE: DE_SUBSTITUTE, INHERIT: UN_INHERIT}


def _standing_on(conn: supply_db.SupplyConnection, dataset_id: str,
                  supply: str) -> tuple[tuple[str, str], ...]:
    """`(period, how)` for every period currently standing on this
    supply, where `how` is SUBSTITUTE or INHERIT.

    The pair rather than the period alone, because the two are cleared
    by different decisions and a refusal that says "clear them first"
    leaves an operator to guess which.
    """
    rows = conn.execute(
        f"SELECT DISTINCT to_slot FROM {TABLE} "
        "WHERE dataset_id = ? AND supply = ? AND action IN (?, ?) "
        "AND to_slot IS NOT NULL",
        [dataset_id, supply, SUBSTITUTE, INHERIT]).fetchall()
    standing = []
    how = {SUBSTITUTED: SUBSTITUTE, INHERITED: INHERIT}
    holds = held_all(conn, dataset_id)
    for (slot,) in rows:
        h = holds.get(slot)
        if h and h.held_as in how and h.holder == supply:
            standing.append((slot, how[h.held_as]))
    return tuple(sorted(standing))


def _judge(conn: supply_db.SupplyConnection, decision: Decision) -> None:
    """Whether this decision is permitted, against the log inside the
    transaction (criterion 3).

    WHAT NEEDS A REASON (REQ-PIPE-074 criteria 6 and 7), and the shape of
    the rule is that a reason is required exactly where somebody a year
    later will ask why:

      - a rejection, because a supplier was told their file was not used
      - promoting a RED supply, because it was known bad and used anyway
      - superseding a supply already promoted into that slot, because
        something downstream changed under whoever was reading it

    A ROUTINE PROMOTION NEEDS NONE, which is criterion 7 and is what
    keeps the requirement honest: demand a reason for everything and the
    reasons become "ok" and the log stops meaning anything.
    """
    needs_reason: str | None = None
    if decision.action == REJECT:
        needs_reason = "rejecting a supply"
    elif decision.action == PROMOTE and decision.supply_is_red:
        needs_reason = "promoting a supply whose checks came back red"
    elif decision.action == PROMOTE and decision.to_slot:
        # (A re-file no longer fills its target - REQ-PIPE-141 - so it
        # supersedes nothing promoted there; it waits to be promoted.)
        # SUPERSESSION IS JUDGED, NOT DECLARED, and this is why the
        # judgement has to be inside the transaction: whether this slot
        # already holds a promoted supply is a fact about other rows, and
        # a caller who checked a moment ago may be wrong by now.
        already = promoted_into(conn, decision.dataset_id, decision.to_slot)
        if already and already != decision.supply:
            needs_reason = (
                f"superseding {already!r}, which is the supply currently promoted "
                f"into {decision.to_slot}")

    if needs_reason and not (decision.reason or "").strip():
        raise DecisionRefused(
            f"{needs_reason} needs a reason. Somebody will ask why a year from "
            "now, and this log is where they will look.")

    if decision.action == PROMOTE:
        # A SUPERSEDED SUPPLY IS NOT PROMOTED (REQ-PIPE-120 criterion 6),
        # judged at the instant the entry is appended - a resend may have
        # landed while somebody was looking at the ticket.
        from qa_tools.common import supersession

        newer = supersession.superseded_by(conn, decision.dataset_id, decision.supply)
        if supersession.is_superseded(conn, decision.dataset_id, decision.supply):
            raise DecisionRefused(
                f"{decision.supply} has been superseded"
                + (f" by {newer}" if newer else " by a person")
                + f". To bring it back first:\n  mothman supply decide --operation "
                f"un-supersede --dataset {decision.dataset_id} --period "
                f"{decision.to_slot} --supply {decision.supply} --reason '<why>' --yes")

    if decision.action == DEMOTE and decision.supply and decision.from_slot:
        # ONLY WHAT THE PERIOD HOLDS IS DEMOTED (#113, REQ-PIPE-129 criteria 4
        # and 7): a demote naming another supply took the period's real table
        # out under that supply's name and left the log and the warehouse
        # disagreeing.
        holder = held(conn, decision.dataset_id, decision.from_slot)
        holding = holder.holder if holder and holder.held_as == PROMOTED else None
        if holding != decision.supply:
            raise DecisionRefused(
                f"{decision.from_slot} does not hold {decision.supply}"
                + (f"; it holds {holding}" if holding else "; nothing is promoted there")
                + ". Check the supply id - `mothman supply slots` shows what each period "
                "holds.")
    if decision.action == DEMOTE and decision.supply and decision.from_slot:
        # ONE WAITING VERSION PER TABLE PER PERIOD (REQ-PIPE-118 criterion
        # 17, Keith 2026-10-05; post-build-review #109 F8). A newer version
        # that arrived while this one was promoted was not superseded - a
        # promoted supply is never superseded - so demoting this one back
        # would leave two versions waiting, and every sibling run would read
        # the table as contested. Judged here, inside the transaction.
        from qa_tools.common import supersession

        waiting = supersession.waiting_in(conn, decision.dataset_id, decision.from_slot,
                                          besides=decision.supply)
        if waiting:
            raise DecisionRefused(
                f"{waiting[0]} is another version of this table, waiting for "
                f"{decision.from_slot}, so demoting {decision.supply} would leave two "
                f"waiting. Reject or supersede {waiting[0]} first: `mothman supply decide "
                f"--operation reject --dataset {decision.dataset_id} --period "
                f"{decision.from_slot} --supply {waiting[0]} --reason '<why>'`, or the "
                f"same with `--operation supersede`.")

    if decision.action in (REJECT, DEMOTE) and decision.supply and decision.from_slot:
        # A SUPPLY FILED TO ANOTHER PERIOD IS NOT DECIDED ABOUT HERE (post-
        # build-review #115, D3): after a re-file, a reject naming the
        # supply's OLD period was recorded against it there - a decision on
        # a period it has left, about a supply waiting somewhere else.
        from qa_tools.common import filing

        rows = conn.execute(
            f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? AND supply_id = ?",
            [decision.dataset_id, decision.supply]).fetchall()
        holder = held(conn, decision.dataset_id, decision.from_slot)
        if (rows and rows[0][0] and rows[0][0] != decision.from_slot
                and not (holder and holder.holder == decision.supply)):
            raise DecisionRefused(
                f"{decision.supply} is filed to {rows[0][0]}, not {decision.from_slot}. "
                f"Decide about it there:\n  mothman supply decide --operation "
                f"{decision.action} --dataset {decision.dataset_id} --period {rows[0][0]} "
                f"--supply {decision.supply} --reason '<why>'")

    if decision.action == REJECT and decision.supply:
        # A SUPERSEDED SUPPLY IS NOT REJECTED (post-build-review #109, F7):
        # it is already out of staging, and rejecting it would let an
        # un-supersede bring a rejected supply back where the overlay reads
        # it. The two states say different things and one supply holds one.
        from qa_tools.common import hierarchy, supersession

        if supersession.is_superseded(conn, decision.dataset_id, decision.supply):
            collection = hierarchy.dataset(decision.dataset_id).collection_id
            raise DecisionRefused(
                f"{decision.supply} is superseded, which already takes it out of the "
                f"queue - there is nothing waiting to reject. `mothman supply superseded "
                f"--collection {collection} --dataset {decision.dataset_id}` lists it.")

    if decision.action == ACKNOWLEDGE:
        # REQ-PIPE-122 criterion 14: only a supply that OWES one, and the
        # refusal says which of the four reasons it is.
        from qa_tools.common import acknowledgement

        why = acknowledgement.why_not_owed(conn, decision.dataset_id, decision.supply,
                                           decision.to_slot)
        if why:
            raise DecisionRefused(f"{decision.supply} owes no acknowledgement: {why}.")

    # A SUPPLY SOMETHING STANDS ON DOES NOT MOVE (REQ-PIPE-084 criterion
    # 11). Judged here rather than in substitution.py because it
    # constrains decisions substitution.py does not own: the person
    # demoting a supply is not thinking about a later period that was
    # substituted onto it six months ago, and nothing else would stop
    # them leaving that period resolving to a table no longer there.
    #
    # NAMES EVERY BLOCKING PERIOD, which the criterion asks for and is
    # also the only useful answer: told about one, an operator
    # de-substitutes it and hits the next.
    if decision.action in MOVES_A_SUPPLY:
        refuse_if_stood_on(conn, decision.dataset_id, decision.supply, decision.action)


def refuse_if_stood_on(conn: supply_db.SupplyConnection, dataset_id: str, supply: str,
                       action: str) -> None:
    """Refuse moving `supply` while a later period stands on it (criterion
    11), naming every blocking period and the command that unblocks each.
    Public so a warning can refuse BEFORE the person is asked to confirm
    something that cannot happen (post-build-review #112)."""
    standing = _standing_on(conn, dataset_id, supply)
    if standing:
        # THE REMEDY, PER PERIOD (REQ-GHUB-082 criterion 25). "Clear
        # them first" was true and not actionable: a substituted
        # period is cleared by a de-substitution and an inherited
        # one by an un-inheritance, and an operator told the wrong
        # one is sent to a route that will refuse them.
        how = ", ".join(f"{slot} ({UNBLOCKED_BY[by]} it)" for slot, by in standing)
        # THE FIX AS A COMMAND TO PASTE (REQ-PIPE-128 NFR 4), one per
        # blocking period and one per line, so each can be copied whole.
        commands = "".join(
            f"\n  mothman supply decide --operation {UNBLOCKED_BY[by]} --dataset "
            f"{dataset_id} --period {slot} --reason '<why>' --yes"
            for slot, by in standing)
        raise DecisionRefused(
            f"{supply!r} cannot be {action}d while "
            f"{len(standing)} later period(s) stand on it: {how}. Each of "
            f"those resolves to this supply - by a substitution somebody "
            f"decided, or because nothing was owed for it - so clear them "
            f"first, or point them elsewhere:{commands}")


def lock_slot(conn: supply_db.SupplyConnection, dataset_id: str, slot: str) -> None:
    """The same lock `_lock` takes for one slot, for a caller that must
    judge the slot under it before deciding what to record (REQ-PIPE-128,
    post-build-review #112). Transaction-scoped and re-entrant."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))", [f"{dataset_id}/{slot}"])


def _lock(conn: supply_db.SupplyConnection, decision: Decision) -> None:
    """Serialise decisions competing for the same slot (criterion 4).

    A TRANSACTION-SCOPED ADVISORY LOCK, so it releases on commit or
    rollback with nothing to remember. `hashtext` rather than a numeric
    key of our own: the key has to be derived from the dataset and slot,
    and PostgreSQL's own hash is right there.

    SORTED, because a re-file names two slots and two concurrent
    re-files in opposite directions would otherwise take them in
    opposite orders and deadlock. Sorting makes that impossible rather
    than unlikely.
    """
    # AND THE PERIOD IT STANDS ON (REQ-PIPE-129 criterion 15): a
    # substitution onto P1 and a promotion displacing P1's supply would
    # otherwise each lock a different slot and race.
    for slot in sorted(set(decision.slots) | ({decision.stands_on} - {None})):
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))",
                      [f"{decision.dataset_id}/{slot}"])


def _table_of(dataset_id: str) -> str | None:
    """The dataset's table, for the entry (REQ-PIPE-130 criterion 10) -
    from the one hierarchy, so the log never holds a second mapping. None
    for a dataset the tree does not know (a test's), which concerns no
    table of this asset."""
    from qa_tools.common import hierarchy

    try:
        return hierarchy.dataset(dataset_id).table
    except hierarchy.UnknownDatasetError:
        return None


def follows(conn: supply_db.SupplyConnection, decision_id: int | None) -> str:
    """When work that a decision caused takes effect: as long after the
    decision took effect as it really ran after the decision was recorded
    (Keith, 2026-10-06, post-build-review #117 D7).

    Live, a decision takes effect when it is recorded, so this is the moment
    the work ran - never before its own checks, which the cause's instant
    alone claimed. In a replay a scripted decision is recorded now but takes
    effect years ago, so this is the cause's instant plus the moments the work
    took - never today, which is #116's reason for using the cause at all.
    One rule, no flag saying which of the two this is. Now, where there is no
    cause to follow.
    """
    from qa_tools.common import asset_time

    now = asset_time.now()
    if decision_id is not None:
        rows = conn.execute(f"SELECT effective_at, recorded_at FROM {TABLE} WHERE id = ?",
                            [decision_id]).fetchall()
        if rows and rows[0][0] is not None and rows[0][1] is not None:
            effective, recorded = rows[0]
            lag = max(now - recorded, now - now)
            return (effective + lag).astimezone(now.tzinfo).isoformat()
    return now.isoformat()


def _insert(conn: supply_db.SupplyConnection, decision: Decision) -> int:
    rows = conn.execute(
        f"INSERT INTO {TABLE} (agency_id, collection_id, dataset_id, action, supply, "
        "from_slot, to_slot, actor, actor_kind, reason, effective_at, stands_on, "
        "amber_setting, amber_level, amber_version, superseded_by, table_name, "
        "promoted_status, replaces, replacement_setting, replacement_level, "
        "replacement_version, caused_by_decision, caused_by_supply) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "RETURNING id",
        [decision.agency_id, decision.collection_id, decision.dataset_id,
         decision.action, decision.supply or None, decision.from_slot, decision.to_slot,
         decision.actor.strip(), decision.actor_kind,
         (decision.reason or "").strip() or None, decision.effective_at,
         decision.stands_on, decision.amber_setting, decision.amber_level,
         decision.amber_version, decision.superseded_by, _table_of(decision.dataset_id),
         decision.promoted_status, decision.replaces, decision.replacement_setting,
         decision.replacement_level, decision.replacement_version,
         decision.caused_by_decision, decision.caused_by_supply]).fetchall()
    return int(rows[0][0])


#: How long a decision waits on a lock before it is refused (REQ-PIPE-129
#: criterion 16) - long enough for another person's decision to finish,
#: short enough that a person is never left looking at a hung terminal
#: while a QA tool reads the table for minutes.
LOCK_TIMEOUT = "15s"

RUN_IN_PROGRESS = ("Something is using these tables right now - most often a QA run "
                   "reading them, or another person's decision on the same period. "
                   "Nothing was done; retry in a minute.")


@contextmanager
def decision_transaction(conn: supply_db.SupplyConnection) -> Iterator[None]:
    """A transaction whose lock waits are bounded (criterion 16): a wait
    past LOCK_TIMEOUT is refused as a run in progress, never a hang.
    Nested, it is a savepoint inside the caller's."""
    import psycopg

    # WHAT THIS TRANSACTION MOVED IN OR OUT OF A PERIOD (REQ-PIPE-121
    # criteria 8, 9 and 15), gathered by every apply_decision inside it and
    # owed ONCE, at the end, by the outermost - so a displacing promotion,
    # which writes a supersession and a promotion, owes one re-evaluation
    # rather than two, and it is recorded in the same transaction.
    outermost = getattr(conn, "_period_moves", None) is None
    if outermost:
        conn._period_moves = []
    try:
        with conn.raw.transaction():
            conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
            yield
            if outermost and conn._period_moves:
                from qa_tools.common import knock_on

                knock_on.owe(conn, conn._period_moves)
    except psycopg.errors.LockNotAvailable as exc:
        raise DecisionRefused(RUN_IN_PROGRESS) from exc
    finally:
        if outermost:
            conn._period_moves = None


@contextmanager
def apply_decision(conn: supply_db.SupplyConnection,
                    decision: Decision) -> Iterator[int]:
    """Record a decision and apply its effect, as one transaction
    (criterion 2).

    Used as:

        with apply_decision(conn, decision) as entry_id:
            promote_the_table(conn)        # the effect, same transaction

    NEITHER CAN BE OBSERVED WITHOUT THE OTHER. The entry is written
    inside the transaction and the caller's effect runs inside the same
    one, so a failure in the effect takes the entry with it and a
    failure writing the entry means the effect never ran. That is the
    reliability NFR satisfied by construction rather than implemented.

    THE ENTRY GOES IN BEFORE THE EFFECT, which reads backwards and is
    right: the entry is what the lock and the judgement were for, and
    writing it first means a caller's effect cannot accidentally be the
    thing that decides whether the slot was free.

    IT DOES NOT CATCH SupplyDbError (criterion 8). An unreachable
    database propagates, and nothing here writes the decision anywhere
    to try again later.
    """
    _check_shape(decision)
    # A REAL TRANSACTION over an autocommit connection - see
    # supply_db.SupplyConnection, which anticipates exactly this caller.
    # `conn.raw.transaction()` issues its own BEGIN and rolls back on any
    # exception escaping the block. Its lock waits are bounded.
    with decision_transaction(conn):
        _lock(conn, decision)
        _judge(conn, decision)
        # HOW EACH OF ITS PERIODS WAS HELD BEFORE, so that afterwards a change
        # is SEEN rather than inferred from the action (REQ-PIPE-121
        # criterion 8): one mechanism, whatever decision moved the table.
        before = {slot: _holding(conn, decision.dataset_id, slot) for slot in decision.slots}
        entry_id = _insert(conn, decision)
        # A DECISION ABOUT A HELD SUPPLY ENDS ITS HOLD (REQ-PIPE-078
        # criterion 6), and it happens HERE because this is the one
        # place every decision passes through. Doing it in each caller
        # would mean a hold outliving the decision that answered it the
        # first time somebody adds a fifth route - and a queue asking
        # for work already done is how people stop reading the queue.
        #
        # IN THE SAME TRANSACTION as the entry, so the two cannot
        # disagree: a rollback takes both, and there is no window where
        # the log says resolved and the hold says waiting.
        #
        # EXCEPT A REFUSAL (REQ-PIPE-151 criterion 5): the gate saying "held -
        # no open period" is a record ABOUT the hold, and resolving the hold
        # with it would close the very thing it reports.
        if decision.action not in RECORDS_A_REFUSAL:
            supply_holds.resolve_for_supply(
                conn, dataset_id=decision.dataset_id, supply=decision.supply or "",
                decision_id=entry_id)
        yield entry_id
        for slot, was in before.items():
            if _holding(conn, decision.dataset_id, slot) != was:
                conn._period_moves.append((entry_id, decision.dataset_id, slot))


def _holding(conn, dataset_id: str, slot: str) -> tuple:
    """What a period holds for a dataset, as a comparable pair."""
    h = held(conn, dataset_id, slot)
    return (h.held_as, h.holder) if h and h.held_as else (None, None)


def record_automatic(conn: supply_db.SupplyConnection, decision: Decision) -> int:
    """An automatic decision, with the rule as the actor (REQ-PIPE-074
    criterion 3).

    A CONVENIENCE OVER apply_decision, NOT A SECOND PATH: it is for a
    rule whose effect is nothing more than the entry - an inheritance at
    a period's birth, say. Anything that touches the warehouse uses the
    context manager, so that the entry and the change stay one
    transaction.
    """
    if decision.actor_kind != RULE:
        raise DecisionRefused(
            "record_automatic is for a decision a RULE made - a person's "
            "decision goes through apply_decision with actor_kind='person'")
    with apply_decision(conn, decision) as entry_id:
        return entry_id


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

#: Every column a reader gets, in a fixed order, so a row reads the same
#: way everywhere.
FIELDS = ("id", "agency_id", "collection_id", "dataset_id", "action", "supply",
          "from_slot", "to_slot", "actor", "actor_kind", "reason",
          "effective_at", "recorded_at")


def _rows(cursor) -> list[dict]:
    return [dict(zip(FIELDS, row)) for row in cursor.fetchall()]


def decisions_for(conn: supply_db.SupplyConnection, dataset_id: str,
                   as_at: str | None = None) -> list[dict]:
    """One dataset's decisions, oldest first (criterion 11).

    Indexed on (dataset_id, effective_at, id), so this costs what this
    dataset's own history costs and nothing for anybody else's - which
    at 30 datasets over years is the difference between a query and a
    scan.
    """
    window = "AND effective_at <= ?" if as_at else ""
    params: list = [dataset_id] + ([as_at] if as_at else [])
    return _rows(conn.execute(
        f"SELECT {', '.join(FIELDS)} FROM {TABLE} WHERE dataset_id = ? {window} "
        "ORDER BY effective_at, id", params))


def all_decisions(conn: supply_db.SupplyConnection, limit: int | None = None) -> list[dict]:
    """The whole log, newest first - what criterion 10's read-only reader
    gets."""
    tail = f"LIMIT {int(limit)}" if limit else ""
    return _rows(conn.execute(
        f"SELECT {', '.join(FIELDS)} FROM {TABLE} "
        f"ORDER BY effective_at DESC, id DESC {tail}"))


def promoted_supply(conn: supply_db.SupplyConnection, dataset_id: str,
                     as_at: str | None = None) -> dict | None:
    """This dataset's most recently promoted supply (REQ-PIPE-074
    criterion 12), from the log alone.

    Returns the ENTRY rather than the supply's name, because every
    question that follows - into which slot, by whom, why - is on the
    same row, and handing back a bare string would send the caller
    looking it up again.
    """
    # FROM qa.slot_holds (REQ-PIPE-130 criterion 9): the newest supply
    # that a slot still holds by a promotion or a re-file. It used to walk
    # the whole log here with its own idea of "undone", a second statement
    # of what a slot holds - so a reject of an unpromoted resupply named
    # "undone" a supply still filling its period. A substitution is not a
    # promoted supply, so it is not counted.
    rows = _rows(conn.execute(
        f"SELECT {', '.join('d.' + f for f in FIELDS)} "
        f'FROM "{qa_store.SCHEMA}".slot_holds(?, ?) h JOIN {TABLE} d ON d.id = h.decision_id '
        "WHERE h.held_as = ? "
        "ORDER BY d.effective_at DESC, d.id DESC LIMIT 1",
        [dataset_id, as_at, PROMOTED]))
    return rows[0] if rows else None
