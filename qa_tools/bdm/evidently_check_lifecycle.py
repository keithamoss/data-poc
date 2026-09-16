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
"""
from __future__ import annotations

CHECK_LIFECYCLE = {
    "data-asset-1.registry-services.birth-registrations.stg_birth_registrations.sex.drift_psi_evidently": {
        "introduced_date": "2026-01-15",
        "description": "Population Stability Index on sex's value distribution vs. the reference run - flags a real distribution shift.",
        "changelog": [],
    },
    "data-asset-1.registry-services.birth-registrations.stg_birth_registrations.row_count_growth_evidently": {
        "introduced_date": "2026-01-15",
        "description": "Row count should mostly grow run over run - a real drop signals a broken/partial extract.",
        "changelog": [],
    },
}
