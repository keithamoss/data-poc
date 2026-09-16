"""
Runs REAL dbt-core (dbt-duckdb adapter) against this project's actual
dbt_project/ for the Child Protection collection - the CP counterpart to
qa_tools/bdm/run_dbt_bdm.py, scoped to the 6 stg_cp_* models and
their tests (PK unique/not_null, the 7 `relationships` tests, and the 3
singular cross-table business-rule tests) rather than
stg_birth_registrations, via `dbt build --select <the 6 CP models + the 3
singular test names>` - an explicit node list rather than a graph
selector, so this never accidentally pulls in (or silently skips) a
birth-registrations test if the project's DAG shape changes later.

Each run is pointed at its own single-run CP DuckDB file under
data/cp_duckdb_runs/ (qa_tools/cp/build_cp_warehouses.py) - same
per-run-warehouse rationale as run_dbt_bdm.py's docstring.
Subprocess invocation and manifest parsing are shared with
run_dbt_bdm.py via qa_tools/common/dbt_common.py - see
plans/wider.md #20.

Which of the 6 CP tables a test result belongs to (for the dashboard's
dataset_id) comes from dbt's own `attached_node` on the test's manifest
entry for generic tests (unique/not_null/relationships - the model the
test is declared under, not necessarily the first of the tables it
depends on), and from cp_common.BUSINESS_RULE_HOME_TABLE for the 3
singular tests (which have no attached_node at all - they're not
column/model-scoped).

_AUDIT_AGGREGATE_SQL (see its own comment, and run_dbt_bdm.py's matching
one) cross-checks every test of a covered shape against its own
--store-failures audit table rather than trusting dbt's own reported
"failures"/status blindly. Two real problems motivate this, both found
live on the CP side while adding dbt_utils.accepted_range on
cp_clients.date_of_birth 2026-09-15: a confirmed, root-caused dbt-core
bug (failures hardcoded to 0 whenever a test's status lands on "Pass" -
dbt-labs/dbt-core#11312, unmerged in our installed 1.12.4 - see
plans/qa-pipeline.md #34 for the full account) caught on accepted_range
itself (0 reported for cp_run_04/07, true count 7/5), and a second,
separate, still-unexplained nondeterminism caught investigating that -
notification_id's pre-existing `unique` test (unrelated to this
session's changes) reporting 0 once, live, then correctly on the very
next re-run of the identical warehouse files, no code changed in
between. 2026-09-15: replaced the original narrow, per-check
_VERIFY_COUNT_SQL (which hand-duplicated each affected check's own SQL
condition against the source model) with this - a check-agnostic
mechanism applied to every instance of a covered test shape, not just
the two specific checks that happened to get caught. See run_dbt_bdm.py's
own comment on _AUDIT_AGGREGATE_SQL for why (Keith's redline against
duplicating a check's own pass/fail logic, item 28).
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
from . import cp_common

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
DBT_PROJECT_DIR = os.path.join(ROOT, "dbt_project")
PROFILES_DIR = os.path.join(os.path.dirname(__file__), "..", "dbt_profiles")
CP_DUCKDB_RUNS_DIR = os.path.join(ROOT, "data", "cp_duckdb_runs")
SCHEMA_YML_PATH = os.path.join(DBT_PROJECT_DIR, "models", "staging", "schema.yml")

# Built once from schema.yml itself, not the compiled manifest - see
# dbt_check_id_lookup()'s own docstring and run_dbt_bdm.py's identical
# constant for why.
_CHECK_ID_LOOKUP = dbt_check_id_lookup(SCHEMA_YML_PATH)

CP_MODELS = [f"stg_{t}" for t in cp_common.TABLES]
CP_SINGULAR_TESTS = list(cp_common.BUSINESS_RULE_HOME_TABLE.keys())

# Test shapes whose --store-failures audit table row count can replace
# run_results.json's own (sometimes wrong) `failures` field - see this
# module's own docstring and plans/qa-pipeline.md #34 for the full
# account, and run_dbt_bdm.py's matching dict for why this counts the
# audit table instead of re-deriving each check's own condition (Keith's
# redline, item 28). Applied to every instance of these test types,
# CP's 3 cross-table business-rule singular tests included (escalation_
# completeness/closed_case_investigation_hygiene/placement_carer_
# approval) - none of these three have ever been directly caught
# exhibiting either bug, but none are currently configured with a
# warn_if/error_if either (so the confirmed accounting bug can't fire on
# them structurally - it only fires when a test's status can land on
# "Pass" despite a nonzero count), while the second, still-unexplained
# nondeterminism has no known trigger condition to rule any test out by.
# The fix is free (dbt already materializes these audit tables via
# --store-failures) - no reason to wait for a specific instance to get
# caught the way the CP-side discovery of this happened by chance.
#
# accepted_range/not_null (row-shaped, full row kept) get COUNT(*);
# accepted_values/unique (value-aggregated, per schema.yml's own comment
# on this) get SUM(n_records). relationships is deliberately excluded -
# a separate, already-documented gap (_failing_sample_keys's own
# docstring): its audit table only carries the offending FK value, not a
# row count in the same shape as everything else here.
_AUDIT_AGGREGATE_SQL = {
    "not_null": "SELECT COUNT(*) FROM {relation}",
    "accepted_range": "SELECT COUNT(*) FROM {relation}",
    "escalation_completeness": "SELECT COUNT(*) FROM {relation}",
    "closed_case_investigation_hygiene": "SELECT COUNT(*) FROM {relation}",
    "placement_carer_approval": "SELECT COUNT(*) FROM {relation}",
    "accepted_values": "SELECT COALESCE(SUM(n_records), 0) FROM {relation}",
    "unique": "SELECT COALESCE(SUM(n_records), 0) FROM {relation}",
}

_DIMENSION_BY_TEST = {
    "unique": "uniqueness",
    "not_null": "completeness",
    "accepted_values": "validity",
    "relationships": "consistency",
    "escalation_completeness": "completeness",
    "closed_case_investigation_hygiene": "consistency",
    "placement_carer_approval": "consistency",
    "accepted_range": "conformity",
}

# A short, human-readable phrase for what each test actually checks -
# written here, where each check result is constructed, not guessed later
# from the check's name string by the dashboard-building code. None for
# the 3 business-rule tests: their own names (escalation_completeness,
# etc.) are already plain enough on their own, and this same business rule
# also shows up under Soda's and datacontract-cli's own already-plain
# names - a reader scanning card titles already sees the shared word
# without a further prefix. accepted_range DOES get one - unlike those
# three, its own name reads as a generic dbt_utils test identifier, not a
# plain description of what it checks here specifically.
_LABEL_BY_TEST = {
    "unique": "Duplicate rate",
    "not_null": "Null rate",
    "accepted_values": "Invalid values",
    "relationships": "Referential integrity",
    "accepted_range": "Date range",
}

# Historical mechanism, currently unused: routes a SINGULAR test (no
# test_metadata at all) to a real column instead of the "(table)"
# fallback, the way run_dbt_bdm.py's own _SINGULAR_TEST_COLUMN still does
# for multiple_birth_sibling. Empty since cp_client_date_of_birth_range
# (this dict's only entry) was retired 2026-09-15, replaced by dbt_utils.
# accepted_range - a real column-level GENERIC test now, routed the same
# way accepted_values/not_null already are, via node["column_name"]
# itself (no lookup needed). Left in place, not deleted, in case a future
# CP singular test needs the same column-routing accepted_range no longer
# does.
_SINGULAR_TEST_COLUMN = {}


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


def _failing_sample_keys(conn, test_name: str, column: str, table: str, node: dict, status: str) -> list[str]:
    """Up to 5 example failing rows' own primary keys, via dbt's
    --store-failures audit table (see dbt_common.py) - identifiers only,
    never full row content, per plans/qa-pipeline.md #15. `relationships`
    (the 7 FK checks) is a deliberate, named gap for now: its audit table
    only carries the offending FK *value* (`from_field`), which would
    need a further resolution step (value -> child model row -> child PK)
    beyond what accepted_values/unique already need - left for a
    follow-up rather than built speculatively."""
    if status not in ("warn", "fail"):
        return []
    relation_name = node.get("relation_name")
    if not relation_name:
        return []
    pk_column = cp_common.TABLE_PK[table]
    model = f"stg_{table}"
    if (test_name in ("not_null", "accepted_range")
            or test_name in cp_common.BUSINESS_RULE_HOME_TABLE):
        # not_null/accepted_range's audit tables keep every column
        # (confirmed against dbt_utils' own accepted_range.sql macro
        # source: `select *`); each singular business-rule test's own
        # query already selects its home table's PK directly (confirmed
        # per-test, not assumed).
        return failing_sample_keys_direct(conn, relation_name, pk_column)
    if test_name == "unique":
        return failing_sample_keys_via_values(conn, relation_name, "unique_field", model, column, pk_column)
    if test_name == "accepted_values":
        # same pre-aggregated (value, n_records) shape as BDM's own
        # accepted_values tests (see run_dbt_bdm.py's _failing_sample_
        # keys) - previously fell through to the relationships case below
        # and returned no sample keys at all for any of this project's
        # accepted_values tests, postcode included; fixed alongside the
        # 2026-09-15 full-triplication pass since it now covers far more
        # checks (concern_type, sex, source_type, risk_rating, outcome,
        # substantiated, placement_type, carer_type, approval_status,
        # team_region).
        return failing_sample_keys_via_values(conn, relation_name, "value_field", model, column, pk_column)
    return []  # relationships - see docstring above


def _status_for(count: int, warn_t: float | None, fail_t: float | None) -> str:
    if fail_t is not None and count > fail_t:
        return "fail"
    if warn_t is not None and count > warn_t:
        return "warn"
    return "pass"


def evaluate_dbt_cp(run_id: str, run_timestamp: str) -> list[dict]:
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
    target_path = os.path.join(DBT_PROJECT_DIR, "target", run_id)
    run_dbt(db_path, "build", CP_MODELS + CP_SINGULAR_TESTS, target_path, PROFILES_DIR, DBT_PROJECT_DIR, ROOT)

    with open(os.path.join(target_path, "manifest.json")) as f:
        manifest = json.load(f)
    with open(os.path.join(target_path, "run_results.json")) as f:
        run_results = json.load(f)

    # One dbt build covers all 6 CP tables at once - the raw output
    # genuinely operates at collection granularity, so it's written there
    # rather than split artificially per table (would misrepresent what
    # the tool actually ran).
    nodes = test_nodes(manifest)

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
        column = node["column_name"] if meta else _SINGULAR_TEST_COLUMN.get(node["name"], "(table)")
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
                # the 3 business-rule singular tests have no warn_if/
                # error_if config, so no threshold to compare against -
                # _status_for would silently read as "always pass" with
                # both thresholds None; any nonzero verified count means
                # the test genuinely failed instead (same fix
                # run_dbt_bdm.py's own mechanism already needed).
                status = "fail" if verified_count > 0 else "pass"

        failing_sample_keys = _failing_sample_keys(conn, test_name, column, table, node, status)

        # Model+column are None for a singular test (no test_metadata,
        # and schema.yml's own tests: block has no model association -
        # fine, singular test names are globally unique - see
        # dbt_check_id_lookup()'s own docstring) even though `column`
        # above may hold a display-only fallback. `table` (already
        # resolved above via _table_for_test()) gives the real model
        # name for a generic test - CP's schema.yml holds 6 models
        # together, so this must match dbt_check_id_lookup()'s own
        # per-model keying or a same-named column+test-type collision
        # across tables (or against BDM's own models, same file) would
        # silently tag a result with the wrong check_id.
        check_id_model = f"stg_{table}" if meta else None
        check_id_column = node["column_name"] if meta else None
        check_id = _CHECK_ID_LOOKUP.get((check_id_model, check_id_column, test_name))
        if check_id is None:
            raise ValueError(f"no check_id found for dbt test {test_name!r} "
                              f"(model={check_id_model!r}, column={check_id_column!r}) - schema.yml "
                              f"is missing meta.check_id or this test isn't declared there")

        results.append({
            "agency_id": cp_common.AGENCY_ID,
            "collection_id": cp_common.COLLECTION_ID,
            "dataset_id": cp_common.TABLE_DATASET_ID[table],
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
            "row_count_total": n_total_by_table[table],
            "row_count_invalid": failures,
            "failing_sample_keys": failing_sample_keys,
            "engine": ENGINE_TAG,
        })

    conn.close()
    # Committed only now, after the audit-table correction above - see
    # run_dbt_bdm.py's own identical comment / qa_results_writer.py's
    # docstring for why.
    write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp, "dbt", run_results,
                     verified=results)
    return results


if __name__ == "__main__":
    from datetime import datetime, timezone
    for run_id in ["cp_run_01_2026-07-06", "cp_run_04_2026-07-27", "cp_run_09_2026-08-31"]:
        res = evaluate_dbt_cp(run_id, datetime.now(timezone.utc).isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            if r["status"] != "pass":
                print(" ", r["dataset_id"], r["column_name"], r["check_name"], r["status"], r["metric_value"])
