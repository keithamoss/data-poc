"""The agency/collection/dataset hierarchy, resolved from one place
(REQ-QAC-039).

WHAT THIS REPLACES. Until 2026-09-23 the tree was literals in twelve
Python files: `AGENCY_ID`/`COLLECTION_ID`/`DATASET_ID` copy-pasted
across the four BDM tool scripts, a hand-maintained
`TABLE_DATASET_ID`/`TABLE_DATASET_NAME` pair in `cp_common.py`, plus
`ticket_sync.py`'s `DATASET_SCOPE`, `acceptance_sync.py`'s
`QA_RESULTS_SCOPE_FOR_DATASET`, `github_links.py`'s folder constants,
both orchestrators and both dashboard build scripts. `ticket_sync.py`'s
own comment had already recorded that it was the FOURTH copy and that
four was the trigger for consolidating - then deferred it.

The cost of that shape was not duplication for its own sake. It was
that a check's id, its dashboard URL and its stored results each
carried a different half of the truth, and nothing could tell you they
disagreed, because no single statement of the tree existed to disagree
WITH.

WHY IT READS CONFIG RATHER THAN DECLARING THE TREE ITSELF. The
hierarchy is data-asset-level configuration, so it lives in
`contract/data-asset.yaml` alongside the other asset-level config - and
alongside REQ-PIPE-049's named delivery calendars, which land in the
same file. A dataset naming a calendar and a dataset naming its
collection then resolve through one file rather than two mechanisms.
Keith's call, 2026-09-23.

READ ONCE, CACHED. Every consumer here is a short-lived CLI or build
process, and the file cannot change mid-run - so the parse happens once
and the result is reused. That also makes this safe to import at module
scope in the tool scripts, which is how they used to use their
constants.

NO FALLBACKS, DELIBERATELY. An unknown dataset id raises rather than
returning None or an empty scope. Every caller here is asking "where
does this dataset live", and a caller that gets a plausible-looking
wrong answer writes results to the wrong path or builds a check_id that
validates and means nothing. The same "fail loudly over a permissive
fallback" stance the rest of this package takes.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import yaml

DATA_ASSET_YAML = Path(__file__).resolve().parent.parent.parent / "contract" / "data-asset.yaml"


class UnknownDatasetError(KeyError):
    """Raised for a dataset id the hierarchy does not define.

    A KeyError subclass so an existing `except KeyError` still catches
    it, but named so the traceback says what actually went wrong rather
    than showing a bare id.
    """


@dataclass(frozen=True)
class Dataset:
    """One dataset's full place in the tree.

    Carries its ancestors rather than pointing at them: every consumer
    that has a dataset wants the agency and collection ids in the same
    breath - to build a check_id, a qa_results path or a dashboard URL -
    and a reference to walk up would just be re-derived at each call
    site, which is the shape this module exists to remove.
    """

    data_asset_id: str
    agency_id: str
    agency_name: str
    collection_id: str
    collection_name: str
    dataset_id: str
    dataset_name: str
    table: str
    contract: str          # the ODCS contract file covering this collection

    @property
    def qa_results_scope(self) -> tuple[str, str]:
        """(agency, collection) - where this dataset's committed QA
        results live under `qa_results/`.

        Deliberately the COLLECTION, not the dataset. Child Protection
        already wrote under its collection while Birth Registrations
        wrote under its dataset id, which is the asymmetry
        REQ-QAC-039's "model a collection for Birth Registrations by
        the same mechanism Child Protection uses" removes. Moving BDM
        onto this changes its committed directory tree, which is why
        that change rides the one combined regeneration rather than
        happening on its own (Keith, 2026-09-23).
        """
        return (self.agency_id, self.collection_id)


def _require(node: dict, key: str, where: str):
    """One required config key, or an error naming where it is missing.

    A bare KeyError here surfaces as the word 'contract' with no
    context, three frames below whatever was actually being asked -
    which is what it did the first time a config without one was
    loaded.
    """
    if key not in node:
        raise ValueError(f"{DATA_ASSET_YAML}: {where} declares no `{key}:`")
    return node[key]


@functools.lru_cache(maxsize=1)
def _load() -> tuple[str, dict[str, Dataset]]:
    with open(DATA_ASSET_YAML) as f:
        doc = yaml.safe_load(f) or {}

    data_asset_id = doc.get("data_asset_id")
    if not data_asset_id:
        raise ValueError(f"{DATA_ASSET_YAML} declares no data_asset_id")

    hierarchy = doc.get("hierarchy") or {}
    datasets: dict[str, Dataset] = {}
    for agency in hierarchy.get("agencies") or []:
        for collection in agency.get("collections") or []:
            for dataset in collection.get("datasets") or []:
                entry = Dataset(
                    data_asset_id=data_asset_id,
                    agency_id=agency["id"],
                    agency_name=agency["name"],
                    collection_id=collection["id"],
                    collection_name=collection["name"],
                    dataset_id=dataset["id"],
                    dataset_name=dataset["name"],
                    table=dataset["table"],
                    contract=_require(collection, "contract",
                                       f"collection {collection.get('id')!r}"),
                )
                # A duplicate id would make every lookup for it
                # ambiguous and silently resolve to whichever came
                # last, so it is an error rather than a last-wins.
                if entry.dataset_id in datasets:
                    raise ValueError(
                        f"{DATA_ASSET_YAML}: dataset id {entry.dataset_id!r} is defined twice"
                    )
                datasets[entry.dataset_id] = entry

    if not datasets:
        raise ValueError(f"{DATA_ASSET_YAML} defines no datasets under hierarchy.agencies")
    return data_asset_id, datasets


def data_asset_id() -> str:
    return _load()[0]


def all_datasets() -> list[Dataset]:
    """Every dataset, in the order the config declares them."""
    return list(_load()[1].values())


def dataset(dataset_id: str) -> Dataset:
    """One dataset by id, or `UnknownDatasetError` naming what is known.

    The error lists the real ids because the usual cause is a near
    miss - an underscore for a hyphen, or a table name where a dataset
    id belongs - and a bare KeyError makes that guesswork.
    """
    _, datasets = _load()
    try:
        return datasets[dataset_id]
    except KeyError:
        raise UnknownDatasetError(
            f"{dataset_id!r} is not a dataset in {DATA_ASSET_YAML.name}. "
            f"Known: {', '.join(sorted(datasets))}"
        ) from None


def dataset_for_table(table: str) -> Dataset:
    """The dataset a physical table belongs to.

    Replaces `cp_common.TABLE_DATASET_ID`. A dataset maps to exactly one
    logical table by construction under the supply model (Thread F), so
    this is a real inverse rather than a lookup that might miss.
    """
    for entry in all_datasets():
        if entry.table == table:
            return entry
    raise UnknownDatasetError(
        f"no dataset maps to table {table!r} in {DATA_ASSET_YAML.name}. "
        f"Known tables: {', '.join(sorted(d.table for d in all_datasets()))}"
    )


def contract_path(collection_id: str) -> Path:
    """The ODCS contract file covering one collection.

    Stated in the hierarchy rather than in a map beside each consumer,
    for the reason REQ-QAC-039 exists: a second copy is a copy that
    drifts, and this one is how a file's own dataset gets resolved from
    its name (REQ-GEN-043).
    """
    return DATA_ASSET_YAML.parent / datasets_in_collection(collection_id)[0].contract


def datasets_in_collection(collection_id: str) -> list[Dataset]:
    """Every dataset under one collection, declaration order.

    Replaces `cp_common.TABLES`, which was a hand-kept list of the same
    six names in a different file from the map that gave them ids.
    """
    found = [d for d in all_datasets() if d.collection_id == collection_id]
    if not found:
        raise UnknownDatasetError(
            f"{collection_id!r} is not a collection in {DATA_ASSET_YAML.name}. "
            f"Known: {', '.join(sorted({d.collection_id for d in all_datasets()}))}"
        )
    return found
