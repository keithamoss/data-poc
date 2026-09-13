"""
Runs all four REAL tools (dbt-core, Soda Core, datacontract-cli, Evidently)
against every generated Child Protection snapshot run - the CP counterpart
to orchestrate_real.py. Aggregates into reports/results_real_cp.json, same
check-result record shape (agency_id/collection_id/dataset_id/...) as
reports/results_real.json, except dataset_id varies per result across the
6 CP tables instead of being one constant.

Assumes data/cp_raw/ (generator/generate_cp_runs.py's output) already
exists - run that first if it doesn't. Builds data/cp_duckdb_runs/ itself
via build_cp_warehouses.build_all().
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import build_cp_warehouses
import cp_common
import run_dbt_real_cp
import run_soda_real_cp
import run_datacontract_real_cp
import run_evidently_real_cp

ROOT = os.path.join(os.path.dirname(__file__), "..")
MANIFEST_PATH = os.path.join(ROOT, "data", "cp_raw", "manifest.json")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_real_cp.json")


def run_real_pipeline_cp() -> dict:
    build_cp_warehouses.build_all()

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    run_timestamp = datetime.now(timezone.utc).isoformat()
    all_results: list[dict] = []

    for entry in manifest:
        run_id = entry["run_id"]
        print(f"--- {run_id} ---")

        all_results.extend(run_dbt_real_cp.evaluate_dbt_real_cp(run_id, run_timestamp))
        all_results.extend(run_soda_real_cp.evaluate_soda_real_cp(run_id, run_timestamp))
        all_results.extend(run_datacontract_real_cp.evaluate_datacontract_real_cp(run_id, run_timestamp))
        all_results.extend(run_evidently_real_cp.evaluate_evidently_real_cp(run_id, run_timestamp))

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")

    output = {
        "generated_at": run_timestamp,
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
    run_real_pipeline_cp()
