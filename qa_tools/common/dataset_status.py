"""
A dataset's own current real aggregate status (red/amber/green) -
worst-of every real, non-retired check's own current value across every
column - the exact same rollup rule the dashboard's own client-side
`worstOf()`/`checkStatus()` (dashboard/qa-reporting-dashboard.template.
html) already apply, reimplemented here in Python because the GitHub
Issues ticketing automation (item 76, plans/qa-pipeline.md) runs inside
a GitHub Action with no JS/browser runtime - the same kind of
client/server split `pipeline/cadence.py`'s own module docstring
already explains for cycle_start().

Operates on the SAME already-built dashboard-JSON shape `pipeline/
build_dashboard_data.py`/`build_cp_dashboard_data.py` produce (a single
dataset dict with `columns: [{checks: [{current, warn, fail,
retired_as_of}, ...]}, ...]`, or - for Child Protection - one entry from
that shape's `datasets` list) - never a live warehouse/DuckDB
connection, matching CLAUDE.md's own hard rule that no "read committed
history" code path may touch live data.
"""
from __future__ import annotations

STATUS_ORDER = {"green": 0, "amber": 1, "red": 2}


def status_for_value(value: float, warn: float, fail: float) -> str:
    """Mirrors the dashboard's own statusForValue() exactly."""
    if value > fail:
        return "red"
    if value > warn:
        return "amber"
    return "green"


def dataset_status(dataset: dict) -> str:
    """The worst status among every real, non-retired check's own
    `current` value, across every column - mirrors the dashboard's own
    `worstOf(c.checks.filter(ck=>!ck.retired).map(checkStatus))` per
    column, then worst-of-columns for the dataset as a whole. A check is
    "retired" the same way the dashboard treats it: `retired_as_of` is
    set (a real, hand-authored declaration, never inferred from
    absence)."""
    worst = "green"
    for col in dataset.get("columns", []):
        for ck in col.get("checks", []):
            if ck.get("retired_as_of"):
                continue
            s = status_for_value(ck["current"], ck["warn"], ck["fail"])
            if STATUS_ORDER[s] > STATUS_ORDER[worst]:
                worst = s
    return worst
