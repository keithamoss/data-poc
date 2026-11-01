"""Which asset a test acts for, read from the registry (the asset split).

A test that does not say which asset it acts for (`@pytest.mark.asset`) acts
for the one whose collections it touches. "Touches" is read from text, never
from a hand-kept list of modules: each asset's own data-asset.yaml gives the
ids that name its agencies, collections, datasets, tables, shorts, run
prefixes and contract stems, and the asset is the one whose ids the test's
own source, its parameters, the module helpers and constants it uses and the
fixtures it requests name. A test naming only one asset's ids acts for that
asset; one naming none, or both, acts for the suite's own (tests/conftest.py).

Test-only: nothing that ships reads an asset it was not told to.
"""
from __future__ import annotations

import functools
import inspect
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

#: Shorts and run prefixes are too short or too common to find as words
#: ("ed", "run_"), so a short counts only quoted, and a run prefix only when
#: it is longer than the bare "run_".
_EDGE_L, _EDGE_R = r"(?<![A-Za-z0-9-])", r"(?![A-Za-z0-9-])"


@functools.lru_cache(maxsize=1)
def _patterns() -> dict[str, re.Pattern]:
    out = {}
    root = ROOT / "assets"
    for folder in sorted(p for p in root.iterdir() if (p / "data-asset.yaml").is_file()):
        doc = yaml.safe_load((folder / "data-asset.yaml").read_text()) or {}
        words, quoted, prefixes = set(), set(), set()
        for agency in (doc.get("hierarchy") or {}).get("agencies") or []:
            words.add(agency["id"])
            quoted.add(str(agency.get("short", "")))
            for c in agency.get("collections") or []:
                words |= {c["id"], c["id"].replace("-", "_")}
                quoted.add(str(c.get("short", "")))
                if len(str(c.get("run_prefix", ""))) > len("run_"):
                    prefixes.add(c["run_prefix"])
                words.add(str(c.get("contract", "")).rsplit("/", 1)[-1].removesuffix("-contract.yaml"))
                for d in c.get("datasets") or []:
                    words |= {d["id"], d["table"]}
        words.discard("")
        quoted.discard("")
        alternatives = [_EDGE_L + "(?:" + "|".join(map(re.escape, sorted(words, key=len, reverse=True))) + ")" + _EDGE_R]
        if quoted:
            alternatives.append(r"""["'](?:""" + "|".join(map(re.escape, sorted(quoted))) + r""")["']""")
        if prefixes:
            alternatives.append(_EDGE_L + "(?:" + "|".join(map(re.escape, sorted(prefixes))) + ")")
        out[folder.name] = re.compile("|".join(alternatives))
    return out


def named(text: str) -> set[str]:
    """The assets whose ids `text` names."""
    return {asset for asset, pattern in _patterns().items() if pattern.search(text)}


def _source(obj) -> str:
    try:
        return inspect.getsource(obj)
    except (OSError, TypeError):
        return ""


def _helpers(func, module, seen: set) -> str:
    """The source of the module's own helpers and the values of its
    constants that `func` names - one level at a time, each once."""
    out = []
    code = getattr(func, "__code__", None)
    if code is None or module is None:
        return ""
    names = set(code.co_names)
    for const in code.co_consts:
        if hasattr(const, "co_names"):
            names |= set(const.co_names)
    for name in names:
        if name in seen or not hasattr(module, name):
            continue
        seen.add(name)
        value = getattr(module, name)
        if inspect.isfunction(value) or inspect.isclass(value):
            if getattr(value, "__module__", None) == module.__name__:
                out.append(_source(value))
                if inspect.isfunction(value):
                    out.append(_helpers(value, module, seen))
        elif isinstance(value, (str, tuple, list, dict, frozenset, set)):
            out.append(repr(value))
    return "\n".join(out)


def text_of(item) -> str:
    """Everything a test names: its own source, its class's, its id and
    parameters, the module helpers and constants it uses and the source of
    the fixtures it requests (other than the conftest's own)."""
    func = getattr(item, "function", None)
    module = sys.modules.get(getattr(func, "__module__", ""), None)
    parts = [item.name, _source(func)]
    if getattr(item, "cls", None) is not None:
        parts.append(_source(item.cls))
    callspec = getattr(item, "callspec", None)
    if callspec is not None:
        parts.append(repr(callspec.params))
    seen: set = set()
    parts.append(_helpers(func, module, seen))
    info = getattr(item, "_fixtureinfo", None)
    for name in getattr(item, "fixturenames", ()):
        for fixturedef in (getattr(info, "name2fixturedefs", {}) or {}).get(name, ()):
            fixture_func = fixturedef.func
            if Path(inspect.getsourcefile(fixture_func) or "").name == "conftest.py":
                continue
            parts.append(_source(fixture_func))
            parts.append(_helpers(fixture_func, sys.modules.get(fixture_func.__module__), seen))
    return "\n".join(p for p in parts if p)


def asset_of_item(item, default: str) -> str:
    """The only asset a test names, or `default`."""
    found = named(text_of(item))
    return found.pop() if len(found) == 1 else default


def module_level_text(path: Path) -> str:
    """A module's statements outside every function and class body - what
    runs when it is imported."""
    import ast

    try:
        source = path.read_text()
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return ""
    lines = source.splitlines()
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # A class body's own statements run at import too.
            if isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        out.append("\n".join(lines[stmt.lineno - 1:stmt.end_lineno]))
            continue
        out.append("\n".join(lines[node.lineno - 1:node.end_lineno]))
    return "\n".join(out)
