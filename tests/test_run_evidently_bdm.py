"""Real Evidently AI integration test for qa_tools/bdm/
run_evidently_bdm.py's evaluate_evidently_bdm() - the actual "compute a
real PSI drift metric and a real row-count-growth comparison, then
shape them into our check-result records" logic, not previously
exercised under pytest at all (see tests/conftest.py's own docstring
and tests/test_orchestrate_reference_run.py, which monkeypatches this
exact function out for its own, narrower purpose). Runs the REAL
evidently.Report + DataDriftPreset/RowCount classes against a small,
real, session-scoped BDM CSV fixture."""
from __future__ import annotations

import qa_tools.bdm.run_evidently_bdm as run_evidently_bdm

from fixture_ids import BDM_DIRTY_RUN_ID as _DIRTY_RUN_ID, BDM_REF_RUN_ID as _REF_RUN_ID

_REF_CSV = "pytest_bdm_ref.csv"
_DIRTY_CSV = "pytest_bdm_dirty.csv"


def _patch(monkeypatch, bdm_raw_dir, bdm_delivery_dirs):
    """The row-count-growth check finds "the run before this one" from
    the arrivals RECOGNISED on disk (REQ-GEN-043), and recognition
    falls back to the real data/deliveries/ tree when nothing says
    otherwise - so a test that does not redirect it is comparing the
    fixture's dirty run against 42 real deliveries, or (more likely)
    finding no previous run at all and silently losing the check."""
    from qa_tools.common import delivery

    deliveries, receipts = bdm_delivery_dirs
    monkeypatch.setattr(delivery, "DELIVERIES_DIR", deliveries)
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", receipts)
    monkeypatch.setattr(run_evidently_bdm, "RAW_DIR", bdm_raw_dir)
    monkeypatch.setattr(run_evidently_bdm, "write_qa_result", lambda *a, **k: None)


def _run(monkeypatch, bdm_raw_dir, bdm_delivery_dirs, run_id, csv_filename, run_timestamp, **kw):
    _patch(monkeypatch, bdm_raw_dir, bdm_delivery_dirs)
    return run_evidently_bdm.evaluate_evidently_bdm(
        run_id, csv_filename, run_timestamp,
        reference_run_id=kw.get("reference_run_id", _REF_RUN_ID),
        reference_csv=kw.get("reference_csv", _REF_CSV),
    )


def test_reference_run_against_itself_has_no_psi_drift(monkeypatch, bdm_raw_dir, bdm_delivery_dirs):
    """run_id == reference_run_id is the real "first run, nothing to
    compare against yet" case status_for_psi() special-cases."""
    results = _run(monkeypatch, bdm_raw_dir, bdm_delivery_dirs, _REF_RUN_ID, _REF_CSV, "2026-01-01T06:30:00Z")

    psi = next(r for r in results if r["check_name"] == "drift:PSI")
    assert psi["status"] == "pass"
    assert psi["engine"] == run_evidently_bdm.ENGINE_TAG
    # The first arrival recognised on disk - no previous run to compare
    # row-count growth against, so only the PSI result should exist.
    assert len(results) == 1


def test_dirty_run_produces_a_real_row_count_drop_failure(monkeypatch, bdm_raw_dir, bdm_delivery_dirs):
    """The dirty fixture run is ~97% smaller than the reference run
    (tests/conftest.py) - a real, deterministic way to force
    evaluate_evidently_bdm's row-count-growth check into a genuine
    "fail" via real Evidently RowCount metrics on both files, not a
    hand-computed stand-in."""
    results = _run(monkeypatch, bdm_raw_dir, bdm_delivery_dirs, _DIRTY_RUN_ID, _DIRTY_CSV, "2026-01-02T06:30:00Z")

    assert len(results) == 2, \
        "the dirty run has a real preceding arrival on disk - row-count-growth must run"
    growth = next(r for r in results if r["check_name"] == "evidently:row_count_growth")
    assert growth["status"] == "fail"
    # metric_value is a POSITIVE percentage drop ((previous-current)/previous),
    # not a signed delta - a real >25% drop is what pushes past FAIL_ROW_DROP.
    assert growth["metric_value"] > 25.0, f"expected a real >25% drop, got {growth['metric_value']}%"
    assert growth["check_id"] == run_evidently_bdm.ROW_COUNT_GROWTH_CHECK_ID


def test_evaluate_evidently_bdm_forwards_the_given_reference_not_the_module_default(
        monkeypatch, bdm_raw_dir, bdm_delivery_dirs, tmp_path):
    """Regression coverage in the same spirit as
    tests/test_orchestrate_reference_run.py, but for the real function
    itself rather than a monkeypatched stand-in: a caller-supplied
    reference must actually be used for the real PSI computation, not
    silently fall back to REFERENCE_RUN_ID's own module-level default
    (a stale hardcoded date, plans/publishing-and-history.md's own
    account of the bug this guards against)."""
    _patch(monkeypatch, bdm_raw_dir, bdm_delivery_dirs)

    results = run_evidently_bdm.evaluate_evidently_bdm(
        _DIRTY_RUN_ID, _DIRTY_CSV, "2026-01-02T06:30:00Z",
        reference_run_id=_REF_RUN_ID, reference_csv=_REF_CSV,
    )
    psi = next(r for r in results if r["check_name"] == "drift:PSI")
    assert psi["reference_run_id"] == _REF_RUN_ID
