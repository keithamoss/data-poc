"""
Check-lifecycle metadata for run_evidently_bdm.py's checks
(plans/publishing-and-history.md Thread D, Phase 1). A separate, tiny
module rather than living inside run_evidently_bdm.py itself, so
qa_tools/common/check_lifecycle.py's parser can read this without
importing evidently/pandas just to see metadata - Evidently's checks
have no YAML definition of their own to carry a `meta:`/`attributes:`
block the way dbt/Soda/the contract do (see check_lifecycle.py's own
docstring on this asymmetry), so this plain dict is where "alongside
the check" means for this one tool.

Writing the reader-facing prose (description/failure_indicates/
technical_note): docs/check-authoring-rules.md is the standing
authoring standard - read it before adding or editing any of the
three. The lifecycle gate only checks that failure_indicates is
present; nothing enforces the wording rules.
"""
from __future__ import annotations

# Named constants, not just dict keys - imported directly by
# run_evidently_bdm.py to tag each real check result with its own
# check_id (2026-09-16, Phase 4 prerequisite), so there's exactly one
# place either string is spelled out, not a literal duplicated between
# this file and the result-construction code.
PSI_CHECK_ID = "data-asset-1.registry-services.birth-registrations.stg_birth_registrations.sex.drift_psi_evidently"
ROW_COUNT_GROWTH_CHECK_ID = (
    "data-asset-1.registry-services.birth-registrations.stg_birth_registrations.row_count_growth_evidently")

CHECK_LIFECYCLE = {
    PSI_CHECK_ID: {
        # Matches this check's own already-existing "dimension": value in
        # run_evidently_bdm.py's own result-construction code (real,
        # pre-existing, confirmed by reading that file directly, not
        # assumed) - a distribution shift between runs read as a
        # cross-run logical consistency concern, not a new category.
        "category": "consistency",
        "introduced_date": "2026-01-15",
        "description": "Population Stability Index on sex's value distribution vs. the reference run - flags a real distribution shift.",
        "changelog": [],
    },
    ROW_COUNT_GROWTH_CHECK_ID: {
        # Matches this check's own already-existing "dimension": value
        # in run_evidently_bdm.py (real, pre-existing) - a growth-over-
        # time concern read as timeliness, not completeness.
        "category": "timeliness",
        "introduced_date": "2026-01-15",
        "description": "Row count should mostly grow run over run - a real drop signals a broken/partial extract.",
        "changelog": [],
    },
}
