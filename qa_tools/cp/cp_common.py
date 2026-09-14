"""
Shared constants for the Child Protection real-tool scripts
(run_dbt_cp.py, run_soda_cp.py, run_datacontract_cp.py,
run_evidently_cp.py, orchestrate_cp.py, and
pipeline/build_cp_dashboard_data.py) - kept in one place so the
agency/collection/dataset id scheme can't drift between the four tools'
scripts the way copy-pasting it four times would risk.

Unlike Birth Registrations (a single table -> a single dataset_id), Child
Protection is 6 tables -> 6 sibling datasets under one collection, so
dataset_id varies per check result rather than being one constant - see
TABLE_DATASET_ID/TABLE_DATASET_NAME below.
"""
from __future__ import annotations

AGENCY_ID = "child-protection-family-support"
AGENCY_NAME = "Department for Child Protection and Family Support"
COLLECTION_ID = "child-protection"
COLLECTION_NAME = "Child Protection"

TABLES = ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers", "cp_case_workers"]

TABLE_DATASET_ID = {
    "cp_clients": "cp-clients",
    "cp_notifications": "cp-notifications",
    "cp_investigations": "cp-investigations",
    "cp_placements": "cp-placements",
    "cp_carers": "cp-carers",
    "cp_case_workers": "cp-case-workers",
}

TABLE_DATASET_NAME = {
    "cp_clients": "Client Register",
    "cp_notifications": "Notifications",
    "cp_investigations": "Investigations",
    "cp_placements": "Placements",
    "cp_carers": "Carer Register",
    "cp_case_workers": "Case Workers",
}

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
    # not a cross-table business rule like the 3 above - a genuinely
    # single-table/single-column singular test (date_of_birth's range
    # check) that reuses this same "singular test, home table" mechanism
    # since it's already correct for this shape too.
    "cp_client_date_of_birth_range": "cp_clients",
}

BUSINESS_RULE_DISPLAY_NAME = {
    "escalation_completeness": "Escalation completeness",
    "closed_case_investigation_hygiene": "Closed-case investigation hygiene",
    "placement_carer_approval": "Placement/carer approval compliance",
}
