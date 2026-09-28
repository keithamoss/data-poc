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
