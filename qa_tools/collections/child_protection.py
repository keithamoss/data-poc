"""Child Protection's adapter (REQ-PIPE-240). Every pointer below is
temporary and names its remover in qa_tools/collections/base.py."""
from qa_tools.collections.base import (
    CollectionAdapter, DatacontractSpec, DbtSpec, SodaSpec, StatsSpec,
)

#: Each table's primary key (all `unique: true` in the contract) - the only
#: value a failing-row sample keeps, never full row content
#: (plans/qa-pipeline.md #15).
TABLE_PK = {
    "cp_clients": "cp_client_id",
    "cp_notifications": "notification_id",
    "cp_investigations": "investigation_id",
    "cp_placements": "placement_id",
    "cp_carers": "carer_id",
    "cp_case_workers": "worker_id",
}

#: Where each cross-table business-rule singular test "lives" for the
#: dashboard: the child table in its join, matching the table its contract
#: quality entry sits under.
BUSINESS_RULE_HOME_TABLE = {
    "escalation_completeness": "cp_notifications",
    "closed_case_investigation_hygiene": "cp_investigations",
    "placement_carer_approval": "cp_placements",
}

#: The valid values the real checks enforce, moved from
#: qa_tools/cp/dataset_stats.py (REQ-PIPE-243).
_POSTCODE_VALID = ["6007", "6008", "6014", "6018", "6019", "6027", "6028", "6030", "6035", "6036", "6050", "6056",
                    "6061", "6062", "6064", "6069", "6100", "6102", "6107", "6109", "6110", "6112", "6122", "6148",
                    "6151", "6155", "6160", "6162", "6163", "6164", "6167", "6168", "6171", "6210", "6215", "6225",
                    "6230", "6258", "6280", "6285", "6312", "6330", "6401", "6430", "6450", "6530", "6714", "6721",
                    "6725"]
_CONCERN_TYPE_VALID = ["Neglect", "Physical abuse", "Emotional abuse", "Sexual abuse",
                        "Domestic violence exposure", "Parental substance use", "Parental mental health concern"]


def _sql_list(values: list[str]) -> str:
    return ",".join("'" + v.replace("'", "''") + "'" for v in values)


ADAPTER = CollectionAdapter(
    collection_id="child-protection",
    label="Child Protection",
    orchestrator="qa_tools.cp.orchestrate_cp",
    run_pipeline_function="run_pipeline_cp",
    results_rebuild="qa_tools.cp.build_results_from_history",
    generator="cli.cp:generate_synthetic_data",
    target_datasets=("cp-clients",),
    dashboard_json="child_protection_dashboard.json",
    # Its datasets, listed under `datasets` in the file's own order.
    dashboard_datasets=lambda doc: list(doc["datasets"]),
    datacontract=DatacontractSpec(
        # Only a `relationships_*` rule is an FK check, decided from the
        # check id's tail. Asking it the other way round ("not a business
        # rule, so an FK check") once grouped a date-range rule with
        # referential integrity.
        labels_by_check_tail={"relationships_datacontract": "Referential integrity"},
    ),
    sample_key=TABLE_PK,
    dbt=DbtSpec(
        singular_home=BUSINESS_RULE_HOME_TABLE,
        dimension_by_test={
            "unique": "uniqueness", "not_null": "completeness", "accepted_values": "conformity",
            "relationships": "consistency", "escalation_completeness": "completeness",
            "closed_case_investigation_hygiene": "consistency",
            "placement_carer_approval": "consistency", "accepted_range": "conformity",
        },
        # None for the three business rules: their own names are plain, and
        # match Soda's and datacontract-cli's names for the same rule.
        label_by_test={
            "unique": "Duplicate rate", "not_null": "Null rate", "accepted_values": "Invalid values",
            "relationships": "Referential integrity", "accepted_range": "Date range",
        },
    ),
    soda=SodaSpec(
        data_source="cp_collection",
        # The three cross-table business rules stay unrouted (the table's
        # own pseudo-column): they are not about one column.
        column_by_name={
            "date_of_birth out of range": "date_of_birth",
            "end_date is not earlier than start_date": "end_date",
        },
        # Matching each rule's own contract quality entry.
        dimension_by_name={
            "Escalation completeness": "completeness",
            "Closed-case investigation hygiene": "consistency",
            "Placement/carer approval compliance": "consistency",
            "date_of_birth out of range": "conformity",
        },
        dimension_by_metric={"reference": "consistency", "row_count": "completeness"},
        invalid_count_metrics=frozenset({"reference"}),
    ),
    stats=StatsSpec(
        aggregates={
            ("cp_clients", "postcode"): {
                "kind": "categorical",
                "invalid_condition": f"postcode NOT IN ({_sql_list(_POSTCODE_VALID)}) OR postcode IS NULL",
                "classification": None,
                "check_names": {"dbt:accepted_values", "invalid_percent", "datacontract:invalid_count"},
            },
            ("cp_clients", "date_of_birth"): {
                "kind": "numeric_date",
                "invalid_condition": "date_of_birth < DATE '1900-01-01'",
                "classification": None,
                "check_names": {"dbt:cp_client_date_of_birth_range", "date_of_birth out of range"},
            },
            ("cp_notifications", "concern_type"): {
                "kind": "categorical",
                "invalid_condition": (f"concern_type NOT IN ({_sql_list(_CONCERN_TYPE_VALID)}) "
                                      f"OR concern_type IS NULL"),
                "classification": None,
                "check_names": {"datacontract:invalid_count"},
            },
        },
        value_counts={("cp_notifications", "concern_type"): _CONCERN_TYPE_VALID},
    ),
    # An arrival naming no dataset of its own is claimed under Client
    # Records' window, as the copied orchestrator did.
    claim_window_dataset="cp-clients",
)
