"""Runs REAL Evidently AI for any collection (REQ-QAC-242): the collection's
one PSI drift check, and a relative volume check per table, as its own
Evidently check file declares them (REQ-QAC-241).

The real evidently.Report + DataDriftPreset API, not a reimplementation -
PSI is computed in qa_tools/common/evidently_common.py. Evidently's PSI
treats every DISTINCT VALUE observed in the column as its own category, so
a dirty run with three different invalid codes gets three separate
categories; PSI is sensitive to that binning (README.md's
known-disagreements section).

THE CURRENT RUN COMES FROM THE WAREHOUSE; THE REFERENCE FROM WHAT WAS
RECORDED (REQ-QAC-088). The current run reads through its own view schema.
The reference's distribution was recorded by dataset_stats when it ran, so
it is rebuilt from that - exact for a categorical column, see
evidently_common. `reference_run_id=None` means there is nothing to measure
against (REQ-QAC-108 criterion 5): reported as having no reference, never as
passing.

BUILT FROM CHILD PROTECTION'S COPY: a check over a table the run cannot read
is not run and is noted as left out (REQ-PIPE-078), and volume is counted
per table. Birth Registrations' single-table copy differs in two places,
kept behind its legacy flags (qa_tools/tools/legacy.py).
"""
from __future__ import annotations

import psycopg

from qa_tools import collections
from qa_tools.common import asked_for, drift_reference, hierarchy, left_out, supply_db
from qa_tools.common.evidently_common import (
    ENGINE_TAG, NO_REFERENCE, collection_checks, compute_psi, frame_from_value_counts,
    recorded_row_count, recorded_row_counts, reference_value_counts, status_for,
)
from qa_tools.common.qa_results_writer import run_owner, write_qa_result

__all__ = ["ENGINE_TAG", "evaluate"]


def drift_dataset(collection_id: str) -> str:
    """The dataset a collection's drift check is about - the check id's
    fourth segment (asset.agency.collection.dataset...)."""
    return collection_checks(collection_id).psi.split(".")[3]


def _table_of(check_id: str) -> str:
    """The table a check is over: its dataset is the check id's fourth
    segment (asset.agency.collection.dataset...)."""
    return hierarchy.dataset(check_id.split(".")[3]).table


def _current_frame(run_id: str, table: str, column: str):
    """This run's drift column, from the warehouse. NO CSV FALLBACK
    (REQ-PIPE-102): every path that reaches here stages first, so a missing
    view is an error to report, not a cue to read a file."""
    import pandas as pd

    schema = supply_db.run_schema(run_id)
    with supply_db.connect(read_only=True, label="mothman:evidently") as conn:
        conn.execute(f'SET search_path TO "{schema}"')
        try:
            rows = conn.execute(f'SELECT {column} FROM {table}').fetchall()
        except psycopg.errors.UndefinedTable as exc:
            existing = supply_db.run_schemas(conn)
            raise ValueError(
                f"run {run_id!r} has no readable {table}: schema {schema!r} "
                f"{'exists but has no such view' if schema in existing else 'does not exist'}. "
                f"Stage that supply before checking it.") from exc
    return pd.DataFrame({column: [r[0] for r in rows]})


def _reference_frame(coll, reference_run_id: str, table: str, column: str):
    """Rebuilt from what that run RECORDED, so its rows need not be found.
    Where nothing was recorded - a hand-supplied check names a reference
    never through QA here, staged moments ago - the warehouse, never a file."""
    counts = reference_value_counts(coll.agency_id, coll.id, reference_run_id, column)
    if counts:
        return frame_from_value_counts(counts, column)
    return _current_frame(reference_run_id, table, column)


def _psi_result(coll, entry, check_id, table, run_id, run_timestamp, reference_run_id) -> dict:
    current = _current_frame(run_id, table, entry["column"])
    if reference_run_id is None:
        psi, snapshot, status = None, None, NO_REFERENCE
    else:
        reference = _reference_frame(coll, reference_run_id, table, entry["column"])
        psi, snapshot = compute_psi(current, reference, entry["column"])
        status = status_for(psi, entry)
    return {
        "agency_id": coll.agency_id,
        "collection_id": coll.id,
        "dataset_id": hierarchy.dataset_for_table(table).dataset_id,
        "check_id": check_id,
        "column_name": entry["column"],
        "check_name": "drift:PSI",
        "dimension": "consistency",
        "label": "Distribution drift",
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "metric_value": round(psi, 4) if psi is not None else None,
        "unit": "PSI",
        "warn_threshold": entry["warn_threshold"],
        "fail_threshold": entry["fail_threshold"],
        "status": status,
        "on_fail_action": "flag",
        "row_count_total": len(current),
        "row_count_invalid": None,
        "engine": ENGINE_TAG,
        "reference_run_id": reference_run_id,
        "_snapshot": snapshot,
        "_frame": current,
    }


def _volume_result(coll, entry, check_id, table, column_name, run_id, run_timestamp,
                   reference_run_id, current, rate_drop, status) -> dict:
    return {
        "agency_id": coll.agency_id,
        "collection_id": coll.id,
        "dataset_id": hierarchy.dataset_for_table(table).dataset_id,
        "check_id": check_id,
        "column_name": column_name,
        "check_name": "evidently:row_count_growth",
        "dimension": "timeliness",
        "label": "Row count vs. last promoted supply",
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "metric_value": None if rate_drop is None else round(rate_drop * 100, 2),
        "unit": "%",
        "warn_threshold": round(entry["warn_threshold"] * 100, 2),
        "fail_threshold": round(entry["fail_threshold"] * 100, 2),
        "status": status,
        "on_fail_action": "flag",
        "row_count_total": current,
        "row_count_invalid": None,
        "engine": ENGINE_TAG,
        "reference_run_id": reference_run_id,
    }


def _current_row_counts(run_id: str, tables) -> dict[str, int]:
    """How many rows this run staged, per table - MEASURED HERE rather than
    read from dataset_stats, which runs after the tool steps: measure the
    present, read the past (REQ-QAC-088)."""
    schema = supply_db.run_schema(run_id)
    counts: dict[str, int] = {}
    with supply_db.connect(read_only=True, label="mothman:evidently-volume") as conn:
        present = {row[0] for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [schema]).fetchall()}
        conn.execute(f'SET search_path TO "{schema}"')
        for table in tables:
            if table in present:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return counts


def _volume_per_table(coll, checks, run_id, run_timestamp, reference_run_id) -> list[dict]:
    """One relative volume check per table (REQ-QAC-108 criterion 1): the
    question is about a TABLE, and a collection-wide count would say
    something shrank without saying what."""
    counts = _current_row_counts(run_id, checks.row_drop)
    reference = (None if reference_run_id is None
                 else recorded_row_counts(coll.agency_id, coll.id, reference_run_id))
    out = []
    for table, check_id in checks.row_drop.items():
        if table not in counts:
            continue
        current = counts[table]
        before = (reference or {}).get(table)
        if not before:
            rate_drop, status = None, NO_REFERENCE
        else:
            rate_drop = (before - current) / before
            status = status_for(rate_drop, checks.checks[check_id])
        out.append(_volume_result(coll, checks.checks[check_id], check_id, table, "(table)",
                                  run_id, run_timestamp, reference_run_id, current,
                                  rate_drop, status))
    return out


def _row_count_of(df) -> tuple[int, dict]:
    """Evidently's own RowCount metric over a frame already in hand."""
    from evidently import Report
    from evidently.metrics import RowCount

    snapshot = Report(metrics=[RowCount()]).run(df, None)
    result = snapshot.dict()
    return int(result["metrics"][0]["value"]), result


def _volume_from_drift_frame(coll, checks, psi, run_id, run_timestamp, reference_run_id,
                             raw_output) -> list[dict]:
    """LEGACY `evidently.volume_from_drift_frame`: the one volume check
    counted by Evidently's RowCount over the drift frame already read, its
    snapshot kept in the raw output, a reference with no recorded count
    counted from its rows, and a reference of zero rows read as no drop."""
    [(table, check_id)] = checks.row_drop.items()
    if table != _table_of(checks.psi):
        raise ValueError(f"{coll.id}: evidently.volume_from_drift_frame needs the volume check "
                         f"on the drift check's own table, not {table!r}")
    entry = checks.checks[check_id]
    current, raw_output["row_count"] = _row_count_of(psi["_frame"])
    if reference_run_id is None:
        rate_drop, status = None, NO_REFERENCE
    else:
        before = recorded_row_count(coll.agency_id, coll.id, reference_run_id)
        if before is None:
            before = _row_count_of(_current_frame(reference_run_id, table, psi["column_name"]))[0]
        rate_drop = (before - current) / before if before else 0.0
        status = status_for(rate_drop, entry)
    return [_volume_result(coll, entry, check_id, table, entry["column"], run_id, run_timestamp,
                           reference_run_id, current, rate_drop, status)]


def _psi_applies(run_id: str, table: str) -> bool:
    """ONLY A RUN THAT CAN READ the drift check's table (2026-10-02), and only
    one that is FOR that table where the run names one: the check is about
    that table, its reference is that table's last promoted supply, and the
    results writer would discard it from any other table's run anyway."""
    owner = run_owner(run_id)
    if owner is not None and owner[1] != table:
        return False
    with supply_db.connect(read_only=True, label="mothman:evidently") as conn:
        return table not in supply_db.resolution_for(conn, run_id).unreadable


def _unreadable(run_id: str, table: str) -> bool:
    with supply_db.connect(read_only=True, label="mothman:evidently") as conn:
        return table in supply_db.resolution_for(conn, run_id).unreadable


def evaluate(collection_id: str, run_id: str, run_timestamp: str,
             reference_run_id: str | None = None, assessment=None) -> list[dict]:
    coll = collections.by_id(collection_id)
    adapter = collections.adapter(coll)
    checks = collection_checks(coll.id)
    psi_entry, psi_table = checks.checks[checks.psi], _table_of(checks.psi)

    asked_for.ask(run_id, run_timestamp, coll.agency_id, coll.id, "evidently")
    results = []
    if _psi_applies(run_id, psi_table):
        results.append(_psi_result(coll, psi_entry, checks.psi, psi_table, run_id,
                                   run_timestamp, reference_run_id))
    raw_output = {"psi": results[0].pop("_snapshot") if results else None}
    if "evidently.volume_from_drift_frame" in adapter.legacy:
        results.extend(_volume_from_drift_frame(coll, checks, results[0], run_id, run_timestamp,
                                                reference_run_id, raw_output))
    else:
        results.extend(_volume_per_table(coll, checks, run_id, run_timestamp, reference_run_id))
    for r in results:
        r.pop("_frame", None)
    evaluated = {r["check_id"] for r in results}
    left_out.note(run_id, "evidently", [
        c for c in (checks.psi, *checks.row_drop.values())
        if c not in evaluated and _unreadable(run_id, _table_of(c))])

    drift_reference.judge(results, assessment)
    write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, "evidently",
                    raw_output, verified=results)
    return results
