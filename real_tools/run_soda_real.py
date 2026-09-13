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


# "failed rows" checks (extract_timestamp ordering, the multiple-birth
# sibling match) have no natural `column` of their own to report - Soda
# scopes them to the whole table, same class of gap
# run_datacontract_real_cp.py solves for datacontract-cli's table-level
# type: sql rules. Routed here by the check's own custom `name:` (the only
# stable identifier a "failed rows" check carries) to the column each rule
# is actually about, so it lands on a real column tile instead of falling
# into "(table)" - which birth-registrations' dashboard builder silently
# drops (there's no "(table-level checks)" pseudo-column here).
_CUSTOM_CHECK_COLUMN = {
    "extract timestamp is logically ordered after date_registered": "extract_timestamp",
    "multiple birth records have a matching sibling": "is_multiple_birth",
}

# A short, human-readable phrase shared with the same rule's dbt/
# datacontract-cli check, so the dashboard makes the overlap obvious -
# same rationale as _CUSTOM_CHECK_COLUMN above.
_CUSTOM_CHECK_LABEL = {
    "extract timestamp is logically ordered after date_registered": "Timestamp ordering",
    "multiple birth records have a matching sibling": "Sibling record match",
}

# Explicit per-metric dimension, rather than a substring guess against
# base_check - a substring check ("validity" if "invalid" in base_check
# else "completeness") missed the one pre-existing custom-named check in
# this file ("sex validity, last 24h only" contains "validity", not
# "invalid" - found and fixed earlier, see plans/qa-pipeline.md #10) and
# would mislabel duplicate_count (uniqueness, not completeness) and both
# new "failed rows" checks (consistency) the same way if left as a guess.
_DIMENSION_BY_BASE_CHECK = {
    "missing_count": "completeness",
    "missing_percent": "completeness",
    "invalid_percent": "validity",
    "duplicate_count": "uniqueness",
    "row_count": "completeness",
}

# Dimension for every custom-named check (c["metrics"] empty, or a scoped
# filter check) - these have no real metric name of their own for
# _DIMENSION_BY_BASE_CHECK to key off, so each is named explicitly instead.
_CUSTOM_CHECK_DIMENSION = {
    "sex validity, last 24h only": "validity",
    "extract timestamp is logically ordered after date_registered": "consistency",
    "multiple birth records have a matching sibling": "consistency",
}


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
        scope = c["filter"] or "all"
        diagnostics = c["diagnostics"]
        value = diagnostics.get("value")
        outcome = c["outcome"]  # "pass" | "warn" | "fail"

        # the real check type (row_count/missing_count/invalid_percent/
        # missing_percent/duplicate_count) comes from the metric this check
        # reads, not from parsing c["name"] - custom-named checks (a
        # scoped filter check, or a "failed rows" check with no metric at
        # all) have a custom `name:` in the YAML that doesn't follow the
        # generic pattern. c["metrics"] is empty for a "failed rows" check
        # (no underlying metric object), hence the guard.
        base_check = metric_name_by_id.get(c["metrics"][0], c["name"]) if c["metrics"] else c["name"]
        # Soda's auto-generated check name is the whole check line ("...
        # warn when > 0 fail when > 5") - a real custom `name:` reads as a
        # short label with no "when".
        is_custom_name = "when" not in c["name"]
        check_name = c["name"] if is_custom_name else f"{base_check}[{scope}]"
        is_pct = base_check.endswith("percent")

        column = c["column"] or (_CUSTOM_CHECK_COLUMN.get(c["name"]) if is_custom_name else None) or "(table)"

        row_count_invalid = None
        if diagnostics.get("blocks"):
            row_count_invalid = diagnostics["blocks"][0].get("totalFailingRows")
        elif base_check == "missing_count":
            row_count_invalid = int(value) if value is not None else None
        elif base_check == "row_count":
            row_count_invalid = 0
        elif is_custom_name and c["name"] in _CUSTOM_CHECK_COLUMN:
            # a "failed rows" check's own value IS the failing-row count.
            row_count_invalid = int(value) if value is not None else None

        # A short, human-readable phrase for what this check actually
        # measures - written here, where the check result is constructed,
        # not guessed later from check_name by the dashboard-building
        # code. None for a custom-named check with no dashboard-visible
        # counterpart (only "sex validity, last 24h only" today): its own
        # name is already plain. The 2 "failed rows" checks DO get an
        # explicit shared label - see _CUSTOM_CHECK_LABEL's own comment.
        label = _CUSTOM_CHECK_LABEL.get(c["name"]) if is_custom_name else {
            "missing_count": "Null rate", "missing_percent": "Null rate",
            "invalid_percent": "Invalid values", "row_count": "Row count",
            "duplicate_count": "Duplicate rate",
        }.get(base_check)

        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            "column_name": column,
            "check_name": check_name,
            "dimension": _CUSTOM_CHECK_DIMENSION.get(c["name"]) if is_custom_name
                         else _DIMENSION_BY_BASE_CHECK.get(base_check, ""),
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
