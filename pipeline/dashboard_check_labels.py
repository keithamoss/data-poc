"""
Shared, small helpers for pipeline/build_dashboard_data.py and
pipeline/build_cp_dashboard_data.py - split out so a fix here can't drift
between the two builders.

1. A hand-curated CHECK_PRIORITY dict used to decide which check is shown
   first in a column's drawer (checks[0] drives the headline "current vs
   previous" comparison and the big trend chart). It only ever had entries
   for a couple of columns, so anything else fell back to whatever order
   the results happened to land in - which for notification_id put a
   check that's flat 0 on every run first, even on a run where the column
   is genuinely red from a *different* check a few cards further down.
   rank_for_headline() replaces that with a real rule: sort by the
   check's own current-run status (worst first), the same status the
   tile itself is colored by, computed with the exact same rule the
   dashboard's own checkStatus() JS function uses - current > fail is
   what actually determines whether the reader sees a check as red in
   the first place, so the headline follows the same definition of
   "worst" the rest of the page does. No column-specific entries to
   maintain, and it can't go stale the way a lookup table can.

2. Raw tool check names shown with no translation - "dbt:unique" and
   "datacontract:duplicate_count" read as two unrelated things unless you
   already know both tools' vocabulary, when they're actually the exact
   same real-world question (are there duplicate values here) asked by
   two different tools. display_name() adds a short, shared, human-
   readable prefix so the overlap is visible at a glance - without hiding
   or merging anything: all four (or however many) real per-tool checks
   still show up as their own card, still individually traceable to the
   tool and number that produced it.

   The label itself is NOT derived here by pattern-matching the check
   name (an earlier version of this file did exactly that, and it was
   wrong to: a second, invented classification layer, disconnected from
   what each check actually tests). Every qa_tools/*/*.py script now
   writes its own `label` directly onto each check-result record, at the
   one place that genuinely knows what a check measures - this module
   just passes that value through unchanged. See any qa_tools/*/run_*.py
   file's `_LABEL_BY_*` dict for where a label actually comes from.
"""
from __future__ import annotations


def status_rank(current, warn, fail) -> int:
    """0 = green, 1 = amber, 2 = red - identical rule to the dashboard's
    own checkStatus() (qa-reporting-dashboard.html): current > fail is
    red, current > warn is amber, otherwise green. Kept in lockstep with
    that function on purpose - the sort order this drives should always
    match what the reader actually sees rendered."""
    current = current or 0
    if current > fail:
        return 2
    if current > warn:
        return 1
    return 0


def rank_for_headline(checks_out: list[dict]) -> None:
    """Sorts checks_out (each already carrying current/warn/fail) worst
    status first, in place. Python's sort is stable, so checks tied on
    status keep whatever relative order they arrived in (e.g. dbt before
    datacontract-cli, matching each engine's place in the underlying
    results list) - no further tie-break needed."""
    checks_out.sort(key=lambda c: status_rank(c["current"], c["warn"], c["fail"]), reverse=True)


def display_name(check_name: str, engine_short: str, label: str | None) -> str:
    """The full string shown as a check card's title. `label` comes
    straight from the check result's own `label` field (see module
    docstring) - None means the check's own name is already plain enough
    (a hand-written Soda `name:`, or a business-rule description that's
    already a full sentence), so no prefix is added."""
    base = f"{check_name} ({engine_short})"
    return f"{label} — {base}" if label else base
