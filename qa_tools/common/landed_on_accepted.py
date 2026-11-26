"""A supply that arrived for a slot we had already accepted
(REQ-PIPE-065).

THE TRIGGER IS STRUCTURAL, and keeping it that way is the whole design.
The slot had been PROMOTED into, and something arrived for it anyway.
There is nothing to configure and nothing to tune. The version this
replaced needed a "within X of the window opening" threshold, and any
such X is arbitrary - with a case just outside it slipping through in
silence, which is the failure mode a threshold always has.

PROXIMITY SURVIVES AS THE EXPLANATION, NEVER AS THE TRIGGER (criteria 4
and 5). Same condition, different diagnosis:

    a supply arrived for Monday, which was already accepted at 16:00.
    It landed 3 minutes before Tuesday's window opened - it may belong
    to Tuesday.

versus the same sentence without the second half where there is no
proximity to report.

THE DISTINCTION A BOUNDARY RULE COULD NOT DRAW, and the reason
criterion 6 exists: a resupply after REJECTION is the expected repair
path - routine, silent, and the slot was never filled. A resupply after
ACCEPTANCE means we had already accepted something for this period,
which is odd and gets reported. Reporting both would make the report
wallpaper; reporting neither would let an accidental duplicate replace
accepted data unseen.

A WARNING, NEVER AN ERROR, because one legitimate case remains: a
supplier realises the extract they sent was wrong - wrong period, wrong
filter - even though it passed every check. Data can be clean and still
be wrong, and that is the limit of any check suite.

IT NEVER AUTO-PROMOTES (criterion 9). Whatever the new supply's own
status, a supply landing in a slot already filled by a promoted one
does not replace it automatically. Without that, a supplier's
accidental duplicate send silently supersedes data already accepted,
and the only trace is a superseded table nobody looked at. Filling an
empty slot is routine; replacing accepted data is a decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from qa_tools.common import display_time

#: How close to an adjacent window counts as worth MENTIONING. This is
#: not a trigger and must never become one - it only decides whether
#: the explanation carries its second sentence, so a value slightly off
#: changes the wording of a report that fires either way.
_WORTH_MENTIONING = timedelta(hours=1)

#: The three things a person can do about it (criterion 7). Named in
#: the report itself, because a warning that does not say what the
#: responses are is one somebody has to go and ask about.
RESPONSES = (
    "accept it as a correction to what was already promoted",
    "re-file it to another slot",
    "reject it as a duplicate",
)


@dataclass(frozen=True)
class LandedOnAccepted:
    """One supply that arrived for an already-accepted slot."""

    dataset_id: str
    supply_id: str
    slot: str
    arrived_at: datetime
    accepted_at: datetime
    near_window: str | None = None
    near_by: timedelta | None = None

    def describe(self) -> str:
        when = display_time.format_instant(self.accepted_at)
        out = (f"A supply arrived for {self.slot}, which was already accepted at {when}.")
        if self.near_window is not None and self.near_by is not None:
            minutes = int(abs(self.near_by).total_seconds() // 60)
            out += (f" It landed {minutes} minute(s) before {self.near_window}'s window "
                     f"opened - it may belong to {self.near_window}.")
        out += " You can " + "; ".join(RESPONSES) + "."
        return out


def report(dataset_id: str, supply_id: str, slot: str, arrived_at: datetime,
            promoted_slots: dict[str, datetime],
            next_window_opens: datetime | None = None,
            next_slot: str | None = None) -> LandedOnAccepted | None:
    """Report this arrival, or None where there is nothing odd about it.

    `promoted_slots` maps a slot name to when its supply was ACCEPTED -
    promoted, not merely staged or arrived. A slot absent from it was
    never filled, so an arrival for it is the ordinary repair path and
    stays silent (criterion 6).
    """
    accepted_at = promoted_slots.get(slot)
    if accepted_at is None:
        return None

    near_window, near_by = None, None
    if next_window_opens is not None and next_slot is not None:
        gap = next_window_opens - arrived_at
        # Only a gap BEFORE the window opens is worth mentioning: after
        # it opens, the arrival could have claimed that slot and did
        # not, which says something different.
        if timedelta(0) <= gap <= _WORTH_MENTIONING:
            near_window, near_by = next_slot, gap

    return LandedOnAccepted(
        dataset_id=dataset_id, supply_id=supply_id, slot=slot, arrived_at=arrived_at,
        accepted_at=accepted_at, near_window=near_window, near_by=near_by)


def may_auto_promote(slot: str, promoted_slots: dict[str, datetime]) -> bool:
    """Criterion 9, as a question anything promoting has to ask.

    A supply landing in a slot already filled by a promoted supply
    NEVER auto-promotes, whatever its own status. This exists as a
    function rather than as prose inside a sprint-11 requirement
    because that is exactly how the rule went missing once already - an
    IOU written against work that does not exist, appearing in the
    register only in the deferral itself.
    """
    return slot not in promoted_slots
