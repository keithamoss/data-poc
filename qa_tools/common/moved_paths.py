"""The move map (REQ-TEST-366): every file the asset split moves or divides,
from its old path to its new path or paths, followed by every read of a base
commit in the push that carries the move - and deleted, with this module, in
the push after it (criterion 3).

WHY. The freeze and lifecycle gates compare a file with itself at the push's
base, and both treat a path that did not exist there as brand new - nothing to
have changed FROM. Moving contract/ to assets/<asset>/ would therefore carry a
frozen or check change through unseen (the requirement's RELIABILITY NFR). So
a reader of a base commit that finds a file's CURRENT path missing there asks
this module for the OLD path instead (criterion 2), through `read_at`.

ONLY FOR THE PUSH THAT CARRIES THE MOVE (criterion 7): the map is consulted
only where it is present in the working tree AND the push's diff base
(MOTHMAN_DIFF_BASE, read through diff_base()) holds no assets/ folder. Before
the move there is no map, so this is inert; after the next push there is no
map either.

A DIVIDED FILE IS COMPARED PART WITH PART (criterion 5). data-asset.yaml,
calendar.yaml and people.yaml each became one file per asset. Read at the base
for an asset, the old file is cut down to that asset's part first - every list
item or mapping key identifying another asset's agency, collection, dataset,
calendar or declared correction removed, by the member lists the map declares
- so a frozen item that moved to the other asset reads as moved, not removed,
and a frozen item changed in the move still fails as it would have in place.
The same cut-down also renames the former data_asset_id wherever it is a whole
value (REQ-QAC-344's rename of `data_asset_id:` and a people assignment's
`data_asset:`), so the rename itself is not read as a change.

THE FORMER data_asset_id COMES FROM THE MAP (REQ-QAC-344 criterion 5), never
from code; `id_rename` hands it to the check-id transform beside
check_lifecycle.migrate_pre_039_check_id.

READS GIT AND THE WORKING TREE, NEVER A DATABASE.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

#: Where the map lives, relative to the repository root (name SETTLED by
#: Keith 2026-11-01).
MAP_REL = "assets/moved-paths.yaml"

#: The keys a list item or mapping is identified by in the divided files -
#: an agency, collection or dataset id, a calendar's name, a declared
#: correction's reference.
_IDENTITY_KEYS = ("id", "name", "dataset", "agency", "collection", "change_reference")


class MoveMapError(ValueError):
    """The move map is malformed."""


@dataclass(frozen=True)
class MoveMap:
    former_data_asset_id: str
    #: asset -> the ids that belong to it (agencies, collections, datasets,
    #: calendars, declared corrections).
    members: dict[str, frozenset[str]]
    #: new path -> old path.
    sources: dict[str, str]
    #: old path -> its new paths (more than one: a divided file).
    targets: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @staticmethod
    def asset_of(new_rel: str) -> str | None:
        """The asset a new path sits under - assets/<asset>/... - or None."""
        parts = Path(new_rel).parts
        return parts[1] if len(parts) > 2 and parts[0] == "assets" else None

    def divided(self, old_rel: str) -> bool:
        return len(self.targets.get(old_rel, ())) > 1

    def others(self, asset: str) -> frozenset[str]:
        """Ids of every OTHER asset that are not also this asset's."""
        mine = self.members.get(asset, frozenset())
        return frozenset().union(*(ids for a, ids in self.members.items() if a != asset)) - mine


def parse(text: str) -> MoveMap:
    """A move map from its YAML text."""
    doc = yaml.safe_load(text) or {}
    former = doc.get("former_data_asset_id")
    if not isinstance(former, str) or not former:
        raise MoveMapError(f"{MAP_REL}: former_data_asset_id is missing")
    members = {str(a): frozenset(str(i) for kind in (ids or {}).values() for i in kind or [])
               for a, ids in (doc.get("assets") or {}).items()}
    sources: dict[str, str] = {}
    targets: dict[str, tuple[str, ...]] = {}
    for entry in doc.get("moves") or []:
        old, new = entry.get("from"), entry.get("to")
        new = [new] if isinstance(new, str) else list(new or [])
        if not isinstance(old, str) or not new:
            raise MoveMapError(f"{MAP_REL}: each move gives `from` and `to` - {entry!r}")
        for n in new:
            if n in sources:
                raise MoveMapError(f"{MAP_REL}: {n} is the target of two moves")
            sources[n] = old
        targets[old] = tuple(new)
    return MoveMap(former, members, sources, targets)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _base_holds_assets(root: Path, base: str) -> bool:
    # Not cached: one `git cat-file` is a few milliseconds, and a cache keyed
    # on a ref like HEAD~1 would outlive what it names.
    return _git(root, "cat-file", "-e", f"{base}:assets").returncode == 0


def applies(root: Path) -> MoveMap | None:
    """The map, where it is to be followed: present in the working tree of
    `root`, and the push's diff base holding no assets/ folder (criterion 7).
    None otherwise - before the move, and in every push after the one that
    carries it."""
    from qa_tools.common.diff_base import diff_base

    path = Path(root) / MAP_REL
    if not path.is_file():
        return None
    if _base_holds_assets(Path(root), diff_base(root=Path(root))):
        return None
    return parse(path.read_text())


def old_path(rel: str, root: Path) -> str | None:
    """The path `rel` had before the move, where the map applies and lists
    it; None otherwise."""
    mm = applies(root)
    return mm.sources.get(rel) if mm else None


def part(doc, asset: str, mm: MoveMap):
    """The part of a divided file's parsed content that went to `asset`:
    every list item and mapping entry identifying another asset's member
    removed, and the former data_asset_id renamed to `asset` wherever it is a
    whole value. Everything else - asset-wide settings, comments' meaning,
    order - kept."""
    others = mm.others(asset)

    def other(value) -> bool:
        return isinstance(value, str) and value in others

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items() if not other(k)}
        if isinstance(node, list):
            return [walk(v) for v in node
                    if not (isinstance(v, dict) and any(other(v.get(k)) for k in _IDENTITY_KEYS))]
        if node == mm.former_data_asset_id:
            return asset
        return node

    return walk(doc)


def read_at(rel: str, ref: str, root: Path, show) -> str | None:
    """`rel` at `ref`, through `show(rel, ref)` - a reader's own one-file
    `git show`, returning None for a missing path - or, where that path is
    missing at `ref` and the map applies, the OLD path's content there: as it
    was for a file moved whole, cut down to this asset's part for a divided
    one (criteria 2 and 5)."""
    text = show(rel, ref)
    if text is not None:
        return text
    mm = applies(root)
    old = mm.sources.get(rel) if mm else None
    if old is None:
        return None
    text = show(old, ref)
    if text is None or not mm.divided(old):
        return text
    asset = mm.asset_of(rel)
    doc = yaml.safe_load(text)
    cut = part(doc, asset, mm)
    return text if cut == doc else yaml.safe_dump(cut, sort_keys=False, allow_unicode=True)


def old_files_under(rel_dir: str, root: Path) -> dict[str, str]:
    """{new path: old path} for every moved file under `rel_dir` - what a
    reader listing a folder at the base reads when the folder is new
    (validate_check_lifecycle._files_in)."""
    mm = applies(root)
    if mm is None:
        return {}
    prefix = rel_dir.rstrip("/") + "/"
    return {new: old for new, old in mm.sources.items() if new.startswith(prefix)}


def id_rename(root: Path, asset: str) -> tuple[str, str] | None:
    """(former data_asset_id, `asset`) where the map applies - what
    check_lifecycle's move transform reads a renamed check id with
    (REQ-QAC-344 criteria 4 and 5); None where it does not."""
    mm = applies(root)
    return (mm.former_data_asset_id, asset) if mm else None
