"""
Runs REAL Evidently AI against cp_notifications' concern_type column (the
Child Protection collection's traffic-light demo column - dirty.py's
apply_cp_notifications_presets is the only preset that touches it, the
same role sex plays for Birth Registrations) vs. the first clean run as
reference - the Child Protection counterpart to run_evidently_real.py.

Same real evidently.Report + evidently.presets.DataDriftPreset API, same
per-distinct-observed-value PSI binning behaviour documented there.
"""
from __future__ import annotations
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import cp_common

ROOT = os.path.join(os.path.dirname(__file__), "..")
CP_RAW_DIR = os.path.join(ROOT, "data", "cp_raw")

ENGINE_TAG = "Evidently 0.7 (real)"
DATASET_ID = cp_common.TABLE_DATASET_ID["cp_notifications"]

REFERENCE_RUN_ID = "cp_run_01_2026-07-06"
# same convention as run_evidently_real.py - Evidently's DataDriftPreset
# only carries one drift/no-drift threshold (0.1) by default, so the
# warn/fail split below is this project's own convention.
WARN_THRESHOLD = 0.10
FAIL_THRESHOLD = 0.25


def _status_for_psi(psi: float, is_reference: bool) -> str:
    if is_reference:
        return "pass"
    if psi > FAIL_THRESHOLD:
        return "fail"
    if psi > WARN_THRESHOLD:
        return "warn"
    return "pass"


def evaluate_evidently_real_cp(run_id: str, run_timestamp: str,
                                reference_run_id: str = REFERENCE_RUN_ID) -> list[dict]:
    from evidently import Report
    from evidently.presets import DataDriftPreset

    reference = pd.read_csv(os.path.join(CP_RAW_DIR, reference_run_id, "cp_notifications.csv"))[["concern_type"]]
    current = pd.read_csv(os.path.join(CP_RAW_DIR, run_id, "cp_notifications.csv"))[["concern_type"]]
    n_total = len(current)

    report = Report(metrics=[DataDriftPreset(columns=["concern_type"], cat_method="psi")])
    snapshot = report.run(current, reference)
    result = snapshot.dict()

    psi = None
    for m in result["metrics"]:
        if m["metric_name"].startswith("ValueDrift(column=concern_type"):
            psi = m["value"]
            break

    status = _status_for_psi(psi, run_id == reference_run_id)

    return [{
        "agency_id": cp_common.AGENCY_ID,
        "collection_id": cp_common.COLLECTION_ID,
        "dataset_id": DATASET_ID,
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


if __name__ == "__main__":
    import json
    from datetime import datetime, timezone

    with open(os.path.join(CP_RAW_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    for entry in manifest:
        res = evaluate_evidently_real_cp(entry["run_id"], datetime.now(timezone.utc).isoformat())
        r = res[0]
        print(f"{entry['run_id']:25s} PSI={r['metric_value']}  status={r['status']:5s}")
