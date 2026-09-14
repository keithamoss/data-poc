"""
Tool-generic Evidently PSI-drift computation, shared by
qa_tools/bdm/run_evidently_bdm.py and
qa_tools/cp/run_evidently_cp.py. The actual reference run,
comparison column, and any dataset-specific extra checks (e.g. birth
registrations' row-count-growth check, which Child Protection doesn't
have) stay in each dataset's own file - see plans/wider.md #20.
"""
from __future__ import annotations

ENGINE_TAG = "Evidently 0.7"

# same pass/warn/fail bands both existing datasets use, applied to the
# real PSI value Evidently computes - Evidently's own DataDriftPreset only
# carries one drift/no-drift threshold (0.1) by default, not a three-way
# band, so the warn/fail split here is this project's convention, not
# Evidently's.
WARN_THRESHOLD = 0.10
FAIL_THRESHOLD = 0.25


def status_for_psi(psi: float, is_reference: bool) -> str:
    if is_reference:
        return "pass"
    if psi > FAIL_THRESHOLD:
        return "fail"
    if psi > WARN_THRESHOLD:
        return "warn"
    return "pass"


def compute_psi(current_df, reference_df, column: str) -> float | None:
    from evidently import Report
    from evidently.presets import DataDriftPreset

    report = Report(metrics=[DataDriftPreset(columns=[column], cat_method="psi")])
    snapshot = report.run(current_df, reference_df)
    result = snapshot.dict()
    for m in result["metrics"]:
        if m["metric_name"].startswith(f"ValueDrift(column={column}"):
            return m["value"]
    return None
