"""Emergency Department's adapter (REQ-PIPE-233): one table, nothing of its
own but what its checks need to be read."""
from qa_tools.collections.base import CollectionAdapter, DbtSpec, SodaSpec, StatsSpec

AGE_GROUPS = ["0-4", "5-14", "15-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75-84", "85+"]
TRIAGE_CATEGORIES = [1, 2, 3, 4, 5]

ADAPTER = CollectionAdapter(
    collection_id="emergency-department",
    label="Emergency Department",
    sample_key={"ed_presentations": "presentation_id"},
    dbt=DbtSpec(
        dimension_by_test={"not_null": "completeness", "accepted_values": "conformity",
                           "accepted_range": "conformity"},
        label_by_test={"not_null": "Null rate", "accepted_values": "Invalid values",
                       "accepted_range": "Length of stay range"},
    ),
    soda=SodaSpec(data_source="ed_collection"),
    # Evidently's drift references are rebuilt from these recorded counts.
    stats=StatsSpec(value_counts={("ed_presentations", "triage_category"): TRIAGE_CATEGORIES,
                                  ("ed_presentations", "age_group"): AGE_GROUPS}),
    claim_window_dataset="ed-presentations",
)
