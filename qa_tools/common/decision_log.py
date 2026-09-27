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
ACTIONS = (PROMOTE, REJECT, DEMOTE, REFILE)

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
    if not (decision.supply or "").strip():
        raise DecisionRefused("a decision needs the supply it acts on")
    if not decision.slots:
        raise DecisionRefused(
            "a decision needs at least one slot - which period it acts on")
    if decision.action == REFILE and not (decision.from_slot and decision.to_slot):
        raise DecisionRefused(
            "a re-file names both slots: the one the supply is in and the one it "
            "is moving to. One entry, not a demotion followed by a promotion.")


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
    action, supply, from_slot, to_slot = rows[0]
    if action in (PROMOTE,) and to_slot == slot:
        return supply
    if action == REFILE and to_slot == slot:
        return supply
    return None


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
        "from_slot, to_slot, actor, actor_kind, reason, effective_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
        [decision.agency_id, decision.collection_id, decision.dataset_id,
         decision.action, decision.supply, decision.from_slot, decision.to_slot,
         decision.actor.strip(), decision.actor_kind,
         (decision.reason or "").strip() or None, decision.effective_at]).fetchall()
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
