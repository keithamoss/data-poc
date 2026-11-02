"""What EVERY asset's configuration declares - its agencies, collections and
datasets - read from each asset folder's data-asset.yaml as the resolver lays
it out now (Keith, 2026-11-03, morning report 12 Q6 and Q8).

One small reader for the checks that must tell another asset's name from a
typo: the dropped-scenario warning (generator/scenario_injection.py), the
refusal of a scenario naming a dataset no asset declares (REQ-GEN-246
criterion 8) and the feedback validator's agency check (REQ-DOCS-219
criterion 10). Each asset's pass otherwise reads only its own hierarchy
(REQ-PIPE-342 criterion 8); this reads the others' CONFIGURATION ONLY - never
another asset's database, data/ or reports/, and it selects no asset.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Declared:
    agencies: frozenset
    collections: frozenset
    datasets: frozenset


def declared() -> Declared:
    """The ids every asset declares, through the one hierarchy reader."""
    from qa_tools.common import assets, config_yaml, hierarchy

    agencies, collections, datasets = set(), set(), set()
    for asset in assets.every():
        path = asset.data_asset_yaml
        _, by_id, _ = hierarchy._from_text(path, config_yaml.read(path))
        for d in by_id.values():
            agencies.add(d.agency_id)
            collections.add(d.collection_id)
            datasets.add(d.dataset_id)
    return Declared(frozenset(agencies), frozenset(collections), frozenset(datasets))
