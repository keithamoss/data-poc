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

import psycopg

from qa_tools.common import hierarchy
from qa_tools.common.evidently_common import (
    ENGINE_TAG, WARN_THRESHOLD, FAIL_THRESHOLD, NO_REFERENCE, status_for_psi, compute_psi,
)
from qa_tools.common.csv_io import load_null_values_by_column
from qa_tools.common.qa_results_writer import write_qa_result
from . import cp_common
from .evidently_check_lifecycle import PSI_CHECK_ID

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CONTRACT_PATH = os.path.join(ROOT, "contract", "child-protection-contract.yaml")
_NULL_VALUES = load_null_values_by_column(CONTRACT_PATH).get("cp_notifications", {})

DATASET_ID = hierarchy.dataset_for_table("cp_notifications").dataset_id

# THERE IS NO DEFAULT REFERENCE ANY MORE (REQ-QAC-108 criterion 4,
# 2026-09-29). This module carried a hardcoded REFERENCE_RUN_ID, and
# then its callers carried `manifest[0]["run_id"]` to avoid it - which
# is the same mistake computed fresh: every supply measured against the
# beginning of history, so drift stops being detectable about a year in.
# The reference is now the most recent EARLIER period a supply was
# really promoted into, resolved per supply by
# drift_reference.reference_run_for_arrival(), and `None` means there is
# no such period rather than "use a default".


_COLUMN = "concern_type"


def _current_frame(run_id: str):
    """This run's column, from the warehouse - see the BDM counterpart.

    NO CSV FALLBACK ANY MORE (REQ-PIPE-102, 2026-09-27). This used to
    catch a bare `Exception` and read `data/cp_raw/<run_id>/
    cp_notifications.csv` instead, which meant a lock, a missing view
    or a wrong schema produced a drift number computed from a file
    rather than an error - a plausible-looking answer to a question
    that had actually failed. Every path that reaches here stages into
    the warehouse first, hand-supplied checks included, so there is no case
    left where the rows are absent and a file would still be right.
    """
    import pandas as pd

    from qa_tools.common import supply_db

    schema = supply_db.run_schema(run_id)
    with supply_db.connect(read_only=True, label="mothman:evidently-cp") as conn:
        conn.execute(f'SET search_path TO "{schema}"')
        try:
            rows = conn.execute(f"SELECT {_COLUMN} FROM cp_notifications").fetchall()
        except psycopg.errors.UndefinedTable as exc:
            # NAME THE SCHEMA. PostgreSQL ignores a missing schema in
            # search_path rather than complaining, so the bare error
            # says only "cp_notifications does not exist" and sends the
            # reader looking for a table when the problem is a whole
            # run's views being absent.
            existing = supply_db.run_schemas(conn)
            raise ValueError(
                f"run {run_id!r} has no readable cp_notifications: schema {schema!r} "
                f"{'exists but has no such view' if schema in existing else 'does not exist'}. "
                f"Stage that supply before checking it.") from exc
    return pd.DataFrame({_COLUMN: [r[0] for r in rows]})


def _reference_frame(reference_run_id: str):
    """Rebuilt from what that run RECORDED, so its rows need not be
    found - see qa_tools/common/evidently_common.py for why that is
    exact for a categorical column.

    A reference with no recorded distribution is an error rather than a
    cue to go looking on disk: drift measured against a baseline nobody
    can name is not a measurement.
    """
    from qa_tools.common.evidently_common import (
        frame_from_value_counts, reference_value_counts,
    )

    counts = reference_value_counts(
        cp_common.AGENCY_ID, cp_common.COLLECTION_ID, reference_run_id, _COLUMN)
    if counts:
        return frame_from_value_counts(counts, _COLUMN)
    # NO RECORDING YET, SO READ THE WAREHOUSE - never a CSV
    # (REQ-PIPE-102 criterion 4). A recorded distribution is the
    # preferred source because it keeps working after the reference
    # supply's own rows have aged out of staging; but a check against
    # a folder somebody handed us creates a brand-new reference run that
    # has never been QA'd, so there is nothing recorded for it yet and
    # its rows are right there, freshly staged. Reading them is not the
    # permissive fallback this requirement removed - that one answered
    # a failed database read from a file on disk. This reads the same
    # database, and still fails if the rows are not there either.
    return _current_frame(reference_run_id)


def evaluate_evidently_cp(run_id: str, run_timestamp: str,
                                reference_run_id: str | None = None) -> list[dict]:
    """Reads the warehouse for the current run and the RECORDED
    distribution for the reference (REQ-QAC-088, 2026-09-27) - the BDM
    counterpart carries the full account.

    `reference_run_id=None` MEANS THERE IS NOTHING TO MEASURE AGAINST
    (REQ-QAC-108 criterion 5), which is true of every dataset's first
    supply and of any supply whose earlier periods hold only views. The
    check is then reported as having no reference, and specifically NOT
    as passing - see evidently_common.NO_REFERENCE.
    """
    current = _current_frame(run_id)
    n_total = len(current)

    if reference_run_id is None:
        psi, psi_snapshot, status = None, None, NO_REFERENCE
    else:
        reference = _reference_frame(reference_run_id)
        psi, psi_snapshot = compute_psi(current, reference, "concern_type")
        status = status_for_psi(psi)

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
    # ever checks cp_notifications, so it resolves that table directly
    # as its write path too) - each result record's own "dataset_id"
    # field above still correctly says "cp-notifications" for dashboard
    # per-table grouping; only the FILE location changes here.
    write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp, "evidently",
                     {"psi": psi_snapshot}, verified=results)
    return results


if __name__ == "__main__":
    from datetime import datetime, timezone

    from qa_tools.common import arrivals
    from qa_tools.common import drift_reference
    manifest = [a for a in arrivals.arrivals_for("child-protection", "cp_run_")]
    for arrival in manifest:
        entry = arrival.as_entry()
        reference_run_id = drift_reference.reference_run_for_arrival(
            DATASET_ID, arrival.received_at)
        res = evaluate_evidently_cp(entry["run_id"], datetime.now(timezone.utc).isoformat(),
                                     reference_run_id=reference_run_id)
        r = res[0]
        print(f"{entry['run_id']:25s} PSI={r['metric_value']}  status={r['status']:5s}")
