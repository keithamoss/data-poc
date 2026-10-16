"""Civil Registration's adapter (REQ-PIPE-240). Every pointer below is
temporary and names its remover in qa_tools/collections/base.py."""
from qa_tools.collections.base import CollectionAdapter, DatacontractSpec, DbtSpec, SodaSpec

ADAPTER = CollectionAdapter(
    collection_id="civil-registration",
    label="Birth Registrations",
    orchestrator="qa_tools.bdm.orchestrate_bdm",
    run_pipeline_function="run_pipeline",
    warehouse_builder="qa_tools.bdm.build_per_run_warehouses",
    warehouse_tables="TABLE",
    results_rebuild="qa_tools.bdm.build_results_from_history",
    generator="cli.bdm:generate_synthetic_data",
    target_datasets=("birth-registrations",),
    dashboard_json="birth_registrations_dashboard.json",
    # One dataset, written as the document itself.
    dashboard_datasets=lambda doc: [doc],
    datacontract=DatacontractSpec(
        # Each the same real-world check as a dbt (and, for the sibling
        # check, Soda) counterpart; the label is what shows the overlap.
        labels_by_check_tail={
            "sibling_match_datacontract": "Sibling record match",
            "timestamp_ordering_datacontract": "Timestamp ordering",
            "freshness_datacontract": "Freshness",
        },
    ),
    sample_key={"birth_registrations": "registration_number"},
    dbt=DbtSpec(
        singular_home={"multiple_birth_sibling": "birth_registrations",
                       "recency": "birth_registrations"},
        singular_column={"multiple_birth_sibling": "is_multiple_birth", "recency": "date_of_birth"},
        # recency is a NOT EXISTS check: its audit table holds one synthetic
        # row and no registration number to sample.
        singular_unsampled=frozenset({"recency"}),
        model_level_column={"expression_is_true": "date_registered"},
        dimension_by_test={
            "unique": "uniqueness", "not_null": "completeness", "accepted_values": "conformity",
            "matches_regex": "conformity", "multiple_birth_sibling": "consistency",
            "accepted_range": "conformity", "expression_is_true": "consistency",
            "recency": "timeliness",
        },
        label_by_test={
            "unique": "Duplicate rate", "not_null": "Null rate", "accepted_values": "Invalid values",
            "matches_regex": "Invalid values", "multiple_birth_sibling": "Sibling record match",
            "accepted_range": "Date-of-birth range",
            "expression_is_true": "Registration/birth date ordering", "recency": "Freshness",
        },
    ),
    soda=SodaSpec(
        data_source="birth_registrations",
        # A `failed rows` check has no column of its own; each is routed to
        # the column it is about, so it lands on a real column tile rather
        # than "(table)", which this collection's dashboard drops.
        column_by_name={
            "extract timestamp is logically ordered after date_registered": "extract_timestamp",
            "multiple birth records have a matching sibling": "is_multiple_birth",
            "recent birth dates present (freshness)": "date_of_birth",
            "date_of_birth is within a plausible range": "date_of_birth",
            "date_registered is not earlier than date_of_birth": "date_registered",
        },
        # Shared with the same rule's dbt / datacontract-cli check, so the
        # dashboard makes the overlap obvious.
        label_by_name={
            "extract timestamp is logically ordered after date_registered": "Timestamp ordering",
            "multiple birth records have a matching sibling": "Sibling record match",
            "recent birth dates present (freshness)": "Freshness",
            "date_of_birth is within a plausible range": "Date-of-birth range",
            "date_registered is not earlier than date_of_birth": "Registration/birth date ordering",
        },
        dimension_by_name={
            "sex validity, last 24h only": "conformity",
            "extract timestamp is logically ordered after date_registered": "consistency",
            "multiple birth records have a matching sibling": "consistency",
            "recent birth dates present (freshness)": "timeliness",
            "date_of_birth is within a plausible range": "conformity",
            "date_registered is not earlier than date_of_birth": "consistency",
        },
        name_dimension_default=None,
        # Explicit per metric, never a substring guess at the check's name
        # (plans/qa-pipeline.md #10).
        dimension_by_metric={
            "missing_count": "completeness", "missing_percent": "completeness",
            "invalid_percent": "conformity", "duplicate_count": "uniqueness",
            "row_count": "completeness",
        },
        invalid_count_metrics=frozenset({"missing_count"}),
    ),
    legacy=frozenset({
        "datacontract.reads_unreadable_tables",
        "soda.reads_unreadable_tables",
        "soda.scope_suffix",
        "soda.named_check_value_is_invalid_count",
        "evidently.reads_unreadable_tables",
        "evidently.volume_from_drift_frame",
        "dbt.no_built_model_guard",
        "dbt.audits_skipped_tests",
        "dbt.no_left_out_note",
    }),
)
