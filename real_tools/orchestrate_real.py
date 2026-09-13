"""
Runs all four REAL tools (dbt-core, Soda Core, datacontract-cli, Evidently)
against every generated run, the real-tool counterpart to
pipeline/orchestrate.py (which runs the four Python equivalents in
engines/). Aggregates into reports/results_real.json, same check-result
record shape as reports/results.json so the two can be diffed directly.

Assumes data/raw/ (generator output), data/warehouse.duckdb (the combined
equivalent-engine warehouse) and data/duckdb_runs/*.duckdb (per-run real
warehouses, real_tools/build_per_run_warehouses.py) already exist - run
./run_pipeline.sh first if they don't.
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import build_per_run_warehouses
import run_dbt_real
import run_soda_real
import run_datacontract_real
import run_evidently_real

ROOT = os.path.join(os.path.dirname(__file__), "..")
MANIFEST_PATH = os.path.join(ROOT, "data", "raw", "manifest.json")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_real.json")


def run_real_pipeline() -> dict:
    build_per_run_warehouses.build_all()

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    run_timestamp = datetime.now(timezone.utc).isoformat()
    all_results: list[dict] = []

    for entry in manifest:
        run_id = entry["run_id"]
        csv_filename = entry["file"]
        print(f"--- {run_id} ---")

        all_results.extend(run_dbt_real.evaluate_dbt_real(run_id, run_timestamp))
        all_results.extend(run_soda_real.evaluate_soda_real(run_id, run_timestamp))
        all_results.extend(run_datacontract_real.evaluate_datacontract_real(run_id, csv_filename, run_timestamp))
        all_results.extend(run_evidently_real.evaluate_evidently_real(run_id, csv_filename, run_timestamp))

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")

    output = {
        "generated_at": run_timestamp,
        "dataset": "registry-services.civil-registration.birth-registrations",
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
    run_real_pipeline()
