"""The extraction kind's ONE SHARED ADAPTER (REQ-QAC-441; REQ-PIPE-440
criterion 4): every collection of every extraction is run through this, built
from what its one-off's data-asset.yaml declares - never from a module in the
one-off's folder, which has none.

What it says is data, not code, as every adapter's is (qa_tools/collections/
base.py): each table's failing-row key is its DECLARED PRIMARY IDENTIFIERS
(REQ-QAC-441 criterion 9 - keys only, never row content), and each recipe
failed-rows check's column is the column its generated name begins with
(asset_model/kinds/extraction_checks.py names them).
"""
from __future__ import annotations

from qa_tools.collections.base import CollectionAdapter, SodaSpec


def _tables(collection) -> list:
    from asset_model import assets, config_yaml
    from asset_model.kinds import extraction_checks

    asset = assets.selected()
    doc = config_yaml.load(asset.data_asset_yaml) or {}
    calendar = config_yaml.load(asset.file("calendar.yaml")) or {}
    return [t for t in extraction_checks.declared(doc, calendar)
            if t.collection_id == collection.id]


def adapter_for(collection) -> CollectionAdapter:
    from asset_model.kinds import extraction_checks

    tables = _tables(collection)
    column_by_name = {}
    for t in tables:
        for c in t.columns:
            for a in ("declared_type", "cohort_bounds"):
                column_by_name[f"{c['name']} {extraction_checks.RECIPE_WORDS[a]['name'].lower()}"] \
                    = c["name"]
    return CollectionAdapter(
        collection_id=collection.id, label=collection.name,
        sample_key={t.table: t.identifiers for t in tables},
        soda=SodaSpec(data_source=collection.id.replace("-", "_"),
                      column_by_name=column_by_name),
    )
