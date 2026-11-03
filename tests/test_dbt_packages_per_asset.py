"""Each asset's dbt packages, installed by `mothman env dbt-deps` and required
before dbt runs (REQ-QAC-368 criteria 5 and 6).

Against an asset of the test's own whose dbt project pulls in one LOCAL
package, so installing it needs no network.
"""
from __future__ import annotations

import os
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

    # ONE MEANING OF "INSTALLED" EVERYWHERE (Keith, 2026-11-03, morning report
    # 12 Q10; REQ-QAC-368 criterion 6 as amended): the run guard uses the
    # package-lock rule `mothman env dbt-deps` uses, so packages installed
    # once and then outdated by an edit to packages.yml are refused too.
    def test_a_stale_lock_is_refused_as_dbt_deps_would_reinstall(self, an_asset, tmp_path, monkeypatch):
        from qa_tools.common import dbt_worker
        from qa_tools.tools import run_dbt

        assert _dbt_deps().exit_code == 0
        assert assets.dbt_project_ready() == an_asset, "precondition: installed and current"
        _another_package(tmp_path, an_asset)
        invoked = []
        monkeypatch.setattr(dbt_worker, "invoke", lambda *a, **k: invoked.append(a))
        with pytest.raises(assets.DbtPackagesMissing) as exc:
            run_dbt.test_names_by_check_id("child-protection")
        assert invoked == []
        assert "'one'" in str(exc.value) and "mothman env dbt-deps" in str(exc.value)

    def test_a_package_deleted_since_is_refused(self, an_asset):
        import shutil

        assert _dbt_deps().exit_code == 0
        installed = [p for p in (an_asset / "dbt_packages").iterdir() if p.is_dir()]
        assert installed, "precondition: a package is installed"
        # A local package is installed as a link to its folder.
        installed[0].unlink() if installed[0].is_symlink() else shutil.rmtree(installed[0])
        (an_asset / "dbt_packages" / "leftover").mkdir()
        (an_asset / "dbt_packages" / "leftover" / "x").write_text("")
        with pytest.raises(assets.DbtPackagesMissing):
            assets.dbt_project_ready()


REAL_ASSETS = sorted(p.parent.parent.name for p in (ROOT / "assets").glob("*/dbt/dbt_project.yml"))


def _compiled(asset: str, tmp_path) -> dict:
    """dbt's own manifest of the real asset's project, compiled into a
    target of the test's own - every test's SQL rendered from the macros it
    names. Against the suite's own test database's server; nothing is built."""
    import json
    import sys

    from psycopg.conninfo import conninfo_to_dict

    info = conninfo_to_dict(os.environ["MOTHMAN_TEST_DSN"])
    env = {**os.environ, "DBT_PG_HOST": info.get("host") or "localhost",
           "DBT_PG_PORT": str(info.get("port") or 5432), "DBT_PG_USER": info.get("user") or "",
           "DBT_PG_PASSWORD": info.get("password") or "", "DBT_PG_DBNAME": info.get("dbname") or "postgres",
           "DBT_PG_SCHEMA": "bfol_never_built", "DBT_RUN_SCHEMA": "bfol_never_built",
           "DBT_SEND_ANONYMOUS_USAGE_STATS": "False"}
    project = ROOT / "assets" / asset / "dbt"
    if not assets_installed(project):
        pytest.fail(f"{asset}'s dbt packages are not installed - run `mothman env dbt-deps`")
    dbt = Path(sys.executable).parent / "dbt"
    done = subprocess.run([str(dbt), "compile", "--project-dir", str(project), "--profiles-dir",
                           str(ROOT / "qa_tools" / "dbt_profiles"), "--target-path", str(tmp_path),
                           "--select", "resource_type:test", "--quiet"],
                          capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads((tmp_path / "manifest.json").read_text())


def assets_installed(project) -> bool:
    from qa_tools.common import dbt_common

    return dbt_common.packages_installed(project)


@pytest.mark.parametrize("asset", REAL_ASSETS)
class TestEachAssetsProject:
    """Each real asset's dbt project (REQ-QAC-368 criteria 1, 2 and 10):
    named mothman_<asset> (C13, Keith 2026-11-02), and reading the shared
    macros and generic tests straight from dbt_shared/ through its own
    macro-paths and test-paths, with no forwarding file (C12)."""

    def test_there_are_two_real_assets(self, asset):
        assert len(REAL_ASSETS) >= 2, REAL_ASSETS

    def test_every_node_is_named_for_its_asset(self, asset, tmp_path):
        manifest = _compiled(asset, tmp_path)
        assert manifest["metadata"]["project_name"] == f"mothman_{asset}"
        ours = [uid for uid, n in manifest["nodes"].items() if n["package_name"] != "dbt_utils"]
        assert ours, "the project compiled no nodes of its own"
        assert all(uid.split(".")[1] == f"mothman_{asset}" for uid in ours), ours[:5]

    def test_a_check_using_a_shared_test_compiles_from_dbt_shared(self, asset, tmp_path):
        import re

        names = {m for f in (ROOT / "dbt_shared").rglob("*.sql")
                 for m in re.findall(r"{%-?\s*test\s+(\w+)\s*\(", f.read_text())}
        assert names, "dbt_shared/ defines no generic test"
        manifest = _compiled(asset, tmp_path)
        shared = [n for n in manifest["nodes"].values()
                  if (n.get("test_metadata") or {}).get("name") in names]
        assert shared, f"no check in {asset} uses one of dbt_shared's tests {sorted(names)}"
        for node in shared:
            uid = f"macro.mothman_{asset}.test_{node['test_metadata']['name']}"
            assert uid in node["depends_on"]["macros"], node["depends_on"]["macros"]
            assert Path(manifest["macros"][uid]["original_file_path"]).parts[3] == "dbt_shared"
            assert node["compiled_code"].strip()

    def test_no_forwarding_file_and_no_package_entry_for_dbt_shared(self, asset):
        import yaml

        project = ROOT / "assets" / asset / "dbt"
        assert not (project / "macros").exists()
        packages = yaml.safe_load((project / "packages.yml").read_text())["packages"]
        assert not [p for p in packages if "local" in p], packages


class TestTheParseCacheSeesTheSharedFolder:
    """The parsed-project cache is keyed on every file dbt reads
    (REQ-PIPE-189), and since C12 that includes dbt_shared/, outside the
    project, through its macro-paths and test-paths."""

    def test_an_edit_in_a_shared_path_outside_the_project_changes_the_key(self, tmp_path):
        from qa_tools.common import dbt_common

        project, shared = tmp_path / "proj", tmp_path / "shared"
        (project / "models").mkdir(parents=True)
        (shared / "macros").mkdir(parents=True)
        (project / "dbt_project.yml").write_text(
            "name: p\nmacro-paths: ['../shared/macros']\ntest-paths: ['tests', '../shared/tests']\n")
        macro = shared / "macros" / "m.sql"
        macro.write_text("{% macro m() %}1{% endmacro %}\n")
        before = dbt_common._project_fingerprint(str(project))
        macro.write_text("{% macro m() %}2{% endmacro %}\n")
        assert dbt_common._project_fingerprint(str(project)) != before


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
