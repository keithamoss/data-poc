"""The Mental Health collection's adapter (REQ-QAC-350): one table, nothing of
its own but what its checks need to be read - Emergency Department's pattern."""
from qa_tools.collections.base import CollectionAdapter, DbtSpec, SodaSpec, StatsSpec

ADAPTER = CollectionAdapter(
    collection_id="mental-health",
    label="Mental Health",
    sample_key={"mental_health_contacts": ["contact_id"]},
    dbt=DbtSpec(
        dimension_by_test={"not_null": "completeness", "accepted_values": "conformity",
                           "contact_in_its_week": "consistency"},
        label_by_test={"not_null": "Null rate", "accepted_values": "Invalid values"},
        singular_home={"contact_in_its_week": "mental_health_contacts"},
    ),
    soda=SodaSpec(data_source="mh_collection"),
    # Evidently's drift references are rebuilt from these recorded counts;
    # each column's allowed values are its contract's, read at run time
    # (REQ-QAC-389).
    stats=StatsSpec(value_counts=(("mental_health_contacts", "service_type"),
                                  ("mental_health_contacts", "referral_source"))),
    claim_window_dataset="mental-health-contacts",
)
