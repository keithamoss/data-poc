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

ADAPTER = CollectionAdapter(
    collection_id="child-protection",
    label="Child Protection",
    # Its datasets, listed under `datasets` in the file's own order.
    datacontract=DatacontractSpec(
        # Only a `relationships_*` rule is an FK check, decided from the
        # check id's tail. Asking it the other way round ("not a business
        # rule, so an FK check") once grouped a date-range rule with
        # referential integrity.
        labels_by_check_tail={"relationships_datacontract": "Referential integrity"},
    ),
    sample_key={table: [pk] for table, pk in TABLE_PK.items()},
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
        invalid_count_metrics=frozenset({"reference"}),
    ),
    stats=StatsSpec(
        aggregates={
            ("cp_clients", "postcode"): {
                "kind": "categorical",
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
                "classification": None,
                "check_names": {"datacontract:invalid_count"},
            },
        },
        # Each categorical column's allowed values are its contract's, read at
        # run time (REQ-QAC-389).
        value_counts=(("cp_notifications", "concern_type"),),
    ),
    # An arrival naming no dataset of its own is claimed under Client
    # Records' window, as the copied orchestrator did.
    claim_window_dataset="cp-clients",
)
