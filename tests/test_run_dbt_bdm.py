"""Real dbt-core integration test for qa_tools/bdm/run_dbt_bdm.py's
evaluate_dbt_bdm() - the actual "parse dbt's real manifest.json/
run_results.json into our check-result shape, and re-verify counts via
the audit-table workaround for the real dbt-core#11312 bug" logic, not
previously exercised under pytest at all (see tests/conftest.py's own
docstring). Runs the REAL `dbt build` CLI (via dbt_common.run_dbt())
against a small, real, session-scoped BDM fixture - genuinely slow
relative to this repo's other tests (dbt-core's own fixed per-
invocation startup cost - see plans/performance.md), a deliberate
trade for real confidence in this specific logic."""
from __future__ import annotations

import pytest

import qa_tools.bdm.run_dbt_bdm as run_dbt_bdm

# Must match conftest.py's own _REF_RUN_ID/_DIRTY_RUN_ID exactly - those
# are the literal names bdm_duckdb_dir's fixture builds the real per-run
# DuckDB files under, and evaluate_dbt_bdm() looks up db_path purely from
# this run_id, so the two can never drift apart. (Real parallel-test
# safety for dbt's own target-path output lives in evaluate_dbt_bdm()
# itself now - see that function's own comment, plans/running-thoughts.md
# #12 - not here.)
_REF_RUN_ID = "pytest_bdm_ref"
_DIRTY_RUN_ID = "pytest_bdm_dirty"


@pytest.fixture
def _dbt_bdm(monkeypatch, bdm_duckdb_dir):
    # dbt's own target_path now lives under DUCKDB_RUNS_DIR itself (see
    # evaluate_dbt_bdm()'s own comment) - a per-worker pytest tmp dir, not
    # a real repo-relative location, so no manual cleanup is needed here
    # any more (pytest's own tmp dir retention handles it, same as every
    # other tmp_path_factory-based fixture in this suite).
    monkeypatch.setattr(run_dbt_bdm, "DUCKDB_RUNS_DIR", bdm_duckdb_dir)
    captured = {}
    monkeypatch.setattr(run_dbt_bdm, "write_qa_result",
                         lambda *a, **k: captured.setdefault("write_qa_result_called", True))
    return captured


def test_clean_run_resolves_every_check_id_and_mostly_passes(_dbt_bdm):
    results = run_dbt_bdm.evaluate_dbt_bdm(_REF_RUN_ID, "2026-01-01T06:30:00Z")

    assert results, "the real dbt build produced no test results at all"
    assert all(r["check_id"] for r in results), "every result must resolve a real check_id (evaluate_dbt_bdm raises if not)"
    assert all(r["run_id"] == _REF_RUN_ID for r in results)
    assert all(r["engine"] == run_dbt_bdm.ENGINE_TAG for r in results)
    assert all(r["status"] in ("pass", "warn", "fail") for r in results)
    # A clean, undirtied 60-row batch should have no genuine failures -
    # real assertion on real dbt output, not a fixture stand-in.
    failing = [r for r in results if r["status"] == "fail"]
    assert not failing, f"clean reference run had real dbt failures: {failing}"
    assert _dbt_bdm["write_qa_result_called"]


def test_dirty_run_produces_a_real_failure_and_correct_row_counts(_dbt_bdm):
    results = run_dbt_bdm.evaluate_dbt_bdm(_DIRTY_RUN_ID, "2026-01-02T06:30:00Z")

    assert results
    assert all(r["check_id"] for r in results)
    # generator.dirty.apply_birth_registrations_presets(severity="red")
    # is calibrated to land in this project's own real fail band - a
    # red-severity run with zero real "fail" statuses would mean either
    # the injector or this parsing logic has genuinely regressed.
    failing = [r for r in results if r["status"] == "fail"]
    assert failing, "a real red-severity dirty run produced no dbt failures at all"
    # row_count_total comes from a real live query against the per-run
    # warehouse (`SELECT COUNT(*) FROM stg_birth_registrations`) - the
    # dirty fixture started at 20 rows; some injectors may add/remove a
    # few, but it must stay in the right ballpark, not silently read the
    # reference run's row count or zero.
    assert all(10 <= r["row_count_total"] <= 30 for r in results)


def test_audit_table_correction_overrides_run_results_failures_field(_dbt_bdm):
    """The specific, highest-risk logic this module exists to protect
    against (plans/qa-pipeline.md #34, dbt-labs/dbt-core#11312 - a real,
    filed dbt-core bug: `failures` is hardcoded to 0 whenever a test's
    final status lands on Pass). Every check this module's own
    _AUDIT_AGGREGATE_SQL covers must report a metric_value that's a real
    non-negative integer, never None/negative - the shape the audit-
    table re-derivation is meant to guarantee regardless of what dbt's
    own (sometimes-wrong) run_results.json said."""
    results = run_dbt_bdm.evaluate_dbt_bdm(_REF_RUN_ID, "2026-01-01T06:30:00Z")
    covered = [r for r in results if r["check_name"].removeprefix("dbt:") in run_dbt_bdm._AUDIT_AGGREGATE_SQL]
    assert covered, "no results matched any _AUDIT_AGGREGATE_SQL-covered test - fixture/test drifted from real schema.yml"
    assert all(isinstance(r["metric_value"], int) and r["metric_value"] >= 0 for r in covered)
