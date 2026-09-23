"""Real integration tests for orchestrate_bdm.run_single()/orchestrate_
cp.run_single() - the AWS event-driven MVP's single-arrival entry points
(plans/running-thoughts.md #5 Thread B / docs/aws-event-driven-mvp-
design.md), built to reuse _run_one() unchanged rather than duplicate it.

Runs the REAL 4-tool chain (dbt-core/Soda Core/datacontract-cli/
Evidently) against the same small, real, session-scoped fixtures
tests/conftest.py already builds for the batch-path tests - this sandbox
has real access to those four tools, just not to AWS, so there's no
reason to stub any of them out here."""
from __future__ import annotations
import os

import qa_tools.bdm.build_per_run_warehouses as build_per_run_warehouses
import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
import qa_tools.bdm.run_datacontract_bdm as run_datacontract_bdm
import qa_tools.bdm.run_dbt_bdm as run_dbt_bdm
import qa_tools.bdm.run_evidently_bdm as run_evidently_bdm
import qa_tools.bdm.run_soda_bdm as run_soda_bdm
import qa_tools.cp.orchestrate_cp as orchestrate_cp

_REF_RUN_ID = "pytest_bdm_ref"
_DIRTY_RUN_ID = "pytest_bdm_dirty"
_CP_REF_RUN_ID = "pytest_cp_ref"
_CP_DIRTY_RUN_ID = "pytest_cp_dirty"


def _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir):
    # run_single() copies the arrived file into build_per_run_warehouses.
    # RAW_DIR itself (see that function's own docstring on why) - in real
    # production this is the same literal path run_datacontract_bdm.py/
    # run_evidently_bdm.py already default to, so all three must point at
    # the SAME tmp dir here for the same reason.
    monkeypatch.setattr(build_per_run_warehouses, "RAW_DIR", raw_dir)
    monkeypatch.setattr(build_per_run_warehouses, "OUT_DIR", duckdb_dir)
    monkeypatch.setattr(run_datacontract_bdm, "RAW_DIR", raw_dir)
    monkeypatch.setattr(run_evidently_bdm, "RAW_DIR", raw_dir)
    monkeypatch.setattr(run_dbt_bdm, "DUCKDB_RUNS_DIR", duckdb_dir)
    monkeypatch.setattr(run_soda_bdm, "DUCKDB_RUNS_DIR", duckdb_dir)
    monkeypatch.setattr(run_datacontract_bdm, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(run_dbt_bdm, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(run_soda_bdm, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(run_evidently_bdm, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(orchestrate_bdm, "write_qa_result", lambda *a, **k: None)


def test_run_single_bdm_produces_real_results_without_touching_the_manifest(monkeypatch, tmp_path, bdm_raw_dir):
    """No manifest.json is read anywhere in this call chain - run_single()
    is fed only the arrived file's own path/metadata, exactly the shape a
    Lambda handler would have from one S3 event, with no batch context at
    all."""
    raw_dir = str(tmp_path / "raw")
    duckdb_dir = str(tmp_path / "duckdb_runs")
    os.makedirs(raw_dir)
    _patch_bdm_dirs(monkeypatch, raw_dir, duckdb_dir)

    # The dirty run's real CSV, copied out of the batch fixture's own raw
    # dir to prove run_single() doesn't depend on it already being in
    # RAW_DIR under its final name - exactly the "arrived somewhere else"
    # shape a Lambda's /tmp download would have.
    arrived_csv = tmp_path / "incoming.csv"
    with open(os.path.join(bdm_raw_dir, f"{_DIRTY_RUN_ID}.csv"), "rb") as src, open(arrived_csv, "wb") as dst:
        dst.write(src.read())

    # The reference run must already be resolvable under RAW_DIR (this
    # test's own stand-in for "already present" - see the design doc's
    # own open question on where this lives in real production) - copy
    # the fixture's clean reference CSV in under its own name first.
    with open(os.path.join(bdm_raw_dir, f"{_REF_RUN_ID}.csv"), "rb") as src:
        with open(os.path.join(raw_dir, f"{_REF_RUN_ID}.csv"), "wb") as dst:
            dst.write(src.read())
    build_per_run_warehouses.build_one(_REF_RUN_ID, os.path.join(raw_dir, f"{_REF_RUN_ID}.csv"), "2026-01-01", None,
                                        out_dir=duckdb_dir)

    results = orchestrate_bdm.run_single(
        _DIRTY_RUN_ID, str(arrived_csv), "2026-01-02", "red",
        reference_run_id=_REF_RUN_ID, reference_csv=f"{_REF_RUN_ID}.csv", run_by="test@example.com")

    assert results, "run_single() produced no real check results at all"
    assert all(r["run_id"] == _DIRTY_RUN_ID for r in results)
    assert all(r["check_id"] for r in results)
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "the real red-severity dirty run produced no failures via run_single()"
    # The arrived file really landed at RAW_DIR/<run_id>.csv, not wherever
    # it was originally downloaded to.
    assert os.path.exists(os.path.join(raw_dir, f"{_DIRTY_RUN_ID}.csv"))


def test_run_single_cp_produces_real_cross_table_results_once_all_6_tables_present(
        monkeypatch, tmp_path, cp_raw_dir, cp_duckdb_dir):
    """CP's own single-delivery entry point - assumes (as documented in
    orchestrate_cp.run_single()'s own docstring) that all 6 tables have
    already landed via 6 real add_table_to_run() calls before this is
    ever invoked, exactly what a CP ingest Lambda would have done by the
    time its own completion_tracker says the delivery is complete."""
    import qa_tools.cp.run_datacontract_cp as run_datacontract_cp
    import qa_tools.cp.run_dbt_cp as run_dbt_cp
    import qa_tools.cp.run_evidently_cp as run_evidently_cp
    import qa_tools.cp.run_soda_cp as run_soda_cp

    monkeypatch.setattr(run_dbt_cp, "CP_DUCKDB_RUNS_DIR", cp_duckdb_dir)
    monkeypatch.setattr(run_soda_cp, "CP_DUCKDB_RUNS_DIR", cp_duckdb_dir)
    monkeypatch.setattr(run_datacontract_cp, "CP_RAW_DIR", cp_raw_dir)
    monkeypatch.setattr(run_evidently_cp, "CP_RAW_DIR", cp_raw_dir)
    for mod in (run_dbt_cp, run_soda_cp, run_datacontract_cp, run_evidently_cp):
        monkeypatch.setattr(mod, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(orchestrate_cp, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(orchestrate_cp, "CP_DUCKDB_RUNS_DIR", cp_duckdb_dir)

    entry = {"run_id": _CP_DIRTY_RUN_ID, "received_at": "2026-04-01T09:00:00+08:00",
             "dirty_severity": "red"}
    results = orchestrate_cp.run_single(entry, reference_run_id=_CP_REF_RUN_ID, run_by="test@example.com")

    assert results, "run_single() produced no real CP check results at all"
    assert all(r["check_id"] for r in results)
    tables_seen = {r["dataset_id"] for r in results}
    assert len(tables_seen) > 1, "results should span more than one of the 6 real CP tables"
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "the real red-severity dirty CP delivery produced no failures via run_single()"
