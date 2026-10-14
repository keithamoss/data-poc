"""What a supply's receipt falls in, for a dataset that may be turned off
(REQ-PIPE-179 criteria 14-19).

ONE QUESTION, ASKED AT FILING AND AGAIN WHENEVER A HOLD IS READ. Where no
owed slot is open at a supply's receipt instant, which calendar period's
slot would then be current - every input resolved as if each effective_to
were absent (criterion 14) - and is the dataset turned off in it? If so,
the supply is held as TURNED OFF (criterion 16), which outranks SCHEDULE
ENDED (criterion 17).

THE LABEL IS WORKED OUT FROM THE CONFIGURATION AS IT STANDS WHEN READ
(criterion 18), never from the reason recorded when the hold was raised:
a turn-off moved or removed since changes what the hold is, and a label
frozen at raising would offer the wrong fix. The recorded reason stays as
history only.

NO FALSE QUIET (the requirement's line): a receipt an owed slot still
covers is that slot's, late or as a resupply, whether or not the dataset
is turned off on the receipt's date (criterion 15) - the last owed slot
before a gap closes only when the gap's first period would have opened.
Config only; no supply rows.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime

from qa_tools.common import agreement as agreement_mod

#: The three labels a held supply carries (criterion 18).
TURNED_OFF = "turned off"
SCHEDULE_ENDED = "schedule ended"
PLAIN = "held"


@dataclass(frozen=True)
class Label:
    """A held supply's label, from configuration as it stands."""

    label: str
    #: For TURNED_OFF: why, at which level, and the gap.
    turned_off: agreement_mod.TurnOff | None = None
    #: For SCHEDULE_ENDED: the calendar's last period.
    last_period: str | None = None
    #: The owed slot now open at the receipt, where there is one - which
    #: the next processing pass files it to (criterion 19).
    covered_by: str | None = None


def gap_at(dataset_id: str, at: datetime, agreement=None) -> agreement_mod.TurnOff | None:
    """The turn-off of the calendar period whose slot would be current at
    `at` (criterion 16), or None where that period is owed, or there is none.

    BY BISECTION over the calendar's own periods (REQ-PIPE-131 NFR 1), each
    period's claim-opening instant from the one slot-instants function,
    which resolves a turned-off period's inputs as criterion 14 says."""
    from qa_tools.common import schedule, slots

    agr = schedule._agreement(agreement)
    if not agr.ever_turned_off(dataset_id):
        return None
    try:
        sequence = slots._calendar_periods(
            dataset_id, slots.claimable_until(dataset_id, at.date(), agr), agr)
    except schedule.NoCalendarAgreed:
        return None
    index = bisect.bisect_right(
        sequence, at, key=lambda p: slots.slot_instants(dataset_id, p.date, agr).claim_opens_at) - 1
    if index < 0:
        return None
    standing = agr.standing_on(dataset_id, sequence[index].date)
    return standing.turned_off if standing.state == agreement_mod.TURNED_OFF else None


def label_at(dataset_id: str, at: datetime, agreement=None) -> Label:
    """What a supply received at `at` would be held as now - covered by an
    owed slot, turned off, schedule ended, or the plain hold."""
    from qa_tools.common import assignment, schedule, slots

    agr = schedule._agreement(agreement)
    try:
        found = slots.slots_for_dataset(
            dataset_id, until=slots.claimable_until(dataset_id, at.date(), agr), agreement=agr)
    except schedule.NoCalendarAgreed:
        return Label(PLAIN)
    slot = assignment.open_slot(found, at)
    if slot is not None:
        return Label(PLAIN, covered_by=slot.name)
    turn = gap_at(dataset_id, at, agr)
    if turn is not None:
        return Label(TURNED_OFF, turned_off=turn)
    final = final_period(dataset_id, agr)
    if assignment.schedule_ended(found, at, final_period=final):
        return Label(SCHEDULE_ENDED, last_period=final)
    return Label(PLAIN)


def final_period(dataset_id: str, agreement=None) -> str | None:
    """The dataset's last owed period, or None where its calendar never runs
    out - filing.final_period_for, for a given agreement."""
    from qa_tools.common import schedule

    try:
        if schedule.calendar_for_dataset(dataset_id, agreement).current.is_cadence_rule:
            return None
    except schedule.NoCalendarAgreed:
        return None
    owed = [p for p in schedule.periods_for_dataset(dataset_id, agreement=agreement) if p.expected]
    return owed[-1].period.name if owed else None


def level_words(turn: agreement_mod.TurnOff, dataset_id: str) -> str:
    """Who it was set for, in the names a reader knows - 'set for Child
    Protection', 'set for Client Register'."""
    from qa_tools.common import hierarchy

    try:
        entry = hierarchy.dataset(dataset_id)
    except hierarchy.UnknownDatasetError:
        return f"set for {dataset_id}"
    if turn.level == agreement_mod.COLLECTION:
        return f"set for {entry.collection_name}"
    return f"set for {entry.dataset_name}"


def as_record(turn: agreement_mod.TurnOff) -> dict:
    """The structured reason a turned-off hold records as history
    (criterion 16) - the effective_to, the turned_off_reason, the level."""
    return {"effective_to": turn.effective_to.isoformat(), "reason": turn.reason,
            "level": turn.level, "version_from": turn.version_from.isoformat()}


def gap_for_period(dataset_id: str, period: str, agreement=None) -> agreement_mod.TurnOff | None:
    """The turn-off a calendar period of this dataset falls inside, or None
    where the period is owed, not yet owing, or not the calendar's."""
    from qa_tools.common import asset_time, schedule, slots

    agr = schedule._agreement(agreement)
    if not agr.ever_turned_off(dataset_id):
        return None
    horizon = asset_time.local_date(asset_time.now())
    horizon = horizon.replace(year=horizon.year + slots.SLOT_LOOKUP_YEARS)
    try:
        sequence = slots._calendar_periods(dataset_id, horizon, agr)
    except schedule.NoCalendarAgreed:
        return None
    found = next((p for p in sequence if p.name == period), None)
    if found is None:
        return None
    standing = agr.standing_on(dataset_id, found.date)
    return standing.turned_off if standing.state == agreement_mod.TURNED_OFF else None


def gap_words(turn: agreement_mod.TurnOff, dataset_id: str) -> str:
    """The gap in words - 'turned off after 31 March 2025 until 1 January
    2026 (supplier paused, set for Client Register)'."""
    until = (f"until {_day(turn.until)}" if turn.until else "for good")
    return (f"turned off after {_day(turn.effective_to)}, {until} ({turn.reason}, "
            f"{level_words(turn, dataset_id)})")


def _day(d) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def refusal(dataset_id: str, period: str, agreement=None) -> str | None:
    """THE ONE REFUSAL for naming a period inside a turned-off gap - a
    placement, a re-file, a confirmed correction's move, a parked move
    (REQ-PIPE-179 criterion 20). None where the period is not in a gap."""
    turn = gap_for_period(dataset_id, period, agreement)
    if turn is None:
        return None
    from qa_tools.common import supply_holds

    return (f"{dataset_id} owes nothing in {period}: it is {gap_words(turn, dataset_id)}. "
            f"Nothing was recorded. A period becomes owed by changing effective_to or "
            f"effective_from in {supply_holds.SCHEDULE_FILE}.")
