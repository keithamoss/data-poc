"""A collection's results file, rebuilt from recorded history alone
(REQ-PIPE-243), and the one function both that rebuild and the live batch
write it with.

A BUILD MAY READ RECORDED QA RESULTS, NEVER ACTUAL DATA, AND NEVER ANYTHING
ELSE (Keith, 2026-09-27). This reads the `qa` schema and nothing else: every
number it needs - check results, the runs, the presentation statistics - was
resolved and recorded at run time (qa_tools/tools/dataset_stats.py).

BUILT FROM CHILD PROTECTION'S COPY: the runs are each supply's CURRENT run
(REQ-PIPE-140 criterion 5), each read for its own results, then the
cross-table scope beside them (REQ-QAC-037 criterion 1 - a walk of the run
ids does not reach it, and missing it once dropped 432 results without a
word). Birth Registrations' copy differed in two places, kept behind its
legacy flags (qa_tools/tools/legacy.py).

ONE AGREED ORDERING down both paths (REQ-PIPE-038): a live run emits a
collection's tables interleaved and a rebuild reads them one after another,
so canonical_order() is what keeps a diff between the two a real check.
"""
from __future__ import annotations

import os

from qa_tools import collections
from qa_tools.common import asset_time, atomic_file
from qa_tools.common.qa_results_reader import (
    RESULT_TOOLS, canonical_order, current_runs_only, list_run_ids, read_cross_table_results,
    read_dataset_stats, read_one,
)

__all__ = ["build_results_from_history", "results_path", "write_results_file"]

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def results_path(collection_id: str) -> str:
    """`<ROOT>/reports/<the collection's results_file>` - the one file both the
    live batch and the rebuild write, named from its agency short and id
    (REQ-PIPE-248 criterion 7)."""
    return os.path.join(ROOT, "reports", collections.by_id(collection_id).results_file)


def write_results_file(collection_id: str, *, runs: list[dict], dataset_stats: dict,
                       results: list[dict], generated_at: str, source: str = "") -> dict:
    """The results file, whole or not at all (another process may be reading
    it), with its summary - and THE FIFTH VERDICT (REQ-QAC-108 criterion 5):
    a check with no reference measured nothing, so it is counted as `nodata`
    rather than under any of the four, which then no longer add up to the
    total on their own."""
    coll = collections.by_id(collection_id)
    adapter = collections.adapter(coll)
    results = canonical_order(results)
    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in ("pass", "warn", "fail", "error", "nodata")}
    if "results.single_dataset_header" in adapter.legacy:
        [dataset] = coll.datasets
        header = {"dataset": f"{coll.agency_id}.{coll.id}.{dataset.dataset_id}"}
    else:
        header = {"collection": f"{coll.agency_id}.{coll.id}",
                  "datasets": sorted(d.dataset_id for d in coll.datasets)}
    output = {
        "generated_at": generated_at,
        **header,
        "runs": runs,
        "dataset_stats": dataset_stats,
        "results": results,
        "summary": {"total_checks": len(results), **counts,
                    "engines": sorted(set(r["engine"] for r in results))},
    }
    path = results_path(collection_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_file.write_json(path, output)
    n_error, n_nodata = counts["error"], counts["nodata"]
    print(f"\n{len(results)} real check results ({counts['pass']} pass / {counts['warn']} warn / "
          f"{counts['fail']} fail{f' / {n_error} error' if n_error else ''}"
          f"{f' / {n_nodata} no reference' if n_nodata else ''}) across {len(runs)} runs"
          f"{source} -> {path}")
    return output


def build_results_from_history(collection_id: str) -> dict:
    """Rebuild the collection's results file from the recorded `qa` schema
    alone - the dashboard build's source, no tool re-run, no supply rows."""
    coll = collections.by_id(collection_id)
    run_ids = current_runs_only(list_run_ids(coll.agency_id, coll.id))
    manifest, stats_by_run = [], {}
    for run_id in run_ids:
        stats = read_dataset_stats(coll.agency_id, coll.id, run_id)
        if stats is None:
            continue
        manifest.append(stats["arrival_record"])
        stats_by_run[run_id] = stats
    # run_index (not run_date) matches the original generation order - a
    # resupply's own run_date sorts it away from its parent delivery.
    manifest.sort(key=lambda m: m["run_index"])

    # AND THE IN-DEVELOPMENT ONES (REQ-PIPE-106 criterion 7): `None` is every
    # supply_state, asked for explicitly because the dashboard is the one
    # reader that has to show a calendar-less dataset's real verdicts.
    results = [r for entry in manifest for tool in RESULT_TOOLS
               for r in read_one(coll.agency_id, coll.id, entry["run_id"], tool,
                                 supply_state=None)]
    results += read_cross_table_results(coll.agency_id, coll.id, supply_state=None)
    return write_results_file(collection_id, runs=manifest, dataset_stats=stats_by_run,
                              results=results, generated_at=asset_time.now().isoformat(),
                              source=", from recorded history")
