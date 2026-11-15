"""`mothman check`'s layout gate: the repository's shape around its asset
folders, read from the working tree alone - no asset selected, no database.

THE TOP OF assets/ (REQ-PIPE-364 criterion 5): only environments.yaml, the
one configuration file the same for every asset, and asset folders, each
holding a data-asset.yaml. A stray file, or a folder that is no asset - a
half-made one, a hidden or underscored one the resolver's discovery passes
over - fails, named, so a third asset is picked up by discovery or refused
here and never silently ignored (REQ-PIPE-342's SCALE NFR). The move map that
criterion once allowed for one push is gone (REQ-TEST-366 criterion 3).

THE SHARED TREE (REQ-PIPE-342 criterion 10): no per-collection file in the
shared code. qa_tools/collections/ and generator/collections/ hold only their
shared base modules - a collection's adapter is in assets/<asset>/collections/
and its provider in assets/<asset>/synthetic/collections/ - and dbt_shared/
only the shared macros and generic tests (macros/ and tests/generic/, each
file defining a macro or a generic test). A model, a singular test or
a schema file there is one collection's, and so is a shared file that names a
model through ref(): a model belongs to the collection whose folder defines
it.

Repository-wide, so it runs once rather than once per asset.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: The only files at the top of assets/ (REQ-PIPE-342 criterion 2).
ASSETS_TOP_FILES = ("environments.yaml",)

#: Each shared code tree and the only modules it may hold.
SHARED_CODE = {
    "qa_tools/collections": ("__init__.py", "base.py"),
    "generator/collections": ("__init__.py", "base.py"),
}

#: A macro or a generic test definition - dbt reads either from both of
#: dbt_shared/'s folders (macro-paths and test-paths), as matches_regex.sql, a
#: generic test filed under macros/, shows.
_DEFINES = re.compile(r"{%-?\s*(?:macro|test)\s+\w+\s*\(")
_REF = re.compile(r"""\bref\(\s*['"]([A-Za-z0-9_]+)['"]""")


def _visible(path: Path, under: Path) -> bool:
    return not any(p == "__pycache__" for p in path.relative_to(under).parts)


def assets_top_problems(root: Path = ROOT) -> list[str]:
    top = Path(root) / "assets"
    if not top.is_dir():
        return ["assets/ is missing - there is no asset folder to check"]
    out = []
    for entry in sorted(top.iterdir()):
        if entry.is_dir():
            if not (entry / "data-asset.yaml").is_file():
                out.append(f"assets/{entry.name}/ holds no data-asset.yaml, so it is no asset - "
                           f"make it one, or remove it")
        elif entry.name not in ASSETS_TOP_FILES:
            out.append(f"assets/{entry.name} sits at the top of assets/, where only "
                       f"{', '.join(ASSETS_TOP_FILES)} and the asset folders belong")
    return out


def shared_tree_problems(root: Path = ROOT) -> list[str]:
    from qa_tools.common import assets

    root = Path(root)
    out = []
    for tree, allowed in SHARED_CODE.items():
        base = root / tree
        for path in sorted(base.rglob("*")) if base.is_dir() else []:
            if not path.is_file() or not _visible(path, base):
                continue
            rel = path.relative_to(root).as_posix()
            if path.parent == base and path.name in allowed:
                continue
            out.append(f"{rel} is in the shared code tree {tree}/, which holds only its "
                       f"shared base modules ({', '.join(allowed)}) - a collection's adapter "
                       f"belongs in assets/<asset>/collections/, its provider in "
                       f"assets/<asset>/synthetic/collections/")
    dbt = root / assets.DBT_SHARED
    parts = (dbt / "macros", dbt / "tests" / "generic")
    for path in sorted(dbt.rglob("*")) if dbt.is_dir() else []:
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        part = next((p for p in parts if path.is_relative_to(p)), None)
        if part is None or path.suffix != ".sql":
            out.append(f"{rel} is in {assets.DBT_SHARED}/, which holds only the shared macros "
                       f"({assets.DBT_SHARED}/macros/*.sql) and generic tests "
                       f"({assets.DBT_SHARED}/tests/generic/*.sql) - a collection's models, "
                       f"singular tests and schema files belong in its asset's dbt/ project")
            continue
        text = path.read_text()
        if not _DEFINES.search(text):
            out.append(f"{rel} defines no macro or generic test, so it is no shared one - a "
                       f"collection's singular test belongs in its asset's dbt/tests/<collection>/")
        for model in _REF.findall(text):
            out.append(f"{rel} names the model {model!r} through ref() - a model is one "
                       f"collection's, so shared dbt code takes it as an argument")
    return out


def main() -> int:
    problems = assets_top_problems() + shared_tree_problems()
    if problems:
        for p in problems:
            print(f"  {p}")
        print(f"layout gate FAILED - {len(problems)} problem(s).")
        return 1
    print("layout OK - only environments.yaml and asset folders at the top of assets/, and "
          "no collection's file in the shared code tree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
