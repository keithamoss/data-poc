"""The fixed date this project's generated history is built around
(REQ-GEN-042).

PINNED, NOT "TODAY". It used to default to `date.today()`, so the whole
fixture slid forward every day it was regenerated - which meant two
regenerations on two consecutive days produced two complete, slightly
different histories that ACCUMULATED rather than replacing one another.
Measured before the fix: the "352 committed runs" this project had been
quoting was really 176, each appearing twice under delivery dates one
day apart, because somebody regenerated on two consecutive days.

BOTH HALVES OF THE FIX MATTER, and either alone leaves a real failure.
A dateless run_id makes a re-run overwrite in place but, with a floating
anchor, silently rewrites every date in the history. A pinned anchor
with a dated run_id still doubles the directory count. So the ids lost
their dates (see generate_runs.py) and the anchor was pinned here.

THE COST IS REAL AND WAS CHOSEN. Keith, 2026-09-22, signing this off:
"I'm happy for demo data to visibly age. That's just how it works." The
generated history drifts further from today until somebody bumps the
constant below and regenerates - which makes regeneration a DELIBERATE
ACT rather than a side effect of running the generator on a different
day. That determinism is the point.

TO REFRESH THE FIXTURE: change ANCHOR_DATE, regenerate, commit. The
whole history moves together, deterministically, and overwrites itself
rather than accumulating beside what was there.
"""
from __future__ import annotations
import os
from datetime import date

# The most recent day a supply lands in the generated history. Every
# date in every dataset is derived from this one value.
#
# 2026-09-22 is the day the history committed alongside REQ-QAC-039 was
# generated - kept deliberately, so pinning the anchor changed no date
# and the commit that introduced it shows the vocabulary change alone
# rather than burying it under a whole-history date shift.
ANCHOR_DATE = date(2026, 9, 22)


def get_anchor_date() -> date:
    """The anchor, or GENERATOR_ANCHOR_DATE if it is set.

    The override survives for the one case that still needs it -
    reproducing a past regeneration byte-for-byte to verify a change is
    behaviour-preserving (CLAUDE.md's "everything is seeded" diffing
    convention). It is no longer how the normal path gets its date.
    """
    override = os.environ.get("GENERATOR_ANCHOR_DATE")
    if override:
        return date.fromisoformat(override)
    return ANCHOR_DATE
