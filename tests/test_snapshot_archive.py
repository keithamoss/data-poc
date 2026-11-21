"""REQ-DASH-373: each asset's snapshot archive is its own folder,
dashboard/snapshots/<asset>/, read by every reader of the archive, and it
starts from the date its data-asset.yaml declares (`snapshots_from`)."""
from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from dashboard import snapshot_dashboard


@pytest.mark.parametrize("asset", [pytest.param("quarterly", marks=pytest.mark.asset("quarterly")),
                                   pytest.param("daily", marks=pytest.mark.asset("daily"))])
class TestEachAssetHasItsOwnArchive:
    """Criteria 3 and 4."""

    def test_the_archive_is_the_selected_assets_folder(self, asset):
        assert snapshot_dashboard.asset_snapshots_dir() == snapshot_dashboard.SNAPSHOTS_ROOT / asset

    def test_it_says_its_folder_and_the_date_it_starts(self, asset):
        assert snapshot_dashboard.archive_settings() == {"asset": asset, "from": "2026-11-21"}

    def test_a_local_sync_reads_the_selected_assets_folder_only(self, asset, tmp_path, monkeypatch):
        root = tmp_path / "snapshots"
        for name in ("quarterly", "daily"):
            (root / name).mkdir(parents=True)
            with gzip.open(root / name / f"20261121T000000Z_{name}.html.gz", "wb") as f:
                f.write(b"<html></html>")
        monkeypatch.setattr(snapshot_dashboard, "SNAPSHOTS_ROOT", root)
        written = snapshot_dashboard.sync_local_snapshots(fonts_dir=tmp_path / "none",
                                                          vendor_dir=tmp_path / "none")
        assert [p.relative_to(root).as_posix() for p in written] == [
            f"{asset}/20261121T000000Z_{asset}.html"]

    def test_a_snapshot_is_archived_into_the_selected_assets_folder(self, asset, tmp_path, monkeypatch):
        monkeypatch.setattr(snapshot_dashboard, "SNAPSHOTS_ROOT", tmp_path / "snapshots")
        page = tmp_path / "page.html"
        page.write_text("<html></html>\nconst SNAPSHOT_MANIFEST = [];\n")
        out = snapshot_dashboard.take_snapshot(html_path=page)
        assert out.parent == tmp_path / "snapshots" / asset
        assert (tmp_path / "snapshots" / asset / "manifest.json").is_file()


def test_the_committed_archive_holds_only_per_asset_folders():
    """Criterion 1's live rule: no archived page at the archive's top, where
    the pre-split pages - each showing both assets' results - were. The
    folder can be absent (no asset has published since), never flat."""
    root = snapshot_dashboard.SNAPSHOTS_ROOT
    names = {p.name for p in Path(__file__).resolve().parents[1].joinpath("assets").iterdir()
             if p.is_dir()}
    assert names, "test precondition - the assets are there"
    top = sorted(p.name for p in root.iterdir()) if root.exists() else []
    assert all(n in names for n in top), top


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
