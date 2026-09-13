"""
Runs REAL dbt-core (dbt-duckdb adapter) against this project's actual
dbt_project/ - `dbt run` then `dbt test`, once per run, each pointed at its
own single-run DuckDB file under data/duckdb_runs/ (see
build_per_run_warehouses.py's docstring for why one file per run rather
than the combined warehouse.duckdb).

Parses dbt's own target/manifest.json (test metadata: column, test type,
config) and target/run_results.json (status, failures) - not a
reimplementation of dbt's test logic, this genuinely shells out to the
`dbt` CLI and reads what it reports.

For the two tests with a percentage fail_calc override (see schema.yml's
comments for why that override was necessary), dbt's own "failures" number
IS the rounded percentage, not a row count - a second, exact row-count
query is run directly against the same per-run DuckDB file purely to
populate this project's row_count_invalid field for the dashboard/report,
without touching dbt's own pass/warn/fail decision at all.
"""
from __future__ import annotations
import json
import os
import re
import subprocess

import duckdb

ROOT = os.path.join(os.path.dirname(__file__), "..")
DBT_PROJECT_DIR = os.path.join(ROOT, "dbt_project")
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "dbt_profiles")
DUCKDB_RUNS_DIR = os.path.join(ROOT, "data", "duckdb_runs")

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"
ENGINE_TAG = "dbt-core 1.12 + dbt-duckdb (real)"

# column/test combos whose fail_calc was overridden to report a rounded
# percentage rather than a raw row count - see schema.yml. Maps to the exact
# SQL used to compute the real invalid row count for row_count_invalid.
_EXACT_COUNT_SQL = {
    ("sex", "accepted_values"): "SELECT COUNT(*) FROM stg_birth_registrations WHERE sex NOT IN ('M','F','X')",
    ("place_of_birth_facility", "not_null"): "SELECT COUNT(*) FROM stg_birth_registrations WHERE place_of_birth_facility IS NULL",
}

_NUM_RE = re.compile(r"([\d.]+)")


def _parse_threshold(spec: str | None) -> float | None:
    if spec is None or spec.strip() == "!= 0":
        return None
    m = _NUM_RE.search(spec)
    return float(m.group(1)) if m else None


def _run_dbt(db_path: str, command: str) -> None:
    env = dict(os.environ)
    env["DBT_DB_PATH"] = db_path
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    subprocess.run(
        ["dbt", command, "--profiles-dir", PROFILES_DIR, "--project-dir", DBT_PROJECT_DIR, "--quiet"],
        env=env, cwd=ROOT, check=False, capture_output=True, text=True,
    )


def _test_nodes(manifest: dict) -> dict[str, dict]:
    return {
        uid: node for uid, node in manifest["nodes"].items()
        if node.get("resource_type") == "test"
    }


def evaluate_dbt_real(run_id: str, run_timestamp: str) -> list[dict]:
    db_path = os.path.join(DUCKDB_RUNS_DIR, f"{run_id}.duckdb")
    _run_dbt(db_path, "run")
    _run_dbt(db_path, "test")

    with open(os.path.join(DBT_PROJECT_DIR, "target", "manifest.json")) as f:
        manifest = json.load(f)
    with open(os.path.join(DBT_PROJECT_DIR, "target", "run_results.json")) as f:
        run_results = json.load(f)

    nodes = _test_nodes(manifest)
    conn = duckdb.connect(db_path, read_only=True)
    n_total = conn.execute("SELECT COUNT(*) FROM stg_birth_registrations").fetchone()[0]

    results = []
    for r in run_results["results"]:
        node = nodes.get(r["unique_id"])
        if node is None:
            continue
        meta = node["test_metadata"]
        test_name = meta["name"]
        column = node["column_name"]
        config = node["config"]
        failures = r.get("failures") or 0
        status = r["status"]
        if status == "error":
            # a real execution failure (bad SQL, missing table, etc.), not a
            # data-quality result - surfaced as-is rather than silently
            # dropped or mapped onto pass/warn/fail.
            status = "error"

        key = (column, test_name)
        is_pct = key in _EXACT_COUNT_SQL
        unit = "%" if is_pct else "count"
        if is_pct:
            row_count_invalid = conn.execute(_EXACT_COUNT_SQL[key]).fetchone()[0]
        else:
            row_count_invalid = failures

        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            "column_name": column,
            "check_name": f"dbt:{test_name}",
            "dimension": "uniqueness" if test_name == "unique" else
                         "completeness" if test_name == "not_null" else "validity",
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": failures,
            "unit": unit,
            "warn_threshold": _parse_threshold(config.get("warn_if")),
            "fail_threshold": _parse_threshold(config.get("error_if")),
            "status": status,
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
        res = evaluate_dbt_real(run_id, datetime.now(timezone.utc).isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            print(" ", r["column_name"], r["check_name"], r["status"], r["metric_value"], r["unit"])
