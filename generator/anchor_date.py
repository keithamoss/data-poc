"""
The "today" every generator script's rolling date window is computed
relative to - shared by generate_runs.py (BDM) and generate_cp_runs.py
(CP) so both stay on the same clock.

Defaults to the real wall-clock date, so regenerating the fixture always
lands with its most recent run near "today" - fixing the real, documented
staleness this project's `[recent]`/freshness checks used to suffer from
(a fixed calendar date drifting further from real "now" every day - see
plans/qa-pipeline.md #3). Overridable via GENERATOR_ANCHOR_DATE (an
ISO date, YYYY-MM-DD) for the one case that still needs a fixed date:
reproducing a past regeneration byte-for-byte to verify a code change is
behaviour-preserving (CLAUDE.md's "everything is seeded" diffing
convention) - pin the anchor and the whole fixture regenerates identically
regardless of what day it's actually run.
"""
from __future__ import annotations
import os
from datetime import date


def get_anchor_date() -> date:
    override = os.environ.get("GENERATOR_ANCHOR_DATE")
    if override:
        return date.fromisoformat(override)
    return date.today()
