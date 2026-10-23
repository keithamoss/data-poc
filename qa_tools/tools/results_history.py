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

AND ONE PATH SINCE REQ-PIPE-279: the live batch writes the file by this
rebuild too, because what the build places and orders results by - each
run's facts and each cross-table result's recorded reads - is in the
record, not in a tool's in-memory results (criteria 16 to 18).
"""
from __future__ import annotations

import os

from qa_tools import collections
from qa_tools.common import asset_time, atomic_file
from qa_tools.common.qa_results_reader import (
    RESULT_TOOLS, canonical_order, current_runs_only, list_run_ids, read_check_reads,
    read_cross_table_results, read_dataset_stats, read_one, run_facts,
)

__all__ = ["build_results_from_history", "results_path", "write_results_file"]

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def results_path(collection_id: str) -> str:
    """`<ROOT>/reports/<the collection's results_file>` - the one file both the
    live batch and the rebuild write, named from its agency short and id
    (REQ-PIPE-248 criterion 7)."""
    return os.path.join(ROOT, "reports", collections.by_id(collection_id).results_file)


def write_results_file(collection_id: str, *, runs: list[dict], dataset_stats: dict,
                       results: list[dict], generated_at: str, source: str = "",
                       facts: dict[str, dict] | None = None) -> dict:
    """The results file, whole or not at all (another process may be reading
    it), with its summary - and THE FIFTH VERDICT (REQ-QAC-108 criterion 5):
    a check with no reference measured nothing, so it is counted as `nodata`
    rather than under any of the four, which then no longer add up to the
    total on their own."""
    coll = collections.by_id(collection_id)
    results = canonical_order(results)
    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in ("pass", "warn", "fail", "error", "nodata")}
    header = {"collection": f"{coll.agency_id}.{coll.id}",
              "datasets": sorted(d.dataset_id for d in coll.datasets)}
    output = {
        "generated_at": generated_at,
        **header,
        "runs": runs,
        # WHAT EACH RUN IS, from qa.run (REQ-PIPE-279 criteria 16 and 17) -
        # its rank, never its run_seq.
        "run_facts": facts or {},
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


def build_results_from_history(collection_id: str, *, generated_at: str | None = None,
                               source: str = ", from recorded history") -> dict:
    """Rebuild the collection's results file from the recorded `qa` schema
    alone - the dashboard build's source, no tool re-run, no supply rows."""
    coll = collections.by_id(collection_id)
    facts = run_facts(coll.agency_id, coll.id)
    run_ids = current_runs_only(list_run_ids(coll.agency_id, coll.id))
    manifest, stats_by_run = [], {}
    for run_id in run_ids:
        stats = read_dataset_stats(coll.agency_id, coll.id, run_id)
        if stats is None:
            continue
        manifest.append(stats["arrival_record"])
        stats_by_run[run_id] = stats
    # IN THE ORDER THE RUNS WERE OPENED (REQ-PIPE-279 criterion 19): it was
    # run_index, an arrival enumeration a re-check had to be stamped with to
    # sort at all (post-build-review #161), and a settled pair shares one.
    manifest.sort(key=lambda m: facts[m["run_id"]]["rank"])

    # AND THE IN-DEVELOPMENT ONES (REQ-PIPE-106 criterion 7): `None` is every
    # supply_state, asked for explicitly because the dashboard is the one
    # reader that has to show a calendar-less dataset's real verdicts.
    results = [r for entry in manifest for tool in RESULT_TOOLS
               for r in read_one(coll.agency_id, coll.id, entry["run_id"], tool,
                                 supply_state=None)]
    # EACH WITH WHAT IT READ (REQ-PIPE-279 criteria 16 and 18), the build's
    # one source for where a cross-table result is placed and shared.
    reads = read_check_reads(coll.agency_id, coll.id)
    results += [{**r, "reads": reads[(r["run_id"], r["check_id"])]}
                for r in read_cross_table_results(coll.agency_id, coll.id, supply_state=None)]
    return write_results_file(collection_id, runs=manifest, dataset_stats=stats_by_run,
                              results=results,
                              generated_at=generated_at or asset_time.now().isoformat(),
                              source=source, facts=facts)
