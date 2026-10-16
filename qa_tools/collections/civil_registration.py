"""Civil Registration's adapter (REQ-PIPE-240). Every pointer below is
temporary and names its remover in qa_tools/collections/base.py."""
from qa_tools.collections.base import CollectionAdapter, DatacontractSpec

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
        sample_key={"birth_registrations": "registration_number"},
    ),
    legacy=frozenset({
        "datacontract.reads_unreadable_tables",
    }),
)
