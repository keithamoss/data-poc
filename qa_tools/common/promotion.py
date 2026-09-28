"""Promotion - the act that fills a slot (REQ-PIPE-075).

A supply reaches a period by being PROMOTED into it, and nothing else
fills a slot. An arrival does not, a staged supply does not, and a
rejected one certainly does not - `filing.filled_slots()` has been a
deliberate stub saying so since before this module existed.

TWO THINGS HERE ARE EASY TO BUILD THE OTHER WAY ROUND, and both are
criteria rather than preferences:

THE TABLES MOVE BEFORE THE ENTRY IS WRITTEN (criterion 9). An entry
written first would say a supply is promoted while the period schema
does not hold it, and - worse - nothing would ever retry, because the
log says it is done. Written in this order, an interruption leaves the
tables moved and no entry, so the next attempt repeats the promotion
and lands where it should. Repeating is cheap; skipping is silent.

PROMOTION MOVES, IT DOES NOT COPY (criterion 15). Staging then holds
only supplies nobody has decided on, which is what makes "what is
waiting for me" answerable by looking at it. PostgreSQL's ALTER TABLE
... SET SCHEMA is a real move and a catalogue-only one, so this costs
nothing even for a large table - see supply_db.move_table.

WHAT THIS MODULE DOES NOT DO, deliberately: decide WHETHER a supply
should be promoted. The automatic gate reads a QA verdict and this
module does not go browsing for one - the caller has it in hand, the
same division decision_log.Decision already makes for `supply_is_red`.
"""
from __future__ import annotations

from collections.abc import Sequence

from qa_tools.common import decision_log, period_schema, supply_db


def promote(conn: supply_db.SupplyConnection, *,
            agency_id: str,
            collection_id: str,
            dataset_id: str,
            supply: str,
            period: str,
            physical_tables: Sequence[str],
            actor: str,
            actor_kind: str,
            effective_at: str,
            reason: str | None = None,
            supply_is_red: bool = False,
            from_schema: str | None = None) -> bool:
    """Move this supply's tables into `period` and record the decision.

    Returns True where it promoted, False where the supply was already
    promoted into this slot and there was nothing to do (criterion 10) -
    a repeat is an ordinary thing for a retry to hit, not an error.

    Raises whatever the move raises. That is the point of the ordering:
    a failure here leaves no entry, so the slot is still unfilled and
    the caller may try again.
    """
    # ALREADY DONE? Asked of the LOG rather than of the catalogue, for
    # the same reason filled_slots() does: a table in the schema that no
    # decision put there is not a promotion.
    if decision_log.promoted_into(conn, dataset_id, period) == supply:
        return False

    schema = period_schema.ensure_period_schema(conn, period)
    decision = decision_log.Decision(
        agency_id=agency_id,
        collection_id=collection_id,
        dataset_id=dataset_id,
        action=decision_log.PROMOTE,
        supply=supply,
        actor=actor,
        actor_kind=actor_kind,
        effective_at=effective_at,
        to_slot=period,
        reason=reason,
        supply_is_red=supply_is_red,
    )

    # A supply usually comes from staging, but a rejection being
    # reversed comes from the rejected schema - criterion 9's "reversed
    # by a later recorded decision".
    source = from_schema or supply_db.STAGING_SCHEMA

    def move() -> None:
        for physical in physical_tables:
            supply_db.move_table(conn, physical, source, schema)

    # ONE TRANSACTION, entry and move together - see this module's
    # docstring on why that is STRONGER than criterion 9's literal
    # ordering rather than a departure from it. decision_log's own
    # record_automatic() says the same in as many words: "anything that
    # touches the warehouse uses the context manager, so that the entry
    # and the change stay one transaction". This touches the warehouse.
    with decision_log.apply_decision(conn, decision):
        move()
    return True


def filled_slots(conn: supply_db.SupplyConnection, dataset_id: str) -> frozenset[str]:
    """Slots this dataset has a supply PROMOTED into (criterion 6).

    Derived from the decision log, never from the warehouse catalogue,
    and the criterion says so in as many words. A table sitting in a
    period schema that no decision promoted is a table somebody put
    there; calling that a filled slot would let a stray object decide
    whether a real supply may be promoted.

    Each slot is resolved through decision_log.promoted_into(), so a
    slot later emptied by a reject, a demote or a re-file OUT stops
    being filled without this having to know those rules itself.
    """
    rows = conn.execute(
        f"SELECT DISTINCT to_slot FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND to_slot IS NOT NULL", [dataset_id]).fetchall()
    return frozenset(
        slot for (slot,) in rows
        if decision_log.promoted_into(conn, dataset_id, slot) is not None)


# ---------------------------------------------------------------------------
# The automatic gate (criteria 1-5 and 12).
#
# A PURE FUNCTION over facts the caller already has, deliberately. Whether
# a supply should promote and what its verdict was are different
# questions, and decision_log.Decision already makes the same split for
# `supply_is_red`. A gate that went browsing for its own inputs could not
# be asked a hypothetical, which is most of what its tests do.
# ---------------------------------------------------------------------------

#: Statuses that promote themselves into an empty slot (criterion 1).
#: Amber is included on purpose: an amber supply is usable data with
#: something worth knowing about it, and holding every one of them for a
#: person is how a queue becomes noise nobody reads.
PROMOTES_ITSELF = frozenset({"green", "amber"})


def should_promote(*, status: str,
                   slot_filled: bool,
                   held_without_slot: bool,
                   has_active_checks: bool,
                   decided_by_a_person: bool = False,
                   contested: bool = False) -> tuple[bool, str | None]:
    """Whether automation may promote this supply, and why not if not.

    The reason is not decoration: "not promoted" with no explanation is
    the state an operator has to escalate, and this string is what the
    ticket and the terminal both end up showing.

    THE ORDER OF THE REFUSALS IS DELIBERATE. Several can be true at once,
    and the one reported should be the one worth acting on first - a red
    verdict is the thing to fix, where a filled slot is merely the reason
    today's attempt stopped.
    """
    if contested:
        # REQ-PIPE-079 criterion 13, and REQ-PIPE-105 criterion 6.
        # Ahead of everything, and "whatever the period holds" is the
        # criterion's own phrase: where several files claim one dataset
        # nobody has said which file IS the supply, so there is no
        # supply here to ask any of the later questions about.
        return False, ("several files claim this dataset and nothing says "
                       "which one is the supply, so a person decides before "
                       "anything is promoted")
    if held_without_slot:
        # Criterion 5. Then, because a supply with no confident slot has
        # no slot to be filled or empty, so every later question is moot.
        return False, ("no slot could be confidently claimed for this supply, "
                       "so it is neither promoted nor arrival-classified")
    if decided_by_a_person:
        # REQ-PIPE-076 criterion 7. Ahead of the verdict, because a person
        # having decided outranks whatever the checks now say.
        return False, ("a person has already decided about this supply, and "
                       "automation defers to them permanently")
    if status not in PROMOTES_ITSELF:
        # Criterion 3.
        return False, (f"this supply's status is {status} rather than green or "
                       "amber, so it waits for a person")
    if not has_active_checks:
        # Criterion 12, and the dangerous direction: a table nobody wrote
        # a check for computes as green by having no failures, and would
        # otherwise promote itself on the strength of nothing having been
        # asked of it.
        return False, ("this table has no ACTIVE checks, so nothing was "
                       "asked of it and green means only that")
    if slot_filled:
        # Criterion 4, whatever the status.
        return False, ("this supply's slot is already filled by a promoted "
                       "supply, so a person decides what happens to it")
    return True, None


def may_arrival_classify(*, held_without_slot: bool) -> bool:
    """Criterion 5's second half.

    A supply with no confident slot is not arrival-classified either -
    early, on time and late are all claims ABOUT A SLOT, so making one
    without a slot would be inventing the thing being measured against.
    """
    return not held_without_slot


def promote_each(conn: supply_db.SupplyConnection,
                 work: Sequence[dict], *,
                 agency_id: str,
                 collection_id: str,
                 period: str,
                 actor: str,
                 actor_kind: str,
                 effective_at: str,
                 reason: str | None = None) -> tuple[list[str], dict[str, str]]:
    """Promote several datasets' supplies, ONE DECISION EACH.

    Returns (dataset ids promoted, {dataset id: why it failed}).

    TWO CRITERIA MEET HERE and they pull the same way. Criterion 11 says
    one dataset's failure must not stop the others - at ~30 datasets on a
    quarterly asset, a run that abandons twenty-nine promotions because
    the thirtieth had a bad table is a run somebody turns off. Criterion
    14 says no operation promotes several supplies on ONE decision, so
    this is a loop over promote() rather than a bulk write: each supply
    gets its own entry, its own reason and its own transaction, and the
    log can answer "why was THIS one promoted" a year later.

    A FAILURE LEAVES NOTHING HALF DONE, because each promote() is its own
    transaction - see this module's docstring. The failure is REPORTED
    rather than raised, because the caller's job is to finish the run and
    then tell somebody, not to stop.
    """
    promoted: list[str] = []
    failures: dict[str, str] = {}
    for item in work:
        dataset_id = item["dataset_id"]
        try:
            did = promote(conn, agency_id=agency_id, collection_id=collection_id,
                          dataset_id=dataset_id, supply=item["supply"],
                          period=item.get("period", period),
                          physical_tables=item["physical_tables"],
                          actor=actor, actor_kind=actor_kind,
                          effective_at=effective_at,
                          reason=item.get("reason", reason),
                          supply_is_red=item.get("supply_is_red", False))
        except Exception as exc:
            # DELIBERATELY BROAD. Anything one dataset's promotion can
            # raise - a missing table, a refused decision, a lock timeout
            # - is a reason to carry on with the other twenty-nine and
            # report this one. Narrowing it would mean a new failure mode
            # silently becoming fatal to the whole run.
            failures[dataset_id] = f"{type(exc).__name__}: {exc}"
            continue
        if did:
            promoted.append(dataset_id)
    return promoted, failures


def status_of(dataset_id: str, results: Sequence[dict], *,
              reads: dict[str, list[str]]) -> str | None:
    """This dataset's status, from EVERY check that contributes to it
    (criterion 2).

    `reads` is check_id -> the logical tables that check declares it
    reads, which is what tables_read.declared_by_check_id() returns and
    what the dashboard already uses. Reusing it rather than deriving a
    second answer is deliberate: two implementations of "which checks
    touch this dataset" would drift, and the drift would show as a
    supply promoting itself past a red check.

    THREE SOURCES, and the middle one is what a naive version misses:
      - the dataset's own results, whatever their scope;
      - a CROSS-TABLE check filed under another dataset that declares it
        reads one of this dataset's tables - a referential check between
        placements and carers belongs to both, and is filed under
        whichever it happened to be declared on;
      - anything else recorded against this dataset.

    RETURNS None WHERE NOTHING CONTRIBUTED, never "green". A dataset with
    no contributing check has no verdict to gate on, and calling that
    green is criterion 12's check-free table arriving by another road.
    """
    from qa_tools.common import dataset_status, hierarchy

    try:
        own_tables = {hierarchy.dataset(dataset_id).table}
    except hierarchy.UnknownDatasetError:
        # A dataset the tree does not know. Its id is the best name for
        # its table there is - the same fallback tables_read._own_table
        # makes, and for the same reason: being slightly over-inclusive
        # beats raising inside a promotion gate.
        #
        # NARROW ON PURPOSE. This was `except Exception` for about a
        # minute, and it silently swallowed an AttributeError from
        # getting the field name wrong - the fallback then made every
        # cross-table check look like it read nothing. A bare except
        # around a lookup turns a bug into a wrong answer.
        own_tables = {dataset_id}

    contributing = []
    for record in results:
        if record.get("dataset_id") == dataset_id:
            contributing.append(record["status"])
            continue
        declared = reads.get(record.get("check_id") or "")
        if declared and own_tables.intersection(declared):
            contributing.append(record["status"])

    if not contributing:
        return None
    return dataset_status.worst_of(contributing)


# ---------------------------------------------------------------------------
# When a promotion needs QA running again (criteria 16 and 17).
#
# A check's verdict is a statement about a supply READ ALONGSIDE a
# particular period's other tables. Move the supply to a different
# period and it sits beside different tables, so a referential check
# that passed against August's carers says nothing about May's.
# Re-running is not caution - the old verdict answers a different
# question.
# ---------------------------------------------------------------------------


def needs_requalification(*, qa_ran_against: str | None,
                          promoted_into: str,
                          actor_kind: str | None = None) -> bool:
    """Whether promoting into `promoted_into` needs QA run again.

    `actor_kind` is accepted and deliberately IGNORED. Criterion 16 is
    about a person's promotion and criterion 17 about any promotion or
    re-file, and both turn on the PERIOD rather than on who asked - a
    verdict computed against one period is no more applicable because a
    person rather than a rule moved it. The parameter exists so a caller
    passing it is not silently wrong about what decides this.

    AN UNKNOWN QA PERIOD RE-RUNS. Not knowing what a verdict was
    computed against is not evidence that it still applies, and the
    cost of being wrong the other way is a stale verdict presented as a
    current one.
    """
    if qa_ran_against is None:
        return True
    return qa_ran_against != promoted_into


def checks_reading(table: str, *, reads: dict[str, list[str]]) -> set[str]:
    """The checks that read this logical table (criterion 17's second half).

    From the check DEFINITIONS - what tables_read.declared_by_check_id()
    returns - rather than from a new record of its own. A check absent
    from one run still reads what it declares, and the dashboard already
    answers this question the same way.
    """
    return {check_id for check_id, tables in reads.items() if table in tables}


def newest_promoted(conn: supply_db.SupplyConnection,
                    dataset_id: str, period: str) -> str | None:
    """The supply most recently PROMOTED into this period, or None.

    REQ-PIPE-105 criterion 7, and it deliberately disagrees with
    period_schema.newest(), which orders by the ARRIVAL key parsed out
    of a physical table name. That is the right answer to a different
    question.

    ARRIVAL ORDER AND PROMOTION ORDER COME APART the moment a person is
    involved. A supply that arrived on Tuesday and was held for a
    decision until Friday is NEWER, as the period sees it, than one that
    arrived on Wednesday and promoted itself immediately - because the
    period holds what was decided into it, in the order it was decided.
    Ordering by arrival would silently prefer the Wednesday file, a
    version nobody chose, over the one somebody looked at and promoted.

    ONLY PROMOTED SUPPLIES ARE CANDIDATES. A staged one has not been
    chosen by anybody, and criteria 6 and 8 say an ambiguous staged
    table is ABSENT rather than a contender.

    Ordered by (effective_at, id) for the same reason
    decision_log.promoted_into does: two decisions can share an instant,
    and `id` is the only total order there is.
    """
    rows = conn.execute(
        f"SELECT action, supply FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND (to_slot = ? OR from_slot = ?) "
        "ORDER BY effective_at DESC, id DESC LIMIT 1",
        [dataset_id, period, period]).fetchall()
    if not rows:
        return None
    action, supply = rows[0]
    # The last decision touching this slot decides what it holds - a
    # promote or a re-file INTO it fills it, anything else empties it.
    # Reusing that rule rather than restating it is why this asks the
    # log rather than the catalogue.
    if action in (decision_log.PROMOTE, decision_log.REFILE):
        return supply
    return None
