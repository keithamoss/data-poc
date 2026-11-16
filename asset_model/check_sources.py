"""Where every check is defined, and the checks read from the WORKING TREE
(REQ-QAC-241 criteria 7, 8 and 10; moved into asset_model/ by REQ-PIPE-380
criterion 12, 380 Q1 (a) SETTLED by Keith 2026-11-14).

WHY HERE. The generator plans what the checks will find (check_bands'
catalogue) from the same check metadata the lifecycle gate compares, so both
read the checks through this one reader rather than a second parser.

THE OTHER HALF IS qa_tools/common/validate_check_lifecycle.py, which reads
the same files AT A GIT REF to compare them with the working tree. The cut
sits at git: this module reads committed configuration as it stands on disk
and runs no git (criterion 8), and the ref read hands its file contents to
the same functions here (sources, dbt_definitions).
"""
from __future__ import annotations

import re
from pathlib import Path

from asset_model import check_lifecycle as cl
from asset_model import collections, config_yaml

ROOT = Path(__file__).resolve().parent.parent

#: Which parser reads each tool's check files.
PARSERS = {"dbt": cl.parse_dbt_check_metadata, "soda": cl.parse_soda_check_metadata,
           "contract": cl.parse_contract_check_metadata}


def sources(asset_text: str | None) -> tuple[list[tuple[str, object]], list[str]]:
    """Every file the checks are defined in - `[(path, parser)]` for the
    YAML tools and `[path]` for Evidently - derived from a data-asset.yaml's
    own text (REQ-QAC-241 criteria 7 and 8): each collection's contract,
    Soda, Evidently and dbt schema files with their retired siblings, plus
    the file checks. A new collection's files are found without a line here.

    Grouped by tool in a fixed order - dbt, Soda, contracts, file checks,
    Evidently - the order the hand-written list had, so nothing that lists
    checks moves."""
    colls = collections.collections_in(config_yaml.parse(asset_text or "") or {})
    yaml_sources = [(c.dbt_schema, PARSERS["dbt"]) for c in colls]
    yaml_sources += [(c.dbt_retired_schema, PARSERS["dbt"]) for c in colls]
    for kind in ("soda", "contract"):
        for c in colls:
            yaml_sources += [(c.check_file(kind), PARSERS[kind]),
                             (c.check_file(kind, retired=True), PARSERS[kind])]
    yaml_sources.append((collections.file_checks(), cl.parse_file_check_metadata))
    evidently = [f for c in colls for f in (c.check_file("evidently"),
                                             c.check_file("evidently", retired=True))]
    return yaml_sources, evidently


#: Where the project's own dbt SQL lives (REQ-QAC-223 criterion 2): macros
#: and custom generic tests - dbt_shared/, read by every asset's project
#: (REQ-QAC-368) - and singular tests, every collection's folder under the
#: selected asset's project's tests/ (asked at call time by the caller).
#: Package macros (dbt_packages/) and models are deliberately NOT covered.
MACRO_HEAD = re.compile(r"{%-?\s*(macro|test)\s+(\w+)\s*\(")


def sql_files_in(rel_dir: str, root: Path = ROOT) -> list[str]:
    """The .sql files anywhere under `rel_dir` in the working tree.
    Recursive because dbt is: it reads every folder under its macro-paths and
    test-paths, so a macro filed in a subfolder still backs checks
    (post-build-review #182 - it used to be invisible here)."""
    d = Path(root) / rel_dir
    return sorted(f"{rel_dir}/{p.relative_to(d).as_posix()}" for p in d.rglob("*.sql")) \
        if d.is_dir() else []


def dbt_definitions(read, files_in, singular_dir: str) -> "cl.DbtDefinition":
    """What `parse_dbt_check_metadata(definition=...)` reads: the project SQL
    behind each dbt check (REQ-QAC-223 criterion 2), from `read(rel)` (a
    file's text or None) and `files_in(rel_dir)` - the working tree's, or a
    git ref's, as the caller reads them.

    The project's macros are scanned ONCE (NFR: not once per check) into
    {name: (file, text)}; a `{% test x(` names test type `x`, a
    `{% macro test_x(` does too. A singular test is its own SQL file plus
    every project macro whose name appears in it, followed transitively. The
    scan is lexical and errs towards including too much, which can only ask
    for a changelog entry that was not strictly needed."""
    macros: dict[str, tuple[str, str]] = {}
    for rel_dir in collections.SHARED_DBT_DIRS:
        for rel in files_in(rel_dir):
            text = read(rel) or ""
            for kind, name in MACRO_HEAD.findall(text):
                macros[name] = (rel, text)
                if kind == "macro" and name.startswith("test_"):
                    macros.setdefault(name[len("test_"):], (rel, text))

    singular = [f for f in files_in(singular_dir)
                if not f.startswith(f"{singular_dir}/generic/")]

    def _with_used_macros(files: list[str], texts: list[str]) -> tuple[str, tuple[str, ...]]:
        seen = set(files)
        i = 0
        while i < len(texts):
            for name, (rel, text) in macros.items():
                if rel not in seen and re.search(rf"\b{re.escape(name)}\s*\(", texts[i]):
                    seen.add(rel)
                    files.append(rel)
                    texts.append(text)
            i += 1
        # Each file is named by its FILE NAME, not its path, so moving a test
        # into a collection's folder is not a change to what it does
        # (REQ-QAC-241's build question): dbt names a singular test by its
        # file name too, and the collections gate keeps those unique.
        return "\n".join(f"-- {f.rsplit('/', 1)[-1]}\n{t}" for f, t in zip(files, texts)), tuple(files)

    def definition(kind: str, name: str):
        if kind == "singular":
            # dbt names a singular test by its file, in any folder under
            # tests/ - generic tests (tests/generic/) are macros, not these.
            rel = next((f for f in singular if f.rsplit("/", 1)[-1] == f"{name}.sql"), None)
            text = read(rel) if rel else None
            if text is None:
                return None, ()
            return _with_used_macros([rel], [text])
        if "." in name or name not in macros:  # dbt's own or a package's
            return None, ()
        rel, text = macros[name]
        return _with_used_macros([rel], [text])

    return definition


def _read_working(rel: str, root: Path) -> str | None:
    path = Path(root) / rel
    return config_yaml.read(path) if path.is_file() else None


def collect_working_tree(yaml_sources, evidently, root: Path = ROOT) -> list[cl.CheckMetadata]:
    """Every check the given sources define, read from the working tree
    under `root`. A source path that does not exist reads as "no checks from
    it" - each tool's own `-retired` sibling is a genuinely optional source
    until a project's first check is retired."""
    from asset_model import assets

    definition = dbt_definitions(lambda rel: _read_working(rel, root),
                                 lambda rel_dir: sql_files_in(rel_dir, root),
                                 f"{assets.dbt_on_disk()}/tests")
    checks: list[cl.CheckMetadata] = []
    for rel_path, parser in yaml_sources:
        if not (Path(root) / rel_path).exists():
            continue
        kwargs = {"definition": definition} if parser is cl.parse_dbt_check_metadata else {}
        checks.extend(parser(Path(root) / rel_path, **kwargs))
    for rel_path in evidently:
        source = _read_working(rel_path, root)
        if source is None:
            continue
        checks.extend(cl.parse_evidently_check_metadata(
            cl.evidently_checks_from_text(source, rel_path), source=rel_path))
    return checks


def working_tree_checks() -> list[cl.CheckMetadata]:
    """Every check defined in the working tree, for the selected asset -
    what the lifecycle gate reads as its "new" side."""
    from asset_model import hierarchy

    return collect_working_tree(*sources(config_yaml.read(hierarchy.data_asset_yaml())), ROOT)
