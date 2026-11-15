"""`mothman check`'s providers gate (REQ-GEN-246 criterion 3): no two
generator providers' declared seed ranges overlap, and every seed each one
derives lies inside its own (criterion 2, checked here as well as before
each generation, so a bad schedule fails at review rather than at the
first regeneration).

Two collections drawing the same seeds would draw the same rows - a
duplicated history that reads as a real one. A range declared once and
checked mechanically is what makes REQ-GEN-232's disjoint Emergency
Department seeds a check rather than a promise.

READS DECLARATIONS ONLY: no provider module imports pandas or numpy at
module level (criterion 7), so this gate costs no tool import.

AND WHAT A PROVIDER IMPORTS (REQ-GEN-370 criterion 5): shared code and the
standard library only, never another provider, an adapter or anything under
assets/ - read from each provider's syntax tree, before any is loaded. The
imports gate (REQ-TEST-384) cannot say this: it sides every provider with the
generator, so one provider importing another is inside one side there.
"""
from __future__ import annotations

import ast
import sys

from pathlib import Path

#: Module stems in a providers or adapters folder that are not one
#: collection's - the shared base each package keeps.
_SHARED_STEMS = ("__init__", "base")


def _shown(path: Path) -> str:
    """`path` from the repository root - or in full, outside it."""
    root = Path(__file__).resolve().parent.parent
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


def _stems(folder: Path) -> set[str]:
    return {p.stem for p in Path(folder).glob("*.py") if p.stem not in _SHARED_STEMS}


def _every_assets_modules() -> tuple[set[str], set[str]]:
    """(adapter stems, provider stems) across every asset - a provider of one
    asset reaching another asset's module is refused as surely as a
    sibling."""
    from qa_tools.common import assets

    adapters, providers = set(), set()
    for asset in assets.every():
        adapters |= _stems(asset.adapters)
        providers |= _stems(asset.providers)
    return adapters, providers


def _reaches_another_module(name: str, adapters: set[str],
                            providers: set[str]) -> bool:
    """Whether a dotted name a provider imports is a provider (another, or
    itself by its package path), an adapter or anything under assets/."""
    parts = name.split(".")
    if parts[0] == "assets" or parts[0].startswith(("mothman_adapter_", "mothman_provider_")):
        return True
    if parts[:2] == ["qa_tools", "collections"] and len(parts) > 2:
        return parts[2] in adapters
    if parts[:2] == ["generator", "collections"] and len(parts) > 2:
        return parts[2] in providers
    return False


#: The resolver's loads by path - called on the resolver module however it is
#: named locally, so json.load and a provider's own helpers stay allowed.
_PATH_LOADS = frozenset({"load", "module_file"})


def _resolver_names(tree: ast.AST) -> set[str]:
    """The local names a provider binds the resolver module
    (qa_tools.common.assets) to."""
    names = {"assets"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "qa_tools.common":
            names |= {a.asname or a.name for a in node.names if a.name == "assets"}
        elif isinstance(node, ast.Import):
            names |= {a.asname for a in node.names
                      if a.name == "qa_tools.common.assets" and a.asname}
    return names


def _loads_by_path_or_name(node, resolver: set[str]) -> bool:
    """Whether a node imports importlib, calls __import__, or calls the
    resolver's load by path."""
    if isinstance(node, ast.Import):
        return any(a.name.split(".")[0] == "importlib" for a in node.names)
    if isinstance(node, ast.ImportFrom):
        return node.level == 0 and (node.module or "").split(".")[0] == "importlib"
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id == "__import__"
        return (isinstance(func, ast.Attribute) and func.attr in _PATH_LOADS
                and isinstance(func.value, ast.Name) and func.value.id in resolver)
    return False


def provider_import_problems(package: Path | None = None) -> list[str]:
    """Every statement in the selected asset's providers - or `package`'s -
    that imports another provider, an adapter or anything under assets/, a
    relative import (in a module loaded by path it can only mean a file
    beside it in an asset folder), or loads a module by path or by name
    (REQ-GEN-370 criterion 5), naming the file and the statement. Read from
    each file's syntax tree, at module and function level and under
    TYPE_CHECKING alike, so a provider that would fail to import is still
    read.

    A LOOKUP THROUGH THE SHARED REGISTRY IS NOT REFUSED (PROVISIONAL,
    REQ-GEN-370's decisions): generator.collections.for_dataset is how
    Linkage Products reads the collections it declares in depends_on
    (REQ-GEN-334 criterion 6, held in order by order_problems below), and
    reaching an adapter through qa_tools.collections needs an import the
    imports gate refuses (REQ-TEST-384)."""
    from qa_tools.common import assets

    package = Path(package) if package is not None else assets.selected().providers
    adapters, providers = _every_assets_modules()
    problems = []
    for path in sorted(package.glob("*.py")):
        if path.stem in _SHARED_STEMS:
            continue
        text = path.read_text()
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            problems.append(f"{_shown(path)} cannot be read: {exc}")
            continue
        resolver = _resolver_names(tree)
        for node in ast.walk(tree):
            if _loads_by_path_or_name(node, resolver):
                problems.append(
                    f"{_shown(path)}: `{ast.get_source_segment(text, node)}` - a provider "
                    f"loads no module by path or by name: no load through the resolver, no "
                    f"importlib, no __import__ (REQ-GEN-370 criterion 5)")
                continue
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                reaches = True
            elif isinstance(node, ast.Import):
                reaches = any(_reaches_another_module(a.name, adapters, providers)
                              for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                reaches = any(_reaches_another_module(n, adapters, providers)
                              for n in names)
            else:
                continue
            if reaches:
                problems.append(
                    f"{_shown(path)}: `{ast.get_source_segment(text, node)}` - a provider "
                    f"imports only shared code and the standard library, never another "
                    f"provider, an adapter or anything under assets/ (REQ-GEN-370 "
                    f"criterion 5)")
    return problems


def declaration_problems() -> list[str]:
    """What a provider declares that only a new collection would trip over
    (post-build-review #232): a provider filed under another collection's
    module, a dataset its collection does not own, a target trial on a
    multi-table collection (the trial tries one table's targets, and only a
    one-table collection's commands can run it), a lever set nothing knows,
    or one lever set declared by two collections (each set reads one
    dataset's rules)."""
    from generator import collections
    from generator.collections.base import CLIENT_POSTCODES, NULL_RATE
    from qa_tools import collections as registry
    from qa_tools.common import assets

    out: list[str] = []
    levers: dict[str, str] = {}
    for coll in registry.all_collections():
        try:
            provider = collections.provider(coll.id)
        except collections.NoProviderError:
            continue
        # WHERE THE PROVIDER IS, since the asset split (post-build-review #332).
        where = _shown(assets.selected().providers / f"{coll.module_name}.py")
        if provider.collection_id != coll.id:
            out.append(f"{where} names collection {provider.collection_id!r}, not {coll.id!r}")
            continue
        owned = [d.dataset_id for d in coll.datasets]
        for field in ("dataset_id", "amber_dataset"):
            value = getattr(provider, field)
            if value is not None and value not in owned:
                out.append(f"{where}'s {field}: dataset {value!r} is not one of {coll.id}'s "
                           f"({', '.join(owned)})")
        # A TRIAL OF A COLLECTION OF SEVERAL DATASETS IS NO LONGER REFUSED
        # (REQ-GEN-298 criterion 10): each tried supply names its own dataset
        # and file, and is tried against its own table. What a trial still
        # needs is somewhere each supply's verdict is compared.
        if provider.target_trial and not provider.target_datasets:
            out.append(f"{coll.id} declares a target trial and no target_datasets - a trial "
                       f"compares each supply in its own dataset, so it must name them")
        if provider.target_levers is not None:
            if provider.target_levers not in (NULL_RATE, CLIENT_POSTCODES):
                out.append(f"{where} declares lever set {provider.target_levers!r}, which "
                           f"generator/targeting.py does not know")
            elif provider.target_levers in levers:
                out.append(f"lever set {provider.target_levers!r} is declared by both "
                           f"{levers[provider.target_levers]} and {coll.id} - each set reads "
                           f"one dataset's rules")
            else:
                levers[provider.target_levers] = coll.id
    return out


def orphan_problems(package: Path | None = None) -> list[str]:
    """A provider module naming no declared collection - a misspelt one would
    otherwise leave its collection silently ungenerated.

    In the selected asset's own providers folder unless told another (the
    asset split: providers live in assets/<asset>/synthetic/collections/;
    generator/collections/ holds only the shared base), each named by its
    path from the repository root - or in full, outside it."""
    from qa_tools import collections as registry
    from qa_tools.common import assets

    package = Path(package) if package is not None else assets.selected().providers
    declared = {c.module_name for c in registry.all_collections()}
    return [f"{_shown(p)} names no declared collection"
            for p in sorted(package.glob("*.py"))
            if p.stem not in ("__init__", "base") and p.stem not in declared]


def _unimportable() -> list[tuple[str, ImportError]]:
    """(path shown, error) for each declared collection's provider that
    cannot be imported (post-build-review #336: it used to raise out of the
    gate as a traceback)."""
    from generator import collections
    from qa_tools import collections as registry
    from qa_tools.common import assets

    out = []
    for coll in registry.all_collections():
        try:
            collections.provider(coll.id)
        except collections.NoProviderError:
            continue
        except ImportError as exc:
            out.append((_shown(assets.selected().providers / f"{coll.module_name}.py"), exc))
    return out


def problems() -> list[str]:
    from generator import collections

    imports = provider_import_problems()
    broken = _unimportable()
    if broken:
        # REPORTED, NOT RAISED, and nothing else is asked: every other check
        # loads every provider. A provider whose forbidden import is already
        # named is not named twice - that import is most often why.
        return imports + [f"{where} cannot be imported: {exc}" for where, exc in broken
                          if not any(p.startswith(f"{where}:") for p in imports)
                          ] + orphan_problems()
    found = collections.providers()
    out = imports + collections.seed_range_problems(found) + collections.order_problems(found)
    for provider in found:
        try:
            provider.check_seeds()
        except collections.base.SeedOutOfRange as exc:
            out.append(str(exc))
    from generator import synthetic_inputs

    # REQ-QAC-294 criterion 3: the generator-only placing configuration agrees
    # with the contracts it names.
    return out + declaration_problems() + orphan_problems() + synthetic_inputs.problems()


def main() -> int:
    from generator import collections

    found = problems()
    if found:
        for p in found:
            print(f"providers: {p}", file=sys.stderr)
        return 1
    print(f"providers OK - {len(collections.providers())} generator provider(s), seed ranges "
          f"disjoint and every derived seed inside its own")
    return 0


if __name__ == "__main__":
    sys.exit(main())
