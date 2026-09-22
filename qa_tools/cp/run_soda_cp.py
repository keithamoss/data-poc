"""
Runs REAL Soda Core (soda-core-duckdb) against
contract/child-protection-soda-checks.yml, via Soda's own Python Scan API -
the Child Protection counterpart to qa_tools/bdm/run_soda_bdm.py.
Soda's own scan results carry which table each check belongs to
(`c["table"]`), so unlike run_dbt_cp.py there's no separate lookup
needed to attribute a result to one of the 6 CP dataset_ids.

Run once per run against its own per-run CP DuckDB file
(qa_tools/cp/build_cp_warehouses.py) - same rationale as
run_soda_bdm.py. Threshold parsing and failing-row sample capture
(CaptureSampler - see soda_common.py and run_soda_bdm.py's own docstring)
shared via qa_tools/common/soda_common.py - see plans/qa-pipeline.md #84.
"""
from __future__ import annotations
import os

import duckdb

from qa_tools.common import hierarchy
from qa_tools.common.soda_common import (
    ENGINE_TAG, threshold, CaptureSampler, failing_sample_keys, check_id_from_resource_attributes,
)
from qa_tools.common.qa_results_writer import write_qa_result
from . import cp_common

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SODA_CHECKS_PATH = os.path.join(ROOT, "contract", "child-protection-soda-checks.yml")
CP_DUCKDB_RUNS_DIR = os.path.join(ROOT, "data", "cp_duckdb_runs")

# dimension for the 3 named `failed rows` business-rule checks - matches
# the dimension each rule's contract/child-protection-contract.yaml quality
# entry uses (escalation completeness is a completeness concern; the other
# two are a cross-table consistency concern). date_of_birth out of range
# is a genuine single-column check (unlike the 3 business rules, which are
# real table-level cross-record concerns) - "conformity" matches BDM's own
# date_of_birth range rule's dimension.
_BUSINESS_RULE_DIMENSION = {
    "Escalation completeness": "completeness",
    "Closed-case investigation hygiene": "consistency",
    "Placement/carer approval compliance": "consistency",
    "date_of_birth out of range": "conformity",
}

# date_of_birth out of range has no natural `column` of its own to report
# (a "failed rows" check, not a column metric) - routed to date_of_birth
# explicitly, same class of gap run_soda_bdm.py's _CUSTOM_CHECK_COLUMN
# solves for BDM's own "failed rows" checks. The 3 genuine cross-table
# business rules deliberately stay unrouted (land on cp_common's
# table-level pseudo-column) since they're not really about one column.
_CUSTOM_CHECK_COLUMN = {
    "date_of_birth out of range": "date_of_birth",
}


def evaluate_soda_cp(run_id: str, run_timestamp: str) -> list[dict]:
    from soda.scan import Scan

    db_path = os.path.join(CP_DUCKDB_RUNS_DIR, f"{run_id}.duckdb")
    conn = duckdb.connect(db_path, read_only=True)
    conn.execute("SET search_path = 'raw'")
    n_total_by_table = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in cp_common.TABLES}

    scan = Scan()
    scan.set_data_source_name("cp_collection")
    scan.add_duckdb_connection(conn, data_source_name="cp_collection")
    scan.add_sodacl_yaml_file(SODA_CHECKS_PATH)
    sampler = CaptureSampler()
    scan.sampler = sampler
    scan.disable_telemetry()
    scan.execute()
    scan_results = scan.get_scan_results()
    metric_name_by_id = {m["identity"]: m["metricName"] for m in scan_results["metrics"]}

    results = []
    for c in scan_results["checks"]:
        table = c["table"]
        if table not in cp_common.TABLES:
            continue  # not a CP table (shouldn't happen - guard anyway)

        column = c["column"] or _CUSTOM_CHECK_COLUMN.get(c["name"]) or "(table)"

        check_id = check_id_from_resource_attributes(c)
        if check_id is None:
            raise ValueError(f"no check_id found in resourceAttributes for soda check {c['name']!r} - "
                              f"the checks YAML is missing attributes.check_id for this check")

        diagnostics = c["diagnostics"]
        value = diagnostics.get("value")
        outcome = c["outcome"]

        base_check = metric_name_by_id.get(c["metrics"][0], c["name"]) if c["metrics"] else c["name"]
        is_custom_name = "when" not in c["name"]
        check_name = c["name"] if is_custom_name else base_check
        is_pct = base_check.endswith("percent")

        row_count_invalid = None
        if diagnostics.get("blocks"):
            row_count_invalid = diagnostics["blocks"][0].get("totalFailingRows")
        elif base_check == "row_count":
            row_count_invalid = 0
        elif base_check == "reference":
            row_count_invalid = int(value) if value is not None else None

        if is_custom_name:
            dimension = _BUSINESS_RULE_DIMENSION.get(check_name, "")
        elif base_check == "reference":
            dimension = "consistency"
        elif base_check == "row_count":
            dimension = "completeness"
        else:
            dimension = ""

        # A short, human-readable phrase for what this check actually
        # measures - written here, where the check result is constructed,
        # not guessed later from check_name by the dashboard-building
        # code. None for the 3 named business-rule checks: their own
        # names are already plain (and match dbt's and datacontract-cli's
        # own names for the same rule closely enough that a reader sees
        # the overlap without a further prefix).
        label = None if is_custom_name else {
            "row_count": "Row count", "reference": "Referential integrity",
            "missing_count": "Null rate", "missing_percent": "Null rate",
            "invalid_percent": "Invalid values", "duplicate_count": "Duplicate rate",
        }.get(base_check)

        results.append({
            "agency_id": cp_common.AGENCY_ID,
            "collection_id": cp_common.COLLECTION_ID,
            "dataset_id": hierarchy.dataset_for_table(table).dataset_id,
            "check_id": check_id,
            "column_name": column,
            "check_name": check_name,
            "dimension": dimension,
            "label": label,
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": value,
            "unit": "%" if is_pct else "count",
            "warn_threshold": threshold(diagnostics.get("warn")),
            "fail_threshold": threshold(diagnostics.get("fail")),
            "status": outcome,
            "on_fail_action": "flag",
            "row_count_total": n_total_by_table[table],
            "row_count_invalid": row_count_invalid,
            "failing_sample_keys": failing_sample_keys(sampler.captured, c["name"], cp_common.TABLE_PK[table]),
            "engine": ENGINE_TAG,
        })

    conn.close()
    # Committed only now, after row_count_total's own live per-table
    # query above - see run_soda_bdm.py's own identical comment /
    # qa_results_writer.py's docstring for why.
    write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp, "soda", scan_results,
                     verified=results)
    return results


if __name__ == "__main__":
    from datetime import datetime, timezone
    for run_id in ["cp_run_01_2026-07-06", "cp_run_04_2026-07-27", "cp_run_09_2026-08-31"]:
        res = evaluate_soda_cp(run_id, datetime.now(timezone.utc).isoformat())
        print(f"--- {run_id} ---")
        for r in res:
            if r["status"] != "pass":
                print(" ", r["dataset_id"], r["column_name"], r["check_name"], r["status"], r["metric_value"])
