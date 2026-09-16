"""
Rebuilds reports/results_bdm.json purely from Phase 1/2/3's committed
qa_results/ history - the read side of plans/publishing-and-history.md
Thread B. Runs no real tool, touches no local data of any kind (not
`data/raw/`, not any DuckDB warehouse) - every number it needs, check
results AND the "runs" manifest AND the presentation-layer stats
(value-counts/arrival/check-aggregates), was already resolved and
committed at run time (qa_results_writer.py's own docstring; qa_tools/
bdm/dataset_stats.py's for the stats/manifest side specifically).

"runs" used to be sourced from local, regenerated data/raw/manifest.json
(Phase 2's own deliberate scope boundary) - changed 2026-09-16, Keith's
hard rule: CI must never touch data, only committed history, full stop,
not even this project's own synthetic stand-in for it. Each run's own
manifest entry is now embedded in its own committed dataset_stats.json
(orchestrate_bdm.py writes it, reading data/raw/manifest.json itself -
the one place with legitimate access) - reconstructed here by reading
every committed run back, not the local file.

Run as `python3 -m qa_tools.bdm.build_results_from_history`. Produces
the exact same reports/results_bdm.json shape orchestrate_bdm.py does
(now including "dataset_stats"), so pipeline/build_dashboard_data.py
(downstream) needs no changes to consume it - just to stop live-querying
a warehouse of its own, which is Phase 3's other half.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone

from qa_tools.common.qa_results_reader import list_run_ids, read_dataset_stats, read_qa_results

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RESULTS_PATH = os.path.join(ROOT, "reports", "results_bdm.json")

AGENCY_ID = "registry-services"
DATASET_ID = "birth-registrations"


def build_results_from_history() -> dict:
    run_ids = list_run_ids(AGENCY_ID, DATASET_ID)

    manifest = []
    dataset_stats_by_run = {}
    for run_id in run_ids:
        stats = read_dataset_stats(AGENCY_ID, DATASET_ID, run_id)
        if stats is None:
            continue  # shouldn't happen for any real committed run - see dataset_stats.py
        manifest.append(stats["manifest_entry"])
        dataset_stats_by_run[run_id] = stats
    # run_index (not run_date) matches the original generation order - a
    # resupply attempt's own run_date is when it actually arrived, which
    # sorts it away from its parent delivery; run_index doesn't.
    manifest.sort(key=lambda m: m["run_index"])

    all_results = read_qa_results(AGENCY_ID, DATASET_ID)

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")
    n_error = sum(1 for r in all_results if r["status"] == "error")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "registry-services.civil-registration.birth-registrations",
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
