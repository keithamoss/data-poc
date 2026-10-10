"""
Generic parallel-or-sequential dispatch across an independent-runs
manifest, shared by qa_tools/bdm/orchestrate_bdm.py and
qa_tools/cp/orchestrate_cp.py rather than each reimplementing it -
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
    with ProcessPoolExecutor(max_workers=max_workers or os.cpu_count()) as ex:
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
    if concurrent is None:
        concurrent = TOOLS_CONCURRENTLY
    if not concurrent:
        return background(), foreground()
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(background)
        try:
            ahead = foreground()
        except BaseException:
            try:
                pending.result()
            except BaseException as first:  # noqa: BLE001 - re-raised as the one that ran first
                raise first from None
            raise
        return pending.result(), ahead
