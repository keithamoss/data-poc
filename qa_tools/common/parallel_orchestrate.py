"""
Generic parallel-or-sequential dispatch across an independent-runs
manifest, used by qa_tools/tools/orchestrate.py (REQ-PIPE-243; it was
shared by the two per-collection orchestrators before that) -
the two scripts' actual per-run tool calls differ (different argument
shapes, different qa_tools/<dataset>/*.py modules), but "run N
independent things, collect results in manifest order, abort on first
failure" is identical between them.

Scoped and measured before building (plans/performance.md #4,
2026-09-14): empirically 2.2x on 4 runs/4 cores for the three
in-process tools, dbt's own concurrency blocked until each run got its
own --target-path (now fixed in qa_tools/common/dbt_common.py).
Default worker count is os.cpu_count() - portable across whatever
machine this runs on next, not hardcoded to the VM this was measured on.

Deliberately kept a sequential mode (Keith's own call) - parallel workers
make stack traces and print-debugging messier, so a single run that needs
investigating is easier to chase down with --sequential than by reading
interleaved worker output.

A run's failure aborts the whole batch (Keith's own call, matching the
pre-parallel behaviour) - see run_manifest's own docstring for how that's
implemented under ProcessPoolExecutor.
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable


def run_manifest(
    manifest: list[dict],
    worker: Callable[..., list[dict]],
    *worker_args,
    sequential: bool = False,
    max_workers: int | None = None,
    before_each: Callable[[dict], None] | None = None,
    after_each: Callable[[dict, list[dict]], None] | None = None,
) -> list[dict]:
    """Runs worker(entry, *worker_args) once per manifest entry, either
    sequentially (in manifest order, today's original behaviour) or in
    parallel across up to `max_workers` processes (default:
    os.cpu_count()). Always returns results concatenated in manifest
    order, regardless of completion order, so output stays byte-for-byte
    reproducible for a given manifest - the same "seeded -> diffable"
    property this project relies on everywhere else.

    `before_each`/`after_each` MAKE THE RUNS DEPENDENT ON EACH OTHER, so
    passing either FORCES SEQUENTIAL EXECUTION whatever `sequential`
    says - and that is the point of them rather than a limitation.
    They exist for filing and promotion (REQ-PIPE-075 criteria 1 and 7):
    a supply fills its open slot or is a resupply of it according to
    whether a PROMOTION has filled it (REQ-PIPE-131), so arrival N's
    filing genuinely depends on arrival N-1's promotion,
    which depends on arrival N-1's checks. The chain is real.

    MEASURED, because it costs something and the number should not be
    guessed at: Child Protection's 18 arrivals take 2m35s in parallel
    and 6m14s in receipt order on this 4-core sandbox, a 2.4x
    regression. WHAT IT BUYS is not a nicety - run in parallel from an
    empty database, every one of the 108 supplies files to 2023-Q1,
    because no slot is ever filled while the filings are being made. In
    receipt order they spread across all 15 quarters, the heaviest
    holding 15, and 67 supplies promote where 6 did. A faster wrong
    answer is not a trade worth having.

    THE OBVIOUS PLACE TO GET THE TIME BACK, for whoever looks next: a
    single run evaluates its four tools one after another and they are
    independent reads. Parallelising WITHIN a run does not touch this
    ordering at all.

    A worker exception aborts the whole batch: under ProcessPoolExecutor,
    a still-running worker isn't killed the instant another one raises
    (cancelling a future that's already executing is a no-op - concurrent
    .futures can only cancel work that hasn't started yet), so remaining
    NOT-YET-STARTED futures are cancelled immediately and the ones already
    running are allowed to finish before the executor tears down and the
    original exception propagates - the same "stop on first failure,
    don't silently produce a partial results file" behaviour the old
    sequential loop gave for free, just not instantaneous.
    """
    if sequential or before_each or after_each:
        results: list[dict] = []
        for entry in manifest:
            if before_each is not None:
                before_each(entry)
            got = worker(entry, *worker_args)
            results.extend(got)
            if after_each is not None:
                after_each(entry, got)
        return results

    ordered_results: list[list[dict] | None] = [None] * len(manifest)
    # THE ASSET AND ITS LAYOUT ARE HANDED TO EACH WORKER (assets.handoff),
    # never left to a fork's inherited memory - the same hand-off the
    # bootstrap's spawned streams get (REQ-PIPE-369 criterion 4).
    from asset_model import assets

    with ProcessPoolExecutor(max_workers=max_workers or os.cpu_count(),
                             initializer=assets.adopt,
                             initargs=assets.handoff()) as ex:
        futures = {ex.submit(worker, entry, *worker_args): i for i, entry in enumerate(manifest)}
        try:
            for future in as_completed(futures):
                ordered_results[futures[future]] = future.result()
        except BaseException:
            for f in futures:
                f.cancel()
            raise

    return [item for run_results in ordered_results for item in run_results]


#: Whether a run's tools overlap (REQ-TEST-116 criterion 3). Set once per
#: process by the batch entry points from their `sequential` flag; a
#: process runs one collection, so one value per process is the right
#: granularity.
TOOLS_CONCURRENTLY = True


def beside(background, foreground, *, concurrent: bool | None = None):
    """Run `background` in a thread while `foreground` runs here; return
    `(background(), foreground())`.

    FOR dbt AND THE OTHER THREE TOOLS (REQ-TEST-116 criterion 3,
    plans/performance.md #5). dbt is a subprocess, so its thread only
    waits; Soda Core, datacontract-cli and Evidently run in-process and
    stay one after another in the foreground, never sharing the
    interpreter concurrently - which none of them was written for.

    FAILURE IS REPORTED IN TOOL ORDER: the background failure wins when
    both fail, as it would have run - and failed - first. Nothing is left
    running behind an exception; the background is always waited for.
    """
    return tuple(side_by_side([background], foreground, concurrent=concurrent))


def side_by_side(background, foreground, *, concurrent: bool | None = None,
                 rank=None) -> list:
    """Run each of `background` in a thread of its own while `foreground`
    runs here; return `[*each background's result, foreground's result]`.

    FOR A RUN'S THREE LANES (REQ-PIPE-431 criterion 4): dbt in its worker,
    datacontract-cli in its worker - each lane's thread only waits on its
    worker - and Soda Core then Evidently in the foreground.

    A STOP - KeyboardInterrupt, SystemExit, anything not an Exception - from
    any lane is raised before any ranking, so an interrupted run is recorded
    as interrupted (post-build-review #370). OTHERWISE, WHEN MORE THAN ONE
    LANE FAILS, the failure `rank(exc)` puts first is raised - the caller's tool order - and lane order where none is given,
    so a report never depends on which lane finished first (criterion 5).
    NOTHING IS LEFT RUNNING BEHIND AN EXCEPTION: every lane is waited for
    before anything is raised. Not concurrent: each lane in turn, the
    background ones first.
    """
    if concurrent is None:
        concurrent = TOOLS_CONCURRENTLY
    lanes = [*background, foreground]
    if not concurrent:
        return [lane() for lane in lanes]
    from concurrent.futures import ThreadPoolExecutor

    outcomes: list = [None] * len(lanes)
    failed: list[tuple[int, BaseException]] = []
    with ThreadPoolExecutor(max_workers=max(1, len(background))) as pool:
        pending = [pool.submit(lane) for lane in background]
        try:
            outcomes[-1] = foreground()
        except BaseException as exc:  # noqa: BLE001 - ranked and re-raised below
            failed.append((len(lanes) - 1, exc))
        for index, future in enumerate(pending):
            try:
                outcomes[index] = future.result()
            except BaseException as exc:  # noqa: BLE001 - ranked and re-raised below
                failed.append((index, exc))
    # A STOP OUTRANKS EVERY TOOL'S FAILURE (post-build-review #370): Ctrl-C or
    # an exit is not a tool crashing, and a lane that failed because of it must
    # not be what the attempt records.
    stops = [f for f in failed if not isinstance(f[1], Exception)]
    if stops:
        raise min(stops, key=lambda f: f[0])[1]
    if failed:
        first = min(failed, key=lambda f: (rank(f[1]) if rank is not None else f[0], f[0]))[1]
        raise first
    return outcomes
