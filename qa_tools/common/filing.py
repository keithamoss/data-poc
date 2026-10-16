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

from dataclasses import dataclass
from datetime import datetime, timedelta

from qa_tools.common import replay_clock as _replay_clock
from qa_tools.common import qa_store, supply_db
from qa_tools.common import verdict as verdict_mod
from qa_tools.common.assignment import Assignment

TABLE = f'"{qa_store.SCHEMA}".filing'
#: A supply's CURRENT filing - its newest row (REQ-PIPE-141 criterion 2,
#: NFR 6). Every reader reads this; only record() and refile() write TABLE.
CURRENT = f'"{qa_store.SCHEMA}".filing_current'
#: A supply's receipt, defined once (REQ-PIPE-144 criterion 12).
RECEIPT = f'"{qa_store.SCHEMA}".supply_receipt'

#: The columns a filing is read back from, in the dict every reader
#: uses (criterion 4). There is no document any more - see the DDL.
_COLUMNS = ("dataset_id", "supply_id", "slot", "branch", "classification",
            "considered", "delivery")
_SELECT = ", ".join(_COLUMNS)


class FilingWithoutDelivery(ValueError):
    """A filing would link to no delivery (REQ-PIPE-144 criterion 18)."""


def _as_dict(row) -> dict:
    out = dict(zip(_COLUMNS, row))
    out["considered"] = list(out["considered"] or [])
    return out


def _connect(label: str) -> supply_db.SupplyConnection:
    conn = supply_db.connect(label=label)
    qa_store.ensure_schema(conn)
    return conn


def record(assignment: Assignment, delivery: str | None, conn=None) -> bool:
    """Record where one supply was filed, once, linked to the delivery it
    came in (REQ-PIPE-144 criteria 10 and 11).

    `delivery` is the ARRIVAL's delivery name, passed in by whoever holds
    the arrival - never parsed out of the supply id, which is the implicit
    link this replaced. A filing with no delivery, or naming one with no
    qa.delivery row, is REFUSED with the delivery named (criterion 18)
    rather than written linking to nothing; the foreign key is the
    database's safety net behind that.

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
    if not delivery:
        raise FilingWithoutDelivery(
            f"{assignment.supply_id} ({assignment.dataset_id}) has no delivery to link "
            f"to, so it was not filed.")
    if conn is None:
        with _connect("mothman:filing-record") as opened:
            return record(assignment, delivery, conn=opened)
    if not conn.execute(
            f'SELECT 1 FROM "{qa_store.SCHEMA}".delivery WHERE name = ?',
            [delivery]).fetchall():
        raise FilingWithoutDelivery(
            f"{assignment.supply_id} ({assignment.dataset_id}) names delivery "
            f"{delivery!r}, which has no delivery record, so it was not filed.")
    judged = _judged_for(
        assignment.dataset_id, assignment.slot, assignment.received_at)
    at = _replay_clock.now()
    rows = conn.execute(
        f"INSERT INTO {TABLE} (dataset_id, supply_id, slot, branch, considered, "
        "delivery, classification, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (dataset_id, supply_id) WHERE refiled_by IS NULL DO NOTHING "
        "RETURNING id",
        [assignment.dataset_id, assignment.supply_id, assignment.slot,
         assignment.branch, list(assignment.considered), delivery,
         judged.classification, at]).fetchall()
    if rows:
        # THE VERDICT, WITH WHAT JUDGED IT (REQ-PIPE-168 criterion 1), in
        # the same transaction as the filing it belongs to.
        verdict_mod.record(conn, rows[0][0], assignment.dataset_id, assignment.supply_id,
                           judged, recorded_at=at)
    return bool(rows)


def _judged_for(dataset_id: str, slot_name: str | None,
                received_at: datetime | None) -> "verdict_mod.Judged":
    """This supply's verdict against the slot it is filed to, with the
    inputs that judged it (REQ-PIPE-168), or no classification where
    there is no receipt instant to judge (REQ-PIPE-080 criterion 1).

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
    if received_at is None:
        return verdict_mod.Judged(None, None, None)
    if not slot_name:
        return verdict_mod.judge(dataset_id, None, received_at)
    try:
        slot = _slot_named(dataset_id, slot_name, received_at)
    except Exception:  # noqa: BLE001 - see the docstring
        return verdict_mod.Judged(None, None, None)
    return verdict_mod.judge(dataset_id, slot, received_at)


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
            f"SELECT {_SELECT} FROM {CURRENT} WHERE dataset_id = ? AND supply_id = ?",
            [dataset_id, supply_id]).fetchall()
    return _as_dict(rows[0]) if rows else None


def filings_of(dataset_id: str) -> list[dict]:
    """Every filing for one dataset.

    Indexed on (dataset_id, recorded_at), so answering it costs nothing
    in the size of any other dataset's history - the same per-dataset
    shape REQ-PIPE-034 established for arrivals, and what the retired
    directory layout gave for free.
    """
    with _connect("mothman:filing-read") as conn:
        return [_as_dict(row) for row in conn.execute(
            f"SELECT {_SELECT} FROM {CURRENT} WHERE dataset_id = ? "
            "ORDER BY recorded_at, supply_id", [dataset_id]).fetchall()]


def filing_history(conn, dataset_id: str) -> list[dict]:
    """Every filing row of one dataset, each with the instant it TOOK
    EFFECT, oldest row first (REQ-DASH-197 criteria 2, 3 and 22).

    A SUPPLY'S FIRST FILING TAKES EFFECT AT ITS RECEIPT - it is written for
    every arrival before any check (REQ-PIPE-075 criterion 7), and the
    receipt is the asset-clock fact; `recorded_at` is only when this
    process got round to writing it. A RE-FILE takes effect when the
    decision that made it did. A row naming no real decision (a test's
    move) falls back to when it was written.

    Read once per build and walked in memory, so answering "as at" each
    date costs nothing more per date (REQ-DASH-197's build-cost NFR).
    """
    rows = conn.execute(
        f"SELECT f.supply_id, f.slot, f.refiled_by, f.recorded_at, r.received_instant, "
        f"       d.effective_at, f.id "
        f"FROM {TABLE} f "
        f"JOIN {RECEIPT} r ON r.dataset_id = f.dataset_id AND r.supply_id = f.supply_id "
        f'LEFT JOIN "{qa_store.SCHEMA}".decision d ON d.id = f.refiled_by '
        "WHERE f.dataset_id = ? ORDER BY f.id", [dataset_id]).fetchall()
    out = []
    seen: set[str] = set()
    for supply, slot, refiled_by, recorded_at, received, decided, row_id in rows:
        at = received if refiled_by is None else (decided or recorded_at)
        # A SUPPLY'S EARLIEST ROW IS ITS FIRST FILING, whoever wrote it: a
        # settled pair's `#2` has no rule's filing - it became a supply when
        # the settlement took effect (REQ-PIPE-193 criterion 12).
        out.append({"supply_id": supply, "slot": slot, "first": supply not in seen,
                    "at": at, "id": row_id})
        seen.add(supply)
    return out


def settled_away(conn, dataset_id: str) -> dict[str, object]:
    """Supply id -> the instant a settlement of a contested pair made it
    rejected or kept-but-superseded (REQ-PIPE-193), for this dataset. Read
    from qa.decision_file, the one record of each file's outcome."""
    return {supply: at for supply, at in conn.execute(
        f'SELECT f.supply_id, d.effective_at FROM "{qa_store.SCHEMA}".decision_file f '
        f'JOIN "{qa_store.SCHEMA}".decision d ON d.id = f.decision_id '
        "WHERE d.dataset_id = ? AND f.outcome IN ('rejected', 'superseded')",
        [dataset_id]).fetchall()}


def filings_as_at(history: list[dict], as_at=None, settled: dict | None = None) -> list[dict]:
    """Each supply first filed on or before `as_at`, with the period it was
    filed to AS AT THAT INSTANT, ordered by when it was FIRST filed - so a
    later re-file of an older supply never makes it the newest arrival
    (REQ-DASH-197 criterion 3). `history` is filing_history()'s answer.

    `settled` is settled_away()'s answer: a file a settlement made rejected
    or kept-but-superseded is not an arrival from that settlement's instant
    on (REQ-DASH-197 criterion 2) - both of a pair's files are filed, so on
    first-filed order alone the spare could be named the latest arrival.
    """
    firsts: dict[str, dict] = {}
    slots: dict[str, tuple] = {}
    for row in history:
        if as_at is not None and row["at"] > as_at:
            continue
        away = (settled or {}).get(row["supply_id"])
        if away is not None and (as_at is None or away <= as_at):
            continue
        if row["first"]:
            firsts[row["supply_id"]] = row
        key = (row["at"], row["id"])
        if row["supply_id"] not in slots or key >= slots[row["supply_id"]][0]:
            slots[row["supply_id"]] = (key, row["slot"])
    ordered = sorted(firsts.values(), key=lambda r: (r["at"], r["supply_id"]))
    return [{"supply_id": r["supply_id"], "slot": slots[r["supply_id"]][1],
             "first_at": r["at"]} for r in ordered]


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

    return period_for_key(dataset_id, asset_time.arrival_key(received_at))


def period_for_key(dataset_id: str, key: str) -> str | None:
    """period_of(), for a caller holding the ARRIVAL KEY - a run id's own
    suffix - rather than the instant. One matching rule for both, so the
    `#1` suffix a contested supply carries is handled in one place."""
    supply = supply_received_at_key(dataset_id, key)
    if supply is None:
        return None
    return next((r.get("slot") for r in filings_of(dataset_id)
                 if r.get("supply_id") == supply), None)


def supply_received_at_key(dataset_id: str, key: str) -> str | None:
    """The supply whose OWN receipt carries this arrival key - one rule for
    period_for_key() and recorded_arrival_at().

    BY THE RECEIPT, NOT THE ID (REQ-PIPE-193 criterion 13, post-build-review
    #170): a settled pair's supply records its own file's receipt on its
    runs, and when the later file is chosen - or the second is re-filed -
    that receipt's key is not the staging key its id carries. The one
    receipt view answers; an id whose staging key matches (its plain form
    or a pair's `#1`) is the fallback for a supply with no receipt row."""
    from qa_tools.common import asset_time, supply_files

    with _connect("mothman:filing-read") as conn:
        rows = conn.execute(
            f"SELECT supply_id, received_at, received_instant FROM {RECEIPT} "
            "WHERE dataset_id = ?", [dataset_id]).fetchall()
    matched = []
    for supply, text, instant in rows:
        try:
            at = datetime.fromisoformat(text) if text else instant
        except ValueError:
            at = instant
        if at is not None and asset_time.arrival_key(at) == key:
            matched.append(supply)
    if matched:
        # Two supplies on one instant is a pair whose `#1` has not been
        # settled - the arrival's own supply is the first.
        return min(matched, key=lambda s: (supply_files.ordinal_of(s) not in ("", "1"), s))
    for record in filings_of(dataset_id):
        supply = record.get("supply_id") or ""
        if (supply_files.staging_key_of(supply) == key
                and supply_files.ordinal_of(supply) in ("", "1")):
            return supply
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

    slots_by_dataset: dict[tuple, list] = {}
    written: list[Assignment] = []
    found_arrivals = list(found_arrivals)
    # A REFUSED DATASET IS HELD, NEVER FILED (REQ-PIPE-173 criteria 2 and 3):
    # its recorded judgements no longer match the agreement and nothing
    # declared accounts for it, so filing a new supply against the changed
    # terms would be the silent re-judgement the backstop exists to stop.
    # Every other dataset files as usual.
    refused = _refused({d for a in found_arrivals for d in a.files_by_dataset})

    for arrival in found_arrivals:
        for dataset_id in sorted(arrival.files_by_dataset):
            # TWO FILES FOR ONE DATASET ARE FILED LIKE ANY SUPPLY
            # (REQ-PIPE-105 criterion 6, amended 2026-10-02). They were a
            # delivery-level HOLD - nothing filed, a work item asking which
            # file was the supply. Now they are CONTESTED: the supply id
            # carries `#1`, its period is known, the overlay refuses to
            # choose between its two staged tables and the promotion gate
            # sees `contested`. Choosing between them is still nobody's
            # job but a person's; it simply needs no second mechanism.
            # KEYED ON THE ARRIVAL'S OWN HORIZON, not built once per
            # dataset (delivery-critic, overnight sprint 3b): under
            # REQ-PIPE-131 a list built for an earlier arrival ends in a
            # slot that CLOSES, so a later arrival in the same call fell
            # past it and was held rather than filed to its own open day.
            try:
                horizon = (dataset_id, slots_mod.claimable_until(
                    dataset_id, arrival.received_at.date()))
            except (ValueError, KeyError, FileNotFoundError):
                horizon = (dataset_id, None)   # no slots - see below
            if horizon not in slots_by_dataset:
                try:
                    # THE CLAIM WINDOW'S REACH, NOT THE ARRIVAL DATE
                    # (post-build-review #73). Capping here at the
                    # arrival date withheld the very slot a supply
                    # arriving early is early FOR - see
                    # slots.claimable_until() for the worked example.
                    slots_by_dataset[horizon] = slots_mod.slots_for_dataset(
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
                    slots_by_dataset[horizon] = []
            supply_id = _supply_id_for(arrival, dataset_id)
            if filing_for(dataset_id, supply_id) is not None:
                continue
            decided = assign_mod.assign(
                dataset_id=dataset_id, supply_id=supply_id,
                at=arrival.received_at, slots=slots_by_dataset[horizon],
                filled=filled_slots(dataset_id), final_period=final_period_for(dataset_id))
            decided = held_as_turned_off(decided)
            # THE RULE FIRST, THE REFUSAL ONLY OVER A FILING (delivery-critic
            # on 173, #4): a supply the rule would hold anyway keeps its own
            # hold - schedule-ended says how it is fixed; a refusal hold
            # over it would clear into a hold nobody was told about.
            if dataset_id in refused and decided.slot and not decided.is_held:
                decided = Assignment(
                    dataset_id=dataset_id, supply_id=supply_id, slot=None,
                    branch=assign_mod.HELD, considered=decided.considered,
                    received_at=arrival.received_at,
                    agreement_refused=refused[dataset_id].message())
            # FILED AND SUPERSEDING IN ONE TRANSACTION (REQ-PIPE-118's
            # reliability NFR): a crash leaves the old state or the new one,
            # never two waiting versions of one table in one period.
            with _connect("mothman:filing-record") as conn:
                with conn.raw.transaction():
                    wrote = record(decided, arrival.delivery_name, conn=conn)
                    if wrote and decided.slot and not decided.is_held:
                        _supersede_earlier(conn, arrival, decided)
            # AN ASSIGNMENT-RULE HOLD IS RECORDED TOO (criterion 3). Its
            # `filing` row above is evidence of what the rule saw and
            # stays write-once; the open work item is the hold, because
            # that is the record a decision has to be able to close.
            if decided.is_held:
                _raise_assignment_hold(arrival, decided)
            written.append(decided)
    return written


def _refused(dataset_ids) -> dict:
    """{dataset_id: Refusal} for these datasets (REQ-PIPE-173). A backstop
    that cannot be evaluated refuses nothing - it is the second line behind
    the commit-time gate, and taking every filing down with it would be the
    blast-radius rule broken."""
    from qa_tools.common import agreement_drift

    try:
        with _connect("mothman:agreement-drift") as conn:
            return agreement_drift.refusals(conn, sorted(dataset_ids))
    except Exception as exc:  # noqa: BLE001 - see the docstring
        print(f"note: the agreement backstop could not be evaluated ({exc}); "
              f"nothing was refused.")
        return {}


def _supersede_earlier(conn, arrival, decided: Assignment) -> None:
    """REQ-PIPE-118 criterion 1: before any check runs over this file, every
    earlier unaccepted version of its table in the same period is
    superseded by it."""
    from qa_tools.common import hierarchy, supersession

    entry = hierarchy.dataset(decided.dataset_id)
    gone = supersession.supersede_earlier(
        conn, agency_id=entry.agency_id, collection_id=entry.collection_id,
        dataset_id=decided.dataset_id, period=decided.slot, newer=decided.supply_id,
        effective_at=arrival.received_at.isoformat())
    for supply in gone:
        print(f"superseded - {decided.dataset_id}: {supply} by {decided.supply_id} "
              f"for {decided.slot}")


def _raise_assignment_hold(arrival, decided: Assignment) -> None:
    """Record a supply the rule found no slot for (REQ-PIPE-064)."""
    from qa_tools.common import supply_holds

    with _connect("mothman:hold-raise") as conn:
        supply_holds.raise_hold(
            conn, dataset_id=decided.dataset_id, supply_id=decided.supply_id,
            kind=supply_holds.ASSIGNMENT_RULE,
            reason=supply_holds.reason_for(decided),
            raised_by=arrival.run_id, delivery=arrival.delivery_name)


def final_period_for(dataset_id: str) -> str | None:
    """The dataset's last authored period, or None where its calendar never
    runs out (a cadence rule) or it has none agreed (REQ-PIPE-154).

    THE WHOLE CALENDAR, not the slots filing looked at - those stop at the
    arrival's claim horizon, which is why this is asked separately."""
    from qa_tools.common import schedule

    try:
        if schedule.calendar_for_dataset(dataset_id).current.is_cadence_rule:
            return None
    except schedule.NoCalendarAgreed:
        return None
    owed = [p for p in schedule.periods_for_dataset(dataset_id) if p.expected]
    return owed[-1].period.name if owed else None


def _supply_id_for(arrival, dataset_id: str) -> str:
    """This dataset's own name for the supply in this arrival.

    The same identifier REQ-PIPE-034 builds, so a filing and an arrival
    can be joined without a second naming scheme to keep in step.
    """
    from qa_tools.common import asset_time

    names = arrival.files_by_dataset.get(dataset_id) or ()
    base = f"{dataset_id}@{asset_time.arrival_key(arrival.received_at)}"
    return base if len(names) <= 1 else f"{base}#1"


#: THE REFERENCE TO WHAT CAUSED A RE-FILE (REQ-PIPE-067 criterion 5) IS
#: NOT KEPT ON THE FILING since REQ-PIPE-144 criterion 8: a re-file's
#: from-period, to-period and reason belong to its decision-log entry,
#: which REQ-PIPE-141 builds. refile() below has no production caller.


def refile(conn, dataset_id: str, supply_id: str, to_slot: str, *,
           decision_id: int) -> dict | None:
    """File one supply to a different slot, as a NEW filing naming the
    decision that made it (REQ-PIPE-141 criteria 1 and 2) - in the
    caller's transaction, beside that decision.

    THE EARLIER FILING STAYS, UNCHANGED, AS HISTORY (criterion 1, NFR 3):
    qa.filing is append-only and the current filing is the newest row
    (qa.filing_current), so nothing here edits what was recorded before.

    THE VERDICT FOLLOWS THE FILING (REQ-PIPE-067): the new row's
    classification is computed against the new slot, from the receipt
    instant already recorded - when we received it is a fact, which
    period it was for is the decision being changed.

    Returns the new filing, or None where the supply was not filed or is
    already filed to that slot (nothing to change).
    """
    rows = conn.execute(
        f"SELECT {_SELECT} FROM {CURRENT} WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, supply_id]).fetchall()
    if not rows:
        return None
    current = _as_dict(rows[0])
    if current.get("slot") == to_slot:
        return None
    receipt = conn.execute(
        f"SELECT received_instant FROM {RECEIPT} WHERE dataset_id = ? AND supply_id = ?",
        [dataset_id, supply_id]).fetchall()
    received_at = receipt[0][0] if receipt else None
    judged = _judged_for(dataset_id, to_slot, received_at)
    at = _replay_clock.now()
    # The rule's branch no longer describes where it sits: a person put it
    # here. The delivery link is carried as it stands (REQ-PIPE-144 c17).
    new_id = conn.execute(
        f"INSERT INTO {TABLE} (dataset_id, supply_id, slot, branch, considered, "
        "delivery, classification, refiled_by, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "RETURNING id",
        [dataset_id, supply_id, to_slot, "refiled-by-a-person", [to_slot],
         current["delivery"], judged.classification, decision_id, at]).fetchall()[0][0]
    # A NEW FILING, A NEW VERDICT (REQ-PIPE-168 criterion 6): the newest
    # verdict for the current filing is the supply's verdict.
    verdict_mod.record(conn, new_id, dataset_id, supply_id, judged, recorded_at=at)
    return {**current, "slot": to_slot, "branch": "refiled-by-a-person",
            "classification": judged.classification}


def assignment_at(dataset_id: str, supply_id: str, at: datetime) -> Assignment:
    """What the filing rule says for a supply received at `at` - the same
    slots, the same filled set and the same rule an arrival is filed by
    (REQ-PIPE-131). A settlement asks it of the chosen file's own receipt
    (REQ-PIPE-193 criteria 10 and 11)."""
    from qa_tools.common import assignment as assign_mod
    from qa_tools.common import slots as slots_mod

    try:
        slots = slots_mod.slots_for_dataset(
            dataset_id, until=slots_mod.claimable_until(dataset_id, at.date()))
    except (ValueError, KeyError, FileNotFoundError):
        slots = []
    return held_as_turned_off(assign_mod.assign(
        dataset_id=dataset_id, supply_id=supply_id, at=at, slots=slots,
        filled=filled_slots(dataset_id), final_period=final_period_for(dataset_id)))


def held_as_turned_off(decided: Assignment) -> Assignment:
    """A hold whose receipt falls in a turned-off gap, said so (REQ-PIPE-179
    criteria 16 and 17): the turn-off recorded as history, and never also
    schedule ended. Every other assignment is returned as it is."""
    from dataclasses import replace

    from qa_tools.common import turned_off

    if not decided.is_held or decided.received_at is None or decided.agreement_refused:
        return decided
    turn = turned_off.gap_at(decided.dataset_id, decided.received_at)
    if turn is None:
        return decided
    return replace(decided, turned_off=turned_off.as_record(turn), schedule_ended=False,
                   last_period=None)


def file_settled(conn, dataset_id: str, supply_id: str, slot: str | None, *,
                 delivery: str, decision_id: int, received_at: datetime | None,
                 branch: str = "settled-by-a-person") -> int:
    """A filing written by a settlement (REQ-PIPE-193 criteria 10 and 12), in
    the caller's transaction: a `#2`'s first filing, or the settled supply's
    new one where its own receipt changes its period or verdict. In
    REQ-PIPE-141's append-only shape - a NEW row naming the decision, the
    earlier row kept - with its verdict judged on THIS file's receipt
    (REQ-PIPE-168). Returns the row's id."""
    judged = _judged_for(dataset_id, slot, received_at)
    at = _replay_clock.now()
    new_id = conn.execute(
        f"INSERT INTO {TABLE} (dataset_id, supply_id, slot, branch, considered, delivery, "
        "classification, refiled_by, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "RETURNING id",
        [dataset_id, supply_id, slot, branch, [slot] if slot else [], delivery,
         judged.classification, decision_id, at]).fetchall()[0][0]
    verdict_mod.record(conn, new_id, dataset_id, supply_id, judged, recorded_at=at)
    return int(new_id)


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
    #: A person's statement of when it was ORIGINALLY received, or
    #: NOT_KNOWN, or None where nobody was asked (REQ-PIPE-103 criterion
    #: 19) - shown beside `received_at`, never as it.
    stated_original: str | None = None
    #: Whether a person filed it, by which route, and who (REQ-PIPE-147).
    filed_by: dict | None = None
    #: Rejected or superseded - out of the queue without being promoted,
    #: so nobody is deciding on it (post-build-review #109, F5).
    set_aside: bool = False

    @property
    def awaiting(self) -> bool:
        """Whether the wait is still running (criterion 10) - never for a
        supply set aside, which is waiting on nobody."""
        return self.received_at is not None and self.filled_at is None and not self.set_aside

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
        if self.filled_at is None and self.set_aside:
            # A SET-ASIDE SUPPLY NEVER FINISHED WAITING (post-build-review
            # #109, F5): a figure measured to now would read as a wait that
            # ended in a promotion, which it did not.
            return None
        return (self.filled_at or asset_time.now()) - self.received_at


def received_at_of(dataset_id: str, supply_id: str) -> datetime | None:
    """Our receipt instant for this supply - from the one receipt view
    (REQ-PIPE-144 criterion 16), never a copy on the filing.

    WITH THE WRITER'S OWN OFFSET (post-build-review #161): the instant
    column comes back in UTC, and a key derived from it - a staged table's
    name, a filing's arrival key - no longer matches the key the supply
    carries, which kept the writer's offset (REQ-PIPE-069 criterion 5). A
    re-check of a Perth-time receipt found neither its table nor its
    period. The view keeps the writer's text for exactly this; the instant
    is the fallback for a row without it. Comparisons are unaffected - two
    aware datetimes compare by instant."""
    with _connect("mothman:filing-read") as conn:
        rows = conn.execute(
            f"SELECT received_at, received_instant FROM {RECEIPT} "
            "WHERE dataset_id = ? AND supply_id = ?",
            [dataset_id, supply_id]).fetchall()
    if not rows:
        return None
    text, instant = rows[0]
    try:
        return datetime.fromisoformat(text) if text else instant
    except ValueError:
        return instant


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
        # THE RECEIPT FROM THE ONE VIEW (REQ-PIPE-144 criterion 16).
        rows = conn.execute(
            f"SELECT f.slot, r.received_instant, f.classification, "
            f"r.originally_received_stated, d.filed_by_kind, d.filing_route, d.filed_by "
            f"FROM {CURRENT} f "
            f"LEFT JOIN {RECEIPT} r USING (dataset_id, supply_id) "
            f'JOIN "{qa_store.SCHEMA}".delivery d ON d.name = f.delivery '
            "WHERE f.dataset_id = ? AND f.supply_id = ?",
            [dataset_id, supply_id]).fetchall()
        if not rows:
            return None
        slot, received_at, classification, stated, kind, route, who = rows[0]
        filled_at = _filled_at(conn, dataset_id, supply_id, slot)
        from qa_tools.common import slot_state

        set_aside = slot_state._rejected(conn, dataset_id, supply_id)
    return RecordedArrival(dataset_id=dataset_id, supply_id=supply_id, slot=slot,
                            received_at=received_at, filled_at=filled_at,
                            classification=classification, stated_original=stated,
                            set_aside=set_aside, filed_by=({"kind": kind} if kind != "person"
                                      else {"kind": kind, "route": route, "who": who}))


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

    RECORDED METADATA, NEVER SUPPLY ROWS. This reads `qa.filing`,
    `qa.decision`, the `qa.supply_receipt` view and `qa.delivery` and nothing
    else - the same access
    `promotion_state.state_for()` already has from this build path, and
    well inside Keith's rule that a build may read recorded results and
    never the extract itself.
    """
    from qa_tools.common import asset_time

    supply = supply_received_at_key(dataset_id, asset_time.arrival_key(received_at))
    return recorded_arrival(dataset_id, supply) if supply else None


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
        "WHERE dataset_id = ? AND supply = ? AND to_slot = ? AND action = ?",
        # A RE-FILE NO LONGER FILLS ITS TARGET (REQ-PIPE-141 criterion 4):
        # the supply is checked there and promoted, or not, by a later
        # decision - which is when it is filled.
        [dataset_id, supply_id, slot, decision_log.PROMOTE]).fetchall()
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
    from qa_tools.common import asset_time, hierarchy, supply_db, supply_files

    key = asset_time.arrival_key(arrival.received_at)
    stated = getattr(arrival, "supply_ids", None) or {}
    out: list[dict] = []
    for dataset_id in sorted(arrival.files_by_dataset):
        # A RUN ABOUT ONE SUPPLY SAYS WHICH (a re-check); an arrival's supply
        # is the one its arrival mints (REQ-PIPE-193 criterion 13).
        supply_id = stated.get(dataset_id) or _supply_id_for(arrival, dataset_id)
        try:
            logical = hierarchy.dataset(dataset_id).table
        except hierarchy.UnknownDatasetError:
            # The same fallback promotion.status_of() makes, and for the
            # same reason: a dataset the tree does not know still has an
            # id, and raising inside the step would cost the other
            # twenty-nine their promotions.
            logical = dataset_id
        resolved = supply_files.resolve(conn, dataset_id, supply_id)
        if resolved is not None:
            # ITS OWN TABLES IN STAGING, by the one resolver - a settled
            # pair's supply is ONE of the two (criterion 13).
            present = set(supply_db.candidates_in(
                conn, supply_db.STAGING_SCHEMA, [logical],
                arrival=resolved.staging_key).get(logical) or [])
            staged = [t for t in resolved.tables if t in present]
        else:
            staged = supply_db.candidates_in(
                conn, supply_db.STAGING_SCHEMA, [logical], arrival=key).get(logical) or []
        period = resolved.period if resolved is not None else None
        out.append({
            "dataset_id": dataset_id,
            "supply": supply_id,
            "period": period,
            "physical_tables": sorted(staged),
            # SEVERAL STAGED TABLES FOR ONE NAME is REQ-PIPE-059's case
            # seen from the warehouse rather than from the file listing.
            # Both are reported because they can disagree - a file that
            # matched but failed to load leaves one without the other -
            # and either is a reason not to choose.
            # AND AN UNSETTLED PAIR stays contested even where the load
            # refused one of its files - choosing is a person's job, never
            # the system's because only one file loaded (REQ-PIPE-193
            # criterion 7).
            "contested": len(staged) > 1 or bool(resolved and resolved.is_pair),
        })
    return out
