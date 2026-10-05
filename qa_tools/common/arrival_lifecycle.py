"""One arrival's lifecycle, defined once (REQ-PIPE-086 criterion 2).

File it and overlay its period, check it, apply the promotion gate - in
that order, for one arrival, and then the next. Every route that keeps a
supply goes through `process()`: the batch, and the terminal's hand-filed
routes. Before this module those steps were composed in five places - the
two batches' before/after hooks and the two hand-filed `run_arrivals()`
loops among them - and the copies had already drifted apart in code (the
batch pointed a contested Birth Registrations arrival at its delivery
while the hand-filed loop called path_for(), which refuses one - latent,
since every kept Birth Registrations route passes a single file; and the
batch stamped one timestamp per pass, the terminal one per arrival). Two copies of a lifecycle is how a supply someone filed by hand
comes to be treated differently from one that arrived on its own, which
is the whole of what REQ-PIPE-086 exists to prevent.

WHAT IS NOT HERE, deliberately, and why:

- STAGING. The batch stages every arrival before the first is checked
  (`build_all()`), and that order is observable: an arrival staged later
  the same day is a candidate the overlay sees. Moving staging inside
  would change what the batch records, and criterion 13 says this change
  changes nothing. The terminal stages its own files before calling in.
- THE PASS-LEVEL STEPS - recording deliveries, the in-flight survey, the
  run-id guard, ticket reconciliation (criterion 12). They concern a whole
  pass, not one arrival.
- THE ORDER. Callers pass arrivals in the order they mean; REQ-PIPE-151
  will give that one key.

The collection-specific halves (which tables, how an arrival becomes a
run entry, which orchestrator's run step) are supplied by each
collection as a `Steps`, so this module knows nothing about either.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from qa_tools.common import asset_time


@dataclass(frozen=True)
class Steps:
    """A collection's own half of the lifecycle."""

    #: File this arrival (and anything simultaneous with it in `among`)
    #: and rebuild its run's view over the period it was filed to.
    file_and_overlay: Callable[[object, Sequence], None]
    #: The run entry the run step is given for this arrival.
    entry_for: Callable[[object], dict]
    #: Check it: `(entry, run_timestamp, run_by, on_step) -> results`.
    run_one: Callable[..., list[dict]]
    #: The promotion gate over this arrival's results.
    promote_after: Callable[[object, list[dict], str], None]


def process(arrival, *, steps: Steps, among: Sequence, run_timestamp: str,
            run_by: str, on_step=None) -> list[dict]:
    """File, overlay, check and gate ONE arrival; return its results.

    PROMOTION FOLLOWS THE RUN and is not inside it (REQ-PIPE-075 criteria
    1 and 13): a promotion that fails must be retryable without re-running
    QA. tests/test_promotion_after_run.py holds the run step to that.
    """
    steps.file_and_overlay(arrival, among)
    got = steps.run_one(steps.entry_for(arrival), run_timestamp, run_by,
                        on_step=on_step)
    steps.promote_after(arrival, got, run_by)
    return got


def process_all(arrivals: Iterable, *, steps: Steps, run_by: str,
                run_timestamp: str | None = None, on_step=None,
                player=None) -> list[dict]:
    """`process()` each arrival in the order given, one at a time.

    ONE AT A TIME BECAUSE THE CHAIN IS REAL: a supply fills its open slot,
    or is a resupply of it where a promotion already filled it
    (REQ-PIPE-131), so arrival N's filing depends on arrival N-1's
    promotion (parallel_orchestrate.run_manifest's docstring
    has the measurement).

    `run_timestamp` None stamps each arrival as it starts, which is what
    a person filing by hand sees; the batch passes one instant for the
    whole pass, as it always has.
    """
    arrivals = list(arrivals)
    results: list[dict] = []
    for arrival in arrivals:
        # SCRIPTED DECISIONS BETWEEN ARRIVALS (REQ-GEN-135 criterion 3): every
        # one that takes effect before this arrival was received is played
        # first - only by the batch replay of a synthetic history, which is
        # the one caller that passes a player.
        if player is not None:
            player.before(arrival)
        stamp = run_timestamp or asset_time.now().isoformat()
        results.extend(process(arrival, steps=steps, among=arrivals,
                               run_timestamp=stamp, run_by=run_by,
                               on_step=on_step))
    if player is not None:
        player.finish()
    return results
