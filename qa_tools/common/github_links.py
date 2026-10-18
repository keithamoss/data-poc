"""
Maps check_id -> a real, clickable GitHub URL, each dataset to its
collection's ODCS contract at the dataset's own entry, and each agency to
its contract/<agency-id>/ folder (running-thoughts.md #8, "deep links from
the dashboard back into GitHub"; the dataset and agency targets since
REQ-DASH-244, below) - scoped via AskUserQuestion
with Keith first (three real forks, all resolved to the recommended
option): pin to the exact build commit rather than the live branch (a
check-source link should always show exactly what that check looked
like when THIS dashboard was published, matching this project's
existing reproducibility pattern - qa_results/, snapshots - rather than
silently drifting if the file changes later); and a check link gets a
real #L<line> anchor, not just a file-level link.

A DATASET'S AND AN AGENCY'S LINK MOVED (REQ-DASH-244 criteria 12 and 13,
Keith 2026-10-16). Both used to point at qa_tools/<bdm|cp>/, the
per-collection code folders, which REQ-QAC-242 deleted - so they had gone
dead. A dataset now opens its contract, what it is held to, and an agency
its folder of contracts and check files; both come from the registry.

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
`- check_id: <value>` entry in its check file.

CI-safe per CLAUDE.md's hard rule: reads only committed check-definition
files (the same ones check_lifecycle validation itself walks, via
validate_check_lifecycle.collect_checks()) and `git rev-parse HEAD` /
the GITHUB_SHA env var - never data/ or a live warehouse.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from qa_tools.common.validate_check_lifecycle import collect_checks

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REPO = "keithamoss/data-poc"

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


def build_folder_links(repo: str = DEFAULT_REPO, sha: str | None = None,
                       root: Path | str = ROOT) -> dict[str, dict[str, str]]:
    """Where each agency's and each dataset's 'View on GitHub' goes, and the
    tooltip naming it - every one from the registry (REQ-DASH-244 criteria 9,
    12 and 13).

    A DATASET OPENS ITS COLLECTION'S ODCS CONTRACT, under its agency's folder,
    at its own schema entry: the contract is what the dataset is held to.
    AN AGENCY OPENS ITS FOLDER, contract/<agency-id>/, which holds every one of
    its collections' contracts and check files (REQ-QAC-241).
    """
    from qa_tools import collections

    sha = sha or current_commit_sha(root)
    root = Path(root)
    out: dict[str, dict[str, str]] = {"agencies": {}, "datasets": {}, "titles": {"agencies": {},
                                                                              "datasets": {}}}
    for coll in collections.all_collections():
        folder = coll.folder
        out["agencies"][coll.agency_id] = f"https://github.com/{repo}/tree/{sha}/{folder}"
        out["titles"]["agencies"][coll.agency_id] = f"View {folder}/ on GitHub"
        rel = coll.check_file("contract")
        path = root / rel
        text = path.read_text() if path.is_file() else ""
        for d in coll.datasets:
            line = _find_line(text, f"- name: {d.table}")
            anchor = f"#L{line}" if line else ""
            out["datasets"][d.dataset_id] = f"https://github.com/{repo}/blob/{sha}/{rel}{anchor}"
            out["titles"]["datasets"][d.dataset_id] = (f"Open {rel} on GitHub, at this dataset's "
                                                       f"entry")
    return out
