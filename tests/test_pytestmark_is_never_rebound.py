"""A test module's `pytestmark` is never REBOUND, only extended.

WHY (REQ-TEST-375, the critical set). A module's marks are one module-level
name, and pytest reads only its last value. During the asset split's merge,
33 modules lost their `critical` mark because a later
`pytestmark = pytest.mark.asset(...)` replaced the `pytestmark =
pytest.mark.critical` above it - nothing failed, the push job just stopped
running them. The critical set is hand-picked and nothing else notices a
module leaving it, so this reads every module under tests/ and fails on any
module-level assignment to `pytestmark` after the first that does not read
the earlier value (`[*pytestmark, ...]`, `pytestmark + [...]`, `+=`).

An ARCHITECTURE RULE READ FROM SOURCE (CLAUDE.md's test rule 1): the thing
guarded is how a module is written, before any test in it runs, and the
loss it guards against is silent at run time by construction.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

NAME = "pytestmark"


def _module_level(body):
    """Module-level statements, into if/try/with blocks but never into a
    function or class, whose own `pytestmark` is not the module's."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield node
        for field in ("body", "orelse", "finalbody", "handlers"):
            inner = getattr(node, field, None)
            if isinstance(inner, list):
                yield from _module_level(inner)


def _targets(node) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return node.targets
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return [node.target]
    return []


def _reads_the_name(expr) -> bool:
    return expr is not None and any(
        isinstance(n, ast.Name) and n.id == NAME and isinstance(n.ctx, ast.Load)
        for n in ast.walk(expr))


def rebindings(source: str) -> list[int]:
    """Line numbers of each module-level assignment to `pytestmark`, after the
    first, that drops the earlier value."""
    seen, dropped = 0, []
    for node in _module_level(ast.parse(source).body):
        if not any(isinstance(t, ast.Name) and t.id == NAME for t in _targets(node)):
            continue
        seen += 1
        if seen == 1 or isinstance(node, ast.AugAssign):
            continue
        if not _reads_the_name(node.value):
            dropped.append(node.lineno)
    return dropped


def _modules() -> list[Path]:
    return sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_test_module_rebinds_its_pytestmark():
    modules = _modules()
    assert len(modules) > 100, f"found only {len(modules)} modules under {TESTS}"
    found = {str(p.relative_to(TESTS.parent)): lines
             for p in modules if (lines := rebindings(p.read_text()))}
    assert not found, (
        "these modules assign `pytestmark` again without keeping its earlier value, so "
        "every mark above the line is lost (a `critical` mark among them leaves the push "
        "set in silence) - extend it instead, e.g. `pytestmark = [*(pytestmark if "
        "isinstance(pytestmark, list) else [pytestmark]), pytest.mark.asset(...)]`:\n  "
        + "\n  ".join(f"{m}: line(s) {', '.join(map(str, ls))}" for m, ls in sorted(found.items())))


class TestTheRuleItself:
    """It can fail: the merge's own shape is caught, and the shapes that keep
    the earlier marks are not."""

    def test_the_merges_shape_is_caught(self):
        src = ("import pytest\npytestmark = pytest.mark.critical\n\ndef test_x():\n    pass\n\n"
               "pytestmark = pytest.mark.asset('quarterly')\n")
        assert rebindings(src) == [7]

    @pytest.mark.parametrize("second", [
        "pytestmark = [pytestmark, pytest.mark.asset('daily')]",
        "pytestmark = [*(pytestmark if isinstance(pytestmark, list) else [pytestmark]), "
        "pytest.mark.asset('daily')]",
        "pytestmark += [pytest.mark.asset('daily')]",
        "pytestmark: list = pytestmark + [pytest.mark.asset('daily')]",
    ])
    def test_extending_keeps_the_earlier_marks(self, second):
        assert rebindings(f"import pytest\npytestmark = [pytest.mark.critical]\n{second}\n") == []

    def test_one_assignment_is_fine_and_a_class_level_one_is_not_the_modules(self):
        src = ("import pytest\npytestmark = pytest.mark.critical\n\nclass TestX:\n"
               "    pytestmark = pytest.mark.slow\n")
        assert rebindings(src) == []

    def test_a_rebinding_inside_a_module_level_block_counts(self):
        src = ("import pytest\npytestmark = pytest.mark.critical\nif True:\n"
               "    pytestmark = pytest.mark.asset('daily')\n")
        assert rebindings(src) == [4]

    def test_a_broken_copy_of_a_real_module_fails_the_guard(self, tmp_path):
        """A real critical module with the merge's line appended is caught."""
        real = next(p for p in _modules()
                    if "pytest.mark.critical" in p.read_text() and not rebindings(p.read_text()))
        broken = real.read_text() + "\npytestmark = pytest.mark.asset('quarterly')\n"
        assert rebindings(broken), real


pytestmark = [pytest.mark.critical, pytest.mark.asset("quarterly")]
