"""The Cancer collection's adapter (REQ-QAC-348): one table, nothing of its
own but what its checks need to be read - Emergency Department's pattern."""
from qa_tools.collections.base import CollectionAdapter, DbtSpec, SodaSpec, StatsSpec

ADAPTER = CollectionAdapter(
    collection_id="cancer",
    label="Cancer",
    sample_key={"cancer_notifications": ["notification_id"]},
    dbt=DbtSpec(
        dimension_by_test={"not_null": "completeness", "accepted_values": "conformity",
                           "notified_before_diagnosed": "consistency"},
        label_by_test={"not_null": "Null rate", "accepted_values": "Invalid values"},
        singular_home={"notified_before_diagnosed": "cancer_notifications"},
    ),
    soda=SodaSpec(data_source="cancer_collection"),
    # Evidently's drift references are rebuilt from these recorded counts;
    # each column's allowed values are its contract's, read at run time
    # (REQ-QAC-389).
    stats=StatsSpec(value_counts=(("cancer_notifications", "primary_site"),
                                  ("cancer_notifications", "stage"))),
    claim_window_dataset="cancer-notifications",
)
