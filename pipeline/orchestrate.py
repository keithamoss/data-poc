"""
End-to-end orchestrator: generate -> load -> run all four engines against
every run -> aggregate into reports/results.json, in the check-result
record shape used across this project.

This is the "set up the repo to run that end to end... generate the
reports and data behind it" piece of the brief - running this one script
regenerates the whole pipeline's output from scratch, deterministically
(every generator call is seeded).
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "generator"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engines"))
sys.path.insert(0, os.path.dirname(__file__))

ROOT = os.path.join(os.path.dirname(__file__), "..")
CONTRACT_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-contract.yaml")
SODA_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-soda-checks.yml")
DBT_PROJECT_DIR = os.path.join(ROOT, "dbt_project")
DB_PATH = os.path.join(ROOT, "data", "warehouse.duckdb")
MANIFEST_PATH = os.path.join(ROOT, "data", "raw", "manifest.json")
RESULTS_PATH = os.path.join(ROOT, "reports", "results.json")


def run_pipeline(regenerate: bool = True) -> dict:
    if regenerate:
        import generate_runs
        generate_runs.main()

    import load as load_mod
    load_mod.load_all(DB_PATH, os.path.join(ROOT, "data", "raw"))

    import contract_engine
    import soda_engine
    import dbt_test_engine
    import evidently_engine

    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    run_timestamp = datetime.utcnow().isoformat()
    all_results: list[dict] = []

    for entry in manifest:
        run_id = entry["run_id"]
        all_results.extend(contract_engine.evaluate_contract(CONTRACT_PATH, DB_PATH, run_id, run_timestamp))
        all_results.extend(soda_engine.evaluate_soda(SODA_PATH, DB_PATH, run_id, run_timestamp))
        all_results.extend(dbt_test_engine.evaluate_dbt_tests(DBT_PROJECT_DIR, DB_PATH, run_id, run_timestamp))
        all_results.extend(evidently_engine.evaluate_drift(DB_PATH, run_id, run_timestamp))

    n_pass = sum(1 for r in all_results if r["status"] == "pass")
    n_warn = sum(1 for r in all_results if r["status"] == "warn")
    n_fail = sum(1 for r in all_results if r["status"] == "fail")

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
            "engines": sorted(set(r["engine"] for r in all_results)),
        },
    }

    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"{len(all_results)} check results ({n_pass} pass / {n_warn} warn / {n_fail} fail) "
          f"across {len(manifest)} runs -> {RESULTS_PATH}")
    return output


if __name__ == "__main__":
    run_pipeline(regenerate=True)
