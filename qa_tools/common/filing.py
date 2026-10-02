"""Where each supply was filed, recorded once (REQ-PIPE-062).

AN ASSIGNMENT IS WRITTEN ONCE AND NEVER RE-DERIVED (criterion 10).
Re-deriving on every run would silently undo a human's re-file and make
history move under a reader - the same instability the stickiness rule
exists to prevent on the promotion side. So a supply already filed is
left exactly as it was, and this is a write-once record rather than a
computed view.

WHY THE BRANCH IS STORED RATHER THAN RECOMPUTED, which is the part that
looks redundant and is not: "why is this supply here" has to be
answerable a year later without re-running anything, and recomputing it
then gives a DIFFERENT answer, because the slot state it was decided
against has moved on. The rule branch is a fact about the moment of
filing, not a property of the supply.

FILED IS NOT FILLED, and keeping them apart is load-bearing. A supply
is FILED against a slot by this rule, with no human in it. A slot is
FILLED only when a supply has been PROMOTED into it - a decision, and
one this PoC does not make yet. Treating a filing as a fill would
reintroduce the forward cascade through the back door: the rejected
14:00 supply in that worked example is filed against Monday, and if
that counted as filling Monday, the 16:00 resupply would be pushed to
Tuesday and every later supply after it.

So filled_slots() returns nothing today, deliberately, and says why
rather than being absent - the promotion side arrives with the decision
log in batch 4.

IT IS A TABLE NOW, NOT A COMMITTED TREE (REQ-PIPE-104). Until 2026-09-28
this wrote `filings/<dataset>/<supply>.json`, gitignored, with recording
switched off - so there was nothing to migrate and only a destination to
build, which is why it is its own requirement rather than part of
REQ-PIPE-089. Building it now matters because it has to be right on the
day REQ-PIPE-062 turns recording on: otherwise flipping that switch
starts committing state to the repository again, which is the thing Keith
settled against.

WHAT WENT WITH THE FILES: the `filings_dir` parameter every function took
for test isolation. A test worker has its own DATABASE now, which is
stronger - a test cannot reach the real filings at all, rather than being
pointed away from them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from qa_tools.common import qa_store, supply_db
from qa_tools.common.assignment import Assignment

TABLE = f'"{qa_store.SCHEMA}".filing'


def _connect(label: str) -> supply_db.SupplyConnection:
    conn = supply_db.connect(label=label)
    qa_store.ensure_schema(conn)
    return conn


def record(assignment: Assignment) -> bool:
    """Record where one supply was filed, once.

    Returns True where a row was written, False where this supply was
    already filed - which is the ordinary case on every run after the
    first, not a guard against a bug.

    ON CONFLICT DO NOTHING rather than a read-then-write, and the
    difference is not tidiness: two arrivals for one dataset can be
    processed by two workers in the same fan-out, and check-then-insert
    is a race with a nice-looking shape. It is also criterion 2 in one
    clause - a supply already filed is left exactly as it was, decided by
    the database rather than by every caller remembering.
    """
    with _connect("mothman:filing-record") as conn:
        record = assignment.as_record()
        verdict = _classification_for(
            assignment.dataset_id, assignment.slot, assignment.received_at)
        if verdict is not None:
            record["classification"] = verdict
        rows = conn.execute(
            f"INSERT INTO {TABLE} (dataset_id, supply_id, slot, branch, record, "
            "received_at, classification) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (dataset_id, supply_id) DO NOTHING "
            "RETURNING dataset_id",
            [assignment.dataset_id, assignment.supply_id, assignment.slot,
             assignment.branch, json.dumps(record),
             assignment.received_at, verdict]).fetchall()
    return bool(rows)


def _classification_for(dataset_id: str, slot_name: str | None,
                         received_at: datetime | None) -> str | None:
    """This supply's verdict against the slot it is filed to, or None
    where there is no receipt instant to judge (REQ-PIPE-080
    criterion 1).

    OUR RECEIPT INSTANT, NEVER THE PROMOTION INSTANT (criterion 8), and
    never an instant out of the supplier's file (criterion 4). A
    verdict taken from when somebody got round to promoting would make
    punctuality a property of OUR responsiveness; one taken from the
    supplier's own extract timestamp lets them decide whether they were
    late.

    NONE IS NOT UNFILED. None means "nothing to judge with" and leaves
    the column empty; UNFILED means "judged, and there is no slot to be
    punctual against" (criterion 6). Collapsing them would make a
    missing receipt look like a held supply.

    IT NEVER RAISES. A dataset whose slots cannot be built - an unknown
    id, no agreed calendar (REQ-PIPE-106) - still has a filing worth
    recording, and a classifier that took the write down with it would
    be the blast-radius rule broken for a presentational field.
    """
    from qa_tools.common import arrival_classification

    if received_at is None:
        return None
    if not slot_name:
        return arrival_classification.UNFILED
    try:
        return arrival_classification.classify(
            received_at, _slot_named(dataset_id, slot_name, received_at))
    except Exception:  # noqa: BLE001 - see the docstring
        return None


def _slot_named(dataset_id: str, slot_name: str, received_at: datetime):
    """The Slot a filing names, or None where the schedule has no such
    period.

    NOT BOUNDED BY THE ARRIVAL DATE, and that is the whole of this
    function. `slots_for_dataset(until=received_at.date())` is what the
    assignment rule passes, and it stops at the period CONTAINING that
    date - so a slot whose claim window has already opened, but whose
    period has not yet begun, is not in the list. Resolve a filing that
    way and a supply re-filed FORWARD loses its verdict entirely:
    the named slot is simply absent, which reads as `unfiled`.

    An authored calendar needs no bound at all. A cadence-rule calendar
    requires one - "every day" has no end of its own - and there the
    period name IS a date, so the slot names its own bound. Falling
    back to the arrival date is for the case where it does not parse,
    which costs the same answer the cap used to give rather than an
    error.
    """
    from datetime import date as date_cls

    from qa_tools.common import slots as slots_mod

    def _find(slots):
        return next((s for s in slots if s.period.name == slot_name), None)

    try:
        return _find(slots_mod.slots_for_dataset(dataset_id))
    except Exception:  # noqa: BLE001 - a cadence rule needs an end; give it one
        try:
            named = date_cls.fromisoformat(slot_name)
        except ValueError:
            named = received_at.date()
        return _find(slots_mod.slots_for_dataset(
            dataset_id, until=max(received_at.date(), named)))


def filing_for(dataset_id: str, supply_id: str) -> dict | None:
    """This supply's filing, or None where it has not been filed."""
    with _connect("mothman:filing-read") as conn:
        rows = conn.execute(
            f"SELECT record FROM {TABLE} WHERE dataset_id = ? AND supply_id = ?",
            [dataset_id, supply_id]).fetchall()
    return rows[0][0] if rows else None


def filings_of(dataset_id: str) -> list[dict]:
    """Every filing for one dataset.

    Indexed on (dataset_id, recorded_at), so answering it costs nothing
    in the size of any other dataset's history - the same per-dataset
    shape REQ-PIPE-034 established for arrivals, and what the retired
    directory layout gave for free.
    """
    with _connect("mothman:filing-read") as conn:
        return [row[0] for row in conn.execute(
            f"SELECT record FROM {TABLE} WHERE dataset_id = ? "
            "ORDER BY recorded_at, supply_id", [dataset_id]).fetchall()]


def period_of(dataset_id: str, received_at) -> str | None:
    """The period this dataset's supply from that arrival was filed to.

    WHY IT LIVES HERE, for the same reason supplies_of() does: the
    supply id is this module's answer, and a caller deriving one from
    an arrival instant would be a second naming scheme to keep in step -
    including the `#1` suffix a held supply carries, which is exactly
    the part a second derivation gets wrong.

    Matched on the ARRIVAL KEY rather than on the whole id, so the held
    variant resolves to the same filing as the plain one. None where
    nothing was filed for this dataset from that arrival, which is a
    real state: a supply with no confident slot is filed nowhere.
    """
    from qa_tools.common import asset_time

    key = asset_time.arrival_key(received_at)
    for record in filings_of(dataset_id):
        supply = record.get("supply_id") or ""
        if "@" not in supply:
            continue
        if supply.rsplit("@", 1)[1].split("#", 1)[0] == key:
            return record.get("slot")
    return None


def filled_slots(dataset_id: str) -> frozenset[str]:
    """Slots a supply has been PROMOTED into (REQ-PIPE-075 criterion 6).

    NOT the slots supplies have been FILED against, and the difference
    is the whole reason this function exists rather than callers
    reading filings_of() and taking the slot names. Only a promotion
    fills a slot; an arrival does not, a staged supply does not, and a
    rejected one certainly does not.

    Returning filings here would be the single easiest way to
    reintroduce the forward cascade, because the rejected supply in
    that worked example IS filed against Monday.

    THIS RETURNED AN EMPTY SET UNTIL 2026-09-28, with a docstring
    saying "so, nothing yet" - a deliberate stub, because promotion did
    not exist to fill anything. It does now, and the answer comes from
    the DECISION LOG rather than from the warehouse catalogue: a table
    somebody put in a period schema is not a promotion.
    """
    from qa_tools.common import promotion

    with _connect("mothman:filing-filled-slots") as conn:
        return promotion.filled_slots(conn, dataset_id)


def file_arrivals(found_arrivals) -> list[Assignment]:
    """Assign and record every dataset's supply in these arrivals.

    BEFORE ANY CHECK RUNS (criterion 1), which is why this is called
    from the orchestrators rather than from whatever consumes the
    result: as first proposed the period was assigned at PROMOTION, but
    checks run before promotion, so at check time there would have been
    no slot to classify against. Assignment is a derivation with no
    human in it; promotion is a decision. There is still exactly one
    place the slot is decided - it just happens earlier.

    A supply whose checks will report red is filed on the same terms as
    any other, so a supply never promoted still carries where it was
    filed: "arrived three weeks late AND was bad" is what belongs on
    the record.

    Returns only the assignments this call actually wrote. A supply
    already filed is left alone.
    """
    from qa_tools.common import assignment as assign_mod
    from qa_tools.common import slots as slots_mod

    slots_by_dataset: dict[str, list] = {}
    written: list[Assignment] = []

    for arrival in found_arrivals:
        for dataset_id in sorted(arrival.files_by_dataset):
            # A HELD supply is not filed: REQ-PIPE-059 refuses to choose
            # between two files for one dataset, and filing one of them
            # would be making that choice by another route.
            #
            # IT IS RECORDED, THOUGH (REQ-PIPE-078 criteria 1 and 3),
            # and that is what this used to get wrong: a bare `continue`
            # meant the one state in this pass that genuinely needs a
            # person left no trace at all, while the assignment-rule
            # hold below got a row. Two holds, two lifetimes, and the
            # criterion asks for the same terms.
            if dataset_id in arrival.held:
                _raise_delivery_hold(arrival, dataset_id)
                continue
            if dataset_id not in slots_by_dataset:
                try:
                    # THE CLAIM WINDOW'S REACH, NOT THE ARRIVAL DATE
                    # (post-build-review #73). Capping here at the
                    # arrival date withheld the very slot a supply
                    # arriving early is early FOR - see
                    # slots.claimable_until() for the worked example.
                    slots_by_dataset[dataset_id] = slots_mod.slots_for_dataset(
                        dataset_id, until=slots_mod.claimable_until(
                            dataset_id, arrival.received_at.date()))
                except (ValueError, KeyError, FileNotFoundError) as exc:
                    # A dataset whose schedule cannot be built yet gets
                    # no slots rather than taking the run down - the
                    # blast-radius rule this batch applies everywhere:
                    # one exhausted or misconfigured schedule must not
                    # fail the other 29 datasets.
                    print(f"note: {dataset_id} has no slots to file against ({exc}) - "
                          f"its supplies are still recorded as arrived.")
                    slots_by_dataset[dataset_id] = []
            supply_id = _supply_id_for(arrival, dataset_id)
            if filing_for(dataset_id, supply_id) is not None:
                continue
            decided = assign_mod.assign(
                dataset_id=dataset_id, supply_id=supply_id,
                at=arrival.received_at, slots=slots_by_dataset[dataset_id],
                filled=filled_slots(dataset_id))
            record(decided)
            # AN ASSIGNMENT-RULE HOLD IS RECORDED TOO (criterion 3). Its
            # `filing` row above is evidence of what the rule saw and
            # stays write-once; the open work item is the hold, because
            # that is the record a decision has to be able to close.
            if decided.is_held:
                _raise_assignment_hold(arrival, decided)
            written.append(decided)
    return written


def _raise_delivery_hold(arrival, dataset_id: str) -> None:
    """Record a supply nothing may choose between (REQ-PIPE-059).

    THE SUPPLY ID IS DERIVED THE SAME WAY A FILED ONE IS, deliberately:
    a held supply has to be nameable before anybody can resolve it, and
    inventing a second naming scheme for the one case where a person is
    involved is how the two stop joining up.
    """
    from qa_tools.common import supply_holds

    with _connect("mothman:hold-raise") as conn:
        supply_holds.raise_hold(
            conn, dataset_id=dataset_id, supply_id=_supply_id_for(arrival, dataset_id),
            kind=supply_holds.DELIVERY_LEVEL,
            reason={"files": sorted(arrival.files_by_dataset.get(dataset_id) or ())},
            raised_by=arrival.run_id, delivery=arrival.delivery_name)


def _raise_assignment_hold(arrival, decided: Assignment) -> None:
    """Record a supply the rule found no slot for (REQ-PIPE-064)."""
    from qa_tools.common import supply_holds

    with _connect("mothman:hold-raise") as conn:
        supply_holds.raise_hold(
            conn, dataset_id=decided.dataset_id, supply_id=decided.supply_id,
            kind=supply_holds.ASSIGNMENT_RULE,
            reason={"unavailable": [list(pair) for pair in decided.unavailable],
                     "considered": list(decided.considered)},
            raised_by=arrival.run_id, delivery=arrival.delivery_name)


def _supply_id_for(arrival, dataset_id: str) -> str:
    """This dataset's own name for the supply in this arrival.

    The same identifier REQ-PIPE-034 builds, so a filing and an arrival
    can be joined without a second naming scheme to keep in step.
    """
    from qa_tools.common import asset_time

    names = arrival.files_by_dataset.get(dataset_id) or ()
    base = f"{dataset_id}@{asset_time.arrival_key(arrival.received_at)}"
    return base if len(names) <= 1 else f"{base}#1"


#: A recomputation carries a reference to the re-filing that caused it
#: (REQ-PIPE-067 criterion 5). THE REFERENCE DANGLES until the decision
#: log exists in sprint 12 to resolve it, and that is stated rather
#: than left for a reader to discover - the alternative failure is
#: specific and was named at sign-off: five of six criteria built, the
#: sixth quietly skipped as un-buildable, and the requirement reported
#: done.
REFILING_REFERENCE = "refiled_by"


def refile(dataset_id: str, supply_id: str, to_slot: str, refiling_id: str,
            reason: str = "") -> dict | None:
    """Move one supply to a different slot, and let its verdict follow.

    THE VERDICT FOLLOWS THE FILING (REQ-PIPE-067). A supply reported
    late purely because it was misfiled was never actually late, and
    leaving a known-wrong verdict in place for the sake of immutability
    is the one place this design would knowingly say something untrue.

    THE ARRIVAL INSTANT DOES NOT MOVE (criterion 3). When we received
    something is a fact; which period it was for is a decision, and
    only the second one is being changed here.

    ATOMIC, never a demote followed by a promote (criterion 5's
    reasoning). One entry with a from-slot, a to-slot and one reason -
    because under the composed version a re-file appears in the
    decision log as two entries, and a reader a year later has to infer
    they were one act. "Why is this supply in Q3?" should have a single
    answer rather than being a correlation exercise.

    `refiling_id` identifies the re-filing in the decision log. Nothing
    resolves it yet - the log is sprint 12 - so it is recorded and
    dangles, which is deliberate and is why this parameter is required
    rather than optional.

    Returns the updated record, or None where the supply was not filed
    or is already in that slot (criterion 6 - an unchanged filing is
    not recomputed).
    """
    current = filing_for(dataset_id, supply_id)
    if current is None or current.get("slot") == to_slot:
        return None

    updated = dict(current)
    updated["slot"] = to_slot
    updated["refiled_from"] = current.get("slot")
    updated[REFILING_REFERENCE] = refiling_id
    if reason:
        updated["refiling_reason"] = reason
    # The branch that ORIGINALLY filed it is kept as history and no
    # longer describes where it sits: a person put it here.
    updated["branch"] = "refiled-by-a-person"

    # THE VERDICT FOLLOWS, THE INSTANT DOES NOT (REQ-PIPE-080 criteria
    # 5 and 8). Recomputed from the receipt instant already recorded
    # against this supply - so a supply reported late purely because it
    # was misfiled stops reading late the moment somebody moves it,
    # without anything re-deriving when it turned up.
    received_at = received_at_of(dataset_id, supply_id)
    verdict = _classification_for(dataset_id, to_slot, received_at)
    if verdict is not None:
        updated["classification"] = verdict
    else:
        updated.pop("classification", None)

    # AN UPDATE, AND THE ONLY ONE THIS TABLE TAKES. Write-once
    # (REQ-PIPE-104 criterion 2) is about the RULE never re-deriving a
    # filing against a schedule that has moved on; a person moving a
    # supply is the other thing entirely, and REQ-PIPE-067 requires the
    # verdict to follow it. That is why `qa.filing` has no append-only
    # trigger while `qa.decision` does - see the DDL.
    with _connect("mothman:filing-refile") as conn:
        conn.execute(
            f"UPDATE {TABLE} SET slot = ?, branch = ?, record = ?, classification = ? "
            "WHERE dataset_id = ? AND supply_id = ?",
            [to_slot, updated["branch"], json.dumps(updated), verdict,
             dataset_id, supply_id])
    return updated


@dataclass(frozen=True)
class RecordedArrival:
    """When a supply reached us, what that earned it, and how long it
    then waited (REQ-PIPE-080 criteria 9, 10 and 11).

    TWO INSTANTS, NEVER ONE IN PLACE OF THE OTHER (criterion 11).
    `received_at` is when WE received the supply; `filled_at` is when a
    decision promoted it into its slot. They answer different
    questions - "did the supplier deliver on time" and "how quickly did
    we act on it" - and a page showing one labelled as the other is the
    specific confusion this requirement exists to end.
    """

    dataset_id: str
    supply_id: str
    slot: str | None
    received_at: datetime | None
    filled_at: datetime | None
    classification: str | None

    @property
    def awaiting(self) -> bool:
        """Whether the wait is still running (criterion 10)."""
        return self.received_at is not None and self.filled_at is None

    @property
    def waited(self) -> timedelta | None:
        """Receipt to promotion, or receipt to NOW where nothing has
        promoted it yet (criterion 10).

        OPEN RATHER THAN ABSENT OR ZERO, which is the criterion's whole
        point: both of those read as "dealt with instantly", and a
        supply nobody has decided on for three weeks is the opposite of
        that. `awaiting` says which of the two this is, so a caller
        never has to infer it from the number.
        """
        from qa_tools.common import asset_time

        if self.received_at is None:
            return None
        return (self.filled_at or asset_time.now()) - self.received_at


def received_at_of(dataset_id: str, supply_id: str) -> datetime | None:
    """Our receipt instant for this supply, as recorded."""
    with _connect("mothman:filing-read") as conn:
        rows = conn.execute(
            f"SELECT received_at FROM {TABLE} WHERE dataset_id = ? AND supply_id = ?",
            [dataset_id, supply_id]).fetchall()
    return rows[0][0] if rows else None


def recorded_arrival(dataset_id: str, supply_id: str) -> RecordedArrival | None:
    """This supply's recorded arrival facts, or None where it has no
    filing at all.

    READ RATHER THAN RECOMPUTED (criterion 1). Every consumer asks this
    instead of deriving punctuality for itself, which is the whole
    reason the classification is a column - three derivations of one
    fact is what REQ-PIPE-080 exists to end.

    `filled_at` COMES FROM THE DECISION LOG, not from this table, and
    deliberately: a slot is filled by a PROMOTION, and the filing knows
    only where a supply was filed. Reading it here would make a filing
    look like a fill, which REQ-PIPE-062's own docstring spends a
    paragraph warning against.
    """
    with _connect("mothman:filing-read") as conn:
        rows = conn.execute(
            f"SELECT slot, received_at, classification FROM {TABLE} "
            "WHERE dataset_id = ? AND supply_id = ?",
            [dataset_id, supply_id]).fetchall()
        if not rows:
            return None
        slot, received_at, classification = rows[0]
        filled_at = _filled_at(conn, dataset_id, supply_id, slot)
    return RecordedArrival(dataset_id=dataset_id, supply_id=supply_id, slot=slot,
                            received_at=received_at, filled_at=filled_at,
                            classification=classification)


def recorded_arrival_at(dataset_id: str, received_at) -> "RecordedArrival | None":
    """This dataset's recorded arrival facts for the supply that came
    in at `received_at` (REQ-PIPE-080 criterion 1).

    THE DASHBOARD BUILD'S ENTRY POINT. A builder knows a dataset and a
    run's receipt instant - the manifest has carried one since
    REQ-GEN-042 - and this answers with the verdict, the two instants
    and the wait, so the builder never computes punctuality itself.
    That is criterion 1's "every consumer reads it" in one call.

    MATCHED ON THE ARRIVAL KEY, exactly as period_of() does, including
    the `#1` suffix a held supply carries. Deriving a supply id here
    instead would be a second naming scheme to keep in step, which is
    the thing _supply_id_for()'s docstring exists to prevent.

    RECORDED METADATA, NEVER SUPPLY ROWS. This reads `qa.filing` and
    `qa.decision` and nothing else - the same access
    `promotion_state.state_for()` already has from this build path, and
    well inside Keith's rule that a build may read recorded results and
    never the extract itself.
    """
    from qa_tools.common import asset_time

    key = asset_time.arrival_key(received_at)
    for record in filings_of(dataset_id):
        supply = record.get("supply_id") or ""
        if "@" not in supply:
            continue
        if supply.rsplit("@", 1)[1].split("#", 1)[0] == key:
            return recorded_arrival(dataset_id, supply)
    return None


def _filled_at(conn, dataset_id: str, supply_id: str, slot: str | None):
    """When a decision promoted THIS supply into its slot, or None.

    THIS SUPPLY, not whatever currently fills the slot. A slot filled
    by a later substitution says nothing about how long this supply
    waited, and reporting it would turn somebody else's promotion into
    this supply's response time.
    """
    if not slot:
        return None
    from qa_tools.common import decision_log

    # `effective_at` RATHER THAN `recorded_at` - when the decision took
    # effect, not when the row reached the table. A bootstrap replays
    # years of arrivals under one wall clock, so recorded_at would make
    # every historical supply look as though it waited until today.
    rows = conn.execute(
        f"SELECT MIN(effective_at) FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND supply = ? AND to_slot = ? AND action IN (?, ?)",
        [dataset_id, supply_id, slot,
         decision_log.PROMOTE, decision_log.REFILE]).fetchall()
    return rows[0][0] if rows else None


def classification_of(dataset_id: str, supply_id: str, arrived_at,
                       slot_by_name) -> str:
    """This supply's arrival verdict, for the slot it is filed to NOW.

    ALWAYS READ, NEVER CACHED FROM AN EARLIER FILING (criteria 2 and
    4). The verdict is not a frozen historical fact - it is a function
    of the current filing, so presenting one computed against a filing
    that has since changed is presenting something known to be untrue.

    LOCAL TO THE SUPPLY THAT MOVED (the non-functional constraint). A
    re-file changes one supply's verdict; nothing here replays a
    history, because a design that needed to would stop being usable
    once a daily feed has years behind it.
    """
    from qa_tools.common import arrival_classification

    record = filing_for(dataset_id, supply_id)
    slot = slot_by_name(record["slot"]) if record and record.get("slot") else None
    return arrival_classification.classify(arrived_at, slot)


def supplies_of(conn, arrival) -> list[dict]:
    """What this arrival brought, in the shape the promotion step reads.

    One dict per dataset the arrival carried:
      dataset_id, supply, period (None where nothing could be filed),
      physical_tables, held, contested.

    WHY IT LIVES HERE rather than in promotion.py: the supply id and the
    slot are both this module's answers, and a second place deriving
    either of them would be a second naming scheme to keep in step -
    the thing _supply_id_for()'s own docstring exists to prevent.

    PHYSICAL TABLES ARE SCOPED TO THIS ARRIVAL (supply_db.candidates_in's
    own `arrival` argument, and see its docstring for the bug that put it
    there). Staging accumulates, so the unscoped question has as many
    answers as there have been runs.

    A DATASET WITH NO STAGED TABLE IS STILL RETURNED, with an empty
    list, so the step refuses it visibly rather than skipping it in
    silence. A supply that arrived and staged nothing is a thing
    somebody should hear about.
    """
    from qa_tools.common import asset_time, hierarchy, supply_db

    key = asset_time.arrival_key(arrival.received_at)
    out: list[dict] = []
    for dataset_id in sorted(arrival.files_by_dataset):
        supply_id = _supply_id_for(arrival, dataset_id)
        try:
            logical = hierarchy.dataset(dataset_id).table
        except hierarchy.UnknownDatasetError:
            # The same fallback promotion.status_of() makes, and for the
            # same reason: a dataset the tree does not know still has an
            # id, and raising inside the step would cost the other
            # twenty-nine their promotions.
            logical = dataset_id
        staged = supply_db.candidates_in(
            conn, supply_db.STAGING_SCHEMA, [logical], arrival=key).get(logical) or []
        record = filing_for(dataset_id, supply_id)
        out.append({
            "dataset_id": dataset_id,
            "supply": supply_id,
            "period": (record or {}).get("slot"),
            "physical_tables": sorted(staged),
            "held": dataset_id in arrival.held,
            # SEVERAL STAGED TABLES FOR ONE NAME is REQ-PIPE-059's case
            # seen from the warehouse rather than from the file listing.
            # Both are reported because they can disagree - a file that
            # matched but failed to load leaves one without the other -
            # and either is a reason not to choose.
            "contested": len(staged) > 1,
        })
    return out
