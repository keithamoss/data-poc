"""
Rebuilds reports/results_cp.json purely from Phase 1's committed
qa_results/ history - the Child Protection counterpart to
qa_tools/bdm/build_results_from_history.py (see that file's own
docstring for the full rationale). Runs no real tool, touches no
per-run DuckDB/CSV data.

Reads two qa_results/ dataset segments per run, not one - dbt/Soda/
datacontract-cli each run once across all 6 CP tables (written under
the collection id, cp_common.COLLECTION_ID), while Evidently is scoped
to cp_notifications alone and writes under its own table-scoped dataset
id (cp_common.TABLE_DATASET_ID["cp_notifications"]) - see
qa_results_writer.py callers' own AGENCY_ID/DATASET_ID/COLLECTION_ID
constants. Interleaved per run_id (not two separate concatenated
blocks) to match orchestrate_cp.py's own _run_one() order exactly.

"runs" still comes from local data/cp_raw/manifest.json, not
qa_results/ - same Thread B scope boundary as the BDM builder (tool
RESULTS only, not generator-run metadata).

Run as `python3 -m qa_tools.cp.build_results_from_history`.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone

from qa_tools.common.qa_results_reader import read_one, TOOL_ORDER
from . import cp_common

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
MANIFEST_PATH = os.path.join(ROOT, "data", "cp_raw", "manifest.json")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_cp.json")

_EVIDENTLY_DATASET_ID = cp_common.TABLE_DATASET_ID["cp_notifications"]


def build_results_from_history() -> dict:
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    all_results: list[dict] = []
    for entry in manifest:
        run_id = entry["run_id"]
        for tool in TOOL_ORDER:
            dataset = _EVIDENTLY_DATASET_ID if tool == "evidently" else cp_common.COLLECTION_ID
            all_results.extend(read_one(cp_common.AGENCY_ID, dataset, run_id, tool))

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": f"{cp_common.AGENCY_ID}.{cp_common.COLLECTION_ID}",
        "datasets": sorted(cp_common.TABLE_DATASET_ID.values()),
        "runs": manifest,
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
