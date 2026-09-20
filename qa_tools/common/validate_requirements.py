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

Extended 2026-09-19 (plans/wider.md #10, the requirements-analysis
agents work) with 6 further optional fields - see requirements.yaml's
own header comment for the full field-by-field rationale. `source`/
`non_functional_requirements`/`open_questions`/`evidence` are each
real-but-permissive (absent is fine; if present, must be a non-empty
string or a list of them). `dependencies` gets one further real check:
every entry must resolve to an actual requirement id elsewhere in this
same file - a dangling reference is a real error, the same treatment
`linked_tests` already gets. `date_written`, if present, must be a real
"YYYY-MM-DD" date.

Extended again the same day (Keith's own follow-up ask) with a real
middle component code in the id itself: every id is now `REQ-<CODE>-NNN`
where `<CODE>` is one of `_COMPONENT_CODES` below - the same 7-part
component taxonomy plans/*.md items and CHANGELOG.md entries already
tag things with, just condensed to 3-4 letters. The bare legacy
`REQ-NNN` shape is no longer valid at all, by Keith's own explicit
follow-up call (drop it entirely rather than grandfather it) - the 22
pre-2026-09-19 entries were migrated to the new shape the same day,
each keeping its own original NNN and picking up whichever real
component code best matches it (see requirements.yaml's own header
comment for the full reasoning and the migration note).

Run as `python3 -m qa_tools.common.validate_requirements` from the repo
root (no git history needed, unlike validate_check_lifecycle.py - this
only ever validates the CURRENT working tree's requirements.yaml
against the CURRENT working tree's test files, there's no "old vs new"
comparison here).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from pydantic import ValidationError

from dashboard.requirements_yaml import parse_requirements
from qa_tools.common.schemas import Requirement, format_error
from qa_tools.common.vocab import COMPONENT_CODES

ROOT = Path(__file__).resolve().parent.parent.parent
REQUIREMENTS_YAML = ROOT / "requirements.yaml"

# The taxonomy itself moved to qa_tools/common/vocab.py (2026-09-20)
# so the declared schema and this validator can both use it without
# importing each other in a circle. Re-exported under its old private
# name because tests/test_component_taxonomy_consistency.py and
# validate_changelog.py both import it from here - that test is what
# fails CI if this, the dashboard's own two consts and
# docs/components.md ever disagree.
_COMPONENT_CODES = COMPONENT_CODES


def _python_symbol_exists(rel_path: str, qualname: list[str]) -> bool:
    """qualname is ["function"] or ["Class", "method"] - real AST parse
    of the referenced file (never a regex/string match, which could be
    fooled by a comment or a docstring mentioning the same name).

    Used by BOTH `linked_tests` and `implemented_by` (2026-09-20). It was
    named `_python_test_exists` while tests were its only caller; the
    mechanism was never test-specific, and pointing it at production
    code is exactly what makes `implemented_by` worth more than a path."""
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
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == name:
                    return True
            # A module-level CONSTANT is a symbol too, and worth pinning
            # for the same reason a function is - delete it and the
            # requirement claiming it should break. Added 2026-09-20,
            # found by the gate itself: qa_tools/common/vocab.py is
            # purely constants, so a bare path was rejected (rightly)
            # and no symbol was acceptable (wrongly).
            elif isinstance(node, ast.Assign):
                if any(isinstance(tgt, ast.Name) and tgt.id == name for tgt in node.targets):
                    return True
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == name:
                    return True
        return False
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
        return _python_symbol_exists(file_part, qualname)
    full_path = ROOT / entry
    return full_path.exists()


# Files whose symbols this toolchain can actually verify, and files
# where a bare path is the honest limit of what it can claim.
#
# Keith's call, 2026-09-20: Python MUST name a symbol; front-end code may
# be a bare path "for now - for the HTML we'll probably end up with a
# separate TypeScript or JavaScript file, and maybe we can take it up
# later". A `::` on a `.html` file IS allowed and IS verified, just not
# here - tests-js/implemented_by.test.js loads the real template into jsdom
# and checks the symbol actually resolves, which is stronger than an AST
# parse because it is real execution rather than a reading of the source.
_FRONT_END_SUFFIXES = (".html", ".js", ".ts")


def _implemented_by_errors(entry: str, where: str) -> list[str]:
    """One `implemented_by` entry: a path, or `path::Symbol` /
    `path::Class::method`.

    The asymmetry between Python and everything else is deliberate and
    is the whole point of the field. `Path.exists()` stays green while a
    module is gutted, stubbed, or renamed-and-recreated - which is
    precisely how `touches:` lines in plans/*.md rotted while continuing
    to look authoritative. An AST-verified symbol cannot: delete
    `parse_contract_check_metadata` and CI names the requirement that
    claimed it."""
    file_part, *qualname = entry.split("::")
    if not (ROOT / file_part).exists():
        return [f"{where}: implemented_by entry {entry!r} names a file that does not exist"]
    if file_part.endswith(".py"):
        if not qualname:
            return [f"{where}: implemented_by entry {entry!r} is a bare Python path - "
                    f"name a symbol (file.py::function or file.py::Class::method), "
                    f"since a path alone stays valid while the code inside it goes away"]
        if not _python_symbol_exists(file_part, qualname):
            return [f"{where}: implemented_by entry {entry!r} names no real "
                    f"function/class/method in that file"]
        return []
    if qualname and not file_part.endswith(_FRONT_END_SUFFIXES):
        return [f"{where}: implemented_by entry {entry!r} qualifies a {Path(file_part).suffix or 'n extensionless'} "
                f"file with '::' - nothing verifies that, and an unchecked claim in a "
                f"checked field is worse than a plain path"]
    return []


def _schema_errors(raw: list[dict]) -> tuple[list[str], list[Requirement]]:
    """Validates each entry against the declared schema, returning error
    strings and the entries that parsed.

    Every entry is tried even after one fails, so an author fixing a
    batch sees the whole list rather than one problem per run - which is
    why this catches ValidationError per entry rather than validating
    the document in one go."""
    errors: list[str] = []
    ok: list[Requirement] = []
    for i, entry in enumerate(raw):
        where = entry.get("id") or f"entry #{i + 1} (no id)"
        try:
            ok.append(Requirement(**entry))
        except ValidationError as e:
            errors.extend(format_error(err, where) for err in e.errors())
    return errors, ok


def _cross_reference_errors(requirements: list[Requirement]) -> list[str]:
    """The half no schema library can express - claims checked against
    the real codebase and against the rest of the document.

    A schema can say `linked_tests` is a list of strings. Only this can
    say that `tests/test_x.py::TestY::test_z` names a method that really
    exists, which is the difference between a decorative reference and
    an enforced one."""
    errors: list[str] = []
    all_ids = {r.id for r in requirements}

    seen: dict[str, int] = {}
    for r in requirements:
        seen[r.id] = seen.get(r.id, 0) + 1
    for rid, count in seen.items():
        if count > 1:
            errors.append(f"id {rid!r} is used {count} times - ids must be globally unique")

    for r in requirements:
        for field in r.missing_when_built():
            errors.append(f"{r.id}: status is 'built' but {field} is empty")

        for entry in r.linked_tests:
            if not _linked_test_exists(entry):
                errors.append(f"{r.id}: linked_tests entry {entry!r} does not resolve to a real "
                               f"file/test")
        for entry in r.implemented_by:
            errors.extend(_implemented_by_errors(entry, r.id))
        for dep in r.dependencies:
            if dep not in all_ids:
                errors.append(f"{r.id}: dependencies entry {dep!r} does not match any real "
                               f"requirement id in this file")
    return errors


def validate(requirements: list[dict]) -> list[str]:
    """Schema first, then cross-references against the real codebase.

    Restructured 2026-09-20 (REQ-DOCS-029). What used to be ~90 lines of
    hand-written field checks is now a declaration in
    `qa_tools/common/schemas.py`; what remains here is everything a
    schema genuinely cannot do."""
    errors, parsed = _schema_errors(requirements)
    return errors + _cross_reference_errors(parsed)


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
