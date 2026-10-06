"""The clock a replay of a synthetic history stamps its records with
(REQ-PIPE-081 criteria 27-31, Keith 2026-10-06).

WHY. A bootstrap replays years of arrivals in a few minutes. Stamped from
the wall clock, every record it wrote - a decision's recorded_at, a
filing's, a run's, a hold's - read as made TODAY about something that took
effect years ago, so "a decision made later changed what this date shows"
(criterion 6) was true of every past date and meant nothing. Keith's
answer: "why can't we just make the synthetic data record dates
properly?" So during a replay, records are stamped with the replay's own
time.

WHAT THE CLOCK READS. Outside a replay, the wall clock (`asset_time.now()`),
always. During one, a SIMULATED clock that keeps running: it is anchored
to an instant - an arrival's receipt as it is processed, a decision's
effective instant as it is recorded - and from there advances at the speed
of the real clock, so two records written one after the other are still
stamped one after the other, as they were before.

WHO MAY TURN IT ON. Only a replay of an asset that declares itself
synthetic (`synthetic: true` in contract/data-asset.yaml). Asking for it
anywhere else is refused: a real asset's record of when something was
written down is evidence, and must never be invented.

PROCESS-WIDE, NOT PER THREAD. A replay processes one arrival at a time in
one process (collections replay in processes of their own), and a run's
four tools write from worker threads - which a context variable would not
reach.
"""
from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

from qa_tools.common import asset_time


class SimulatedClockRefused(RuntimeError):
    """A simulated clock was asked for on an asset that is not synthetic."""


#: (simulated anchor, monotonic seconds at the anchor), or None outside a
#: replay - and None until the first anchor inside one.
_anchor: tuple[datetime, float] | None = None
_active = False


def active() -> bool:
    """Whether a replay on a synthetic asset is stamping with this clock."""
    return _active


def now() -> datetime:
    """The instant to stamp a record with: the wall clock, or during a
    replay the simulated clock."""
    if _active and _anchor is not None:
        at, mono = _anchor
        return at + timedelta(seconds=time.monotonic() - mono)
    return asset_time.now()


def anchor(instant) -> None:
    """Set the simulated clock to `instant` (a datetime or ISO string). A
    no-op outside a replay, so callers need not ask first."""
    global _anchor
    if not _active:
        return
    at = asset_time.parse_instant(instant, "replay clock anchor")
    _anchor = (asset_time.localise(at), time.monotonic())


def advance_to(instant) -> None:
    """Move the simulated clock forward to `instant` if it is behind it - a
    decision recorded as it takes effect. Never backwards."""
    if not _active:
        return
    at = asset_time.parse_instant(instant, "replay clock")
    if _anchor is None or at > now():
        anchor(at)


def _is_synthetic() -> bool:
    """Whether contract/data-asset.yaml declares the asset synthetic - read
    here rather than through the reset module, which nothing but `mothman env`
    may reach (REQ-PIPE-144 criterion 23)."""
    import yaml
    raw = yaml.safe_load(asset_time.DATA_ASSET_YAML.read_text()) or {}
    return raw.get("synthetic") is True


def _require_synthetic() -> None:
    if not _is_synthetic():
        raise SimulatedClockRefused(
            "a simulated clock stamps only a replay of a synthetic history, and this "
            "data asset does not declare `synthetic: true` - a real record of when "
            "something was written down is never invented")


def start() -> None:
    """Turn the simulated clock on. Refused unless the asset is synthetic."""
    global _active, _anchor
    _require_synthetic()
    _active, _anchor = True, None


def stop() -> None:
    global _active, _anchor
    _active, _anchor = False, None


@contextmanager
def replaying():
    """A replay's span: the simulated clock when the asset is synthetic, the
    wall clock otherwise - a real asset's first bootstrap is still a
    bootstrap, and its records carry when they were really written."""
    if not _is_synthetic():
        yield False
        return
    start()
    try:
        yield True
    finally:
        stop()


def on_replay_clock(fn):
    """A batch replay, on the replay's clock for its whole span. A decorator
    rather than a wrapper function so the replay's own body is still what
    `inspect.getsource` reads (functools.wraps)."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with replaying():
            return fn(*args, **kwargs)
    return run
