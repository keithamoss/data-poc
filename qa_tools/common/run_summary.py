"""How a QA run's try ended, in words - the terminal's half (REQ-TEST-416).

ONE SUMMARY LINE PER TRY, BEGINNING WITH ITS RUN ID, printed by the
orchestrator's run step (orchestrate.run_one) from what Attempt.end returned -
never from a re-read of the record (N12):

    <run>: checked in 3m 12s
    <run>: checked in 3m 12s, on the second try - the first crashed in dbt-core after 1m 04s
    <run>: crashed in dbt-core after 1m 04s (CompilationError)
    <run>: timed out after 45m (LockNotAvailable)
    <run>: stopped after 2m 10s

A FAILED TRY'S STORED MESSAGE IS PRINTED ONCE, indented beneath that line,
and then what follows - so the stage-failure report and the processing
pass's failure line need not, and do not, repeat it (criteria 2 and 8).

The same words in a pipe or with NO_COLOR set: nothing here is coloured, so
no meaning is carried by colour (criterion 6). 'Slow' is never judged or
printed here (TR9) - the page alone judges it.

The words for an ended try are shared with the read-only terminal commands
(REQ-TEST-418), so a try reads one way wherever the terminal names it; the
page has its own twin in the template, in its own words (REQ-DASH-414).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qa_tools.common.display_time import format_elapsed

#: WHAT FOLLOWS A FAILED TRY, in the page's words (criteria 2 and 8).
NEXT_STEP = ("Its supply shows as Could not be checked. The next `mothman pipeline process` "
             "tries it again; if it fails the same way every time, reject the supply in "
             "Filing decisions or fix the cause.")

COMPLETED, TIMED_OUT, INTERRUPTED, CRASHED, TOOL_ERROR = (
    "COMPLETED", "TIMED-OUT", "INTERRUPTED", "CRASHED", "TOOL-ERROR")

#: The outcomes that are a FAILED try, whose message and next step follow.
FAILED = (TIMED_OUT, CRASHED, TOOL_ERROR)

_ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
             "ninth", "tenth")


def ordinal(n: int) -> str:
    """'first' for 1 ... 'tenth', then '11th', '12th', '21st'."""
    if 1 <= n <= len(_ORDINALS):
        return _ORDINALS[n - 1]
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def run_time(elapsed_ms: int | None) -> str:
    """A run time in the shared format, or '' where there is none."""
    return "" if elapsed_ms is None else format_elapsed(elapsed_ms / 1000)


def how_it_ended(outcome: str | None, *, tool: str | None = None,
                 elapsed_ms: int | None = None) -> str:
    """How one try ended, in the terminal's words - never its error type, which
    a caller adds where it belongs."""
    took = run_time(elapsed_ms)
    if outcome == COMPLETED:
        return f"checked in {took}"
    if elapsed_ms is None:
        # An end nobody recorded: found dead by a later try, or not yet found.
        return "did not finish, its run time unknown"
    if outcome == TOOL_ERROR:
        return f"crashed in {tool} after {took}"
    if outcome == TIMED_OUT:
        return f"timed out after {took}"
    if outcome == INTERRUPTED:
        return f"stopped after {took}"
    return f"crashed after {took}"


def _row(attempt: Any) -> Mapping[str, Any]:
    return attempt if isinstance(attempt, Mapping) else attempt.__dict__


def lines(run_id: str, ended: Any) -> list[str]:
    """The summary line and, for a failed try, its message and the next step.

    `ended` is what Attempt.end returned (qa_results_writer.Ended)."""
    said = how_it_ended(ended.outcome, tool=ended.tool, elapsed_ms=ended.elapsed_ms)
    if ended.outcome == COMPLETED:
        earlier = [_row(a) for a in ended.earlier]
        # ONLY WHERE THE TRY BEFORE IT FAILED: a run reopened after it
        # completed (a re-check under its own key) needed no "another try".
        # Numbered across the run key, as the page numbers them (PROVISIONAL,
        # 2026-11-16).
        if earlier and earlier[-1].get("outcome") != COMPLETED:
            before = earlier[-1]
            said += (f", on the {ordinal(len(earlier) + 1)} try - the {ordinal(len(earlier))} "
                     + how_it_ended(before.get("outcome"), tool=before.get("tool"),
                                    elapsed_ms=before.get("elapsed_ms")))
        return [f"{run_id}: {said}"]
    if ended.outcome not in FAILED:
        return [f"{run_id}: {said}"]
    out = [f"{run_id}: {said}" + (f" ({ended.error_type})" if ended.error_type else "")]
    for line in (ended.error_message or "").splitlines() or [""]:
        if line.strip():
            out.append(f"    {line}")
    out.append(f"  {NEXT_STEP}")
    return out


#: Set on the exception a failed try raised, once its summary is printed, so
#: a later report of the same failure names it without repeating the message
#: (criterion 8).
SAID = "_run_step_said"


def already_said(exc: BaseException | None) -> bool:
    """Whether the run step already said how this failure's try ended - looked
    for on `exc` and on the cause a stage failure carries."""
    while exc is not None:
        if getattr(exc, SAID, False):
            return True
        exc = getattr(exc, "cause", None)
    return False
