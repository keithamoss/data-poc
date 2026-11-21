"""REQ-TEST-388: every asset's dbt project declares the same dbt packages and
versions, and `mothman dashboard validate-dbt-packages` fails when two
assets' packages.yml or package-lock.yml differ once parsed.

These drive the real gate over asset folders written to a temporary
directory, copied from this repository's own, and the real command over this
repository. No database, asset selection or network."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from qa_tools.common import validate_dbt_packages as vdp

ROOT = Path(__file__).resolve().parent.parent

#: REQ-TEST-375: cheap and database-free, so in push CI's critical set.
#: Asset-free: the gate compares every asset; quarterly is the suite's default (C11).
pytestmark = [pytest.mark.critical, pytest.mark.asset("quarterly")]

NEXT = "make both match, then run `mothman env dbt-deps` for each asset"


def _asset(root: Path, name: str) -> Path:
    """assets/<name>/dbt/ holding copies of this repository's quarterly files."""
    dbt = root / "assets" / name / "dbt"
    dbt.mkdir(parents=True)
    for file in vdp.FILES:
        shutil.copy(ROOT / "assets" / "quarterly" / "dbt" / file, dbt / file)
    return dbt


@pytest.fixture
def two(tmp_path):
    return tmp_path, _asset(tmp_path, "alpha"), _asset(tmp_path, "beta")


def _run(root: Path, capsys) -> tuple[int, str]:
    code = vdp.main(root=root)
    return code, capsys.readouterr().out


def _edit(path: Path, change) -> None:
    doc = yaml.safe_load(path.read_text())
    change(doc)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def test_identical_assets_pass(two, capsys):
    root, _, _ = two
    code, out = _run(root, capsys)
    assert code == 0, out
    assert "agree across 2 assets (alpha, beta)" in out


def test_a_differing_package_revision_fails(two, capsys):
    root, _, beta = two
    _edit(beta / "packages.yml", lambda d: d["packages"][0].update(revision="1.3.2"))
    code, out = _run(root, capsys)
    assert code == 1
    line = next(x for x in out.splitlines() if x.startswith("dbt packages: assets"))
    assert "'alpha' and 'beta' differ in packages.yml at packages[0].revision" in line
    assert "alpha: '1.3.1', beta: '1.3.2'" in line
    assert line.endswith(NEXT)


def test_a_differing_lock_hash_fails(two, capsys):
    root, _, beta = two
    _edit(beta / "package-lock.yml", lambda d: d.update(sha1_hash="0" * 40))
    code, out = _run(root, capsys)
    assert code == 1
    assert "differ in package-lock.yml at sha1_hash" in out
    assert out.strip().splitlines()[0].endswith(NEXT)


def test_a_package_one_asset_lacks_fails(two, capsys):
    root, _, beta = two
    _edit(beta / "packages.yml", lambda d: d["packages"].append({"package": "x/y",
                                                                  "version": "1.0.0"}))
    code, out = _run(root, capsys)
    assert code == 1
    assert "at packages[1] (alpha: '(absent)'" in out


def test_a_difference_in_comments_and_quoting_alone_passes(two, capsys):
    root, _, beta = two
    path = beta / "packages.yml"
    path.write_text("# a comment is not a package\n"
                    + path.read_text().replace('"https://github.com/dbt-labs/dbt-utils.git"',
                                               "https://github.com/dbt-labs/dbt-utils.git")
                    + "# nor is this\n")
    code, out = _run(root, capsys)
    assert code == 0, out


def test_one_asset_passes_and_says_it_compared_one(tmp_path, capsys):
    _asset(tmp_path, "only")
    code, out = _run(tmp_path, capsys)
    assert code == 0
    assert "compared one asset (only)" in out


def test_this_repository_passes_through_the_real_command():
    from cli.dashboard import dashboard_group

    assert len(vdp.asset_projects(ROOT)) >= 2, "fewer than two assets - nothing compared"
    result = CliRunner().invoke(dashboard_group, ["validate-dbt-packages"])
    assert result.exit_code == 0, result.output
    assert "agree across" in result.output


def test_mothman_check_runs_it_once_whatever_the_asset(monkeypatch):
    import cli.check as check_cli

    calls = []

    class Done:
        returncode = 0

    monkeypatch.setattr(check_cli.subprocess, "run", lambda argv, **kw: calls.append(
        (argv, (kw.get("env") or {}).get("MOTHMAN_ASSET"))) or Done())
    monkeypatch.setattr(check_cli.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.delenv("MOTHMAN_ASSET", raising=False)
    result = CliRunner().invoke(check_cli.check_command, ["--only", "dbt packages"])
    assert result.exit_code == 0, result.output
    assert calls == [(["uv", "run", "mothman", "dashboard", "validate-dbt-packages"], None)]
    labels = [g[0] for g in check_cli._GATES]
    assert labels.index("dbt packages") < labels.index("schedule")


def test_validate_config_runs_it():
    wf = yaml.safe_load((ROOT / ".github/workflows/validate-config.yml").read_text())
    runs = [s.get("run") for s in wf["jobs"]["validate"]["steps"]]
    assert "uv run mothman dashboard validate-dbt-packages" in runs


def test_an_asset_folder_with_no_dbt_project_fails(two, capsys):
    """Post-build critic (2026-11-15): an asset folder - one with a
    data-asset.yaml - that has no dbt/ differs, as a missing file does."""
    root, _, _ = two
    (root / "assets" / "gamma").mkdir()
    (root / "assets" / "gamma" / "data-asset.yaml").write_text("data_asset_id: gamma\n")
    code, out = _run(root, capsys)
    assert code == 1
    assert "asset 'gamma' has no dbt/packages.yml, which 'alpha' has" in out
    assert out.strip().splitlines()[0].endswith(NEXT)
