"""Every past decision in words, for the terminal (REQ-PIPE-166 criterion 12
- Keith, 2026-10-15: it covers `mothman supply decisions` as well as the page).

THE SAME WORDS AS THE PAGE'S DECISION_DONE, held twice on purpose: the raw
dashboard template has to work with no build step, so it keeps its own
const, and tests/test_decision_words.py fails on any difference between the
two. A new action is worded in both or the test says which is missing.
"""
from __future__ import annotations

DONE: dict[str, str] = {
    "promote": "promoted", "reject": "rejected", "demote": "demoted",
    "supersede": "superseded", "un-supersede": "restored", "refile": "re-filed",
    "substitute": "substituted", "inherit": "carried forward",
    "inherit-refused": "refused carrying forward",
    "promotion-withheld": "held back",
    "promotion-refused": "refused promotion",
    "keep": "kept where it was", "excuse-lateness": "excused for lateness",
    "withdraw-excuse": "un-excused", "acknowledge": "acknowledged",
    "de-substitute": "no longer substituted", "un-inherit": "no longer carried forward",
    "mark-not-supplied": "marked not supplied", "still-failing": "recorded as still failing",
    "choose-file": "settled",
    "withdraw-acknowledgement": "no longer acknowledged",
    "withdraw-not-supplied": "no longer marked not supplied",
    "re-check": "re-checked",
    # REQ-PIPE-280 and REQ-PIPE-271 (PROVISIONAL, not put to Keith).
    "carry-forward": "carried forward instead",
    "carry-forward-warning": "warned a newer supply could be carried forward",
}


def said(action: str) -> str:
    """The decision in words; an action not worded yet is shown as it is,
    never dropped."""
    return DONE.get(action, action)
