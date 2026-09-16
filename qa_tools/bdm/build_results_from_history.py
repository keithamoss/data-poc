"""
Rebuilds reports/results_bdm.json purely from Phase 1's committed
qa_results/ history - the read side of plans/publishing-and-history.md
Thread B/Phase 2. Unlike orchestrate_bdm.py, this runs no real tool and
touches no per-run DuckDB warehouse - every check-result number it needs
(including dbt's audit-corrected failures/status and Soda's row-count
totals) was already resolved and committed at run time, in each tool's
own `verified` field - see qa_results_writer.py's own docstring for why.

"runs" (data/raw/manifest.json's own generator-run metadata - delivery
dates, resupply chains, dirty_severity) stays sourced from local,
regenerated data/raw/ rather than qa_results/, matching Thread B's
explicit scope: tool RESULTS only, not the underlying synthetic-data
generation metadata (plans/publishing-and-history.md's own "Confirmed
explicitly with Keith" bullet). So this still needs data/raw/
manifest.json to exist locally (run ./run_pipeline.sh's first step, or
generator.generate_runs, if it doesn't) - just not data/duckdb_runs/ or
data/warehouse.duckdb.

Run as `python3 -m qa_tools.bdm.build_results_from_history`. Produces
the exact same reports/results_bdm.json shape orchestrate_bdm.py does,
so pipeline/build_dashboard_data.py (downstream) needs no changes.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone

from qa_tools.common.qa_results_reader import read_qa_results

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
MANIFEST_PATH = os.path.join(ROOT, "data", "raw", "manifest.json")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_bdm.json")

AGENCY_ID = "registry-services"
DATASET_ID = "birth-registrations"


def build_results_from_history() -> dict:
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    all_results = read_qa_results(AGENCY_ID, DATASET_ID)

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
          f"{f' / {n_error} error' if n_error else ''}) across {len(manifest)} runs, "
          f"from committed history -> {RESULTS_PATH}")
    return output


if __name__ == "__main__":
    build_results_from_history()
