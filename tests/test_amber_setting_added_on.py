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


def test_a_version_not_yet_committed_is_added_today(tmp_path, monkeypatch):
    repo = tmp_path
    _git(repo, "init", "-q")
    f = repo / "contract" / "data-asset.yaml"
    f.parent.mkdir()
    f.write_text("data_asset_id: x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base", when="2026-10-01T09:00:00+08:00")
    f.write_text("data_asset_id: x\namber_setting:\n  versions:\n"
                 "    - effective_from: '2026-10-02'\n      value: hold\n")
    monkeypatch.setattr(validate_schedule, "ROOT", repo)
    assert validate_schedule._version_added_on(
        "contract/data-asset.yaml", "HEAD", "2026-10-02") is None


def test_a_version_is_dated_by_the_commit_that_added_it_not_the_push(tmp_path, monkeypatch):
    """delivery critic on 8a942e7, M1: an unrelated edit earlier in the same
    push dated the change - so a version back-dated to the 2nd, added on
    the 10th, passed because the file was first touched on the 1st."""
    repo = tmp_path
    _git(repo, "init", "-q")
    f = repo / "contract" / "data-asset.yaml"
    f.parent.mkdir()
    base = "data_asset_id: x\namber_setting:\n  versions:\n    - effective_from: '2023-01-01'\n      value: promote\n"
    f.write_text(base)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base", when="2026-09-01T09:00:00+08:00")
    f.write_text(base + "# an unrelated edit\n")
    _git(repo, "commit", "-qam", "unrelated", when="2026-10-01T09:00:00+08:00")
    f.write_text(base.replace("value: promote\n", "value: promote\n    - effective_from: '2026-10-02'\n      value: hold\n") + "# an unrelated edit\n")
    _git(repo, "commit", "-qam", "the version", when="2026-10-10T09:00:00+08:00")
    monkeypatch.setattr(validate_schedule, "ROOT", repo)
    assert validate_schedule._version_added_on(
        "contract/data-asset.yaml", "HEAD~2", "2026-10-02") == date(2026, 10, 10)
