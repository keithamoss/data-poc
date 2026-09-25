"""Which commit the two history-comparing gates compare against.

`validate_schedule.py`'s past-date guard and
`validate_check_lifecycle.py` both answer "did something that should be
immutable change?" by reading one file at an earlier commit. Both used
`HEAD~1` at `fetch-depth: 2`, which has a hole neither docstring
mentioned: **a push of two or more commits is only ever checked on its
last one.** Move a past date in commit A, land commit B on top, and
neither gate sees it - for the calendars and for every hand-authored
check alike (plans/post-build-review.md #44).

One function, in its own module, because BOTH gates need it and neither
should own it. They were already drifting - the schedule guard took a
`ref` parameter and the check gate hardcoded the string - which is how
two copies of one decision start.

THIS IS THE CHEAP HALF, deliberately. The strong version is a committed
seal of what has already elapsed, which needs no git history at all;
that was designed on 2026-09-25 and deferred to
`plans/running-thoughts.md` #44, because the obvious way to build it
costs ~63MB a year in repeated hashes and the elegant way is the same
artefact that item exists to design. This closes the multi-commit hole
today without adding a byte.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: CI sets this to the commit the push started from
#: (`github.event.before`). Unset locally, where HEAD~1 is what a
#: person comparing against "before my change" means anyway.
ENV_VAR = "MOTHMAN_DIFF_BASE"

FALLBACK = "HEAD~1"


def _resolves(ref: str) -> bool:
    """True if `ref` names a commit this checkout can actually read.

    Checked rather than assumed, because the two ways it legitimately
    fails are both ordinary rather than exceptional: a branch's FIRST
    push reports an all-zeros before-SHA, and a shallow checkout simply
    cannot reach a commit older than its depth. Neither is a finding,
    and neither should take a gate down.
    """
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=ROOT, capture_output=True, text=True).returncode == 0


def diff_base(fallback: str = FALLBACK) -> str:
    """The ref to compare against - the push's base where CI says so,
    `HEAD~1` otherwise.

    Falling back rather than failing is deliberate and matches what
    both gates already do when there is no previous commit: a checkout
    that cannot see far enough is a weaker check, not a broken build.
    The alternative - failing when the configured base is unreachable -
    would turn every first push of a branch red.
    """
    ref = (os.environ.get(ENV_VAR) or "").strip()
    if ref and _resolves(ref):
        return ref
    return fallback
