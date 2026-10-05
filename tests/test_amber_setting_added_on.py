"""REQ-PIPE-122 criterion 7 as amended 2026-10-05 (Keith): 'the day it
is added' is the date, on the asset's clock, of the commit that
introduced the version - not the day the gate runs."""
from __future__ import annotations

import os
import subprocess
from datetime import date

from qa_tools.common import validate_schedule


def _git(repo, *args, when=None):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)


def test_a_committed_change_is_dated_by_its_commit(tmp_path, monkeypatch):
    repo = tmp_path
    _git(repo, "init", "-q")
    f = repo / "contract" / "data-asset.yaml"
    f.parent.mkdir()
    f.write_text("a: 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base", when="2026-10-01T09:00:00+08:00")
    f.write_text("a: 2\n")
    _git(repo, "add", ".")
    # 11:30pm Perth on the 4th - already the 4th in UTC too.
    _git(repo, "commit", "-qm", "late", when="2026-10-04T23:30:00+08:00")
    monkeypatch.setattr(validate_schedule, "ROOT", repo)
    assert validate_schedule._added_on("contract/data-asset.yaml", "HEAD~1") == date(2026, 10, 4)


def test_an_uncommitted_change_is_added_today(tmp_path, monkeypatch):
    repo = tmp_path
    _git(repo, "init", "-q")
    f = repo / "contract" / "data-asset.yaml"
    f.parent.mkdir()
    f.write_text("a: 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base", when="2026-10-01T09:00:00+08:00")
    f.write_text("a: 2\n")
    monkeypatch.setattr(validate_schedule, "ROOT", repo)
    assert validate_schedule._added_on("contract/data-asset.yaml", "HEAD") is None
