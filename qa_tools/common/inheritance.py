"""A period nobody owed a supply for, filled with what is still current
(REQ-PIPE-098).

AN ANNUAL DATASET IN A QUARTERLY ASSET is the case. Somebody queries the
warehouse for this quarter and finds `cp_carers` missing - not because a
supplier failed, but because carers are supplied once a year and this is
not the quarter. A missing table is the wrong answer to a question
nobody should have had to ask: the current carers are the ones promoted
in the annual period, and they are still current.

SO THE RULE FILLS IT, and unlike a substitution nobody has to decide
anything. That is the whole distinction (criterion 12), and it is worth
holding onto because the two are identical in SQL - both are a view in a
period's schema pointing at an earlier promoted table:

  - SUBSTITUTION says a supply WAS owed and did not come, and a person
    chose what to stand on. It is REQ-PIPE-084, it needs a reason, and
    only a person can make one.
  - INHERITANCE says nothing was owed at all. The schedule says so, the
    rule acts on it, and there is nothing for a person to decide.

Collapsing them would lose the difference between a supplier who missed
a quarter and one who was never due, which is exactly the difference the
dashboard exists to show.

ONCE, WHEN THE PERIOD IS BORN (criteria 1 and 2). Not on every run, not
on demand: a period's inherited views are decided at the moment it
opens, from what was current then, and nothing recreates them
afterwards. A rule that kept re-pointing them would silently change what
a historical period resolved to every time something newer was
promoted - which is a period quietly rewriting its own past.

NON-PARTICIPATION COMES FROM THE SCHEDULE AND NOWHERE ELSE (criterion
5). The tempting shortcut is "no supply arrived, so presumably none was
due", and it is exactly backwards: a missing supply is the thing this
system exists to report, and inferring agreement from absence would
silence it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qa_tools.common import (decision_log, hierarchy, period_schema, schedule,
                             supply_db)

#: What a rule records as its own name in the decision log.
RULE_ACTOR = "inheritance rule"


@dataclass(frozen=True)
class Inherited:
    """One dataset's inheritance into one period."""

    dataset_id: str
    period: str
    stands_on: str
    supply: str
    reason: str


@dataclass(frozen=True)
class Refused:
    """A dataset that does not participate and had nothing to stand on.

    RECORDED AND SURFACED, never silent (criterion 10). An attempt that
    could not complete is the state somebody has to know about: the
    period genuinely has no table for this dataset, and the reason is
    ours rather than the supplier's.
    """

    dataset_id: str
    period: str
    reason: str


@dataclass(frozen=True)
class Outcome:
    inherited: list[Inherited] = field(default_factory=list)
    refused: list[Refused] = field(default_factory=list)

    @property
    def nothing_happened(self) -> bool:
        return not (self.inherited or self.refused)


def _does_not_participate(dataset_id: str, period_name: str) -> tuple[bool, str]:
    """`(True, the schedule's own reason)` where nothing is owed.

    FROM THE SCHEDULE, which is criterion 5, and from the one function
    that already answers it - schedule.not_expected_periods() returns
    {period: reason} and refuses a period declared with no reason, so
    criterion 6's "record the reason the schedule states" needs no
    second source that could disagree with it.
    """
    reason = schedule.not_expected_periods(dataset_id).get(period_name)
    if reason:
        return True, reason
    # AND THE OTHER WAY A SCHEDULE SAYS IT (2026-10-02): `delivery_months`
    # subsetting the calendar. Case Workers is delivered in February and
    # August only, and the slot builder has always honoured that - but
    # this read only `not_expected`, so Q2 and Q4 opened without Case
    # Workers and every check reading it went red as "missing". A period
    # the dataset's own slots leave out, under delivery_months, is owed
    # nothing; the reason is the schedule's own words.
    #
    # ONLY FOR A PERIOD OF ITS OWN CALENDAR: the first cut of this asked
    # "is it one of my slots?" of every period in the asset, so Birth
    # Registrations' daily periods read as Case Workers declining them
    # and were each recorded as a refused inheritance.
    months = schedule.delivery_months(dataset_id)
    if (months and period_name in _calendar_period_names(dataset_id)
            and period_name not in _slot_names(dataset_id)):
        import calendar

        names = [calendar.month_name[m] for m in months]
        return True, (f"{dataset_id} is delivered in {' and '.join(names)} only "
                      f"(delivery_months), so nothing is owed for {period_name}")
    return False, ""


def _calendar_period_names(dataset_id: str) -> frozenset[str]:
    """Every period of this dataset's own calendar, owed or not."""
    try:
        name = schedule.calendar_for_dataset(dataset_id).name
        return frozenset(p.name for p in schedule.periods_for_calendar(name))
    except schedule.ScheduleConfigError:
        # A cadence rule has no end to enumerate to, and a daily calendar
        # thinned by month is not a shape anything declares today.
        return frozenset()


def _slot_names(dataset_id: str) -> frozenset[str]:
    """The periods this dataset's own schedule owes a supply for."""
    from qa_tools.common import slots as slots_mod

    return frozenset(s.name for s in slots_mod.slots_for_dataset(dataset_id))


def _most_recent_promoted(conn, dataset_id: str,
                          before: str) -> tuple[str, str] | None:
    """`(period, supply)` of the newest PROMOTED table, or None.

    ONLY A PROMOTED ONE (criterion 14). A period that is itself
    inherited or substituted holds a view, not a table, and pointing at
    one would build a chain whose bottom nobody can see - the same
    refusal REQ-PIPE-084 criterion 16 makes for substitution.

    ORDERED BY THE PERIOD'S OWN DATE rather than by when the promotion
    happened, because "the supply that is still current" is a statement
    about the data's period, not about our paperwork.
    """
    # WHAT EACH SLOT HOLDS COMES FROM qa.slot_holds (REQ-PIPE-130
    # criterion 9). This walked the log itself, newest-first, reading the
    # first entry INTO each slot - so it never saw a demote, reject or
    # re-file OUT (those name only from_slot) and pointed an inheritance
    # at a supply whose table had gone; and a withheld note read a filled
    # period as empty (delivery-critic, overnight sprint 2).
    best: tuple[str, str] | None = None
    best_date = None
    before_date = schedule.date_of(before, dataset_id)
    for slot, h in decision_log.held_all(conn, dataset_id).items():
        if h.held_as != decision_log.PROMOTED:
            continue
        supply = h.holder
        when = schedule.date_of(slot, dataset_id)
        if when is None:
            # A period this dataset's calendar does not name - another
            # calendar's, or one since renamed. Not a candidate rather
            # than an error.
            continue
        if before_date is None or when >= before_date:
            # Only what was current BEFORE this period. A later period's
            # supply is not what this one inherits.
            continue
        if best_date is None or when > best_date:
            best, best_date = (slot, supply), when
    return best


def _physical_in(conn, *, period: str, logical: str) -> str:
    """The PHYSICAL table this logical name resolves to in that period.

    A SUPPLY ID IS NOT A TABLE NAME, and this module assumed it was
    until 2026-09-29. `cp-carers@202605010100000000` is how a filing and
    a decision name a supply; `cp_carers__202605010100000000` is what
    the warehouse can call a table, because dbt and Soda write the name
    into their own SQL unquoted. The log records the first and the
    period schema holds the second, so building a view needs both - the
    id to record what this period stands on, the table to point at.

    THE SAME DEFECT substitution._physical_in() was written for, in a
    module written the same night and never joined up. It hid here for
    the same reason: every test of the rule's own pass promoted with
    `supply=physical, physical_tables=[physical]`, so the two names were
    one string and every assertion held. Found by a test in a different
    module that minted them differently
    (plans/post-build-review.md #66).
    """
    found = period_schema.promoted_in(conn, period, [logical]).get(logical) or []
    if not found:
        raise InheritanceRefused(
            f"{period} holds no table called {logical!r}, so there is nothing "
            f"to stand on. The decision log says a supply was promoted into it "
            f"- if that is still true, the table has been moved or dropped.")
    # ONE VERSION PER PERIOD (REQ-PIPE-128): promoted_in raises on more
    # than one, so there is no second to choose between here.
    from qa_tools.common import period_tables

    # A TABLE, ASKED OF THE CATALOGUE (REQ-PIPE-129 criterion 8): under
    # plain names a view and a table look alike, so the name cannot say.
    if period_tables.is_view(conn, period_schema.period_schema(period), found[0]):
        raise InheritanceRefused(
            f"{period}'s {logical} is a view, not a promoted table, so nothing can "
            f"inherit from it - a chain whose bottom nobody can see.")
    return found[0]


def inherit_into(conn: supply_db.SupplyConnection, period_name: str, *,
                 effective_at: str, caused_by: str | None = None) -> Outcome:
    """Fill this newly-opened period for every dataset that owes it
    nothing.

    CALLED ONCE, BY period_schema.open_period(), at the moment the
    period is created. Calling it again is not forbidden by anything
    here - it would simply find each view already recorded - but nothing
    does, and criterion 2 is why: a rule that recreated these views
    later would change what a historical period resolves to every time
    something newer was promoted.
    """
    outcome = Outcome()
    schema = period_schema.period_schema(period_name)
    for entry in hierarchy.all_datasets():
        try:
            skipped, reason = _does_not_participate(entry.dataset_id, period_name)
        except Exception as exc:  # noqa: BLE001 - one bad schedule must not stop the rest
            print(f"note: cannot tell whether {entry.dataset_id} participates in "
                  f"{period_name} ({type(exc).__name__}: {exc}) - not inherited.")
            continue
        if not skipped:
            continue

        source = _most_recent_promoted(conn, entry.dataset_id, period_name)
        if source is None:
            # CRITERION 9: no view, and nothing fabricated. An empty
            # table would be a lie with a schema on it.
            outcome.refused.append(Refused(
                dataset_id=entry.dataset_id, period=period_name,
                reason=("nothing is owed for this period and there is no earlier "
                        "promoted supply to stand on, so the table is genuinely "
                        "absent")))
            _record(conn, entry, action=decision_log.INHERIT_REFUSED, supply="",
                    period=period_name, stands_on=None,
                    reason=outcome.refused[-1].reason, effective_at=effective_at)
            continue

        stands_on, supply = source
        try:
            # UNDER BOTH SLOTS' LOCKS, judged again there (#113, REQ-PIPE-129
            # criterion 15), and the view and its entry one transaction.
            with decision_log.decision_transaction(conn):
                for slot in sorted({period_name, stands_on}):
                    decision_log.lock_slot(conn, entry.dataset_id, slot)
                physical = _still_stands_on(conn, entry.dataset_id, stands_on, supply,
                                            entry.table)
                conn.execute(
                    f'CREATE OR REPLACE VIEW "{schema}".'
                    f'"{supply_db._ident(entry.table, "table name")}" AS SELECT * FROM '
                    f'"{period_schema.period_schema(stands_on)}"."{physical}"')
                _record(conn, entry, action=decision_log.INHERIT, supply=supply,
                        period=period_name, stands_on=stands_on, reason=reason,
                        effective_at=effective_at, caused_by=caused_by)
        except InheritanceRefused as exc:
            # THE LOG SAYS A SUPPLY IS THERE AND THE SCHEMA DOES NOT.
            # Recorded as a refusal rather than raised, on criterion
            # 10's own terms and for the same reason the no-source case
            # is: one dataset's problem must not stop the rest of the
            # period being born.
            outcome.refused.append(Refused(
                dataset_id=entry.dataset_id, period=period_name, reason=str(exc)))
            _record(conn, entry, action=decision_log.INHERIT_REFUSED, supply="",
                    period=period_name, stands_on=None, reason=str(exc),
                    effective_at=effective_at)
            continue
        outcome.inherited.append(Inherited(
            dataset_id=entry.dataset_id, period=period_name, stands_on=stands_on,
            supply=supply, reason=reason))
    return outcome


def _record(conn, entry, *, action: str, supply: str, period: str,
            stands_on: str | None, reason: str, effective_at: str,
            caused_by: str | None = None) -> None:
    """One decision-log entry, with THE RULE as the actor (criterion 8).

    An INHERIT is recorded inside the transaction that created its view
    (#113), so the two cannot be observed apart; nested in a caller's
    transaction, apply_decision is a savepoint.
    """
    decision = decision_log.Decision(
        agency_id=entry.agency_id, collection_id=entry.collection_id,
        dataset_id=entry.dataset_id, action=action, supply=supply,
        actor=RULE_ACTOR, actor_kind=decision_log.RULE,
        effective_at=effective_at, to_slot=period, stands_on=stands_on,
        reason=reason, caused_by_supply=caused_by)
    with decision_log.apply_decision(conn, decision):
        pass


def inherited(conn: supply_db.SupplyConnection, dataset_id: str,
              period: str) -> Inherited | None:
    """This dataset's inheritance into this period, or None.

    FROM THE LOG, for the reason substitution.substituted() gives: a
    view in a schema says an object exists, not what put it there or
    whether it still means what it meant.
    """
    h = decision_log.held(conn, dataset_id, period)
    if not h or h.held_as != decision_log.INHERITED:
        return None
    return Inherited(dataset_id=dataset_id, period=period, stands_on=h.stands_on,
                     supply=h.holder, reason="")


def refusals(conn: supply_db.SupplyConnection | None = None) -> list[Refused]:
    """Every inheritance that could not complete, for the queue that
    surfaces them at WARNING prominence (criterion 10).

    OPENS ITS OWN CONNECTION WHEN NOT GIVEN ONE, and that is what lets
    outstanding.py call it without opening a connection of its own - the
    same shape as filing.filled_slots(). That module's docstring is
    explicit about why it matters: a narrow reader can only answer
    questions about RECORDS, where `supply_db.connect` can answer any
    question at all, including ones about supply rows it must never ask.
    """
    if conn is None:
        with supply_db.connect(read_only=True,
                                label="mothman:inheritance-refusals") as opened:
            return refusals(opened)
    rows = conn.execute(
        f"SELECT dataset_id, to_slot, reason FROM {decision_log.TABLE} "
        "WHERE action = ? ORDER BY dataset_id, to_slot",
        [decision_log.INHERIT_REFUSED]).fetchall()
    return [Refused(dataset_id=d, period=p, reason=r or "") for d, p, r in rows]


class InheritanceRefused(Exception):
    """An inheritance or un-inheritance this module will not perform.

    ONE EXCEPTION TYPE, the same shape substitution.SubstitutionRefused
    has and for the same reason: the caller's response is identical in
    every case - tell the operator what is wrong and touch nothing.
    """


def inherit_one(conn: supply_db.SupplyConnection, *, dataset_id: str,
                period: str, actor: str, reason: str,
                effective_at: str) -> Inherited:
    """One dataset, one period, at an operator's asking (REQ-PIPE-099
    criterion 1).

    NOT A SECOND IMPLEMENTATION OF inherit_into(). That one fills a
    whole period at its birth, for every dataset that owes it nothing,
    with the RULE as the actor; this fills ONE dataset's place in a
    period that already exists, because a person asked - the case
    criterion 6 creates, where an operator un-inherited a period to free
    a demotion and now has to put each one back explicitly.

    THE PERSON IS THE ACTOR (criterion 2, and REQ-GHUB-082 criterion
    33's second half). An inheritance the rule performed and one an
    operator asked for are different facts about who is accountable, and
    the log has to be able to tell them apart.

    TWO REFUSALS, both of them about the period rather than about the
    supply:
      - a period the dataset DOES participate in (criterion 9). A supply
        is owed for it, and standing it on an earlier one would hide
        exactly the gap this system exists to report.
      - a period that already holds a PROMOTED table (criterion 12).
        It resolves to a real supply already; a view over the top would
        be an indirection nobody could see past.
    """
    if not (reason or "").strip():
        raise InheritanceRefused(
            "an inheritance an operator asks for needs a reason, on the same "
            "terms as every other filing decision a person makes.")

    entry = hierarchy.dataset(dataset_id)
    skipped, schedule_reason = _does_not_participate(dataset_id, period)
    if not skipped:
        raise InheritanceRefused(
            f"{dataset_id} DOES participate in {period}, so a supply is owed "
            f"for it. Inheriting would stand this period on an earlier supply "
            f"and hide a gap somebody should see. If the supply is genuinely "
            f"not coming, that is a substitution - a person deciding what to "
            f"stand on - rather than an inheritance.")

    already = period_schema.promoted_in(conn, period, [entry.table]).get(entry.table)
    if already:
        raise InheritanceRefused(
            f"{period} already resolves to a real supply for {dataset_id} "
            f"({', '.join(already)}). There is nothing to inherit into.")

    source = _most_recent_promoted(conn, dataset_id, period)
    if source is None:
        raise InheritanceRefused(
            f"there is no earlier promoted supply for {dataset_id} to stand "
            f"{period} on. The table is genuinely absent, and an empty one "
            f"would be a lie with a schema on it.")

    stands_on, supply = source
    # RESOLVED BEFORE THE TRANSACTION OPENS, so a period whose table has
    # gone missing is a refusal rather than a rolled-back decision - the
    # same ordering substitution.substitute() uses.
    physical = _physical_in(conn, period=stands_on, logical=entry.table)
    schema = period_schema.period_schema(period)
    decision = decision_log.Decision(
        agency_id=entry.agency_id, collection_id=entry.collection_id,
        dataset_id=dataset_id, action=decision_log.INHERIT, supply=supply,
        actor=actor, actor_kind=decision_log.PERSON, effective_at=effective_at,
        to_slot=period, stands_on=stands_on, reason=reason)
    with decision_log.apply_decision(conn, decision):
        # JUDGED AGAIN UNDER THE LOCK (#113, REQ-PIPE-129 criterion 15).
        physical = _still_stands_on(conn, dataset_id, stands_on, supply, entry.table)
        conn.execute(
            f'CREATE OR REPLACE VIEW "{schema}".'
            f'"{supply_db._ident(entry.table, "table name")}" AS SELECT * FROM '
            f'"{period_schema.period_schema(stands_on)}"."{physical}"')
    return Inherited(dataset_id=dataset_id, period=period, stands_on=stands_on,
                      supply=supply, reason=schedule_reason or reason)


def _still_stands_on(conn, dataset_id: str, stands_on: str, supply: str,
                     logical: str) -> str:
    """Under the decision's lock on both slots: `stands_on` still holds
    `supply` as a promoted table, and its physical name (#113, REQ-PIPE-129
    criterion 15). A promotion that displaced it while this was being
    decided is refused here, rather than the view quietly reading the
    newcomer under the old supply's name."""
    h = decision_log.held(conn, dataset_id, stands_on)
    if not h or h.held_as != decision_log.PROMOTED or h.holder != supply:
        raise InheritanceRefused(
            f"{stands_on} no longer holds {supply} - "
            + (f"it holds {h.holder} ({h.held_as})" if h and h.holder else "it holds nothing")
            + ". Something changed while this was being decided; try again.")
    return _physical_in(conn, period=stands_on, logical=logical)


def un_inherit(conn: supply_db.SupplyConnection, *, dataset_id: str,
               period: str, actor: str, reason: str, effective_at: str,
               confirmed: bool = False) -> None:
    """Take a period's inheritance back out (REQ-PIPE-099 criterion 3).

    WHAT IT IS FOR is criterion 5, and it is worth stating because the
    operation reads like tidying and is not: a demotion, rejection or
    re-file is REFUSED while a later period stands on that supply
    (REQ-PIPE-084 criterion 11), and an inherited period stands on one
    just as hard as a substituted one. Un-inheriting is how an operator
    clears that obstacle. The obstacle exists to make somebody look, so
    clearing it is a decision in its own right and is recorded as one.

    THE VIEW GOES, so nothing in that period depends on the supply any
    more. A period left with a view pointing at a table that is about to
    move is the state this whole refusal exists to prevent.

    NOTHING PUTS IT BACK (criterion 4 and criterion 6). inherit_into()
    runs once, at a period's birth, so it will not revisit this one;
    inherit_one() is the only way back and an operator has to ask for it
    per period, which is the criterion's own "explicitly afterwards".

    EXPLICIT CONFIRMATION (criterion 10), as a required argument rather
    than a prompt inside the function - the same reasoning
    substitution.de_substitute() records: a prompt here would be skipped
    by the first caller that is not a terminal.
    """
    if not confirmed:
        raise InheritanceRefused(
            f"un-inheriting {period} needs an explicit confirmation. Anything "
            f"reading that period for {dataset_id} will stop resolving the "
            f"moment this is done.")
    if not (reason or "").strip():
        raise InheritanceRefused(
            "an un-inheritance needs a reason, on the same terms as the "
            "inheritance it reverses.")

    current = inherited(conn, dataset_id, period)
    if current is None:
        raise InheritanceRefused(
            f"{period} holds no inheritance for {dataset_id} to remove. Either "
            f"it never inherited, somebody has already removed it, or what it "
            f"holds is a SUBSTITUTION - which is de-substituted rather than "
            f"un-inherited, because a person decided it and the log should say "
            f"which of the two is being undone.")

    entry = hierarchy.dataset(dataset_id)
    decision = decision_log.Decision(
        agency_id=entry.agency_id, collection_id=entry.collection_id,
        dataset_id=dataset_id, action=decision_log.UN_INHERIT,
        supply=current.supply, actor=actor, actor_kind=decision_log.PERSON,
        effective_at=effective_at, from_slot=period, reason=reason)
    schema = period_schema.period_schema(period)
    with decision_log.apply_decision(conn, decision):
        conn.execute(
            f'DROP VIEW IF EXISTS "{schema}".'
            f'"{supply_db._ident(entry.table, "table name")}"')
