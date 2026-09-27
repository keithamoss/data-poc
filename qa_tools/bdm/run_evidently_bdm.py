"""
Runs REAL Evidently AI (evidently>=0.7, the current Report/DataDriftPreset
API - a full rewrite since the 0.4.x API this project's dependencies originally
assumed) against each run's `sex` column vs. the reference run (run_01),
via the real evidently.Report + evidently.presets.DataDriftPreset classes -
not a reimplementation of PSI. PSI computation itself is shared with
run_evidently_cp.py via qa_tools/common/evidently_common.py - the
row-count-growth check below is birth-registrations-specific (Child
Protection's periodic-snapshot extract doesn't have the same "should
mostly grow" expectation an event feed does) - see plans/qa-pipeline.md #84.

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
import os

from . import bdm_common
from qa_tools.common.evidently_common import ENGINE_TAG, WARN_THRESHOLD, FAIL_THRESHOLD, status_for_psi, compute_psi
from qa_tools.common.qa_results_writer import write_qa_result
from .evidently_check_lifecycle import PSI_CHECK_ID, ROW_COUNT_GROWTH_CHECK_ID

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CONTRACT_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-contract.yaml")

AGENCY_ID = bdm_common.AGENCY_ID
COLLECTION_ID = bdm_common.COLLECTION_ID
DATASET_ID = bdm_common.DATASET_ID

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



def _previous_run_id(manifest: list[dict], run_id: str) -> str | None:
    """The immediately preceding run in manifest order, or None for the
    first run - unlike PSI's comparison against a fixed baseline run,
    "did row count grow" is inherently about consecutive runs, not a
    fixed reference.

    Returns the RUN ID rather than its csv_path (2026-09-27): the count
    now comes from what that run recorded, so its file is only a
    fallback for a run that was never staged."""
    for i, entry in enumerate(manifest):
        if entry["run_id"] == run_id:
            return manifest[i - 1]["run_id"] if i > 0 else None
    return None


def _recorded_previous_count(manifest: list[dict], previous_run_id: str) -> int | None:
    from qa_tools.common.evidently_common import recorded_row_count

    return recorded_row_count(AGENCY_ID, COLLECTION_ID, previous_run_id)


def _row_count_of(df) -> tuple[int, dict]:
    """Evidently's own RowCount metric over a frame already in hand.

    Takes a frame rather than a filename (2026-09-27) so the current
    run's count comes from the warehouse rows this module already read,
    rather than from re-opening the CSV it no longer depends on."""
    from evidently import Report
    from evidently.metrics import RowCount

    snapshot = Report(metrics=[RowCount()]).run(df, None)
    result = snapshot.dict()
    return int(result["metrics"][0]["value"]), result


def _current_frame(run_id: str):
    """This run's `sex` column, from the warehouse.

    NO CSV FALLBACK (REQ-PIPE-102, 2026-09-27). There used to be one,
    "for the ad-hoc local-file path where somebody is checking a file
    that was never staged" - and that premise was simply not true:
    `run_single()` calls `build_one()` before any tool runs, because
    the other three read the warehouse and would have nothing to read
    otherwise. The reference was the only genuinely unstaged thing,
    and the local-file path stages that too now.
    """
    import pandas as pd
    import psycopg

    from qa_tools.common import supply_db

    schema = supply_db.run_schema(run_id)
    with supply_db.connect(read_only=True, label="mothman:evidently-bdm") as conn:
        conn.execute(f'SET search_path TO "{schema}"')
        try:
            rows = conn.execute("SELECT sex FROM birth_registrations").fetchall()
        except psycopg.errors.UndefinedTable as exc:
            # NAME THE SCHEMA: PostgreSQL ignores a missing schema in
            # search_path rather than complaining, so the bare error
            # blames the table when a whole run's views are absent.
            existing = supply_db.run_schemas(conn)
            raise ValueError(
                f"run {run_id!r} has no readable birth_registrations: schema "
                f"{schema!r} {'exists but has no such view' if schema in existing else 'does not exist'}. "
                f"Stage that supply before checking it.") from exc
    return pd.DataFrame({"sex": [r[0] for r in rows]})


def _reference_frame(reference_run_id: str):
    """The reference distribution, rebuilt from what was RECORDED for
    that run rather than by finding its rows again.

    Its rows may be anywhere by now - staged, promoted into a period
    schema, or aged out - and none of that matters, because
    `dataset_stats` wrote its `sex` distribution down when it ran.

    WHERE NOTHING WAS RECORDED, THE WAREHOUSE - never a file
    (REQ-PIPE-102). An ad-hoc check names a reference run that has
    never been through QA here, so there is no recording yet and its
    rows were staged moments ago. Reading them is not the permissive
    fallback this removed: that one answered a failed database read
    from a copy on disk.
    """
    from qa_tools.common.evidently_common import (
        frame_from_value_counts, reference_value_counts,
    )

    counts = reference_value_counts(AGENCY_ID, COLLECTION_ID, reference_run_id, "sex")
    if counts:
        return frame_from_value_counts(counts, "sex")
    return _current_frame(reference_run_id)


def evaluate_evidently_bdm(run_id: str, run_timestamp: str,
                                 reference_run_id: str = REFERENCE_RUN_ID) -> list[dict]:
    """THE CURRENT RUN COMES FROM THE WAREHOUSE; THE REFERENCE COMES
    FROM WHAT WAS RECORDED (REQ-QAC-088, 2026-09-27).

    This was the last tool reading the supplier's CSV, which made it the
    one answering a different question from the other three - they
    checked what had been loaded, it checked what had been sent.

    The current run reads through its own view schema, which is open
    while it is being checked. The REFERENCE does not need its rows at
    all: its distribution was recorded by dataset_stats when it ran, so
    it is rebuilt from that. See evidently_common's own section for why
    that reconstruction is exact rather than approximate, and for the
    categorical-only limit.

    NO FILENAME PARAMETERS ANY MORE (REQ-PIPE-102, 2026-09-27). This
    took `csv_filename` and `reference_csv` as a fallback for "a
    supply checked without being staged", which is not a state that
    occurs: run_single() stages before any tool runs. Keeping them
    would have left two parameters naming a source nothing reads,
    which is the trap `build_all(raw_dir=...)` had already sprung
    once.
    """
    reference = _reference_frame(reference_run_id)
    current = _current_frame(run_id)
    n_total = len(current)

    psi, psi_snapshot = compute_psi(current, reference, "sex")
    status = status_for_psi(psi, run_id == reference_run_id)
    raw_output = {"psi": psi_snapshot}

    results = [{
        "agency_id": AGENCY_ID,
        "collection_id": COLLECTION_ID,
        "dataset_id": DATASET_ID,
        "check_id": PSI_CHECK_ID,
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

    from qa_tools.common import arrivals
    manifest = [a.as_entry() | {"csv_path": str(a.path_for("birth-registrations"))}
                for a in arrivals.arrivals_for("civil-registration", "run_")
                if "birth-registrations" not in a.held]
    previous_run_id = _previous_run_id(manifest, run_id)
    if previous_run_id is not None:
        # THE CURRENT COUNT IS MEASURED, THE PREVIOUS ONE WAS RECORDED.
        # Both used to come from re-reading a CSV. The previous run's
        # count was written down by dataset_stats when that run was
        # checked, so re-deriving it is both unnecessary and less true -
        # the recording is what the warehouse actually held.
        current_count, row_count_snapshot = _row_count_of(current)
        previous_count = _recorded_previous_count(manifest, previous_run_id)
        if previous_count is None:
            # NOTHING RECORDED FOR THE PREVIOUS RUN, so count its rows
            # in the WAREHOUSE - never by re-reading a CSV
            # (REQ-PIPE-102). Its rows were staged when it was checked.
            previous_count = _row_count_of(_current_frame(previous_run_id))[0]
        raw_output["row_count"] = row_count_snapshot
        rate_drop = (previous_count - current_count) / previous_count if previous_count else 0.0
        results.append({
            "agency_id": AGENCY_ID,
            "collection_id": COLLECTION_ID,
            "dataset_id": DATASET_ID,
            "check_id": ROW_COUNT_GROWTH_CHECK_ID,
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

    write_qa_result(AGENCY_ID, COLLECTION_ID, run_id, run_timestamp, "evidently", raw_output, verified=results)
    return results


if __name__ == "__main__":
    from datetime import datetime, timezone

    from qa_tools.common import arrivals
    manifest = [a.as_entry() | {"csv_path": str(a.path_for("birth-registrations"))}
                for a in arrivals.arrivals_for("civil-registration", "run_")
                if "birth-registrations" not in a.held]
    ref = manifest[0]  # not the module-level REFERENCE_RUN_ID default - see orchestrate_bdm.py
    for entry in manifest:
        res = evaluate_evidently_bdm(entry["run_id"], datetime.now(timezone.utc).isoformat(),
                                      reference_run_id=ref["run_id"])
        psi, growth = res[0], (res[1] if len(res) > 1 else None)
        growth_str = f"row_growth={growth['metric_value']:+.1f}%  status={growth['status']:5s}" if growth else "row_growth=n/a (first run)"
        print(f"{entry['run_id']:25s} PSI={psi['metric_value']}  status={psi['status']:5s}  |  {growth_str}")
