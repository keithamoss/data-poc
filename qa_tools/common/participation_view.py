"""What each participation value of a dataset resolves to on a date, and
where it came from (REQ-PIPE-181 criteria 13-15).

One view, for the one renderer `mothman schedule show --on` and the
terminal's Calendar entry share (cli/schedule.py `_show_values`), over the
one resolution function (agreement.resolve) - so neither can describe a
value the way the other does not.

Configuration only: the agreement, never data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from qa_tools.common import agreement as agreement_mod

#: The values in the order a reader asks about them, with their labels.
_ONE_DAY = timedelta(days=1)
LABELS = (("participates", "Owes"), ("expected_time", "Due time"), ("grace", "Grace"),
          ("days_before", "Days before"), ("claim_window", "Claim window"))


@dataclass(frozen=True)
class Value:
    label: str
    text: str
    #: Where it came from, in words that name the level.
    source: str
    #: "<date>: <text>" where a level above changes it later, else None.
    changes: str | None = None


@dataclass(frozen=True)
class View:
    dataset_id: str
    on: date
    #: Set instead of values where the date is before the first version.
    not_yet: date | None
    values: tuple[Value, ...] = ()
    #: 'Turned off - nothing due' or 'Turning off after <date> - nothing more
    #: owed' (REQ-PIPE-179 criterion 29), or None.
    headline: str | None = None
    #: What a turn-off means for it (REQ-PIPE-179 criterion 28), in order.
    turn_off: tuple[str, ...] = ()


def _day(d) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


def _turn_off_for(dataset_id: str, on: date, agr):
    """(the turn-off that matters on `on` - the one in force, else the next
    one ahead - and the standing on `on`), or (None, standing)."""
    standing = agr.standing_on(dataset_id, on)
    if standing.turned_off is not None:
        return standing.turned_off, standing
    entry = agr.dataset(dataset_id)
    ahead = []
    for level, versions in ((agreement_mod.DATASET, entry.participation),
                            (agreement_mod.COLLECTION, agr.defaults_for(dataset_id))):
        for v in versions:
            if v.effective_to is not None and v.effective_to >= on:
                probe = agr.standing_on(dataset_id, v.effective_to + _ONE_DAY)
                if probe.turned_off is not None:
                    ahead.append(probe.turned_off)
    return (min(ahead, key=lambda t: t.effective_to) if ahead else None), standing


def _turn_off_lines(dataset_id: str, on: date,
                    agr) -> tuple[str | None, tuple[str, ...], bool]:
    """REQ-PIPE-179 criteria 28 and 29 - from configuration alone. The third
    value says whether an owed slot is still open on the date."""
    from qa_tools.common import agreement_freeze, asset_time, slots, turned_off

    if not agr.ever_turned_off(dataset_id):
        return None, (), False
    turn, standing = _turn_off_for(dataset_id, on, agr)
    lines: list[str] = []
    if standing.brought_back:
        # NAMING THE GAP IT CAME BACK INSIDE (post-build-review #190 D9b).
        from qa_tools.common import in_force

        mine = in_force.version_on(agr.dataset(dataset_id).participation, on)
        above = in_force.version_on(agr.defaults_for(dataset_id), on)
        lines.append(f"Back on by a version of its own from {_day(mine.effective_from)}, "
                     f"inside {_collection(dataset_id)}'s turned-off gap (turned off after "
                     f"{_day(above.effective_to)}, {above.turned_off_reason or 'no reason given'}).")
    if turn is None:
        return None, tuple(lines), False
    lines.append(f"Turned off after {_day(turn.effective_to)} ({turn.reason}), "
                 f"{turned_off.level_words(turn, dataset_id)}"
                 + (f", until {_day(turn.until)}." if turn.until else " - for good."))
    start = asset_time.start_of_day(on)
    try:
        owed = slots.slots_for_dataset(dataset_id, until=turn.effective_to, agreement=agr)
    except Exception:  # noqa: BLE001 - a schedule that cannot be built shows nothing owed
        owed = []
    still = [s for s in owed if s.date <= turn.effective_to
             and (s.closes_at is None or s.closes_at > start)]
    for s in still:
        lines.append(f"Still owes {s.name}: its slot stays open until "
                     f"{asset_time.localise(s.closes_at).strftime('%-d %b %Y %H:%M')}."
                     if s.closes_at else f"Still owes {s.name}.")
    try:
        sequence = slots._calendar_periods(dataset_id, (turn.until or turn.effective_to)
                                           + _ONE_DAY * 400, agr)
    except Exception:  # noqa: BLE001
        sequence = []
    gap = [p for p in sequence if p.date > turn.effective_to
           and (turn.until is None or p.date < turn.until)]
    if gap and turn.until is not None:
        lines.append(f"Owes nothing in {gap[0].name} to {gap[-1].name}." if len(gap) > 1
                     else f"Owes nothing in {gap[0].name}.")
    elif gap:
        lines.append(f"Owes nothing from {gap[0].name} on - the turn-off is permanent.")
    else:
        lines.append("Owes nothing after it - the turn-off is permanent."
                     if turn.until is None else "")
    if gap:
        opens = agreement_freeze._claim_open(dataset_id, gap[0].date, agr)
        if opens is not None:
            when = asset_time.localise(opens).strftime('%-d %b %Y %H:%M')
            # REQ-PIPE-179 c28 as amended by Keith, 2026-10-15 (morning report
            # 5 Q10): "ordinary edit" read unclearly; say which file.
            lines.append(f"Edit calendar.yaml to change this until {when}, when the first "
                         f"period's claim window opens. After that it needs a declared "
                         f"correction." if opens > start else
                         f"A declared correction is needed to change it - {gap[0].name}'s "
                         f"claim window opened {when}.")
    headline = None
    if standing.state == agreement_mod.TURNED_OFF and not still:
        headline = "Turned off - nothing due"
    elif (standing.state == agreement_mod.OWING and not still and turn.effective_to >= on
          and _authored_by(dataset_id, turn.effective_to, on, agr)):
        # ONLY ONCE IT IS WRITTEN DOWN (post-build-review #199 F12, Keith
        # 2026-10-15): one meaning across surfaces - the page's marker waits
        # for the authored date too (REQ-DASH-180 criterion 25).
        headline = f"Turning off after {_day(turn.effective_to)} - nothing more owed"
    return headline, tuple(x for x in lines if x), bool(still)


def _authored_by(dataset_id: str, effective_to: date, on: date, agr) -> bool:
    """Whether the turn-off ending `effective_to` was authored on or before
    `on` - the date its changelog or a correction records, as the page reads
    it (turned_off.timeline's authoredOn). None authored is not yet."""
    from qa_tools.common import turned_off

    return any(t["effectiveTo"] == effective_to.isoformat() and t.get("authoredOn")
               and t["authoredOn"] <= on.isoformat()
               for t in turned_off.timeline(dataset_id, agr))


def _collection(dataset_id: str) -> str:
    from qa_tools.common import hierarchy

    return hierarchy.dataset(dataset_id).collection_name


def _text(key: str, version, dataset_id: str, on: date, agr) -> str:
    from qa_tools.common import schedule

    value = getattr(version, key)
    if key == "participates":
        if value is None:
            return "every period"
        months = ", ".join(schedule.MONTH_NAMES[m - 1] for m in value)
        return months + (f" - {version.reason}" if version.reason else "")
    if key in ("grace", "claim_window"):
        if value is None:
            if key == "claim_window":
                return schedule.format_duration(
                    schedule.claim_window(dataset_id, on=on, agreement=agr))
            return "none"
        return schedule.format_duration(value)
    if key == "days_before":
        return str(value)
    return value or "none"


def _fallback(key: str) -> str:
    return {"participates": " - so every period is owed",
            "days_before": " - so none",
            "expected_time": " - so its periods have no due instant",
            "grace": " - so its periods have no due instant"}.get(key, "")


def view(dataset_id: str, on: date, agreement=None) -> View:
    from qa_tools.common import hierarchy, schedule

    agr = schedule._agreement(agreement)
    entry = agr.dataset(dataset_id)
    resolved = agr.participation_on(dataset_id, on)
    if resolved is None:
        first = entry.participation[0].effective_from if entry and entry.participation else None
        return View(dataset_id, on, not_yet=first)
    name = hierarchy.dataset(dataset_id).collection_name
    cal_name = agr.calendar_name_for(dataset_id)
    later = [d.effective_from for d in agr.defaults_for(dataset_id) if d.effective_from > on]
    cal = schedule.calendar_for_dataset(dataset_id, agr)
    cal_later = [v.effective_from for v in cal.versions if v.effective_from > on]
    values = []
    for key, label in LABELS:
        source = resolved.sources.get(key, (agreement_mod.FALLBACK, None))
        if key == "claim_window" and source[0] == agreement_mod.FALLBACK:
            # THE CALENDAR IS A LEVEL TOO (delivery-critic on 181, F7): its
            # version's date, and a later version changing the window.
            source = (agreement_mod.FALLBACK, schedule._version_in_force(cal, on).effective_from)
        words = agreement_mod.describe_source(source, collection_name=name,
                                              calendar_name=cal_name, key=key)
        if words == "no level states this":
            words += _fallback(key)
        text = _text(key, resolved, dataset_id, on, agr)
        changes = None
        if source[0] == agreement_mod.COLLECTION:
            for when in later:
                then = agr.participation_on(dataset_id, when)
                if then is None or then.sources.get(key, (None,))[0] != agreement_mod.COLLECTION:
                    break
                new = _text(key, then, dataset_id, when, agr)
                if new != text:
                    changes = f"{when.day} {when.strftime('%b %Y')}: {new}"
                    break
        elif key == "claim_window" and source[0] == agreement_mod.FALLBACK:
            for when in cal_later:
                then = agr.participation_on(dataset_id, when)
                if then is None or then.claim_window is not None:
                    break
                new = _text(key, then, dataset_id, when, agr)
                if new != text:
                    changes = f"{when.day} {when.strftime('%b %Y')}: {new}"
                    break
        values.append(Value(label, text, words, changes))
    headline, lines, still_open = _turn_off_lines(dataset_id, on, agr)
    if agr.standing_on(dataset_id, on).state == agreement_mod.TURNED_OFF and not still_open:
        # NOTHING IS OWED, and its timing is its last version's, said so
        # (REQ-PIPE-179 criterion 29) - only once no owed slot is still open
        # (post-build-review #190 D9a): until then it is still owing.
        values = [Value(x.label, "nothing - turned off", x.source) if x.label == "Owes"
                  else Value(x.label + " (when last on)", x.text, x.source, x.changes)
                  if x.label in ("Due time", "Grace") else x for x in values]
    return View(dataset_id, on, not_yet=None, values=tuple(values), headline=headline,
                turn_off=lines)
