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

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

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
            from_schema: str | None = None,
            amber=None,
            remove_substitution: bool = False,
            status: str | None = None,
            replacing=None) -> bool:
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
    # decision put there is not a promotion. Asked again under the lock.
    if decision_log.promoted_into(conn, dataset_id, period) == supply:
        return False
    from qa_tools.common import supersession

    if not physical_tables and not supersession.is_superseded(conn, dataset_id, supply):
        # (A superseded supply is refused by the decision log under the
        # lock, naming un-supersede - a better answer than this one.)
        # NOTHING TO MOVE IS NOT A PROMOTION (post-build-review #112): a
        # rejected supply or a mistyped id has no staged tables, and
        # recording it would supersede what the period holds while leaving
        # that table in place - two answers, or none.
        raise decision_log.DecisionRefused(
            f"{supply} has no tables in "
            f"{from_schema or supply_db.STAGING_SCHEMA} to promote, so nothing was done. "
            "Check the supply id against `mothman supply queue`.")
    _refuse_what_the_slot_forbids(conn, dataset_id, supply, period, actor_kind,
                                  remove_substitution, replacing=replacing)

    # OPENED, NOT JUST CREATED (REQ-PIPE-098 criterion 4): a first
    # promotion is one of the two ways a period comes into existence,
    # and it is the moment every dataset that owes this period nothing
    # inherits into it. Before the transaction below, because
    # inheritance writes decisions of its own.
    period_schema.open_period(conn, period, opened_by=actor,
                               effective_at=effective_at)
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
        # REQ-PIPE-122 criterion 19: the setting an automatic amber
        # promotion acted under. None for everything else.
        amber_setting=amber.value if amber else None,
        amber_level=amber.level if amber else None,
        amber_version=amber.version if amber else None,
        # THE STATUS IT WAS PROMOTED ON (REQ-PIPE-130 criterion 11), rule or
        # person: the gate passes the one it judged; a person's promotion
        # reads it from the recorded results, the same function the gate's
        # re-evaluations use (REQ-PIPE-121 NFR 4).
        promoted_status=_status_at_promotion(conn, dataset_id, supply, status),
        # THE SETTING A RULE'S REPLACEMENT ACTED UNDER (REQ-PIPE-123
        # criterion 5); `replaces` is filled in under the lock below.
        replacement_setting=replacing.value if replacing else None,
        replacement_level=replacing.level if replacing else None,
        replacement_version=replacing.version if replacing else None,
    )

    # A supply usually comes from staging, but a rejection being
    # reversed comes from the rejected schema - criterion 9's "reversed
    # by a later recorded decision".
    source = from_schema or supply_db.STAGING_SCHEMA

    def move() -> None:
        # INTO THE PERIOD THROUGH THE ONE CODE PATH, under its plain base
        # name (REQ-PIPE-129 criteria 1, 2 and 9).
        from qa_tools.common import period_tables

        for physical in physical_tables:
            period_tables.bring_in(conn, physical=physical, source_schema=source,
                                   period=period)

    # ONE TRANSACTION, entry and move together - see this module's
    # docstring on why that is STRONGER than criterion 9's literal
    # ordering rather than a departure from it. decision_log's own
    # record_automatic() says the same in as many words: "anything that
    # touches the warehouse uses the context manager, so that the entry
    # and the change stay one transaction". This touches the warehouse.
    # ONE TRANSACTION FOR EVERYTHING (REQ-PIPE-128 criteria 2 and 4, NFR
    # 3): removing a substitution, superseding what the slot held, and the
    # promotion itself - each its own entry, all or none. Nested
    # apply_decision blocks are savepoints inside this one.
    with decision_log.decision_transaction(conn):
        # THE SLOT IS JUDGED UNDER ITS LOCK (post-build-review #112). Read
        # before it, two promotions at once each saw the slot as it was and
        # neither displaced the other. The lock is re-entrant, so the
        # decisions below take it again harmlessly.
        decision_log.lock_slot(conn, dataset_id, period)
        if decision_log.promoted_into(conn, dataset_id, period) == supply:
            return False
        h = _refuse_what_the_slot_forbids(conn, dataset_id, supply, period, actor_kind,
                                          remove_substitution, replacing=replacing)
        substituted = bool(h and h.held_as == decision_log.SUBSTITUTED)
        displaced = (h.holder if h and h.held_as == decision_log.PROMOTED
                     and h.holder != supply else None)
        if substituted:
            from qa_tools.common import hierarchy, substitution

            substitution.de_substitute(
                conn, agency_id=agency_id, collection_id=collection_id,
                dataset_id=dataset_id, logical_table=hierarchy.dataset(dataset_id).table,
                period=period, actor=actor, effective_at=effective_at, confirmed=True,
                reason=reason or f"{supply} promoted into {period}")
        if displaced:
            from qa_tools.common import supersession

            supersession.supersede_promoted(
                conn, agency_id=agency_id, collection_id=collection_id,
                dataset_id=dataset_id, supply=displaced, period=period, by=supply,
                actor=actor, actor_kind=actor_kind, effective_at=effective_at,
                replacing=list(physical_tables))
        if displaced:
            # The supply this promotion REPLACED, named on its own entry
            # (REQ-PIPE-123 criterion 5) - known only now, under the lock.
            import dataclasses

            decision = dataclasses.replace(decision, replaces=displaced)
        with decision_log.apply_decision(conn, decision):
            move()
    # CHECKED WHEN IT IS TAKEN (REQ-PIPE-081 criterion 13), after the
    # transaction - mid-way, a supersession is not a state to report.
    from qa_tools.common import census

    census.after_move(conn, trigger="promote", period=period)
    return True


def _status_at_promotion(conn, dataset_id: str, supply: str, given: str | None) -> str | None:
    """The supply's status now, for the promotion entry - green, amber or
    red, or None where no recorded result contributes."""
    if given is not None:
        return given if given in ("green", "amber", "red") else None
    from qa_tools.common import supply_status

    from qa_tools.common import hierarchy

    try:
        found = supply_status.status(conn, dataset_id, supply)
    except (UnreadableVerdictError, hierarchy.UnknownDatasetError):
        return None
    return found if found in ("green", "amber", "red") else None


def _refuse_what_the_slot_forbids(conn, dataset_id: str, supply: str, period: str,
                                  actor_kind: str, remove_substitution: bool,
                                  replacing=None):
    """What the slot holds decides what else happens (REQ-PIPE-128
    criteria 4, 5 and 10). Returns what it holds; raises where it forbids
    this promotion."""
    h = decision_log.held(conn, dataset_id, period)
    if h and h.held_as == decision_log.INHERITED:
        # Criterion 5: nothing was expected for this period.
        raise decision_log.DecisionRefused(
            f"Nothing was expected from {dataset_id} for {period}: it is inherited, "
            f"standing on an earlier period because the schedule owes nothing then. "
            f"Un-inherit it first, as its own decision:\n"
            f"  mothman supply decide --operation un-inherit --dataset {dataset_id} "
            f"--period {period} --reason '<why>' --yes")
    if (actor_kind == decision_log.RULE and h and h.held_as == decision_log.PROMOTED
            and h.holder != supply and replacing is None):
        # (REQ-PIPE-123: unless the replacement setting the gate resolved
        # permits it - the only rule that displaces accepted data.)
        # A RULE NEVER DISPLACES (criterion 2 is a person's promotion). The
        # gate's own filled-slot check is read before the lock; this is the
        # same answer under it, so a person promoting at the same instant
        # wins rather than being superseded (post-build-review #112).
        raise decision_log.DecisionRefused(
            f"{period} already holds {h.holder}; no automatic rule displaces a promoted "
            f"supply. A person can:\n"
            f"  mothman supply decide --operation promote --dataset {dataset_id} "
            f"--period {period} --supply {supply} --reason '<why>'")
    substituted = bool(h and h.held_as == decision_log.SUBSTITUTED)
    if substituted and actor_kind == decision_log.RULE:
        # Criterion 10: no automatic rule promotes into a substitution.
        raise decision_log.DecisionRefused(
            f"{period} is substituted onto {h.stands_on}; no automatic rule promotes "
            f"into it. A person can, removing the substitution:\n"
            f"  mothman supply decide --operation promote --dataset {dataset_id} "
            f"--period {period} --supply {supply} --reason '<why>'")
    if substituted and not remove_substitution:
        # Criterion 4: the person is told first, and confirms.
        raise decision_log.DecisionRefused(
            f"{period} is substituted onto {h.stands_on}; promoting {supply} removes "
            f"that substitution. Confirm it by promoting through the command, which "
            f"shows the consequence first:\n"
            f"  mothman supply decide --operation promote --dataset {dataset_id} "
            f"--period {period} --supply {supply} --reason '<why>'")
    return h


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

    AND SO A SUBSTITUTED SLOT COUNTS TOO (REQ-PIPE-084 criterion 4),
    which arrived later and needed no change here - that is the
    delegation paying for itself. The period answers, so nothing should
    treat it as owed, and an arrival for it is a supply landing on a
    filled slot rather than the one that was missing.
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

#: REQ-PIPE-122: the amber setting's strictest value, and what the gate
#: says when it applies. The words "amber, waiting for a person" are this
#: state's own label - deliberately not "held" (criterion 18).
AMBER_HOLD = "hold"
AMBER_WAITING_REASON = ("this supply is amber and its amber setting is hold, so it "
                        "is not promoted automatically - amber, waiting for a person")

#: Statuses that promote themselves into an empty slot (criterion 1).
#: Amber is included on purpose: an amber supply is usable data with
#: something worth knowing about it, and holding every one of them for a
#: person is how a queue becomes noise nobody reads.
PROMOTES_ITSELF = frozenset({"green", "amber"})


#: The window a promotion's invented lag falls in, for a supply being
#: replayed from history. Hours to a couple of days: long enough to
#: read as somebody getting to it, short enough not to read as
#: neglect.
_LAG_MIN = timedelta(hours=1)
_LAG_SPAN = timedelta(days=3) - _LAG_MIN


def effective_at_for(received_at: datetime, *, now: datetime | None = None,
                      seed: str = "") -> datetime:
    """When a promotion of this supply took effect.

    TWO THINGS ARE TRUE OF ANY PROMOTION, synthetic or real, and this
    is just both of them: it cannot have taken effect BEFORE the supply
    arrived, and it cannot have taken effect in the FUTURE. So the
    answer is `min(now, received_at + lag)`.

    WHY THAT IS NOT A REPLAY HACK, which is the point of expressing it
    this way. In production an arrival is minutes old, `received_at +
    lag` is ahead of now, and the rule returns `now` - unchanged
    behaviour, no mode to set. In a replay the arrival is years old and
    the rule returns the backdated instant. One expression, correct in
    both, and nothing to forget to switch on.

    WHAT IT FIXES. A bootstrap replays four years of arrivals under one
    wall clock, so every promotion used to take effect within the same
    few minutes - 91 decisions across one distinct day, measured
    2026-10-02 - and "what did we hold as at 30 June 2024" resolved to
    nothing in place, for everything. Meanwhile the ARRIVALS were
    backdated properly, so the generator's fiction disagreed with
    itself: February 2023 for the arrival, today for its promotion.

    THE LAG IS INVENTED, AND SAYING SO IS PART OF THE DESIGN. Keith
    chose it (2026-10-02) over promoting at the arrival instant, so
    REQ-PIPE-080's receipt-to-promotion interval shows a spread rather
    than a column of zeros. It is seeded off the run id so a
    regeneration reproduces it, like everything else here - but no
    particular supply's wait is a measurement of anything, and nothing
    should be inferred from one. The synthetic corpus is fiction
    throughout; this part of it is merely newer.
    """
    from qa_tools.common import asset_time

    now = now or asset_time.now()
    digest = hashlib.sha256((seed or "").encode()).digest()
    # A FRACTION OF THE WINDOW from the digest, rather than a modulo
    # over hours - the window is a duration, so the lag should move
    # with it if it is ever retuned.
    fraction = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    return min(now, received_at + _LAG_MIN + _LAG_SPAN * fraction)


def should_promote(*, status: str,
                   slot_filled: bool,
                   held_without_slot: bool,
                   has_active_checks: bool,
                   decided_by_a_person: bool = False,
                   contested: bool = False,
                   inherited: bool = False,
                   amber_setting: str | None = None) -> tuple[bool, str | None]:
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
    if not has_active_checks:
        # Criterion 12, and the dangerous direction: a table nobody wrote
        # a check for computes as green by having no failures, and would
        # otherwise promote itself on the strength of nothing having been
        # asked of it.
        #
        # AHEAD OF THE VERDICT, because the two arrive together:
        # status_of() returns None where nothing contributed, which IS
        # the check-free case. Reporting "its status is None rather than
        # green or amber" sends an operator looking for a failing check
        # that does not exist. If nothing was asked, there is no answer
        # to report.
        return False, ("this table has no ACTIVE checks, so nothing was "
                       "asked of it and green means only that")
    if status not in PROMOTES_ITSELF:
        # Criterion 3.
        return False, (f"this supply's status is {status} rather than green or "
                       "amber, so it waits for a person")
    if status == "amber" and amber_setting == AMBER_HOLD:
        # REQ-PIPE-122 criterion 10. Never "held" (criterion 18) - that
        # word means a supply filed to no slot.
        return False, AMBER_WAITING_REASON
    if slot_filled:
        # Criterion 4, whatever the status.
        return False, ("this supply's slot is already filled by a promoted "
                       "supply, so a person decides what happens to it")
    if inherited:
        # REQ-PIPE-098 criterion 17, and it needs its own refusal rather
        # than riding on the one above. A SUBSTITUTED period counts as
        # filled, so a supply arriving into one is already caught. An
        # INHERITED period deliberately does not - nothing was owed - so
        # without this the rule would promote straight over the
        # inherited view and nobody would be asked.
        return False, ("nothing was owed for this period, so it stands on an "
                       "earlier supply - a person decides whether this one "
                       "replaces it")
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
                          supply_is_red=item.get("supply_is_red", False),
                          amber=item.get("amber"), status=item.get("status"),
                          replacing=item.get("replacing"))
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


class UnreadableVerdictError(RuntimeError):
    """A check result whose status this gate cannot map to a verdict.

    Its own type because the CALLER has to tell it apart from a red
    supply: one is a supply waiting for a person, the other is a bug or
    a new tool status nobody taught this about."""


def _gating_status(record: dict) -> str | None:
    """The verdict the gate reads for one result.

    A GAP RED WARNS, IT DOES NOT BLOCK (REQ-QAC-108 criterion 15 as
    amended 2026-10-05, Keith). A drift or volume check measured across
    an owed period with nothing promoted is recorded red, with the
    measurement's own verdict kept beside it as `measured_status`; the
    gate reads that measurement, so a real drift still blocks and the gap
    alone does not. As signed, one supply left waiting made every later
    supply of its dataset wait too.

    With NO REFERENCE AT ALL (criterion 9) there is no measurement, and
    the check is read as having no reference - the same quiet status a
    new dataset's drift check carries - so it neither passes nor blocks.
    """
    if record.get("reference_gap"):
        if record.get("reference_not_evaluated"):
            return "nodata"
        measured = record.get("measured_status")
        if measured:
            return measured
    return record.get("status")


def _is_file_check(check_id: str | None) -> bool:
    from qa_tools.common import check_id as cid, file_checks

    parsed = cid.try_parse(check_id or "")
    return bool(parsed and parsed.tool == file_checks.TOOL)


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
        # A FILE CHECK IS NEVER PART OF A STATUS (REQ-QAC-096 criteria 9 and
        # 10): it is a statement about the file as delivered, and a refused
        # file reaches its dataset only as a failed load. Skipped HERE, at
        # the one status function, rather than at each reader - several
        # read every scope of a run, and the first version of the file
        # checks would have had a column-order warning turning a green
        # supply amber.
        if _is_file_check(record.get("check_id")):
            continue
        mine = record.get("dataset_id") == dataset_id
        if not mine:
            declared = reads.get(record.get("check_id") or "")
            mine = bool(declared and own_tables.intersection(declared))
        if not mine:
            continue
        # A RECORDED RESULT CARRIES ITS TOOL'S OWN VERDICT - `pass`,
        # `warn`, `fail`, `error` - and the gate speaks the dashboard's
        # green/amber/red. The first version of this fed the raw verdict
        # straight into worst_of(), which orders only the second
        # vocabulary, so EVERY real result raised. Found by writing a
        # test against the shape qa.check_result actually holds rather
        # than the shape the gate wished for.
        verdict = dataset_status.dashboard_status(_gating_status(record))
        if verdict is None:
            # AN UNREADABLE VERDICT IS NOT EVIDENCE OF HEALTH, and
            # dropping it would be exactly that - the supply would
            # promote itself on the strength of a result nobody could
            # read. Raised rather than mapped to red, because "it is
            # red" sends an operator looking for a failing check and
            # the real problem is that we do not understand the answer.
            raise UnreadableVerdictError(
                f"check {record.get('check_id')!r} recorded status "
                f"{record.get('status')!r}, which is not a verdict this gate "
                f"can read - so nothing can be concluded about {dataset_id}")
        contributing.append(verdict)

    if not contributing:
        return None
    # rollup_statuses(), NOT worst_of(), and the difference only shows
    # in one case - which is the case this line exists for. worst_of()
    # is a reduce seeded at green, so a dataset whose every contributing
    # check carries a QUIET status (a drift check with no reference,
    # REQ-QAC-108 criterion 5) rolls up to green and promotes itself on
    # the strength of nothing having been measured. rollup_statuses()
    # returns the quiet status instead, which should_promote() refuses.
    # On every mixed input the two agree exactly.
    return dataset_status.rollup_statuses(contributing)


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

    REQ-PIPE-105 criterion 7. It orders by PROMOTION, never by the arrival
    key in a table name (sample_data.newest's question, which is a
    different one) - and since REQ-PIPE-128 a period holds one version
    anyway, so within a period there is nothing to order.

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
    # WHAT THE SLOT HOLDS COMES FROM qa.slot_holds (REQ-PIPE-130
    # criterion 9). This used to take the newest entry naming the slot,
    # so a withheld note on a filled period read it as empty
    # (delivery-critic, overnight sprint 2).
    h = decision_log.held(conn, dataset_id, period)
    return h.holder if h and h.held_as == decision_log.PROMOTED else None


# ---------------------------------------------------------------------------
# The step that follows a QA run (criteria 1 and 13)
#
# EVERYTHING ABOVE IS A DECISION MADE IN ISOLATION - one gate, one move,
# one entry. This is the one place that assembles them into the act the
# pipeline performs: take what a run just found, ask the gate about each
# supply it carried, and promote the ones that qualify.
#
# IT IS DELIBERATELY NOT PART OF THE RUN. Criterion 13's reason is
# retryability - a promotion that fails must be repeatable without
# re-running QA - and the structural consequence is that the
# orchestrators' own run function must not call this. A test asserts
# that against the AST rather than trusting the comment
# (tests/test_promotion_after_run.py).
# ---------------------------------------------------------------------------

#: What an automatic promotion records as its reason. A rule does not
#: have to justify itself the way a person does, but an entry that says
#: nothing is one a reader has to reconstruct the gate to understand.
#: What the promotion rule records as its own name in the decision log
#: (REQ-PIPE-074: an automatic decision's actor is the rule, by name).
#: Never the identity that ran the pipeline - post-build-review #81 found
#: both orchestrators passing that, so a person-shaped address was named
#: as the decider of entries that also said a rule decided them.
RULE_ACTOR = "promotion rule"

AUTOMATIC_REASON = ("every check contributing to this dataset passed or warned, "
                    "and its slot for this period was unfilled")


@dataclass(frozen=True)
class AfterRun:
    """What the promotion step did, in three lists that mean three things.

    `refused` and `failed` are NOT the same and collapsing them would
    lose the distinction an operator needs. A refusal is the gate
    working - red, a filled slot, no confident slot - and the supply is
    waiting for a person. A failure is something going wrong, and the
    supply is waiting for a retry.
    """

    promoted: tuple[str, ...] = ()
    refused: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def nothing_happened(self) -> bool:
        return not (self.promoted or self.refused or self.failed)


def after_run(conn: supply_db.SupplyConnection, *,
              agency_id: str,
              collection_id: str,
              supplies: Sequence[dict],
              results: Sequence[dict],
              reads: dict[str, list[str]],
              actor: str,
              actor_kind: str,
              effective_at: str) -> AfterRun:
    """Promote whatever this run's supplies earned, one decision each.

    `supplies` is what the run actually carried, one dict per dataset:
      dataset_id, supply, period (None where nothing could be filed),
      physical_tables, and the two refusals only the caller can see -
      `held` (REQ-PIPE-059 could not choose between two files) and
      `contested` (REQ-PIPE-079 criterion 13).

    `results` is this run's check results and `reads` is check_id -> the
    tables each declares, which together are how status_of() finds every
    check contributing to a dataset - including the cross-table ones
    filed under a sibling (criterion 2).

    NOTHING HERE RAISES for one supply's sake. At ~30 datasets on the
    quarterly asset a step that abandons twenty-nine promotions because
    the thirtieth was odd is a step somebody turns off, which is the
    same blast-radius rule this batch applies everywhere.
    """
    from qa_tools.common import (amber_setting, inheritance, rejection, replacement_setting,
                                 supersession)

    work: list[dict] = []
    refused: dict[str, str] = {}

    for item in supplies:
        dataset_id = item["dataset_id"]
        period = item.get("period")
        # NO AUTOMATIC RULE PROMOTES A SUPERSEDED SUPPLY (REQ-PIPE-118
        # criterion 14): a later version of its table arrived for the same
        # period, and only a person brings it back (REQ-PIPE-120).
        if supersession.is_superseded(conn, dataset_id, item["supply"]):
            newer = supersession.superseded_by(conn, dataset_id, item["supply"])
            refused[dataset_id] = (f"a newer version of this table for {period} arrived "
                                   f"({newer}), so this one is superseded" if newer else
                                   "a person superseded this supply")
            continue
        try:
            status = status_of(dataset_id, results, reads=reads)
        except UnreadableVerdictError as exc:
            # A REFUSAL rather than a failure: retrying will not make the
            # verdict readable, so this is a supply waiting for a person.
            refused[dataset_id] = str(exc)
            continue
        # THE AMBER SETTING, resolved only for an amber supply and as at
        # the instant this decision takes effect (REQ-PIPE-122 criterion 4).
        # A configuration that cannot answer is a refusal, never a default.
        amber = None
        if status == "amber":
            try:
                amber = amber_setting.resolve(dataset_id, effective_at)
            except amber_setting.AmberSettingError as exc:
                refused[dataset_id] = str(exc)
                continue
        # MAY THIS SUPPLY REPLACE A PROMOTED ONE (REQ-PIPE-123)? Only where
        # the slot is filled by a PROMOTED supply - never a substituted or
        # inherited one (criterion 9) - and the replacement setting in force
        # now permits this status. It lifts the filled-slot refusal and
        # nothing else: every other refusal below still comes first
        # (criterion 10).
        replacing = None
        held = decision_log.held(conn, dataset_id, period) if period else None
        if (held and held.held_as == decision_log.PROMOTED
                and held.holder != item["supply"] and status in ("green", "amber")):
            try:
                setting = replacement_setting.resolve(dataset_id, effective_at)
            except amber_setting.AmberSettingError as exc:
                refused[dataset_id] = str(exc)
                continue
            if replacement_setting.permits(setting, status):
                replacing = setting
        ok, why = should_promote(
            # NO PERIOD IS THE SAME REFUSAL AS A HELD SUPPLY, and saying
            # so here rather than inventing a fourth reason keeps the
            # operator-facing text down to the five the gate already
            # owns. A supply nothing could file has no slot to fill.
            held_without_slot=bool(item.get("held")) or period is None,
            contested=bool(item.get("contested")),
            status=status,
            # Nothing contributed means nothing was asked - see the
            # gate's own comment on why that outranks the verdict.
            has_active_checks=status is not None,
            slot_filled=(period in filled_slots(conn, dataset_id)) and replacing is None,
            inherited=(period is not None
                       and inheritance.inherited(conn, dataset_id, period) is not None),
            decided_by_a_person=rejection.decided_by_a_person(
                conn, dataset_id, item["supply"]),
            amber_setting=amber.value if amber else None,
        )
        if not ok:
            refused[dataset_id] = why or "refused"
            if why == AMBER_WAITING_REASON:
                _record_amber_waiting(conn, agency_id=agency_id,
                                      collection_id=collection_id, dataset_id=dataset_id,
                                      supply=item["supply"], period=period, amber=amber,
                                      effective_at=effective_at)
            continue
        reason = AUTOMATIC_REASON
        if replacing is not None:
            # NOT WHILE A LATER PERIOD STANDS ON IT (criterion 8): left
            # waiting for a person, and why recorded.
            try:
                decision_log.refuse_if_stood_on(conn, dataset_id, held.holder,
                                                decision_log.SUPERSEDE)
            except decision_log.DecisionRefused as exc:
                why = (f"the replacement setting '{replacing.value}' would replace "
                       f"{held.holder}, but a later period stands on it - {exc}")
                refused[dataset_id] = why
                _record_withheld(conn, agency_id=agency_id, collection_id=collection_id,
                                 dataset_id=dataset_id, supply=item["supply"],
                                 period=period, reason=why, effective_at=effective_at)
                continue
            # THE SETTING THAT AUTHORISED IT IS THE REASON (criterion 5).
            reason = (f"{AUTOMATIC_REASON} It replaces {held.holder} under the replacement "
                      f"setting '{replacing.value}' (set for the {replacing.level}, version "
                      f"{replacing.version}); {held.holder} is superseded, not rejected.")
        work.append({"dataset_id": dataset_id, "supply": item["supply"],
                     "period": period,
                     "physical_tables": item["physical_tables"],
                     "reason": reason, "amber": amber, "status": status,
                     "replacing": replacing})

    promoted, failed = promote_each(
        conn, work, agency_id=agency_id, collection_id=collection_id,
        # Each item carries its own; this is the fallback for a caller
        # that promotes one period's worth, and promote_each prefers the
        # item's every time.
        period="", actor=actor, actor_kind=actor_kind,
        effective_at=effective_at)
    return AfterRun(promoted=tuple(promoted), refused=refused, failed=failed)


def _record_amber_waiting(conn, *, agency_id: str, collection_id: str, dataset_id: str,
                          supply: str, period: str, amber, effective_at: str) -> None:
    """REQ-PIPE-122 criteria 10 and 19: under hold, the rule records that
    it stood back and the setting it stood back under - a promotion-
    withheld note, which changes nothing a slot holds. Recorded once per
    supply: a retry finds it and records nothing more."""
    already = conn.execute(
        f"SELECT 1 FROM {decision_log.TABLE} WHERE dataset_id = ? AND action = ? "
        "AND supply = ? AND amber_setting = ?",
        [dataset_id, decision_log.PROMOTION_WITHHELD, supply, AMBER_HOLD]).fetchall()
    if already:
        return
    with decision_log.apply_decision(conn, decision_log.Decision(
            agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
            action=decision_log.PROMOTION_WITHHELD, supply=supply, actor=RULE_ACTOR,
            actor_kind=decision_log.RULE, effective_at=effective_at, to_slot=period,
            reason=AMBER_WAITING_REASON, amber_setting=amber.value,
            amber_level=amber.level, amber_version=amber.version)):
        pass


def _record_withheld(conn, *, agency_id: str, collection_id: str, dataset_id: str,
                     supply: str, period: str, reason: str, effective_at: str) -> None:
    """The rule stood back from a replacement and says why (REQ-PIPE-123
    criterion 8) - a promotion-withheld note, which changes no slot. Once
    per supply and reason, so a retry records nothing more."""
    if conn.execute(
            f"SELECT 1 FROM {decision_log.TABLE} WHERE dataset_id = ? AND action = ? "
            "AND supply = ? AND reason = ?",
            [dataset_id, decision_log.PROMOTION_WITHHELD, supply, reason]).fetchall():
        return
    with decision_log.apply_decision(conn, decision_log.Decision(
            agency_id=agency_id, collection_id=collection_id, dataset_id=dataset_id,
            action=decision_log.PROMOTION_WITHHELD, supply=supply, actor=RULE_ACTOR,
            actor_kind=decision_log.RULE, effective_at=effective_at, to_slot=period,
            reason=reason)):
        pass


def after_runs(found_arrivals, results: Sequence[dict], *,
               agency_id: str,
               collection_id: str,
               actor: str,
               actor_kind: str,
               effective_at: str) -> AfterRun:
    """Run the promotion step over a whole batch, one arrival at a time.

    NEVER ASKS FOR A TYPED ENVIRONMENT ID (REQ-PIPE-093 criterion 9): the
    pipeline's own filing and promotion are rule-driven and unattended, and
    a production run that stopped for a person would never finish.

    The batch counterpart to after_run(), and the shape both
    orchestrators call. Returns the three lists MERGED across arrivals,
    because what an operator wants at the end of a run is "what got
    promoted and what did not", not a per-arrival breakdown they have
    to fold themselves.

    IN RECEIPT ORDER, AND STRICTLY SEQUENTIALLY, even though the QA runs
    that produced these results were parallel. Promotion order decides
    which supply fills a slot: two supplies for one dataset and period
    are a race, and the loser must see the slot filled rather than both
    seeing it empty. The runs can be parallel because they only read;
    this writes.

    ONE CONNECTION FOR THE WHOLE BATCH rather than one per arrival. Each
    promotion is still its own transaction - promote() sees to that -
    and re-opening a connection thirty times to prove it would only add
    failure modes.

    `results` is every result in the batch; each arrival's step is given
    the subset carrying its own run_id. A result with no run_id belongs
    to no run and is left out rather than counted everywhere.
    """
    from qa_tools.common import filing

    merged = AfterRun(promoted=(), refused={}, failed={})
    promoted: list[str] = []
    by_run: dict[str, list[dict]] = {}
    for record in results:
        run_id = record.get("run_id")
        if run_id:
            by_run.setdefault(run_id, []).append(record)

    reads = _declared_reads()
    with supply_db.connect(label="mothman:promote-after-run") as conn:
        for arrival in sorted(found_arrivals, key=lambda a: (a.sequence, a.run_id)):
            outcome = after_run(
                conn, agency_id=agency_id, collection_id=collection_id,
                supplies=filing.supplies_of(conn, arrival),
                results=by_run.get(arrival.run_id, []),
                reads=reads, actor=actor, actor_kind=actor_kind,
                effective_at=effective_at)
            promoted.extend(outcome.promoted)
            # LAST WORD WINS on a dataset seen twice, which is the right
            # answer rather than a shortcut: a later arrival's refusal
            # ("the slot is already filled") is the current state, and
            # the earlier arrival's success is already in the log.
            merged.refused.update(outcome.refused)
            merged.failed.update(outcome.failed)
    return AfterRun(promoted=tuple(promoted), refused=merged.refused,
                     failed=merged.failed)


def _declared_reads() -> dict[str, list[str]]:
    """check_id -> the logical tables it declares it reads.

    Wrapped so that a configuration problem in the declarations cannot
    stop the promotion step: an empty mapping means cross-table checks
    are attributed only to the dataset they are filed under, which is
    the pre-criterion-2 behaviour and STRICTLY LESS PERMISSIVE than
    being wrong in the other direction - a missing declaration can only
    ever cost a promotion, never grant one.
    """
    from qa_tools.common import tables_read
    from qa_tools.common.validate_check_lifecycle import collect_checks

    try:
        # `None` is the working tree's own checks, which is what a live
        # run is checking against - the same call
        # pipeline/build_cp_dashboard_data.py makes. Configuration, not
        # state, so this is a legitimate read from anywhere.
        return tables_read.declared_by_check_id(collect_checks(None))
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"note: could not read the cross-table declarations "
              f"({type(exc).__name__}: {exc}) - the promotion gate will see only "
              f"each dataset's own results, which can refuse a promotion but "
              f"never grant one.")
        return {}


def report(outcome: AfterRun) -> None:
    """Say what the promotion step did, in the terminal, every run.

    NOT SILENT ON SUCCESS. A promotion moves a supplier's data into the
    period the dashboard reads; somebody running the pipeline should see
    that happen rather than discover it later. And a REFUSAL is the
    line that matters most - it is the queue of things waiting for a
    person, which is exactly what nobody looks for unless it is put in
    front of them.
    """
    if outcome.promoted:
        print(f"\npromoted {len(outcome.promoted)} supply/supplies: "
              f"{', '.join(sorted(outcome.promoted))}")
    for dataset_id, why in sorted(outcome.refused.items()):
        print(f"not promoted - {dataset_id}: {why}")
    for dataset_id, why in sorted(outcome.failed.items()):
        print(f"PROMOTION FAILED - {dataset_id}: {why} "
              f"(the QA results are recorded; re-run to retry the promotion)")
