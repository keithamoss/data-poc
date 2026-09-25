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
HELD = "held-nothing-confidently-claimable"
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
    #: An assignment the rule made but could not be sure of
    #: (REQ-PIPE-065 criterion 1): it took the oldest claimable
    #: unfilled slot while an EARLIER slot for the same dataset was
    #: also unfilled, so the supply might have been for that one. It
    #: defaults BACKWARD because late is commoner than early, and says
    #: so rather than presenting the guess as certain.
    ambiguous: bool = False
    ambiguity: str | None = None
    #: For a HELD supply: why each slot it looked at was unavailable
    #: (REQ-PIPE-064 criterion 4). A hold that says only "no slot"
    #: tells a person nothing they can act on, and acting on it is the
    #: entire point - the resolution is a human assigning it.
    unavailable: tuple[tuple[str, str], ...] = ()

    @property
    def is_resupply(self) -> bool:
        return self.branch == RESUPPLY

    @property
    def is_held(self) -> bool:
        return self.branch == HELD

    def describe(self) -> str:
        """Why this supply is where it is, in words.

        For a hold this is the whole deliverable: criterion 4 asks it
        to name the slots it considered AND why each was unavailable,
        because the resolution is a person choosing one.
        """
        if not self.is_held:
            return f"{self.supply_id} -> {self.slot} ({self.branch})"
        reasons = "; ".join(f"{name}: {why}" for name, why in self.unavailable)
        return (f"{self.supply_id} could not be placed - {reasons or 'no slot was open'}. "
                f"It stays staged and is not checked until somebody assigns it.")

    def as_record(self) -> dict:
        return {"dataset_id": self.dataset_id, "supply_id": self.supply_id,
                "slot": self.slot, "branch": self.branch,
                "considered": list(self.considered), "resupply_of": self.resupply_of,
                "unavailable": [list(pair) for pair in self.unavailable],
                "ambiguous": self.ambiguous, "ambiguity": self.ambiguity}


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


def closed_by_monotonic_filling(slots: Sequence[slots_mod.Slot],
                                 filled: frozenset[str]) -> frozenset[str]:
    """Slots that may no longer be claimed because a LATER one is
    filled (REQ-PIPE-063).

    THE FAILURE THIS PREVENTS IS WORSE THAN A CASCADE, because it
    manufactures a delivery that never happened. Tuesday is missed
    entirely; Wednesday 22:00 arrives, is promoted, and fills
    Wednesday; Wednesday 23:00 a RESUPPLY of Wednesday arrives.
    Without this rule the oldest claimable unfilled slot is TUESDAY, so
    a Wednesday resupply files as Tuesday one day late - and a service
    failure is erased using another day's data. The resupply branch
    never fires to stop it, because an outstanding missed slot means a
    claimable unfilled one exists.

    ASKED, NEVER RECORDED. The answer changes as later slots fill, so a
    stored flag would be wrong from the moment the next promotion
    lands - the same reasoning REQ-PIPE-052 applied to overdue.

    GENUINE LATENESS SURVIVES: Monday's supply landing Tuesday 03:00
    finds Tuesday unfilled with nothing later filled, so Tuesday is
    still open. And consecutive slots filled late in sequence each
    fill, so a feed running behind reads as running behind rather than
    as a run of missing slots.
    """
    if not filled:
        return frozenset()
    last_filled = max((i for i, s in enumerate(slots) if s.name in filled), default=-1)
    return frozenset(s.name for s in slots[:last_filled] if s.name not in filled)


def oldest_claimable_unfilled(slots: Sequence[slots_mod.Slot], at: datetime,
                               filled: frozenset[str],
                               closed: frozenset[str] = frozenset()) -> slots_mod.Slot | None:
    """The oldest slot whose window is open, which is unfilled, and
    which monotonic filling has not closed.

    Stops at the first hit. With monotonic filling the filled slots and
    the closed ones together form a prefix, so this is the slot just
    after it.
    """
    for slot in slots:
        if slot.name in filled or slot.name in closed:
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

    # 2. OLDEST CLAIMABLE UNFILLED, minus anything monotonic filling
    #    has closed (REQ-PIPE-063). Lateness still works.
    closed = closed_by_monotonic_filling(slots, filled)
    oldest = oldest_claimable_unfilled(slots, at, filled, closed)
    if oldest is not None:
        if oldest.name not in considered:
            considered.append(oldest.name)
        # MARKED WHERE IT CANNOT BE SURE (REQ-PIPE-065 criterion 1). An
        # arrival while a PRIOR slot is also unfilled cannot be told
        # apart from a late one by any rule, so it defaults backward -
        # late is commoner than early - and says that it guessed. The
        # alternative is presenting a guess as certain, which is a
        # false-confidence problem rather than a missing nicety.
        earlier = [s.name for s in slots
                    if s.name != oldest.name and s.due_at < oldest.due_at
                    and s.name not in filled]
        return Assignment(dataset_id=dataset_id, supply_id=supply_id,
                           slot=oldest.name, branch=OLDEST_CLAIMABLE,
                           considered=tuple(considered),
                           ambiguous=bool(earlier),
                           ambiguity=(
                               f"filed to {oldest.name}, but {', '.join(earlier)} "
                               f"{'is' if len(earlier) == 1 else 'are'} also unfilled - a late "
                               f"supply and an early one look identical here, so this defaulted "
                               f"backward and needs review" if earlier else None))

    # 3. A RESUPPLY of the most recently filled slot - but only where
    #    that slot is the one the arrival is actually IN. This is the
    #    Wednesday 23:00 case the monotonic-filling decision traces:
    #    Wednesday is filled and current, so a second Wednesday file is
    #    confidently a Wednesday resupply.
    latest = most_recently_filled(slots, filled)
    if latest is not None and current is not None and latest.name == current.name:
        if latest.name not in considered:
            considered.append(latest.name)
        return Assignment(dataset_id=dataset_id, supply_id=supply_id,
                           slot=latest.name, branch=RESUPPLY,
                           considered=tuple(considered), resupply_of=latest.name)

    # 4. HELD FOR A HUMAN (criterion 6). The arrival could only go in a
    #    slot monotonic filling has closed, and Thread H names the
    #    answer: "when nothing is confidently claimable, hold it for a
    #    human and let them decide where it is filed."
    #
    #    THIS IS THE NAMED LIMIT OF THE RULE, not a gap in it. Once a
    #    delivery is skipped AND a later one has landed, a genuine
    #    backfill of the older slot cannot be placed by ANY rule - it is
    #    not claimable, and defaulting it into a future slot is the
    #    forward cascade again. Keith: "I think we can't design around
    #    that." Guessing here is what turns a service failure into a met
    #    obligation, which this requirement rates worse than a cascade
    #    because it manufactures a delivery that never happened.
    if closed:
        return Assignment(
            dataset_id=dataset_id, supply_id=supply_id, slot=None, branch=HELD,
            considered=tuple(considered) or tuple(sorted(closed)),
            unavailable=_why_unavailable(slots, at, filled, closed))

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
                       branch=UNASSIGNABLE, considered=tuple(considered),
                       unavailable=_why_unavailable(slots, at, filled, closed))


def _why_unavailable(slots: Sequence[slots_mod.Slot], at: datetime,
                      filled: frozenset[str],
                      closed: frozenset[str]) -> tuple[tuple[str, str], ...]:
    """Each slot this arrival could have gone in, and why it could not
    (REQ-PIPE-064 criterion 4).

    A HOLD THAT SAYS ONLY "no slot" IS NOT ACTIONABLE, and acting on it
    is the entire point - the resolution is a person assigning the
    supply to a slot, which they cannot do without knowing what was
    ruled out and on what grounds.

    Only slots near the arrival are named. Listing every slot a daily
    feed has ever had would bury the three that matter, which is the
    same reasoning that keeps holds aggregated rather than one banner
    per dataset.
    """
    out: list[tuple[str, str]] = []
    for slot in slots:
        if slot.name in filled:
            why = "already filled by a promoted supply"
        elif slot.name in closed:
            why = "closed - a later slot has been filled, so this one can no longer be claimed"
        elif not slots_mod.is_claimable(slot, at):
            why = "its claim window has not opened yet, and nothing may claim forward"
        else:
            continue
        out.append((slot.name, why))
    # Nearest first: the slots around the arrival are the ones a person
    # is choosing between.
    return tuple(out[-6:])
