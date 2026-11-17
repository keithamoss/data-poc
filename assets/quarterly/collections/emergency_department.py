"""Emergency Department's adapter (REQ-PIPE-233): one table, nothing of its
own but what its checks need to be read."""
from qa_tools.collections.base import CollectionAdapter, DbtSpec, SodaSpec, StatsSpec

ADAPTER = CollectionAdapter(
    collection_id="emergency-department",
    label="Emergency Department",
    sample_key={"ed_presentations": ["presentation_id"]},
    dbt=DbtSpec(
        dimension_by_test={"not_null": "completeness", "accepted_values": "conformity",
                           "accepted_range": "conformity"},
        label_by_test={"not_null": "Null rate", "accepted_values": "Invalid values",
                       "accepted_range": "Length of stay range"},
    ),
    soda=SodaSpec(data_source="ed_collection"),
    # Evidently's drift references are rebuilt from these recorded counts;
    # each column's allowed values are its contract's, read at run time
    # (REQ-QAC-389).
    stats=StatsSpec(value_counts=(("ed_presentations", "triage_category"),
                                  ("ed_presentations", "age_group"))),
    claim_window_dataset="ed-presentations",
)
