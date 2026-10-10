"""Early, on time or late - measured against the slot the supply was
FILED TO (REQ-PIPE-066).

THE GAP THIS CLOSES, with its worked examples, because the old
behaviour is plausible enough to be reinstated by accident.
pipeline.cadence.classify_arrival() derives the cycle from the ARRIVAL
DATE via cycle_start(), which is defined as the most recent expected
day at or before its input - so it can only ever look BACKWARDS. Two
consequences fall straight out:

  A quarterly supply arriving 2026-07-25 for the 2026-08-01 anchor
  resolves to the 2026-05-01 anchor, and reads about TWELVE WEEKS LATE
  for a quarter that was filled months ago.

  A 10pm daily arrival intended for the next day reads late against
  the current one.

And "early" can only mean early WITHIN a cycle, because a backwards
lookup can never land on a slot that has not started.

THE FIX IS A SIGNATURE CHANGE, not a new cadence property: classify
against the ASSIGNED SLOT. Assignment already decided the period using
information cycle_start() does not have - namely which slots are
already filled - so deriving it a second time here would create two
implementations of one concept that can disagree, which is exactly the
failure this project has already recorded once.

IT REMOVES A CONCEPT RATHER THAN ADDING ONE, and that is the part most
likely to be undone by a well-meaning later change. Once the slot is
known, EARLY is simply "arrived before due_at". There is no separate
earliness window left to configure: it is a filing parameter, not a
cadence one.

PER TABLE, NEVER PER DELIVERY. If cp_clients lands 09:00 and
cp_placements 14:00, each gets its own verdict rather than the whole
delivery taking the worst - one late table must not drag five punctual
siblings down with it. It follows from slots being per-table.

THE GRACE IS THE SLOT'S OWN, which is per-dataset: Birth Registrations
allows an hour and Child Protection eight, so a collection-level or
asset-level grace would be one table's answer imposed on the rest.

COMPUTABLE BEFORE PROMOTION, because a REJECTED supply still gets
classified - "arrived three weeks late AND was bad" is exactly what
belongs on the record for a supply that never got promoted. Anything
needing promotion state would make the record depend on a decision that
may never be taken.
"""
from __future__ import annotations

from datetime import datetime

from qa_tools.common import asset_time, slots as slots_mod

EARLY = "early"
ON_TIME = "on_time"
LATE = "late"

#: A supply with no assigned slot (criterion 8). NOT a fourth kind of
#: punctuality - there is nothing to be punctual against - and saying
#: "on time" or "late" here would be inventing a verdict from an
#: absence.
UNFILED = "unfiled"


def classify(arrived_at: datetime, slot: slots_mod.Slot | None) -> str:
    """Early, on time or late for the slot this supply was filed to.

    A PURE FUNCTION of the arrival instant and the assigned slot, which
    is what makes it computable at check time and identical wherever it
    is asked. Nothing measures how early a supply is in order to assign
    it - earliness is a reported CONSEQUENCE of the assignment, not an
    input to it.
    """
    if slot is None:
        return UNFILED
    asset_time.parse_instant(arrived_at, "classify(arrived_at)")
    if arrived_at < slot.due_at:
        return EARLY
    if arrived_at <= slot.late_after:
        return ON_TIME
    return LATE


def describe(status: str, arrived_at: datetime, slot: slots_mod.Slot | None) -> str:
    """The verdict in words, naming the slot it was measured against.

    The slot is named because the whole failure this replaces was a
    verdict measured against the WRONG period - "filed to Q3, reported
    late for Q2" - and a bare "late" gives a reader no way to notice
    that has happened again.
    """
    if slot is None:
        return "unfiled - no slot was assigned, so there is nothing to be early or late for"
    if status == EARLY:
        return f"early for {slot.name}, which was due {slot.due_at.isoformat()}"
    if status == ON_TIME:
        return f"on time for {slot.name}, within its own grace allowance"
    return f"late for {slot.name}, which was due {slot.due_at.isoformat()}"
