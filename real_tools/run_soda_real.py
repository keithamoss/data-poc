"""
Runs REAL Soda Core (soda-core-duckdb) against this project's actual
contract/bdm-birth-registrations-soda-checks.yml, via Soda's own Python
Scan API (add_duckdb_connection + add_sodacl_yaml_file) - not a
reimplementation, this hands the real SodaCL file to the real soda-core
engine and reads back its own scan results.

Run once per run against its own per-run DuckDB file (same rationale as
real_tools/run_dbt_real.py - the checks file has no run_id-scoped `where`,
so the daily-batch reality is one file per day, one scan per day).

Genuine, real finding from actually running this (documented in README.md,
not "fixed" away): the `filter birth_registrations [recent]: where:
extract_timestamp >= CURRENT_DATE - 1` block uses Soda's real CURRENT_DATE,
i.e. today's actual wall-clock date - not, as engines/soda_engine.py's
equivalent assumed for lack of a real "now", the latest extract_timestamp
in the run. Since every synthetic run's dates are in the past relative to
whenever this actually runs, the [recent] filter scopes to 0 rows for every
historical run, and its check always reports "pass" (0/0) - a real
divergence from the equivalent's per-run "as-of" interpretation, not a bug
in either engine.
"""
from __future__ import annotations
import os

import duckdb

ROOT = os.path.join(os.path.dirname(__file__), "..")
SODA_CHECKS_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-soda-checks.yml")
DUCKDB_RUNS_DIR = os.path.join(ROOT, "data", "duckdb_runs")

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"
ENGINE_TAG = "Soda Core 3.5 (real)"


def _threshold(spec: dict | None) -> float | None:
    if not spec:
        return None
    for key in ("greaterThan", "greaterThanOrEqual"):
        if key in spec:
            return spec[key]
    # a lower-bound-only spec (row_count's warn/fail also carry a lessThan
    # side) - same "upper bound wins for a single scalar" convention the
    # equivalent engine's _numeric_threshold() documents.
    return next(iter(spec.values()), None)


def evaluate_soda_real(run_id: str, run_timestamp: str) -> list[dict]:
    from soda.scan import Scan

    db_path = os.path.join(DUCKDB_RUNS_DIR, f"{run_id}.duckdb")
    conn = duckdb.connect(db_path, read_only=True)
    # dbt's source config puts the loaded table in a schema literally named
    # "raw" (see build_per_run_warehouses.py) - Soda's checks file refers to
    # the bare table name, so it needs "raw" on the search path to resolve.
    conn.execute("SET search_path = 'raw'")
    n_total = conn.execute("SELECT COUNT(*) FROM birth_registrations").fetchone()[0]

    scan = Scan()
    scan.set_data_source_name("birth_registrations")
    scan.add_duckdb_connection(conn, data_source_name="birth_registrations")
    scan.add_sodacl_yaml_file(SODA_CHECKS_PATH)
    scan.disable_telemetry()
    scan.execute()
    scan_results = scan.get_scan_results()
    metric_name_by_id = {m["identity"]: m["metricName"] for m in scan_results["metrics"]}

    results = []
    for c in scan_results["checks"]:
        column = c["column"] or "(table)"
        scope = c["filter"] or "all"
        diagnostics = c["diagnostics"]
        value = diagnostics.get("value")
        outcome = c["outcome"]  # "pass" | "warn" | "fail"

        # the real check type (row_count/missing_count/invalid_percent/
        # missing_percent) comes from the metric this check reads, not from
        # parsing c["name"] - the scoped [recent] check has a custom `name:`
        # in the YAML ("sex validity, last 24h only") that doesn't follow
        # the generic pattern at all.
        base_check = metric_name_by_id.get(c["metrics"][0], c["name"])
        # Soda's auto-generated check name is the whole check line ("...
        # warn when > 0 fail when > 5") - a real custom `name:` (only the
        # [recent] sex check has one) reads as a short label with no "when".
        is_custom_name = "when" not in c["name"]
        check_name = c["name"] if is_custom_name else f"{base_check}[{scope}]"
        is_pct = base_check.endswith("percent")

        row_count_invalid = None
        if diagnostics.get("blocks"):
            row_count_invalid = diagnostics["blocks"][0].get("totalFailingRows")
        elif base_check == "missing_count":
            row_count_invalid = int(value) if value is not None else None
        elif base_check == "row_count":
            row_count_invalid = 0

        # A short, human-readable phrase for what this check actually
        # measures - written here, where the check result is constructed,
        # not guessed later from check_name by the dashboard-building
        # code. None for a custom-named check (only "sex validity, last
        # 24h only" today): its own name is already plain.
        label = None if is_custom_name else {
            "missing_count": "Null rate", "missing_percent": "Null rate",
            "invalid_percent": "Invalid values", "row_count": "Row count",
        }.get(base_check)

        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            "column_name": column,
            "check_name": check_name,
            "dimension": "validity" if "invalid" in base_check else "completeness",
            "label": label,
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": value,
            "unit": "%" if is_pct else "count",
            "warn_threshold": _threshold(diagnostics.get("warn")),
            "fail_threshold": _threshold(diagnostics.get("fail")),
            "status": outcome,
            "on_fail_action": "flag",
            "row_count_total": n_total,
            "row_count_invalid": row_count_invalid,
            "engine": ENGINE_TAG,
        })

    conn.close()
    return results


if __name__ == "__main__":
    from datetime import datetime, timezone
    for run_id in ["run_01_2026-09-01", "run_04_2026-09-04", "run_09_2026-09-09"]:
        res = evaluate_soda_real(run_id, datetime.now(timezone.utc).isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            print(" ", r["column_name"], r["check_name"], r["status"], r["metric_value"], r["unit"])
