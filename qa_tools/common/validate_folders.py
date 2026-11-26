"""`mothman check`'s folders gate (REQ-PIPE-446 criteria 1, 2, 4, 5 and 13).

REPOSITORY-WIDE: it reads the asset and one-off folder NAMES, each folder's
data-asset.yaml for `data_asset_id` and `project`, and nothing else - no
asset is selected and no database is opened.

- A one-off folder whose name does not meet NAME_PATTERN (criterion 1): never
  selectable, so named here rather than left to fail somewhere quieter.
- A kind folder with no kind plug-in registered in code (criterion 2).
- One id under assets/ and a kind, or under two kinds (criterion 4).
- A data_asset_id other than the folder's name, assets and one-offs alike
  (criterion 5).
- A one-off that names no project (criterion 13; Keith 2026-11-21, every kind
  declares one).
"""
from __future__ import annotations

import sys
from pathlib import Path

from asset_model import assets, config_yaml, one_off_kinds


def _declared(folder: Path) -> dict:
    path = folder / "data-asset.yaml"
    if not path.is_file():
        return {}
    return config_yaml.load(path) or {}


def problems() -> list[str]:
    found: list[str] = []
    for path in assets.bad_one_off_names():
        found.append(f"{path}: the one-off's folder name is not lowercase letters, digits "
                     f"and single hyphens, so it can never be selected - rename it.")
    for kind in assets.one_off_kinds():
        if one_off_kinds.get(kind) is None:
            found.append(f"{assets.one_offs_root() / kind}: no kind plug-in is registered in "
                         f"code for {kind!r} - its package reader, generator, check layers "
                         f"and display words (asset_model/kinds/).")
    for name, folders in sorted(assets.id_clashes().items()):
        found.append(f"{name!r} names {len(folders)} folders - "
                     f"{', '.join(str(f) for f in folders)}. They would share data/{name}, "
                     f"reports/{name}, the database supply_{name} and a module tag; rename "
                     f"all but one.")
    folders = [(a.name, a.folder) for a in assets.every()]
    folders += [(name, assets.one_offs_root() / kind / name) for kind, name in assets.one_offs()]
    for name, folder in folders:
        stated = _declared(folder).get("data_asset_id")
        if stated is not None and stated != name:
            found.append(f"{folder / 'data-asset.yaml'} states data_asset_id {stated!r}, but "
                         f"its folder is {name!r} - the folder's name is its identity; make "
                         f"them match.")
    for kind, name in assets.one_offs():
        folder = assets.one_offs_root() / kind / name
        if not str(_declared(folder).get("project") or "").strip():
            found.append(f"{folder / 'data-asset.yaml'} names no project - every one-off, of "
                         f"every kind, states the project it is for (`project:`).")
    return found


def main() -> int:
    found = problems()
    if found:
        for p in found:
            print(f"  {p}")
        print(f"folders gate FAILED - {len(found)} problem(s).")
        return 1
    print("folders OK - every asset and one-off folder is named for its data_asset_id.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
