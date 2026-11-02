"""`mothman debug snapshot-worktrees` (cli/worktree_snapshot.py): every
worktree's uncommitted work reaches `wip/<branch>-snap` on the remote, and the
worktree itself - its branch, its staging, its files - is exactly as it was.

The second half is the one that matters. The first, hand-written version of
this snapshot (2026-11-01) used `git add -N` and `git reset` on the real index,
and unstaged whatever the running agents had staged; these tests fail against
that shape."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli import worktree_snapshot


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, Path]:
    """A repository with one commit, a bare 'origin', and a second worktree
    on its own branch."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "work")
    git(main, "config", "user.email", "t@example.com")
    git(main, "config", "user.name", "t")
    (main / "tracked.txt").write_text("one\n")
    (main / ".gitignore").write_text("ignored.txt\n")
    git(main, "add", "-A")
    git(main, "commit", "-q", "-m", "first")
    git(main, "remote", "add", "origin", str(remote))
    git(main, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "feature")
    return main, remote


def test_a_snapshot_carries_tracked_and_untracked_changes_but_not_ignored_ones(repo):
    main, remote = repo
    wt = main.parent / "wt"
    (wt / "tracked.txt").write_text("two\n")
    (wt / "new.txt").write_text("brand new\n")
    (wt / "ignored.txt").write_text("never\n")

    snaps = {s.branch: s for s in worktree_snapshot.snapshot_all(main)}

    assert snaps["feature"].sha is not None
    pushed = git(remote, "rev-parse", "refs/heads/wip/feature-snap")
    assert pushed == snaps["feature"].sha
    assert git(remote, "show", f"{pushed}:tracked.txt") == "two"
    assert git(remote, "show", f"{pushed}:new.txt") == "brand new"
    files = git(remote, "ls-tree", "-r", "--name-only", pushed).splitlines()
    assert "ignored.txt" not in files
    # the snapshot sits on top of the worktree's own HEAD
    assert git(remote, "rev-parse", f"{pushed}^") == git(wt, "rev-parse", "HEAD")


@pytest.mark.critical  # REQ-TEST-375: a guard test for REQ-PIPE-092's one named exception
def test_the_worktree_is_left_exactly_as_it_was(repo):
    main, _ = repo
    wt = main.parent / "wt"
    (wt / "tracked.txt").write_text("staged\n")
    git(wt, "add", "tracked.txt")          # something staged
    (wt / "tracked.txt").write_text("staged then edited\n")  # and unstaged on top
    (wt / "untracked.txt").write_text("u\n")
    before = (git(wt, "status", "--porcelain"), git(wt, "diff", "--cached"),
              git(wt, "rev-parse", "HEAD"), git(wt, "branch", "--show-current"))

    worktree_snapshot.snapshot_all(main)

    after = (git(wt, "status", "--porcelain"), git(wt, "diff", "--cached"),
             git(wt, "rev-parse", "HEAD"), git(wt, "branch", "--show-current"))
    assert after == before
    assert (wt / "tracked.txt").read_text() == "staged then edited\n"


def test_a_clean_worktree_pushes_nothing(repo):
    main, remote = repo

    snaps = {s.branch: s for s in worktree_snapshot.snapshot_all(main)}

    assert snaps["work"].sha is None and snaps["feature"].sha is None
    assert git(remote, "for-each-ref", "refs/heads/") == ""


def test_dry_run_builds_but_pushes_nothing(repo):
    main, remote = repo
    (main.parent / "wt" / "new.txt").write_text("x\n")

    snaps = {s.branch: s for s in worktree_snapshot.snapshot_all(main, push=False)}

    assert snaps["feature"].sha is not None
    assert git(remote, "for-each-ref", "refs/heads/") == ""


def test_a_detached_worktree_is_skipped(repo):
    main, _ = repo
    git(main, "worktree", "add", "-q", "--detach", str(main.parent / "det"))

    branches = {b for _, b in worktree_snapshot.worktrees(main)}

    assert branches == {"work", "feature"}


def test_the_command_reports_each_worktree(repo, monkeypatch):
    main, _ = repo
    (main.parent / "wt" / "new.txt").write_text("x\n")
    from cli import debug

    monkeypatch.setattr(worktree_snapshot, "snapshot_all",
                        lambda repo_, remote, push: [
                            worktree_snapshot.Snapshot("work", main, None),
                            worktree_snapshot.Snapshot("feature", main, "abc1234def")])

    out = CliRunner().invoke(debug.debug_group, ["snapshot-worktrees", "--dry-run"])

    assert out.exit_code == 0, out.output
    assert "work: no uncommitted changes" in out.output
    assert "feature: snapshot abc1234 built, not pushed" in out.output


@pytest.mark.critical  # REQ-TEST-375: a guard test for REQ-PIPE-092's one named exception
def test_it_only_ever_pushes_to_a_wip_snap_ref(repo):
    """Why the publish-path guard (tests/test_publish.py) lets this one pusher
    through: it publishes nothing. Every ref it writes is wip/<branch>-snap,
    and no other ref on the remote moves."""
    main, remote = repo
    (main / "tracked.txt").write_text("changed on work\n")
    (main.parent / "wt" / "new.txt").write_text("x\n")

    worktree_snapshot.snapshot_all(main)

    refs = git(remote, "for-each-ref", "--format=%(refname)").splitlines()
    assert refs, "precondition: something was pushed"
    assert set(refs) == {"refs/heads/wip/work-snap", "refs/heads/wip/feature-snap"}, refs
