"""
Runs REAL Evidently AI (evidently>=0.7, the current Report/DataDriftPreset
API - a full rewrite since the 0.4.x API the original requirements-real.txt
assumed) against each run's `sex` column vs. the reference run
(run_01, same convention as engines/drift_engine.py), via the real
evidently.Report + evidently.presets.DataDriftPreset classes - not a
reimplementation of PSI.

Genuine finding from running the real tool, not assumed: Evidently's PSI
computation treats every DISTINCT VALUE actually observed in the column as
its own category (so a dirty run with three different invalid codes - e.g.
run_09's "9"/"U"/"O" - gets three separate PSI categories), where
engines/drift_engine.py's equivalent collapses everything outside {M,F,X}
into one combined "_other" bucket. Both are real, defensible PSI
implementations; they land in the same 0.1-0.25 "warn" band on run_09 but
at genuinely different values (real Evidently: ~0.144; the equivalent's
own 3-bucket-plus-other scheme: ~0.179) - PSI is sensitive to how many
categories the shift is binned into, and this is a real example of that,
not a bug in either. See README.md's known-disagreements section.
"""
from __future__ import annotations
import os

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW_DIR = os.path.join(ROOT, "data", "raw")

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"
ENGINE_TAG = "Evidently 0.7 (real)"

REFERENCE_RUN_ID = "run_01_2026-09-01"
# same pass/warn/fail bands engines/drift_engine.py uses, applied to the
# real PSI value Evidently computes - Evidently's own DataDriftPreset only
# carries one drift/no-drift threshold (0.1) by default, not a three-way
# band, so the warn/fail split here is this project's convention, not
# Evidently's.
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


def evaluate_evidently_real(run_id: str, csv_filename: str, run_timestamp: str,
                             reference_run_id: str = REFERENCE_RUN_ID,
                             reference_csv: str = f"{REFERENCE_RUN_ID}.csv") -> list[dict]:
    from evidently import Report
    from evidently.presets import DataDriftPreset

    reference = pd.read_csv(os.path.join(RAW_DIR, reference_csv))[["sex"]]
    current = pd.read_csv(os.path.join(RAW_DIR, csv_filename))[["sex"]]
    n_total = len(current)

    report = Report(metrics=[DataDriftPreset(columns=["sex"], cat_method="psi")])
    snapshot = report.run(current, reference)
    result = snapshot.dict()

    psi = None
    for m in result["metrics"]:
        if m["metric_name"].startswith("ValueDrift(column=sex"):
            psi = m["value"]
            break

    status = _status_for_psi(psi, run_id == reference_run_id)

    return [{
        "agency_id": AGENCY_ID,
        "collection_id": COLLECTION_ID,
        "dataset_id": DATASET_ID,
        "column_name": "sex",
        "check_name": "drift:PSI",
        "dimension": "consistency",
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

    with open(os.path.join(RAW_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    for entry in manifest:
        res = evaluate_evidently_real(entry["run_id"], entry["file"], datetime.now(timezone.utc).isoformat())
        r = res[0]
        print(f"{entry['run_id']:25s} PSI={r['metric_value']}  status={r['status']:5s}")
