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
reliability workaround this dataset needed) - see plans/qa-pipeline.md #84.

A REAL, confirmed dbt-core reliability problem, not assumed - and, as of
2026-09-15, actually root-caused (see plans/qa-pipeline.md #34 for the
full account, this is the short version): `dbt/task/test.py`'s
`build_test_run_result()` in this project's installed dbt-core (1.12.4)
hardcodes `failures = 0` as its default and only ever overwrites it when
a test's final status lands on Fail or Warn - a test whose real failure
count is nonzero but under every configured threshold (a genuine "Pass")
always reports `failures=0`, discarding the true count. A real, filed
dbt-core bug (dbt-labs/dbt-core#11312, tagged `type:bug`, fix unmerged as
of our installed version), first found here on `sex`/
`place_of_birth_facility` reporting 0 on certain runs while the identical
compiled SQL, run directly via DuckDB's own Python API, always gave the
right answer.

A second, separate, still-NOT-root-caused phenomenon was also found live
in this project (originally on the retired recent_births_present
singular test, since reproduced on the Child Protection side - see
plans/qa-pipeline.md #34): a test's reported status/failures flipping
between correct and wrong across separate `dbt build` invocations of the
*identical* warehouse file, with no code change in between - genuine
nondeterminism, not explained by the accounting bug above (that bug is
deterministic given the same config/data; this one isn't). Points at
something in dbt-duckdb's query execution path itself, not dbt-core's
result-reporting logic - still an open question, feeds the same
upstream-repro follow-up as before (plans/qa-pipeline.md #1).

_AUDIT_AGGREGATE_SQL (see its own comment) protects against both at once
for every test of a covered shape, not just the specific checks caught
exhibiting either one: it re-derives the true count from each test's own
`--store-failures` audit table (`relation_name`) rather than trusting
`run_results.json`'s own `failures`/`status` fields - dbt-core still
genuinely ran the real check (that's what "engine" attributes this result
to, and what a *mismatch* would mean if this verification query itself
had a bug); this only stops trusting the specific summary fields known to
be unreliable.

Also captures up to 5 example failing rows' registration_numbers per
check (via dbt's --store-failures audit tables, see dbt_common.py) -
identifiers only, never full row content, per plans/qa-pipeline.md #15.
Not every test shape supports this (recency has no per-row concept at
all - see _failing_sample_keys()'s own docstring for the exact coverage).
"""
from __future__ import annotations
import json
import os

import duckdb

from qa_tools.common.check_lifecycle import dbt_check_id_lookup
from qa_tools.common.dbt_common import (
    ENGINE_TAG, parse_threshold, run_dbt, test_nodes,
    failing_sample_keys_direct, failing_sample_keys_via_values,
)
from qa_tools.common.qa_results_writer import write_qa_result

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DBT_PROJECT_DIR = os.path.join(ROOT, "dbt_project")
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "..", "dbt_profiles")
DUCKDB_RUNS_DIR = os.path.join(ROOT, "data", "duckdb_runs")
SCHEMA_YML_PATH = os.path.join(DBT_PROJECT_DIR, "models", "staging", "schema.yml")

# Built once from schema.yml itself, not the compiled manifest - see
# dbt_check_id_lookup()'s own docstring for why. Only ever needs the
# ACTIVE file: a real result can only exist for a check that's
# currently running, and a retired check (moved to schema-retired.yml,
# see that file's header comment) never produces one.
_CHECK_ID_LOOKUP = dbt_check_id_lookup(SCHEMA_YML_PATH)

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"

# Test shapes whose --store-failures audit table can replace
# run_results.json's own (sometimes wrong) `failures` field - see
# plans/qa-pipeline.md #34 for the full account: a confirmed dbt-core bug
# (failures hardcoded to 0 whenever a test's final status lands on "Pass",
# dbt-labs/dbt-core#11312, unmerged in this project's installed 1.12.4),
# plus a separate, still-unexplained nondeterminism (a flaky CP unique
# test, same item) this incidentally also protects against - both
# manifest the same way: a reported count/status that doesn't match what
# the audit table actually holds.
#
# 2026-09-15: replaces the previous _VERIFY_COUNT_SQL, which hand-
# maintained a direct copy of each affected check's own SQL condition
# against the source model (e.g. "...WHERE sex NOT IN ('M','F','X')") -
# exactly the "duplicate the check's own pass/fail logic" pattern Keith's
# redline (item 28) rules out, and the same drift risk item 26's bug
# already demonstrated once for a hand-maintained copy of a check's
# condition. Querying the audit table instead needs no knowledge of what
# the check's condition actually is - it counts whatever dbt itself
# already decided was a failing row, via the exact same relation_name
# failing_sample_keys_direct/_via_values already read reliably all
# session. Applied to every instance of these test types (not a curated
# list of specific checks that happened to get caught) - the whole point
# is this stops depending on someone having already noticed a given check
# misbehave.
#
# One test shape is deliberately excluded: `accepted_values`/`unique`
# need SUM(n_records) instead of COUNT(*), since their own main_sql
# pre-aggregates to (value, count) pairs - see schema.yml's own comment
# on this distinction. `recency` used to be excluded too (dbt_utils' own
# macro stored a one-row-per-group most_recent/threshold summary, not
# failing rows - COUNT(*) on it was meaningless) - Phase 5f (#61)
# rebuilt it as a singular test (tests/recency.sql) that, like
# multiple_birth_sibling, returns 0 or 1 synthetic failing rows via
# --store-failures, so COUNT(*) on its own audit table is now exactly
# right, and gets the same dbt-core-bug/flakiness protection every other
# test here does - genuinely warranted here specifically, since this
# exact check (under its old name, recent_births_present.sql) is the
# one plans/qa-pipeline.md #34 already caught exhibiting the still-
# unexplained nondeterminism this workaround guards against.
_AUDIT_AGGREGATE_SQL = {
    "not_null": "SELECT COUNT(*) FROM {relation}",
    "matches_regex": "SELECT COUNT(*) FROM {relation}",
    "accepted_range": "SELECT COUNT(*) FROM {relation}",
    "expression_is_true": "SELECT COUNT(*) FROM {relation}",
    "multiple_birth_sibling": "SELECT COUNT(*) FROM {relation}",
    "recency": "SELECT COUNT(*) FROM {relation}",
    "accepted_values": "SELECT COALESCE(SUM(n_records), 0) FROM {relation}",
    "unique": "SELECT COALESCE(SUM(n_records), 0) FROM {relation}",
}

# Neither multiple_birth_sibling nor recency has an attached column of
# its own (both singular tests, not generic column tests) - same class
# of gap run_dbt_cp.py solves with cp_common.BUSINESS_RULE_HOME_TABLE,
# just column- rather than table-scoped since this dataset is a single
# table. Without this, either check would land under column_name=
# "(table)", which the dashboard builder silently drops for birth-
# registrations (there's no "(table-level checks)" pseudo-column here
# the way Child Protection has). multiple_birth_sibling has been a
# singular test since the 2026-09-15 dbt_utils switch (a cross-table-
# shaped self-join no generic test in dbt_utils/dbt-expectations
# covers); recency moved BACK to one in Phase 5f (#61, 2026-09-17) -
# dbt_utils.recency's own macro can't anchor "now" against anything but
# real wall-clock time, see tests/recency.sql's own comment.
_SINGULAR_TESTS = ["multiple_birth_sibling", "recency"]
_SINGULAR_TEST_COLUMN = {
    "multiple_birth_sibling": "is_multiple_birth",
    "recency": "date_of_birth",
}

# dbt_utils.expression_is_true is declared at MODEL level in schema.yml
# (it operates across the model, not one column - a cross-field
# comparison) - same class of routing gap as _SINGULAR_TEST_COLUMN
# above, just for a generic test whose manifest node genuinely has no
# column_name (None, not missing) rather than for a singular test (which
# has no test_metadata at all).
_MODEL_LEVEL_TEST_COLUMN = {
    "expression_is_true": "date_registered",
}

_DIMENSION_BY_TEST = {
    "unique": "uniqueness",
    "not_null": "completeness",
    "accepted_values": "conformity",
    "matches_regex": "conformity",
    "multiple_birth_sibling": "consistency",
    "accepted_range": "conformity",
    "expression_is_true": "consistency",
    "recency": "timeliness",
}

# A short, human-readable phrase for what each test actually checks -
# written here, at the point each check result is constructed (the one
# place that genuinely knows what a check tests), not guessed later from
# the check's name string by the dashboard-building code. multiple_birth_
# sibling gets an explicit shared label (unlike the CP singular business-
# rule tests, whose own names already read plainly) because it's the same
# rule as the contract's and Soda's own version of it, under different
# names - the label is what makes that overlap visible on the dashboard.
# accepted_range/expression_is_true/recency get the same treatment for
# the same reason, now that they're dbt_utils' generic names rather than
# this project's own descriptively-named singular test files.
_LABEL_BY_TEST = {
    "unique": "Duplicate rate",
    "not_null": "Null rate",
    "accepted_values": "Invalid values",
    "matches_regex": "Invalid values",
    "multiple_birth_sibling": "Sibling record match",
    "accepted_range": "Date-of-birth range",
    "expression_is_true": "Registration/birth date ordering",
    "recency": "Freshness",
}


def _failing_sample_keys(conn, test_name: str, column: str, node: dict, status: str) -> list[str]:
    """Up to 5 example registration_numbers for the rows that actually
    failed this test, via dbt's own --store-failures audit table (see
    dbt_common.py) - never full row content, per plans/qa-pipeline.md
    #15's "flag it, not full row content" line. One test shape is
    deliberately skipped, not an oversight: recency's own query (tests/
    recency.sql) is a NOT EXISTS existence check - its audit table holds
    at most one synthetic `failing_row` value, no registration_number or
    any other per-row identifier to sample - and any test with no
    relation_name (shouldn't happen once --store-failures is always on,
    guarded anyway)."""
    if status not in ("warn", "fail"):
        return []
    relation_name = node.get("relation_name")
    if not relation_name:
        return []
    if test_name in ("not_null", "matches_regex", "multiple_birth_sibling",
                      "accepted_range", "expression_is_true"):
        # the audit table already IS (a projection of) the failing rows
        # themselves - not_null/matches_regex/accepted_range keep every
        # column (confirmed against dbt_utils' own macro source:
        # accepted_range's `select *`, expression_is_true's `select
        # {{ '*' if should_store_failures() }}`), multiple_birth_sibling's
        # own query already selects registration_number directly.
        return failing_sample_keys_direct(conn, relation_name, "registration_number")
    if test_name in ("accepted_values", "unique"):
        # these two dbt generic-test macros pre-aggregate their audit
        # table to the offending VALUE (+ a count), not the failing row -
        # resolve back to real registration_numbers via one follow-up
        # query against the model itself.
        value_column = "value_field" if test_name == "accepted_values" else "unique_field"
        return failing_sample_keys_via_values(
            conn, relation_name, value_column, "stg_birth_registrations", column, "registration_number")
    return []


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
    # Lives beside db_path (DUCKDB_RUNS_DIR/<run_id>.duckdb), not under
    # DBT_PROJECT_DIR/target/ - that's a fixed, repo-relative path shared
    # by every invocation regardless of DUCKDB_RUNS_DIR, so two tests
    # reusing the same run_id (tests/test_run_dbt_bdm.py's own two tests,
    # by design, matching conftest.py's fixture-built data) would collide
    # if ever scheduled onto different parallel workers - a real risk,
    # not hypothetical (plans/running-thoughts.md #12, confirmed by
    # reproducing it). DUCKDB_RUNS_DIR is already genuinely unique per
    # real production run (untouched) and, in tests, already monkeypatched
    # to a per-worker tmp dir - so basing target_path on it inherits that
    # same uniqueness for free, no test-file changes needed.
    target_path = os.path.join(DUCKDB_RUNS_DIR, "dbt_target", run_id)
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
        # Three cases: a real column-level generic test (column_name set);
        # a model-level generic test (test_metadata present, but
        # column_name is None - dbt_utils.expression_is_true, declared
        # under the model itself in schema.yml, not a column); a
        # singular test (no test_metadata at all - multiple_birth_
        # sibling, recency).
        if meta and node["column_name"]:
            column = node["column_name"]
        elif meta:
            column = _MODEL_LEVEL_TEST_COLUMN.get(test_name, "(table)")
        else:
            column = _SINGULAR_TEST_COLUMN.get(node["name"], "(table)")
        config = node.get("config", {})
        status = r["status"]
        failures = r.get("failures") or 0
        warn_t = parse_threshold(config.get("warn_if"))
        fail_t = parse_threshold(config.get("error_if"))

        relation_name = node.get("relation_name")
        if test_name in _AUDIT_AGGREGATE_SQL and relation_name and status != "error":
            sql = _AUDIT_AGGREGATE_SQL[test_name].format(relation=relation_name)
            verified_count = conn.execute(sql).fetchone()[0]
            failures = verified_count
            if warn_t is not None or fail_t is not None:
                status = _status_for(verified_count, warn_t, fail_t)
            else:
                # a hard pass/fail test (no warn_if/error_if config, so no
                # threshold to compare against) - _status_for would
                # silently read as "always pass" with both thresholds
                # None; any nonzero verified count means the test
                # genuinely failed instead.
                status = "fail" if verified_count > 0 else "pass"

        failing_sample_keys = _failing_sample_keys(conn, test_name, column, node, status)

        # The lookup key's column segment is None for a model-level or
        # singular test even though `column` above may hold a display-
        # only column (_MODEL_LEVEL_TEST_COLUMN/_SINGULAR_TEST_COLUMN) -
        # matches dbt_check_id_lookup()'s own keying exactly. Model is
        # None for a singular test (schema.yml's own tests: block has no
        # model association - see that function's own docstring on why
        # that's fine); every generic test here is on this dataset's one
        # model.
        check_id_model = "stg_birth_registrations" if meta else None
        check_id_column = node["column_name"] if (meta and node["column_name"]) else None
        check_id = _CHECK_ID_LOOKUP.get((check_id_model, check_id_column, test_name))
        if check_id is None:
            raise ValueError(f"no check_id found for dbt test {test_name!r} "
                              f"(model={check_id_model!r}, column={check_id_column!r}) - schema.yml "
                              f"is missing meta.check_id or this test isn't declared there")

        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            "check_id": check_id,
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
            "failing_sample_keys": failing_sample_keys,
            "engine": ENGINE_TAG,
        })

    conn.close()
    # Committed only now, after the audit-table correction above (not
    # right after run_results.json is read) - raw_output stays dbt's own
    # unmodified output (bug included), but `verified` (=`results`, the
    # already-corrected records) is what a later, no-live-DB read of
    # this file actually needs - see qa_results_writer.py's own
    # docstring for why.
    write_qa_result(AGENCY_ID, DATASET_ID, run_id, run_timestamp, "dbt", run_results, verified=results)
    return results


if __name__ == "__main__":
    from datetime import datetime, timezone
    for run_id in ["run_01_2026-09-01", "run_04_2026-09-04", "run_09_2026-09-09"]:
        res = evaluate_dbt_bdm(run_id, datetime.now(timezone.utc).isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            print(" ", r["column_name"], r["check_name"], r["status"], r["metric_value"], r["unit"])
