"""An asset's synthetic-era setting versions, held apart from its real ones
(REQ-GEN-371).

THE SPLIT: a setting version that exists only to stage the synthetic history -
back-dated, or named a synthetic era in its changelog, or the version that
says that era ends - lives in assets/<asset>/synthetic/eras.yaml; every other
version stays in data-asset.yaml. A real deployment has no synthetic/ folder,
so it reads data-asset.yaml alone and falls back as it would for a level that
declares nothing.

ONE TIMELINE, MERGED (criterion 2): every reader of a setting - the resolver,
the schedule gate and its freeze - reads the two files merged, each level's
versions in effective_from order, so a version moved between the files is not
a change (criterion 5) and the resolved setting on every date is the same
(criterion 4).

WHICH SETTINGS (Keith, 2026-11-18): the amber and replacement settings, whose
eras exist to stage scenarios. A list setting (census_years) records the real
world - its versions are back-dated only because they were written late - and
stays in data-asset.yaml.

eras.yaml has the shape of data-asset.yaml's setting levels, keyed by id:

    amber_setting: {versions: [...]}
    replacement_setting: {versions: [...]}
    collections:
      <collection id>: {replacement_setting: {versions: [...]}}
    datasets:
      <dataset id>: {amber_setting: {versions: [...]}}
"""
from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

__all__ = ["FILE", "KEYS", "ErasError", "is_synthetic", "merged", "path_for"]

FILE = "eras.yaml"
#: The settings whose synthetic eras move (Keith, 2026-11-18).
KEYS = ("amber_setting", "replacement_setting")
#: What a changelog says to name a synthetic era, or its end.
ERA_WORDS = "synthetic era"


class ErasError(ValueError):
    """eras.yaml names a collection or dataset the hierarchy does not hold."""


def path_for(data_asset_yaml: Path | str) -> Path:
    """The eras.yaml beside an asset's data-asset.yaml, in its synthetic/."""
    return Path(data_asset_yaml).parent / "synthetic" / FILE


def is_synthetic(version: dict) -> bool:
    """Criterion 1's rule: back-dated (its effective_from earlier than its
    first changelog entry's date), or its changelog calls it a synthetic era
    - which the version saying that era ends does too."""
    log = [e for e in (version.get("changelog") or []) if isinstance(e, dict)]
    if any(ERA_WORDS in str(e.get("change") or "").lower() for e in log):
        return True
    try:
        start = date.fromisoformat(str(version.get("effective_from")))
        first = date.fromisoformat(str(log[0].get("date")))
    except (IndexError, TypeError, ValueError):
        return False
    return start < first


def _levels(doc: dict):
    """(collection id, node) and (dataset id, node) for every level below the
    asset in the hierarchy."""
    for agency in ((doc.get("hierarchy") or {}).get("agencies") or []):
        for coll in (agency.get("collections") or []):
            yield "collections", coll.get("id"), coll
            for ds in (coll.get("datasets") or []):
                yield "datasets", ds.get("id"), ds


def _merge_setting(node: dict, key: str, extra: dict | None) -> None:
    versions = list((extra or {}).get("versions") or [])
    if not versions:
        return
    mine = (node.get(key) or {}).get("versions") or []
    both = sorted(list(mine) + versions, key=lambda v: str((v or {}).get("effective_from")))
    node[key] = {**(node.get(key) or {}), "versions": both}


def merged(doc: dict, eras: dict | None) -> dict:
    """data-asset.yaml's document with eras.yaml's versions merged into each
    level, effective_from order (criterion 2). The caller's documents are left
    alone. Refuses an eras.yaml naming a level the hierarchy does not hold -
    a version that would otherwise be silently dropped."""
    if not eras:
        return doc
    out = copy.deepcopy(doc)
    for key in KEYS:
        _merge_setting(out, key, eras.get(key))
    nodes = {(kind, ident): node for kind, ident, node in _levels(out)}
    for kind in ("collections", "datasets"):
        for ident, settings in ((eras.get(kind) or {}).items()):
            node = nodes.get((kind, ident))
            if node is None:
                raise ErasError(f"{FILE} sets {kind[:-1]} {ident!r}, which is not in the "
                                f"asset's hierarchy - remove it, or add the {kind[:-1]}.")
            for key in KEYS:
                _merge_setting(node, key, (settings or {}).get(key))
    return out


def merged_for(doc: dict, data_asset_yaml: Path | str) -> dict:
    """`doc` merged with the eras.yaml beside `data_asset_yaml`, where there is
    one."""
    from asset_model import config_yaml

    path = path_for(data_asset_yaml)
    if not path.exists():
        return doc
    return merged(doc, config_yaml.load(path) or {})
