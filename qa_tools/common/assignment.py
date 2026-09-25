"""Which slot a supply is for (REQ-PIPE-062).

THE RULE, in the order it is applied:

1. If the arrival is at or before the CURRENT slot's due instant plus
   that slot's grace, and that slot is unfilled, it fills the current
   slot - even where earlier slots are unfilled.
2. Otherwise it fills the OLDEST slot whose claim window has opened and
   which is unfilled.
3. Otherwise it is a RESUPPLY of the most recently filled slot.

NEVER CLAIM FORWARD, under any branch. A slot whose claim window has
not opened cannot be claimed at all, which makes the forward cascade
structurally impossible rather than merely unlikely. The asymmetry is
the argument: mis-attributing an arrival BACKWARDS is one contained
error on one supply, while mis-attributing it FORWARDS cascades through
every future delivery.

BOTH CASCADES ARE WHY STEP 1 EXISTS, and both read as perfectly
reasonable rules, which is why they are written down here rather than
left to be rediscovered.

  THE FORWARD CASCADE, from "oldest unfilled slot" alone. Daily feed
  due 12:00 Monday. Mon 14:00 arrives, red, rejected - Monday still
  unfilled. Mon 16:00 arrives, green, promoted - Monday filled. Mon
  20:00 a third file arrives, and the oldest unfilled slot is now
  TUESDAY, so a Monday resupply files as Tuesday's delivery. The next
  takes Wednesday. Every later supply is off by one, permanently. The
  cause: "oldest unfilled" assumes every arrival fills a NEW
  obligation, and a resupply does not.

  THE BACKWARD CASCADE, introduced by the fix for the forward one.
  Daily feed due ~22:00. Monday filled; the supplier's system goes
  down and Tuesday and Wednesday are missed; the next supply arrives
  on time at 22:00 Thursday. Under "oldest claimable unfilled" it
  files as Tuesday two days late, the next as Wednesday, the next as
  Thursday - a permanent two-day lag, every day locally plausible,
  never self-correcting.

PUNCTUALITY IS EVIDENCE OF WHICH SLOT A SUPPLY IS FOR. That is what
step 1 says and why it comes first: Thursday 22:00 for a Thursday due
22:00 fills Thursday, and Tuesday and Wednesday stay unfilled and read
as missed, which is TRUE. Monday's supply arriving Tuesday 03:00 is not
on time for Tuesday, so it takes the oldest unfilled - Monday, late.
Lateness still works, and an outage no longer eats the future.

ONLY A PROMOTION FILLS A SLOT, and that is load-bearing rather than
definitional. Without it the Monday 16:00 resupply above would itself
have been pushed to Tuesday, because Monday would have been "filled" by
the rejected 14:00 supply. An arrival does not fill a slot; a staged
supply does not; a rejected one certainly does not.

THE COST BEING ACCEPTED, stated because it is real: a boundary misfile
is wrong TWICE. A punctual supplier is recorded as delivering a very
late resupply, AND the slot they actually filled is left to go overdue
as a phantom missing delivery. The DATA half is fine - it sits in the
previous slot, present and checked. Generous or contiguous claim
windows were rejected as the cure, because they reintroduce the
forward cascade exactly; no window sizing gets both, and the trade is
taken in favour of never claiming forward.

NOTHING HERE READS THE SUPPLY. Assignment is a function of slot
configuration and promotion state alone. Deriving the period from the
supply's own content is circular - it infers the filing decision from
the very data whose correctness is about to be tested, and a resupply
exists precisely because the first attempt was wrong, possibly wrong in
its dates. A supplier-declared period is unenforceable across a wide
supplier base, and the suppliers who would get it wrong are exactly the
ones whose data most needs QA.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from qa_tools.common import asset_time, slots as slots_mod

#: Which branch of the rule decided an assignment. Recorded with the
#: supply rather than recomputed later, because recomputing is NOT
#: equivalent - the slot state it was decided against has moved on.
ON_TIME = "on-time-current-slot"
OLDEST_CLAIMABLE = "oldest-claimable-unfilled"
RESUPPLY = "resupply-of-most-recently-filled"
UNASSIGNABLE = "no-slot-and-nothing-filled"


@dataclass(frozen=True)
class Assignment:
    """Where one supply was filed, and why.

    `branch` and `considered` are not diagnostics - they are the answer
    to "why is this supply here", asked a year later by somebody who
    cannot re-run anything. Recomputing it then would give a different
    answer, because the slot state it was decided against has moved on.
    """

    dataset_id: str
    supply_id: str
    slot: str | None
    branch: str
    considered: tuple[str, ...]
    resupply_of: str | None = None

    @property
    def is_resupply(self) -> bool:
        return self.branch == RESUPPLY

    def as_record(self) -> dict:
        return {"dataset_id": self.dataset_id, "supply_id": self.supply_id,
                "slot": self.slot, "branch": self.branch,
                "considered": list(self.considered), "resupply_of": self.resupply_of}


def current_slot(slots: Sequence[slots_mod.Slot], at: datetime) -> slots_mod.Slot | None:
    """The slot a supply arriving at `at` is CURRENTLY in - the newest
    one whose claim window has opened.

    FOUND BY BISECTION, not by scanning. A daily feed with years of
    history has thousands of slots, and the rule only ever needs this
    one and the oldest claimable unfilled one; walking the whole
    sequence per arrival is the thing the non-functional constraint
    forbids. Slots come back oldest first, so their claim instants are
    already sorted.
    """
    asset_time.parse_instant(at, "current_slot(at)")
    opens = [s.claim_opens_at for s in slots]
    index = bisect.bisect_right(opens, at) - 1
    return slots[index] if index >= 0 else None


def oldest_claimable_unfilled(slots: Sequence[slots_mod.Slot], at: datetime,
                               filled: frozenset[str]) -> slots_mod.Slot | None:
    """The oldest slot whose window is open and which is unfilled.

    Stops at the first hit. Once REQ-PIPE-063's monotonic filling
    lands, the filled slots are a prefix and this is the slot just
    after it; until then it is bounded by the run of filled slots at
    the front, which is the same bound in practice.
    """
    for slot in slots:
        if slot.name in filled:
            continue
        if slots_mod.is_claimable(slot, at):
            return slot
        # Slots are ordered, so the first one that is NOT claimable
        # means every later one is in the future too.
        return None
    return None


def most_recently_filled(slots: Sequence[slots_mod.Slot],
                          filled: frozenset[str]) -> slots_mod.Slot | None:
    for slot in reversed(slots):
        if slot.name in filled:
            return slot
    return None


def assign(dataset_id: str, supply_id: str, at: datetime,
            slots: Sequence[slots_mod.Slot],
            filled: frozenset[str]) -> Assignment:
    """File one supply, by rule, with no human in it.

    `filled` is the set of slot names a supply has been PROMOTED into -
    never staged, never merely arrived, never rejected.

    A supply whose checks will report red is assigned on exactly the
    same terms as any other (criterion 11), so a supply that is never
    promoted still carries where it was filed. "Arrived three weeks
    late AND was bad" is what belongs on the record.
    """
    asset_time.parse_instant(at, "assign(at)")
    considered: list[str] = []

    # 1. ON TIME FOR THE CURRENT SLOT. Punctuality is evidence of which
    #    slot a supply is for, and this branch is the whole defence
    #    against the backward cascade.
    current = current_slot(slots, at)
    if current is not None:
        considered.append(current.name)
        if current.name not in filled and at <= current.late_after:
            return Assignment(dataset_id=dataset_id, supply_id=supply_id,
                               slot=current.name, branch=ON_TIME,
                               considered=tuple(considered))

    # 2. OLDEST CLAIMABLE UNFILLED. Lateness still works.
    oldest = oldest_claimable_unfilled(slots, at, filled)
    if oldest is not None:
        if oldest.name not in considered:
            considered.append(oldest.name)
        return Assignment(dataset_id=dataset_id, supply_id=supply_id,
                           slot=oldest.name, branch=OLDEST_CLAIMABLE,
                           considered=tuple(considered))

    # 3. A RESUPPLY of the most recently filled slot. This is where a
    #    second file for an already-filled slot lands, and it is what
    #    stops "oldest unfilled" pushing it into the future.
    latest = most_recently_filled(slots, filled)
    if latest is not None:
        if latest.name not in considered:
            considered.append(latest.name)
        return Assignment(dataset_id=dataset_id, supply_id=supply_id,
                           slot=latest.name, branch=RESUPPLY,
                           considered=tuple(considered), resupply_of=latest.name)

    # Nothing claimable and nothing ever filled: a supply arriving
    # before this dataset's first slot window opens. Recorded as
    # unassignable rather than forced into a slot, because forcing it
    # would be claiming forward - the one thing criterion 5 makes
    # absolute.
    return Assignment(dataset_id=dataset_id, supply_id=supply_id, slot=None,
                       branch=UNASSIGNABLE, considered=tuple(considered))
