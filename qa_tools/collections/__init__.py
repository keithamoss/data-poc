"""The collection registry (REQ-PIPE-240): every collection the data asset
declares, read from contract/data-asset.yaml's hierarchy, and the adapter
each one's code is reached through.

WHY ONE REGISTRY. Until this, which collections existed was written down in
five places - processing_pass.COLLECTIONS, recheck's orchestrator map,
checkpoints' short-name map, bootstrap's ("bdm", "cp") branches and its
target-trial map - each a second copy of the hierarchy that a new
collection had to be added to by hand, and that said nothing when it was
not. A collection is now either picked up everywhere or refused by name.

THE SCALE THIS IS FOR is about thirty collections on one asset (Keith,
2026-10-16), so nothing here assumes two, and nothing assumes a calendar.

ADAPTERS ARE CODE, CHOSEN BY CONFIGURATION, NEVER IMPORTED FROM IT
(criterion 4). A collection's id picks WHICH module of this package
loads - `civil-registration` loads `qa_tools.collections.civil_registration`
- and the id must match the hierarchy's own id pattern first, so
configuration can never name an arbitrary import path.

READS CONFIGURATION AND NOTHING ELSE: no connection is opened here.
"""
from __future__ import annotations

import functools
import importlib
import re
from dataclasses import dataclass

from qa_tools.common import config_yaml, hierarchy

#: A collection id as the hierarchy writes them - and the only shape that
#: may become a module name.
ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


class UnknownCollectionError(KeyError):
    """A collection, short or run prefix the hierarchy does not declare.
    Names the value and every known one (criterion 3)."""

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else ""


class NoAdapterError(UnknownCollectionError):
    """A declared collection with no adapter module: refused by name rather
    than run with another collection's behaviour (criterion 6)."""


@dataclass(frozen=True)
class Collection:
    id: str
    name: str
    agency_id: str
    agency_name: str
    short: str
    run_prefix: str
    contract: str
    datasets: tuple[hierarchy.Dataset, ...]

    @property
    def module_name(self) -> str:
        """The adapter module, named by the id with hyphens as underscores."""
        return self.id.replace("-", "_")


@functools.lru_cache(maxsize=1)
def _load() -> tuple[Collection, ...]:
    doc = config_yaml.parse(hierarchy.DATA_ASSET_YAML.read_text()) or {}
    by_collection: dict[str, list[hierarchy.Dataset]] = {}
    for d in hierarchy.all_datasets():
        by_collection.setdefault(d.collection_id, []).append(d)
    found = []
    for agency in ((doc.get("hierarchy") or {}).get("agencies") or []):
        for coll in agency.get("collections") or []:
            where = f"collection {coll.get('id')!r}"
            found.append(Collection(
                id=coll["id"], name=coll["name"], agency_id=agency["id"],
                agency_name=agency["name"],
                short=str(hierarchy._require(coll, "short", where)),
                run_prefix=str(hierarchy._require(coll, "run_prefix", where)),
                contract=str(hierarchy._require(coll, "contract", where)),
                datasets=tuple(by_collection.get(coll["id"], ()))))
    return tuple(found)


def all_collections() -> list[Collection]:
    """Every collection the hierarchy declares, in hierarchy order."""
    return list(_load())


def _refuse(kind: str, value: str, known: list[str]):
    raise UnknownCollectionError(
        f"{value!r} is not a collection {kind} in {hierarchy.DATA_ASSET_YAML.name}. "
        f"Known: {', '.join(known)}")


def by_id(collection_id: str) -> Collection:
    for c in _load():
        if c.id == collection_id:
            return c
    _refuse("id", collection_id, [c.id for c in _load()])


def by_short(short: str) -> Collection:
    for c in _load():
        if c.short == short:
            return c
    _refuse("short name", short, [c.short for c in _load()])


def by_run_prefix(prefix: str) -> Collection:
    for c in _load():
        if c.run_prefix == prefix:
            return c
    _refuse("run prefix", prefix, [c.run_prefix for c in _load()])


def resolve(value: str) -> Collection:
    """A collection by id, short or run prefix - whichever `value` is."""
    for c in _load():
        if value in (c.id, c.short, c.run_prefix):
            return c
    _refuse("id, short name or run prefix", value,
            [f"{c.id} ({c.short}, {c.run_prefix})" for c in _load()])


def dataset(dataset_id: str) -> hierarchy.Dataset:
    """A dataset by id through the one index across every collection."""
    return hierarchy.dataset(dataset_id)


def collection_of(dataset_id: str) -> Collection:
    return by_id(hierarchy.dataset(dataset_id).collection_id)


def adapter(collection: Collection | str):
    """The collection's adapter, from this package only (criterion 4)."""
    c = collection if isinstance(collection, Collection) else resolve(collection)
    if not ID_PATTERN.fullmatch(c.id):
        raise UnknownCollectionError(
            f"collection id {c.id!r} is not a hierarchy id, so it cannot name an adapter")
    name = f"{__name__}.{c.module_name}"
    try:
        return importlib.import_module(name).ADAPTER
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        raise NoAdapterError(
            f"collection {c.id!r} has no adapter - {name.replace('.', '/')}.py does not "
            f"exist, so nothing knows how to run it") from None


def adapters() -> list:
    """Every collection's adapter, in hierarchy order."""
    return [adapter(c) for c in _load()]
