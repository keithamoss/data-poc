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
parse is a finding of its own, never a crash. RULES holds REQ-PIPE-376
criterion 8 (no underscore-led asset_model name used outside it) and
REQ-PIPE-390 criterion 5 (no status ranking of its own) as rules of this
gate rather than scanners of their own; neither is allowlistable.
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
from asset_model import config_yaml

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

#: The asset resolver's path loader, in asset_model/ since REQ-PIPE-380, and
#: which side each kind it loads is on (criterion 5).
LOADER_MODULES = frozenset({"asset_model.assets"})
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


def _asset_model_bindings(tree, rel: str, root: Path) -> dict[str, str]:
    """{local name: asset_model module} for every asset_model module the file
    binds as a name - `from asset_model import x [as y]`, `import
    asset_model.x as y` - at any depth."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for a in node.names:
                full = f"{node.module}.{a.name}"
                if full.split(".")[0] == "asset_model" and syntax_walk._is_module(root, full):
                    out[a.asname or a.name] = full
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] == "asset_model" and a.asname:
                    out[a.asname] = a.name
    return out


def _private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def private_names(rel: str, tree, root: Path) -> tuple[list[Finding], list[Problem]]:
    """REQ-PIPE-376 criteria 3 and 8: no module outside asset_model/ (and
    tests/, which the gate does not read) uses an underscore-led asset_model
    name - imported from it, read as an attribute of it, or named to
    getattr/setattr on it. A name the shared code is used by is public, so a
    private one is a promise nobody knows was made. Reads source, because the
    rule is an architecture rule with no behaviour to observe (CLAUDE.md's
    test rule allows that when said). Never allowlistable: the fix is to give
    the name a public one in asset_model/."""
    if side_of_file(rel) in (None, "asset_model"):
        return [], []
    problems = []

    def found(line, module, name, how):
        problems.append(Problem(
            f"{rel}:{line}: {side_of_file(rel)} {how} {module}.{name}, an underscore-led "
            f"asset_model name - give it a public name in {module.replace('.', '/')}.py "
            f"(REQ-PIPE-376 criterion 3)"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module \
                and node.module.split(".")[0] == "asset_model":
            for a in node.names:
                if _private(a.name):
                    found(node.lineno, node.module, a.name, "imports")
    bound = _asset_model_bindings(tree, rel, root)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id in bound and _private(node.attr):
            found(node.lineno, bound[node.value.id], node.attr, "reads")
        elif isinstance(node, ast.Call) and len(node.args) >= 2 \
                and isinstance(node.args[0], ast.Name) and node.args[0].id in bound \
                and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str) \
                and _private(node.args[1].value):
            found(node.lineno, bound[node.args[0].id], node.args[1].value, "names")
        elif isinstance(node, ast.Attribute) and _private(node.attr):
            # import asset_model.x, then asset_model.x._name
            dotted = ast.unparse(node.value)
            if dotted.split(".")[0] == "asset_model" and syntax_walk._is_module(root, dotted):
                found(node.lineno, dotted, node.attr, "reads")
    return [], problems


#: The status words a ranking orders (REQ-PIPE-390): the ordered statuses.
RANKED_WORDS = frozenset({"nodata", "green", "amber", "red"})


def _words_sequence(node, named: dict) -> bool:
    """A tuple or list literal of two or more status words - or a name a
    module-level assignment binds to one."""
    if isinstance(node, ast.Name):
        return node.id in named
    if not isinstance(node, (ast.Tuple, ast.List)):
        return False
    words = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return len(words) == len(node.elts) and len(set(words) & RANKED_WORDS) >= 2


def status_rankings(rel: str, tree, root: Path) -> tuple[list[Finding], list[Problem]]:
    """REQ-PIPE-390 criterion 5: no Python module outside asset_model/ (and
    tests/) defines its own ranking of the status words. Three shapes:
    a dictionary literal mapping two or more of nodata, green, amber and red
    to numbers, which is what each former copy was ({"green": 0, "amber": 1,
    "red": 2}); a tuple or list of the words read as an order through
    `.index()`; and `enumerate()` over one (a dictionary or list
    comprehension numbering the words). A sequence of the words that is
    only tested for membership is not a ranking and passes. The ranking is
    asset_model.statuses' ORDERED_STATUSES and VERDICT_ORDER, read rather
    than repeated. Python modules only - the dashboard page keeps its own
    copy, held equal by status-cases.json (criterion 4). Reads source, an
    architecture rule with no behaviour to observe. Never allowlistable."""
    if side_of_file(rel) in (None, "asset_model"):
        return [], []
    named = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and _words_sequence(node.value, {}):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    named[t.id] = node.value
    problems = []

    def found(node, how):
        problems.append(Problem(
            f"{rel}:{node.lineno}: {side_of_file(rel)} defines its own ranking of the "
            f"status words ({how}: {ast.unparse(node)}) - read asset_model.statuses' "
            f"ORDERED_STATUSES or VERDICT_ORDER instead (REQ-PIPE-390 criterion 5)"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict) and node.keys:
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if len(keys) != len(node.keys) or len(set(keys) & RANKED_WORDS) < 2:
                continue
            if all(isinstance(v, ast.Constant) and isinstance(v.value, (int, float))
                   and not isinstance(v.value, bool)
                   or (isinstance(v, ast.UnaryOp) and isinstance(v.operand, ast.Constant))
                   for v in node.values):
                found(node, "numbered")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "index" \
                    and _words_sequence(func.value, named):
                found(node, "an order read through .index()")
            elif isinstance(func, ast.Name) and func.id == "enumerate" and node.args \
                    and _words_sequence(node.args[0], named):
                found(node, "numbered by enumerate()")
    return [], problems


# ---- configuration read through config_yaml (REQ-PIPE-397 criterion 8) -------

#: Where the rule reads: the code that runs inside a pinned generation or
#: replay - the shared reading code, the real pipeline, the generator, the
#: dashboard build, the bootstrap and the CLI that drives them
#: (post-build-review #395), and each asset's adapters and providers.
PINNED_READ_TOPS = ("asset_model", "qa_tools", "generator", "pipeline", "dashboard",
                    "bootstrap", "cli")

#: The one module allowed to read a configuration file itself.
CONFIG_YAML = "asset_model/config_yaml.py"

#: PyYAML's parse calls - every one of them belongs in config_yaml.
YAML_PARSES = frozenset({"safe_load", "load", "full_load", "unsafe_load", "safe_load_all",
                         "load_all"})


def _pinned_scope(rel: str) -> bool:
    parts = rel.split("/")
    if parts[0] in PINNED_READ_TOPS:
        return rel != CONFIG_YAML
    return parts[0] == "assets" and len(parts) > 3 and (
        parts[2] == "collections" or parts[2:4] == ["synthetic", "collections"])


def _yaml_names(tree) -> set[str]:
    """Names the file binds to the yaml module."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.asname or a.name for a in node.names if a.name == "yaml"}
    return out


def _yaml_parse_imports(tree) -> list:
    """`from yaml import safe_load` (or any parse call), each as its node."""
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "yaml" and node.level == 0
            and any(a.name in YAML_PARSES for a in node.names)]


def _read_names(tree, opened: set[str]) -> set[str]:
    """Names assigned a file's content: `text = Path(p).read_text()`, `text =
    open(p).read()`, or `text = fh.read()` on a handle a `with open(...)`
    bound - however the name or the path is spelled (post-build-review
    #395). File-wide, so a name reused for something else is read as the
    stricter case."""
    out = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        value = node.value
        handle_read = (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                       and value.func.attr == "read" and isinstance(value.func.value, ast.Name)
                       and value.func.value.id in opened)
        if _is_file_read(value) or handle_read:
            out.add(node.targets[0].id)
    return out


def _is_file_read(node) -> bool:
    """A call that reads a file's content: x.read_text(), x.read_bytes(),
    open(x) or open(x, 'r'/'rb'), or x.read() on one of those."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in ("read_text", "read_bytes"):
        return True
    if isinstance(func, ast.Attribute) and func.attr == "read":
        return _is_file_read(func.value)
    if isinstance(func, ast.Name) and func.id == "open":
        mode = node.args[1] if len(node.args) > 1 else next(
            (k.value for k in node.keywords if k.arg == "mode"), None)
        return mode is None or (isinstance(mode, ast.Constant) and isinstance(mode.value, str)
                                and "r" in mode.value and "+" not in mode.value)
    return False


def _opened_names(tree) -> set[str]:
    """Names bound by `with open(x) as name` (a read)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if _is_file_read(item.context_expr) and isinstance(item.optional_vars, ast.Name):
                    out.add(item.optional_vars.id)
    return out


def _names_yaml(node) -> bool:
    """Whether an expression names a YAML file: a '.yaml'/'.yml' literal in
    it, or a function, method or attribute whose name ends in yaml or yml
    (data_asset_yaml(), calendar_yaml())."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                and (".yaml" in sub.value or ".yml" in sub.value):
            return True
        name = sub.attr if isinstance(sub, ast.Attribute) else (
            sub.id if isinstance(sub, ast.Name) else None)
        if name and name.lower().endswith(("_yaml", "_yml")):
            return True
    return False


def _read_target(node: ast.Call):
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "read":
        return _read_target(func.value)
    if isinstance(func, ast.Attribute):
        return func.value
    return node.args[0] if node.args else None


def pinned_reads(rel: str, tree, root: Path) -> tuple[list[Finding], list[Problem]]:
    """REQ-PIPE-397 criterion 8: a module that runs inside a pinned run reads
    configuration through config_yaml (read, load or a Built store), never
    itself - or the pin would miss it in silence. Three shapes fail, each
    naming the file, the line and what it reads:

    - a PyYAML parse call (yaml.safe_load, yaml.load, ...): config_yaml.parse
      for text the caller holds, config_yaml.load for a file;
    - config_yaml.parse of the caller's own read (x.read_text(), open(x), a
      `with open(x) as f` handle, or a name assigned any of those or a
      handle's read()): config_yaml.load(x) instead;
    - `from yaml import safe_load` (any parse call imported by name);
    - read_text/open of a path naming a YAML file (a '.yaml' or '.yml' literal,
      or a name ending in yaml or yml): config_yaml.read or load.

    PROVISIONAL (2026-11-16): the gate cannot know statically which file a
    path names, so it holds every YAML read in these packages to config_yaml
    rather than only the snapshot set's - a YAML file outside the set (the
    register, a workflow) read through config_yaml is simply read from disk.
    Reads source, an architecture rule with no behaviour to observe. Never
    allowlistable: the fix is a one-line change to config_yaml."""
    if not _pinned_scope(rel):
        return [], []
    yaml_names = _yaml_names(tree)
    opened = _opened_names(tree)
    read_names = _read_names(tree, opened)
    parses = {id(c.node) for c in syntax_walk.calls_of(
        tree, rel, frozenset({"asset_model.config_yaml"}), "parse", root)}
    problems = []

    def found(node, what, instead):
        problems.append(Problem(
            f"{rel}:{node.lineno}: reads configuration outside config_yaml ({what}) - "
            f"{instead}, so a pinned run answers it from its snapshot (REQ-PIPE-397 "
            f"criterion 8)"))

    for node in _yaml_parse_imports(tree):
        found(node, ast.unparse(node), "import config_yaml and call config_yaml.parse or load")
    seen: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in YAML_PARSES \
                and isinstance(func.value, ast.Name) and func.value.id in yaml_names:
            found(node, ast.unparse(node),
                  "use config_yaml.parse for text you hold, config_yaml.load for a file")
            for sub in ast.walk(node):
                seen.add(id(sub))
        elif id(node) in parses and node.args:
            arg = node.args[0]
            if _is_file_read(arg) or (isinstance(arg, ast.Name)
                                      and arg.id in opened | read_names):
                found(node, f"parses its own read of {ast.unparse(arg)}",
                      "use config_yaml.load(path)")
                for sub in ast.walk(arg):
                    seen.add(id(sub))
    for node in ast.walk(tree):
        if id(node) in seen or not _is_file_read(node):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "read":
            continue
        target = _read_target(node)
        if target is not None and _names_yaml(target):
            found(node, f"reads {ast.unparse(target)}", "use config_yaml.read or load")
    return [], problems


#: Each rule takes (file relative to the root, its syntax tree, the root) and
#: returns (allowlistable findings, problems): the forbidden edges
#: (REQ-TEST-384), the underscore-name rule (REQ-PIPE-376 criterion 8), the
#: status-ranking rule (REQ-PIPE-390 criterion 5) and configuration read
#: through config_yaml (REQ-PIPE-397 criterion 8).
RULES = (forbidden_edges, private_names, status_rankings, pinned_reads)


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
        doc = config_yaml.parse(text) or {}
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
