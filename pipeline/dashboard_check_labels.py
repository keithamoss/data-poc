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


# One canonical status implementation per language (plans/qa-pipeline.md
# item 74's follow-up, 2026-09-19). This module used to carry its own
# copy of the green/amber/red rule, which is how it drifted from
# qa_tools/common/dataset_status.py in the first place - and that drift
# is what shipped a real TypeError to CI. There is a genuine,
# unavoidable client/server split here (the dashboard is static, so the
# browser must be able to re-roll status for any as-of date a viewer
# picks; the ticketing Action has no JS runtime), but that argues for
# exactly TWO implementations - one JS, one Python - not four. This is
# the Python one's only home; the JS one is guarded against it by a real
# shared-fixture cross-check (tests/test_status_parity.py).
from qa_tools.common.check_id import try_parse
from qa_tools.common.dataset_status import (  # noqa: F401
    STATUS_ORDER,
    dashboard_status,
    dashboard_status_of,
    status_for_value,
)


def status_rank(current, warn, fail, status: str | None = None) -> int:
    """0 = green, 1 = amber, 2 = red, for sorting. Thin wrapper over the
    canonical rule - the real tool verdict wins where one exists,
    threshold math is the fallback, and a None bound means "no bound of
    that kind", never zero."""
    return STATUS_ORDER[dashboard_status_of(
        {"current": current, "current_status": status}, "current", "current_status", warn, fail
    )]


def rank_for_headline(checks_out: list[dict]) -> None:
    """Sorts checks_out (each already carrying current/warn/fail, and
    current_status where the tool gave a real verdict) worst status
    first, in place. Python's sort is stable, so checks tied on status
    keep whatever relative order they arrived in (e.g. dbt before
    datacontract-cli, matching each engine's place in the underlying
    results list) - no further tie-break needed."""
    checks_out.sort(
        key=lambda c: status_rank(c["current"], c["warn"], c["fail"], c.get("current_status")),
        reverse=True,
    )


def display_name(check_name: str, engine_short: str, label: str | None) -> str:
    """The string shown as a check card's title.

    The tool and its macro used to be appended - "Invalid values -
    dbt:accepted_values (dbt-core)". Both are gone (Keith, 2026-09-20,
    plans/running-thoughts.md #19): rules 10 and 11 of
    docs/check-authoring-rules.md forbid naming a tool or a macro
    anywhere in a check's prose, on the grounds that a steward does not
    know which tool ran the check - and the heading directly above that
    prose was doing exactly that, on every check in the dashboard.

    Nothing is lost by dropping the tool. Every check card and drawer
    already carries `note` - "Computed by dbt-core against this run's
    real data" - so the tool is still one line below, in a sentence
    rather than in brackets.

    This is only safe because the URL no longer keys on this string; see
    `url_key()`. While it did, the heading had to stay unique within a
    column, which is what the macro suffix was really buying.

    `label` is None where the check's own name is already plain (a
    hand-written Soda `name:`, or a business rule whose name is a full
    sentence) - that name is used as-is.
    """
    return label or check_name


def url_key(check_id: str) -> str:
    """The stable, URL-facing identity of a check.

    The dashboard used to key its /check/ URLs on the DISPLAY name, which
    made every heading change a broken bookmark and required the heading
    to stay unique within a column - which is most of why headings read
    "Invalid values - dbt:accepted_values (dbt-core)" rather than
    something a steward would recognise (plans/running-thoughts.md #19).

    REQ-QAC-023 already built the guarantee this needs and then left it
    unused: `validate_tail_uniqueness()` exists precisely because "a
    dashboard URL carries agency, collection, dataset and column but no
    table, keying the check on its tail alone". This is that wiring.

    Falls back to the raw check_id for anything that does not parse, so a
    malformed id degrades to an ugly URL rather than an absent one.
    """
    parsed = try_parse(check_id)
    return parsed.tail if parsed else check_id
