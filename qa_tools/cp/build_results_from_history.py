"""
Rebuilds reports/results_cp.json purely from Phase 1/2/3's committed
qa_results/ history - the Child Protection counterpart to
qa_tools/bdm/build_results_from_history.py (see that file's own
docstring for the full rationale). Runs no real tool, touches no local
data of any kind.

Reads every tool's output from the same qa_results/ dataset segment per
run - cp_common.COLLECTION_ID. All 5 files (dbt/soda/datacontract/
evidently/dataset_stats) live together under one run_id directory now;
Evidently briefly wrote under its own table-scoped dataset id
(hierarchy.dataset_for_table("cp_notifications").dataset_id) instead, a real bug
fixed 2026-09-16 (run_evidently_cp.py's own comment on the write side)
- Evidently's own per-result "dataset_id" field still correctly says
"cp-notifications" for dashboard per-table grouping, only the file
location was wrong. Interleaved per run_id (not two separate
concatenated blocks) to match orchestrate_cp.py's own _run_one() order
exactly.

"runs" used to come from local data/cp_raw/manifest.json - changed
2026-09-16, Keith's hard rule: CI must never touch data, only committed
history. Same fix as the BDM builder - see that file's own docstring.

Run as `python3 -m qa_tools.cp.build_results_from_history`.
"""
from __future__ import annotations
import json
import os

from qa_tools.common import hierarchy
from qa_tools.common.qa_results_reader import read_cross_table_results  # noqa: F401
from qa_tools.common.qa_results_reader import list_run_ids, read_dataset_stats, read_one, TOOL_ORDER
from . import cp_common
from qa_tools.common import asset_time

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_cp.json")


def build_results_from_history() -> dict:
    run_ids = list_run_ids(cp_common.AGENCY_ID, cp_common.COLLECTION_ID)

    manifest = []
    dataset_stats_by_run = {}
    for run_id in run_ids:
        stats = read_dataset_stats(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id)
        if stats is None:
            continue
        manifest.append(stats["arrival_record"])
        dataset_stats_by_run[run_id] = stats
    manifest.sort(key=lambda m: m["run_index"])

    all_results: list[dict] = []
    for entry in manifest:
        run_id = entry["run_id"]
        for tool in TOOL_ORDER:
            all_results.extend(read_one(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, tool))
    # THE CROSS-TABLE SCOPE IS A SIBLING OF THE RUN DIRECTORIES, so a
    # walk of the run ids does not reach it (REQ-QAC-037 criterion 1).
    # Missing this is not a visible failure: the live run assembles its
    # results in memory and looks perfectly correct, while THIS path -
    # the one CI rebuilds the published dashboard from - quietly drops
    # every cross-table check. Measured when it happened: 3,204 results
    # live against 2,772 rebuilt, with all 126 relationships_soda and
    # 126 relationships_dbt gone and nothing anywhere saying so.
    all_results.extend(read_cross_table_results(
        cp_common.AGENCY_ID, cp_common.COLLECTION_ID))

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")

    output = {
        "generated_at": asset_time.now().isoformat(),
        "collection": f"{cp_common.AGENCY_ID}.{cp_common.COLLECTION_ID}",
        "datasets": sorted(d.dataset_id for d in hierarchy.datasets_in_collection(cp_common.COLLECTION_ID)),
        "runs": manifest,
        "dataset_stats": dataset_stats_by_run,
        "results": all_results,
        "summary": {
            "total_checks": len(all_results),
            "pass": n_pass,
            "warn": n_warn,
            "fail": n_fail,
            "error": n_error,
            "engines": sorted(set(r["engine"] for r in all_results)),
        },
    }

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{len(all_results)} real check results ({n_pass} pass / {n_warn} warn / {n_fail} fail"
          f"{f' / {n_error} error' if n_error else ''}) across {len(manifest)} runs, "
          f"from committed history -> {RESULTS_PATH}")
    return output


if __name__ == "__main__":
    build_results_from_history()
