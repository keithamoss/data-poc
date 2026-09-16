"""Tests for dashboard/check_no_local_embed_committed.py - the pre-commit
guard for Phase 3's "never commit a local dashboard data-embed rebuild"
rule (plans/publishing-and-history.md). Uses a real temp git repo and a
real subprocess invocation of the script (not a mocked diff), same
rigor as tests/test_validate_check_lifecycle.py's own git-history tests
- the git-diff-reading mechanism is exactly the part worth testing for
real."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "dashboard" / "check_no_local_embed_committed.py"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(tmp_path):
    repo = tmp_path
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _run_check(repo) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=repo, capture_output=True, text=True)


_DASHBOARD_SKELETON = textwrap.dedent("""\
    <html><body>
    <script>
    const REAL_BIRTH_REG_DATA = {"old":1};
    const REAL_CP_DATA = {"old":1};
    </script>
    </body></html>
    """)


def test_passes_when_the_file_is_not_staged(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "dashboard").mkdir()
    (repo / "dashboard" / "qa-reporting-dashboard.html").write_text(_DASHBOARD_SKELETON)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial commit")

    result = _run_check(repo)

    assert result.returncode == 0


def test_blocks_a_commit_that_only_touches_the_two_embedded_consts(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "dashboard").mkdir()
    dashboard_path = repo / "dashboard" / "qa-reporting-dashboard.html"
    dashboard_path.write_text(_DASHBOARD_SKELETON)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial commit")

    # exactly what embed_dashboard_data.py does - rewrite only the two const lines
    rebuilt = _DASHBOARD_SKELETON.replace(
        'const REAL_BIRTH_REG_DATA = {"old":1};', 'const REAL_BIRTH_REG_DATA = {"new":2};'
    ).replace(
        'const REAL_CP_DATA = {"old":1};', 'const REAL_CP_DATA = {"new":2};'
    )
    dashboard_path.write_text(rebuilt)
    _git(repo, "add", "-A")

    result = _run_check(repo)

    assert result.returncode == 1
    assert "embedded-data consts" in result.stderr
    assert "REAL_BIRTH_REG_DATA" in result.stderr


def test_allows_a_genuine_hand_edit_that_also_touches_other_lines(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "dashboard").mkdir()
    dashboard_path = repo / "dashboard" / "qa-reporting-dashboard.html"
    dashboard_path.write_text(_DASHBOARD_SKELETON)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial commit")

    # a real edit - touches a line other than the two embedded consts
    edited = _DASHBOARD_SKELETON.replace("<body>", "<body class=\"dark\">")
    dashboard_path.write_text(edited)
    _git(repo, "add", "-A")

    result = _run_check(repo)

    assert result.returncode == 0


def test_allows_a_hand_edit_that_happens_to_also_touch_the_const_lines(tmp_path):
    """A real edit that touches BOTH the const lines AND something
    else (e.g. someone reformats the whole <script> block by hand)
    must still pass - only a diff that touches NOTHING BUT the two
    const lines is treated as a suspicious local rebuild."""
    repo = _init_repo(tmp_path)
    (repo / "dashboard").mkdir()
    dashboard_path = repo / "dashboard" / "qa-reporting-dashboard.html"
    dashboard_path.write_text(_DASHBOARD_SKELETON)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial commit")

    edited = _DASHBOARD_SKELETON.replace("<body>", "<body class=\"dark\">").replace(
        'const REAL_BIRTH_REG_DATA = {"old":1};', 'const REAL_BIRTH_REG_DATA = {"new":2};'
    )
    dashboard_path.write_text(edited)
    _git(repo, "add", "-A")

    result = _run_check(repo)

    assert result.returncode == 0
