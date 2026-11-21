"""REQ-PIPE-372: until REQ-PIPE-255 gives each asset hosting of its own, only
an asset whose data-asset.yaml says `publish_to_gh_pages: true` publishes to
the gh-pages branch; any other is refused before anything is built, written
or pushed, non-zero, pointing to `mothman dashboard rebuild`. And the site
carries only the selected asset's snapshot archive (criterion 4; REQ-DASH-373
criterion 3).

THE REMOTE IS A REAL ONE, a bare repository standing in for GitHub (criterion
6's "stub git remote"): the publish runs in a scratch repository whose
`origin` is that bare repository, so "pushes nothing" is read from the
remote's own refs rather than from a mock having been called.
"""
from __future__ import annotations

import gzip
import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli import dashboard as dashboard_cli

GIT = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]


@pytest.fixture
def stub_remote(tmp_path, monkeypatch):
    """A scratch repository, the publish's working directory, whose origin
    is a bare repository - (repo, remote)."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README").write_text("source\n")
    subprocess.run([*GIT, "add", "-A"], cwd=repo, check=True)
    subprocess.run([*GIT, "commit", "-qm", "source"], cwd=repo, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=repo, check=True)
    monkeypatch.chdir(repo)
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(key, "t")
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(key, "t@example.com")
    return repo, remote


def _remote_refs(remote: Path) -> str:
    return subprocess.run(["git", "for-each-ref"], cwd=remote, capture_output=True,
                          text=True, check=True).stdout


@pytest.fixture
def steps(monkeypatch):
    """The build and the gate recorded rather than run - the real build reads
    the deployment database. prepare_deploy_site writes a one-page site, so
    the real _publish has something to push."""
    from dashboard import snapshot_dashboard

    done = []

    def step(name):
        return lambda *a, **k: done.append(name)

    for name in ("_rebuild_results", "_build_data", "_embed", "_check_renders"):
        monkeypatch.setattr(dashboard_cli, name, step(name))
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", step("take_snapshot"))

    def site(site_dir, **_k):
        done.append("prepare_deploy_site")
        Path(site_dir).mkdir(parents=True, exist_ok=True)
        (Path(site_dir) / "index.html").write_text("<html>the page</html>")
    monkeypatch.setattr(snapshot_dashboard, "prepare_deploy_site", site)
    return done


class TestAnAssetWithoutTheSettingIsRefused:
    """Criteria 1 and 2."""

    @pytest.mark.asset("daily")
    def test_it_exits_non_zero_naming_rebuild_and_pushes_nothing(self, stub_remote, steps):
        _repo, remote = stub_remote
        got = CliRunner().invoke(dashboard_cli.publish_command, [])
        said = " ".join(got.output.replace("│", " ").split())
        assert got.exit_code != 0, got.output
        assert "The daily asset's dashboard is not published yet" in said, said
        assert "REQ-PIPE-255" in said and "`mothman dashboard rebuild`" in said, said
        assert steps == [], "refused before anything was built or written"
        assert _remote_refs(remote) == "", "nothing reached the remote"

    @pytest.mark.asset("daily")
    def test_pipeline_run_with_publish_is_refused_before_the_run(self, monkeypatch):
        """`pipeline run --publish` reaches the same refusal before processing
        anything, rather than after a whole run."""
        import contextlib

        from cli import pipeline
        from qa_tools.common import processing_pass, streams
        from qa_tools.tools import orchestrate

        ran = []
        # EVERY STEP OF THE RUN RECORDED, NOT RUN: were the refusal to come
        # after the run, this would otherwise process every arrival for real.
        monkeypatch.setattr(streams, "holds_history", lambda *a, **k: ran.append("history") or False)
        monkeypatch.setattr(processing_pass, "pass_lock", lambda *a, **k: contextlib.nullcontext())
        monkeypatch.setattr(orchestrate, "run_stream", lambda *a, **k: ran.append("run_stream"))
        for name in ("_build_data", "_embed", "publish"):
            monkeypatch.setattr(dashboard_cli, name, lambda *a, _n=name, **k: ran.append(_n))
        got = CliRunner().invoke(pipeline.run_command, ["--publish"])
        assert got.exit_code != 0, got.output
        assert "is not published yet" in got.output
        assert ran == [], "nothing of the run started"


class TestAnAssetWithTheSettingPublishes:
    """Criterion 1: the quarterly asset holds it, and its publish proceeds."""

    @pytest.mark.asset("quarterly")
    def test_it_builds_gates_and_pushes(self, stub_remote, steps):
        _repo, remote = stub_remote
        got = CliRunner().invoke(dashboard_cli.publish_command, [])
        assert got.exit_code == 0, got.output
        assert steps[:4] == ["_rebuild_results", "_build_data", "_embed", "_check_renders"]
        assert "refs/heads/gh-pages" in _remote_refs(remote)

    def test_only_the_quarterly_asset_holds_it(self):
        """Criterion 1, read from each asset's own file - the setting, never
        a name in code (NFR 1)."""
        import yaml

        folder = Path(__file__).resolve().parents[1] / "assets"
        held = {p.parent.name: (yaml.safe_load(p.read_text()) or {}).get("publish_to_gh_pages") is True
                for p in sorted(folder.glob("*/data-asset.yaml"))}
        assert held == {"quarterly": True, "daily": False}, held


class TestTheSiteCarriesOnlyTheSelectedAssetsArchive:
    """REQ-PIPE-372 criterion 4, REQ-DASH-373 criterion 3."""

    @pytest.mark.asset("quarterly")
    def test_another_assets_local_snapshot_never_reaches_the_site(self, tmp_path, monkeypatch):
        from dashboard import snapshot_dashboard

        root = tmp_path / "snapshots"
        for asset in ("quarterly", "daily"):
            (root / asset).mkdir(parents=True)
            with gzip.open(root / asset / f"20261121T000000Z_{asset}.html.gz", "wb") as f:
                f.write(f"<html>{asset}</html>".encode())
            (root / asset / "manifest.json").write_text(json.dumps([{"file": f"20261121T000000Z_{asset}.html.gz"}]))
        monkeypatch.setattr(snapshot_dashboard, "SNAPSHOTS_ROOT", root)
        page = tmp_path / "page.html"
        page.write_text("<html>live</html>\nconst SNAPSHOT_MANIFEST = [];\n")
        site = tmp_path / "_site"

        snapshot_dashboard.prepare_deploy_site(site, html_path=page)

        placed = sorted(p.relative_to(site).as_posix() for p in (site / "snapshots").rglob("*.html"))
        assert placed == ["snapshots/quarterly/20261121T000000Z_quarterly.html"], placed
        assert "daily" not in (site / "index.html").read_text()


class TestNoWorkflowPublishes:
    """Criterion 3: an automated publish runs only for an asset whose
    configuration holds the setting, and none runs today. Read from the
    workflow files - an architecture rule with no behaviour of its own to
    drive: any publish goes through publish(), which asks the setting first."""

    def test_no_workflow_calls_the_publish(self):
        root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
        files = sorted(root.glob("*.yml"))
        assert files, "test precondition - the workflows are there"
        calling = [f.name for f in files if "dashboard publish" in f.read_text()
                   or "--publish" in f.read_text()]
        assert calling == [], calling


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
