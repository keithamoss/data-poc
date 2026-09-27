"""
Reshapes recorded QA history into "who published what, when"
changelog/activity-feed events. The feed's own UI is separate; this
module only produces the data.

IT USED TO JOIN COMMITTED FILES TO GIT HISTORY, and that is worth
reading before anybody rebuilds it, because the reasoning was sound
and the conclusion has been overtaken (REQ-PIPE-089 criteria 16
and 22).

- Grouping key is (agency, dataset, run_timestamp), not "one commit" -
  a single commit could legitimately bundle QA events for several
  datasets, and a per-commit grouping would conflate them. THIS
  SURVIVES: the key is still the run, which is what it always should
  have been.
- `run_by`/`run_timestamp` came straight from file content, unaffected
  by whatever happened to the commit that later carried it. THIS
  SURVIVES TOO: they are columns on `qa.run` now.
- `committed_at`/`commit_sha` (as they were then called) could NOT
  safely be self-recorded at
  commit time: a commit made locally can be rebased before it reaches
  the shared branch, rewriting its SHA and bumping its committer date -
  so a value recorded before push could be silently wrong, exactly in
  the "QA'd today but not published for days" case this feature exists
  to catch. The only honest answer was to walk the real pushed branch.

  THAT QUESTION NO LONGER EXISTS. Results are not committed, so there
  is no commit to be rebased and no gap between running QA and
  publishing it - a result is visible the moment its run completes.
  `completed_at` IS the "when did this land" answer, recorded by the
  run itself, and it cannot be rewritten by anything downstream.

WHAT THIS COSTS, so it is a choice rather than a discovery: the feed
can no longer distinguish "QA'd on Monday, published on Thursday",
because that gap was an artefact of results travelling through git.
`commit_sha` is gone from every event.

WHAT IT BUYS, beyond honesty: the git walk this replaces was a real
performance hazard, documented at length in CLAUDE.md. It span one
`git show` per commit touching the subtree, diffing each commit's
entire changed tree - measured at 225 MB and 5.3 M lines of diff
output for one dataset's twelve commits, and it grew with both commit
count and diff size. Two fixes got it to 0.7s; a column needs none.
"""
from __future__ import annotations


from qa_tools.common import qa_store, supply_db



def build_changelog(agency: str, dataset: str, conn=None) -> list[dict]:
    """One entry per real QA event for this (agency, dataset):
    `{agency, dataset, run_timestamp, run_by, published_at}`.

    `published_at` is when the run COMPLETED - the moment its results
    became visible to anything reading them. It was called `committed_at`
    and held the commit date of whatever push carried the files: the same
    question asked of a mechanism that no longer exists. The NAME was the
    last of that mechanism left (REQ-PIPE-090 criterion 5), and a field
    called committed_at holding a completion time is exactly the kind of
    thing a reader trusts and should not.

    Sorted by run_timestamp, oldest first - the feed's own UI can
    re-sort as it likes.

    `qa_results_dir` and `repo_root` used to be accepted and ignored here,
    so callers did not all have to change alongside the storage.
    REQ-PIPE-089's last phase removed them.
    """
    close = conn is None
    if conn is None:
        conn = supply_db.connect(label="mothman:changelog")
        qa_store.ensure_schema(conn)
    try:
        rows = conn.execute(
            f'SELECT run_timestamp, run_by, completed_at '
            f'FROM "{qa_store.SCHEMA}".run_visible '
            "WHERE agency_id = ? AND collection_id = ? ORDER BY run_timestamp",
            [agency, dataset]).fetchall()
    finally:
        if close:
            conn.close()

    # ONE EVENT PER run_timestamp, which is the grouping key the file
    # version used and for the same reason - two runs of the same
    # collection at the same instant are one QA event, not two.
    events: dict[str, dict] = {}
    for run_timestamp, run_by, completed_at in rows:
        stamp = _iso(run_timestamp)
        events[stamp] = {
            "agency": agency,
            "dataset": dataset,
            "run_timestamp": stamp,
            "run_by": run_by,
            "published_at": _iso(completed_at),
        }
    return sorted(events.values(), key=lambda e: e["run_timestamp"])


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 3:
        print("usage: python3 -m qa_tools.common.changelog <agency> <dataset>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(build_changelog(sys.argv[1], sys.argv[2]), indent=2))
