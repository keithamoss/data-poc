"""
Child Protection's own place in the hierarchy, resolved rather than
restated (REQ-QAC-039), plus the genuinely CP-specific lookups the four
real-tool scripts share (run_dbt_cp.py, run_soda_cp.py,
run_datacontract_cp.py, run_evidently_cp.py, orchestrate_cp.py, and
pipeline/build_cp_dashboard_data.py).

WHAT CHANGED, 2026-09-23. The agency/collection ids and names, the list
of tables, and the hand-maintained table -> dataset id/name maps all
used to be literals here - a second statement of the tree that nothing
held to the first. They now come from `qa_tools/common/hierarchy.py`,
which reads `contract/data-asset.yaml`. The one literal left is
COLLECTION_ID: these scripts have to say WHICH collection they are for,
and naming it is a reference, not a restatement.

Unlike Birth Registrations (one table -> one dataset), Child Protection
is 6 tables -> 6 sibling datasets under one collection, so dataset_id
varies per check result rather than being one constant - call
`hierarchy.dataset_for_table(table)` for it.
"""
from __future__ import annotations

from qa_tools.common import hierarchy

# The one thing these scripts genuinely declare: which collection they
# are for. Everything else below is looked up from it.
COLLECTION_ID = "child-protection"

_DATASETS = hierarchy.datasets_in_collection(COLLECTION_ID)

AGENCY_ID = _DATASETS[0].agency_id
AGENCY_NAME = _DATASETS[0].agency_name
COLLECTION_NAME = _DATASETS[0].collection_name

# Declaration order in contract/data-asset.yaml, which is the order the
# real tool scripts have always iterated these tables in.
TABLES = [d.table for d in _DATASETS]

# each table's primary key column (all `unique: true` in
# contract/child-protection-contract.yaml) - used to pull just the
# identifier out of a failing-row sample, never full row content, per
# plans/qa-pipeline.md #15's "flag it, not full row content" line.
TABLE_PK = {
    "cp_clients": "cp_client_id",
    "cp_notifications": "notification_id",
    "cp_investigations": "investigation_id",
    "cp_placements": "placement_id",
    "cp_carers": "carer_id",
    "cp_case_workers": "worker_id",
}

# where each of the 3 cross-table business-rule singular tests / SQL rules
# "lives" for dashboard purposes - matches the table their quality: block
# sits under in contract/child-protection-contract.yaml (the child table in
# each rule's join, not the parent), and the table dbt's singular tests are
# associated with for the same reason (see dbt_project/tests/*.sql).
BUSINESS_RULE_HOME_TABLE = {
    "escalation_completeness": "cp_notifications",
    "closed_case_investigation_hygiene": "cp_investigations",
    "placement_carer_approval": "cp_placements",
    # cp_client_date_of_birth_range (a genuine single-table/single-column
    # singular test, never a cross-table business rule like the 3 above)
    # retired 2026-09-15, replaced by dbt_utils.accepted_range - see
    # plans/qa-pipeline.md's dbt_utils switch. The 3 real business rules
    # stay singular tests: no generic test, dbt_utils/dbt-expectations
    # included, abstracts away an arbitrary cross-table join condition.
}

BUSINESS_RULE_DISPLAY_NAME = {
    "escalation_completeness": "Escalation completeness",
    "closed_case_investigation_hygiene": "Closed-case investigation hygiene",
    "placement_carer_approval": "Placement/carer approval compliance",
}
