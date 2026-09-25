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
# shared table of cases neither side owns (status-cases.json, read by
# tests/test_status_parity.py and tests-js/status-parity.test.js).
#
# That cross-check was named here before it existed - this comment cited
# tests/test_status_parity.py while no such file was in the repo, from
# 2026-09-19 until REQ-QAC-047 built it on 2026-09-23. Left recorded
# rather than quietly corrected: a comment describing a guard that is
# not there reads exactly like one describing a guard that is.
from qa_tools.common.check_id import TOOLS, try_parse
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
    that kind", never zero.

    A STATUS WITH NO VERDICT SORTS BELOW EVERYTHING, which is the one
    thing `STATUS_ORDER` cannot answer: `inactive` is deliberately
    outside the ordering (post-build-review #4), so indexing it raised a
    KeyError and took the whole dashboard build down. That was the right
    failure - loud, at build time - but this function's job is to put
    checks in an order for a HEADLINE, and "there is no rule for this
    column" belongs at the bottom of that list rather than anywhere in
    it. Ranked here, locally, rather than by giving `inactive` a number
    in the shared vocabulary, which is exactly the invented ordering
    that vocabulary refuses.
    """
    resolved = dashboard_status_of(
        {"current": current, "current_status": status}, "current", "current_status", warn, fail
    )
    return STATUS_ORDER.get(resolved, _UNRANKED)


#: Below nodata's -1, so a check carrying no verdict at all sorts last.
_UNRANKED = -2


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
    REQ-DASH-026): rules 10 and 11 of
    docs/check-authoring-rules.md forbid naming a tool or a macro
    anywhere in a check's prose, on the grounds that a check's
    explanation should not assume the reader knows which tool ran it -
    and the heading directly above that prose was doing exactly that, on
    every check in the dashboard.

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
    something a data engineer would recognise (plans/running-thoughts.md
    #19).

    REQ-QAC-023 already built the guarantee this needs and then left it
    unused: `validate_tail_uniqueness()` exists precisely because "a
    dashboard URL carries agency, collection, dataset and column but no
    table, keying the check on its tail alone". This is that wiring.

    Falls back to the raw check_id for anything that does not parse, so a
    malformed id degrades to an ugly URL rather than an absent one.
    """
    parsed = try_parse(check_id)
    return parsed.tail if parsed else check_id


def tool_ref(check_id: str) -> str:
    """The terse "which tool, which check" line shown under a card's
    plain-English headline - "dbt:not_null", "soda:missing_count",
    "datacontract:closed_case_hygiene".

    REQ-DASH-026. The criterion originally asked for the tool's own
    check name verbatim, which does not survive contact with two of the
    four tools: 20 of 54 real names exceed 40 characters, and
    datacontract's SQL rules reach 200 - a full sentence restating, in
    tool vocabulary, the description printed directly above it.

    So this is derived from the check_id's own tail instead, which is
    already a hand-authored terse name, already unique within a column
    (REQ-QAC-023's validate_tail_uniqueness gates that in CI), and
    already what url_key() puts in the address bar. Card and URL
    therefore resolve to the same string, which is the point: what a
    reader sees is what they can deep-link to and grep the contract for.
    Hand-authoring a second set of short names was the alternative, and
    it would have been a mapping with nothing keeping it honest.

    The tail is "<terse_name>_<tool>"; this moves the tool to the front
    with a colon, reusing check_id.TOOLS rather than restating it. That
    matters more than it looks: the grammar ALREADY requires the tail to
    end in one of those four (see check_id.py's own `tail` pattern), so
    a second list here would be a copy that can only ever drift out of
    agreement with the thing actually enforcing it - and the symptom
    would be a card silently reading "some_check_greatexpectations"
    while the id parsed fine.

    An id that does not parse at all falls through to url_key()'s own
    raw-id fallback, so an unfamiliar shape reads oddly rather than
    being mangled into a wrong tool name.
    """
    key = url_key(check_id)
    for tool in TOOLS:
        suffix = "_" + tool
        if key.endswith(suffix) and len(key) > len(suffix):
            return f"{tool}:{key[:-len(suffix)]}"
    return key
