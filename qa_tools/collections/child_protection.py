"""Child Protection's adapter (REQ-PIPE-240). Every pointer below is
temporary and names its remover in qa_tools/collections/base.py."""
from qa_tools.collections.base import CollectionAdapter

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
)
