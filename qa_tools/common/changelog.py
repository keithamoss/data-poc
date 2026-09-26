"""
Reshapes committed qa_results/ history + real git history into "who
published what, when" changelog/activity-feed events -
plans/publishing-and-history.md Phase 3's remaining DATA-logic item
(2026-09-16). The feed's own UI is a separate, later phase (Phase 5) -
this module only produces the data.

Design settled with Keith across several rounds (see plans/publishing-
and-history.md's own Phase 3 write-up for the full back-and-forth; this
is the short version):

- Grouping key is (agency, dataset, run_timestamp), not "one git
  commit" - a single commit can legitimately bundle QA events for
  multiple datasets (e.g. someone runs both orchestrate_bdm.py and
  orchestrate_cp.py, then commits both together), and a naive
  per-commit grouping would conflate them into one event.
- `run_by`/`run_timestamp` come straight from committed qa_results/
  file content (qa_tools/common/git_identity.py's get_run_by(),
  stamped once per orchestrate_bdm.py/orchestrate_cp.py invocation) -
  pure data, unaffected by anything that happens to the commit that
  later carries it (a rebase, for instance).
- `committed_at`/`commit_sha` can NOT be safely self-recorded at commit
  time, even though that would be simpler: a commit made locally,
  pre-push, can still be rebased before it reaches the shared branch,
  which rewrites its SHA and (git's own default behaviour) bumps its
  committer date to rebase time - so a value recorded before push can
  end up silently wrong, precisely in the "QA'd today but not actually
  published for days" scenario this feature exists to catch. The only
  way to know "when did this actually land" is to look at the real,
  already-pushed branch - resolved below by walking that dataset's own
  git history ONCE (ROOT-relative, not a search per known value - see
  _committed_at_by_run_timestamp()'s own docstring for why).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from qa_tools.common.qa_results_reader import list_run_ids, read_run_provenance

ROOT = Path(__file__).resolve().parent.parent.parent
QA_RESULTS_DIR = ROOT / "qa_results"

_RUN_TIMESTAMP_RE = re.compile(r'"run_timestamp":\s*"([^"]*)"')


# A commit-boundary marker for _committed_at_by_run_timestamp()'s single
# `git log -p` stream - deliberately not a bare "%H|%cI" line, which
# could theoretically collide with real diff content; this prefix can't
# appear in qa_results/'s own JSON output.
_COMMIT_BOUNDARY_PREFIX = "@@CHANGELOG_COMMIT@@"
_COMMIT_BOUNDARY_RE = re.compile(rf"^{re.escape(_COMMIT_BOUNDARY_PREFIX)}([0-9a-f]+)\|(.*)$")


def _committed_at_by_run_timestamp(agency: str, dataset: str, repo_root: Path) -> dict[str, tuple[str, str]]:
    """One walk of every commit that ever touched this dataset's own
    qa_results/ subtree (oldest first), returning {run_timestamp:
    (commit_sha, committed_at)} for every value any of those commits
    introduced.

    Deliberately NOT one `git log -S"<value>"` pickaxe search per known
    run_timestamp - that would re-walk the same commit history once per
    value (O(events) searches x O(commits) examined each = O(events^2)
    overall), whereas walking the history once and reading each
    commit's own diff for whatever it added gives the same answer in a
    single pass (O(commits) total, each commit's diff read once). Scoped
    with Keith specifically over this concern (a year of daily QA runs
    -> low thousands of commits, not something to pay quadratic cost
    against on every dashboard rebuild).

    A SINGLE `git log -p` call (real bug found and fixed 2026-09-18,
    Keith's own question about test runtime growing again): the
    original version still issued one extra `git show <sha>` subprocess
    PER commit on top of the initial `git log` - real subprocess-
    spawn + tree-diff overhead that scales with both the NUMBER of
    commits touching this path and the SIZE of each commit's own diff,
    which grew a lot the same day this bug was found (several
    qa_results/ regeneration commits touching 80-900+ files each) -
    measured at ~13s for Birth Registrations' own 12 commits alone,
    dominating embed_dashboard_data.embed()'s own real runtime and
    every test that exercises it. Two real fixes, not one: (1) `git log
    -p` streams every commit's own patch inline with its own log line
    in ONE process, instead of one extra `git show` subprocess PER
    commit; (2) the pathspec is narrowed to `dataset_stats.json` files
    specifically, not every file under this dataset's qa_results/
    subtree - the only file `read_run_provenance()`/`build_changelog()`
    itself ever reads, so it's also the only one this function needs to
    search, and excluding dbt.json/soda.json (real, verbose native tool
    output, the bulk of the diff volume on a full regeneration) is what
    actually did most of the work: measured 225MB/5.3M lines of diff
    output for Birth Registrations' full-tree pathspec (~9s just to
    generate) vs. 1.7MB/56K lines narrowed to dataset_stats.json alone
    (~0.7s) - a ~13x reduction, (1) alone barely moved the needle
    against a diff already this large."""
    # REQ-PIPE-038 moved dataset_stats into the `_raw` scope, because
    # it describes a RUN rather than a dataset. The pathspec follows it
    # rather than widening to `**`: the narrowing is what makes this
    # function fast (see the paragraph above), and a `**` would put the
    # real dbt and Soda output back into the diff it reads.
    from qa_tools.common import tables_read as tables_read_mod

    rel_path = f"qa_results/{agency}/{dataset}/"
    dataset_stats_pathspec = f"{rel_path}{tables_read_mod.RAW_SCOPE}/*/dataset_stats.json"
    log = subprocess.run(
        ["git", "log", "-p", "--reverse", f"--format={_COMMIT_BOUNDARY_PREFIX}%H|%cI", "--", dataset_stats_pathspec],
        cwd=repo_root, capture_output=True, text=True, check=True,
    )
    result: dict[str, tuple[str, str]] = {}
    current_sha = current_committed_at = None
    for line in log.stdout.splitlines():
        boundary = _COMMIT_BOUNDARY_RE.match(line)
        if boundary:
            current_sha, current_committed_at = boundary.group(1), boundary.group(2)
            continue
        # only genuinely ADDED content lines - "+++ b/path" is the
        # per-file diff header, not content, and must be excluded
        # separately since it also starts with "+".
        if not line.startswith("+") or line.startswith("+++") or current_sha is None:
            continue
        match = _RUN_TIMESTAMP_RE.search(line)
        if match:
            # setdefault, not overwrite: commits are walked oldest
            # first, so the FIRST commit to introduce a given value
            # is the one that actually committed it - a later
            # regeneration re-adding the same value (shouldn't
            # happen in practice, run_timestamp is wall-clock and
            # effectively unique per invocation) would otherwise
            # overwrite a true earlier commit with a spurious later
            # one.
            result.setdefault(match.group(1), (current_sha, current_committed_at))
    return result


def build_changelog(agency: str, dataset: str, qa_results_dir: Path | str = QA_RESULTS_DIR,
                     repo_root: Path = ROOT) -> list[dict]:
    """One entry per real QA event for this (agency, dataset),
    reconstructed from committed qa_results/ history:
    `{agency, dataset, run_timestamp, run_by, commit_sha, committed_at}`.

    `commit_sha`/`committed_at` are None if no commit introducing that
    run_timestamp was found in `repo_root`'s history - shouldn't happen
    for any run committed in the normal way, but this is best-effort
    reconstruction from git, not a hard invariant like check_id, so it
    degrades rather than raising. Sorted by run_timestamp, oldest
    first - the feed's own UI (Phase 5) can re-sort as it likes."""
    run_ids = list_run_ids(agency, dataset, qa_results_dir)

    run_by_for_timestamp: dict[str, str | None] = {}
    for run_id in run_ids:
        provenance = read_run_provenance(agency, dataset, run_id, qa_results_dir)
        if provenance is None or provenance["run_timestamp"] is None:
            continue
        run_by_for_timestamp[provenance["run_timestamp"]] = provenance["run_by"]

    committed_at_by_timestamp = _committed_at_by_run_timestamp(agency, dataset, repo_root)

    events = []
    for run_timestamp, run_by in run_by_for_timestamp.items():
        commit_sha, committed_at = committed_at_by_timestamp.get(run_timestamp, (None, None))
        events.append({
            "agency": agency,
            "dataset": dataset,
            "run_timestamp": run_timestamp,
            "run_by": run_by,
            "commit_sha": commit_sha,
            "committed_at": committed_at,
        })
    events.sort(key=lambda e: e["run_timestamp"])
    return events


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 3:
        print("usage: python3 -m qa_tools.common.changelog <agency> <dataset>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(build_changelog(sys.argv[1], sys.argv[2]), indent=2))
