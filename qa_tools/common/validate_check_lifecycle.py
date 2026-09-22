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

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from qa_tools.common import check_id as cid
from qa_tools.common import check_lifecycle as cl

ROOT = Path(__file__).resolve().parent.parent.parent

# The same YAML files Phase 1's real retrofit covers - kept as a plain
# list here (not derived from anything dynamic) so a brand-new dataset's
# check files just get added to this list, same as Phase 1's own
# retrofit was itself a manual, deliberate act per dataset.
_YAML_SOURCES = [
    ("dbt_project/models/staging/schema.yml", cl.parse_dbt_check_metadata),
    ("dbt_project/schema-retired.yml", cl.parse_dbt_check_metadata),
    ("contract/bdm-birth-registrations-soda-checks.yml", cl.parse_soda_check_metadata),
    ("contract/bdm-birth-registrations-soda-checks-retired.yml", cl.parse_soda_check_metadata),
    ("contract/child-protection-soda-checks.yml", cl.parse_soda_check_metadata),
    ("contract/child-protection-soda-checks-retired.yml", cl.parse_soda_check_metadata),
    ("contract/bdm-birth-registrations-contract.yaml", cl.parse_contract_check_metadata),
    ("contract/bdm-birth-registrations-contract-retired.yaml", cl.parse_contract_check_metadata),
    ("contract/child-protection-contract.yaml", cl.parse_contract_check_metadata),
    ("contract/child-protection-contract-retired.yaml", cl.parse_contract_check_metadata),
]
_EVIDENTLY_SOURCES = [
    "qa_tools/bdm/evidently_check_lifecycle.py",
    "qa_tools/bdm/evidently_check_lifecycle_retired.py",
    "qa_tools/cp/evidently_check_lifecycle.py",
    "qa_tools/cp/evidently_check_lifecycle_retired.py",
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
    (e.g. `"HEAD~1"`). A source path missing at `ref=None` reads as "no
    checks from it" too, same as a path that didn't exist yet at an old
    ref - each tool's own `-retired` sibling file (schema-retired.yml
    etc., see their own header comments) is a genuinely optional source
    until a real project's first check ever gets retired, so this can't
    assume every listed path already exists on disk."""
    checks: list[cl.CheckMetadata] = []
    for rel_path, parser in _YAML_SOURCES:
        if ref is None:
            if not (ROOT / rel_path).exists():
                continue
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
            if not (ROOT / rel_path).exists():
                continue
            with open(ROOT / rel_path) as f:
                source = f.read()
        else:
            source = _old_file_content(rel_path, ref)
            if source is None:
                continue
        checks.extend(cl.parse_evidently_check_metadata(
            _evidently_dict_from_source(source, rel_path), source=rel_path))

    return checks


def _check_id_errors(checks: list[cl.CheckMetadata]) -> list[str]:
    """REQ-QAC-023's three gates plus REQ-QAC-039's fourth, all on the
    CURRENT tree only - unlike the changelog rule above there is no
    old-vs-new comparison to make; a check_id either matches the grammar
    and the hierarchy or it does not.

    Kept here, beside the existing gate, rather than in a separate
    command: a contributor who broke one of these broke the same thing
    the other rules protect, and finding that out in two places is
    worse than finding it out in one."""
    ids = [c.check_id for c in checks]
    errors = cid.validate_grammar(ids)
    errors += cid.validate_tail_uniqueness(ids)
    # REQ-QAC-039: shaped right is not the same as meaning something.
    # An id naming an agency or collection the dataset does not sit
    # under passes the grammar and resolves to nothing.
    errors += cid.validate_hierarchy_agreement(ids)
    for rel_path, parser in _YAML_SOURCES:
        if parser is not cl.parse_contract_check_metadata:
            continue  # only the ODCS contracts attach rules to a column
        if not (ROOT / rel_path).exists():
            continue
        errors += cid.validate_column_matches(cl.contract_rule_attachments(ROOT / rel_path))
    return errors


def _looks_like_sentinel(value: str) -> bool:
    """True for a value that MEANS the sentinel but is not spelled as
    it - "self evident", "Self_Evident", "selfevident". Letters only,
    lowercased, so spacing, punctuation and case all collapse."""
    return re.sub(r"[^a-z]", "", value.lower()) == "selfevident"


def _explanation_errors(checks: list[cl.CheckMetadata]) -> list[str]:
    """REQ-QAC-025: no check ships without a plain-English explanation.

    Two separate requirements, both reported in the same pass so a
    contributor fixing a batch sees the whole list rather than one at a
    time:

    - every check states what it VERIFIES (`description`);
    - every check either states what a failure INDICATES, or declares
      explicitly that the cause is self-evident from what it verifies.

    An absent `failure_indicates` is neither of those - it is a field
    nobody filled in, and the whole point of the `self-evident`
    sentinel is to make a deliberate decision distinguishable from an
    unfilled one.

    RETIRED CHECKS ARE INCLUDED, on the same terms as active ones. An
    earlier version of this exempted them, reasoning that they are
    history nobody reads - but REQ-QAC-025 says otherwise in as many
    words, and it is right: a retired check still renders in the
    dashboard behind the retired-checks toggle, so a reader can still
    meet its prose. There is exactly one retired check today and it was
    authored rather than excused.

    `technical_note` is never required (REQ-QAC-025 again) - it is
    sparse by design.
    """
    errors = []
    for c in sorted(checks, key=lambda c: c.check_id):
        if not (c.description or "").strip():
            errors.append(
                f"{c.check_id}: no description. Every check must say in plain English "
                f"what it verifies - see docs/check-authoring-rules.md")
        value = (c.failure_indicates or "").strip()
        if not value:
            errors.append(
                f"{c.check_id}: no failure_indicates. Author one, or set it to "
                f"'{cl.SELF_EVIDENT}' if the cause adds nothing to what the check "
                f"verifies - see docs/check-authoring-rules.md")
        elif _looks_like_sentinel(value) and not cl.is_self_evident(value):
            # Any non-empty value satisfies the rule above, so a
            # near-miss spelling passes the gate AND renders verbatim on
            # a public page - "self evident" under a heading, which is
            # the exact leak the template's own normalisation prevents
            # for the correct spelling. Caught here because the gate is
            # the only layer that can tell a typo from real prose.
            errors.append(
                f"{c.check_id}: failure_indicates is {value!r}, which reads as the "
                f"sentinel but is not it. Spell it exactly '{cl.SELF_EVIDENT}' - "
                f"anything else is treated as authored prose and rendered as-is "
                f"on the published page.")
    return errors


def main(require_explanations: bool = False) -> int:
    old_checks = collect_checks("HEAD~1")
    new_checks = collect_checks(None)
    errors = cl.validate(old_checks, new_checks) + _check_id_errors(new_checks)

    # Always counted, only sometimes fatal. The counting half was what
    # made REQ-QAC-024's authoring pass tractable - "257 checks to
    # write" became a number that visibly moved - and it stays useful
    # for anyone running the command locally mid-change.
    unauthored = _explanation_errors(new_checks)
    if require_explanations:
        errors += unauthored
    elif unauthored:
        print(f"  note: {len(unauthored)} plain-English explanation(s) missing "
              f"(REQ-QAC-025). Not failing the build - pass "
              f"--require-explanations to make this a gate.", file=sys.stderr)

    if errors:
        print(f"check-lifecycle validation FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"check-lifecycle validation OK - {len(new_checks)} checks "
          f"({len(old_checks)} in the previous commit), zero errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--require-explanations" in sys.argv[1:]))
