"""How the dashboard describes the asset (REQ-DASH-244 criterion 10).

contract/presentation.yaml holds the words the page uses that no contract
field carries: each agency's blurb, and who supplies each collection and
how. Read by the dashboard builder, the embed step and `mothman check`'s
collections gate, which fails a registered collection with no entry before
any build (criterion 8).
"""
from __future__ import annotations

from pathlib import Path

from qa_tools.common import config_yaml

#: What every collection's entry must carry.
COLLECTION_KEYS = ("provider", "delivery_format", "provenance")


def _load(path: Path) -> dict:
    """The file as it reads now, parsed only when its text has changed, and
    the caller's own copy (REQ-PIPE-254): config_yaml keys the parse on the
    content and deep-copies what it hands out, so an edited file is seen on
    the next call and no caller's change reaches another's."""
    return config_yaml.load(path) or {}


def _default() -> Path:
    """Beside the hierarchy, wherever that is read from - the repository's
    contract/ unless a test has moved it."""
    from qa_tools.common import hierarchy

    return Path(hierarchy.data_asset_yaml()).parent / "presentation.yaml"


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


def list_setting_label(setting: str, path: Path | None = None) -> str | None:
    """A list setting's display name - 'Census years' - keying the page's
    tile for the set a result was judged against (REQ-DASH-299 criterion 9)."""
    entry = (load(path).get("list_settings") or {}).get(setting)
    label = entry.get("label") if isinstance(entry, dict) else None
    return str(label) if label else None


def relation_word(dataset_id: str, path: Path | None = None) -> str | None:
    """A dataset's word for its relation to the one source it links with no
    code - 'Geocodes' - keying the page's tile naming that source
    (REQ-DASH-299 criterion 10)."""
    entry = (load(path).get("datasets") or {}).get(dataset_id)
    word = entry.get("relation") if isinstance(entry, dict) else None
    return str(word) if word else None


def _single_codeless_source(dataset) -> str | None:
    """The source a dataset links with no code - its linked_datasets a
    single entry with no code (REQ-QAC-294 criterion 2) - or None."""
    linked = tuple(getattr(dataset, "linked", ()) or ())
    return linked[0][0] if len(linked) == 1 and linked[0][1] is None else None


def linked_source(dataset, path: Path | None = None) -> dict | None:
    """{datasetId, relation} for a dataset linking one source with no code,
    else None - the page's relation tile (REQ-DASH-299 criterion 10)."""
    source = _single_codeless_source(dataset)
    if source is None:
        return None
    return {"datasetId": source, "relation": relation_word(dataset.dataset_id, path)}


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
    out += _tile_word_problems(path)
    return out


def _tile_word_problems(path: Path) -> list[str]:
    """Every list setting the asset declares, and every dataset linking one
    source with no code, has its tile's word (REQ-DASH-299 criteria 9 and 10;
    NFR 2) - so the page never shows a tile it cannot name."""
    from qa_tools.common import amber_setting, config_yaml, hierarchy

    out = []
    doc = config_yaml.load(Path(hierarchy.data_asset_yaml())) or {}
    for _container, name in amber_setting.list_setting_keys(doc):
        if not list_setting_label(name, path):
            out.append(f"list setting {name!r} has no `label` under `list_settings:` in "
                       f"contract/presentation.yaml, so its tile on the dataset page has no name")
    for ds in hierarchy.all_datasets():
        if _single_codeless_source(ds) is not None and not relation_word(ds.dataset_id, path):
            out.append(f"dataset {ds.dataset_id!r} links one source with no code but has no "
                       f"`relation` under `datasets:` in contract/presentation.yaml, so its tile "
                       f"on the dataset page has no name")
    return out
