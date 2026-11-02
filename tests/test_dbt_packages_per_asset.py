"""Each asset's dbt packages, installed by `mothman env dbt-deps` and required
before dbt runs (REQ-QAC-368 criteria 5 and 6).

Against an asset of the test's own whose dbt project pulls in one LOCAL
package, so installing it needs no network.
"""
from __future__ import annotations

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
    real = assets.selected()
    # The real asset's own folder, its adapters (collections/) among it - all
    # but its dbt project, which is rebuilt below without its packages.
    for entry in real.folder.iterdir():
        if entry.name != real.dbt_project.name:
            (folder / entry.name).symlink_to(entry)
    dbt = folder / real.dbt_project.name
    dbt.mkdir()
    for entry in real.dbt_project.iterdir():
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

    def test_an_edited_packages_file_installs_again(self, an_asset, tmp_path):
        """A package added to packages.yml: dbt's own lock no longer matches
        it, so the packages install again (REQ-QAC-368 d5, C6)."""
        assert _dbt_deps().exit_code == 0
        _another_package(tmp_path, an_asset)
        result = _dbt_deps()
        assert result.exit_code == 0, result.output
        assert "already installed" not in result.output
        assert (an_asset / "dbt_packages" / "second_probe").exists()


class TestInstalledIsDecidedByDbtsOwnLock:
    """C6 (Keith, 2026-11-02, REQ-QAC-368 d5): whether the packages count
    as installed is decided by dbt's own package-lock.yml - the hash dbt
    itself writes of packages.yml, and the packages that lock names being in
    dbt_packages/ - never by a stamp file of ours."""

    def test_packages_a_bare_dbt_deps_installed_count_as_installed(self, an_asset, monkeypatch):
        """No stamp of ours: a bare `dbt deps` wrote the lock and the
        packages, and that is enough."""
        import sys

        dbt = Path(sys.executable).parent / "dbt"
        done = subprocess.run([str(dbt), "deps", "--project-dir", str(an_asset),
                               "--profiles-dir", str(ROOT / "qa_tools" / "dbt_profiles")],
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr
        ran = []
        real = subprocess.run
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.append(a) or real(*a, **k))
        result = _dbt_deps()
        assert result.exit_code == 0, result.output
        assert "already installed" in result.output
        assert ran == []

    def test_no_file_of_ours_is_written_beside_the_packages(self, an_asset):
        assert _dbt_deps().exit_code == 0
        installed = {p.name for p in (an_asset / "dbt_packages").iterdir()}
        assert installed == {"shared_probe"}

    def test_a_change_dbt_does_not_count_is_still_installed(self, an_asset, monkeypatch):
        """A comment in packages.yml leaves dbt's own hash where it was, so
        dbt would not re-lock it, and nor does this."""
        assert _dbt_deps().exit_code == 0
        (an_asset / "packages.yml").write_text("# a comment\n" + (an_asset / "packages.yml").read_text())
        ran = []
        real = subprocess.run
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.append(a) or real(*a, **k))
        result = _dbt_deps()
        assert result.exit_code == 0, result.output
        assert "already installed" in result.output
        assert ran == []

    def test_a_missing_lock_installs_again(self, an_asset):
        assert _dbt_deps().exit_code == 0
        (an_asset / "package-lock.yml").unlink()
        result = _dbt_deps()
        assert result.exit_code == 0, result.output
        assert "already installed" not in result.output
        assert (an_asset / "package-lock.yml").is_file()


def _another_package(tmp_path, project):
    second = tmp_path / "second"
    (second / "macros").mkdir(parents=True)
    (second / "dbt_project.yml").write_text('name: second_probe\nversion: "1.0"\n'
                                            'config-version: 2\nmacro-paths: ["macros"]\n')
    (second / "macros" / "probe2.sql").write_text("{% macro probe2() %}2{% endmacro %}\n")
    with open(project / "packages.yml", "a") as f:
        f.write(f"  - local: {second}\n")


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


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
