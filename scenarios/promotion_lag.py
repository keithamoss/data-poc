"""The seeded promotion lag of a replayed synthetic history (REQ-PIPE-382
criterion 3; REQ-GEN-386 criterion 4).

WHERE IT LIVES AND WHY (REQ-PIPE-382 OQ1, SETTLED by Keith 2026-11-14 as (b),
then the rule's own home as (a)): on a real asset a promotion takes effect
simply now - the instant it is made - and this rule is not in shipped code. The
bootstrap's replay clock applies it when the pipeline asks the clock when a
decision takes effect; the Linkage Products provider predicts each source
promotion's effective instant with it (its release must be received after
them). One copy, importable by both, in the package a real deployment leaves
out.

THE LAG IS INVENTED, AND SAYING SO IS PART OF THE DESIGN. Keith chose it
(2026-10-02) over promoting at the arrival instant, so REQ-PIPE-080's
receipt-to-promotion interval shows a spread rather than a column of zeros. It
is seeded off the run id so a regeneration reproduces it - but no particular
supply's wait is a measurement of anything.

THE BOUNDS, each Keith's:
- SPREAD ACROSS THE CLAIM WINDOW where one is given (2026-10-11, REQ-GEN-185;
  post-build-review #156), else one hour to three days after receipt;
- NEVER AT OR PAST THE NEXT RECEIPT of the same dataset - just before it, and
  never before this supply's own (2026-10-06, post-build-review #117 D5);
- NEVER AFTER THE REAL PRESENT (REQ-PIPE-382, v6): a history whose anchor
  rolls to today cannot record a promotion taking effect in the real future.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from asset_model import asset_time

#: The window a promotion's invented lag falls in where no claim window is
#: given: long enough to read as somebody getting to it, short enough not to
#: read as neglect.
LAG_MIN = timedelta(hours=1)
LAG_SPAN = timedelta(days=3) - LAG_MIN


def fraction_of(seed: str) -> float:
    """Where in its window a supply's lag falls, from its seed: a fraction
    rather than a modulo over hours, so the lag moves with the window if it is
    ever retuned."""
    digest = hashlib.sha256((seed or "").encode()).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def effective_at(received_at: datetime, *, seed: str = "", before: datetime | None = None,
                 within: timedelta | None = None, cap: datetime | None = None) -> datetime:
    """When a replayed promotion of a supply received at `received_at` takes
    effect: receipt plus the seeded lag, spread across `within` where given,
    just before `before` (the next receipt) and never before receipt, and never
    after `cap` - the real present unless given."""
    cap = cap if cap is not None else asset_time.real_now()
    fraction = fraction_of(seed)
    if within is not None:
        low = min(LAG_MIN, within)
        took = min(cap, received_at + low + (within - low) * fraction)
    else:
        took = min(cap, received_at + LAG_MIN + LAG_SPAN * fraction)
    if before is not None and took >= before:
        took = max(received_at, before - timedelta(seconds=1))
    return took
