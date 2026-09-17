"""
Check-lifecycle metadata for run_evidently_cp.py's checks
(plans/publishing-and-history.md Thread D, Phase 1). A separate, tiny
module rather than living inside run_evidently_cp.py itself - see
qa_tools/bdm/evidently_check_lifecycle.py's own docstring for why
(Evidently's checks have no YAML definition of their own to carry
metadata the way dbt/Soda/the contract do).
"""
from __future__ import annotations

# A named constant, not just a dict key - imported directly by
# run_evidently_cp.py to tag its real check result with its own
# check_id (2026-09-16, Phase 4 prerequisite) - see
# qa_tools/bdm/evidently_check_lifecycle.py's identical comment.
PSI_CHECK_ID = (
    "data-asset-1.child-protection-family-support.cp-notifications."
    "stg_cp_notifications.concern_type.drift_psi_evidently")

CHECK_LIFECYCLE = {
    PSI_CHECK_ID: {
        "introduced_date": "2023-01-15",
        "description": "Population Stability Index on concern_type's value distribution vs. the reference run - this collection's own traffic-light demo column.",
        "changelog": [],
    },
}
