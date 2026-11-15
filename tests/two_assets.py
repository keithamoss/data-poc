"""A fixture repository holding TWO asset folders (REQ-PIPE-364 criterion 6).

`make(tmp_path)` builds `<tmp>/repo/` with assets/one/ and assets/two/, each a
copy of the real daily asset's configuration renamed to its folder - so both
assets declare the same agency, collection, shorts, run prefix, tables and
provider seeds, which is the case where both assets reuse a collection id and
each must still pass. Beside them it copies the shared trees the layout gate
reads (qa_tools/collections/, generator/collections/, dbt_shared/) and
environments.yaml.

`acting_for(root, name, monkeypatch)` points the resolver at the fixture's
assets/ and selects one of its assets, as `mothman check`'s per-asset pass
selects a real one; the suite's autouse fixture points it back after the test.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from qa_tools.common import assets

#: The real asset copied into each fixture asset - the smaller of the two,
#: one collection of one dataset.
SOURCE = "daily"
NAMES = ("one", "two")

_SKIP = shutil.ignore_patterns("dbt_packages", "target", "__pycache__", "logs")


def make(tmp_path: Path) -> Path:
    repo = Path(tmp_path) / "repo"
    real = assets._DEFAULT.root
    for name in NAMES:
        folder = repo / "assets" / name
        shutil.copytree(real / SOURCE, folder, ignore=_SKIP)
        path = folder / "data-asset.yaml"
        text = path.read_text()
        assert f"data_asset_id: {SOURCE}\n" in text
        path.write_text(text.replace(f"data_asset_id: {SOURCE}\n", f"data_asset_id: {name}\n"))
    shutil.copy(real / "environments.yaml", repo / "assets" / "environments.yaml")
    for shared in ("qa_tools/collections", "generator/collections", assets.DBT_SHARED):
        shutil.copytree(assets.ROOT / shared, repo / shared, ignore=_SKIP)
    return repo


def acting_for(repo: Path, name: str, monkeypatch) -> assets.Asset:
    assets.use_root(Path(repo) / "assets")
    monkeypatch.setenv(assets.ASSET_ENV, name)
    return assets.selected()


def hierarchy_of(repo: Path, name: str) -> dict:
    return yaml.safe_load((Path(repo) / "assets" / name / "data-asset.yaml").read_text())


def write_hierarchy(repo: Path, name: str, doc: dict) -> None:
    (Path(repo) / "assets" / name / "data-asset.yaml").write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))


def collection(doc: dict) -> dict:
    """The one collection the copied asset declares."""
    return doc["hierarchy"]["agencies"][0]["collections"][0]


def dataset(doc: dict) -> dict:
    return collection(doc)["datasets"][0]


def add_dataset(repo: Path, name: str, dataset_id: str, table: str) -> None:
    """A second dataset in the asset's one collection, a copy of the first
    under a new id and table."""
    doc = hierarchy_of(repo, name)
    copy = dict(dataset(doc), id=dataset_id, table=table, name=dataset_id)
    copy.pop("linked_datasets", None)
    collection(doc)["datasets"].append(copy)
    write_hierarchy(repo, name, doc)


def add_collection(repo: Path, name: str, *, collection_id: str, short: str, run_prefix: str,
                   dataset_id: str, table: str, label: str) -> None:
    """A second collection in the asset's one agency: a copy of the first
    under the given identifiers, with its own adapter and provider copied
    from the first's and renamed - so the only thing it can share with the
    first is what the caller asks it to."""
    doc = hierarchy_of(repo, name)
    first = collection(doc)
    module = collection_id.replace("-", "_")
    copy = dict(first, id=collection_id, name=collection_id, short=short, run_prefix=run_prefix)
    copy["datasets"] = [dict(first["datasets"][0], id=dataset_id, table=table, name=dataset_id)]
    doc["hierarchy"]["agencies"][0]["collections"].append(copy)
    write_hierarchy(repo, name, doc)
    folder = Path(repo) / "assets" / name
    old = first["id"].replace("-", "_")
    adapter = (folder / "collections" / f"{old}.py").read_text()
    adapter = adapter.replace(f'collection_id="{first["id"]}"', f'collection_id="{collection_id}"')
    adapter = re.sub(r'\blabel="[^"]*"', f'label="{label}"', adapter, count=1)
    (folder / "collections" / f"{module}.py").write_text(adapter)
    provider = (folder / "synthetic" / "collections" / f"{old}.py").read_text()
    provider = provider.replace(f'collection_id = "{first["id"]}"',
                                f'collection_id = "{collection_id}"')
    (folder / "synthetic" / "collections" / f"{module}.py").write_text(provider)
