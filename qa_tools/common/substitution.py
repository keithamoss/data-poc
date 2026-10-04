"""A period nobody supplied, standing on an earlier real one (REQ-PIPE-084).

THE PROBLEM IS A QUERY THAT BREAKS RATHER THAN ANSWERS. Somebody asks
the warehouse for this quarter's carers and the supplier never sent
them. An empty table is the worst possible answer: it is indistinguishable
from "there are no carers", and it is what a naive design gives you. A
SUBSTITUTION makes the period resolve, for that one table, to a supply
somebody promoted earlier - so the query answers with something real and
defensible, and the indirection is visible to anyone who looks.

NEVER BY DEFAULT, ALWAYS BY A DECISION. Nothing here is reachable by an
automatic rule, and the reason is the whole requirement: a period
silently falling back to an older one is a stale number presented as a
current one, which is the failure this project exists to make
impossible. A person decides that the supply will not arrive, a person
chooses what to stand on, and the log carries both plus their reason.

A VIEW, NOT A COPY (criterion 2). Copying would make the substituted
period a second physical truth that can drift from the one it was taken
from, and would quietly double the storage of every period a supplier
skips. A view also makes criterion 11 meaningful: the supply underneath
genuinely cannot move while something stands on it, and the decision log
refuses to let it.

WHAT THIS DELIBERATELY DOES NOT DO is decide that a period is owed
nothing at all. A dataset the schedule says does not participate in a
period has no gap to fill, and substituting into it would assert that
somebody should have supplied it. That is INHERITANCE (REQ-PIPE-098),
a different decision with a different meaning, and criterion 18 makes
this one refuse rather than blur them.
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import decision_log, period_schema, supply_db


class SubstitutionRefused(RuntimeError):
    """A substitution this will not perform, with the reason in the message.

    Separate from decision_log.DecisionRefused because these are
    refusals about the WAREHOUSE and the SCHEDULE - no earlier promoted
    supply, a period that already resolves, a period nothing is owed for
    - judged before a decision is ever built. A caller showing an
    operator why cannot tell them apart from the type alone, which is
    why both carry the whole sentence.
    """


@dataclass(frozen=True)
class Substitution:
    """One period's indirection, as the log describes it."""

    period: str
    stands_on: str
    supply: str

    @property
    def describes(self) -> str:
        return (f"{self.period} stands on {self.stands_on}'s supply "
                f"{self.supply}")


def _physical_in(conn, *, period: str, logical: str) -> str:
    """The PHYSICAL table this logical name resolves to in that period.

    A SUPPLY ID IS NOT A TABLE NAME, and this function exists because
    the first version of this module assumed it was.
    `cp-carers@202605010100000000` is how a filing and a decision name a
    supply; `cp_carers__202605010100000000` is what the warehouse can
    call a table, because dbt and Soda write the name into their own SQL
    unquoted. The decision log records the first and the period schema
    holds the second, so building a view needs both - the id to judge
    the decision against the log, the table to point the view at.

    The two coincided in the tests that first covered this module, which
    is exactly why nothing caught it: a helper promoted with
    `supply=physical, physical_tables=[physical]`, so every assertion
    held and the real system, where they differ, would have failed on
    the first substitution anybody made.
    """
    found = period_schema.promoted_in(conn, period, [logical]).get(logical) or []
    if not found:
        raise SubstitutionRefused(
            f"{period} holds no table called {logical!r}, so there is nothing to "
            f"point at. The decision log says a supply was promoted into it - if "
            f"that is still true, the table has been moved or dropped since.")
    if len(found) > 1:
        # REQ-PIPE-068's rule, applied here: several versions with no
        # basis to choose between them is absence, not a coin toss.
        raise SubstitutionRefused(
            f"{period} holds {len(found)} versions of {logical!r} "
            f"({', '.join(sorted(found))}) and nothing says which is the supply, "
            f"so nothing can stand on it.")
    return found[0]


def _view_sql(conn, *, period: str, logical: str, stands_on: str,
              physical: str) -> None:
    schema = period_schema.ensure_period_schema(conn, period)
    source = period_schema.period_schema(stands_on)
    conn.execute(
        f'CREATE OR REPLACE VIEW "{schema}"."{supply_db._ident(logical, "table name")}" '
        f'AS SELECT * FROM "{source}"."{supply_db._ident(physical, "table name")}"')


def substituted(conn: supply_db.SupplyConnection, dataset_id: str,
                period: str) -> Substitution | None:
    """This period's indirection, or None where it has none.

    FROM THE LOG, never from the catalogue. A view sitting in a period
    schema says an object exists; it cannot say whether somebody has
    since removed the indirection, and a de-substitution that failed to
    drop the object would otherwise read as a live substitution
    forever.
    """
    h = decision_log.held(conn, dataset_id, period)
    if not h or h.held_as != decision_log.SUBSTITUTED:
        return None
    return Substitution(period=period, stands_on=h.stands_on, supply=h.holder)


def _refuse_unless_substitutable(conn, *, dataset_id: str, period: str,
                                 stands_on: str, supply: str,
                                 participates: bool) -> None:
    """Criteria 7, 15, 16 and 18, in the order an operator meets them."""
    if not participates:
        # Criterion 18. First, because it says the period is not a gap at
        # all - every later question assumes one.
        raise SubstitutionRefused(
            f"nothing is owed for {period}: the schedule says {dataset_id} does "
            f"not participate in it, so there is no gap to fill. A period that "
            f"was never owed a supply is INHERITED, not substituted.")

    holds = decision_log.held(conn, dataset_id, period)
    if holds and holds.held_as == decision_log.PROMOTED:
        # Criterion 15.
        raise SubstitutionRefused(
            f"{period} already resolves to a real supply ({holds.holder}). A period "
            f"holding a promoted table is answered; substituting into it would "
            f"replace an answer rather than supply a missing one.")

    source = decision_log.held(conn, dataset_id, stands_on)
    if not source or source.held_as != decision_log.PROMOTED:
        # Criteria 7 and 16 meet here, and the message has to serve both.
        # A period that is itself substituted or inherited fails the same
        # test as one that holds nothing: neither has a physical promoted
        # table of its own, and standing on it would build a chain whose
        # bottom nobody can see.
        what = (f"is itself {source.held_as}" if source and source.held_as
                else "holds no promoted supply")
        raise SubstitutionRefused(
            f"{stands_on} cannot be stood on: it {what}. A substitution points "
            f"at a real promoted table, never at another period's indirection - "
            f"otherwise a chain forms and nothing can say what the data is.")

    if source.holder != supply:
        raise SubstitutionRefused(
            f"{stands_on} resolves to {source.holder!r}, not {supply!r}. Stand on "
            f"what the period actually holds.")


def substitute(conn: supply_db.SupplyConnection, *,
               agency_id: str,
               collection_id: str,
               dataset_id: str,
               logical_table: str,
               period: str,
               stands_on: str,
               supply: str,
               actor: str,
               reason: str,
               effective_at: str,
               participates: bool = True) -> Substitution:
    """Make `period` resolve, for this table, to `stands_on`'s supply.

    A PERSON'S DECISION AND ONLY A PERSON'S (criterion 1). There is no
    actor_kind argument: this records `person` and nothing else, so an
    automatic caller cannot reach it by passing the wrong value. That is
    the same shape rejection.py uses, and for the same reason - the rule
    that must never be broken is better expressed as an absent parameter
    than as a validated one.

    A REASON IS REQUIRED HERE rather than left to the log's own judgement.
    Criterion 5 asks for one unconditionally, and a substitution is
    exactly the decision somebody asks about a year later: the period
    answers, the answer is not this period's data, and the only record of
    why is this.

    ANY STATUS MAY BE STOOD ON (criterion 1). A period that held an amber
    or red supply held one, and the person confirming it is the right
    thing to stand on is the point of the decision - filtering to green
    would substitute judgement for theirs and leave some gaps unfillable.
    """
    if not (reason or "").strip():
        raise SubstitutionRefused(
            "a substitution needs a reason. The period will answer with data "
            "that is not its own, and this is the only record of why.")
    _refuse_unless_substitutable(
        conn, dataset_id=dataset_id, period=period, stands_on=stands_on,
        supply=supply, participates=participates)

    # Same reason promotion.promote() does it here - see its comment.
    period_schema.open_period(conn, period, opened_by=actor,
                               effective_at=effective_at)

    decision = decision_log.Decision(
        agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
        action=decision_log.SUBSTITUTE, supply=supply, actor=actor,
        actor_kind=decision_log.PERSON, effective_at=effective_at,
        to_slot=period, stands_on=stands_on, reason=reason)

    # RESOLVED BEFORE THE TRANSACTION OPENS, so a period whose table has
    # gone missing is a refusal rather than a rolled-back decision.
    physical = _physical_in(conn, period=stands_on, logical=logical_table)

    with decision_log.apply_decision(conn, decision):
        _view_sql(conn, period=period, logical=logical_table,
                  stands_on=stands_on, physical=physical)
    return Substitution(period=period, stands_on=stands_on, supply=supply)


def de_substitute(conn: supply_db.SupplyConnection, *,
                  agency_id: str,
                  collection_id: str,
                  dataset_id: str,
                  logical_table: str,
                  period: str,
                  actor: str,
                  reason: str,
                  effective_at: str,
                  confirmed: bool = False) -> None:
    """Remove `period`'s indirection, leaving the slot unfilled.

    ONE DATASET AND ONE PERIOD AT A TIME (criterion 9), which is not a
    limitation to be lifted later: a sweep that removes several
    indirections on one confirmation is exactly how somebody empties a
    year of periods meaning to empty one.

    EXPLICIT CONFIRMATION, ON EVERY ROUTE (criterion 13), and it is a
    required argument rather than a prompt inside a function so that
    every route has to obtain it - a prompt here would be skipped by the
    first caller that is not a terminal.

    NOTHING RE-CREATES WHAT A PERSON REMOVED (criterion 13's second
    half). Nothing in this module or anywhere else creates an
    indirection except substitute(), which only a person reaches.
    """
    if not confirmed:
        raise SubstitutionRefused(
            f"de-substituting {period} needs an explicit confirmation. Anything "
            f"reading that period will stop resolving the moment this is done.")
    if not (reason or "").strip():
        raise SubstitutionRefused(
            "a de-substitution needs a reason, on the same terms as the "
            "substitution it reverses.")

    current = substituted(conn, dataset_id, period)
    if current is None:
        raise SubstitutionRefused(
            f"{period} has no indirection to remove. Either it was never "
            f"substituted or somebody has already removed it.")

    decision = decision_log.Decision(
        agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
        action=decision_log.DE_SUBSTITUTE, supply=current.supply, actor=actor,
        actor_kind=decision_log.PERSON, effective_at=effective_at,
        from_slot=period, reason=reason)

    schema = period_schema.period_schema(period)
    with decision_log.apply_decision(conn, decision):
        conn.execute(
            f'DROP VIEW IF EXISTS "{schema}".'
            f'"{supply_db._ident(logical_table, "table name")}"')
