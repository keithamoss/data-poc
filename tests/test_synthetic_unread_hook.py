"""The audit hook REQ-GEN-370 criterion 3's tests watch with
(tests/synthetic_unread_support.py) sees each kind of read it claims to, and
excuses only the one read REQ-GEN-381 owns. No database, no pipeline."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from synthetic_unread_support import asset_folder, watching


@pytest.fixture
def folder(tmp_path):
    return asset_folder(tmp_path, synthetic="decisions: []\n")


def _reads(seen) -> list:
    return seen["reads"]


class TestWhatTheHookSees:

    def test_an_open_is_a_read(self, folder):
        with watching(folder) as seen:
            (folder / "synthetic" / "scripted_decisions.yaml").read_text()
        assert _reads(seen)

    def test_a_child_process_handed_a_synthetic_path_is_a_read(self, folder):
        """dbt runs as a child process (qa_tools/common/dbt_worker.py), which
        the hook cannot follow - so a path under synthetic/ handed to one is."""
        target = folder / "synthetic" / "scripted_decisions.yaml"
        with watching(folder) as seen:
            subprocess.run([sys.executable, "-c", "pass", str(target)], check=True)
        assert any(event == "subprocess.Popen" for event, *_ in _reads(seen)), seen

    def test_a_path_inside_a_child_processs_argument_is_a_read(self, folder):
        with watching(folder) as seen:
            subprocess.run([sys.executable, "-c", "pass",
                            f"--project-dir={folder / 'synthetic'}"], check=True)
        assert _reads(seen)

    def test_a_child_process_started_in_synthetic_is_a_read(self, folder):
        with watching(folder) as seen:
            subprocess.run([sys.executable, "-c", "pass"], cwd=folder / "synthetic",
                           check=True)
        assert _reads(seen)

    def test_a_listing_by_descriptor_is_a_read(self, folder):
        fd = os.open(folder / "synthetic", os.O_RDONLY)
        try:
            with watching(folder) as seen:
                list(os.scandir(fd))
        finally:
            os.close(fd)
        assert _reads(seen)

    def test_a_relative_open_is_a_read(self, folder, monkeypatch):
        monkeypatch.chdir(folder)
        with watching(folder) as seen:
            open(os.path.join("synthetic", "scripted_decisions.yaml")).close()
        assert _reads(seen)

    def test_opening_the_folder_for_a_descriptor_is_a_read(self, folder):
        """A file opened by name against a directory descriptor carries no
        path in its event - but getting the descriptor opens the folder."""
        with watching(folder) as seen:
            fd = os.open(folder / "synthetic", os.O_RDONLY)
            os.close(os.open("scripted_decisions.yaml", os.O_RDONLY, dir_fd=fd))
            os.close(fd)
        assert _reads(seen)

    def test_a_read_elsewhere_is_not_a_read(self, folder):
        with watching(folder) as seen:
            (folder / "data-asset.yaml").read_text()
            subprocess.run([sys.executable, "-c", "pass"], check=True)
        assert _reads(seen) == []
        assert seen["asset_reads"] > 0


class TestTheOneExcuse:

    @pytest.mark.asset("daily")
    def test_a_player_built_outside_the_batch_pass_is_not_excused(self, folder):
        """Only orchestrate._begin's Player is excused (REQ-GEN-381 ends it);
        one built anywhere else reading the file is a read."""
        from asset_model import assets
        from qa_tools.common import scripted_decisions

        before = assets.use_folder(folder)
        try:
            with watching(folder) as seen:
                scripted_decisions.Player("civil-registration", placements={})
        finally:
            assets.restore(before)
        assert _reads(seen), seen
        assert seen["allowed"] == []


#: The data asset this module's tests act for (C11, Keith 2026-11-02).
pytestmark = pytest.mark.asset("daily")
