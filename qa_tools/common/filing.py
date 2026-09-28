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
        rows = conn.execute(
            f"INSERT INTO {TABLE} (dataset_id, supply_id, slot, branch, record) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (dataset_id, supply_id) DO NOTHING "
            "RETURNING dataset_id",
            [assignment.dataset_id, assignment.supply_id, assignment.slot,
             assignment.branch, json.dumps(assignment.as_record())]).fetchall()
    return bool(rows)


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
            if dataset_id in arrival.held:
                continue
            if dataset_id not in slots_by_dataset:
                try:
                    slots_by_dataset[dataset_id] = slots_mod.slots_for_dataset(
                        dataset_id, until=arrival.received_at.date())
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
            written.append(decided)
    return written


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

    # AN UPDATE, AND THE ONLY ONE THIS TABLE TAKES. Write-once
    # (REQ-PIPE-104 criterion 2) is about the RULE never re-deriving a
    # filing against a schedule that has moved on; a person moving a
    # supply is the other thing entirely, and REQ-PIPE-067 requires the
    # verdict to follow it. That is why `qa.filing` has no append-only
    # trigger while `qa.decision` does - see the DDL.
    with _connect("mothman:filing-refile") as conn:
        conn.execute(
            f"UPDATE {TABLE} SET slot = ?, branch = ?, record = ? "
            "WHERE dataset_id = ? AND supply_id = ?",
            [to_slot, updated["branch"], json.dumps(updated), dataset_id, supply_id])
    return updated


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
