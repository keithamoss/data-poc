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


def status_for_value(value: float, warn: float | None, fail: float | None) -> str:
    """Mirrors the dashboard's own statusForValue() exactly - including
    (plans/qa-pipeline.md item 74) that a None bound means "this check
    has no threshold of that kind", never zero, so it can never be
    crossed. The real case: the ODCS `rowCount` rule is a two-sided
    `mustBeBetween`, so neither bound exists as a single-sided number.

    Only a FALLBACK now: where a real tool verdict was recorded, that
    wins - see dashboard_status_of() below and its two callers."""
    if fail is not None and value > fail:
        return "red"
    if warn is not None and value > warn:
        return "amber"
    return "green"


def dashboard_status_of(record: dict, value_key: str, status_key: str,
                        warn: float | None, fail: float | None) -> str:
    """The real tool verdict where one was recorded, threshold math
    otherwise - the Python mirror of the dashboard's own
    checkStatus()/historyStatus() (item 74). Kept as one helper so the
    two callers below can't drift apart the way this module drifted from
    its own JS counterpart."""
    recorded = record.get(status_key)
    if recorded in STATUS_ORDER:
        return recorded
    return status_for_value(record.get(value_key) or 0, warn, fail)


def status_by_run(dataset: dict) -> dict[str, str]:
    """Real PER-RUN status (not just "current") - mirrors the
    dashboard's own client-side `datasetStatusByRun()` exactly
    (running-thoughts.md #3's leaderboard is this function's own first
    real server-side consumer, but the underlying rollup rule already
    shipped in Phase 7's resupply-chain redesign). Deliberately does
    NOT filter out retired checks the way dataset_status() above does -
    that's `datasetStatusByRun()`'s own real behavior, mirrored exactly
    rather than "corrected": a check being retired as of TODAY has no
    bearing on what its own real recorded value was at some historical
    run N, which is what this function is answering.

    Also mirrors that function's own sparse-result quirk: a run_id
    whose worst real status is green is never actually written into the
    returned dict (an all-green run never beats the "green" default
    it's compared against). Callers must read a MISSING run_id as
    green, via `.get(run_id, "green")` - same as the dashboard's own JS
    callers already do (`statusByRun.get(run.run_id) || "green"`). Not
    a bug to fix; a faithful mirror of real, already-shipped behavior."""
    by_run: dict[str, str] = {}
    for col in dataset.get("columns", []):
        for ck in col.get("checks", []):
            for h in ck.get("history", []):
                s = dashboard_status_of(h, "value", "status", ck["warn"], ck["fail"])
                prev = by_run.get(h["run_id"], "green")
                if STATUS_ORDER[s] > STATUS_ORDER[prev]:
                    by_run[h["run_id"]] = s
    return by_run


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
            s = dashboard_status_of(ck, "current", "current_status", ck["warn"], ck["fail"])
            if STATUS_ORDER[s] > STATUS_ORDER[worst]:
                worst = s
    return worst
