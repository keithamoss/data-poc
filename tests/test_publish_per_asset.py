"""REQ-PIPE-372 and REQ-PIPE-354: each asset publishes to a project of its
own, declared in its own data-asset.yaml - the interim publish_to_gh_pages
setting, which held the daily asset's publish until REQ-PIPE-255 gave it
hosting, is gone (REQ-PIPE-372 criterion 5) - and each site carries only the
selected asset's snapshot archive (REQ-PIPE-372 criterion 4, REQ-DASH-373
criterion 3). No workflow publishes (REQ-PIPE-372 criterion 3).
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest


class TestEachAssetDeclaresItsOwnProject:
    """REQ-PIPE-372 criterion 5 (its interim publish_to_gh_pages replaced by
    each asset's own hosting keys) and REQ-PIPE-354 criteria 3 and 4: two
    projects, one per asset, each read from that asset's own file. The
    refusal of an asset with none is tests/test_cloudflare_publish.py's."""

    def test_each_asset_names_a_project_of_its_own(self):
        import yaml

        folder = Path(__file__).resolve().parents[1] / "assets"
        found = {p.parent.name: (yaml.safe_load(p.read_text()) or {})
                 for p in sorted(folder.glob("*/data-asset.yaml"))}
        projects = {name: doc["hosting"]["pages_project"] for name, doc in found.items()}
        assert projects == {"daily": "data-poc-daily", "quarterly": "data-poc-quarterly"}, projects
        assert not any("publish_to_gh_pages" in doc for doc in found.values()), \
            "the interim setting is gone (REQ-PIPE-372 criterion 5)"


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
