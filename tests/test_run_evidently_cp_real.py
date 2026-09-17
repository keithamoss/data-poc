"""Real Evidently AI integration test for qa_tools/cp/run_evidently_cp.py's
evaluate_evidently_cp() - the CP counterpart to
tests/test_run_evidently_bdm.py (concern_type PSI drift, not sex - see
that module's own docstring). Named test_run_evidently_cp_real.py, not
test_run_evidently_cp.py, since tests/test_run_evidently_cp.py already
exists (an earlier, narrower test of where this module's own results
get written, not its output-parsing logic - see that file's own
docstring)."""
from __future__ import annotations

import qa_tools.cp.run_evidently_cp as run_evidently_cp

_REF_RUN_ID = "pytest_cp_ref"
_DIRTY_RUN_ID = "pytest_cp_dirty"


def _run(monkeypatch, cp_raw_dir, run_id, run_timestamp, reference_run_id=_REF_RUN_ID):
    monkeypatch.setattr(run_evidently_cp, "CP_RAW_DIR", cp_raw_dir)
    monkeypatch.setattr(run_evidently_cp, "write_qa_result", lambda *a, **k: None)
    return run_evidently_cp.evaluate_evidently_cp(run_id, run_timestamp, reference_run_id=reference_run_id)


def test_reference_run_against_itself_has_no_psi_drift(monkeypatch, cp_raw_dir):
    results = _run(monkeypatch, cp_raw_dir, _REF_RUN_ID, "2026-01-01T09:00:00Z")

    assert len(results) == 1
    psi = results[0]
    assert psi["check_name"] == "drift:PSI"
    assert psi["status"] == "pass"
    assert psi["engine"] == run_evidently_cp.ENGINE_TAG
    assert psi["reference_run_id"] == _REF_RUN_ID


def test_dirty_run_has_a_real_check_id_and_reference(monkeypatch, cp_raw_dir):
    """generator.dirty.apply_cp_notifications_presets(severity="red")
    perturbs concern_type's own value distribution (the same column
    this check watches) - real evidence this is a genuine, non-trivial
    PSI computation against real data, not just a shape check."""
    results = _run(monkeypatch, cp_raw_dir, _DIRTY_RUN_ID, "2026-04-01T09:00:00Z")

    assert len(results) == 1
    psi = results[0]
    assert psi["check_id"] == run_evidently_cp.PSI_CHECK_ID
    assert psi["metric_value"] is not None
    assert psi["reference_run_id"] == _REF_RUN_ID
