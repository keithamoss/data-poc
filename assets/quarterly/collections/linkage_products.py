"""Linkage Products' adapter (REQ-PIPE-336 criterion 1): the asset's linkage
release, linkage-keys, checked against the same quarter's linked tables, and
the geocoding release, one geo_<source> table per geocoded source (REQ-PIPE-296
criterion 1) - served here by extending only the declarations. Nothing in the
shared modules names this collection (criterion 2)."""
from qa_tools.collections.base import CollectionAdapter, DbtSpec, SodaSpec, StatsSpec

#: The geocoding tables, and the allowed match levels in display order.
GEO_TABLES = ("geo_cp_clients", "geo_ed_presentations")
MATCH_LEVELS = ("address", "postcode", "suburb", "not geocoded")

ADAPTER = CollectionAdapter(
    collection_id="linkage-products",
    label="Linkage Products",
    # A failing-row sample keeps only the key (plans/qa-pipeline.md #15): a
    # row's dataset and every identifier column the contract declares
    # (REQ-PIPE-341 criterion 3), so a referential failure names its record.
    # A geocoding table's key is the identifiers its source declares and the
    # census year (REQ-QAC-294 criterion 9; REQ-QAC-297 criterion 8).
    sample_key={"linkage_keys": ["dataset", "id_1", "id_2"],
                **{t: ["id_1", "census_year"] for t in GEO_TABLES}},
    # The three set-member tests are counted and sampled from their audit
    # rows, one row per violation (REQ-QAC-297 criterion 2).
    dbt=DbtSpec(row_counted_tests=frozenset({
        "missing_set_members", "duplicated_set_members", "unexpected_set_members"})),
    soda=SodaSpec(
        data_source="lp_collection",
        column_by_name={
            "Expected identifiers present": "id_1",
            "No surplus identifiers": "id_1",
            "Client Register links match a client": "id_1",
            "ED Presentations links match a presentation": "id_1",
            "Known match level": "match_level",
            "SA2 code in its format": "sa2_code",
            "LGA code in its format": "lga_code",
            "Rows matching no source record": "id_1",
        },
    ),
    # match_level's value counts only - read by the drift reference and the
    # page's value bars; never an area code or an identifier (REQ-QAC-297
    # criteria 11 and 15).
    stats=StatsSpec(value_counts={(t, "match_level"): MATCH_LEVELS for t in GEO_TABLES}),
    claim_window_dataset="linkage-keys",
)
