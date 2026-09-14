"""
Runs REAL Evidently AI (evidently>=0.7, the current Report/DataDriftPreset
API - a full rewrite since the 0.4.x API this project's dependencies originally
assumed) against each run's `sex` column vs. the reference run (run_01),
via the real evidently.Report + evidently.presets.DataDriftPreset classes -
not a reimplementation of PSI. PSI computation itself is shared with
run_evidently_cp.py via qa_tools/common/evidently_common.py - the
row-count-growth check below is birth-registrations-specific (Child
Protection's periodic-snapshot extract doesn't have the same "should
mostly grow" expectation an event feed does) - see plans/wider.md #20.

Genuine finding from running the real tool, not assumed: Evidently's PSI
computation treats every DISTINCT VALUE actually observed in the column as
its own category (so a dirty run with three different invalid codes - e.g.
run_09's "9"/"U"/"O" - gets three separate PSI categories). Found by
comparing against the equivalent engine that existed at the time (since
removed), which collapsed everything outside {M,F,X} into one combined
"_other" bucket - both landed in the same 0.1-0.25 "warn" band on run_09
but at genuinely different values (real Evidently: ~0.144; the
equivalent's own 3-bucket-plus-other scheme: ~0.179) - PSI is sensitive to
how many categories the shift is binned into. See README.md's
known-disagreements section.
"""
from __future__ import annotations
import json
import os

import pandas as pd

from qa_tools.common.evidently_common import ENGINE_TAG, WARN_THRESHOLD, FAIL_THRESHOLD, status_for_psi, compute_psi

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
RAW_DIR = os.path.join(ROOT, "data", "raw")

AGENCY_ID = "registry-services"
COLLECTION_ID = "civil-registration"
DATASET_ID = "birth-registrations"

# A fallback default only - see run_evidently_cp.py's identical comment
# and orchestrate_bdm.py for why real callers never rely on it.
REFERENCE_RUN_ID = "run_01_2026-09-01"

# Row-growth check: "some reduction in a daily refresh is fine" (Keith's
# own words) - so only a genuinely large drop trips this, not any decrease
# at all. Same two-tier-band-is-our-convention-not-the-tool's approach as
# PSI: Evidently's RowCount metric does support a built-in Reference-based
# test (gte(Reference(relative=...))), tried first, but that only gives
# one pass/fail band and buries the actual reference value inside a
# free-text test description rather than a clean field - computing the
# real row count via Evidently for both runs and applying our own two-tier
# comparison, exactly like PSI, is both simpler and consistent.
WARN_ROW_DROP = 0.10
FAIL_ROW_DROP = 0.25


def _status_for_row_drop(rate_drop: float) -> str:
    if rate_drop > FAIL_ROW_DROP:
        return "fail"
    if rate_drop > WARN_ROW_DROP:
        return "warn"
    return "pass"


def _row_count(csv_filename: str) -> int:
    from evidently import Report
    from evidently.metrics import RowCount

    df = pd.read_csv(os.path.join(RAW_DIR, csv_filename))
    snapshot = Report(metrics=[RowCount()]).run(df, None)
    return int(snapshot.dict()["metrics"][0]["value"])


def _previous_run_file(manifest: list[dict], run_id: str) -> str | None:
    """The immediately preceding run in manifest order, or None for the
    first run - unlike PSI's comparison against a fixed baseline run,
    "did row count grow" is inherently about consecutive runs, not a
    fixed reference."""
    for i, entry in enumerate(manifest):
        if entry["run_id"] == run_id:
            return manifest[i - 1]["file"] if i > 0 else None
    return None


def evaluate_evidently_bdm(run_id: str, csv_filename: str, run_timestamp: str,
                                 reference_run_id: str = REFERENCE_RUN_ID,
                                 reference_csv: str = f"{REFERENCE_RUN_ID}.csv") -> list[dict]:
    reference = pd.read_csv(os.path.join(RAW_DIR, reference_csv))[["sex"]]
    current = pd.read_csv(os.path.join(RAW_DIR, csv_filename))[["sex"]]
    n_total = len(current)

    psi = compute_psi(current, reference, "sex")
    status = status_for_psi(psi, run_id == reference_run_id)

    results = [{
        "agency_id": AGENCY_ID,
        "collection_id": COLLECTION_ID,
        "dataset_id": DATASET_ID,
        "column_name": "sex",
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

    with open(os.path.join(RAW_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    previous_file = _previous_run_file(manifest, run_id)
    if previous_file is not None:
        current_count = _row_count(csv_filename)
        previous_count = _row_count(previous_file)
        rate_drop = (previous_count - current_count) / previous_count if previous_count else 0.0
        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            # No single column "owns" a whole-dataset row count; attributed
            # to registration_number (the row-identifying primary key) as
            # the least-arbitrary home, rather than "(table)" - which
            # birth-registrations' dashboard builder silently drops (see
            # pipeline/build_dashboard_data.py; there's no "(table-level
            # checks)" pseudo-column here the way Child Protection has).
            "column_name": "registration_number",
            "check_name": "evidently:row_count_growth",
            "dimension": "timeliness",
            "label": "Row count vs. previous run",
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": round(rate_drop * 100, 2),
            "unit": "%",
            "warn_threshold": round(WARN_ROW_DROP * 100, 2),
            "fail_threshold": round(FAIL_ROW_DROP * 100, 2),
            "status": _status_for_row_drop(rate_drop),
            "on_fail_action": "flag",
            "row_count_total": current_count,
            "row_count_invalid": None,
            "engine": ENGINE_TAG,
            "reference_run_id": None,
        })

    return results


if __name__ == "__main__":
    from datetime import datetime, timezone

    with open(os.path.join(RAW_DIR, "manifest.json")) as f:
        manifest = json.load(f)
    ref = manifest[0]  # not the module-level REFERENCE_RUN_ID default - see orchestrate_bdm.py
    for entry in manifest:
        res = evaluate_evidently_bdm(entry["run_id"], entry["file"], datetime.now(timezone.utc).isoformat(),
                                      reference_run_id=ref["run_id"], reference_csv=ref["file"])
        psi, growth = res[0], (res[1] if len(res) > 1 else None)
        growth_str = f"row_growth={growth['metric_value']:+.1f}%  status={growth['status']:5s}" if growth else "row_growth=n/a (first run)"
        print(f"{entry['run_id']:25s} PSI={psi['metric_value']}  status={psi['status']:5s}  |  {growth_str}")
