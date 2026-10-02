"""What each slot held, and when that changed (REQ-PIPE-081).

THE QUESTION IS "WHAT WAS IN PLACE", not "what had arrived". Those read
alike and are different: a supply that arrived in June and was promoted
in August was not in place in June, and a supply demoted in August was
in place in June all the same. The page has answered the second
question while labelling it the first, by filtering runs on their
arrival date.

THE ANSWERS TRAVEL, NOT THE RULE, and that is the decision worth
keeping. `decision_log.promoted_into(as_at=...)` already resolves a
slot correctly, but a static page cannot call it once per date the
reader picks. Shipping the DECISIONS and letting the page apply the
rule would put a second implementation of it in JavaScript, free to
drift from the first - which this project has paid for before:
REQ-DASH-054 deleted a JS port of the cadence rule for exactly this
reason, and CLAUDE.md records the day four implementations of status
existed and one rendered a check with fourteen real violations green.

So what travels is a timeline of ANSWERS - what this slot resolved to
after each decision - and the page does a lookup. The rule stays in
Python, in one place, and `in_place_on()` below is the lookup, kept
here so the test suite can hold the two against each other.

RECORDED DECISIONS AND NOTHING ELSE (criterion 3). This reads the
decision log; it does not look at what the warehouse currently holds,
because those contents are the result of the NEWEST decision and would
answer "now" whatever instant was asked for.
"""
from __future__ import annotations

from qa_tools.common import decision_log, supply_db

#: Actions that put a supply INTO a slot. A substitution counts: the
#: period answers, which is what a reader of it needs to know.
FILLS = (decision_log.PROMOTE, decision_log.REFILE, decision_log.SUBSTITUTE)


def for_dataset(dataset_id: str, conn: supply_db.SupplyConnection | None = None) -> list[dict]:
    """Every change to what one dataset's slots held, oldest first.

    One entry per (decision, slot it changed) - so a re-file, which
    empties one slot and fills another, contributes TWO. Keying on the
    decision instead would lose half of it.

    ORDERED BY (effective_at, id), the same total order
    `promoted_into()` uses. Two decisions can share an instant and `id`
    is the only tiebreak there is; without it the order is whichever
    row the planner returned first, which is stable right up until it
    is not.

    `at` IS THE EFFECTIVE INSTANT, never the recorded one. A decision
    taken on Tuesday and recorded on Friday took effect on Tuesday.
    The recorded instant answers "what did we know", which is a real
    question and a different one.
    """
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:slot-timeline") as opened:
            return for_dataset(dataset_id, conn=opened)

    rows = conn.execute(
        f"SELECT id, action, supply, from_slot, to_slot, effective_at, actor, "
        f"actor_kind, reason FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? AND (to_slot IS NOT NULL OR from_slot IS NOT NULL) "
        "ORDER BY effective_at, id", [dataset_id]).fetchall()

    out: list[dict] = []
    for (ident, action, supply, from_slot, to_slot, effective_at,
         actor, actor_kind, reason) in rows:
        at = effective_at.isoformat() if hasattr(effective_at, "isoformat") else str(effective_at)
        common = {"at": at, "action": action, "actor": actor,
                   "actor_kind": actor_kind, "reason": reason or "",
                   "decision_id": ident}
        # EMPTIED FIRST, then filled - so a re-file's two entries land
        # in an order a reader can follow, and so a lookup at the same
        # instant sees the destination rather than the origin.
        if from_slot and from_slot != to_slot:
            out.append({**common, "slot": from_slot, "supply": None})
        if to_slot:
            out.append({**common, "slot": to_slot,
                         "supply": supply if action in FILLS else None})
    return out


def in_place_on(timeline: list[dict], slot: str, at: str) -> str | None:
    """What `slot` held as at `at`, by lookup over the timeline.

    THE PAGE'S OWN RULE, written here in Python so the suite can hold
    it against `decision_log.promoted_into()` and fail if the two ever
    disagree. The JavaScript does the same lookup; what it must never
    do is re-derive which actions fill and which empty, because that is
    the rule and the rule has one home.
    """
    answer = None
    for entry in timeline:
        if entry["slot"] != slot:
            continue
        if entry["at"] > at:
            break
        answer = entry["supply"]
    return answer


# --------------------------------------------------------------------
# Tying an answer to a run
#
# SEPARATE FROM for_dataset() DELIBERATELY. Criterion 3 says an "as at
# T" answer is derived from the decision log alone, and that is exactly
# what for_dataset() reads. Getting from a supply to the run that
# CHECKED it is a different recorded fact in a different table, so it
# is a different function rather than a quiet widening of the log-only
# one. A caller that wants both asks for both.
# --------------------------------------------------------------------


def _run_for(conn, dataset_id: str, supply: str) -> str | None:
    """The run that checked this supply, via drift_reference.

    ONE IMPLEMENTATION OF THE MAPPING, not a second. The supply id and
    the physical table share an ARRIVAL KEY, and `drift_reference`
    already works that out - including the rule about which run wins
    where several read the same table. Re-deriving it here would be the
    thing this module's own docstring argues against, one layer down.
    """
    from qa_tools.common import drift_reference

    return drift_reference.run_for(conn, dataset_id, supply)


def with_runs(timeline: list[dict], dataset_id: str,
               conn: supply_db.SupplyConnection | None = None) -> list[dict]:
    """The same timeline, each entry naming the run that checked it.

    `run_id` IS NONE FOR AN EMPTIED SLOT, because nothing is in place
    to show, and None for a supply no run ever read - a real state
    rather than a fault, true of anything promoted by hand before QA
    saw it. The entry is still the truth about what the slot held.

    LOOKED UP ONCE PER SUPPLY rather than once per entry: a supply
    promoted, demoted and promoted again appears several times and the
    answer cannot differ between them.
    """
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:slot-timeline-runs") as opened:
            return with_runs(timeline, dataset_id, conn=opened)

    cache: dict[str, str | None] = {}
    out = []
    for entry in timeline:
        supply = entry.get("supply")
        if supply and supply not in cache:
            cache[supply] = _run_for(conn, dataset_id, supply)
        out.append({**entry, "run_id": cache.get(supply) if supply else None})
    return out
