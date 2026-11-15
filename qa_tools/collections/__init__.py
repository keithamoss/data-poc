"""The collection registry's PIPELINE HALF (REQ-PIPE-240, split by
REQ-PIPE-380 criterion 3): loading a declared collection's QA adapter by
path. Which collections exist - each one's short, run prefix and check
files - is the declaration half, asset_model/collections.py, shared with the
generator; the cut sits here because running an adapter's code is the real
pipeline's alone, and asset_model/ runs no adapter or provider code.

ADAPTERS ARE CODE, CHOSEN BY CONFIGURATION, NEVER IMPORTED FROM IT
(criterion 4). A collection's id picks WHICH FILE of the selected asset's
adapter folder loads, BY PATH (REQ-PIPE-369 criterion 2, assets.load) -
`civil-registration` loads `civil_registration.py`, registered as
`mothman_adapter_<asset>_civil_registration`, never imported as a package
module - and the id must match the hierarchy's own id pattern first, so
configuration can never name an arbitrary import path.
"""
from __future__ import annotations

from asset_model import assets
from asset_model.collections import ID_PATTERN, Collection, UnknownCollectionError, all_collections, resolve


class NoAdapterError(UnknownCollectionError):
    """A declared collection with no adapter module: refused by name rather
    than run with another collection's behaviour (criterion 6)."""


def adapter_module(collection: Collection | str):
    """The collection's adapter module, loaded by path from the selected
    asset's adapter folder (REQ-PIPE-369 criterion 2) - the id checked against
    the hierarchy's id pattern BEFORE any path is built from it."""
    c = collection if isinstance(collection, Collection) else resolve(collection)
    if not ID_PATTERN.fullmatch(c.id):
        raise UnknownCollectionError(
            f"collection id {c.id!r} is not a hierarchy id, so it cannot name an adapter")
    try:
        return assets.load("adapter", c.module_name)
    except assets.NoModule:
        raise NoAdapterError(
            f"collection {c.id!r} has no adapter - "
            f"{assets.module_file('adapter', c.module_name)} does not exist, so nothing "
            f"knows how to run it") from None


def adapter(collection: Collection | str):
    """The collection's adapter (criterion 4)."""
    return adapter_module(collection).ADAPTER


def adapters() -> list:
    """Every collection's adapter, in hierarchy order."""
    return [adapter(c) for c in all_collections()]


def adapter_file(collection_id: str) -> str:
    """The file a collection's adapter loads from - what a spawned process
    reports back, and what a gate names. In this half since REQ-PIPE-380
    criterion 4: it was assets.adapter_file, asset_model's one import of the
    real pipeline."""
    return adapter_module(collection_id).__file__
