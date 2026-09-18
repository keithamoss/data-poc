"""
CI gate for requirements.yaml (item 75, plans/qa-pipeline.md) - Keith's
own scoping call was "enforced ID-based linkage" to real tests, not a
decorative reference: this fails loudly (nonzero exit) if the file's
own schema is violated, if any `id` is duplicated, if a `built`
requirement has zero `linked_tests`, or if any `linked_tests` entry
doesn't resolve to something real - a plain file for a `tests-js/*.js`
entry, or (for a `path.py::Name` / `path.py::Class::name` pytest node
id) an actual function/method definition found by parsing that file's
real AST, not just a string match. A requirement claiming to be
verified by a test that doesn't exist is exactly the failure mode this
whole feature exists to prevent.

Run as `python3 -m qa_tools.common.validate_requirements` from the repo
root (no git history needed, unlike validate_check_lifecycle.py - this
only ever validates the CURRENT working tree's requirements.yaml
against the CURRENT working tree's test files, there's no "old vs new"
comparison here).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from dashboard.requirements_yaml import parse_requirements

ROOT = Path(__file__).resolve().parent.parent.parent
REQUIREMENTS_YAML = ROOT / "requirements.yaml"

_ID_RE = re.compile(r"^REQ-\d{3}$")
_VALID_MOSCOW = {"must", "should", "could", "wont"}
_VALID_STATUS = {"not_started", "in_progress", "built"}


def _python_test_exists(rel_path: str, qualname: list[str]) -> bool:
    """qualname is ["function"] or ["Class", "method"] - real AST parse
    of the referenced file (never a regex/string match, which could be
    fooled by a comment or a docstring mentioning the same name)."""
    full_path = ROOT / rel_path
    if not full_path.exists():
        return False
    try:
        tree = ast.parse(full_path.read_text())
    except SyntaxError:
        return False

    if len(qualname) == 1:
        # A bare module-level function ("file.py::test_x") OR a bare
        # class ("file.py::TestX", real pytest shorthand for "any test
        # in this class") - both are real, legitimate single-segment
        # references.
        name = qualname[0]
        return any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name
            for node in tree.body
        )
    if len(qualname) == 2:
        class_name, method_name = qualname
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return any(
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name
                    for item in node.body
                )
        return False
    return False  # a deeper qualname than this project's own tests ever use


def _linked_test_exists(entry: str) -> bool:
    """A `tests-js/*.js` entry (no `::`) - real file existence only, JS
    tests don't get the same AST-level node-id check Python ones do
    (Vitest has no equivalent stable "node id" convention this project
    already relies on elsewhere). A `path.py` or `path.py::qual::name`
    entry - real file existence, plus a real AST-verified definition
    for the `::`-qualified form."""
    if "::" in entry:
        file_part, *qualname = entry.split("::")
        if not file_part.endswith(".py"):
            return False
        return _python_test_exists(file_part, qualname)
    full_path = ROOT / entry
    return full_path.exists()


def validate(requirements: list[dict]) -> list[str]:
    """Pure function, no file I/O of its own (except each linked_tests
    entry's own real existence check) - testable directly against
    fixture data, same pattern as qa_tools.common.check_lifecycle."""
    errors: list[str] = []
    seen_ids: dict[str, int] = {}

    for i, r in enumerate(requirements):
        where = r.get("id") or f"entry #{i + 1} (no id)"

        rid = r.get("id", "")
        if not _ID_RE.match(rid):
            errors.append(f"{where}: id {rid!r} doesn't match ^REQ-\\d{{3}}$")
        else:
            seen_ids[rid] = seen_ids.get(rid, 0) + 1

        if not (r.get("title") or "").strip():
            errors.append(f"{where}: missing/empty title")
        if not (r.get("story") or "").strip():
            errors.append(f"{where}: missing/empty story")

        moscow = r.get("moscow")
        if moscow not in _VALID_MOSCOW:
            errors.append(f"{where}: moscow {moscow!r} not one of {sorted(_VALID_MOSCOW)}")

        status = r.get("status")
        if status not in _VALID_STATUS:
            errors.append(f"{where}: status {status!r} not one of {sorted(_VALID_STATUS)}")

        acceptance = r.get("acceptance_criteria") or []
        if not acceptance or not all((c or "").strip() for c in acceptance):
            errors.append(f"{where}: acceptance_criteria must have at least 1 non-empty entry")

        linked = r.get("linked_tests") or []
        if status == "built" and not linked:
            errors.append(f"{where}: status is 'built' but linked_tests is empty - "
                           f"a built requirement needs at least one real test verifying it")
        for entry in linked:
            if not _linked_test_exists(entry):
                errors.append(f"{where}: linked_tests entry {entry!r} does not resolve to a real "
                               f"file/test")

    for rid, count in seen_ids.items():
        if count > 1:
            errors.append(f"id {rid!r} is used {count} times - ids must be globally unique")

    return errors


def main() -> int:
    requirements = parse_requirements(REQUIREMENTS_YAML)
    errors = validate(requirements)

    if errors:
        print(f"requirements validation FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"requirements validation OK - {len(requirements)} requirements, zero errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
