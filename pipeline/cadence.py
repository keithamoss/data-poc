"""
Real, computable per-dataset delivery cadence (plans/qa-pipeline.md,
Phase 5j) - replaces AS_OF_OFFSET_DAYS' flat global day-count staleness
rule and the old decorative sla.frequency/expectedBy/latencyHours text
(none of which anything ever actually checked - grep confirmed
latencyHours wasn't read anywhere at all, and the old onTime computation
used a hardcoded 24h literal, not that field). Each dataset's real ODCS
contract now carries a genuine cadence rule in its `slaProperties:`
array (a real ODCS mechanism - "no limit on the type of properties" per
its own schema - not a new invented top-level YAML key): WHICH day a
delivery's expected (daily every day; weekly on a given weekday;
quarterly on specific anchor months' given day-of-month), WHAT time of
day it's expected (AWST - Keith's call, this agency is WA-based, no
daylight saving to account for), and how much lateness (latency_minutes)
is tolerated before a real delivery counts as late rather than on time.

Two things this module does, deliberately kept separate:
1. cycle_start(cadence, on_or_before) - "as of this date, what's the
   most recent day a delivery was expected?" Pure date arithmetic, no
   timezone/latency involved - also reimplemented in the dashboard's
   own JS (qa-reporting-dashboard.template.html's cycleStartDate()),
   since the as-of picker lets a viewer pick ANY date in the browser,
   not just dates this Python code has already seen - a genuine,
   unavoidable client/server split (a static site has no backend to
   ask), not duplicated logic that could silently drift: both sides are
   tested against the same real cadence configs and the same known
   dates (see tests/test_cadence.py's own cross-check against
   generator/generate_cp_runs.py's _quarter_start(), which this
   generalizes).
2. classify_arrival(cadence, run_date, arrived_at) - "was
   THIS SPECIFIC, ALREADY-HAPPENED delivery early, on time, or late?"
   A real timestamp comparison (this run's own real earliest_extract,
   already committed to qa_results/, against the expected UTC moment +
   latency_minutes grace) - computed ONCE per real run, here, at
   dashboard-build time (a pure function of committed data, no live
   DuckDB access - see CLAUDE.md's CI-never-touches-data rule), and
   embedded as a fixed historical fact. Never needs porting to JS: a
   past run's own real arrival time never changes no matter what as-of
   date someone later picks.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta

import yaml

from qa_tools.common import asset_time

def _sla_properties_to_dict(items: list[dict]) -> dict:
    return {i["property"]: i for i in (items or []) if "property" in i}


def parse_cadence_from_contract(contract_path: str) -> dict:
    """Reads the real `slaProperties:` array from an ODCS contract file.
    Returns {"type": "daily"|"weekly"|"quarterly", "weekday": int|None
    (0=Monday, matching date.weekday()), "anchor_months": list[int]|None,
    "day_of_month": int|None, "expected_time": "HH:MM" (AWST),
    "latency_minutes": int} - the one place this repo's cadence config
    gets parsed, so both build_dashboard_data.py (BDM) and
    build_cp_dashboard_data.py (CP) read the exact same real contract
    data rather than each hand-maintaining their own copy."""
    with open(contract_path) as f:
        doc = yaml.safe_load(f)
    props = _sla_properties_to_dict(doc.get("slaProperties"))

    cadence_type = props["cadenceType"]["value"]
    cadence: dict = {"type": cadence_type}
    if cadence_type == "weekly":
        cadence["weekday"] = int(props["cadenceWeekday"]["value"])
    elif cadence_type == "quarterly":
        cadence["anchor_months"] = sorted(int(m) for m in str(props["cadenceAnchorMonths"]["value"]).split(","))
        cadence["day_of_month"] = int(props["cadenceDayOfMonth"]["value"])
    cadence["expected_time"] = str(props["expectedTime"]["value"])
    cadence["latency_minutes"] = int(props["latency"]["value"])
    return cadence


def cycle_start(cadence: dict, on_or_before: date) -> date:
    """The most recent day, at or before `on_or_before`, a delivery was
    expected under this cadence."""
    t = cadence["type"]
    if t == "daily":
        return on_or_before
    if t == "weekly":
        delta = (on_or_before.weekday() - cadence["weekday"]) % 7
        return on_or_before - timedelta(days=delta)
    if t == "quarterly":
        # Generalizes generator/generate_cp_runs.py's own
        # _quarter_start() (verified there against a January date
        # correctly resolving to the PRIOR year's anchor, and the exact
        # anchor month) to an arbitrary anchor-month list/day-of-month,
        # not just the hardcoded Feb/May/Aug/Nov/day-1 case: for each
        # anchor month, consider both this year's and last year's
        # occurrence, keep only those at or before on_or_before, return
        # the latest. tests/test_cadence.py cross-checks this against
        # the real generator function directly for CP's real config.
        dom = cadence["day_of_month"]
        candidates = []
        for month in cadence["anchor_months"]:
            for year in (on_or_before.year, on_or_before.year - 1):
                d = date(year, month, dom)
                if d <= on_or_before:
                    candidates.append(d)
        return max(candidates)
    raise ValueError(f"unknown cadence type {t!r}")


def expected_moment(cadence: dict, expected_day: date) -> datetime:
    """`expected_day` (a plain date - the cycle's own expected day, from
    cycle_start()) + cadence['expected_time'] (a wall-clock time) -> the
    real instant that represents, in the data asset's own timezone.

    Was `expected_moment_utc()` until REQ-PIPE-048, and subtracted a
    hardcoded `AWST_OFFSET = timedelta(hours=8)` to get there. Same
    answer today - Western Australia does not observe daylight saving,
    so the offset and the zone agree - and a correct one for an asset
    whose zone does. The rename is the point rather than tidiness: the
    return value was never meaningfully UTC, it was an instant, and
    naming a representation in the function encouraged callers to think
    in offsets."""
    return asset_time.wall_clock(expected_day, cadence["expected_time"])


def classify_arrival(cadence: dict, run_date: date, arrived_at: datetime,
                      where: str = "classify_arrival(arrived_at)") -> str:
    """"early" | "onTime" | "late" - run_date is this specific real
    delivery's own date (used to resolve which cycle it belongs to, via
    the same cycle_start() rule); arrived_at is that delivery's own
    real, already-committed arrival instant.

    A NAIVE arrived_at is a hard error (REQ-PIPE-048), not a value
    quietly read as UTC. This function used to do exactly that, and its
    own docstring said so - "naive values are treated as already UTC,
    matching how this repo's timestamps are stored". Which was true, and
    is the bug: a supply that arrived at 10pm in Perth classified
    against a UTC reading of its own timestamp is being judged against
    the following afternoon. `where` names the source in the error,
    since the fix is always at the source rather than here."""
    expected_day = cycle_start(cadence, run_date)
    expected = expected_moment(cadence, expected_day)
    grace_end = expected + timedelta(minutes=cadence["latency_minutes"])
    arrived_at = asset_time.parse_instant(arrived_at, where)
    if arrived_at < expected:
        return "early"
    if arrived_at <= grace_end:
        return "onTime"
    return "late"
