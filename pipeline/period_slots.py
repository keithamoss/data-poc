"""Each dataset's slots for the page - period, round and instants - so the
page never stands a period's date in for a round or a due date
(REQ-DASH-326 criterion 8, the architect's S3).

THE ANSWERS TRAVEL, NOT THE RULE: every value comes from the one
slot-instants function filing uses (qa_tools.common.slots). The page picks
the slot whose claim window most recently opened on the date on show
(criterion 5) and reads its period, round and due instant off it.

ONLY SLOTS WHOSE CLAIM WINDOW HAS OPENED BY NOW, so nothing in the future is
embedded - which is also every period an open or filed-to slot fills
(criterion 10): a supply can only be filed to an open slot.

ONLY FOR AN AUTHORED CALENDAR (criterion 3). A cadence-rule calendar keeps
its period-date headings and current cycle, so it gets nothing here, and the
page's existing path answers for it. CONFIGURATION ONLY - no database.
"""
from __future__ import annotations

from datetime import timedelta

from qa_tools.common import asset_time, files_go, schedule, slots


def _iso(instant) -> str | None:
    return instant.isoformat() if instant is not None else None


def for_dataset(dataset_id: str, now=None) -> dict | None:
    """{filesGo, slots: [{period, date, round, opens, due, closes}]}, oldest
    first, or None for a cadence-rule calendar or a dataset with none."""
    now = now or asset_time.now()
    today = asset_time.local_date(now)
    try:
        cal = schedule.calendar_for_dataset(dataset_id)
    except schedule.NoCalendarAgreed:
        return None
    if cal.version_in_force(today).is_cadence_rule:
        return None
    until = today + timedelta(days=400)
    agr = schedule._agreement(None)
    try:
        found = slots.slots_for_dataset(dataset_id, until=until)
        sequence = slots._calendar_periods(dataset_id, until, agr)
    except (schedule.ScheduleConfigError, schedule.NoCalendarAgreed):
        return None
    owed = {s.period.name: s for s in found}
    begins = found[0].round_date if found and found[0].round_date else None
    out = []
    # EVERY ROUND FROM THE FIRST OWED ONE, OWED OR NOT, so the current cycle
    # on a date can be a period the dataset owes nothing in (REQ-DASH-182
    # criterion 10): the round's own claim opening still marks when that
    # period is current. Each round names the period its files fill, as
    # pipeline/owed_nothing.py does.
    for i, rnd in enumerate(sequence):
        if begins is not None and rnd.date < begins:
            continue
        j = i + (agr.files_go_to_period_for(dataset_id, rnd.date) or 0)
        if j >= len(sequence):
            continue
        period = sequence[j]
        slot = owed.get(period.name)
        if slot is not None:
            opens, due, closes = slot.claim_opens_at, slot.due_at, slot.closes_at
        else:
            instants = slots.slot_instants(dataset_id, rnd.date, agr)
            opens, due, closes = instants.claim_opens_at, instants.due_at, None
        if opens > now:
            continue
        out.append({"period": period.name, "date": period.date.isoformat(),
                    "round": rnd.date.isoformat(), "owed": slot is not None,
                    "opens": _iso(opens), "due": _iso(due), "closes": _iso(closes)})
    # THE FIRST OWED SLOT, open or not, for 'Not owed yet — owes from
    # <period>, first due <instant>' (REQ-DASH-182 criterion 3 as amended).
    first = found[0] if found else None
    return {"filesGo": files_go.describe(dataset_id, today),
            "first": {"period": first.period.name, "due": _iso(first.due_at),
                      "opens": _iso(first.claim_opens_at)} if first else None,
            "slots": out}
