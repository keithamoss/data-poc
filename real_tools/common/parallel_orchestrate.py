"""
Generic parallel-or-sequential dispatch across an independent-runs
manifest, shared by real_tools/bdm/orchestrate_real_bdm.py and
real_tools/cp/orchestrate_real_cp.py rather than each reimplementing it -
the two scripts' actual per-run tool calls differ (different argument
shapes, different real_tools/<dataset>/*.py modules), but "run N
independent things, collect results in manifest order, abort on first
failure" is identical between them.

Scoped and measured before building (plans/performance.md #4,
2026-09-14): empirically 2.2x on 4 runs/4 cores for the three
in-process tools, dbt's own concurrency blocked until each run got its
own --target-path (now fixed in real_tools/common/dbt_common.py).
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
) -> list[dict]:
    """Runs worker(entry, *worker_args) once per manifest entry, either
    sequentially (in manifest order, today's original behaviour) or in
    parallel across up to `max_workers` processes (default:
    os.cpu_count()). Always returns results concatenated in manifest
    order, regardless of completion order, so output stays byte-for-byte
    reproducible for a given manifest - the same "seeded -> diffable"
    property this project relies on everywhere else.

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
    if sequential:
        return [item for entry in manifest for item in worker(entry, *worker_args)]

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
