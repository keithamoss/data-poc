"""`mothman check`'s imports gate (REQ-TEST-384, signed by Keith 2026-11-14).

THE SEPARATION, CHECKED RATHER THAN REMEMBERED (plans/running-thoughts.md
#134, Keith 2026-10-31: 'a strict separation'). Every Python file of the
repository outside tests/, scripts/ and docs/ sits on one SIDE:

  asset_model  asset_model/ - configuration and the delivery tree
  pipeline     the real pipeline: qa_tools/, pipeline/, dashboard/, aws/
               and each asset's collections/ (its QA adapters)
  generator    generator/, synthetic_data_generator/ and each asset's
               synthetic/collections/ (its providers)
  scenarios    scenarios/
  bootstrap    bootstrap/
  cli          cli/

and may import only the sides ALLOWED names for it. An import is any import
statement at any depth - module level, inside a function, under `if
TYPE_CHECKING:` - an importlib.import_module call with a literal name, and a
call of the asset resolver's path loader (assets.load), which runs an
adapter or a provider file with no import statement at all: its kind names
the side it loads, so a kind that is not a literal is a finding of its own.
A file in no side fails too, so a new top-level package is given a side
before it can land.

WHAT IS NOT A FINDING YET is on the ALLOWLIST file - every forbidden import
the tree held when the gate landed, each naming the requirement that removes
it. The list only shrinks: an entry matching no import any more fails, asking
for its deletion, and an entry the push's base commit did not hold fails as a
gain. The fix for a finding is to move the code across the boundary.

It reads the syntax trees of the files git tracks (committed or staged, so a
scratch file in a working tree is not read, and a tracked one in a hidden
directory is) through qa_tools/common/syntax_walk.py, and imports nothing it
reads, so it needs no asset, no database and no network. A file that does not
parse is a finding of its own, never a crash. RULES is
where REQ-PIPE-376 criterion 8 (no underscore-led asset_model name used
outside it) and REQ-PIPE-390 criterion 5 (no status ranking of its own) join
as rules of this gate rather than scanners of their own.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from qa_tools.common import diff_base as _diff_base
from qa_tools.common import syntax_walk

ROOT = Path(__file__).resolve().parent.parent.parent

#: The committed allowlist, relative to the repository root.
ALLOWLIST = "imports-allowlist.yaml"

#: Top-level directories the gate does not read, each for its reason.
EXEMPT = {
    "tests": "a test of the bootstrap imports the pipeline and the bootstrap together by design",
    "scripts": "throwaway dev-only tools that ship with nothing",
    "docs": "illustrations beside design notes (docs/quarantine_sex_column.py)",
}

#: Which side each top-level package is on.
TOP_SIDES = {
    "asset_model": "asset_model",
    "qa_tools": "pipeline", "pipeline": "pipeline", "dashboard": "pipeline", "aws": "pipeline",
    "generator": "generator", "synthetic_data_generator": "generator",
    "scenarios": "scenarios",
    "bootstrap": "bootstrap",
    "cli": "cli",
}
SIDES = ("asset_model", "pipeline", "generator", "scenarios", "bootstrap", "cli")

#: What each side may import (criterion 3; the generator's edges Q1, SETTLED
#: by Keith 2026-11-02). Every side may import itself.
ALLOWED = {
    "asset_model": frozenset({"asset_model"}),
    "pipeline": frozenset({"pipeline", "asset_model"}),
    "generator": frozenset({"generator", "asset_model", "scenarios"}),
    "scenarios": frozenset({"scenarios", "asset_model"}),
    "bootstrap": frozenset({"bootstrap", "asset_model", "scenarios", "pipeline", "generator"}),
    "cli": frozenset(SIDES),
}

#: The asset resolver's path loader, where it lives today and where REQ-PIPE-380
#: moves it, and which side each kind it loads is on (criterion 5).
LOADER_MODULES = frozenset({"asset_model.assets", "asset_model.assets"})
LOADER = "load"
LOADED_SIDES = {"adapter": "pipeline", "provider": "generator"}

_REQUIREMENT = re.compile(r"REQ-[A-Z]+-\d+")


def side_of_file(rel: str) -> str | None:
    """The side a repository file is on, or None. An asset's QA adapters
    (assets/<asset>/collections/) are the real pipeline's and its providers
    (assets/<asset>/synthetic/collections/) the generator's - sorted by folder,
    so a thirtieth collection or a new asset needs no change here."""
    parts = rel.split("/")
    if len(parts) > 1 and parts[0] in TOP_SIDES:
        return TOP_SIDES[parts[0]]
    if parts[0] == "assets" and len(parts) > 3:
        if parts[2] == "collections":
            return "pipeline"
        if parts[2:4] == ["synthetic", "collections"] and len(parts) > 4:
            return "generator"
    return None


#: What a module under assets/ that no side owns is reported as: a file there
#: outside collections/ and synthetic/collections/ is in no side, and no side
#: may import it (REQ-PIPE-380 criterion 9 for asset_model/).
NO_SIDE = "no side"


def side_of_module(module: str) -> str | None:
    """The side a dotted module name is on, or None for anything not ours. A
    module under assets/ is sided exactly as side_of_file sides its file -
    assets.<asset>.collections.* the pipeline's, assets.<asset>.synthetic.
    collections.* the generator's - and anything else under assets/ is NO_SIDE."""
    parts = module.split(".")
    if parts[0] == "assets":
        return side_of_file("/".join(parts) + "/__init__.py") or NO_SIDE
    return TOP_SIDES.get(parts[0])


@dataclass(frozen=True)
class Finding:
    """One forbidden import: `module` is the dotted name, or '<kind> loaded
    by path' for a call of the path loader."""
    file: str
    line: int
    side: str
    imported_side: str
    module: str

    def __str__(self) -> str:
        return (f"{self.file}:{self.line}: {self.side} imports {self.imported_side} "
                f"({self.module}) - forbidden edge")


@dataclass(frozen=True)
class Problem:
    """A finding the allowlist cannot excuse: a file in no side, a loader call
    whose kind is not a literal, or something wrong with the allowlist."""
    text: str

    def __str__(self) -> str:
        return self.text


def _loads(tree, rel: str, root: Path, side: str) -> tuple[list[Finding], list[Problem]]:
    findings, problems = [], []
    for call in syntax_walk.calls_of(tree, rel, LOADER_MODULES, LOADER, root):
        node = call.node
        kind = node.args[0] if node.args else next(
            (k.value for k in node.keywords if k.arg == "kind"), None)
        if not (isinstance(kind, ast.Constant) and isinstance(kind.value, str)):
            problems.append(Problem(
                f"{rel}:{call.line}: {side} loads by path with a kind that is not a literal "
                f"({call.text}) - the gate cannot tell which side it loads; pass 'adapter' "
                f"or 'provider' as written"))
            continue
        loaded = LOADED_SIDES.get(kind.value)
        if loaded is None:
            problems.append(Problem(
                f"{rel}:{call.line}: {side} loads by path a kind no side owns "
                f"({call.text}) - the gate knows {', '.join(sorted(LOADED_SIDES))}"))
        elif loaded not in ALLOWED[side]:
            findings.append(Finding(rel, call.line, side, loaded,
                                    f"{kind.value} loaded by path"))
    return findings, problems



def forbidden_edges(rel: str, tree, root: Path) -> tuple[list[Finding], list[Problem]]:
    """The imports rule: every forbidden edge one file has."""
    side = side_of_file(rel)
    if side is None:
        return [], [Problem(
            f"{rel}:1: in no side - give its top-level directory a side in "
            f"qa_tools/common/validate_imports.py's TOP_SIDES (or put it under one that "
            f"has one) before it lands")]
    findings = []
    for imp in dict.fromkeys(syntax_walk.imports(tree, rel, root)):
        target = side_of_module(imp.module)
        if target is not None and target not in ALLOWED[side]:
            findings.append(Finding(rel, imp.line, side, target, imp.module))
    loads, problems = _loads(tree, rel, root, side)
    return findings + loads, problems


#: Each rule takes (file relative to the root, its syntax tree, the root) and
#: returns (allowlistable findings, problems). REQ-PIPE-376 criterion 8 and
#: REQ-PIPE-390 criterion 5 add theirs here.
RULES = (forbidden_edges,)


def scan(root: Path = ROOT) -> tuple[list[Finding], list[Problem]]:
    """Every rule over every tracked file. Raises syntax_walk.NotARepository
    where `root` is not a git checkout."""
    findings, problems, unparsed = [], [], []
    for rel, tree in syntax_walk.files(root, exempt=tuple(EXEMPT), tracked=True,
                                       unparsed=unparsed):
        for rule in RULES:
            f, p = rule(rel, tree, root)
            findings += f
            problems += p
    problems += [Problem(f"{rel}:{getattr(exc, 'lineno', None) or 1}: cannot be parsed "
                         f"({getattr(exc, 'msg', None) or exc}) - the gate cannot read its "
                         f"imports until it does")
                 for rel, exc in unparsed]
    return findings, problems


# ---- the allowlist ------------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    file: str
    imports: str
    removed_by: str

    @property
    def key(self) -> tuple[str, str]:
        return self.file, self.imports

    def __str__(self) -> str:
        return f"{self.file} imports {self.imports} ({self.removed_by or 'no requirement'})"


def read_allowlist(text: str) -> tuple[list[Entry], list[str]]:
    """(the entries, what is malformed): a file that is not YAML, `entries`
    that is not a list, or an entry that is not a mapping is reported rather
    than raised, each naming what it found."""
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return [], [f"{ALLOWLIST}: malformed - not YAML ({str(exc).splitlines()[0]})"]
    if not isinstance(doc, dict):
        return [], [f"{ALLOWLIST}: malformed - expected a mapping with `entries:`, "
                    f"found {type(doc).__name__}"]
    listed = doc.get("entries") or []
    if not isinstance(listed, list):
        return [], [f"{ALLOWLIST}: malformed - `entries` must be a list, found "
                    f"{type(listed).__name__} ({listed!r})"]
    entries, malformed = [], []
    for i, e in enumerate(listed):
        if not isinstance(e, dict):
            malformed.append(f"{ALLOWLIST}: malformed entry {i + 1} ({e!r}) - each entry is "
                             f"a mapping of file, imports and removed_by")
            continue
        entries.append(Entry(str(e.get("file", "")), str(e.get("imports", "")),
                             str(e.get("removed_by") or "")))
    return entries, malformed


def parse_allowlist(text: str) -> list[Entry]:
    return read_allowlist(text)[0]


def load_allowlist(root: Path = ROOT) -> list[Entry] | None:
    path = Path(root) / ALLOWLIST
    return parse_allowlist(path.read_text(encoding="utf-8")) if path.exists() else None


def _allowlist_at_base(root: Path) -> tuple[str, list[Entry] | None]:
    """(the base commit, short; the allowlist as it held it), the list None
    where the base did not hold one (the gate's own landing). Raises
    LookupError where the base cannot be read."""
    ref = _diff_base.diff_base(root=root)
    if not _diff_base._resolves(ref, root):
        raise LookupError((os.environ.get(_diff_base.ENV_VAR) or "").strip() or ref)
    sha = subprocess.run(["git", "rev-parse", "--short", f"{ref}^{{commit}}"], cwd=root,
                         capture_output=True, text=True).stdout.strip() or ref
    shown = subprocess.run(["git", "show", f"{ref}:{ALLOWLIST}"], cwd=root,
                           capture_output=True, text=True)
    return sha, (parse_allowlist(shown.stdout) if shown.returncode == 0 else None)


def _known_requirements(root: Path) -> set[str] | None:
    path = Path(root) / "requirements.yaml"
    if not path.exists():
        return None
    return set(re.findall(r"^\s*- id: (REQ-[A-Z]+-\d+)\s*$", path.read_text(encoding="utf-8"),
                          re.M))


def allowlist_problems(entries: list[Entry], findings: list[Finding], root: Path,
                       base: tuple[str, list[Entry] | None] | None) -> list[str]:
    out = []
    known = _known_requirements(root)
    live = {(f.file, f.module) for f in findings}
    seen = set()
    for e in entries:
        if e.key in seen:
            out.append(f"{ALLOWLIST}: entry {e} is listed twice - delete one")
        seen.add(e.key)
        if not _REQUIREMENT.fullmatch(e.removed_by):
            out.append(f"{ALLOWLIST}: entry {e} names no requirement - every entry names "
                       f"the requirement that removes it, so the list is a to-do list")
        elif known is not None and e.removed_by not in known:
            out.append(f"{ALLOWLIST}: entry {e} names {e.removed_by}, which requirements.yaml "
                       f"does not hold")
        if e.key not in live:
            out.append(f"{ALLOWLIST}: entry {e} matches no import any more - delete it")
    if base is not None:
        sha, at_base = base
        if at_base is not None:
            held = {b.key for b in at_base}
            out += [f"{ALLOWLIST}: entry {e} is absent at the base commit {sha} - the list "
                    f"only shrinks (REQ-TEST-384); move the code across the boundary instead"
                    for e in entries if e.key not in held]
    return out


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    root = Path(root or ROOT)
    try:
        findings, problems = scan(root)
    except syntax_walk.NotARepository as exc:
        print(f"imports: {exc} - the gate reads committed files only")
        return 1
    path = root / ALLOWLIST
    if not path.exists():
        print(f"imports: {ALLOWLIST} is missing - the gate reads its exceptions from it")
        return 1
    entries, malformed = read_allowlist(path.read_text(encoding="utf-8"))
    try:
        base = _allowlist_at_base(root)
    except LookupError as unreadable:
        print(f"imports: note - gain check skipped: the base commit ({unreadable}) cannot be "
              f"read from this checkout (a shallow clone, or a first commit), so whether "
              f"{ALLOWLIST} gained an entry is unchecked here.")
        base = None
    allowed = {e.key for e in entries}
    new = [f for f in findings if (f.file, f.module) not in allowed]
    listed = malformed + allowlist_problems(entries, findings, root, base)
    for line in [*map(str, new), *map(str, problems), *listed]:
        print(line)
    count = len(new) + len(problems) + len(listed)
    if count:
        print(f"imports: {count} problem(s). The fix for a forbidden edge is to move the code "
              f"across the boundary, not to add an entry to {ALLOWLIST}, which only shrinks.")
        return 1
    print(f"imports: no forbidden edge outside {ALLOWLIST} ({len(entries)} entr"
          f"{'y' if len(entries) == 1 else 'ies'} left to remove, "
          f"{len(findings)} import(s) they excuse)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
