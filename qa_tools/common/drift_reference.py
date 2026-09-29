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

#: The two actions that put a real supply INTO a period. A substitution
#: or an inheritance puts a view there, which is what criterion 6 skips.
A_REAL_SUPPLY = (decision_log.PROMOTE, decision_log.REFILE)


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
        latest = decision_log.latest_for_slot(conn, dataset_id, slot)
        if latest and latest[0] in A_REAL_SUPPLY:
            return Reference(dataset_id=dataset_id, period=slot, supply=latest[1])
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
    table is the one that brought it. No physical table in this
    deployment's 150 is read by more than one run today, which makes
    this rule dormant rather than wrong.
    """
    from qa_tools.common import hierarchy, qa_store

    if "@" not in (supply or ""):
        return None
    arrival = supply.rsplit("@", 1)[1]
    try:
        logical = hierarchy.dataset(dataset_id).table
    except hierarchy.UnknownDatasetError:
        return None

    rows = conn.execute(
        f'SELECT t.run_key FROM "{qa_store.SCHEMA}".tables_read t '
        f'JOIN "{qa_store.SCHEMA}".run r ON r.run_key = t.run_key '
        "WHERE t.logical_table = ? AND t.physical_table LIKE ? "
        "ORDER BY r.run_instant, t.run_key LIMIT 1",
        [logical, f"{logical}__{arrival}%"]).fetchall()
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
