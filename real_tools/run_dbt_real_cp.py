"""
Runs REAL dbt-core (dbt-duckdb adapter) against this project's actual
dbt_project/ for the Child Protection collection - the CP counterpart to
run_dbt_real.py, scoped to the 6 stg_cp_* models and their tests (PK
unique/not_null, the 7 `relationships` tests, and the 3 singular
cross-table business-rule tests) rather than stg_birth_registrations,
via `dbt run`/`dbt test --select <the 6 CP models + the 3 singular test
names>` - an explicit node list rather than a graph selector, so this
never accidentally pulls in (or silently skips) a birth-registrations
test if the project's DAG shape changes later.

Each run is pointed at its own single-run CP DuckDB file under
data/cp_duckdb_runs/ (real_tools/build_cp_warehouses.py) - same
per-run-warehouse rationale as run_dbt_real.py's docstring.

Which of the 6 CP tables a test result belongs to (for the dashboard's
dataset_id) comes from dbt's own `attached_node` on the test's manifest
entry for generic tests (unique/not_null/relationships - the model the
test is declared under, not necessarily the first of the tables it
depends on), and from cp_common.BUSINESS_RULE_HOME_TABLE for the 3
singular tests (which have no attached_node at all - they're not
column/model-scoped).
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys

import duckdb

sys.path.insert(0, os.path.dirname(__file__))
import cp_common

ROOT = os.path.join(os.path.dirname(__file__), "..")
DBT_PROJECT_DIR = os.path.join(ROOT, "dbt_project")
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "dbt_profiles")
CP_DUCKDB_RUNS_DIR = os.path.join(ROOT, "data", "cp_duckdb_runs")

ENGINE_TAG = "dbt-core 1.12 + dbt-duckdb (real)"

CP_MODELS = [f"stg_{t}" for t in cp_common.TABLES]
CP_SINGULAR_TESTS = list(cp_common.BUSINESS_RULE_HOME_TABLE.keys())

_NUM_RE = re.compile(r"([\d.]+)")

_DIMENSION_BY_TEST = {
    "unique": "uniqueness",
    "not_null": "completeness",
    "relationships": "consistency",
    "escalation_completeness": "completeness",
    "closed_case_investigation_hygiene": "consistency",
    "placement_carer_approval": "consistency",
}


def _parse_threshold(spec: str | None) -> float | None:
    if spec is None or spec.strip() == "!= 0":
        return None
    m = _NUM_RE.search(spec)
    return float(m.group(1)) if m else None


def _run_dbt(db_path: str, command: str, select: list[str]) -> None:
    env = dict(os.environ)
    env["DBT_DB_PATH"] = db_path
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    subprocess.run(
        ["dbt", command, "--profiles-dir", PROFILES_DIR, "--project-dir", DBT_PROJECT_DIR,
         "--quiet", "--select", *select],
        env=env, cwd=ROOT, check=False, capture_output=True, text=True,
    )


def _table_for_test(node: dict) -> str | None:
    meta = node.get("test_metadata")
    if meta is None:
        return cp_common.BUSINESS_RULE_HOME_TABLE.get(node["name"])
    attached = node.get("attached_node")
    if not attached or "stg_cp_" not in attached:
        return None
    model_name = attached.split(".")[-1]  # e.g. "stg_cp_notifications"
    table = model_name.removeprefix("stg_")
    return table if table in cp_common.TABLES else None


def evaluate_dbt_real_cp(run_id: str, run_timestamp: str) -> list[dict]:
    db_path = os.path.join(CP_DUCKDB_RUNS_DIR, f"{run_id}.duckdb")
    # A single `dbt build` (build the 6 models, then run their tests)
    # instead of separate `dbt run` + `dbt test` calls - dbt-core's fixed
    # per-invocation startup cost was being paid twice per run for no
    # benefit; verified directly, this halves the time (9.5s -> 4.2s for
    # one run - see plans/performance.md). run_results.json then also
    # contains the 6 models' own build results, which _table_for_test
    # already silently skips via node["test_metadata"] being absent from
    # non-test nodes entirely (KeyError-safe since we only look them up
    # for uids present in `nodes`, which is test-only).
    _run_dbt(db_path, "build", CP_MODELS + CP_SINGULAR_TESTS)

    with open(os.path.join(DBT_PROJECT_DIR, "target", "manifest.json")) as f:
        manifest = json.load(f)
    with open(os.path.join(DBT_PROJECT_DIR, "target", "run_results.json")) as f:
        run_results = json.load(f)

    nodes = {uid: n for uid, n in manifest["nodes"].items() if n.get("resource_type") == "test"}

    conn = duckdb.connect(db_path, read_only=True)
    n_total_by_table = {t: conn.execute(f"SELECT COUNT(*) FROM stg_{t}").fetchone()[0] for t in cp_common.TABLES}

    results = []
    for r in run_results["results"]:
        node = nodes.get(r["unique_id"])
        if node is None:
            continue
        table = _table_for_test(node)
        if table is None:
            continue  # a birth-registrations test, out of scope here

        meta = node.get("test_metadata")
        test_name = meta["name"] if meta else node["name"]
        column = node["column_name"] if meta else "(table)"
        config = node.get("config", {})
        status = r["status"]
        failures = r.get("failures") or 0
        warn_t = _parse_threshold(config.get("warn_if"))
        fail_t = _parse_threshold(config.get("error_if"))

        results.append({
            "agency_id": cp_common.AGENCY_ID,
            "collection_id": cp_common.COLLECTION_ID,
            "dataset_id": cp_common.TABLE_DATASET_ID[table],
            "column_name": column,
            "check_name": f"dbt:{test_name}",
            "dimension": _DIMENSION_BY_TEST.get(test_name, ""),
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": failures,
            "unit": "count",
            "warn_threshold": warn_t,
            "fail_threshold": fail_t,
            "status": status,
            "on_fail_action": "flag",
            "row_count_total": n_total_by_table[table],
            "row_count_invalid": failures,
            "engine": ENGINE_TAG,
        })

    conn.close()
    return results


if __name__ == "__main__":
    from datetime import datetime, timezone
    for run_id in ["cp_run_01_2026-07-06", "cp_run_04_2026-07-27", "cp_run_09_2026-08-31"]:
        res = evaluate_dbt_real_cp(run_id, datetime.now(timezone.utc).isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            if r["status"] != "pass":
                print(" ", r["dataset_id"], r["column_name"], r["check_name"], r["status"], r["metric_value"])
