"""
Runs REAL Evidently AI against cp_notifications' concern_type column (the
Child Protection collection's traffic-light demo column - dirty.py's
apply_cp_notifications_presets is the only preset that touches it, the
same role sex plays for Birth Registrations) vs. the first clean run as
reference - the Child Protection counterpart to
qa_tools/bdm/run_evidently_bdm.py.

Same real evidently.Report + evidently.presets.DataDriftPreset API, same
per-distinct-observed-value PSI binning behaviour documented there. PSI
computation shared via qa_tools/common/evidently_common.py - see
plans/qa-pipeline.md #84.
"""
from __future__ import annotations
import os

from qa_tools.common.evidently_common import ENGINE_TAG, WARN_THRESHOLD, FAIL_THRESHOLD, status_for_psi, compute_psi
from qa_tools.common.csv_io import load_null_values_by_column, read_csv_explicit_nulls
from qa_tools.common.qa_results_writer import write_qa_result
from . import cp_common
from .evidently_check_lifecycle import PSI_CHECK_ID

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CP_RAW_DIR = os.path.join(ROOT, "data", "cp_raw")
CONTRACT_PATH = os.path.join(ROOT, "contract", "child-protection-contract.yaml")
_NULL_VALUES = load_null_values_by_column(CONTRACT_PATH).get("cp_notifications", {})

DATASET_ID = cp_common.TABLE_DATASET_ID["cp_notifications"]

# A fallback default only, for calling this function directly with no
# other context - real callers (orchestrate_cp.py, this file's own
# __main__ block below) always pass the manifest's actual first run_id
# instead, since this literal goes stale every time the anchor date rolls
# forward (generator/anchor_date.py) and data/cp_raw/ isn't cleared
# between regenerations, so a stale copy can sit there and get silently
# used instead of raising - see orchestrate_cp.py and
# plans/qa-pipeline.md for the bug this was found as.
REFERENCE_RUN_ID = "cp_run_01_2026-07-06"


def evaluate_evidently_cp(run_id: str, run_timestamp: str,
                                reference_run_id: str = REFERENCE_RUN_ID) -> list[dict]:
    reference = read_csv_explicit_nulls(
        os.path.join(CP_RAW_DIR, reference_run_id, "cp_notifications.csv"), _NULL_VALUES)[["concern_type"]]
    current = read_csv_explicit_nulls(
        os.path.join(CP_RAW_DIR, run_id, "cp_notifications.csv"), _NULL_VALUES)[["concern_type"]]
    n_total = len(current)

    psi, psi_snapshot = compute_psi(current, reference, "concern_type")
    status = status_for_psi(psi, run_id == reference_run_id)

    results = [{
        "agency_id": cp_common.AGENCY_ID,
        "collection_id": cp_common.COLLECTION_ID,
        "dataset_id": DATASET_ID,
        "check_id": PSI_CHECK_ID,
        "column_name": "concern_type",
        "check_name": "drift:PSI",
        "dimension": "consistency",
        "label": "Distribution drift",
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "metric_value": round(psi, 4) if psi is not None else None,
        "unit": "PSI",
        "warn_threshold": WARN_THRESHOLD,
        "fail_threshold": FAIL_THRESHOLD,
        "status": status,
        "on_fail_action": "flag",
        "row_count_total": n_total,
        "row_count_invalid": None,
        "engine": ENGINE_TAG,
        "reference_run_id": reference_run_id,
    }]
    # Written under the COLLECTION id, not this module's own table-scoped
    # DATASET_ID - 2026-09-16 fix, Keith's call: qa_results/ output stays
    # dataset(collection)-level for every tool, matching run_dbt_cp.py/
    # run_soda_cp.py/run_datacontract_cp.py/dataset_stats.py, which all
    # already write there. Evidently was the one real outlier (it only
    # ever checks cp_notifications, so it used TABLE_DATASET_ID directly
    # as its write path too) - each result record's own "dataset_id"
    # field above still correctly says "cp-notifications" for dashboard
    # per-table grouping; only the FILE location changes here.
    write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp, "evidently",
                     {"psi": psi_snapshot}, verified=results)
    return results


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    with open(os.path.join(CP_RAW_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    reference_run_id = manifest[0]["run_id"]  # not the module-level REFERENCE_RUN_ID default - see orchestrate_cp.py
    for entry in manifest:
        res = evaluate_evidently_cp(entry["run_id"], datetime.now(timezone.utc).isoformat(),
                                     reference_run_id=reference_run_id)
        r = res[0]
        print(f"{entry['run_id']:25s} PSI={r['metric_value']}  status={r['status']:5s}")
