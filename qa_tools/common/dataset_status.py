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

REQ-QAC-047. This module and its browser twin are held to ONE committed
table of cases - status-cases.json at the repo root - read by tests/
test_status_parity.py and tests-js/status-parity.test.js. Neither suite
owns the table, which is the point: a suite that writes its own expected
answers blesses whatever its own side already does. That is not
hypothetical here. A test written for REQ-PIPE-053 asserted that a
rollup handed an unorderable status returns green, reasoning correctly
about the implementation and wrongly about the rule, and it passed for a
day.

The behaviour change this brought is from silently-wrong to
noisily-broken. An unrecognised recorded status used to fall through to
threshold arithmetic here and return green; in the dashboard it passed
straight out to a rollup that could not order it, where the reduce kept
its green seed. Two routes, one false green. Both now raise.
"""
from __future__ import annotations

class UnknownStatusError(ValueError):
    """A recorded status neither implementation recognises.

    Raised rather than fallen back on, and that is the whole point of
    REQ-QAC-047. The previous behaviour converted "I do not know what
    this is" into "this is fine" - an unrecognised verdict fell through
    to threshold arithmetic here, and passed straight out to a rollup
    that could not order it in the dashboard, where the reduce kept its
    green seed. Two different routes to the same false green.

    This changes the failure mode from silently-wrong to noisily-broken.
    That is deliberate: a malformed committed result now stops a
    dashboard build that would previously have rendered a green tile."""


# The agreed vocabulary. Held to status-cases.json by tests/
# test_status_parity.py and tests-js/status-parity.test.js, which is what
# stops this module and the dashboard's own STATUS_ORDER drifting apart
# the way they did in plans/qa-pipeline.md item 74.
#
# The numbers ARE the rule: worst-of is a reduce seeded at green, so
# nodata sits below green where it can only ever lose. "Nothing to show
# yet" must not outrank a real green, and must not look like the worst
# outcome either.
ORDERED_STATUSES = {"nodata": -1, "green": 0, "amber": 1, "red": 2}

# Recognised, but deliberately OUTSIDE the ordering so no rollup can
# absorb them - a caller that needs one surfaces it ALONGSIDE the rolled
# up status, never through it. Asked to order one, worst_of() fails,
# because the only two honest answers are "throw" and "green", and green
# is how item 74 happened.
UNORDERED_STATUSES = {"exhausted"}

RECOGNISED_STATUSES = set(ORDERED_STATUSES) | UNORDERED_STATUSES

# Recognition is scoped to WHERE a status was read from, which the first
# draft of this got wrong and the shared table's own cases caught.
# `exhausted` is a property of a dataset's SCHEDULE; a check result
# carrying it means something upstream wrote a dataset-level status onto
# a check. A flat vocabulary would render that bug instead of reporting
# it.
CHECK_STATUSES = set(ORDERED_STATUSES)
DATASET_STATUSES = RECOGNISED_STATUSES

# Retained under its original name because callers outside this module
# index it directly. Same mapping, now including nodata - whose absence
# was the defect.
STATUS_ORDER = ORDERED_STATUSES


def is_retired(check: dict) -> bool:
    """Whether a check is retired, by the one rule both implementations
    apply: `retired_as_of` carries a real, hand-authored date. Never
    inferred from absence.

    A function rather than an inline truth test because the two sides
    had expressed the same rule differently and disagreed on one input:
    the dashboard tested `retired_as_of != null`, so an EMPTY STRING
    read as retired, while this module tested truthiness and read the
    same check as active. The dashboard's reading is the dangerous one -
    it drops a live check out of the rollup entirely. Empty means nobody
    wrote a date, so the check is active."""
    return bool(check.get("retired_as_of"))


def recognised_status(value: str, read_from: str, allowed=None) -> str:
    """Returns a recorded status if it is one both implementations know
    AT THIS LEVEL, and raises naming it and where it came from otherwise.

    `read_from` is not decoration. Turning a silent wrong answer into a
    loud one is only worth doing if the noise says enough to act on, and
    a bare "unknown status" in a dashboard build tells nobody which of
    four tools wrote it or onto which field."""
    allowed = CHECK_STATUSES if allowed is None else allowed
    if value in allowed:
        return value
    note = ""
    if value in RECOGNISED_STATUSES:
        note = (f" {value!r} is a real status, but not one a {read_from!r} "
                "may carry - something wrote a dataset-level status onto a "
                "check result.")
    raise UnknownStatusError(
        f"unrecognised status {value!r} read from {read_from!r}; "
        f"valid here are {sorted(allowed)}.{note} An unrecognised "
        "status is not evidence of health, so it is refused rather than "
        "read as green - see status-cases.json."
    )


def worst_of(statuses) -> str:
    """Worst-of across an orderable set, seeded green - the Python mirror
    of the dashboard's own worstOf().

    Fails on anything it cannot order, including a RECOGNISED but
    deliberately unordered status like `exhausted`. Dropping it silently
    returns green; ranking it invents an ordering nobody agreed."""
    worst = "green"
    for s in statuses:
        if s not in ORDERED_STATUSES:
            raise UnknownStatusError(
                f"cannot order status {s!r} in a rollup; orderable statuses "
                f"are {sorted(ORDERED_STATUSES)}"
                + (f". {s!r} is recognised but deliberately unorderable - it "
                   "is surfaced alongside a rolled-up status, never through "
                   "one." if s in UNORDERED_STATUSES else "")
            )
        if ORDERED_STATUSES[s] > ORDERED_STATUSES[worst]:
            worst = s
    return worst

# Each real check result carries its own tool's verdict - a real `status`
# written by every qa_tools/*/run_*.py module from what dbt-core/Soda
# Core/datacontract-cli/Evidently actually decided. That verdict is the
# authority everywhere; threshold math is only ever a fallback, because a
# warn/fail pair cannot express every real rule (the ODCS `rowCount` rule
# is a two-sided `mustBeBetween`, so neither bound exists as a single
# number). plans/qa-pipeline.md item 74.
_DASHBOARD_STATUS_BY_TOOL_STATUS = {
    "pass": "green",
    "warn": "amber",
    "fail": "red",
    "error": "red",
}


def dashboard_status(tool_status: str | None) -> str | None:
    """Maps a real tool verdict onto the dashboard's own green/amber/red
    vocabulary. None for anything unrecognised (or absent), so callers
    fall back rather than silently reading an unknown verdict as green -
    an unknown verdict is not evidence of health."""
    if not tool_status:
        return None
    return _DASHBOARD_STATUS_BY_TOOL_STATUS.get(tool_status)


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
    if recorded:
        return recognised_status(recorded, status_key)
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
                if worst_of([s, prev]) != prev:
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
    return worst_of(
        dashboard_status_of(ck, "current", "current_status", ck["warn"], ck["fail"])
        for col in dataset.get("columns", [])
        for ck in col.get("checks", [])
        if not is_retired(ck)
    )
