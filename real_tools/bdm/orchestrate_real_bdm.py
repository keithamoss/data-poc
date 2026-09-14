"""
Runs all four REAL tools (dbt-core, Soda Core, datacontract-cli, Evidently)
against every generated Birth Registrations run. Aggregates into
reports/results_real.json. The Child Protection counterpart is
real_tools/cp/orchestrate_real_cp.py.

Runs the manifest's runs IN PARALLEL by default (real_tools/common/
parallel_orchestrate.py, one process per CPU core - measured ~3.4x on
this project's own 15-run manifest, see plans/performance.md #4), with a
--sequential flag for easier debugging (parallel workers interleave their
print output and stack traces; a single run under investigation is
simpler to chase down sequentially). Either way, results come back in
manifest order, so output stays byte-for-byte reproducible for a given
manifest.

Assumes data/raw/ (generator output), data/warehouse.duckdb (the combined
warehouse, still built by pipeline/load.py/orchestrate.py - see that
file's docstring for why it's still needed) and data/duckdb_runs/*.duckdb
(per-run real warehouses, real_tools/bdm/build_per_run_warehouses.py)
already exist - run ./run_pipeline.sh first if they don't.

Run as `python3 -m real_tools.bdm.orchestrate_real_bdm` (this is a package
now, not a flat script directory - see plans/wider.md #20).
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone

from real_tools.common import parallel_orchestrate
from . import build_per_run_warehouses
from . import run_dbt_real_bdm
from . import run_soda_real_bdm
from . import run_datacontract_real_bdm
from . import run_evidently_real_bdm

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
MANIFEST_PATH = os.path.join(ROOT, "data", "raw", "manifest.json")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_real.json")


def _run_one(entry: dict, run_timestamp: str) -> list[dict]:
    run_id = entry["run_id"]
    csv_filename = entry["file"]
    print(f"--- {run_id} ---")

    results: list[dict] = []
    results.extend(run_dbt_real_bdm.evaluate_dbt_real_bdm(run_id, run_timestamp))
    results.extend(run_soda_real_bdm.evaluate_soda_real_bdm(run_id, run_timestamp))
    results.extend(run_datacontract_real_bdm.evaluate_datacontract_real_bdm(run_id, csv_filename, run_timestamp))
    results.extend(run_evidently_real_bdm.evaluate_evidently_real_bdm(run_id, csv_filename, run_timestamp))
    return results


def run_real_pipeline(sequential: bool = False) -> dict:
    build_per_run_warehouses.build_all()

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    run_timestamp = datetime.now(timezone.utc).isoformat()
    all_results = parallel_orchestrate.run_manifest(manifest, _run_one, run_timestamp, sequential=sequential)

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
    run_real_pipeline(sequential="--sequential" in sys.argv)
