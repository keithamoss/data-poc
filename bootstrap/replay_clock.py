"""The clock a replay of a synthetic history installs (REQ-PIPE-081 criteria
27-31, Keith 2026-10-06; REQ-PIPE-382 and REQ-GEN-381).

WHY. A bootstrap replays years of arrivals in a few minutes. Stamped from
the wall clock, every record it wrote - a decision's recorded_at, a
filing's, a run's, a hold's - read as made TODAY about something that took
effect years ago, so "a decision made later changed what this date shows"
(criterion 6) was true of every past date and meant nothing. Keith's
answer: "why can't we just make the synthetic data record dates
properly?" So during a replay, records are stamped with the replay's own
time.

ONE CLOCK, AND THIS REPLACES IT (REQ-PIPE-382, B1 SETTLED by Keith
2026-11-14). The real pipeline asks asset_model.asset_time for the time and
announces neutral events - an arrival received at R is being processed, a
delivery or file received at R is being staged, a decision takes effect at T
- and imports nothing of this module. ReplayClock is installed through
asset_time.installed() for the span of a replay, and is the only clock that
acts on those events:

- it is ANCHORED at an instant - an arrival's or a file's receipt, a scripted
  decision's instant - and runs on from there at the speed of the real clock,
  so two records written one after the other are still stamped in order;
- it MOVES FORWARD to a decision's effective instant as the decision is
  recorded, never backwards;
- for the span of an arrival's processing it STAGES THE AGREEMENT AS IT STOOD
  at that receipt (REQ-PIPE-382 criterion 10; correction_replay.staged);
- asked when a decision takes effect it answers RECEIPT PLUS THE SEEDED LAG
  (scenarios/promotion_lag.py; REQ-PIPE-382 criterion 3, OQ1 SETTLED by Keith
  2026-11-14), never after the real wall-clock present.

BEFORE ITS FIRST ANCHOR it reads the clock beneath it - the wall clock, or
MOTHMAN_PINNED_NOW's pinned instant where that is set (criterion 12).

WHO MAY INSTALL IT. Only a replay of an asset that declares itself synthetic:
asset_time.installed() refuses anywhere else, in asset_model/, so the refusal
holds where this package is absent (criterion 6). A real asset's record of
when something was written down is evidence, and is never invented.

PROCESS-WIDE, NOT PER THREAD. A replay processes one arrival at a time in
one process (streams replay in processes of their own, each installing its
own clock), and a run's four tools write from worker threads - which a
context variable would not reach.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timedelta

from asset_model import asset_time
from scenarios import promotion_lag

#: The refusal asset_time.installed() raises - kept under its old name.
SimulatedClockRefused = asset_time.ClockInstallRefused


class ReplayClock(asset_time.Clock):
    """A replay's simulated clock."""

    def __init__(self, beneath: asset_time.Clock):
        self.beneath = beneath
        #: (simulated anchor, monotonic seconds at the anchor), or None until
        #: the first anchor.
        self._anchor: tuple[datetime, float] | None = None

    def now(self) -> datetime:
        if self._anchor is not None:
            at, mono = self._anchor
            return at + timedelta(seconds=time.monotonic() - mono)
        return self.beneath.now()

    def anchor(self, instant) -> None:
        """Set the simulated clock to `instant` (a datetime or ISO string)."""
        at = asset_time.parse_instant(instant, "replay clock anchor")
        self._anchor = (asset_time.localise(at), time.monotonic())

    def advance_to(self, instant) -> None:
        """Move forward to `instant` if behind it. Never backwards."""
        at = asset_time.parse_instant(instant, "replay clock")
        if self._anchor is None or at > self.now():
            self.anchor(at)

    # ---- the pipeline's events (REQ-PIPE-382 criterion 8) -------------------

    @contextmanager
    def processing_arrival(self, received_at):
        """An arrival's processing: anchored at its receipt, with the
        agreement as it stood then staged for the span (criterion 10)."""
        from bootstrap import correction_replay

        self.anchor(received_at)
        with correction_replay.for_instant(received_at):
            yield

    def receiving(self, received_at) -> None:
        self.anchor(received_at)

    def taking_effect(self, instant) -> None:
        self.advance_to(instant)

    def when_effective(self, received_at, *, run_id: str, next_receipt=None,
                       claim_window=None) -> datetime:
        """Receipt plus Keith's 2026-10-02 lag seeded off the run id, spread
        across the claim window, just before the next receipt and never
        before this one, and never after the real present (criterion 3)."""
        return promotion_lag.effective_at(
            asset_time.parse_instant(received_at, "a replayed receipt"), seed=run_id,
            before=next_receipt, within=claim_window, cap=asset_time.real_now())


def installed() -> ReplayClock | None:
    """The replay clock in force in this process, or None."""
    clock = asset_time.current()
    return clock if isinstance(clock, ReplayClock) else None


def active() -> bool:
    """Whether a replay clock is installed in this process."""
    return installed() is not None


def now() -> datetime:
    """The time, from the one clock - kept for the bootstrap's own readers."""
    return asset_time.now()


def anchor(instant) -> None:
    """Anchor the installed replay clock at `instant` - a scripted decision
    played at its own instant. A no-op where none is installed, so a player
    needs not ask first."""
    clock = installed()
    if clock is not None:
        clock.anchor(instant)


def advance_to(instant) -> None:
    """Move the installed replay clock forward to `instant`; a no-op where
    none is installed."""
    clock = installed()
    if clock is not None:
        clock.advance_to(instant)


@contextmanager
def replaying():
    """A replay's span: a ReplayClock installed over the clock in force,
    refused unless the asset declares itself synthetic (REQ-PIPE-382
    criterion 6). There is no wall-clock branch any more (REQ-GEN-381
    criterion 2): the bootstrap is refused on a real asset before it gets
    here. Re-entered inside a replay's span, it is that replay."""
    clock = installed()
    if clock is not None:
        yield clock
        return
    with asset_time.installed(ReplayClock(asset_time.current())) as clock:
        yield clock
