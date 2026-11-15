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

THIS IS THE GIT-REF HALF (REQ-PIPE-380 criterion 12): reading a check file
AT A REF - git show, git ls-tree - stays here. Where the checks are defined,
the dbt-SQL scan and the WORKING-TREE read are asset_model/check_sources.py,
which the generator reads checks through too; this module hands its ref's
file contents to the same sources() and dbt_definitions(), so there is one
parser, and the cut sits at git because asset_model/ runs none.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from asset_model import assets, check_sources
from asset_model import check_id as cid
from asset_model import check_lifecycle as cl
from qa_tools.common.diff_base import diff_base

ROOT = Path(__file__).resolve().parent.parent.parent

def _sources(ref: str | None) -> tuple[list[tuple[str, object]], list[str]]:
    """Every file the checks at `ref` are defined in - `[(path, parser)]`
    for the YAML tools and `[path]` for Evidently - derived from THAT ref's
    own hierarchy (REQ-QAC-241 criteria 7 and 8): each collection's
    contract, Soda, Evidently and dbt schema files with their retired
    siblings, plus contract/file-checks.yaml. A new collection's files are
    found without a line here.

    Grouped by tool in a fixed order - dbt, Soda, contracts, file checks,
    Evidently - the order the hand-written list had, so nothing that lists
    checks moves."""
    from asset_model import hierarchy

    if ref is not None:
        # A READ AT A GIT REF names the files by repository path, which a
        # folder outside the repository has none of: refused, never read as
        # "no checks" (C7, REQ-PIPE-342 decision 18).
        assets.folder_rel()
        assets.dbt_rel()
    asset = hierarchy.data_asset_yaml()
    rel_asset = asset.relative_to(ROOT).as_posix() if asset.is_relative_to(ROOT) else None
    text = asset.read_text() if ref is None or rel_asset is None else _old_file_content(rel_asset, ref)
    return check_sources.sources(text)


def _yaml_outside_synthetic(folder: Path):
    """Every YAML file under an asset folder, never descending into its
    synthetic/ folder - which is not listed, let alone read."""
    for entry in sorted(folder.iterdir()):
        if entry.name == "synthetic":
            continue
        if entry.is_dir():
            yield from entry.rglob("*.y*ml")
        elif entry.is_file() and entry.match("*.y*ml"):
            yield entry


def sources_fingerprint() -> str:
    """A digest of every file the working tree's checks are collected from -
    each collection's check files and dbt folders, the shared dbt SQL - and
    of contract/ as a whole (a parser may consult the asset file or the
    hierarchy): what REQ-PIPE-192's declarations are keyed on, so an edit to
    any of them is seen however small (REQ-QAC-241 criterion 11). Read,
    never parsed."""
    import hashlib

    from asset_model import collections

    digest = hashlib.sha256(str(ROOT).encode())
    yaml_sources, evidently = _sources(None)
    paths = [ROOT / rel for rel, _parser in yaml_sources]
    paths += [ROOT / rel for rel in evidently]
    dirs = list(collections.SHARED_DBT_DIRS)
    for c in collections.all_collections():
        dirs += [c.dbt_models, c.dbt_tests]
    for rel_dir in dirs:
        if (ROOT / rel_dir).is_dir():
            paths += sorted(p for p in (ROOT / rel_dir).rglob("*") if p.is_file())
    contract = ROOT / assets.folder_on_disk()
    if contract.is_dir():
        # NOT ITS synthetic/ FOLDER (REQ-GEN-370 criterion 3, post-build-review
        # #337): no check is collected from synthetic-only configuration, and
        # the checks read nothing there - listing it was the staging step
        # reading scripted_decisions.yaml.
        paths += sorted(p for p in _yaml_outside_synthetic(contract))
    for path in dict.fromkeys(paths):
        digest.update(str(path).encode())
        try:
            digest.update(path.read_bytes())
        except FileNotFoundError:
            digest.update(b"\0missing")
    return digest.hexdigest()


def _old_file_content(rel_path: str, ref: str | None) -> str | None:
    """The file's content at `ref`, or None if it didn't exist there yet.

    `ref=None` reads the WORKING TREE - the one reader every source file a
    definition hash covers goes through, at either side of the comparison
    (REQ-QAC-223 criterion 4)."""
    if ref is None:
        path = ROOT / rel_path
        return path.read_text() if path.is_file() else None
    return _git_show(rel_path, ref)


def _git_show(rel_path: str, ref: str) -> str | None:
    result = subprocess.run(["git", "show", f"{ref}:{rel_path}"], cwd=ROOT,
                             capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout


def _dbt_singular_dir(ref: str | None = None) -> str:
    # At a git ref, a repository path - refused outside it (C7).
    return f"{assets.dbt_on_disk() if ref is None else assets.dbt_rel()}/tests"


def _files_in(rel_dir: str, ref: str | None) -> list[str]:
    """The .sql files anywhere under `rel_dir`, at `ref` or in the working
    tree (check_sources.sql_files_in, at None)."""
    if ref is None:
        return check_sources.sql_files_in(rel_dir, ROOT)
    result = subprocess.run(["git", "ls-tree", "-r", "--name-only", f"{ref}:{rel_dir}"], cwd=ROOT,
                            capture_output=True, text=True)
    if result.returncode != 0:
        # A folder new since `ref` held no files there.
        return []
    return sorted(f"{rel_dir}/{n}" for n in result.stdout.split() if n.endswith(".sql"))


def dbt_definitions(ref: str | None) -> "cl.DbtDefinition":
    """What `parse_dbt_check_metadata(definition=...)` reads at one ref - the
    one scan (check_sources.dbt_definitions) over this ref's files."""
    return check_sources.dbt_definitions(lambda rel: _old_file_content(rel, ref),
                                         lambda rel_dir: _files_in(rel_dir, ref),
                                         _dbt_singular_dir(ref))


def _dbt_kwargs(parser, ref: str | None) -> dict:
    """A dbt parser is given the project SQL as it stood at the SAME ref as
    the YAML it parses, so both sides of the comparison see their own."""
    return {"definition": dbt_definitions(ref)} if parser is cl.parse_dbt_check_metadata else {}


def collect_checks(ref: str | None) -> list[cl.CheckMetadata]:
    """`ref=None` means the current working tree; otherwise a git ref
    (e.g. `"HEAD~1"`). A source path missing at either reads as "no checks
    from it", same as a path that didn't exist yet at an old ref - each
    tool's own `-retired` sibling file is a genuinely optional source.

    THE WORKING-TREE READ IS asset_model/check_sources.py (REQ-PIPE-380
    criterion 12, 380 Q1 (a) SETTLED by Keith 2026-11-14), so the generator
    reads checks exactly as this gate does; reading a check file AT A REF -
    git - is this half's, and stays here."""
    yaml_sources, evidently = _sources(ref)
    if ref is None:
        return check_sources.collect_working_tree(yaml_sources, evidently, ROOT)
    checks: list[cl.CheckMetadata] = []
    for rel_path, parser in yaml_sources:
        content = _old_file_content(rel_path, ref)
        if content is None:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False) as f:
            f.write(content)
            tmp_path = f.name
        # THE OLD SIDE AS IT WAS: a rule added since applies to the tree now.
        past = {"past": True} if parser is cl.parse_contract_check_metadata else {}
        checks.extend(parser(tmp_path, **past, **_dbt_kwargs(parser, ref)))

    for rel_path in evidently:
        source = _old_file_content(rel_path, ref)
        if source is None:
            continue
        checks.extend(cl.parse_evidently_check_metadata(
            cl.evidently_checks_from_text(source, rel_path), source=rel_path))

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
    for rel_path, parser in _sources(None)[0]:
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


def _by_source_file(errors: list[str], old_checks, new_checks, base) -> list[str]:
    """ONE EDITED FILE, ONE FAILURE (REQ-QAC-223 criterion 7). A shared macro
    backs many checks - matches_regex.sql backs 11 - so an edit to it would
    otherwise fail the gate once per check. Where an edited project file
    moved more than one undocumented check, those checks' messages become one
    naming the file and listing them; a file behind a single check keeps that
    check's own message."""
    undocumented = set(cl.find_undocumented_changes(old_checks, new_checks))
    if not undocumented:
        return errors
    files: dict[str, list[str]] = {}
    for c in new_checks:
        if c.check_id in undocumented:
            for f in c.definition_files:
                files.setdefault(f, []).append(c.check_id)
    grouped: list[str] = []
    covered: set[str] = set()
    for f, ids in sorted(files.items()):
        ids = sorted(set(ids) - covered)
        if len(ids) < 2 or _old_file_content(f, base) == _old_file_content(f, None):
            continue
        covered |= set(ids)
        grouped.append(f"{f} changed without a new changelog entry on the {len(ids)} checks it "
                       "defines: " + ", ".join(repr(i) for i in ids))
    kept = [e for e in errors
            if not any(e == f"Check config changed without a new changelog entry: {i!r}" for i in covered)]
    return grouped + kept


#: The frozen-defaults table (REQ-QAC-176 criterion 10), read as text at
#: either ref so the gate can compare the two sides without importing either.
FROZEN_DEFAULTS_FILE = "asset_model/frozen_defaults.py"


def frozen_defaults_at(ref: str | None) -> tuple[dict, ...]:
    """FROZEN_DEFAULTS as the file stood at `ref` (None: the working tree),
    read with ast.literal_eval - empty where the file did not exist yet."""
    import ast

    text = _old_file_content(FROZEN_DEFAULTS_FILE, ref)
    if text is None:
        return ()
    for node in ast.parse(text).body:
        target = (node.target if isinstance(node, ast.AnnAssign) else
                  node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1
                  else None)
        if isinstance(target, ast.Name) and target.id == "FROZEN_DEFAULTS":
            return tuple(ast.literal_eval(node.value))
    raise ValueError(f"{FROZEN_DEFAULTS_FILE} at {ref or 'the working tree'} defines no "
                     "FROZEN_DEFAULTS literal")


def _setting_at(settings: dict, path) -> tuple[bool, object]:
    here: object = settings
    for key in path:
        if not isinstance(here, dict) or key not in here:
            return False, None
        here = here[key]
    return True, here


def _describe_entry(index: int, entry: dict) -> str:
    return (f"frozen default #{index} ({entry.get('tool')} {'.'.join(map(str, entry.get('path') or []))}"
            f"{' for ' + str(entry['kind']) if entry.get('kind') else ''} = {entry.get('value')!r}, "
            f"{entry.get('scheme')})")


def frozen_default_errors(old_table, new_table, old_checks) -> list[str]:
    """REQ-QAC-176 criterion 11, both refusals, each naming the entry: an
    existing entry changed or removed, except as a new entry under a new
    scheme version; and a new entry naming a setting some check at the diff
    base writes at that same value, naming each check it would move."""
    from asset_model import check_fingerprint as fp

    errors: list[str] = []
    for i, entry in enumerate(new_table):
        missing = [k for k in ("tool", "path", "kind", "value", "scheme") if k not in entry]
        if missing or entry.get("scheme") not in fp.SCHEMES or not isinstance(entry.get("path"), list):
            errors.append(f"{_describe_entry(i, entry)} is malformed - each entry gives tool, "
                          f"path (a list of keys), kind, value and a kept scheme "
                          f"({', '.join(fp.SCHEMES)})")
    kept = 0
    for i, entry in enumerate(old_table):
        if i < len(new_table) and fp.same(new_table[i], entry):
            kept += 1
            continue
        errors.append(f"{_describe_entry(i, entry)} was changed or removed - the frozen "
                      f"defaults are append-only; change a default by appending a new entry "
                      f"under a new scheme version ({FROZEN_DEFAULTS_FILE})")
    for i, entry in enumerate(new_table[kept:], start=kept):
        if any(fp.same(entry, old) for old in old_table) or "path" not in entry:
            continue
        moved = sorted(c.check_id for c in old_checks
                       if c.tool == entry.get("tool")
                       and (entry.get("kind") is None or entry["kind"] == c.check_kind)
                       and (lambda found: found[0] and fp.same(found[1], entry.get("value")))(
                           _setting_at(c.hashed_settings, entry["path"])))
        if moved:
            errors.append(f"{_describe_entry(i, entry)} is refused: {len(moved)} check(s) at "
                          f"the diff base already write that setting at that value, so dropping "
                          f"it would move their stored fingerprints: "
                          + ", ".join(repr(m) for m in moved))
    return errors


def main(require_explanations: bool = False) -> int:
    # Not a literal "HEAD~1" - a push of several commits would then
    # only ever be checked on its last one, and every retroactive edit
    # underneath it would pass unread. See qa_tools/common/diff_base.py
    # (plans/post-build-review.md #44).
    base = diff_base(root=ROOT)
    old_checks = collect_checks(base)
    new_checks = collect_checks(None)
    errors = _by_source_file(cl.validate(old_checks, new_checks), old_checks, new_checks, base)
    # REQ-QAC-176 criterion 11: the frozen defaults stay frozen.
    errors += frozen_default_errors(frozen_defaults_at(base), frozen_defaults_at(None),
                                    old_checks)
    errors += _check_id_errors(new_checks)
    # REQ-GEN-183 criteria 9 and 10: every SQL-bodied check names the
    # columns its SQL reads, in the contract's own table names.
    errors += cl.reads_columns_errors(new_checks, cl.contract_columns())

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
