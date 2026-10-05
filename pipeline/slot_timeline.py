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

from qa_tools.common import decision_log, qa_store, supply_db

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

    # THE ANSWERS COME FROM qa.slot_holds (REQ-PIPE-130 criterion 9),
    # asked as at each instant a decision took effect - never from a rule
    # re-stated here. This module used to work out for itself which
    # actions fill and which empty, and so read a withheld note, or a
    # reject of some other supply filed to the period, as emptying a slot
    # that still held its supply (post-build-review #84). An entry is
    # written where the decision that last CHANGED a slot moves on.
    instants = [r[0] for r in conn.execute(
        f"SELECT DISTINCT effective_at FROM {decision_log.TABLE} "
        "WHERE dataset_id = ? ORDER BY effective_at", [dataset_id]).fetchall()]
    out: list[dict] = []
    seen: dict[str, int] = {}
    for instant in instants:
        changed = []
        for slot, decision_id, fills in conn.execute(
                f'SELECT slot, decision_id, fills FROM "{qa_store.SCHEMA}".slot_holds(?, ?)',
                [dataset_id, instant]).fetchall():
            if seen.get(slot) != decision_id:
                seen[slot] = decision_id
                changed.append((slot, decision_id, fills))
        at = instant.isoformat() if hasattr(instant, "isoformat") else str(instant)
        # EMPTIED FIRST, then filled - so a re-file's two entries land in
        # an order a reader can follow, and so a lookup at the same
        # instant sees the destination rather than the origin.
        for slot, decision_id, fills in sorted(changed, key=lambda c: (c[2] is not None, c[0])):
            action, actor, actor_kind, reason = conn.execute(
                f"SELECT action, actor, actor_kind, reason FROM {decision_log.TABLE} "
                "WHERE id = ?", [decision_id]).fetchall()[0]
            out.append({"at": at, "action": action, "actor": actor,
                        "actor_kind": actor_kind, "reason": reason or "",
                        "decision_id": decision_id, "slot": slot, "supply": fills})
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


#: What each decision does to the supply it names, for the page's verdict
#: (REQ-PIPE-081 criteria 1, 2 and 8 as amended 2026-10-05, Keith). A
#: decision not listed - a withheld note, an acknowledgement, a refusal -
#: changes nothing about whether the supply is in the view.
_STATE_AFTER = {
    decision_log.PROMOTE: "promoted",
    decision_log.REFILE: "promoted",
    decision_log.DEMOTE: "withdrawn",
    decision_log.REJECT: "withdrawn",
    decision_log.SUPERSEDE: "withdrawn",
    decision_log.UN_SUPERSEDE: "awaiting",
}


def supply_states(dataset_id: str,
                  conn: supply_db.SupplyConnection | None = None) -> dict[str, list[dict]]:
    """{supply: [{at, state}]} - each supply's state after every decision
    about it, oldest first, state one of promoted, awaiting or withdrawn.

    Before its first entry a filed supply is AWAITING A DECISION, which is
    why only decisions travel: the page already knows when each run
    arrived. A withdrawn supply - demoted, turned down by a reject,
    re-filed out of its slot or superseded (criterion 2) - leaves the
    dataset's verdict; the
    newest supply promoted or awaiting is the one shown (criterion 1).
    The answers, not the rule: the page looks these up and never decides
    for itself which action withdraws.
    """
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:supply-states") as opened:
            return supply_states(dataset_id, conn=opened)
    actions = tuple(_STATE_AFTER)
    out: dict[str, list[dict]] = {}
    for supply, action, at in conn.execute(
            f"SELECT supply, action, effective_at FROM {decision_log.TABLE} "
            f"WHERE dataset_id = ? AND supply IS NOT NULL AND action IN "
            f"({', '.join('?' * len(actions))}) ORDER BY effective_at, id",
            [dataset_id, *actions]).fetchall():
        state = _STATE_AFTER[action]
        entries = out.setdefault(supply, [])
        if entries and entries[-1]["state"] == state:
            continue
        entries.append({"at": at.isoformat() if hasattr(at, "isoformat") else str(at),
                        "state": state})
    return out


def run_states(dataset_id: str,
               conn: supply_db.SupplyConnection | None = None) -> dict[str, list[dict]]:
    """supply_states() keyed by the run that checked each supply - what the
    dashboard embeds, since the page knows runs. A supply no run read is
    left out: there is nothing of it on the page to withdraw."""
    if conn is None:
        with supply_db.connect(read_only=True, label="mothman:run-states") as opened:
            return run_states(dataset_id, conn=opened)
    out: dict[str, list[dict]] = {}
    for supply, states in supply_states(dataset_id, conn=conn).items():
        run = _run_for(conn, dataset_id, supply)
        if run:
            out[run] = states
    return out


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
