"""Tests for qa_tools/{bdm,cp}/build_results_from_history.py - the
CI-safe "rebuild reports/*.json from committed qa_results/ history, no
real tool re-run, no live data access" path (plans/publishing-and-
history.md Phase 2/3). Runs against the REAL committed qa_results/
history already in this repo (not a hand-crafted fixture) - exactly
what CI itself reads, and exactly the "must never touch data/" rule
this module exists to satisfy, so there's nothing to fake here."""
from __future__ import annotations

import qa_tools.bdm.build_results_from_history as bdm_history
import qa_tools.cp.build_results_from_history as cp_history


def test_bdm_rebuilds_from_real_committed_history(tmp_path, monkeypatch, deployment_history):
    results_path = tmp_path / "results_bdm.json"
    monkeypatch.setattr(bdm_history, "RESULTS_PATH", str(results_path))

    output = bdm_history.build_results_from_history()

    assert results_path.exists(), "should write reports/results_bdm.json (redirected to tmp here)"
    assert output["runs"], "the real committed qa_results/registry-services/civil-registration/ history is empty"
    assert output["results"], "no real check results found across committed history"
    # run_index, not run_date - a resupply's own run_date sorts away from its parent delivery (see module docstring)
    run_indexes = [r["run_index"] for r in output["runs"]]
    assert run_indexes == sorted(run_indexes)

    summary = output["summary"]
    assert summary["total_checks"] == len(output["results"])
    # EVERY VERDICT IS COUNTED, and this line is the one that found the
    # gap. REQ-QAC-108 added a fifth - `nodata`, a drift or volume check
    # with no reference period - and the summary went on counting four,
    # so the parts stopped adding up to the whole. Nothing else noticed:
    # the dashboard reads `results`, not `summary`.
    counted = sum(summary[k] for k in ("pass", "warn", "fail", "error", "nodata"))
    assert counted == summary["total_checks"], (
        f"{summary['total_checks'] - counted} result(s) carry a verdict the "
        f"summary does not count: "
        f"{sorted({r['status'] for r in output['results']})}")
    assert summary["engines"] == sorted(summary["engines"])
    assert summary["engines"], "no real engine names found in committed history"

    # every run's own dataset_stats got carried through keyed by run_id
    assert set(output["dataset_stats"]) == {r["run_id"] for r in output["runs"]}


def test_cp_rebuilds_from_real_committed_history(tmp_path, monkeypatch, deployment_history):
    results_path = tmp_path / "results_cp.json"
    monkeypatch.setattr(cp_history, "RESULTS_PATH", str(results_path))

    output = cp_history.build_results_from_history()

    assert results_path.exists()
    assert output["runs"], "the real committed qa_results/child-protection-family-support/child-protection/ history is empty"
    assert output["results"]
    run_indexes = [r["run_index"] for r in output["runs"]]
    assert run_indexes == sorted(run_indexes)

    summary = output["summary"]
    assert summary["total_checks"] == len(output["results"])
    # EVERY VERDICT IS COUNTED, and this line is the one that found the
    # gap. REQ-QAC-108 added a fifth - `nodata`, a drift or volume check
    # with no reference period - and the summary went on counting four,
    # so the parts stopped adding up to the whole. Nothing else noticed:
    # the dashboard reads `results`, not `summary`.
    counted = sum(summary[k] for k in ("pass", "warn", "fail", "error", "nodata"))
    assert counted == summary["total_checks"], (
        f"{summary['total_checks'] - counted} result(s) carry a verdict the "
        f"summary does not count: "
        f"{sorted({r['status'] for r in output['results']})}")

    # results span more than one of the 6 real CP tables - not silently
    # collapsed onto just one dataset_id by the interleaved-per-run read
    tables_seen = {r["dataset_id"] for r in output["results"]}
    assert len(tables_seen) > 1
    assert set(output["dataset_stats"]) == {r["run_id"] for r in output["runs"]}
