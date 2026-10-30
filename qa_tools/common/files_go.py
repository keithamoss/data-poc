"""Which period a collection's files go into, in words (REQ-DASH-326
criterion 7, REQ-PIPE-327 criterion 1).

ONE PHRASE FUNCTION FOR BOTH SURFACES. The dashboard's SLA tile line is
embedded from here by the build and the terminal prints the same string, so
the two cannot word the value differently. Shaped like amber_setting.describe
- the value, then where it was set and since when - with the round named by
its date, never by the period its date belongs to (REQ-PIPE-327 criterion 9).

CONFIGURATION ONLY: contract/calendar.yaml through the agreement.
"""
from __future__ import annotations

from datetime import date

from qa_tools.common import hierarchy, schedule


def value_words(value: int) -> str:
    """'Files go into the period they arrive in', '... the next period' or
    '... <N> periods ahead'."""
    if value == 0:
        return "Files go into the period they arrive in"
    if value == 1:
        return "Files go into the next period"
    return f"Files go {value} periods ahead"


def round_words(on: date) -> str:
    """'the 1 February 2015 round' - a round named by its date."""
    return f"the {on.day} {on.strftime('%B %Y')} round"


def _first_round_on_or_after(dataset_id: str, when: date, agr) -> date | None:
    from qa_tools.common import slots

    for period in slots._calendar_periods(dataset_id, None, agr):
        if period.date >= when:
            return period.date
    return None


def describe(dataset_id: str, on: date, agreement=None) -> str | None:
    """The value in force for `dataset_id` on the round dated `on`, with the
    collection it is stated on and the round its version took effect from -
    'Files go into the next period (set for Child Protection, since the 1
    February 2015 round)'. None where the dataset's calendar is a cadence
    rule (REQ-DASH-326 criterion 3) or no version is in force."""
    from qa_tools.common import in_force

    agr = schedule._agreement(agreement)
    try:
        cal = schedule.calendar_for_dataset(dataset_id, agr)
    except (schedule.NoCalendarAgreed, hierarchy.UnknownDatasetError):
        return None
    try:
        if cal.version_in_force(on).is_cadence_rule:
            return None
    except schedule.ScheduleConfigError:
        return None                   # before the calendar's first version
    collection_id = agr.collection_of(dataset_id)
    version = in_force.version_on(agr.offsets.get(collection_id, ()), on)
    if version is None:
        return None
    name = next((d.collection_name for d in hierarchy.all_datasets()
                 if d.collection_id == collection_id), None) or "its collection"
    first = _first_round_on_or_after(dataset_id, version.effective_from, agr)
    since = f", since {round_words(first)}" if first else ""
    return f"{value_words(version.value)} (set for {name}{since})"


def later_version(dataset_id: str, on: date, agreement=None) -> str | None:
    """The next version due after `on`, in words, for the terminal - 'from
    the 1 August 2026 round: Files go into the period they arrive in' - or
    None where none is authored (REQ-PIPE-327 criterion 1)."""
    agr = schedule._agreement(agreement)
    for version in agr.offsets.get(agr.collection_of(dataset_id), ()):
        if version.effective_from > on:
            first = _first_round_on_or_after(dataset_id, version.effective_from, agr)
            when = round_words(first) if first else version.effective_from.isoformat()
            return f"from {when}: {value_words(version.value)}"
    return None


# ---- The terminal's words for a supply and a slot (REQ-PIPE-327) -----------

def for_received(period: str, received_at) -> str:
    """'For 2026-Q2 · received <instant>' - the same wording as the
    dashboard's supply-history heading (REQ-PIPE-327 criterion 3)."""
    from qa_tools.common import display_time

    when = display_time.format_instant(received_at) if received_at is not None else "-"
    return f"For {period} · received {when}"


def for_due(period: str, due_at) -> str:
    """'For 2026-Q2 · due <instant>' - a slot named by the period it is for
    and its own due instant (REQ-PIPE-327 criterion 2)."""
    from qa_tools.common import display_time

    return f"For {period} · due {display_time.format_instant(due_at)}"


def held_words(held) -> str:
    """Which kind of held (REQ-PIPE-327 criteria 3 and 6): 'Held, would be a
    second supply for <period> - agreement change from the <day> round',
    'Held, would be for <period>' where only a person stands between it and
    one period, else 'Held, no period yet'."""
    fed = getattr(held, "doubly_fed", None)
    if fed:
        when = date.fromisoformat(str(fed.get("from_round") or fed["round"])[:10])
        return (f"Held, would be a second supply for {fed['period']} - agreement change "
                f"from {round_words(when)}")
    reason = getattr(held, "reason", None) or {}
    unavailable = [p for p in (reason.get("unavailable") or []) if p]
    periods = {p[0] for p in unavailable}
    if len(periods) == 1:
        return f"Held, would be for {next(iter(periods))}"
    return "Held, no period yet"


def rounds_fill(dataset_id: str, months, on: date, agreement=None) -> str | None:
    """'rounds whose files go into Q2 and Q4' for a participates line, where
    the collection's value is not 0 (REQ-PIPE-327 criterion 8), else None."""
    from qa_tools.common import slots

    agr = schedule._agreement(agreement)
    value = agr.files_go_to_period_for(dataset_id, on) or 0
    if not value or not months:
        return None
    sequence = slots._calendar_periods(dataset_id, None, agr)
    names = []
    for i, rnd in enumerate(sequence):
        if rnd.date < on or rnd.date.month not in months or i + value >= len(sequence):
            continue
        tail = sequence[i + value].name.split("-")[-1]
        if tail not in names:
            names.append(tail)
        if len(names) == len(months):
            break
    if not names:
        return None
    said = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"rounds whose files go into {said}"


def fall_rounds(dataset_id: str, agreement=None) -> list[tuple[date, str]]:
    """[(round date, doubly-fed period)] for every round whose files would
    fill a period an earlier round already filled - a fall in the value
    (REQ-PIPE-322 criterion 3, REQ-PIPE-327 criterion 7)."""
    from qa_tools.common import slots

    agr = schedule._agreement(agreement)
    # A CADENCE RULE HAS NO END to walk, and no files_go_to_period other
    # than its collection's: only an authored calendar's rounds are listed.
    try:
        sequence = slots._calendar_periods(dataset_id, None, agr)
    except schedule.ScheduleConfigError:
        return []
    out, furthest = [], -1
    for i, rnd in enumerate(sequence):
        value = agr.files_go_to_period_for(dataset_id, rnd.date)
        if value is None:
            continue
        j = i + value
        if j <= furthest and j < len(sequence):
            out.append((rnd.date, sequence[j].name))
        furthest = max(furthest, j)
    return out
