"""The one syntax-tree walker every source-reading gate shares (REQ-TEST-384
criterion 9, the architect's non-blocking point on separation v5).

WHY ONE. Three readers of Python syntax trees were proposed beside
validate_caches' own - the imports gate (REQ-TEST-384), the underscore-name
rule (REQ-PIPE-376 criterion 8) and the status-ranking rule (REQ-PIPE-390
criterion 5). Four walkers would be four answers to "which files are product
code" and four ways of reading an import, and they would drift. So the file
list, the parse and the reading of imports live here once; validate_caches
and validate_imports are rules over what it yields, and the two later rules
join validate_imports.RULES rather than becoming scanners of their own.

WHAT IT NEVER DOES: import what it reads. Everything is `ast` over committed
source, so it needs no database, no asset, no pandas and no network.
"""
from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: Directories never walked, whatever they hold: tool caches, installs and
#: version control. Any directory whose name starts with a dot is skipped too.
SKIPPED_DIRS = frozenset({"node_modules", "__pycache__"})


class NotARepository(Exception):
    """`tracked=True` was asked of a directory git cannot list."""


def tracked_python_files(root: Path = ROOT, exempt: tuple[str, ...] = ()) -> list[Path]:
    """Every .py file git tracks under `root` (the index: committed or staged),
    sorted, outside the top-level directories named in `exempt` - hidden
    directories included, so a tracked .github/scripts/x.py is read. A tracked
    file deleted from the working tree is left out, having nothing to read."""
    root = Path(root)
    done = subprocess.run(["git", "ls-files", "-z", "--cached", "--", "*.py"], cwd=root,
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise NotARepository(f"{root}: git cannot list its tracked files "
                             f"({done.stderr.strip() or done.returncode})")
    out = []
    for rel in filter(None, done.stdout.split("\0")):
        path = root / rel
        if rel.split("/")[0] not in exempt and path.is_file():
            out.append(path)
    return sorted(set(out))


def python_files(root: Path = ROOT, tops: tuple[str, ...] | None = None,
                 exempt: tuple[str, ...] = ()) -> list[Path]:
    """Every .py file on disk under `root` - or only under the named top-level
    directories - sorted, skipping SKIPPED_DIRS, hidden directories and the
    top-level directories named in `exempt`. validate_caches reads this way;
    the imports gate reads tracked_python_files()."""
    root = Path(root)
    starts = [root / t for t in tops] if tops is not None else [root]
    out = []
    for start in starts:
        if start.is_file() and start.suffix == ".py":
            out.append(start)
            continue
        if not start.is_dir():
            continue
        for path in start.rglob("*.py"):
            rel = path.relative_to(root).parts
            if rel[0] in exempt:
                continue
            if any(p in SKIPPED_DIRS or p.startswith(".") for p in rel[:-1]):
                continue
            out.append(path)
    return sorted(set(out))


def parse(path: Path) -> ast.Module:
    return ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))


def files(root: Path = ROOT, tops: tuple[str, ...] | None = None,
          exempt: tuple[str, ...] = (), *, tracked: bool = False,
          unparsed: list | None = None):
    """(path relative to root, posix; syntax tree) for every file
    python_files() names - or, with `tracked`, tracked_python_files(). A file
    that does not parse raises, unless `unparsed` is given: then (its path,
    the SyntaxError) is appended there and the walk goes on."""
    root = Path(root)
    paths = (tracked_python_files(root, exempt) if tracked
             else python_files(root, tops, exempt))
    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            tree = parse(path)
        except (SyntaxError, ValueError) as exc:
            if unparsed is None:
                raise
            unparsed.append((rel, exc))
            continue
        yield rel, tree


# ---- imports ----------------------------------------------------------------


@dataclass(frozen=True)
class Import:
    """One module a file reaches: by an import statement at any depth (module
    level, inside a function, under `if TYPE_CHECKING:`), or by
    importlib.import_module or __import__ with a literal name, positional or
    by keyword."""
    line: int
    module: str


def _is_module(root: Path, dotted: str) -> bool:
    path = Path(root, *dotted.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def _package_of(rel: str) -> list[str]:
    """The dotted package a file sits in, from its path."""
    return rel.split("/")[:-1]


def _absolute(rel: str, module: str | None, level: int) -> str | None:
    if level == 0:
        return module
    package = _package_of(rel)
    if level - 1 > len(package):
        return None
    base = package[:len(package) - (level - 1)]
    return ".".join(base + ([module] if module else [])) or None


def _import_module_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """(names bound to importlib, names bound to importlib.import_module)."""
    modules, direct = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "importlib":
                    modules.add(a.asname or "importlib")
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib" and node.level == 0:
            for a in node.names:
                if a.name == "import_module":
                    direct.add(a.asname or a.name)
    return modules, direct


def imports(tree: ast.AST, rel: str, root: Path = ROOT) -> list[Import]:
    """Every module `tree` (the file at `rel`) reaches, as a dotted name.
    `from X import a` reaches X.a where that is a module in the repository,
    else X; a relative import is resolved against the file's own package."""
    out = []
    lib_modules, lib_direct = _import_module_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(Import(node.lineno, a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(rel, node.module, node.level)
            if base is None:
                continue
            for a in node.names:
                candidate = f"{base}.{a.name}"
                out.append(Import(node.lineno, candidate if a.name != "*"
                                  and _is_module(root, candidate) else base))
        elif isinstance(node, ast.Call):
            func = node.func
            named = ((isinstance(func, ast.Name)
                      and (func.id in lib_direct or func.id == "__import__"))
                     or (isinstance(func, ast.Attribute) and func.attr == "import_module"
                         and isinstance(func.value, ast.Name) and func.value.id in lib_modules))
            first = node.args[0] if node.args else next(
                (k.value for k in node.keywords if k.arg == "name"), None)
            if named and isinstance(first, ast.Constant) and isinstance(first.value, str) \
                    and not first.value.startswith("."):
                out.append(Import(node.lineno, first.value))
    return out


@dataclass(frozen=True)
class Call:
    """A call of a function bound by import from one of a set of modules."""
    line: int
    node: ast.Call

    @property
    def text(self) -> str:
        return ast.unparse(self.node)


def calls_of(tree: ast.AST, rel: str, module_names: frozenset[str], function: str,
             root: Path = ROOT) -> list[Call]:
    """Every call in `tree` of `function` from any module in `module_names`,
    whatever the file binds it to: `from pkg import mod` then `mod.f(...)`,
    `import pkg.mod as m` then `m.f(...)`, `import pkg.mod` then
    `pkg.mod.f(...)`, or `from pkg.mod import f as g` then `g(...)`."""
    aliases: set[str] = set()      # a local name for the module
    dotted: set[str] = set()       # the module's full dotted name, used as written
    direct: set[str] = set()       # a local name for the function itself
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in module_names:
                    (aliases.add(a.asname) if a.asname else dotted.add(a.name))
        elif isinstance(node, ast.ImportFrom):
            base = _absolute(rel, node.module, node.level)
            for a in node.names:
                if base in module_names and a.name == function:
                    direct.add(a.asname or a.name)
                elif f"{base}.{a.name}" in module_names:
                    aliases.add(a.asname or a.name)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in direct:
            out.append(Call(node.lineno, node))
        elif isinstance(func, ast.Attribute) and func.attr == function:
            owner = ast.unparse(func.value)
            if owner in aliases or owner in dotted:
                out.append(Call(node.lineno, node))
    return out
