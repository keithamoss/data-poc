"""The fake Widget Register's adapter (REQ-TEST-249) - what a new one-table
collection costs. Installed only in a copy of the repository."""
from qa_tools.collections.base import CollectionAdapter, DbtSpec, SodaSpec, StatsSpec

ADAPTER = CollectionAdapter(
    collection_id="widget-register",
    label="Widget Register",
    dashboard_datasets=lambda doc: list(doc["datasets"]),
    sample_key={"widgets": "widget_id"},
    dbt=DbtSpec(
        dimension_by_test={"unique": "uniqueness", "not_null": "completeness"},
        label_by_test={"unique": "Duplicate rate", "not_null": "Null rate"},
    ),
    soda=SodaSpec(
        data_source="widget_register",
    ),
    # Evidently's drift reference is rebuilt from these recorded counts.
    stats=StatsSpec(value_counts={("widgets", "colour"): ["red", "green", "blue"]}),
)
