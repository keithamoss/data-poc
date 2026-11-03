"""What EVERY asset's configuration declares - its agencies, collections and
datasets - read from each asset folder's data-asset.yaml as the resolver lays
it out now (Keith, 2026-11-03, morning report 12 Q6 and Q8).

One small reader for the checks that must tell another asset's name from a
typo: the dropped-scenario warning (generator/scenario_injection.py), the
refusal of a scenario naming a dataset no asset declares (REQ-GEN-246
criterion 8) and the feedback validator's agency check (REQ-DOCS-219
criterion 10). Each asset's pass otherwise reads only its own hierarchy
(REQ-PIPE-342 criterion 8, which since 2026-11-03 names these two readers as
its exception); this reads the others' CONFIGURATION ONLY - never another
asset's database, data/ or reports/, and it selects no asset.

ITS PREMISE (Keith, 2026-11-03, the Q6/Q8 follow-up, post-build-review #315
H1): scenarios exist only for SYNTHETIC assets, and both synthetic assets are
always present together, for demo and for test - so this read always finds
both, and another asset's scenario is always told from a mistyped one. A
deployment whose assets/ root is injected with a single asset (#55) is a
real one, and a real asset carries no scenarios, so the case where the other
asset's folder is missing - and its scenarios would read as mistyped - does
not arise. REJECTED: staying quiet when the other asset's folder is absent,
and deferring the question to REQ-PIPE-354.

A FOLDER WITH NO data-asset.yaml DECLARES NOTHING and is passed over
(post-build-review #315 M2) - a half-made asset or a stray directory under
assets/ must not stop generation or the feedback validator.
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
    from qa_tools.common import assets, hierarchy

    agencies, collections, datasets = set(), set(), set()
    for asset in assets.every():
        path = asset.data_asset_yaml
        if not path.is_file():
            continue
        for d in hierarchy.datasets_declared_in(path):
            agencies.add(d.agency_id)
            collections.add(d.collection_id)
            datasets.add(d.dataset_id)
    return Declared(frozenset(agencies), frozenset(collections), frozenset(datasets))
