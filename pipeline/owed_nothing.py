"""Every period a dataset owes nothing in, and the delivery time in force on
each date, for the dashboard (REQ-DASH-182).

THE ANSWERS TRAVEL, NOT THE RULE - the decision pipeline/slot_timeline.py
and pipeline/closed_slots.py record. Whether a period is owed is
REQ-PIPE-110's, REQ-PIPE-179's and REQ-PIPE-181's to decide, through
schedule and agreement; this lists each period that is NOT owed with its
kind and reason, and each participation version's resolved timing, and the
page only compares their dates with the date on show.

CONFIGURATION ONLY (criterion 5): contract/calendar.yaml through the one
resolution function. Nothing here reads a database.
"""
from __future__ import annotations

from datetime import date

from qa_tools.common import agreement as agreement_mod
from qa_tools.common import schedule, slots

#: The three kinds of period a dataset owes nothing in (criterion 2). The
#: page words each; the build only names it.
PARTICIPATION, NOT_EXPECTED, TURNED_OFF = "participation", "not_expected", "turned_off"


def for_dataset(dataset_id: str, until: date, agreement=None) -> list[dict]:
    """[{period, date, kind, reason, months}] for every calendar period up to
    `until` that this dataset owes nothing in, oldest first.

    NOT BEFORE THE FIRST PARTICIPATION VERSION (criterion 6): a period
    before a dataset owes anything is not yet owing, which the SLA tile and
    the empty-dataset notice say instead (criterion 3).
    """
    agr = schedule._agreement(agreement)
    begins = schedule.owes_from(dataset_id, agr)
    skipped = schedule.not_expected_periods(dataset_id, agr)
    own_dates = schedule.dataset_dates_override(dataset_id, agr) is not None
    out: list[dict] = []
    for period in slots._calendar_periods(dataset_id, until, agr):
        if period.date > until or (begins is not None and period.date < begins):
            continue
        row = {"period": period.name, "date": period.date.isoformat()}
        standing = agr.standing_on(dataset_id, period.date)
        if standing.state == agreement_mod.TURNED_OFF:
            out.append({**row, "kind": TURNED_OFF, "reason": standing.turned_off.reason,
                        "months": None})
            continue
        months = None if own_dates else schedule.delivery_months(dataset_id, period.date, agr)
        if months is not None and period.date.month not in months:
            version = agr.participation_on(dataset_id, period.date)
            out.append({**row, "kind": PARTICIPATION, "reason": (version.reason or "").strip(),
                        "months": sorted(months)})
        elif period.name in skipped:
            out.append({**row, "kind": NOT_EXPECTED, "reason": skipped[period.name],
                        "months": None})
    return out


def sla_timeline(dataset_id: str, agreement=None) -> dict:
    """{owesFrom, versions: [{from, cadence, reason}]} - the delivery time in
    force from each participation version's date (criteria 3, 7, 8, 11).

    Each `cadence` has the shape agreement.cadence() gives the page, with
    the DATASET'S OWN months in place of its calendar's (criterion 11) and
    each value resolved from the level REQ-PIPE-181 says. `reason` is the
    authored reason only while the dataset owes fewer periods than its
    calendar has, for the tile's muted second line.
    """
    agr = schedule._agreement(agreement)
    base = agreement_mod.cadence(dataset_id, agr)
    begins = schedule.owes_from(dataset_id, agr)
    versions = []
    for version in agr.resolved_versions(dataset_id):
        cadence = {k: v for k, v in base.items()
                   if k not in ("expected_time", "latency_minutes", "days_before")}
        partial = False
        if "anchor_months" in base and version.participates is not None:
            own = sorted(m for m in base["anchor_months"] if m in version.participates)
            partial = own != base["anchor_months"]
            cadence["anchor_months"] = own
        cadence["expected_time"] = version.expected_time
        cadence["latency_minutes"] = int(version.grace.total_seconds() // 60)
        if version.days_before:
            cadence["days_before"] = version.days_before
        versions.append({"from": version.effective_from.isoformat(), "cadence": cadence,
                         "reason": (version.reason or "").strip() or None if partial else None})
    return {"owesFrom": begins.isoformat() if begins else None, "versions": versions}
