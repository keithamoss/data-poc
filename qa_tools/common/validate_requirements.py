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
import re
import sys
from pathlib import Path

from dashboard.requirements_yaml import parse_requirements

ROOT = Path(__file__).resolve().parent.parent.parent
REQUIREMENTS_YAML = ROOT / "requirements.yaml"

# Single source of truth for the id's own middle component code - the
# same 7-part taxonomy plans/*.md items and CHANGELOG.md entries tag
# things with (dashboard/qa-reporting-dashboard.template.html's own
# `COMPONENT_ICON`/`PLANS_ALL_COMPONENTS` consts), just condensed to
# 3-4 letters for the id. Keep this dict and those two consts in sync
# by hand if the taxonomy itself ever changes - nothing currently
# cross-checks them against each other.
_COMPONENT_CODES = {
    "GEN": "Data generation",
    "QAC": "QA checks & contract",
    "PIPE": "Pipeline & publishing",
    "DASH": "Dashboard UI",
    "GHUB": "GitHub workflow & people",
    "TEST": "Testing & dev tooling",
    "DOCS": "Docs & process",
}
# "REQ-<CODE>-NNN" only - the old bare "REQ-NNN" shape is no longer
# valid, see this module's own docstring for the same-day migration.
_ID_RE = re.compile(r"^REQ-(?:" + "|".join(_COMPONENT_CODES) + r")-\d{3}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
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


def _valid_string_list(value, field_name: str, where: str) -> list[str]:
    """Real validation shared by all 4 optional list-of-strings fields
    (non_functional_requirements/dependencies/open_questions/evidence):
    absent/empty is fine (all 4 are optional), but if present, must be
    a real list of non-empty strings - a stray `null` entry or a bare
    string instead of a list is a real authoring mistake, not silently
    accepted."""
    if value is None:
        return []
    errors = []
    if not isinstance(value, list):
        errors.append(f"{where}: {field_name} must be a list, got {type(value).__name__}")
        return errors
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            errors.append(f"{where}: {field_name} entries must be non-empty strings, got {entry!r}")
    return errors


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
            errors.append(
                f"{where}: id {rid!r} doesn't match ^REQ-({'|'.join(_COMPONENT_CODES)})-\\d{{3}}$"
            )
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

        # dashboard/requirements_yaml.py's own parser defaults an unset
        # `source` to `""` (falsy), not `None` - `main()` below always
        # runs against parser output, so this must treat a real, unset
        # default the same as genuinely absent, only flagging an
        # actually-present-but-invalid value (whitespace-only, or a
        # non-string).
        source = r.get("source")
        if source and (not isinstance(source, str) or not source.strip()):
            errors.append(f"{where}: source, if present, must be a non-empty string")

        # Same "permissive if absent, strict if present" treatment as
        # `source` - dashboard/requirements_yaml.py's own parser also
        # defaults an unset `date_written` to `""`.
        date_written = r.get("date_written")
        if date_written and (not isinstance(date_written, str) or not _DATE_RE.match(date_written)):
            errors.append(f"{where}: date_written {date_written!r}, if present, must be a real "
                           f"\"YYYY-MM-DD\" date")

        for field_name in ("non_functional_requirements", "open_questions", "evidence"):
            errors.extend(_valid_string_list(r.get(field_name), field_name, where))

        # dependencies gets the same "is it a real list of strings" check
        # as the other 3, PLUS its own extra rule below (each entry must
        # actually exist as a real REQ-id in this same file) - same
        # "dangling reference is a real error" treatment linked_tests
        # already gets, checked once every id is known (after this loop).
        errors.extend(_valid_string_list(r.get("dependencies"), "dependencies", where))

    for rid, count in seen_ids.items():
        if count > 1:
            errors.append(f"id {rid!r} is used {count} times - ids must be globally unique")

    all_ids = set(seen_ids)
    for i, r in enumerate(requirements):
        where = r.get("id") or f"entry #{i + 1} (no id)"
        for dep in r.get("dependencies") or []:
            if isinstance(dep, str) and dep not in all_ids:
                errors.append(f"{where}: dependencies entry {dep!r} does not match any real "
                               f"requirement id in this file")

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
