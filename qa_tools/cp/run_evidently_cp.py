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

from qa_tools.common import hierarchy, left_out
from qa_tools.common.evidently_common import (
    ENGINE_TAG, WARN_THRESHOLD, FAIL_THRESHOLD, NO_REFERENCE, WARN_ROW_DROP, FAIL_ROW_DROP,
    status_for_psi, status_for_row_drop, compute_psi, recorded_row_counts,
)
from qa_tools.common.csv_io import load_null_values_by_column
from qa_tools.common import drift_reference
from qa_tools.common.qa_results_writer import write_qa_result
from . import cp_common
from .evidently_check_lifecycle import PSI_CHECK_ID, ROW_COUNT_GROWTH_CHECK_IDS

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


def _current_row_counts(run_id: str) -> dict[str, int]:
    """How many rows this run staged, per table.

    MEASURED HERE RATHER THAN READ FROM dataset_stats, because
    dataset_stats runs AFTER the tool steps - a check cannot compare
    against a number that does not exist yet when it runs. The reference
    side is read from what its own run recorded, which is the asymmetry
    REQ-QAC-088 established for PSI and this follows: measure the
    present, read the past.
    """
    from qa_tools.common import supply_db

    schema = supply_db.run_schema(run_id)
    counts: dict[str, int] = {}
    with supply_db.connect(read_only=True, label="mothman:evidently-cp-volume") as conn:
        # ASKED OF THE CATALOGUE FIRST, rather than counting each table
        # and catching the failures. A TABLE THIS RUN DID NOT STAGE IS
        # NOT A ZERO - single-table mode stages one and borrows the
        # rest, and a partial resupply is a real shape (REQ-PIPE-068),
        # so a missing view means "this run has nothing to say about
        # that table" rather than "it arrived empty", which is the
        # difference between silence and a red. Catching the error
        # instead would also leave the transaction aborted, so the
        # tables after the missing one would fail too.
        present = {row[0] for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [schema]).fetchall()}
        conn.execute(f'SET search_path TO "{schema}"')
        for table in ROW_COUNT_GROWTH_CHECK_IDS:
            if table in present:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return counts


def _volume_results(run_id: str, run_timestamp: str, reference_run_id: str | None) -> list[dict]:
    """One relative volume check per Child Protection dataset
    (REQ-QAC-108 criterion 1).

    SIX RATHER THAN ONE. The question is about a TABLE, and a
    collection-wide count would tell a reader something shrank without
    saying what. Birth Registrations needed one because it has one
    table, not because one is the right number.

    THE SAME BANDS AS BIRTH REGISTRATIONS, from evidently_common rather
    than restated here - criterion 1's own words are "so that both
    collections judge volume the same way", which two copies of two
    numbers would stop being true of on the first day somebody tuned
    one of them.
    """
    counts = _current_row_counts(run_id)
    reference = (None if reference_run_id is None else recorded_row_counts(
        cp_common.AGENCY_ID, cp_common.COLLECTION_ID, reference_run_id))

    out = []
    for table, check_id in ROW_COUNT_GROWTH_CHECK_IDS.items():
        if table not in counts:
            continue
        current = counts[table]
        before = (reference or {}).get(table)
        if not before:
            # NO REFERENCE, or a reference that recorded nothing for
            # this table (criterion 5). Zero counts here too, and
            # deliberately: dividing by it would be an error, and
            # calling a supply an infinite drop from nothing is not a
            # measurement.
            rate_drop, status = None, NO_REFERENCE
        else:
            rate_drop = (before - current) / before
            status = status_for_row_drop(rate_drop)
        out.append({
            "agency_id": cp_common.AGENCY_ID,
            "collection_id": cp_common.COLLECTION_ID,
            "dataset_id": hierarchy.dataset_for_table(table).dataset_id,
            "check_id": check_id,
            # "(table)" plus a supply-level check name is what puts this
            # in the dashboard's "Supply-level checks" section - which
            # is where "did this arrive the right size" belongs, and is
            # the mechanism REQ-DASH-033 built rather than a lookalike.
            # Birth Registrations attributes its own to a real column
            # because its builder has no such section.
            "column_name": "(table)",
            "check_name": "evidently:row_count_growth",
            "dimension": "timeliness",
            "label": "Row count vs. last promoted supply",
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "metric_value": None if rate_drop is None else round(rate_drop * 100, 2),
            "unit": "%",
            "warn_threshold": round(WARN_ROW_DROP * 100, 2),
            "fail_threshold": round(FAIL_ROW_DROP * 100, 2),
            "status": status,
            "on_fail_action": "flag",
            "row_count_total": current,
            "row_count_invalid": None,
            "engine": ENGINE_TAG,
            "reference_run_id": reference_run_id,
        })
    return out


def evaluate_evidently_cp(run_id: str, run_timestamp: str,
                                reference_run_id: str | None = None,
        assessment=None) -> list[dict]:
    """Reads the warehouse for the current run and the RECORDED
    distribution for the reference (REQ-QAC-088, 2026-09-27) - the BDM
    counterpart carries the full account.

    `reference_run_id=None` MEANS THERE IS NOTHING TO MEASURE AGAINST
    (REQ-QAC-108 criterion 5), which is true of every dataset's first
    supply and of any supply whose earlier periods hold only views. The
    check is then reported as having no reference, and specifically NOT
    as passing - see evidently_common.NO_REFERENCE.
    """
    results = []
    if _psi_applies(run_id):
        results.append(_psi_result(run_id, run_timestamp, reference_run_id))
    results.extend(_volume_results(run_id, run_timestamp, reference_run_id))
    # WHAT IT DID NOT EVALUATE FOR WANT OF A TABLE (REQ-PIPE-115
    # criterion 17) - a run that is not for cp_notifications skipping PSI
    # is out of its scope, not left out, and the scope filter says so.
    evaluated = {r["check_id"] for r in results}
    left_out.note(run_id, "evidently", [
        c for c in (PSI_CHECK_ID, *ROW_COUNT_GROWTH_CHECK_IDS.values())
        if c not in evaluated and _unreadable_for(run_id, c)])

    # Written under the COLLECTION id, not this module's own table-scoped
    # DATASET_ID - 2026-09-16 fix, Keith's call: qa_results/ output stays
    # dataset(collection)-level for every tool, matching run_dbt_cp.py/
    # run_soda_cp.py/run_datacontract_cp.py/dataset_stats.py, which all
    # already write there. Evidently was the one real outlier (it only
    # ever checks cp_notifications, so it resolves that table directly
    # as its write path too) - each result record's own "dataset_id"
    # field above still correctly says "cp-notifications" for dashboard
    # per-table grouping; only the FILE location changes here.
    psi_snapshot = results[0].pop("_snapshot", None) if results and \
        results[0].get("check_id") == PSI_CHECK_ID else None
    # THE GAP RULE (REQ-QAC-108 criteria 8 to 17) - drift_reference.judge.
    drift_reference.judge(results, assessment)
    write_qa_result(cp_common.AGENCY_ID, cp_common.COLLECTION_ID, run_id, run_timestamp, "evidently",
                     {"psi": psi_snapshot}, verified=results)
    return results


def _unreadable_for(run_id: str, check_id: str) -> bool:
    """Whether `check_id` went unevaluated because its table cannot be
    read, rather than because it is another run's."""
    from qa_tools.common import supply_db

    table = ("cp_notifications" if check_id == PSI_CHECK_ID else
             next(t for t, c in ROW_COUNT_GROWTH_CHECK_IDS.items() if c == check_id))
    with supply_db.connect(read_only=True, label="mothman:evidently-cp") as conn:
        return table in supply_db.resolution_for(conn, run_id).unreadable


def _psi_applies(run_id: str) -> bool:
    """Whether this run should evaluate the cp_notifications PSI check.

    ONLY A RUN THAT CAN READ cp_notifications (2026-10-02). One file is
    one arrival (REQ-PIPE-105), so a run reads its siblings from its
    period and cp_notifications can be absent - held, contested with
    nothing promoted, or in a different period from a Case Workers file.
    Reading it raised and failed the run after three tools had recorded
    their results. Not run is the honest outcome, as for dbt and Soda.

    AND ONLY A RUN THAT IS FOR cp_notifications, where the run names a
    table at all. The check is about that table, its reference is that
    table's last promoted supply, and the results writer would discard
    it from any other table's run anyway - so evaluating it there costs
    a reference lookup that can fail for a result nobody keeps. A run
    whose id names no table (a trial, a fixture) evaluates it as before.
    """
    from qa_tools.common import supply_db
    from qa_tools.common.qa_results_writer import run_owner

    owner = run_owner(run_id)
    if owner is not None and owner[1] != "cp_notifications":
        return False
    with supply_db.connect(read_only=True, label="mothman:evidently-cp") as conn:
        return "cp_notifications" not in supply_db.resolution_for(conn, run_id).unreadable


def _psi_result(run_id: str, run_timestamp: str, reference_run_id: str | None) -> dict:
    """The one PSI result over cp_notifications.concern_type."""
    current = _current_frame(run_id)
    n_total = len(current)

    if reference_run_id is None:
        psi, psi_snapshot, status = None, None, NO_REFERENCE
    else:
        reference = _reference_frame(reference_run_id)
        psi, psi_snapshot = compute_psi(current, reference, "concern_type")
        status = status_for_psi(psi)

    return {
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
        # Popped by the caller before anything is recorded: the raw
        # snapshot goes into the tool's raw output, not into a result.
        "_snapshot": psi_snapshot,
    }


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
