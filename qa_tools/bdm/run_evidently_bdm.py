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
from qa_tools.common.evidently_common import (
    ENGINE_TAG, WARN_THRESHOLD, FAIL_THRESHOLD, NO_REFERENCE, WARN_ROW_DROP, FAIL_ROW_DROP,
    status_for_psi, status_for_row_drop, compute_psi,
)
from qa_tools.common.qa_results_writer import write_qa_result
from .evidently_check_lifecycle import PSI_CHECK_ID, ROW_COUNT_GROWTH_CHECK_ID

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CONTRACT_PATH = os.path.join(ROOT, "contract", "bdm-birth-registrations-contract.yaml")

AGENCY_ID = bdm_common.AGENCY_ID
COLLECTION_ID = bdm_common.COLLECTION_ID
DATASET_ID = bdm_common.DATASET_ID

# THERE IS NO DEFAULT REFERENCE ANY MORE - see run_evidently_cp.py's
# identical note for the full account (REQ-QAC-108 criterion 4).

# THE BANDS AND THE BANDING MOVED TO evidently_common (REQ-QAC-108
# criterion 1, 2026-09-29), so Child Protection's six datasets share
# them rather than acquire a second convention. They were this
# collection's own, and the reasoning for the two-tier shape is worth
# keeping here where it was written: Evidently's RowCount metric does
# support a built-in Reference-based test (gte(Reference(relative=...))),
# tried first, but that gives one pass/fail band and buries the actual
# reference value inside a free-text test description rather than a
# clean field - computing the real row count for both runs and applying
# our own two-tier comparison, exactly like PSI, is both simpler and
# consistent.



def _recorded_previous_count(reference_run_id: str) -> int | None:
    """The row count that run RECORDED, or None where it recorded none.

    `_previous_run_id(manifest, run_id)` used to sit beside this and
    pick the immediately preceding ARRIVAL. It was removed 2026-09-29
    with REQ-QAC-108: criterion 2 gives drift and volume ONE reference,
    and criterion 4 rules out an arrival nobody promoted. A rejected
    supply was becoming the yardstick for the one after it.
    """
    from qa_tools.common.evidently_common import recorded_row_count

    return recorded_row_count(AGENCY_ID, COLLECTION_ID, reference_run_id)


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
    "for the local-file path where somebody is checking a file
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
    (REQ-PIPE-102). A hand-supplied check names a reference run that
    has never been through QA here, so there is no recording yet and its
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
                                 reference_run_id: str | None = None) -> list[dict]:
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
    current = _current_frame(run_id)
    n_total = len(current)

    if reference_run_id is None:
        # NOTHING TO MEASURE AGAINST (REQ-QAC-108 criterion 5). True of
        # this dataset's first supply, and of any supply whose earlier
        # periods hold only views. Reported as a check with no
        # reference, never as a pass.
        psi, psi_snapshot, status = None, None, NO_REFERENCE
    else:
        reference = _reference_frame(reference_run_id)
        psi, psi_snapshot = compute_psi(current, reference, "sex")
        status = status_for_psi(psi)
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

    # THE VOLUME CHECK TAKES THE SAME REFERENCE AS THE DRIFT ONE
    # (REQ-QAC-108 criterion 2, which says "every drift and volume
    # check" rather than naming them separately). It used to compare
    # against the PREVIOUS ARRIVAL, whatever became of it - so a supply
    # that arrived and was rejected became the yardstick for the one
    # after it, which is the failure criterion 4 names. Both checks now
    # measure against the last supply anybody actually promoted, and
    # both report no reference where there is none.
    #
    # THIS ALSO STOPPED A QA STEP READING THE DELIVERY TREE. Finding the
    # previous arrival meant walking data/deliveries/ from inside a
    # check, so the check's answer depended on what happened to be on
    # disk rather than on what had been recorded.
    current_count, row_count_snapshot = _row_count_of(current)
    raw_output["row_count"] = row_count_snapshot
    if reference_run_id is None:
        rate_drop, volume_status = None, NO_REFERENCE
    else:
        # THE CURRENT COUNT IS MEASURED, THE REFERENCE ONE WAS RECORDED.
        # Both used to come from re-reading a CSV. The reference run's
        # count was written down by dataset_stats when that run was
        # checked, so re-deriving it is both unnecessary and less true -
        # the recording is what the warehouse actually held.
        reference_count = _recorded_previous_count(reference_run_id)
        if reference_count is None:
            # NOTHING RECORDED FOR THE REFERENCE RUN, so count its rows
            # in the WAREHOUSE - never by re-reading a CSV
            # (REQ-PIPE-102). Its rows were staged when it was checked.
            reference_count = _row_count_of(_current_frame(reference_run_id))[0]
        rate_drop = ((reference_count - current_count) / reference_count
                     if reference_count else 0.0)
        volume_status = status_for_row_drop(rate_drop)
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
        "label": "Row count vs. last promoted supply",
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "metric_value": None if rate_drop is None else round(rate_drop * 100, 2),
        "unit": "%",
        "warn_threshold": round(WARN_ROW_DROP * 100, 2),
        "fail_threshold": round(FAIL_ROW_DROP * 100, 2),
        "status": volume_status,
        "on_fail_action": "flag",
        "row_count_total": current_count,
        "row_count_invalid": None,
        "engine": ENGINE_TAG,
        "reference_run_id": reference_run_id,
    })

    write_qa_result(AGENCY_ID, COLLECTION_ID, run_id, run_timestamp, "evidently", raw_output, verified=results)
    return results


if __name__ == "__main__":
    from datetime import datetime, timezone

    from qa_tools.common import arrivals, drift_reference
    found = [a for a in arrivals.arrivals_for("civil-registration", "run_")
             if "birth-registrations" not in a.contested]
    for arrival in found:
        entry = arrival.as_entry()
        res = evaluate_evidently_bdm(
            entry["run_id"], datetime.now(timezone.utc).isoformat(),
            reference_run_id=drift_reference.reference_run_for_arrival(
                DATASET_ID, arrival.received_at))
        psi, growth = res[0], (res[1] if len(res) > 1 else None)
        growth_str = f"row_growth={growth['metric_value']:+.1f}%  status={growth['status']:5s}" if growth else "row_growth=n/a (first run)"
        print(f"{entry['run_id']:25s} PSI={psi['metric_value']}  status={psi['status']:5s}  |  {growth_str}")
