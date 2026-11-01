"""Each asset's dbt packages, installed by `mothman env dbt-deps` and required
before dbt runs (REQ-QAC-368 criteria 5 and 6).

Against an asset of the test's own whose dbt project pulls in one LOCAL
package, so installing it needs no network.
"""
from __future__ import annotations

import asset_folders
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from qa_tools.common import assets

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def an_asset(tmp_path, monkeypatch) -> Path:
    """assets/one/, today's configuration and adapters, whose dbt project is a
    copy of today's minus its installed packages, pulling in one local
    package beside it. Selected."""
    root = tmp_path / "assets"
    folder = root / "one"
    folder.mkdir(parents=True)
    for entry in (asset_folders.real_folder()).iterdir():
        (folder / entry.name).symlink_to(entry)
    (folder / "collections").symlink_to(ROOT / "qa_tools" / "collections")
    dbt = folder / "dbt"
    dbt.mkdir()
    for entry in (ROOT / "dbt_project").iterdir():
        if entry.name not in ("dbt_packages", "packages.yml", "package-lock.yml", "target", "logs"):
            (dbt / entry.name).symlink_to(entry)
    shared = tmp_path / "shared"
    (shared / "macros").mkdir(parents=True)
    (shared / "dbt_project.yml").write_text('name: shared_probe\nversion: "1.0"\n'
                                           'config-version: 2\nmacro-paths: ["macros"]\n')
    (shared / "macros" / "probe.sql").write_text("{% macro probe() %}1{% endmacro %}\n")
    (dbt / "packages.yml").write_text(f"packages:\n  - local: {shared}\n")
    assets.use_root(root)
    monkeypatch.setenv(assets.ASSET_ENV, "one")
    return dbt


def _dbt_deps():
    from cli.env import env_group

    return CliRunner().invoke(env_group, ["dbt-deps"])


class TestInstalling:

    def test_it_installs_the_selected_assets_packages(self, an_asset):
        result = _dbt_deps()
        assert result.exit_code == 0, result.output
        assert (an_asset / "dbt_packages" / "shared_probe").exists()
        assert "one" in result.output

    def test_run_again_it_changes_nothing_and_says_so(self, an_asset, monkeypatch):
        assert _dbt_deps().exit_code == 0
        before = sorted(p.name for p in (an_asset / "dbt_packages").iterdir())
        ran = []
        real = subprocess.run
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.append(a) or real(*a, **k))
        result = _dbt_deps()
        assert result.exit_code == 0, result.output
        assert "already installed" in result.output
        assert ran == []
        assert sorted(p.name for p in (an_asset / "dbt_packages").iterdir()) == before

    def test_a_deleted_package_installs_again(self, an_asset):
        """The groundwork critic: the stamp alone said installed after the
        package directory itself had gone, so dbt then failed to compile."""
        import shutil

        assert _dbt_deps().exit_code == 0
        installed = an_asset / "dbt_packages" / "shared_probe"
        if installed.is_symlink() or installed.is_file():
            installed.unlink()
        else:
            shutil.rmtree(installed)
        result = _dbt_deps()
        assert result.exit_code == 0, result.output
        assert "already installed" not in result.output
        assert installed.exists()

    def test_an_edited_packages_file_installs_again(self, an_asset):
        assert _dbt_deps().exit_code == 0
        (an_asset / "packages.yml").write_text((an_asset / "packages.yml").read_text() + "\n")
        result = _dbt_deps()
        assert result.exit_code == 0, result.output
        assert "already installed" not in result.output


class TestARunWithoutThemIsRefused:

    def test_before_dbt_is_invoked_naming_the_asset_and_the_command(self, an_asset, monkeypatch):
        from qa_tools.common import dbt_worker
        from qa_tools.tools import run_dbt

        invoked = []
        monkeypatch.setattr(dbt_worker, "invoke", lambda *a, **k: invoked.append(a))
        with pytest.raises(assets.DbtPackagesMissing) as exc:
            run_dbt.test_names_by_check_id("child-protection")
        assert invoked == []
        assert "'one'" in str(exc.value) and "mothman env dbt-deps" in str(exc.value)
