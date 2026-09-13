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

A REAL, confirmed dbt-duckdb reliability problem, not assumed: for the two
custom-configured tests (sex, place_of_birth_facility), dbt's own reported
"failures" value was repeatedly and reproducibly wrong on certain runs -
0 instead of the true row count - while the IDENTICAL compiled SQL,
executed directly via DuckDB's own Python API against the same file,
always gave the right answer. This was chased at length (see schema.yml's
comments and README.md's known-disagreements section): it survived
removing every layer of arithmetic from fail_calc (rounding, casting,
percentage division, even plain count(*) with no override at all),
`--no-partial-parse`, `--store-failures`, and switching COUNT for SUM -
none of it was the cause, and it reproduces on some runs (the clean ones)
but not others (amber/red) with no SQL-level explanation found. Rather
than silently trust a demonstrably-unreliable number from a review tool,
these two checks' metric_value/row_count_invalid/status are independently
recomputed here via a direct query against the same warehouse dbt just
tested - dbt-core still genuinely ran the real check (that's what
`status`/`failures` get compared against, when they can be trusted, and
what "engine" attributes this result to) - only the two known-unreliable
numbers are cross-checked rather than passed through blindly.
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

# column/test combos where dbt's own "failures" value was observed to be
# unreliable (see module docstring) - mapped to the exact SQL used to
# independently recompute the true failing-row count.
_VERIFY_COUNT_SQL = {
    ("sex", "accepted_values"): "SELECT COUNT(*) FROM stg_birth_registrations WHERE sex NOT IN ('M','F','X')",
    ("place_of_birth_facility", "not_null"): "SELECT COUNT(*) FROM stg_birth_registrations WHERE place_of_birth_facility IS NULL",
}

_NUM_RE = re.compile(r"([\d.]+)")

# A short, human-readable phrase for what each test actually checks -
# written here, at the point each check result is constructed (the one
# place that genuinely knows what a check tests), not guessed later from
# the check's name string by the dashboard-building code. None means "this
# check's own name is already plain enough" (not used by this file today,
# but kept for parity with run_dbt_real_cp.py's singular business-rule
# tests, which do use it).
_LABEL_BY_TEST = {
    "unique": "Duplicate rate",
    "not_null": "Null rate",
    "accepted_values": "Invalid values",
}


def _parse_threshold(spec: str | None) -> float | None:
    if spec is None or spec.strip() == "!= 0":
        return None
    m = _NUM_RE.search(spec)
    return float(m.group(1)) if m else None


def _status_for(count: int, warn_t: float | None, fail_t: float | None) -> str:
    if fail_t is not None and count > fail_t:
        return "fail"
    if warn_t is not None and count > warn_t:
        return "warn"
    return "pass"


def _run_dbt(db_path: str, command: str) -> None:
    env = dict(os.environ)
    env["DBT_DB_PATH"] = db_path
    env["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    subprocess.run(
        # --select scopes this to stg_birth_registrations only - required
        # since Phase 2 added 6 Child Protection models + 3 singular tests
        # to this same dbt_project/: an unscoped call picks those up too
        # and (a) errors trying to build them against a birth-registrations
        # -only warehouse that has none of the CP tables, and (b) the CP
        # singular tests have no test_metadata, which this file's own
        # parsing below assumed every result would have. Found as a real,
        # live KeyError while implementing the `dbt build` change just
        # below - a genuine regression from Phase 2, not hypothetical.
        ["dbt", command, "--profiles-dir", PROFILES_DIR, "--project-dir", DBT_PROJECT_DIR, "--quiet",
         "--select", "stg_birth_registrations"],
        env=env, cwd=ROOT, check=False, capture_output=True, text=True,
    )


def _test_nodes(manifest: dict) -> dict[str, dict]:
    return {
        uid: node for uid, node in manifest["nodes"].items()
        if node.get("resource_type") == "test"
    }


def evaluate_dbt_real(run_id: str, run_timestamp: str) -> list[dict]:
    db_path = os.path.join(DUCKDB_RUNS_DIR, f"{run_id}.duckdb")
    # A single `dbt build` (build the model, then run its tests) instead of
    # separate `dbt run` + `dbt test` subprocess calls - dbt-core's fixed
    # per-invocation startup cost (~2.4s just for `dbt --version`, before
    # any project work) was being paid twice per run for no benefit; one
    # call does identical work in about half the wall-clock time, verified
    # directly (9.5s -> 4.2s on the Child Protection project this was
    # first measured against - see plans/performance.md). run_results.json
    # then also contains the model-build step's own result, which the
    # parsing below already silently skips (nodes.get() returns None for
    # anything that isn't a test node), so nothing further changes.
    _run_dbt(db_path, "build")

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
        status = r["status"]
        failures = r.get("failures") or 0
        warn_t = _parse_threshold(config.get("warn_if"))
        fail_t = _parse_threshold(config.get("error_if"))

        key = (column, test_name)
        if key in _VERIFY_COUNT_SQL and status != "error":
            verified_count = conn.execute(_VERIFY_COUNT_SQL[key]).fetchone()[0]
            failures = verified_count
            status = _status_for(verified_count, warn_t, fail_t)

        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            "column_name": column,
            "check_name": f"dbt:{test_name}",
            "dimension": "uniqueness" if test_name == "unique" else
                         "completeness" if test_name == "not_null" else "validity",
            "label": _LABEL_BY_TEST.get(test_name),
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": failures,
            "unit": "count",
            "warn_threshold": warn_t,
            "fail_threshold": fail_t,
            "status": status,
            "on_fail_action": "flag",
            "row_count_total": n_total,
            "row_count_invalid": failures,
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
