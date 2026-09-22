"""
Maps check_id -> a real, clickable GitHub URL, and each dataset/agency
to its own qa_tools/<bdm|cp>/ folder (running-thoughts.md #8, "deep
links from the dashboard back into GitHub") - scoped via AskUserQuestion
with Keith first (three real forks, all resolved to the recommended
option): pin to the exact build commit rather than the live branch (a
check-source link should always show exactly what that check looked
like when THIS dashboard was published, matching this project's
existing reproducibility pattern - qa_results/, snapshots - rather than
silently drifting if the file changes later); a dataset/agency link
points at qa_tools/<bdm|cp>/ specifically (the real per-dataset
orchestration code, already this repo's established one-folder-per-
dataset convention - CLAUDE.md's own layout table), doubling as the
agency link too since each real agency maps to exactly one dataset/
collection today; and a check link gets a real #L<line> anchor, not
just a file-level link.

Line-finding is deliberately a plain text scan for the check_id's own
literal value, not a per-tool-specific YAML/AST parse: check_lifecycle.
py already guarantees every check_id is globally unique
(find_duplicate_check_ids), and it's a long, dotted, structurally-
distinctive string - the first line containing it as a substring IS its
real definition, in every one of the 3 real formats this repo's checks
are actually authored in (verified against real file content before
writing this, not assumed): dbt/soda's `check_id: <value>` on one line,
the ODCS contract's `value: <value>` on the line under a
`- property: check_id` customProperty entry, and Evidently's
`SOME_CHECK_ID = "<value>"` constant assignment.

CI-safe per CLAUDE.md's hard rule: reads only committed check-definition
files (the same ones check_lifecycle validation itself walks, via
validate_check_lifecycle.collect_checks()) and `git rev-parse HEAD` /
the GITHUB_SHA env var - never data/ or a live warehouse.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from qa_tools.common import hierarchy
from qa_tools.common.validate_check_lifecycle import collect_checks

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REPO = "keithamoss/data-poc"

# agency -> the qa_tools/ source folder its real tool scripts live in.
# Genuinely NOT part of the hierarchy - it maps an agency onto this
# repo's own code layout, which contract/data-asset.yaml has no business
# knowing about - so it stays a literal. Add an entry when an agency
# arrives.
AGENCY_QA_FOLDER = {
    "registry-services": "bdm",
    "child-protection-family-support": "cp",
}

# The per-dataset view of the same thing. Derived from the hierarchy
# (REQ-QAC-039) rather than enumerating every dataset a second time -
# which is what it used to do, and what made this one of the four copies
# of the tree that requirement removed.
DATASET_QA_FOLDER = {d.dataset_id: AGENCY_QA_FOLDER[d.agency_id] for d in hierarchy.all_datasets()}


def current_commit_sha(root: Path | str = ROOT) -> str:
    """GITHUB_SHA (set automatically on every real Actions run) if
    present, else a real `git rev-parse HEAD` in `root` - the local-dev
    fallback, so links still resolve (just to whatever's currently
    checked out) when building outside CI."""
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _rel_path(source_file: str, root: Path) -> str:
    p = Path(source_file)
    return str(p.relative_to(root)) if p.is_absolute() else source_file


def _find_line(text: str, needle: str) -> int | None:
    for i, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return i
    return None


def build_check_source_links(repo: str = DEFAULT_REPO, sha: str | None = None, root: Path | str = ROOT) -> dict[str, str]:
    """{check_id: github_url}, one entry per real check across all 4
    tools, active AND retired (collect_checks(None) already walks both -
    the same source lists check_lifecycle validation itself uses, so a
    check's link never goes stale relative to what CI is actually
    gating)."""
    sha = sha or current_commit_sha(root)
    root = Path(root)
    links: dict[str, str] = {}
    for check in collect_checks(None):
        rel_path = _rel_path(check.source_file, root)
        full_path = root / rel_path
        if not full_path.exists():
            continue
        text = full_path.read_text()
        line = _find_line(text, check.check_id)
        anchor = f"#L{line}" if line else ""
        links[check.check_id] = f"https://github.com/{repo}/blob/{sha}/{rel_path}{anchor}"
    return links


def build_folder_links(repo: str = DEFAULT_REPO, sha: str | None = None, root: Path | str = ROOT) -> dict[str, dict[str, str]]:
    """{"agencies": {agencyId: url}, "datasets": {datasetId: url}} - both
    keyed off AGENCY_QA_FOLDER/DATASET_QA_FOLDER above, both currently
    resolving to the same real qa_tools/<bdm|cp>/ folder per real
    agency/dataset."""
    sha = sha or current_commit_sha(root)

    def folder_url(code: str) -> str:
        return f"https://github.com/{repo}/tree/{sha}/qa_tools/{code}"

    return {
        "agencies": {agency_id: folder_url(code) for agency_id, code in AGENCY_QA_FOLDER.items()},
        "datasets": {dataset_id: folder_url(code) for dataset_id, code in DATASET_QA_FOLDER.items()},
    }
