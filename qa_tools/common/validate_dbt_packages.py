"""`mothman check`'s dbt packages gate (REQ-TEST-388, signed by Keith 2026-11-14).

SAME PACKAGES, KEPT PER PROJECT, GATED (SPLIT D2, SETTLED by Keith
2026-11-03). dbt reads packages.yml and package-lock.yml from each project,
so every asset's dbt project (assets/<asset>/dbt/) keeps its own, and
`mothman env dbt-deps` installs each asset's from them (REQ-QAC-368). What
holds them together is this gate: it fails when any two asset folders'
packages.yml, or their package-lock.yml, differ once parsed as YAML - a
comment is not a package - naming both assets, the file and the first entry
that differs, so that an upgrade cannot land in one asset and be forgotten in
the other. The lock file is compared too: dbt's own package-lock.yml is what
'installed' means (REQ-QAC-368 decision 5 as changed by C6).

REPOSITORY-WIDE: it compares across assets, so it runs once whatever
MOTHMAN_ASSET says. It reads committed files only - no database, no asset
selection, no dbt Hub or GitHub.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent

#: The files dbt reads from each project (qa_tools/common/dbt_common.py names
#: the lock file too; it is not imported, since it opens the database module).
FILES = ("packages.yml", "package-lock.yml")
NEXT_STEP = "make both match, then run `mothman env dbt-deps` for each asset"
ABSENT = "(absent)"


def asset_projects(root: Path = ROOT) -> dict[str, Path]:
    """{asset name: where its dbt project is} for every asset folder under
    assets/ - one holding a data-asset.yaml or a dbt/ - by name. An asset
    folder with no dbt/ is listed too, so its missing files are a difference
    (the post-build critic, 2026-11-15) rather than an asset silently skipped."""
    base = Path(root) / "assets"
    if not base.is_dir():
        return {}
    return {p.name: p / "dbt" for p in sorted(base.iterdir())
            if p.is_dir() and not p.name.startswith((".", "_"))
            and ((p / "dbt").is_dir() or (p / "data-asset.yaml").is_file())}


def _read(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else ABSENT


def first_difference(a, b, where: str = "") -> tuple[str, object, object] | None:
    """(the path of the first entry that differs, its value in a, in b), or
    None where the two parsed documents are equal."""
    if isinstance(a, dict) and isinstance(b, dict):
        for key in list(a) + [k for k in b if k not in a]:
            here = f"{where}.{key}" if where else str(key)
            if key not in a or key not in b:
                return here, a.get(key, ABSENT), b.get(key, ABSENT)
            found = first_difference(a[key], b[key], here)
            if found:
                return found
        return None
    if isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            here = f"{where}[{i}]"
            if i >= len(a) or i >= len(b):
                return here, a[i] if i < len(a) else ABSENT, b[i] if i < len(b) else ABSENT
            found = first_difference(a[i], b[i], here)
            if found:
                return found
        return None
    return None if a == b else (where or "(the whole file)", a, b)


def problems(root: Path = ROOT) -> list[str]:
    projects = asset_projects(root)
    names = list(projects)
    out = []
    for name in names[1:]:
        first = names[0]
        for file in FILES:
            left_doc, right_doc = _read(projects[first] / file), _read(projects[name] / file)
            if (left_doc == ABSENT) != (right_doc == ABSENT):
                lacking, having = (first, name) if left_doc == ABSENT else (name, first)
                out.append(f"dbt packages: asset {lacking!r} has no dbt/{file}, which "
                           f"{having!r} has - {NEXT_STEP}")
                continue
            found = first_difference(left_doc, right_doc)
            if found:
                where, left, right = found
                out.append(f"dbt packages: assets {first!r} and {name!r} differ in {file} at "
                           f"{where} ({first}: {left!r}, {name}: {right!r}) - {NEXT_STEP}")
    return out


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    root = Path(root or ROOT)
    found = problems(root)
    for line in found:
        print(line)
    if found:
        return 1
    names = list(asset_projects(root))
    if not names:
        print("dbt packages: no asset folder holds a dbt project - nothing to compare")
    elif len(names) == 1:
        print(f"dbt packages: compared one asset ({names[0]}) - there is no other asset to "
              f"differ from")
    else:
        print(f"dbt packages: {', '.join(FILES)} agree across {len(names)} assets "
              f"({', '.join(names)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
