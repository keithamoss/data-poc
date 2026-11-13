"""The collection registry (REQ-PIPE-240): every collection the data asset
declares, read from the selected asset's data-asset.yaml hierarchy, and the adapter
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
(criterion 4). A collection's id picks WHICH FILE of the selected asset's
adapter folder loads, BY PATH (REQ-PIPE-369 criterion 2, assets.load) -
`civil-registration` loads `civil_registration.py`, registered as
`mothman_adapter_<asset>_civil_registration`, never imported as a package
module - and the id must match the hierarchy's own id pattern first, so
configuration can never name an arbitrary import path.

READS CONFIGURATION AND NOTHING ELSE: no connection is opened here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from qa_tools.common import assets, config_yaml, hierarchy

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
    #: The agency's short (REQ-PIPE-248 criterion 7), which names the
    #: collection's report files.
    agency_short: str = ""

    @property
    def label(self) -> str:
        """How people know it (REQ-TEST-245 criterion 2): a one-table
        collection by its dataset's name, an N-table one by its collection's
        name. Unique across the asset (post-build-review #230), because every
        picker shows a collection by it."""
        return self.datasets[0].dataset_name if len(self.datasets) == 1 else self.name

    @property
    def results_file(self) -> str:
        """Its results file's name under reports/ (REQ-PIPE-248 criterion 7)."""
        return f"results_{self.agency_short}_{self.id}.json"

    @property
    def dashboard_file(self) -> str:
        """Its dashboard data file's name under reports/."""
        return f"{self.agency_short}_{self.id}_dashboard.json"

    @property
    def module_name(self) -> str:
        """The adapter module, named by the id with hyphens as underscores."""
        return self.id.replace("-", "_")

    # ---- the collection's check files, found by convention (REQ-QAC-241) ----
    #
    # Every collection's contract, Soda, Evidently and retired-check files sit
    # in its agency's folder, contract/<agency-id>/, named from one stem - its
    # contract's file name less `-contract.yaml`. Paths are relative to the
    # repository root where it holds the asset's folder - as the lifecycle
    # gate reads them at any git ref, after asking assets.folder_rel(), which
    # refuses a folder outside it (C7) - and the folder itself otherwise.

    @property
    def folder(self) -> str:
        return f"{assets.folder_on_disk()}/{self.agency_id}"

    @property
    def stem(self) -> str:
        return self.contract.rsplit("/", 1)[-1].removesuffix("-contract.yaml")

    def check_file(self, kind: str, *, retired: bool = False) -> str:
        """`kind` is contract, soda or evidently; the retired sibling where
        `retired` is set."""
        suffix = {"contract": "contract{r}.yaml", "soda": "soda-checks{r}.yml",
                  "evidently": "evidently-checks{r}.yml"}[kind]
        return f"{self.folder}/{self.stem}-" + suffix.format(r="-retired" if retired else "")

    #: The collection's own dbt folders (REQ-QAC-241 criterion 4), in the
    #: selected asset's dbt project, asked at call time (REQ-QAC-368).
    @property
    def dbt_models(self) -> str:
        return f"{assets.dbt_on_disk()}/models/{self.id}"

    @property
    def dbt_tests(self) -> str:
        return f"{assets.dbt_on_disk()}/tests/{self.id}"

    @property
    def dbt_schema(self) -> str:
        return f"{self.dbt_models}/schema.yml"

    #: Outside model-paths, so dbt never runs a retired check.
    @property
    def dbt_retired_schema(self) -> str:
        return f"{assets.dbt_on_disk()}/retired/{self.id}/schema-retired.yml"

    def check_sources(self) -> list[tuple[str, str]]:
        """Every file this collection's checks are defined in, as
        (path, tool): its contract, Soda, Evidently and dbt schema files,
        each followed by its retired sibling (REQ-QAC-241 criterion 8)."""
        out = []
        for kind, tool in (("contract", "contract"), ("soda", "soda"), ("evidently", "evidently")):
            out += [(self.check_file(kind), tool), (self.check_file(kind, retired=True), tool)]
        return out + [(self.dbt_schema, "dbt"), (self.dbt_retired_schema, "dbt")]


#: The checks no collection owns: shared dbt SQL - every asset project's macro-paths,
#: dbt_shared/ (REQ-QAC-368 criterion 2) - and the file checks derived once
#: for every dataset (REQ-QAC-241 criterion 8).
SHARED_DBT_DIRS = (f"{assets.DBT_SHARED}/macros", f"{assets.DBT_SHARED}/tests/generic")


def file_checks() -> str:
    """The selected asset's file checks, by repository path where the
    repository holds them, asked at call time (REQ-PIPE-342 criterion 6) -
    it was the FILE_CHECKS constant."""
    return f"{assets.folder_on_disk()}/file-checks.yaml"


def collections_in(doc: dict) -> list[Collection]:
    """The collections a parsed data-asset.yaml declares, without datasets -
    what the lifecycle gate reads at a git ref, whose hierarchy may not be
    today's (REQ-QAC-241 criterion 7). `short` and `run_prefix` may be
    absent there, as they were before REQ-PIPE-240."""
    found = []
    for agency in ((doc.get("hierarchy") or {}).get("agencies") or []):
        for coll in agency.get("collections") or []:
            found.append(Collection(
                id=coll["id"], name=coll.get("name", coll["id"]), agency_id=agency["id"],
                agency_name=agency.get("name", agency["id"]),
                short=str(coll.get("short", "")), run_prefix=str(coll.get("run_prefix", "")),
                contract=str(coll.get("contract", "")), datasets=(),
                agency_short=str(agency.get("short", ""))))
    return found


_BUILT = config_yaml.Built()


def _load() -> tuple[Collection, ...]:
    """Every collection, built from data-asset.yaml as it reads now and
    keyed on its content (REQ-PIPE-254): an edited or swapped hierarchy is
    seen on the next call, an unchanged one is not built again."""
    path = hierarchy.data_asset_yaml()
    text = config_yaml.read(path)
    return _BUILT.get(str(path), text, lambda: _build(path, text))


def _build(path, text: str) -> tuple[Collection, ...]:
    # ONE READ FOR BOTH HALVES (REQ-PIPE-254 criterion 6): the collections
    # and the datasets inside them come from the same text, never from two
    # reads that could see two versions of the file. Named by its path, so a
    # slip names the file and its line rather than `<unicode string>`
    # (tests/test_cli_config_unreadable.py): the CLI modules reach this
    # registry while they import.
    doc = config_yaml.parse(text, name=str(path)) or {}
    by_collection: dict[str, list[hierarchy.Dataset]] = {}
    for d in hierarchy._from_text(path, text)[1].values():
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
                datasets=tuple(by_collection.get(coll["id"], ())),
                agency_short=str(hierarchy._require(agency, "short",
                                                    f"agency {agency.get('id')!r}"))))
    return tuple(found)


def check_files(kind: str, *, retired: bool = False) -> list[str]:
    """Every collection's `kind` check file (contract, soda or evidently)."""
    return [c.check_file(kind, retired=retired) for c in _load()]


def all_collections() -> list[Collection]:
    """Every collection the hierarchy declares, in hierarchy order."""
    return list(_load())


def _refuse(kind: str, value: str, known: list[str]):
    raise UnknownCollectionError(
        f"{value!r} is not a collection {kind} in {hierarchy.data_asset_yaml().name}. "
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
    return [adapter(c) for c in _load()]
