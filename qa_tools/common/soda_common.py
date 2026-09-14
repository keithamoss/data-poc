"""
Tool-generic Soda Core helpers, shared by qa_tools/bdm/run_soda_bdm.py
and qa_tools/cp/run_soda_cp.py. The actual check-to-dashboard-field
mapping (dimension/label per check, custom-name handling) is genuinely
different per dataset and stays in each dataset's own file - see
plans/wider.md #20.
"""
from __future__ import annotations

ENGINE_TAG = "Soda Core 3.5"


def threshold(spec: dict | None) -> float | None:
    if not spec:
        return None
    for key in ("greaterThan", "greaterThanOrEqual"):
        if key in spec:
            return spec[key]
    # a lower-bound-only spec (row_count's warn/fail also carry a lessThan
    # side) - "upper bound wins for a single scalar" convention, same one
    # the now-removed equivalent engine's _numeric_threshold() used.
    return next(iter(spec.values()), None)
