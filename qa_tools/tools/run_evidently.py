"""Runs REAL Evidently AI for any collection (REQ-QAC-242): the collection's
PSI drift checks, all on one dataset, and a relative volume check per table, as its own
Evidently check file declares them (REQ-QAC-241).

The real evidently.Report + DataDriftPreset API, not a reimplementation -
PSI is computed in asset_model/drift.py. Evidently's PSI
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
per table, for every collection since REQ-QAC-247 and REQ-PIPE-248.
"""
from __future__ import annotations

import psycopg

from asset_model import collections
from qa_tools.common import asked_for, drift_reference, left_out, supply_db
from asset_model import drift, hierarchy
from qa_tools.common.evidently_common import ENGINE_TAG, recorded_row_counts, reference_value_counts
from asset_model.drift import (
    NO_REFERENCE,
    collection_checks,
    compute_psi,
    frame_from_value_counts,
    status_for,
)
from qa_tools.common.qa_results_writer import run_owner, write_qa_result

__all__ = ["ENGINE_TAG", "evaluate"]


def drift_dataset(collection_id: str) -> str | None:
    """The dataset a collection's drift checks are about, for a run that names
    no dataset of its own - the check ids' fourth segment
    (asset.agency.collection.dataset...) where they share one; None where the
    collection declares none, or declares them on several datasets, whose
    references are each run's own (REQ-QAC-297 criterion 11)."""
    datasets = {c.split(".")[3] for c in collection_checks(collection_id).psi}
    return next(iter(datasets)) if len(datasets) == 1 else None


def _excluding(frame, entry: dict):
    """evidently_common.excluding - the one copy, shared with the
    generator's drift planning (REQ-GEN-295 criterion 7 as amended)."""
    return drift.excluding(frame, entry)


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
    current = _excluding(_current_frame(run_id, table, entry["column"]), entry)
    empty = None
    if reference_run_id is None:
        psi, snapshot, status = None, None, NO_REFERENCE
    elif not len(current):
        # NOTHING TO COMPARE (found building REQ-GEN-298: TS-110's empty
        # geocoding file): Evidently refuses an empty frame, which took the
        # whole run down with it - coverage's 0 percent Fail included
        # (REQ-QAC-340 criterion 4). Recorded not evaluated, never a pass.
        psi, snapshot, status = None, None, NO_REFERENCE
        empty = ("The supply holds no rows to compare with the reference, so drift was not "
                 "measured. This check did not fail - it could not be evaluated.")
    else:
        reference = _excluding(_reference_frame(coll, reference_run_id, table, entry["column"]),
                               entry)
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
        **({"not_evaluated_reason": empty} if empty else {}),
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
    if reference_run_id is not None and reference is None:
        # NOTHING RECORDED FOR IT - a hand-supplied check's reference, staged
        # moments ago and never through QA here: count its staged rows, as
        # _reference_frame rebuilds the drift reference from them
        # (post-build-review #236).
        reference = _current_row_counts(reference_run_id, checks.row_drop)
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


def _assertion_table(coll, entry: dict, check_id: str) -> str:
    """The table an assertion check is about: its own `table`, else its
    check id's dataset's."""
    return entry.get("table") or _table_of(check_id)


def _assertion_result(coll, entry: dict, check_id: str, run_id: str,
                      run_timestamp: str) -> dict:
    """ONE ASSERTION ABOUT THIS SUPPLY ALONE (REQ-QAC-441), measured by the
    real Evidently Report - RowCount for `row_count`, MissingValueCount for
    `missing` - over the run's own view. Needs no reference, so it never
    reads as having none."""
    import pandas as pd
    from evidently import Dataset, DataDefinition, Report
    from evidently.metrics import MissingValueCount, RowCount

    table = _assertion_table(coll, entry, check_id)
    schema = supply_db.run_schema(run_id)
    with supply_db.connect(read_only=True, label="mothman:evidently-assert") as conn:
        conn.execute(f'SET search_path TO "{schema}"')
        if entry["method"] == "row_count":
            total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            frame = pd.DataFrame({"n": range(total)})
            column = None
        else:
            column = entry["column"]
            rows = conn.execute(f'SELECT "{column}" FROM {table}').fetchall()
            frame = pd.DataFrame({column: [None if r[0] is None else str(r[0]) for r in rows]},
                                 dtype=object)
            total = len(frame)
    metric = (RowCount() if column is None else MissingValueCount(column=column))
    dataset = Dataset.from_pandas(frame, data_definition=DataDefinition(
        text_columns=[] if column is None else [column]))
    got = Report([metric]).run(dataset, None).dict()["metrics"][0]["value"]
    if column is None:
        value, bad = int(got), None
        status = "pass" if value == int(entry["expected"]) else "fail"
        unit, label = "rows", "Row count"
        threshold = int(entry["expected"])
    else:
        value = bad = int(got["count"])
        status = "pass" if value == 0 else "fail"
        unit, label, threshold = "rows", "Null rate", 0
    return {
        "agency_id": coll.agency_id, "collection_id": coll.id,
        "dataset_id": hierarchy.dataset_for_table(table).dataset_id,
        "check_id": check_id, "column_name": column or "(table)",
        "check_name": f"evidently:{entry['method']}",
        "dimension": entry.get("category") or "completeness", "label": label,
        "run_id": run_id, "run_timestamp": run_timestamp,
        "metric_value": value, "unit": unit,
        "warn_threshold": None, "fail_threshold": threshold,
        "status": status, "on_fail_action": "flag",
        "row_count_total": total, "row_count_invalid": bad,
        "engine": ENGINE_TAG,
    }


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
    checks = collection_checks(coll.id)

    asked_for.ask(run_id, run_timestamp, coll.agency_id, coll.id, "evidently")
    results = []
    # EACH DATASET'S DRIFT CHECKS, for the run that is FOR it (REQ-QAC-297
    # criterion 11): a run evaluates the drift checks on its own table only.
    for psi_table in dict.fromkeys(_table_of(c) for c in checks.psi):
        if _psi_applies(run_id, psi_table):
            results.extend(_psi_result(coll, checks.checks[c], c, psi_table, run_id,
                                       run_timestamp, reference_run_id)
                           for c in checks.psi if _table_of(c) == psi_table)
    # EACH DRIFT CHECK'S SNAPSHOT BY ITS ID (REQ-QAC-231): read by nothing, and
    # never compared (tests/equiv_support.py leaves tool_output.raw_output out
    # of its snapshot), so the shape is free to say which.
    raw_output = {"psi": {r["check_id"]: r.pop("_snapshot") for r in results} or None}
    results.extend(_volume_per_table(coll, checks, run_id, run_timestamp, reference_run_id))
    # EACH ASSERTION, for the run that is FOR its table and can read it, as a
    # drift check is (REQ-QAC-441).
    for c in checks.assertions:
        if _psi_applies(run_id, _assertion_table(coll, checks.checks[c], c)):
            results.append(_assertion_result(coll, checks.checks[c], c, run_id, run_timestamp))
    evaluated = {r["check_id"] for r in results}
    left_out.note(run_id, "evidently", [
        c for c in (*checks.psi, *checks.row_drop.values(), *checks.assertions)
        if c not in evaluated and _unreadable(
            run_id, _assertion_table(coll, checks.checks[c], c) if c in checks.assertions
            else _table_of(c))])

    drift_reference.judge(results, assessment)
    write_qa_result(coll.agency_id, coll.id, run_id, run_timestamp, "evidently",
                    raw_output, verified=results)
    return results
