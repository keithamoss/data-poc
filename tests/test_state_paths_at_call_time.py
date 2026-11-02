"""Every asset path a product module uses is asked of the resolver at CALL
TIME (REQ-PIPE-342 criteria 5 to 7, REQ-PIPE-365 criterion 1, REQ-TEST-357
criterion 6).

AN ARCHITECTURE RULE, SO IT READS SOURCE (tests rule 1): there is no
behaviour to observe for "no module builds data/ itself" short of moving the
tree, which is the move's job. The resolver (qa_tools/common/assets.py) is
the one place today's layout - contract/, data/, reports/ - is written down;
anything else naming one of them is a reader the move would leave behind,
and one computing a resolver path at import keeps the folder of whichever
asset was selected when it was imported.

Three rules, over every product package:

  A. no string starting `data/`, `reports/` or `contract/` (f-string pieces
     included);
  B. no `"data"`, `"reports"` or `"contract"` used as a path component - an
     operand of `/`, or an argument to os.path.join, Path or joinpath;
  C. no call to a resolver lookup at import time - in a module or class
     body, a default argument or a decorator.

ALLOWED, a shrink-only list with a reason each: messages that name a file
for a person, and repository-wide lists that are not one asset's. An entry
that no longer matches anything fails too, so the list cannot hold a stale
exemption for the next reader to hide behind.

The geocoding merge, and any module after it, is held to the same rules.
"""
from __future__ import annotations

import pytest

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PRODUCT = ("qa_tools", "pipeline", "generator", "dashboard", "cli", "synthetic_data_generator")

#: The resolver itself, where the layout is written down.
RESOLVER = "qa_tools/common/assets.py"

STATE_ROOTS = ("data", "reports", "contract")
_PREFIX = re.compile(r"^(data|reports|contract)/")

#: The resolver's lookups, and the call-time wrappers built on them.
LOOKUPS = frozenset({
    "selected", "data_dir", "reports_dir", "data_path", "reports_path", "deliveries_dir",
    "receipts_dir", "folder_rel", "dbt_project_ready", "module_file",
    "default_deliveries_dir", "default_receipts_dir", "bookkeeping_path", "placements_path",
    "reports_root", "open_tickets_json", "ticket_resolutions_json",
})

#: (file, the string's start) -> why it may stay. SHRINK-ONLY.
ALLOWED = {
    # MESSAGES - a file named for a person, not a path anything opens.
    ("qa_tools/common/leaderboard.py", "contract/data-asset.yaml names no"):
        "an error message naming the file to edit",
    ("qa_tools/common/ticket_sync.py", "contract/data-asset.yaml names no"):
        "an error message naming the file to edit",
    ("qa_tools/common/people.py", "contract/people.yaml must hold"):
        "an error message naming the file to edit",
    ("qa_tools/common/postgres_version.py", "contract/data-asset.yaml: `"):
        "an error message naming the file to edit",
    ("qa_tools/common/presentation.py", "contract/presentation.yaml is missing"):
        "an error message naming the file to edit",
    ("qa_tools/common/scripted_corrections.py", "contract/scripted_decisions.yaml correction"):
        "an error message naming the file to edit",
    ("qa_tools/common/scripted_decisions.py", "contract/scripted_decisions.yaml decision"):
        "an error message naming the file to edit",
    ("qa_tools/common/validate_hierarchy.py", "contract/data-asset.yaml: "):
        "a gate's finding naming the file to edit",
    ("qa_tools/common/agreement.py", "contract/calendar.yaml"):
        "the default LABEL a parsed document's messages carry - never opened",
    ("qa_tools/common/asset_time.py", "contract/data-asset.yaml"):
        "the default LABEL a parsed document's messages carry - never opened",
    # REPOSITORY-WIDE - not one asset's, so not the resolver's to answer.
    ("qa_tools/common/replay_inputs.py", "contract/**"):
        "the cache key's repository-wide input globs; the move rewrites them",
    ("qa_tools/common/build_output.py", "reports"):
        "an --out-dir build's own layout, DIR/reports/, not an asset's state tree",
}


def _modules():
    found = []
    for pkg in PRODUCT:
        found += sorted((ROOT / pkg).rglob("*.py"))
    return [p for p in found if str(p.relative_to(ROOT)) != RESOLVER]


def _docstrings(tree) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def _path_components(tree) -> set[int]:
    """Constants used as a path component (rule B)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            out.update(id(side) for side in (node.left, node.right))
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in ("join", "Path", "PurePath", "joinpath"):
                out.update(id(a) for a in node.args)
    return out


def hard_coded(source: str) -> list[tuple[int, str]]:
    """Rules A and B over one module's source: (line, string) for each."""
    tree = ast.parse(source)
    docs, components = _docstrings(tree), _path_components(tree)
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in docs:
            continue
        value = node.value
        if _PREFIX.match(value) or (value in STATE_ROOTS and id(node) in components):
            out.append((node.lineno, value))
    return out


def _import_time_nodes(tree):
    """Every node evaluated when the module is imported: module and class
    bodies (not function bodies), default arguments and decorators."""
    def walk(body):
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from stmt.decorator_list
                yield from stmt.args.defaults
                yield from (d for d in stmt.args.kw_defaults if d is not None)
            elif isinstance(stmt, ast.ClassDef):
                yield from stmt.decorator_list
                yield from walk(stmt.body)
            else:
                yield stmt
    for top in walk(tree.body):
        yield from ast.walk(top)


def import_time_lookups(source: str) -> list[tuple[int, str]]:
    """Rule C over one module's source: (line, lookup) for each call."""
    out = []
    for node in _import_time_nodes(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in LOOKUPS:
                out.append((node.lineno, name))
    return out


def _allowed(rel: str, value: str) -> tuple | None:
    for key in ALLOWED:
        if key[0] == rel and value.startswith(key[1]):
            return key
    return None


class TestTheRulesCatchWhatTheyAreFor:
    """The detectors themselves, so a rule that silently stopped matching
    cannot read as a clean tree (tests rule 3)."""

    def test_a_hard_coded_state_path_is_caught(self):
        source = ('from pathlib import Path\nROOT = Path(".")\n'
                  'A = ROOT / "data" / "deliveries"\n'
                  'B = os.path.join(ROOT, "reports", "x.json")\n'
                  'C = f"contract/{agency}"\n'
                  'D = "data/scenario_placements.json"\n')
        assert sorted(v for _, v in hard_coded(source)) == sorted(
            ["data", "reports", "contract/", "data/scenario_placements.json"])

    def test_a_word_that_is_not_a_path_is_not(self):
        source = ('KIND = "contract"\nX = {"contract": 1}\n'
                  'def f():\n    """data/ is where it lives."""\n    return "reports"\n')
        assert hard_coded(source) == []

    def test_a_lookup_at_import_time_is_caught(self):
        source = ("from qa_tools.common import assets, delivery\n"
                  "DELIVERIES = assets.deliveries_dir()\n"
                  "class C:\n    WHERE = delivery.bookkeeping_path()\n"
                  "def f(where=assets.reports_path('x')):\n    return where\n")
        assert sorted(n for _, n in import_time_lookups(source)) == [
            "bookkeeping_path", "deliveries_dir", "reports_path"]

    def test_a_lookup_at_call_time_is_not(self):
        source = ("from qa_tools.common import assets\n"
                  "def deliveries():\n    return assets.deliveries_dir()\n"
                  "class C:\n    def m(self):\n        return assets.data_path('x')\n")
        assert import_time_lookups(source) == []


class TestNoProductModuleBuildsAnAssetPathItself:
    def test_there_are_modules_to_read(self):
        assert len(_modules()) > 100

    def test_no_hard_coded_contract_data_or_reports_path(self):
        offenders = []
        for path in _modules():
            rel = str(path.relative_to(ROOT))
            for line, value in hard_coded(path.read_text()):
                if _allowed(rel, value) is None:
                    offenders.append(f"{rel}:{line} {value!r}")
        assert offenders == [], (
            "a product module builds a contract/, data/ or reports/ path itself - ask the "
            "resolver (qa_tools/common/assets.py) at call time instead (REQ-PIPE-342 "
            "criterion 6):\n  " + "\n  ".join(offenders))

    def test_no_resolver_lookup_at_import_time(self):
        offenders = []
        for path in _modules():
            rel = str(path.relative_to(ROOT))
            offenders += [f"{rel}:{line} {name}()"
                          for line, name in import_time_lookups(path.read_text())]
        assert offenders == [], (
            "a product module asks the resolver at import time, so it keeps the folder of "
            "whichever asset was selected when it was imported - ask inside a function "
            "(REQ-PIPE-342 criterion 6):\n  " + "\n  ".join(offenders))

    def test_every_exemption_is_still_used(self):
        """SHRINK-ONLY: an exemption nothing needs any more is removed."""
        used = set()
        for path in _modules():
            rel = str(path.relative_to(ROOT))
            for _, value in hard_coded(path.read_text()):
                key = _allowed(rel, value)
                if key is not None:
                    used.add(key)
        assert set(ALLOWED) - used == set(), sorted(set(ALLOWED) - used)


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
