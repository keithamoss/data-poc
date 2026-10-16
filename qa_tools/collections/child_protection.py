"""Child Protection's adapter (REQ-PIPE-240). Every pointer below is
temporary and names its remover in qa_tools/collections/base.py."""
from qa_tools.collections.base import CollectionAdapter, DatacontractSpec

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

ADAPTER = CollectionAdapter(
    collection_id="child-protection",
    label="Child Protection",
    orchestrator="qa_tools.cp.orchestrate_cp",
    run_pipeline_function="run_pipeline_cp",
    warehouse_builder="qa_tools.cp.build_cp_warehouses",
    warehouse_tables="TABLES",
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
        sample_key=TABLE_PK,
    ),
)
