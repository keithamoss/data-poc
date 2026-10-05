"""What drift and volume are measured AGAINST (REQ-QAC-108).

THE FAILURE THIS CLOSES is a plausible-looking wrong file. A test
extract, a truncated export: every column is the right type, every
required field is present, every value is in its allowed set. Nothing
column-level catches it. What catches it is noticing that this supply is
wildly unlike the last one - which only works if "the last one" is the
right thing.

THREE WRONG ANSWERS, all of them tempting, and this module exists to
refuse each by name:

  - A FIXED RUN CHOSEN ONCE. This project shipped that, twice: a
    hardcoded `REFERENCE_RUN_ID` that went stale every time the anchor
    date rolled forward, then `manifest[0]["run_id"]`, which is merely
    a stale constant computed fresh. Both measure every supply against
    the beginning of history, so drift stops being detectable about a
    year in (criterion 4).
  - AN ARRIVAL NOBODY PROMOTED. A supply that was rejected, or is still
    staged awaiting a decision, is exactly the file somebody decided not
    to stand on - and measuring the next one against it makes a bad
    supply the yardstick for the one after (criterion 4).
  - THE CURRENT PERIOD'S OWN SUPPLY. A resupply correcting a bad file
    would be measured against the file it is correcting, so the bigger
    the correction the louder the alarm (criterion 3).

AND THE ONE THAT IS SUBTLER THAN ALL THREE (criterion 6). A period whose
table is a VIEW - inherited because the dataset owed nothing, or stood
up by a person's substitution - holds no supply of its own. Measuring
against it compares a supply with ITSELF one hop away: identical
distributions, zero drift, a green check that asked nothing. So the walk
back skips those periods entirely and keeps going until it reaches one a
supply was really promoted into.
"""
from __future__ import annotations

from dataclasses import dataclass

from qa_tools.common import decision_log, schedule, supply_db

#: (A period holds a real supply where qa.slot_holds says it is held as
#: PROMOTED; a substitution or an inheritance puts a view there, which is
#: what criterion 6 skips - REQ-PIPE-130 criterion 9.)


@dataclass(frozen=True)
class Reference:
    """The period a check compares against, and what it holds."""

    dataset_id: str
    period: str
    supply: str

    def describes(self) -> str:
        return f"{self.period}, which holds {self.supply}"


class NoReference(Exception):
    """No earlier period holds a promoted supply for this dataset.

    AN EXCEPTION RATHER THAN None, because criterion 5 forbids the one
    thing a None invites: reporting the check as PASSING. A caller that
    forgets to handle a None writes a green result; a caller that
    forgets to handle this one writes nothing at all, and an absent
    result is visibly absent.
    """


def reference_for(conn: supply_db.SupplyConnection, dataset_id: str,
                  current_period: str) -> Reference:
    """The most recent EARLIER period a supply was promoted into.

    However many periods ago that is (criterion 2). A dataset supplied
    annually into a quarterly asset is three quarters behind its own
    last supply, and walking back a fixed number of periods would find
    nothing; walking back until a real supply turns up finds it.

    Raises NoReference where there is none.
    """
    current_date = schedule.date_of(current_period, dataset_id)
    if current_date is None:
        raise NoReference(
            f"{current_period!r} is not a period on {dataset_id}'s calendar, so "
            f"there is nothing to measure back from")

    rows = conn.execute(
        f"SELECT DISTINCT to_slot FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND to_slot IS NOT NULL",
        [dataset_id]).fetchall()

    candidates = []
    for (slot,) in rows:
        when = schedule.date_of(slot, dataset_id)
        if when is None or when >= current_date:
            # CRITERION 3 lives in that `>=`: the current period's own
            # supply is never the reference, so a resupply is never
            # measured against the file it is correcting.
            continue
        candidates.append((when, slot))

    for _when, slot in sorted(candidates, reverse=True):
        h = decision_log.held(conn, dataset_id, slot)
        if h and h.held_as == decision_log.PROMOTED:
            return Reference(dataset_id=dataset_id, period=slot, supply=h.holder)
        # Anything else - a view, a rejection, a demotion - is not a
        # supply this period holds, so keep walking (criterion 6).

    raise NoReference(
        f"no earlier period holds a promoted supply for {dataset_id}, so there "
        f"is nothing to measure {current_period} against. This is a check with "
        f"no reference, not a check that passed.")


def run_for(conn: supply_db.SupplyConnection, dataset_id: str,
            supply: str) -> str | None:
    """The run that CHECKED this supply, or None.

    THE MAPPING NOBODY THOUGHT WAS RECORDED, and it is - in the physical
    table's own name. A supply is `cp-carers@202608010100000000` and the
    table it staged into is `cp_carers__202608010100000000`: the same
    ARRIVAL KEY, recorded on one side by `qa.filing` and on the other by
    `qa.tables_read`. Nothing had to be added; the question had to be
    asked of the right column.

    Worth saying because it was written up as a fork needing a decision
    a couple of hours before this function existed. The options put
    forward were a heuristic, a new recorded relationship, or waiting
    for REQ-PIPE-079's wiring. None was needed.

    THE EARLIEST RUN THAT READ IT, where several did. A run reads a
    table it did not stage when it BORROWS one (REQ-PIPE-068's
    borrow_views, for the partial-resupply case), and a borrow always
    happens after the staging - so the first run to read a physical
    table is the one that brought it. THE RUN NAMED FOR THE TABLE COMES
    FIRST, though: every Child Protection run reads its siblings' tables
    at the same instant, so "earliest" alone tied (post-build-review
    #110, H1) - the earlier claim here that no table was read by more
    than one run was wrong for Child Protection.
    """
    from qa_tools.common import hierarchy, qa_store

    if "@" not in (supply or ""):
        return None
    # THE SUPPLY'S CURRENT RUN, WHERE ONE IS RECORDED (REQ-PIPE-140
    # criterion 5): a re-run is the supply's verdict from then on, and the
    # run records whose supply it checked - the table-name match below is
    # for a run recorded before runs said so.
    current = qa_store.current_run(conn, dataset_id, supply)
    if current:
        return current
    arrival = supply.rsplit("@", 1)[1]
    try:
        logical = hierarchy.dataset(dataset_id).table
    except hierarchy.UnknownDatasetError:
        return None

    rows = conn.execute(
        f'SELECT t.run_key FROM "{qa_store.SCHEMA}".tables_read t '
        f'JOIN "{qa_store.SCHEMA}".run r ON r.run_key = t.run_key '
        "WHERE t.logical_table = ? AND t.physical_table LIKE ? "
        # THE RUN NAMED FOR THIS TABLE FIRST (dashboard UX critic on
        # 8a942e7, H1): a Child Protection run reads every sibling's table
        # for its cross-table checks, all at one instant, so the earliest
        # reader tied and the alphabetical tie-break named cp_carers' run
        # for every dataset's supply.
        "ORDER BY (t.run_key NOT LIKE ?), r.run_instant, t.run_key LIMIT 1",
        [logical, f"{logical}__{arrival}%", f"{logical}__{arrival}%"]).fetchall()
    return rows[0][0] if rows else None


def reference_run_for(conn: supply_db.SupplyConnection, dataset_id: str,
                      current_period: str) -> str | None:
    """The run whose recorded distribution a drift check compares against.

    reference_for() answers WHICH PERIOD; this answers which run's
    recorded numbers describe it. Returns None where the reference
    period's supply has no run - which is a real state rather than an
    error, and one the caller must report as "no reference" rather than
    as a pass (criterion 5).

    RAISES NOTHING OF ITS OWN. reference_for()'s NoReference is the
    caller's to handle; this narrows it to "there is a period but no
    recorded run for it", which reads the same way to whoever is told.
    """
    return run_for(conn, dataset_id, reference_for(conn, dataset_id, current_period).supply)


def reference_run_for_arrival(dataset_id: str, received_at) -> str | None:
    """The reference run for the supply an arrival brought, or None.

    THE ORCHESTRATORS' ENTRY POINT. They know an arrival and a dataset;
    this answers with the run whose recorded numbers a drift or volume
    check measures against. Everything between - which period that
    supply was filed to, how far back the last real promotion was, which
    run checked it - is this module's and filing's business rather than
    the orchestrator's.

    NONE RATHER THAN AN EXCEPTION, because "there is nothing earlier to
    measure against" is an ordinary state rather than a fault: it is
    true of every dataset's first supply, for ever. What is NOT ordinary
    is reporting it as a pass, which criterion 5 forbids in as many
    words - so the caller turns this None into a check with no
    reference, never into a green one.

    ITS OWN CONNECTION, read-only, for the reason filing.filled_slots()
    and promotion_state.state_for() both give: a narrow reader can only
    answer questions about records, where a connection handed in could
    answer any question at all.
    """
    from qa_tools.common import filing

    period = filing.period_of(dataset_id, received_at)
    if not period:
        return None
    with supply_db.connect(read_only=True,
                            label="mothman:drift-reference") as conn:
        try:
            return reference_run_for(conn, dataset_id, period)
        except NoReference:
            return None


# --------------------------------------------------------------------
# THE GAP RULE (REQ-QAC-108 criteria 2 and 5 as amended, 8 to 17 -
# Keith, 2026-10-04, taken over from REQ-PIPE-035 criteria 7 and 8).
#
# Walking back to the last promoted supply is right, and on its own it
# passes a GAP silently: a dataset that missed last quarter is measured
# against the quarter before, reads green, and nobody is told the
# comparison skipped a period that owed a supply. So the walk now also
# says WHAT IT SKIPPED, and the checks that measured across it go red -
# with the real measurement kept, and said apart from the red, because
# "drifted" and "compared across a hole" are different things to fix.
# --------------------------------------------------------------------

MEASURED = "measured"
GAP = "gap"
NO_REFERENCE_OWED = "no-reference-owed"
NO_REFERENCE_NEW = "no-reference-new"


@dataclass(frozen=True)
class Assessment:
    """What a drift or volume check is measured against, and whether the
    comparison may stand unflagged."""

    kind: str
    dataset_id: str = ""
    reference: Reference | None = None
    run_id: str | None = None
    #: Owed, overdue, earlier periods between the reference and now with
    #: no accepted supply, oldest first - each one a reason for criterion
    #: 8's red (or criterion 9's, where there is no reference at all).
    gap: tuple[str, ...] = ()
    #: Owed periods a person has already dealt with (criterion 17) - said,
    #: never counted against the supply.
    dealt_with: tuple[str, ...] = ()

    @property
    def gap_named(self) -> str:
        """The owed periods, named - at most the five most recent, so a
        daily feed's years of history do not become a paragraph."""
        if len(self.gap) <= 5:
            return ", ".join(self.gap)
        return f"{', '.join(self.gap[-5:])} and {len(self.gap) - 5} earlier"

    @property
    def reason(self) -> str | None:
        """The words a reader is given - criterion 8's example form."""
        if self.kind == GAP and self.reference:
            missing = self.gap_named
            verb = "has" if len(self.gap) == 1 else "have"
            return (f"compared with {self.reference.period}, not {self.gap[-1]}: "
                    f"{missing} {verb} no accepted supply")
        if self.kind == NO_REFERENCE_OWED:
            missing = self.gap_named
            return (f"not evaluated: no earlier period holds an accepted supply to compare "
                    f"with, and {missing} owed one")
        if self.kind == NO_REFERENCE_NEW:
            return "no earlier period owed this dataset a supply, so there is nothing to compare with yet"
        if self.reference and self.dealt_with:
            return (f"compared with {self.reference.period}, not {self.dealt_with[-1]}: "
                    f"a person has already dealt with {', '.join(self.dealt_with)}")
        return None


def _owed_earlier(conn, dataset_id: str, current_period: str, as_at, *,
                  after_date=None) -> tuple[list[str], list[str]]:
    """(gap, dealt_with): this dataset's OWN slots before the current
    period - and after `after_date` - that are overdue at `as_at` and
    hold no promoted supply.

    FROM ITS OWN SCHEDULE (criterion 12): a period the dataset owed
    nothing has no slot, so an inherited period is neither a gap nor a
    reference. NOT YET OVERDUE IS NOT A GAP (criterion 11): a slot whose
    due time and grace have not passed is simply not due.
    """
    from qa_tools.common import slots as slots_mod

    current_date = schedule.date_of(current_period, dataset_id)
    try:
        own = slots_mod.slots_for_dataset(
            dataset_id, until=slots_mod.claimable_until(dataset_id, as_at.date()))
    except (ValueError, KeyError, FileNotFoundError):
        return [], []
    gap, dealt = [], []
    for slot in own:
        when = slot.period.date
        if current_date is None or when >= current_date:
            continue
        if after_date is not None and when <= after_date:
            continue
        if slot.due_at + slot.grace > as_at:
            continue
        h = decision_log.held(conn, dataset_id, slot.name)
        if h and h.held_as == decision_log.PROMOTED:
            continue
        if h and h.held_as == decision_log.SUBSTITUTED:
            dealt.append(slot.name)
            continue
        # ACCEPTED AS NOT SUPPLIED (REQ-PIPE-132) is the third way a person
        # deals with the gap - said, never counted (criterion 17).
        from qa_tools.common import not_supplied

        if not_supplied.marked(conn, dataset_id, slot.name, as_at=as_at.isoformat()):
            dealt.append(slot.name)
            continue
        gap.append(slot.name)
    return gap, dealt


def assess(conn: supply_db.SupplyConnection, dataset_id: str, current_period: str,
           as_at) -> Assessment:
    """The reference for this dataset's period, and every owed period the
    comparison crosses (criteria 2, 5, 8 to 12 and 17)."""
    try:
        ref = reference_for(conn, dataset_id, current_period)
    except NoReference:
        gap, _dealt = _owed_earlier(conn, dataset_id, current_period, as_at)
        return Assessment(kind=NO_REFERENCE_OWED if gap else NO_REFERENCE_NEW,
                          dataset_id=dataset_id, gap=tuple(gap))
    run_id = run_for(conn, dataset_id, ref.supply)
    gap, dealt = _owed_earlier(conn, dataset_id, current_period, as_at,
                               after_date=schedule.date_of(ref.period, dataset_id))
    return Assessment(kind=GAP if gap else MEASURED, dataset_id=dataset_id,
                      reference=ref, run_id=run_id,
                      gap=tuple(gap), dealt_with=tuple(dealt))


def assess_arrival(dataset_id: str, received_at) -> Assessment | None:
    """assess() for the supply an arrival brought - None where it has no
    period (held, a trial), which the caller reports as no reference."""
    from qa_tools.common import asset_time, filing

    period = filing.period_of(dataset_id, received_at)
    if not period:
        return None
    at = (received_at if hasattr(received_at, "tzinfo")
          else asset_time.parse_instant(received_at, f"received_at for {dataset_id}"))
    with supply_db.connect(read_only=True, label="mothman:drift-reference") as conn:
        return assess(conn, dataset_id, period, at)


def judge(results: list[dict], assessment: Assessment | None) -> list[dict]:
    """Apply the gap rule to drift and volume results, in place.

    ONE RESULT PER CHECK AND RUN (criterion 13): the real metric stays,
    the measured verdict is kept as `measured_status` beside the red, the
    reference period and the reason are carried - so the dashboard,
    terminal and ticket can say "the measurement was fine; the comparison
    skipped a period" rather than calling it drift (criterion 14). The
    red does NOT count against automatic promotion - the gate reads
    `measured_status` (criterion 15 as amended 2026-10-05; promotion.
    _gating_status).
    """
    if assessment is None:
        return results
    for r in results:
        # The assessment is about ONE dataset's reference; a result about
        # another table's volume is another run's to judge.
        if assessment.dataset_id and r.get("dataset_id") != assessment.dataset_id:
            continue
        if assessment.reference:
            r["reference_period"] = assessment.reference.period
        reason = assessment.reason
        if reason:
            r["reference_reason"] = reason
        if assessment.kind == GAP:
            r["measured_status"] = r.get("status")
            r["status"] = "fail"
            r["reference_gap"] = list(assessment.gap)
        elif assessment.kind == NO_REFERENCE_OWED:
            # CRITERION 9: red, NOT EVALUATED, under its own tool, with no
            # metric - never "no data", never the unrunnable pseudo-tool.
            r["status"] = "fail"
            r["metric_value"] = None
            r["measured_status"] = None
            r["reference_gap"] = list(assessment.gap)
            r["reference_not_evaluated"] = True
    return results


def reference_note(record: dict, to_status=lambda s: s) -> dict | None:
    """What a dashboard shows beside a drift or volume verdict: which
    period it was compared with, why, and - where the red is the gap
    rule's rather than the measurement's - the verdict the measurement
    alone gave (criterion 14). None for a record the rule did not touch.
    `to_status` maps a recorded status to the reader's vocabulary."""
    reason = record.get("reference_reason")
    if not reason:
        return None
    measured = record.get("measured_status")
    return {"reason": reason, "period": record.get("reference_period"),
            "measuredStatus": to_status(measured) if measured else None,
            "gap": record.get("reference_gap") or []}
