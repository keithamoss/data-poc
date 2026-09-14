"""
Runs REAL dbt-core (dbt-duckdb adapter) against this project's actual
dbt_project/ - `dbt build` (model + its tests), once per run, each pointed
at its own single-run DuckDB file under data/duckdb_runs/ (see
build_per_run_warehouses.py's docstring for why one file per run rather
than the combined warehouse.duckdb). --select scopes this call to
stg_birth_registrations + its own singular test(s) only - the same
dbt_project/ also holds Child Protection's models, built separately by
qa_tools/cp/run_dbt_cp.py.

Parses dbt's own target/manifest.json (test metadata: column, test type,
config) and target/run_results.json (status, failures) - not a
reimplementation of dbt's test logic, this genuinely shells out to the
`dbt` CLI and reads what it reports. Subprocess invocation and manifest
parsing are shared with run_dbt_cp.py via
qa_tools/common/dbt_common.py; everything below is genuinely
dataset-specific (which tests exist, what they mean, a real dbt-duckdb
reliability workaround this dataset needed) - see plans/wider.md #20.

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

A third, newer instance of the same class of problem: the
recent_births_present singular test (no config, no fail_calc arithmetic
at all - the simplest possible test shape) reported "fail" for run_10 in
a full 10-run orchestrate_bdm.py pass, while re-running that exact
test in isolation seconds later, against the same warehouse file, correctly
returned "pass" - and stayed correct on every subsequent re-run. No
SQL-level or config-level explanation found (unlike the other two, this
test has no arithmetic to remove), which points at dbt-duckdb itself
rather than anything in this project's own SQL - feeds into the same open
upstream-repro follow-up as the other two (plans/qa-pipeline.md #1).
Treated the same way here: independently verified via direct query, not
trusted blindly.
"""
from __future__ import annotations
import json
import os

import duckdb

from qa_tools.common.dbt_common import ENGINE_TAG, parse_threshold, run_dbt, test_nodes

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DBT_PROJECT_DIR = os.path.join(ROOT, "dbt_project")
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "..", "dbt_profiles")
DUCKDB_RUNS_DIR = os.path.join(ROOT, "data", "duckdb_runs")

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"

# column/test combos where dbt's own "failures" value was observed to be
# unreliable (see module docstring) - mapped to the exact SQL used to
# independently recompute the true failing-row count.
_VERIFY_COUNT_SQL = {
    ("sex", "accepted_values"): "SELECT COUNT(*) FROM stg_birth_registrations WHERE sex NOT IN ('M','F','X')",
    ("place_of_birth_facility", "not_null"): "SELECT COUNT(*) FROM stg_birth_registrations WHERE place_of_birth_facility IS NULL",
    # A third, newer instance of the same reliability problem, found live:
    # a clean re-run of just this one test in isolation correctly returned
    # 0 rows (pass) for run_10, but dbt's own run_results.json - from a
    # full 10-run orchestrate_bdm.py pass minutes earlier, same
    # warehouse file, same compiled SQL - reported it failed. Same
    # treatment as the two above: recompute independently rather than
    # trust dbt's reported status for this specific check.
    ("date_of_birth", "recent_births_present"):
        "SELECT CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END FROM stg_birth_registrations "
        "WHERE date_of_birth >= CURRENT_DATE - INTERVAL 7 DAY",
}

# multiple_birth_sibling has no attached column of its own (a singular
# test, not a generic column test) - same class of gap run_dbt_cp.py
# solves with cp_common.BUSINESS_RULE_HOME_TABLE, just column- rather than
# table-scoped since this dataset is a single table. Without this, the
# check would land under column_name="(table)", which the dashboard
# builder silently drops for birth-registrations (there's no
# "(table-level checks)" pseudo-column here the way Child Protection has).
_SINGULAR_TESTS = ["multiple_birth_sibling", "recent_births_present"]
_SINGULAR_TEST_COLUMN = {
    "multiple_birth_sibling": "is_multiple_birth",
    "recent_births_present": "date_of_birth",
}

_DIMENSION_BY_TEST = {
    "unique": "uniqueness",
    "not_null": "completeness",
    "accepted_values": "validity",
    "multiple_birth_sibling": "consistency",
    "recent_births_present": "timeliness",
}

# A short, human-readable phrase for what each test actually checks -
# written here, at the point each check result is constructed (the one
# place that genuinely knows what a check tests), not guessed later from
# the check's name string by the dashboard-building code. multiple_birth_
# sibling gets an explicit shared label (unlike the CP singular business-
# rule tests, whose own names already read plainly) because it's the same
# rule as the contract's and Soda's own version of it, under different
# names - the label is what makes that overlap visible on the dashboard.
_LABEL_BY_TEST = {
    "unique": "Duplicate rate",
    "not_null": "Null rate",
    "accepted_values": "Invalid values",
    "multiple_birth_sibling": "Sibling record match",
    "recent_births_present": "Freshness",
}


def _status_for(count: int, warn_t: float | None, fail_t: float | None) -> str:
    if fail_t is not None and count > fail_t:
        return "fail"
    if warn_t is not None and count > warn_t:
        return "warn"
    return "pass"


def evaluate_dbt_bdm(run_id: str, run_timestamp: str) -> list[dict]:
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
    target_path = os.path.join(DBT_PROJECT_DIR, "target", run_id)
    run_dbt(db_path, "build", ["stg_birth_registrations", *_SINGULAR_TESTS], target_path,
            PROFILES_DIR, DBT_PROJECT_DIR, ROOT)

    with open(os.path.join(target_path, "manifest.json")) as f:
        manifest = json.load(f)
    with open(os.path.join(target_path, "run_results.json")) as f:
        run_results = json.load(f)

    nodes = test_nodes(manifest)
    conn = duckdb.connect(db_path, read_only=True)
    n_total = conn.execute("SELECT COUNT(*) FROM stg_birth_registrations").fetchone()[0]

    results = []
    for r in run_results["results"]:
        node = nodes.get(r["unique_id"])
        if node is None:
            continue
        meta = node.get("test_metadata")
        test_name = meta["name"] if meta else node["name"]
        column = node["column_name"] if meta else _SINGULAR_TEST_COLUMN.get(node["name"], "(table)")
        config = node.get("config", {})
        status = r["status"]
        failures = r.get("failures") or 0
        warn_t = parse_threshold(config.get("warn_if"))
        fail_t = parse_threshold(config.get("error_if"))

        key = (column, test_name)
        if key in _VERIFY_COUNT_SQL and status != "error":
            verified_count = conn.execute(_VERIFY_COUNT_SQL[key]).fetchone()[0]
            failures = verified_count
            if warn_t is not None or fail_t is not None:
                status = _status_for(verified_count, warn_t, fail_t)
            else:
                # a hard pass/fail singular test (no warn_if/error_if
                # config, so no threshold to compare against) - _status_for
                # would silently read as "always pass" with both
                # thresholds None; any nonzero verified count means the
                # test genuinely failed instead.
                status = "fail" if verified_count > 0 else "pass"

        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            "column_name": column,
            "check_name": f"dbt:{test_name}",
            "dimension": _DIMENSION_BY_TEST.get(test_name, ""),
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
        res = evaluate_dbt_bdm(run_id, datetime.now(timezone.utc).isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            print(" ", r["column_name"], r["check_name"], r["status"], r["metric_value"], r["unit"])
