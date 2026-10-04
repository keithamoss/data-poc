"""Which slot a supply is for (REQ-PIPE-062, as amended by REQ-PIPE-131).

THE RULE: a supply is filed only to the slot of its dataset that is OPEN
at its receipt instant.

- A slot is OPEN from its own claim-opening instant until the claim-
  opening instant of the NEXT PERIOD OF ITS CALENDAR, whether or not the
  dataset owes anything in that next period (slots.Slot.closes_at).
- If that open slot is unfilled, the supply fills it - early, on time or
  late for it alike.
- If a promoted supply already fills it, the supply is a resupply of it.
- If no slot is open - before the dataset's first claim window, or in a
  calendar period the dataset does not participate in - it is HELD for a
  person (REQ-PIPE-064), and filed neither forward nor backward.

NEVER CLAIM FORWARD, and since REQ-PIPE-131 NEVER BACKWARD EITHER. The
open slot is the newest whose window HAS opened, so a slot whose window
has not opened can never be claimed (REQ-PIPE-062 criterion 5). And a
slot that has closed is never filed to automatically, whatever its
state - which is the defect REQ-PIPE-131 fixed: a file arriving late for
the current period while an OLDER one was unfilled used to be filed
backward into the older one (the retired oldest-claimable-unfilled
branch), because a claim window never closed and REQ-PIPE-063's
monotonic filling closed a slot only once a LATER one was filled.

WHY THE CASCADES CANNOT HAPPEN, which the old rule needed three branches
and a monotonic-filling pass to guarantee:

  THE FORWARD CASCADE - a Monday resupply filed as Tuesday's because
  "oldest unfilled" assumed every arrival fills a new obligation. Monday
  is the open slot until Tuesday's window opens, and a filled open slot
  takes a resupply, so a third Monday file is a Monday resupply.

  THE BACKWARD CASCADE - after an outage, every later supply filed one
  slot behind its own day for ever. Each supply goes to the slot open
  when it arrived, so a missed day stays missed and today's file is
  today's.

THE COST BEING ACCEPTED, stated because it is real and was Keith's call
(2026-10-04): Monday's file arriving after Tuesday's claim window opened
is filed as TUESDAY's, and Monday closes with no supply. A closed,
visibly empty Monday was judged better than Monday's data filed
backward, and a person can re-file it.

ONLY A PROMOTION FILLS A SLOT. An arrival does not, a staged supply does
not, a rejected one certainly does not - otherwise a resupply after a
rejection would be recorded as a resupply of nothing.

NOTHING HERE READS THE SUPPLY. Assignment is a function of slot
configuration, the receipt instant and promotion state alone. Deriving
the period from the supply's content is circular - a resupply exists
precisely because the first attempt was wrong, possibly in its dates.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from qa_tools.common import asset_time, slots as slots_mod

#: Which branch of the rule decided an assignment (REQ-PIPE-062
#: criterion 9). Recorded with the supply rather than recomputed later,
#: because recomputing is NOT equivalent - the slot state it was decided
#: against has moved on.
OPEN_UNFILLED = "open-slot-unfilled"
RESUPPLY = "resupply-of-open-slot"
HELD = "held-no-open-slot"


@dataclass(frozen=True)
class Assignment:
    """Where one supply was filed, and why.

    `branch` and `considered` are not diagnostics - they are the answer
    to "why is this supply here", asked a year later by somebody who
    cannot re-run anything.
    """

    dataset_id: str
    supply_id: str
    slot: str | None
    branch: str
    considered: tuple[str, ...]
    resupply_of: str | None = None
    #: For a HELD supply: why each slot near it was unavailable
    #: (REQ-PIPE-064 criterion 4). A hold that says only "no slot" tells
    #: a person nothing they can act on, and acting on it is the point.
    unavailable: tuple[tuple[str, str], ...] = ()
    #: OUR RECEIPT INSTANT (REQ-PIPE-080 criterion 4) - when our own
    #: storage recorded the object, never a timestamp inside the
    #: supplier's file. Carried so the filing can record the arrival
    #: classification at the moment it records the slot.
    #:
    #: OPTIONAL, because a caller with no arrival instant is a real case
    #: - a test. The filing then records no classification rather than
    #: inventing one from the clock.
    received_at: "datetime | None" = None

    @property
    def is_resupply(self) -> bool:
        return self.branch == RESUPPLY

    @property
    def is_held(self) -> bool:
        return self.branch == HELD

    def describe(self) -> str:
        """Why this supply is where it is, in words.

        For a hold this is the whole deliverable: REQ-PIPE-064 criterion
        4 asks it to name the slots it considered AND why each was
        unavailable, because the resolution is a person choosing one.
        """
        if not self.is_held:
            return f"{self.supply_id} -> {self.slot} ({self.branch})"
        reasons = "; ".join(f"{name}: {why}" for name, why in self.unavailable)
        return (f"{self.supply_id} could not be placed - no period of this dataset "
                f"was open when it arrived ({reasons or 'no slot at all'}). It is not "
                f"filed forward or backward, stays staged, and is not checked until "
                f"somebody assigns it.")

    def as_record(self) -> dict:
        # NO resupply_of (REQ-PIPE-144 criterion 5 - it always equals the
        # slot on a resupply) and NO unavailable (criterion 6 - a held
        # supply's reasons live in qa.hold.reason).
        return {"dataset_id": self.dataset_id, "supply_id": self.supply_id,
                "slot": self.slot, "branch": self.branch,
                "considered": list(self.considered)}


def current_slot(slots: Sequence[slots_mod.Slot], at: datetime) -> slots_mod.Slot | None:
    """The newest slot whose claim window has opened by `at` - open or
    already closed.

    FOUND BY BISECTION, not by scanning (REQ-PIPE-131 criterion 11). A
    daily feed has thousands of slots, and walking them per arrival is
    what the requirement's scale constraint forbids. Slots come back
    oldest first, and REQ-PIPE-134 forbids overlapping periods, so their
    claim instants are sorted.
    """
    asset_time.parse_instant(at, "current_slot(at)")
    index = _opened_by(slots, at) - 1
    return slots[index] if index >= 0 else None


def _opened_by(slots: Sequence[slots_mod.Slot], at: datetime) -> int:
    """How many slots' claim windows have opened by `at` - a bisection
    that reads O(log n) slots, never a key list built from all of them
    (which is O(n) per arrival, and what the first version did)."""
    return bisect.bisect_right(slots, at, key=lambda s: s.claim_opens_at)


def open_slot(slots: Sequence[slots_mod.Slot], at: datetime) -> slots_mod.Slot | None:
    """The one slot open at `at`, or None (REQ-PIPE-131 criteria 1, 5).

    The newest slot whose window has opened, by bisection - and only if
    it has not closed since. Nothing older can be open: periods do not
    overlap (REQ-PIPE-134), and each closes when the next calendar
    period's window opens.
    """
    candidate = current_slot(slots, at)
    if candidate is None or not slots_mod.is_open(candidate, at):
        return None
    return candidate


def assign(dataset_id: str, supply_id: str, at: datetime,
            slots: Sequence[slots_mod.Slot],
            filled: frozenset[str]) -> Assignment:
    """File one supply, by rule, with no human in it.

    `at` is the RECEIPT instant, never when the supply is processed
    (REQ-PIPE-131 criterion 5): a file received inside a slot's open
    interval and processed after it closed is that slot's.

    `filled` is the set of slot names a supply has been PROMOTED into -
    never staged, never merely arrived, never rejected.

    A supply whose checks will report red is assigned on exactly the
    same terms as any other (REQ-PIPE-062 criterion 11).
    """
    asset_time.parse_instant(at, "assign(at)")
    found = open_slot(slots, at)
    if found is None:
        considered = current_slot(slots, at)
        return Assignment(
            dataset_id=dataset_id, supply_id=supply_id, received_at=at, slot=None,
            branch=HELD, considered=(considered.name,) if considered else (),
            unavailable=_why_unavailable(slots, at, filled))
    if found.name in filled:
        return Assignment(dataset_id=dataset_id, supply_id=supply_id, received_at=at,
                           slot=found.name, branch=RESUPPLY,
                           considered=(found.name,), resupply_of=found.name)
    return Assignment(dataset_id=dataset_id, supply_id=supply_id, received_at=at,
                       slot=found.name, branch=OPEN_UNFILLED, considered=(found.name,))


def _why_unavailable(slots: Sequence[slots_mod.Slot], at: datetime,
                      filled: frozenset[str]) -> tuple[tuple[str, str], ...]:
    """The slots either side of a held arrival, and why neither took it
    (REQ-PIPE-064 criterion 4).

    ONLY THE TWO THAT MATTER: the newest slot whose window had opened -
    closed - and the next one, whose window had not. Listing every slot
    a daily feed has ever had would bury them. Found by bisection, like
    the rule itself.
    """
    out: list[tuple[str, str]] = []
    index = _opened_by(slots, at)
    if index > 0:
        before = slots[index - 1]
        state = ("filled by a promoted supply, and " if before.name in filled else "")
        # NO INSTANT IN THE SENTENCE: a hold's reason is stored and shown
        # verbatim, and a raw ISO instant is the one thing REQ-DASH-071
        # says a reader never sees. The slot's own config says when.
        out.append((before.name,
                    f"{state}closed - the next period's claim window had opened"))
    if index < len(slots):
        out.append((slots[index].name,
                    "its claim window has not opened yet, and nothing may claim forward"))
    return tuple(out)
