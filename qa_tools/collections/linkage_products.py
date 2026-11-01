"""Linkage Products' adapter (REQ-PIPE-336 criterion 1): the asset's linkage
release, linkage-keys, checked against the same quarter's linked tables. Its
checks are all Soda's; the geocoding datasets join it under REQ-PIPE-296.
Nothing in the shared modules names this collection (criterion 2)."""
from qa_tools.collections.base import CollectionAdapter, SodaSpec

ADAPTER = CollectionAdapter(
    collection_id="linkage-products",
    label="Linkage Products",
    # A failing-row sample keeps only the key (plans/qa-pipeline.md #15): a
    # row's dataset and every identifier column the contract declares
    # (REQ-PIPE-341 criterion 3), so a referential failure names its record.
    sample_key={"linkage_keys": ["dataset", "id_1", "id_2"]},
    soda=SodaSpec(
        data_source="lp_collection",
        column_by_name={
            "Expected identifiers present": "id_1",
            "No surplus identifiers": "id_1",
            "Client Register links match a client": "id_1",
            "ED Presentations links match a presentation": "id_1",
        },
    ),
    claim_window_dataset="linkage-keys",
)
