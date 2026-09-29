"""
Check-lifecycle metadata for run_evidently_cp.py's checks
(plans/publishing-and-history.md Thread D, Phase 1). A separate, tiny
module rather than living inside run_evidently_cp.py itself - see
qa_tools/bdm/evidently_check_lifecycle.py's own docstring for why
(Evidently's checks have no YAML definition of their own to carry
metadata the way dbt/Soda/the contract do).

Writing the reader-facing prose (description/failure_indicates/
technical_note): docs/check-authoring-rules.md is the standing
authoring standard - read it before adding or editing any of the
three. The lifecycle gate only checks that failure_indicates is
present; nothing enforces the wording rules.
"""
from __future__ import annotations

# A named constant, not just a dict key - imported directly by
# run_evidently_cp.py to tag its real check result with its own
# check_id (2026-09-16, Phase 4 prerequisite) - see
# qa_tools/bdm/evidently_check_lifecycle.py's identical comment.
PSI_CHECK_ID = (
    "data-asset-1.child-protection-family-support.child-protection."
    "cp-notifications.concern_type.drift_psi_evidently")

#: One relative volume check per Child Protection dataset (REQ-QAC-108
#: criterion 1). SIX RATHER THAN ONE, because the question is about a
#: TABLE - Birth Registrations has one table and so needed one check,
#: and a collection-wide row count would tell a reader that something
#: shrank without saying what.
#:
#: WRITTEN OUT RATHER THAN DERIVED FROM THE HIERARCHY, which is how the
#: first version did it and why that was wrong: the lifecycle validator
#: EXEC'S this file's source, including at an older git ref, so a
#: hierarchy lookup here runs against whatever tree happens to be
#: configured at the time - and several tests install a minimal one, in
#: which "child-protection" is not a collection at all. A check
#: registry is configuration; it should read the same whatever the
#: process around it is doing.
#:
#: Keyed by TABLE because that is what the evaluator counts rows in;
#: the dataset id in each value is what a result is filed under, and
#: the two are checked against the hierarchy by a test rather than by
#: being derived from it here.
_PREFIX = "data-asset-1.child-protection-family-support.child-protection"
ROW_COUNT_GROWTH_CHECK_IDS = {
    "cp_clients": f"{_PREFIX}.cp-clients.row_count_growth_evidently",
    "cp_notifications": f"{_PREFIX}.cp-notifications.row_count_growth_evidently",
    "cp_investigations": f"{_PREFIX}.cp-investigations.row_count_growth_evidently",
    "cp_placements": f"{_PREFIX}.cp-placements.row_count_growth_evidently",
    "cp_carers": f"{_PREFIX}.cp-carers.row_count_growth_evidently",
    "cp_case_workers": f"{_PREFIX}.cp-case-workers.row_count_growth_evidently",
}

CHECK_LIFECYCLE = {
    PSI_CHECK_ID: {
        # See qa_tools/bdm/evidently_check_lifecycle.py's identical
        # comment - matches this check's own already-existing
        # "dimension": "consistency" in run_evidently_cp.py.
        "category": "consistency",
        "introduced_date": "2023-01-15",
        "description": "The spread of values must stay close to the reference supply.",
        "failure_indicates": "self-evident",
        "changelog": [],
    },
    **{
        check_id: {
            # The same category Birth Registrations' own volume check
            # carries, and for the same reading: a supply arriving much
            # smaller than the last one is a question about the refresh
            # rather than about any column's content.
            "category": "timeliness",
            # THE DAY IT WAS AUTHORED, not the day the collection
            # started. A check cannot have found anything before it
            # existed, and back-dating one would put verdicts in its
            # history that nothing ever computed.
            "introduced_date": "2026-09-29",
            "description": "The number of rows must not drop sharply against the last promoted supply.",
            "failure_indicates": "self-evident",
            "changelog": [],
        }
        for check_id in ROW_COUNT_GROWTH_CHECK_IDS.values()
    },
}
