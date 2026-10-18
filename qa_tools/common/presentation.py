"""How the dashboard describes the asset (REQ-DASH-244 criterion 10).

contract/presentation.yaml holds the words the page uses that no contract
field carries: each agency's blurb, and who supplies each collection and
how. Read by the dashboard builder, the embed step and `mothman check`'s
collections gate, which fails a registered collection with no entry before
any build (criterion 8).
"""
from __future__ import annotations

import functools
from pathlib import Path

import yaml

#: What every collection's entry must carry.
COLLECTION_KEYS = ("provider", "delivery_format", "provenance")


@functools.cache
def _load(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _default() -> Path:
    """Beside the hierarchy, wherever that is read from - the repository's
    contract/ unless a test has moved it."""
    from qa_tools.common import hierarchy

    return Path(hierarchy.DATA_ASSET_YAML).parent / "presentation.yaml"


def load(path: Path | None = None) -> dict:
    return _load(Path(path or _default()))


def agency_blurbs(path: Path | None = None) -> dict[str, str]:
    """{agency id: blurb} - an agency with none shows none."""
    return {agency_id: str(entry.get("blurb") or "")
            for agency_id, entry in (load(path).get("agencies") or {}).items()
            if isinstance(entry, dict) and entry.get("blurb")}


def for_collection(collection_id: str, path: Path | None = None) -> dict:
    entry = (load(path).get("collections") or {}).get(collection_id)
    if not isinstance(entry, dict):
        raise ValueError(f"collection {collection_id!r} has no entry under `collections:` in "
                         f"contract/presentation.yaml")
    return entry


def problems(path: Path | None = None) -> list[str]:
    """Every registered collection the dashboard could not describe."""
    from qa_tools import collections

    path = Path(path or _default())
    if not path.is_file():
        return ["contract/presentation.yaml is missing, so the dashboard cannot be built"]
    found = load(path).get("collections") or {}
    out = []
    for coll in collections.all_collections():
        entry = found.get(coll.id)
        if not isinstance(entry, dict):
            out.append(f"collection {coll.id!r} has no entry under `collections:` in "
                       f"contract/presentation.yaml, so the dashboard cannot be built for it")
            continue
        for key in COLLECTION_KEYS:
            if not isinstance(entry.get(key), str):
                out.append(f"collection {coll.id!r}'s entry in contract/presentation.yaml has "
                           f"no `{key}`")
    return out
