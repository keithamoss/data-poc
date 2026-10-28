"""No process-long cache under qa_tools/ or pipeline/ that nobody reviewed
(REQ-PIPE-254 criteria 16 to 18, signed by Keith 2026-10-24).

WHY A GATE. Nine values built from configuration files sat behind
functools.lru_cache or functools.cache, one per process or one per path, so
an edited or swapped file was answered for what it used to say, and a test
that swapped one had to know every cache to clear. plans/post-build-review.md
#217 is the incident of the list somebody had to keep complete: the tests'
helper cleared the hierarchy and not the registry built from it. Those nine
are keyed on their files' content now (qa_tools/common/config_yaml.Built), and
this gate is what stops a tenth appearing: a rule in a docstring is the same
list, kept by nobody.

WHAT IT FAILS. A function under qa_tools/ or pipeline/ carrying lru_cache or
cache from functools - by any spelling of the import: `functools.lru_cache`,
`import functools as ft` then `ft.cache`, `from functools import cache`, or
an alias of either - that is not on ALLOWLIST below. It reads only committed
source, with `ast`, so it needs no database and no import of what it scans.
An allowlist entry that names no cache fails too, so the list cannot outlive
what it excuses.

WHAT IT DOES NOT. functools.cached_property is not in it (Keith, at
sign-off): it holds a value per instance for that instance's life, so a
swapped file is seen by the next instance.

AN ALLOWLIST ENTRY IS A DELIBERATE, REVIEWED ACT, with its reason beside it.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: Where the gate looks, relative to the repository root.
SCANNED = ("qa_tools", "pipeline")

#: The functools names that hold a value for the life of the process.
CACHING = frozenset({"lru_cache", "cache"})

#: (file relative to the root, function name) -> why it is safe. Exactly the
#: caches REQ-PIPE-254 left unkeyed (criterion 17); none it keyed.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("qa_tools/common/datacontract_common.py", "_derived"):
        "keyed on the rule's own qualityDefinition text, so an edited rule is a "
        "new key (REQ-PIPE-192)",
    ("qa_tools/common/validate_schedule.py", "_content_at"):
        "keyed on a git ref, whose content never changes, and cleared at the "
        "start of each validate()",
    ("qa_tools/common/validate_requirements.py", "_parsed"):
        "a short-lived validator off the run path, keyed on each file's mtime "
        "and size as well as its path (settled by REQ-TEST-253)",
    ("qa_tools/common/validate_requirements.py", "_sprint_numbers"):
        "a short-lived validator off the run path, reading the delivery plan "
        "once per run (settled by REQ-TEST-253)",
}


def _names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """(names bound to the functools module, names bound to lru_cache or
    cache themselves) by this file's own imports."""
    modules, direct = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "functools":
                    modules.add(alias.asname or "functools")
        elif isinstance(node, ast.ImportFrom) and node.module == "functools":
            for alias in node.names:
                if alias.name in CACHING:
                    direct.add(alias.asname or alias.name)
    return modules, direct


def _is_caching(expr: ast.AST, modules: set[str], direct: set[str]) -> bool:
    """Whether a decorator, or the function a call is made of, is lru_cache or
    cache: bare (`@cache`), called (`@lru_cache(maxsize=4)`) or through the
    module (`@functools.cache`)."""
    if isinstance(expr, ast.Call):
        expr = expr.func
    if isinstance(expr, ast.Name):
        return expr.id in direct
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        return expr.value.id in modules and expr.attr in CACHING
    return False


def caches_in(path: Path) -> list[tuple[str, int]]:
    """(function name, line) for every cached function in one file -
    decorated, or wrapped by assignment (`f = functools.cache(g)`)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules, direct = _names(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_is_caching(d, modules, direct) for d in node.decorator_list):
                found.append((node.name, node.lineno))
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            wrapped = (_is_caching(call.func, modules, direct)
                       or (isinstance(call.func, ast.Call)
                           and _is_caching(call.func.func, modules, direct)))
            if wrapped:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        found.append((target.id, node.lineno))
    return found


def scan(root: Path = ROOT) -> list[tuple[str, str, int]]:
    """(file relative to root, function, line) for every cache under the
    scanned trees."""
    out = []
    for top in SCANNED:
        for path in sorted((Path(root) / top).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            out.extend((rel, name, line) for name, line in caches_in(path))
    return out


def problems(root: Path = ROOT, allowlist: dict | None = None) -> list[str]:
    allowlist = ALLOWLIST if allowlist is None else allowlist
    found = scan(root)
    out = [f"{rel}:{line}: {name}() carries functools.lru_cache or functools.cache and is "
           f"not on qa_tools/common/validate_caches.py's ALLOWLIST. A value held for the "
           f"process answers an edited or swapped file for what it used to say - key it on "
           f"the file's content with config_yaml.Built (REQ-PIPE-254), or allowlist it with "
           f"the reason it is safe."
           for rel, name, line in found if (rel, name) not in allowlist]
    present = {(rel, name) for rel, name, _ in found}
    out += [f"{rel}: the ALLOWLIST excuses {name}(), which carries no lru_cache or cache - "
            f"remove the entry, so the list cannot outlive what it excuses."
            for rel, name in allowlist if (rel, name) not in present]
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else ROOT
    found = problems(root)
    if found:
        for line in found:
            print(line)
        return 1
    print(f"caches: no unreviewed cache under {', '.join(SCANNED)} "
          f"({len(scan(root))} allowlisted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
