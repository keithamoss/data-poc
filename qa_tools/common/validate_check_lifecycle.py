"""
Phase 3's CI gate step for Thread D (plans/publishing-and-history.md):
parses every real check definition across all 4 tools x both datasets,
at both the current working tree ("new") and the immediately-previous
commit ("old" - Keith's call, 2026-09-16: the previous commit on the
pushed branch, not whatever's currently live on GitHub Pages - simplest,
no extra state to track, and catches "changed without a changelog entry
in the same commit" which is the more useful thing anyway), and runs
check_lifecycle.validate() between them. Fails loudly (nonzero exit,
every error listed) if any check_id is duplicated or any check's config
changed without a new changelog entry - the actual CI gate, not just a
check someone has to remember to run locally.

"Old" doesn't exist for a file that's brand new in this push (e.g. a
new dataset's first check-definition file) - `git show <ref>:<path>`
fails for a path that didn't exist at that ref, treated as "no old
checks from that file" rather than an error (nothing to have changed
FROM - matches check_lifecycle.find_undocumented_changes()'s own
"brand new check_id" exemption).

Run as `python3 -m qa_tools.common.validate_check_lifecycle` from a git
checkout with at least 2 commits of history (`fetch-depth: 2` in CI).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from qa_tools.common import check_lifecycle as cl

ROOT = Path(__file__).resolve().parent.parent.parent

# The same YAML files Phase 1's real retrofit covers - kept as a plain
# list here (not derived from anything dynamic) so a brand-new dataset's
# check files just get added to this list, same as Phase 1's own
# retrofit was itself a manual, deliberate act per dataset.
_YAML_SOURCES = [
    ("dbt_project/models/staging/schema.yml", cl.parse_dbt_check_metadata),
    ("contract/bdm-birth-registrations-soda-checks.yml", cl.parse_soda_check_metadata),
    ("contract/child-protection-soda-checks.yml", cl.parse_soda_check_metadata),
    ("contract/bdm-birth-registrations-contract.yaml", cl.parse_contract_check_metadata),
    ("contract/child-protection-contract.yaml", cl.parse_contract_check_metadata),
]
_EVIDENTLY_SOURCES = [
    "qa_tools/bdm/evidently_check_lifecycle.py",
    "qa_tools/cp/evidently_check_lifecycle.py",
]


def _old_file_content(rel_path: str, ref: str) -> str | None:
    """The file's content at `ref`, or None if it didn't exist there yet."""
    result = subprocess.run(["git", "show", f"{ref}:{rel_path}"], cwd=ROOT,
                             capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout


def _evidently_dict_from_source(source: str, filename: str) -> dict:
    """Evidently's lifecycle metadata is a plain Python dict literal, not
    YAML - no file-format parser to reuse, so this evals the module's own
    source text (trusted - our own repo content at a real git ref, same
    trust level as importing the file directly) and pulls out
    CHECK_LIFECYCLE, without needing to actually import a whole second
    copy of the module via importlib machinery."""
    namespace: dict = {}
    exec(compile(source, filename, "exec"), namespace)
    return namespace.get("CHECK_LIFECYCLE", {})


def collect_checks(ref: str | None) -> list[cl.CheckMetadata]:
    """`ref=None` means the current working tree; otherwise a git ref
    (e.g. `"HEAD~1"`)."""
    checks: list[cl.CheckMetadata] = []
    for rel_path, parser in _YAML_SOURCES:
        if ref is None:
            checks.extend(parser(ROOT / rel_path))
            continue
        content = _old_file_content(rel_path, ref)
        if content is None:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as f:
            f.write(content)
            tmp_path = f.name
        checks.extend(parser(tmp_path))

    for rel_path in _EVIDENTLY_SOURCES:
        if ref is None:
            with open(ROOT / rel_path) as f:
                source = f.read()
        else:
            source = _old_file_content(rel_path, ref)
            if source is None:
                continue
        checks.extend(cl.parse_evidently_check_metadata(
            _evidently_dict_from_source(source, rel_path), source=rel_path))

    return checks


def main() -> int:
    old_checks = collect_checks("HEAD~1")
    new_checks = collect_checks(None)
    errors = cl.validate(old_checks, new_checks)

    if errors:
        print(f"check-lifecycle validation FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"check-lifecycle validation OK - {len(new_checks)} checks "
          f"({len(old_checks)} in the previous commit), zero errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
