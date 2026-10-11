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
from datetime import date

from qa_tools.common import agreement as agreement_mod

#: The values in the order a reader asks about them, with their labels.
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
    return View(dataset_id, on, not_yet=None, values=tuple(values))
