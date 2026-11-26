"""Civil Registration's adapter (REQ-PIPE-240). Every pointer below is
temporary and names its remover in qa_tools/collections/base.py."""
from qa_tools.collections.base import (
    CollectionAdapter, DatacontractSpec, DbtSpec, SodaSpec, StatsSpec,
)

ADAPTER = CollectionAdapter(
    collection_id="civil-registration",
    label="Birth Registrations",
    # One dataset, written as the document itself.
    datacontract=DatacontractSpec(
        # Each the same real-world check as a dbt (and, for the sibling
        # check, Soda) counterpart; the label is what shows the overlap.
        labels_by_check_tail={
            "sibling_match_datacontract": "Sibling record match",
            "timestamp_ordering_datacontract": "Timestamp ordering",
            "freshness_datacontract": "Freshness",
        },
    ),
    sample_key={"birth_registrations": ["registration_number"]},
    dbt=DbtSpec(
        singular_home={"multiple_birth_sibling": "birth_registrations",
                       "recency": "birth_registrations"},
        singular_column={"multiple_birth_sibling": "is_multiple_birth", "recency": "date_of_birth"},
        # recency is a NOT EXISTS check: its audit table holds one synthetic
        # row and no registration number to sample.
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
        invalid_count_metrics=frozenset({"missing_count"}),
    ),
    stats=StatsSpec(
        aggregates={
            ("birth_registrations", "sex"): {
                "kind": "categorical",
                "classification": None,
                "check_names": {"dbt:accepted_values", "invalid_percent", "datacontract:invalid_count"},
            },
            ("birth_registrations", "place_of_birth_suburb"): {
                "kind": "categorical",
                "classification": None,
                "check_names": {"dbt:accepted_values", "invalid_percent", "datacontract:invalid_count"},
            },
            ("birth_registrations", "date_of_birth"): {
                "kind": "numeric_date",
                "invalid_condition": "date_of_birth < DATE '1900-01-01'",
                "classification": None,
                "check_names": {"datacontract:custom_sql"},
            },
        },
        # Each categorical column's allowed values are its contract's, read at
        # run time (REQ-QAC-389).
        value_counts=(("birth_registrations", "sex"),),
    ),
    claim_window_dataset="birth-registrations",
)
