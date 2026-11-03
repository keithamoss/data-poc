"""Snapshot every worktree's uncommitted work to a side branch on the remote.

Written 2026-11-01 after a replaced container lost a day of unpushed work
(plans/running-thoughts.md #135). Pushing checkpoints left two gaps - a
builder's work between commits, and edits that exist only on the container's
disk - so a periodic check-in copies each worktree's uncommitted state,
untracked files included (gitignore honoured), to `wip/<branch>-snap`.

It NEVER TOUCHES THE WORKTREE: the snapshot is built in a throwaway index file
(GIT_INDEX_FILE), committed with `commit-tree` on top of the worktree's HEAD,
and pushed by sha. The worktree's own branch, index and files are exactly as
they were. The first, hand-written version used `git add -N` and `git reset`
on the real index and unstaged whatever the running agents had staged; that is
the failure this shape exists to rule out, and the test pins it.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Snapshot:
    branch: str
    worktree: Path
    sha: str | None  # None: nothing uncommitted, nothing pushed


def _git(cwd: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout.strip()


def worktrees(repo: Path) -> list[tuple[Path, str]]:
    """Every worktree of `repo` that is on a branch, as (path, branch).
    A detached worktree has no branch to name a side branch after, so it is
    left out."""
    found, path = [], None
    for line in _git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            path = Path(line.split(" ", 1)[1])
        elif line.startswith("branch refs/heads/") and path is not None:
            found.append((path, line.removeprefix("branch refs/heads/")))
    return found


def snapshot_one(worktree: Path, branch: str, remote: str = "origin",
                 push: bool = True) -> Snapshot:
    """Commit `worktree`'s uncommitted state in a throwaway index and push it
    to `<remote>/wip/<branch>-snap`. Returns the snapshot's sha, or None when
    the worktree has nothing uncommitted (then nothing is pushed)."""
    fd, index = tempfile.mkstemp(prefix="snap-index-")
    os.close(fd)
    os.unlink(index)  # git must create it; an empty file is not an index
    env = {**os.environ, "GIT_INDEX_FILE": index}
    try:
        _git(worktree, "read-tree", "HEAD", env=env)
        _git(worktree, "add", "-A", ".", env=env)
        tree = _git(worktree, "write-tree", env=env)
        if tree == _git(worktree, "rev-parse", "HEAD^{tree}"):
            return Snapshot(branch, worktree, None)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sha = _git(worktree, "commit-tree", tree, "-p", "HEAD",
                   "-m", f"snapshot of {branch} {stamp} [skip ci]", env=env)
        if push:
            _git(worktree, "push", "-q", "-f", remote,
                 f"{sha}:refs/heads/wip/{branch}-snap")
        return Snapshot(branch, worktree, sha)
    finally:
        if os.path.exists(index):
            os.unlink(index)


def snapshot_all(repo: Path, remote: str = "origin",
                 push: bool = True) -> list[Snapshot]:
    """`snapshot_one` for every worktree of `repo` that is on a branch."""
    return [snapshot_one(path, branch, remote, push)
            for path, branch in worktrees(repo)]
