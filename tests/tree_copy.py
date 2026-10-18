"""A temporary copy of the tracked working tree (REQ-TEST-252 criterion 15,
REQ-TEST-249 criterion 2).

Every file git tracks, as it stands in the working tree - edits not yet
committed included, deletions honoured - copied into a directory of the
test's own. A test adds what it needs to the COPY and runs mothman there,
so nothing it registers can reach the repository's own contract/, data/ or
reports/, and no environment variable or path ever has to tell the
registry where adapters load from (REQ-PIPE-240 criterion 4).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def tracked_files(root: Path = ROOT) -> list[str]:
    """Every path git tracks that exists in the working tree."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True,
                         capture_output=True).stdout.decode().split("\0")
    return [p for p in out if p and (root / p).is_file()]


def copy_tracked_tree(dest: Path, root: Path = ROOT) -> Path:
    """Copy every tracked file into `dest`, preserving paths; return `dest`."""
    files = tracked_files(root)
    assert files, "git tracks no files here - the copy would prove nothing"
    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    return dest
