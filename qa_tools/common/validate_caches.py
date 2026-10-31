"""No process-long cache under qa_tools/, pipeline/ or generator/ that nobody reviewed
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
`import functools as ft` then `ft.cache`, `from functools import cache` or
`*`, an alias of either by import or by assignment (`memo =
functools.lru_cache`), or a wrap by assignment, plain, annotated or onto an
attribute - that is not on ALLOWLIST below. It reads only committed
source, with `ast`, so it needs no database and no import of what it scans.
An allowlist entry that names no cache fails too, so the list cannot outlive
what it excuses.

AND A VALUE BUILT FROM CONFIGURATION AT IMPORT (post-build-review #282 (7),
Keith 2026-10-29): a top-level statement calling into one of CONFIG_READERS
- `DATASET_SCOPE = {... for d in hierarchy.all_datasets()}` - holds what the
file said when the module was first imported, for the process. It has no
allowlist: such a value is read when it is asked for instead.

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

#: Where the gate looks, relative to the repository root. generator/ joined
#: 2026-10-29 (post-build-review #282 (7), Keith's option a):
#: emergency_department.run_plan held the calendar for the process.
SCANNED = ("qa_tools", "pipeline", "generator")

#: THE MODULES WHOSE CALLS READ CONFIGURATION, by the name a file binds them
#: to: a call into one at import builds a value from the file as it stood
#: then, and holds it for the process as surely as a cache does
#: (ticket_sync.DATASET_SCOPE, post-build-review #282 (7)). config_yaml is
#: not one - config_yaml.Built() at import is the content-keyed store itself.
CONFIG_READERS = frozenset({"hierarchy", "collections", "agreement", "asset_time",
                            "arrival_patterns", "presentation", "schedule", "slots"})

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
    # generator/, scanned from 2026-10-29: each built from module constants
    # and a fixed seed alone, reading no file, so nothing can go stale.
    ("generator/collections/child_protection.py", "_cp_delay"):
        "a fixed resupply-delay curve from numpy constants; reads no file",
    ("generator/collections/child_protection.py", "run_plan"):
        "drawn from N_QUARTERS and a fixed seed; reads no file",
    ("generator/collections/child_protection.py", "grown_run_plan"):
        "drawn from GROWN_QUARTERS and a fixed seed; reads no file",
    ("generator/collections/civil_registration.py", "run_plan"):
        "drawn from N_DELIVERIES and a fixed seed; reads no file",
    ("generator/collections/emergency_department.py", "_postcodes"):
        "the postcodes of generator/names_au.py's SUBURBS constant; reads no file",
}


def _names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """(names bound to the functools module, names bound to lru_cache or
    cache themselves) by this file's own imports - a star import of functools
    binds both - and by plain assignment of either (`memo =
    functools.lru_cache`), followed until nothing new is bound."""
    modules, direct = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "functools":
                    modules.add(alias.asname or "functools")
        elif isinstance(node, ast.ImportFrom) and node.module == "functools":
            for alias in node.names:
                if alias.name == "*":
                    direct |= CACHING
                elif alias.name in CACHING:
                    direct.add(alias.asname or alias.name)
    aliases = [(targets, node.value) for node in ast.walk(tree)
               for targets in [_targets(node)] if targets and node.value is not None
               and not isinstance(node.value, ast.Call)]
    grew = True
    while grew:
        grew = False
        for targets, value in aliases:
            if isinstance(value, ast.Name) and value.id in modules:
                new = {t for t in targets if t not in modules}
                modules |= new
            elif _is_caching(value, modules, direct):
                new = {t for t in targets if t not in direct}
                direct |= new
            else:
                continue
            grew = grew or bool(new)
    return modules, direct


def _targets(node: ast.AST) -> list[str]:
    """The names an assignment binds - plain, annotated, or onto an attribute
    (`A.f = ...`, named by the attribute) - or [] for anything else."""
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return []
    out = []
    for target in targets:
        if isinstance(target, ast.Name):
            out.append(target.id)
        elif isinstance(target, ast.Attribute):
            out.append(target.attr)
    return out


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
    decorated, or wrapped by assignment (`f = functools.cache(g)`, annotated
    or onto an attribute)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules, direct = _names(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(_is_caching(d, modules, direct) for d in node.decorator_list):
                found.append((node.name, node.lineno))
        elif _targets(node) and isinstance(node.value, ast.Call):
            call = node.value
            wrapped = (_is_caching(call.func, modules, direct)
                       or (isinstance(call.func, ast.Call)
                           and _is_caching(call.func.func, modules, direct)))
            if wrapped:
                found.extend((name, node.lineno) for name in _targets(node))
    return found


def _calls_a_reader(node: ast.AST) -> bool:
    """Whether evaluating `node` at import calls into a configuration reader -
    never looking inside a function, class or lambda, which run later."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
        return False
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and isinstance(node.func.value, ast.Name) and node.func.value.id in CONFIG_READERS:
        return True
    return any(_calls_a_reader(child) for child in ast.iter_child_nodes(node))


def import_time_reads(path: Path) -> list[int]:
    """The line of each top-level statement in one file that builds a value
    from configuration as the module is imported."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [node.lineno for node in tree.body
            if not isinstance(node, (ast.Import, ast.ImportFrom)) and not _is_main(node)
            and _calls_a_reader(node)]


def _is_main(node: ast.AST) -> bool:
    """`if __name__ == "__main__":` - run as a script, never on import."""
    return (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"
            and any(isinstance(c, ast.Constant) and c.value == "__main__"
                    for c in node.test.comparators))


def scan_import_time(root: Path = ROOT) -> list[tuple[str, int]]:
    out = []
    for top in SCANNED:
        for path in sorted((Path(root) / top).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            out.extend((rel, line) for line in import_time_reads(path))
    return out


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
    out += [f"{rel}:{line}: builds a value from configuration at import, which holds it "
            f"for the process as a cache would - an edited or swapped file is answered for "
            f"what it said when the module was first imported. Read it when it is asked for "
            f"(post-build-review #282 (7))."
            for rel, line in scan_import_time(root)]
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
