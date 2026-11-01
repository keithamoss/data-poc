"""The asset a command acts for comes from MOTHMAN_ASSET, with no default
(REQ-PIPE-363 criterion 10): `--help` and `mothman check` run without one, an
unset or mistyped variable is named rather than hidden behind 'No such
command', a collection the selected asset does not hold is 'No such command'
with the asset's own commands beneath it, the bare wizard refuses before its
banner, and the asset is named wherever the environment is.

Each refusal runs in a real non-TTY session - a subprocess with no terminal -
because that is where a person meets it first.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from qa_tools.common import assets

ROOT = Path(__file__).resolve().parent.parent

#: Points the resolver at an assets/ folder of the test's own, then runs the
#: CLI as the console script does.
_DRIVER = """
import sys, runpy
from pathlib import Path
from qa_tools.common import assets
if sys.argv[1]:
    assets.use_root(Path(sys.argv[1]))
sys.argv = ["mothman", *sys.argv[2:]]
runpy.run_module("cli.app", run_name="__main__")
"""


def _mothman(*args: str, asset: str | None, root: Path | None = None):
    env = {k: v for k, v in os.environ.items() if k != assets.ASSET_ENV}
    if asset is not None:
        env[assets.ASSET_ENV] = asset
    return subprocess.run([sys.executable, "-c", _DRIVER, str(root or ""), *args], cwd=ROOT,
                          env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          timeout=300)


def _said(result) -> str:
    """Everything the command printed, with Rich's error box and its line
    wrapping flattened to single spaces - a sentence is one sentence however
    wide the terminal is."""
    return re.sub(r"[│╭╮╰╯─\s]+", " ", result.stdout + result.stderr)


@pytest.fixture
def two_assets(tmp_path) -> Path:
    """assets/ with two folders: `quarterly`, today's configuration without
    Civil Registration, and `daily`, today's configuration whole - each
    reaching today's adapters and providers by its own folders."""
    root = tmp_path / "assets"
    real = ROOT / "contract"
    for name in ("quarterly", "daily"):
        folder = root / name
        folder.mkdir(parents=True)
        for entry in real.iterdir():
            if entry.name != "data-asset.yaml":
                (folder / entry.name).symlink_to(entry)
        doc = yaml.safe_load((real / "data-asset.yaml").read_text())
        if name == "quarterly":
            for agency in doc["hierarchy"]["agencies"]:
                agency["collections"] = [c for c in agency["collections"]
                                         if c["id"] != "civil-registration"]
            doc["hierarchy"]["agencies"] = [a for a in doc["hierarchy"]["agencies"]
                                            if a["collections"]]
        (folder / "data-asset.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
        (folder / "collections").symlink_to(ROOT / "qa_tools" / "collections")
        (folder / "synthetic").mkdir()
        (folder / "synthetic" / "collections").symlink_to(ROOT / "generator" / "collections")
    (root / "environments.yaml").symlink_to(real / "environments.yaml")
    return root


class TestWithNoAssetSet:

    def test_help_runs_and_says_how_to_set_one(self):
        result = _mothman("--help", asset=None)
        assert result.returncode == 0, _said(result)
        assert "Collections" in result.stdout
        assert "Set MOTHMAN_ASSET to one of: daily, quarterly" in result.stdout
        # No collection's group is built, so none is listed.
        assert not re.search(r"^\W*(bdm|cp)\s", result.stdout, re.M), result.stdout

    def test_check_runs_its_gates_for_each_asset_folder(self):
        result = _mothman("check", "--only", "people", asset=None)
        assert result.returncode == 0, _said(result)
        assert "people validation OK" in result.stdout

    def test_a_collection_command_names_the_variable_not_no_such_command(self):
        result = _mothman("cp", "qa", asset=None)
        assert result.returncode != 0
        said = _said(result)
        assert "No such command" not in said and "Traceback" not in said, said
        assert "MOTHMAN_ASSET is not set" in said
        assert "Set it to one of: daily, quarterly" in said and "deliberately no default" in said

    def test_a_mistyped_asset_is_named_the_same_way(self):
        result = _mothman("cp", "qa", asset="data-asset-one")
        assert result.returncode != 0
        said = _said(result)
        assert "No such command" not in said and "Traceback" not in said, said
        assert "MOTHMAN_ASSET is 'data-asset-one', which names no asset folder" in said

    def test_the_bare_wizard_refuses_before_its_banner(self):
        result = _mothman(asset=None)
        assert result.returncode != 0
        said = _said(result)
        assert "MOTHMAN_ASSET is not set" in said
        assert "\\/\\/" not in said and "Traceback" not in said, said

    #: THE GROUNDWORK CRITIC'S TWO (REQ-PIPE-363 criterion 6, post-build-review):
    #: `scenarios list` read the placements through an import-time constant,
    #: and `pipeline checkpoint list` opened its own connection to the server
    #: without asking which asset it acts for.
    @pytest.mark.parametrize("command", [("scenarios", "list"),
                                         ("pipeline", "checkpoint", "list")])
    def test_a_command_reading_state_or_connecting_is_refused(self, command):
        result = _mothman(*command, asset=None)
        assert result.returncode != 0, _said(result)
        said = _said(result)
        assert "MOTHMAN_ASSET is not set" in said and "Set it to one of: daily, quarterly" in said
        assert "Traceback" not in said, said

    def test_tidying_test_databases_needs_no_asset(self):
        """PROVISIONAL (REQ-PIPE-363): the suite's own databases belong to no
        asset - each test selects its own - so this one connection is exempt."""
        result = _mothman("env", "tidy-test-databases", "--dry-run",
                          "--older-than-hours", "100000", asset=None)
        assert result.returncode == 0, _said(result)

    @pytest.mark.parametrize("asset", [None, "nowhere"])
    def test_a_command_that_reads_the_asset_is_refused_before_it_reads(self, asset):
        result = _mothman("collections", asset=asset)
        assert result.returncode != 0
        said = _said(result)
        assert "MOTHMAN_ASSET" in said and "Set it to one of: daily, quarterly" in said
        assert "Traceback" not in said, said


class TestAnotherAssetsCollection:

    def test_is_no_such_command_with_the_assets_own_beneath(self, two_assets):
        result = _mothman("bdm", "qa", asset="quarterly", root=two_assets)
        assert result.returncode != 0
        said = _said(result)
        assert "No such command 'bdm'" in said
        assert "Commands for asset 'quarterly':" in said
        listed = said.split("Commands for asset 'quarterly':", 1)[1]
        assert "cp" in listed.split() and "bdm" not in listed.split()

    def test_the_other_asset_still_has_it(self, two_assets):
        result = _mothman("bdm", "--help", asset="daily", root=two_assets)
        assert result.returncode == 0, _said(result)


class TestTheAssetIsNamed:

    def test_beside_the_environment(self, monkeypatch):
        from cli import common

        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        assert common.environment_statement() == \
            "Environment: Claude Code sandbox (not production) · Asset: quarterly"

    def test_on_every_wizard_prompt(self, monkeypatch):
        import questionary

        from cli import common

        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        question = common._with_environment_toolbar(questionary.text("m"))
        last = question.application.layout.container.children[-1]
        text = "".join(fragment for _, fragment in last.content.content.text)
        assert "· Asset: quarterly" in text

    def test_in_env_current(self):
        result = _mothman("env", "current", asset="quarterly")
        assert result.returncode == 0, _said(result)
        assert "Asset: quarterly" in result.stdout

    def test_in_env_list(self):
        result = _mothman("env", "list", asset="quarterly")
        assert result.returncode == 0, _said(result)
        assert "Asset: quarterly" in result.stdout

    def test_env_list_says_when_none_is_set(self):
        result = _mothman("env", "list", asset=None)
        assert result.returncode == 0, _said(result)
        assert "MOTHMAN_ASSET is not set" in result.stdout
