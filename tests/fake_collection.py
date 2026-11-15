"""The fake Widget Register, added to a copy of the repository (REQ-TEST-249).

THE FILES ARE IN tests/fake_collection_files/ (criterion 1): its contract and
check files under assets/quarterly/widget-agency/, its dbt models under
assets/quarterly/dbt/models/widget-register/, its QA adapter under
assets/quarterly/collections/ and its generator provider under
assets/quarterly/synthetic/collections/ - laid out exactly where a real
quarterly collection's would go since the asset split - plus inserts/, the
blocks it adds to the asset's configuration.

`install(tree)` copies the files into a copy made by tests/tree_copy.py and
inserts each block WHOLE, as text, so every pre-existing line of the file it
lands in stays where it was (criterion 3). `additions_only(tree)` is that
criterion's check, and holds for any copy, not only this one's.

THREE CONFIGURATION FILES TAKE AN INSERT, not one. Criterion 3 names only
the hierarchy (data-asset.yaml), but a dataset with no entry in the asset's
calendar.yaml is refused outright, and REQ-DASH-244 put every collection's words
in its presentation.yaml, whose gate fails a collection with no entry. So the
criterion covers all three, by the same rule (Keith, 2026-10-18, amending it;
plans/running-thoughts.md #106). All three are the quarterly asset's
(post-build-review #333).
"""
from __future__ import annotations

import difflib
import shutil
from pathlib import Path

import yaml

from tree_copy import ROOT, tracked_files

FILES = Path(__file__).resolve().parent / "fake_collection_files"
INSERTS = FILES / "inserts"

COLLECTION_ID, SHORT, AGENCY_ID = "widget-register", "wreg", "widget-agency"
DATASET_ID, TABLE = "widgets", "widgets"
#: The asset the fake joins, and its folder (post-build-review #333).
ASSET = "quarterly"
A = f"assets/{ASSET}"

#: Where a collection's own new files may go (criterion 3).
OWN_PATHS = (f"{A}/{AGENCY_ID}/", f"{A}/dbt/models/{COLLECTION_ID}/",
             f"{A}/dbt/tests/{COLLECTION_ID}/", f"{A}/collections/",
             f"{A}/synthetic/collections/")

#: The asset-wide files that take an insert, and where each block lands.
EDITED = (f"{A}/data-asset.yaml", f"{A}/calendar.yaml", f"{A}/presentation.yaml")


def own_files() -> list[str]:
    """Every file the fake adds, as a repository path."""
    out = sorted(str(p.relative_to(FILES)) for p in FILES.rglob("*")
                 if p.is_file() and not p.is_relative_to(INSERTS) and "__pycache__" not in p.parts)
    assert out, f"{FILES} holds no files - the test would add nothing"
    return out


def _insert(lines: list[str], at: int, block: str) -> list[str]:
    return lines[:at] + block.splitlines(keepends=True) + lines[at:]


def _block(name: str) -> str:
    return (INSERTS / name).read_text()


def _index(lines: list[str], startswith: str, after: int = 0) -> int:
    for i in range(after, len(lines)):
        if lines[i].startswith(startswith):
            return i
    raise AssertionError(f"no line starts {startswith!r}")


def install(tree: Path) -> Path:
    """Add the fake collection's files and blocks to the copy at `tree`."""
    for rel in own_files():
        dest = tree / rel
        assert not dest.exists(), f"{rel} already exists in the copy - the fake would overwrite it"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FILES / rel, dest)

    # The hierarchy's agencies are the file's last list: the block goes at the end.
    path = tree / f"{A}/data-asset.yaml"
    path.write_text(path.read_text().rstrip("\n") + "\n" + _block("data-asset.yaml"))

    # The calendar: a collection entry before the datasets' heading comment,
    # a dataset entry at the end (the datasets list is last).
    path = tree / f"{A}/calendar.yaml"
    lines = path.read_text().splitlines(keepends=True)
    heading = next(i for i, line in enumerate(lines) if "EACH DATASET'S PARTICIPATION" in line) - 1
    while not lines[heading - 1].strip():
        heading -= 1
    lines = _insert(lines, heading, _block("calendar-collections.yaml"))
    path.write_text("".join(lines).rstrip("\n") + "\n" + _block("calendar-datasets.yaml"))

    # Presentation: an agency before `collections:`, a collection at the end
    # of `collections:` - before the comment heading the next key, since
    # `collections:` is no longer the file's last list.
    path = tree / f"{A}/presentation.yaml"
    lines = path.read_text().splitlines(keepends=True)
    lines = _insert(lines, _index(lines, "collections:"), _block("presentation-agencies.yaml"))
    after = _index(lines, "collections:") + 1
    end = next((i for i in range(after, len(lines))
                if lines[i].strip() and not lines[i].startswith(" ")), len(lines))
    while end > after and (not lines[end - 1].strip() or lines[end - 1].startswith("#")):
        end -= 1
    path.write_text("".join(_insert(lines, end, _block("presentation-collections.yaml"))))

    for rel in EDITED:  # each still parses, and now names the fake
        assert COLLECTION_ID in (tree / rel).read_text(), rel
        yaml.safe_load((tree / rel).read_text())
    return tree


def additions_only(tree: Path, root: Path = ROOT) -> list[str]:
    """Criterion 3: every way the copy at `tree` differs from the tracked
    working tree other than by additions in the allowed places. Empty means
    the copy is the tree plus a collection's own files and its inserts."""
    problems = []
    tracked = tracked_files(root)
    assert tracked, "git tracks no files here - the comparison would prove nothing"
    for rel in tracked:
        here, there = root / rel, tree / rel
        if not there.is_file():
            problems.append(f"{rel} is missing from the copy")
        elif here.read_bytes() != there.read_bytes():
            if rel not in EDITED:
                problems.append(f"{rel} differs")
                continue
            before = here.read_text().splitlines()
            after = there.read_text().splitlines()
            for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, before, after,
                                                              autojunk=False).get_opcodes():
                if op != "equal" and op != "insert":
                    problems.append(f"{rel}: lines {a1 + 1}-{a2} were {op}d, not only added to")
    known = set(tracked)
    for path in tree.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(tree))
        if rel in known:
            continue
        if not rel.startswith(OWN_PATHS):
            problems.append(f"{rel} is new and outside a collection's own places")
    return problems
