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
from qa_tools.common import replay_clock


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
    done: list[str] = []
    stage = FILING
    try:
        steps.file_and_overlay(arrival, among)
        done.append(FILING)
        stage = CHECKING
        got = steps.run_one(steps.entry_for(arrival), run_timestamp, run_by,
                            on_step=on_step)
        done.append(CHECKING)
        stage = GATING
        steps.promote_after(arrival, got, run_by)
    except StageFailed:
        raise
    except Exception as exc:
        # WHICH ARRIVAL, WHICH STAGE, AND WHAT HAD COMPLETED (REQ-TEST-150
        # criterion 7) - the original exception chained, nothing swallowed.
        raise StageFailed(arrival.run_id, stage, tuple(done), exc) from exc
    return got


FILING, CHECKING, GATING = "filing and overlay", "checks", "promotion gate"


class StageFailed(RuntimeError):
    """One arrival's lifecycle stopped at a named stage."""

    def __init__(self, run_id: str, stage: str, completed: tuple[str, ...], cause):
        super().__init__(f"{run_id}: the {stage} stage failed ({type(cause).__name__}: "
                         f"{cause})" + (f" after {', '.join(completed)} completed"
                                        if completed else " before anything completed"))
        self.run_id, self.stage, self.completed, self.cause = run_id, stage, completed, cause


class ArrivalBusy(RuntimeError):
    """Another process has this arrival, or has already finished it."""


def process_all(arrivals: Iterable, *, steps: Steps, run_by: str,
                run_timestamp: str | None = None, on_step=None,
                player=None, exclusive: bool = False, prepare=None,
                start_at: int = 1, after_each=None) -> list[dict]:
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
    if exclusive:
        return _exclusively(arrivals, steps=steps, run_by=run_by,
                            run_timestamp=run_timestamp, on_step=on_step)
    results: list[dict] = []
    for position, arrival in enumerate(arrivals, start=1):
        # A RESUME STARTS PART-WAY (REQ-TEST-159): the arrivals before
        # `start_at` are already in the checkpoint it was copied from.
        if position < start_at:
            continue
        # STAGED AND RECORDED AS IT ARRIVES (REQ-TEST-159, Keith's signing
        # answer): `prepare` stages this arrival and records its delivery -
        # with every arrival sharing its receipt instant, which are filed
        # together - so the database never holds an arrival from its future.
        if prepare is not None:
            prepare(arrival, arrivals)
        # SCRIPTED DECISIONS BETWEEN ARRIVALS (REQ-GEN-135 criterion 3): every
        # one that takes effect before this arrival was received is played
        # first - only by the batch replay of a synthetic history, which is
        # the one caller that passes a player.
        if player is not None:
            player.before(arrival)
        # A REPLAY PROCESSES EACH ARRIVAL AS IT IS RECEIVED (REQ-PIPE-081
        # criteria 27-31): its run is stamped then, not with one instant for
        # the whole pass - which was the wall clock, the day of the replay.
        if replay_clock.active():
            replay_clock.anchor(arrival.received_at)
            stamp = replay_clock.now().isoformat()
        else:
            stamp = run_timestamp or asset_time.now().isoformat()
        results.extend(process(arrival, steps=steps, among=arrivals,
                               run_timestamp=stamp, run_by=run_by,
                               on_step=on_step))
        # A CHECKPOINT IS TAKEN HERE (REQ-TEST-159 criterion 1): once this
        # arrival is fully processed and before the next is touched.
        if after_each is not None:
            after_each(position, arrival, player)
    if player is not None:
        player.finish()
    return results


def arriving_with(arrival, among) -> list:
    """This arrival and every other in `among` from the SAME DELIVERY or
    received at the SAME INSTANT. A delivery's tables are all loaded before
    any of it is checked (REQ-PIPE-035 criterion 10) - its files can land
    minutes apart (REQ-GEN-044) - and a zip's files are filed together
    (REQ-PIPE-105 criterion 5)."""
    return [a for a in among if a.delivery_name == arrival.delivery_name
            or a.received_at == arrival.received_at] or [arrival]


def staged_as_it_arrives(stage_one) -> Callable:
    """A `prepare` for process_all: stage each arrival, and record the
    delivery it came in, just before the first arrival of its delivery (or
    of its receipt instant) is processed (REQ-TEST-159). Before this, a batch staged and
    recorded EVERY arrival up front, so a replay's database already held
    the future while the past was being checked - harmless to a full replay
    run to the end, and wrong for a checkpoint taken part-way through it.

    STAGED AT ITS OWN RECEIPT on the replay clock, as the processing pass
    stages an arrival when it lands (REQ-PIPE-151)."""
    from qa_tools.common import delivery_log

    done: set[str] = set()

    def prepare(arrival, among) -> None:
        for a in arriving_with(arrival, among):
            if a.run_id in done:
                continue
            replay_clock.anchor(a.received_at)
            stage_one(a)
            delivery_log.record_arrival(a)
            done.add(a.run_id)
    return prepare


def _exclusively(arrivals, *, steps, run_by, run_timestamp, on_step) -> list[dict]:
    """Each arrival under its own lock - the hand-filed path's half of
    REQ-PIPE-151 criterion 6 (post-build-review #120 D1).

    A processing pass takes the pass lock and then each arrival's; a person
    keeping a supply at the terminal takes no pass lock, so without this the
    two could process one arrival at once - which the critic reproduced:
    each dropped the other's run schemas and both failed. Refused rather
    than waited for, because the other process may be a whole pass long,
    and refused BEFORE filing, so nothing is left half done. Once the lock
    is held the record is read again: a pass that finished the arrival
    while the person was answering questions has already recorded it, and a
    second set of results under its run id is what REQ-PIPE-086 criterion 8
    forbids.
    """
    from qa_tools.common import processing_pass, supply_db

    results: list[dict] = []
    with supply_db.connect(label="mothman:keep-arrival-locks") as conn:
        for arrival in arrivals:
            with processing_pass.arrival_lock(conn, arrival.run_id) as mine:
                if not mine:
                    raise StageFailed(arrival.run_id, FILING, (), ArrivalBusy(
                        "another process is processing this arrival right now - nothing "
                        "was done to it; run `mothman pipeline process` once that "
                        "finishes, or keep it again"))
                state = processing_pass.state_of(arrival, processing_pass.recorded(conn))
                if state != processing_pass.UNCHECKED:
                    raise StageFailed(arrival.run_id, FILING, (), ArrivalBusy(
                        "another process has already checked this arrival, so its "
                        "results stand and nothing was recorded again"))
                stamp = run_timestamp or asset_time.now().isoformat()
                results.extend(process(arrival, steps=steps, among=arrivals,
                                       run_timestamp=stamp, run_by=run_by,
                                       on_step=on_step))
    return results
