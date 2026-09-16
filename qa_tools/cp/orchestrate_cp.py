"""
Runs all four REAL tools (dbt-core, Soda Core, datacontract-cli, Evidently)
against every generated Child Protection snapshot run - the CP counterpart
to qa_tools/bdm/orchestrate_bdm.py. Aggregates into
reports/results_cp.json, same check-result record shape
(agency_id/collection_id/dataset_id/...) as reports/results_bdm.json,
except dataset_id varies per result across the 6 CP tables instead of
being one constant.

Runs the manifest's runs IN PARALLEL by default (qa_tools/common/
parallel_orchestrate.py, shared with orchestrate_bdm.py - see that
file's docstring and plans/performance.md #4), with a --sequential flag
for easier debugging.

Assumes data/cp_raw/ (generator/generate_cp_runs.py's output) already
exists - run that first if it doesn't. Builds data/cp_duckdb_runs/ itself
via build_cp_warehouses.build_all().

Run as `python3 -m qa_tools.cp.orchestrate_cp` (this is a package
now, not a flat script directory - see plans/wider.md #20).
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

import duckdb

from qa_tools.common import parallel_orchestrate
from qa_tools.common.qa_results_reader import read_dataset_stats
from qa_tools.common.qa_results_writer import write_qa_result
from . import build_cp_warehouses
from . import cp_common
from . import dataset_stats
from . import run_dbt_cp
from . import run_soda_cp
from . import run_datacontract_cp
from . import run_evidently_cp

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
MANIFEST_PATH = os.path.join(ROOT, "data", "cp_raw", "manifest.json")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_cp.json")
CP_DUCKDB_RUNS_DIR = os.path.join(ROOT, "data", "cp_duckdb_runs")


def _run_one(entry: dict, run_timestamp: str, reference_run_id: str) -> list[dict]:
    run_id = entry["run_id"]
    print(f"--- {run_id} ---")

    results: list[dict] = []
    results.extend(run_dbt_cp.evaluate_dbt_cp(run_id, run_timestamp))
    results.extend(run_soda_cp.evaluate_soda_cp(run_id, run_timestamp))
    results.extend(run_datacontract_cp.evaluate_datacontract_cp(run_id, run_timestamp))
    results.extend(run_evidently_cp.evaluate_evidently_cp(run_id, run_timestamp, reference_run_id=reference_run_id))

    # Same rationale as orchestrate_bdm.py's identical block - see
    # qa_tools/bdm/dataset_stats.py's own docstring.
    conn = duckdb.connect(os.path.join(CP_DUCKDB_RUNS_DIR, f"{run_id}.duckdb"), read_only=True)
    stats = dataset_stats.compute_dataset_stats(conn, entry)
    conn.close()
    write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp, "dataset_stats", stats)

    return results


def run_pipeline_cp(sequential: bool = False) -> dict:
    build_cp_warehouses.build_all()

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    # The first manifest entry (cp_run_01, always clean by RUN_PLAN
    # construction) - NOT run_evidently_cp.REFERENCE_RUN_ID, a hardcoded
    # literal that goes stale every time the anchor date rolls forward
    # (generator/anchor_date.py) - see orchestrate_bdm.py's identical fix
    # and plans/qa-pipeline.md for the bug this was found as.
    reference_run_id = manifest[0]["run_id"]
    run_timestamp = datetime.now(timezone.utc).isoformat()
    all_results = parallel_orchestrate.run_manifest(
        manifest, _run_one, run_timestamp, reference_run_id, sequential=sequential)

    # Same rationale as orchestrate_bdm.py's identical block.
    dataset_stats_by_run = {}
    for entry in manifest:
        stats = read_dataset_stats(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, entry["run_id"])
        if stats is not None:
            dataset_stats_by_run[entry["run_id"]] = stats

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")

    output = {
        "generated_at": run_timestamp,
        "dataset_stats": dataset_stats_by_run,
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
          f"{f' / {n_error} error' if n_error else ''}) across {len(manifest)} runs -> {RESULTS_PATH}")
    return output


if __name__ == "__main__":
    run_pipeline_cp(sequential="--sequential" in sys.argv)
