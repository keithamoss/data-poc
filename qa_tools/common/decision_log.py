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

from qa_tools.common import qa_store, supply_db

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

ACTIONS = (PROMOTE, REJECT, DEMOTE, REFILE, SUBSTITUTE, DE_SUBSTITUTE,
           INHERIT, INHERIT_REFUSED, UN_INHERIT)

#: The actions a RULE may take. Everything else is a person's, and
#: rejection.py and substitution.py enforce that by not offering an
#: actor_kind at all.
AUTOMATIC_ACTIONS = (PROMOTE, INHERIT, INHERIT_REFUSED)

#: The decisions that move a supply, and so are the ones criterion 11
#: refuses while a later period stands on it.
MOVES_A_SUPPLY = (REJECT, DEMOTE, REFILE)

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
    if decision.action != INHERIT_REFUSED and not (decision.supply or "").strip():
        raise DecisionRefused("a decision needs the supply it acts on")
    if decision.action == INHERIT_REFUSED and (decision.supply or "").strip():
        raise DecisionRefused(
            "a refused inheritance names no supply - that is what it could not "
            "find. Recording one would say the opposite of what happened.")
    if not decision.slots:
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
    if decision.action not in (SUBSTITUTE, INHERIT) and decision.stands_on:
        raise DecisionRefused(
            f"only a substitution or an inheritance stands on a period; "
            f"{decision.action!r} does not")


def promoted_into(conn: supply_db.SupplyConnection, dataset_id: str, slot: str,
                   as_at: str | None = None) -> str | None:
    """The supply this slot resolves to, as at an instant (criterion 9).

    From this table alone, which is what makes it an answer rather than a
    reconstruction. The rule is "the last decision affecting this slot
    wins": a promote or a re-file INTO it fills it, a reject, a demote or
    a re-file OUT OF it empties it.

    `as_at` IS ABOUT `effective_at`, NEVER `recorded_at`. The question is
    what the warehouse held at that moment, and a decision taken on
    Tuesday and recorded on Friday took effect on Tuesday. Using the
    recorded instant would answer a different question - what we knew -
    which is also worth asking and is not this.

    ORDERED BY (effective_at, id), because two decisions can share an
    instant and `id` is the only total order there is. Without it the
    answer is whichever row the planner returned first, which is stable
    right up until it is not.
    """
    window = "AND effective_at <= ?" if as_at else ""
    params: list = [dataset_id, slot, slot]
    if as_at:
        params.append(as_at)
    rows = conn.execute(
        f"SELECT action, supply, from_slot, to_slot FROM {TABLE} "
        f"WHERE dataset_id = ? AND (to_slot = ? OR from_slot = ?) {window} "
        "ORDER BY effective_at DESC, id DESC LIMIT 1", params).fetchall()
    if not rows:
        return None
    action, supply, _from_slot, to_slot = rows[0]
    if to_slot != slot:
        return None
    # A SUBSTITUTED SLOT COUNTS AS FILLED (REQ-PIPE-084 criterion 4).
    # That is the point of it: the period answers, so nothing should
    # treat it as owed, and the next arrival for it is a supply landing
    # on a filled slot rather than the one that was missing.
    # AN INHERITED PERIOD IS NOT A FILLED SLOT, and that is the whole of
    # criterion 7: the dataset does not participate, so nothing was owed
    # and there is no slot to fill. Counting it would make "filled"
    # mean two different things - a supply arrived, and no supply was
    # ever due - which is the distinction the dashboard exists to show.
    return supply if action in (PROMOTE, REFILE, SUBSTITUTE) else None


def latest_for_slot(conn: supply_db.SupplyConnection, dataset_id: str,
                     slot: str) -> tuple[str, str, str | None] | None:
    """`(action, supply, stands_on)` of the last decision on this slot.

    promoted_into() answers "what does this period resolve to" and
    deliberately flattens a substitution into the supply it stands on,
    which is what every reader of a period wants. This answers the
    narrower question a DECISION has to ask: HOW does it resolve, so
    that substituting into a period that already holds a real promoted
    supply can be refused with the right words (criterion 15).
    """
    rows = conn.execute(
        f"SELECT action, supply, stands_on FROM {TABLE} "
        "WHERE dataset_id = ? AND (to_slot = ? OR from_slot = ?) "
        "ORDER BY effective_at DESC, id DESC LIMIT 1",
        [dataset_id, slot, slot]).fetchall()
    return (rows[0][0], rows[0][1], rows[0][2]) if rows else None


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
    for (slot,) in rows:
        latest = latest_for_slot(conn, dataset_id, slot)
        if latest and latest[0] in STANDS_ON_A_SUPPLY and latest[1] == supply:
            standing.append((slot, latest[0]))
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
    elif decision.action in (PROMOTE, REFILE) and decision.to_slot:
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
        standing = _standing_on(conn, decision.dataset_id, decision.supply)
        if standing:
            # THE REMEDY, PER PERIOD (REQ-GHUB-082 criterion 25). "Clear
            # them first" was true and not actionable: a substituted
            # period is cleared by a de-substitution and an inherited
            # one by an un-inheritance, and an operator told the wrong
            # one is sent to a route that will refuse them.
            how = ", ".join(f"{slot} ({UNBLOCKED_BY[action]} it)"
                             for slot, action in standing)
            raise DecisionRefused(
                f"{decision.supply!r} cannot be {decision.action}d while "
                f"{len(standing)} later period(s) stand on it: {how}. Each of "
                f"those resolves to this supply - by a substitution somebody "
                f"decided, or because nothing was owed for it - so clear them "
                f"first, or point them elsewhere.")


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
    for slot in sorted(decision.slots):
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))",
                      [f"{decision.dataset_id}/{slot}"])


def _insert(conn: supply_db.SupplyConnection, decision: Decision) -> int:
    rows = conn.execute(
        f"INSERT INTO {TABLE} (agency_id, collection_id, dataset_id, action, supply, "
        "from_slot, to_slot, actor, actor_kind, reason, effective_at, stands_on) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        [decision.agency_id, decision.collection_id, decision.dataset_id,
         decision.action, decision.supply or None, decision.from_slot, decision.to_slot,
         decision.actor.strip(), decision.actor_kind,
         (decision.reason or "").strip() or None, decision.effective_at,
         decision.stands_on]).fetchall()
    return int(rows[0][0])


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
    # exception escaping the block.
    with conn.raw.transaction():
        _lock(conn, decision)
        _judge(conn, decision)
        entry_id = _insert(conn, decision)
        yield entry_id


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
    window = "AND effective_at <= ?" if as_at else ""
    params: list = [dataset_id] + ([as_at] if as_at else [])
    candidates = _rows(conn.execute(
        f"SELECT {', '.join(FIELDS)} FROM {TABLE} WHERE dataset_id = ? {window} "
        "ORDER BY effective_at DESC, id DESC", params))
    # WALKED RATHER THAN FILTERED IN SQL, because "most recently
    # promoted" means the newest promotion THAT HAS NOT SINCE BEEN
    # UNDONE - a supply promoted in March and demoted in April is not
    # the answer, and `WHERE action = 'promote'` would say it was.
    undone: set[str] = set()
    for entry in candidates:
        if entry["action"] in (REJECT, DEMOTE):
            undone.add(entry["supply"])
            continue
        if entry["action"] == REFILE:
            # A re-file moves a supply; it stays promoted, elsewhere.
            if entry["supply"] not in undone:
                return entry
            continue
        if entry["action"] == PROMOTE and entry["supply"] not in undone:
            return entry
    return None
