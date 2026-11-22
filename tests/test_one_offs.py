"""one-offs/<kind>/<id>/ read by the resolver beside assets/ (REQ-PIPE-446),
and REQ-PIPE-363's one-off amendments (criteria 1, 4, 5, 6, 11 and 12).

Driven through a TEST KIND, 'audit' (tests/one_off_support.py): this is the
kind-neutral layer, and the extraction's own files are REQ-PIPE-439's and
REQ-PIPE-440's. The CLI's refusals run in a real non-TTY session - a
subprocess with no terminal - with the resolver pointed at the test's
one-offs root and the test kind registered, as tests/test_cli_asset_selection.py
runs the asset refusals.
"""
from __future__ import annotations

import multiprocessing
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import one_off_support
from asset_model import assets
from qa_tools.common import validate_folders

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def one_offs(tmp_path, monkeypatch):
    world = one_off_support.OneOffs(tmp_path, monkeypatch)
    yield world
    world.close()


class TestTheListing:
    """Criteria 1 and 6."""

    def test_every_kind_folder_is_listed_directories_only(self, one_offs):
        one_offs.add("cohort-a")
        one_offs.add("cohort-b")
        (one_offs.root / one_off_support.KIND / "notes.txt").write_text("not a one-off")
        (one_offs.root / one_off_support.KIND / ".hidden").mkdir()
        assert assets.one_offs() == [("audit", "cohort-a"), ("audit", "cohort-b")]

    def test_the_enduring_assets_list_is_assets_alone(self, one_offs):
        one_offs.add("cohort-a")
        assert assets.names() == ["daily", "quarterly"]
        assert "cohort-a" not in [a.name for a in assets.every()]

    def test_a_bad_name_fails_check_and_selects_nothing(self, one_offs):
        one_offs.add("Cohort_A", data_asset_id="Cohort_A")
        assert assets.one_offs() == []
        assert any("Cohort_A" in p for p in validate_folders.problems())
        with pytest.raises(assets.OneOffRefused):
            assets.select_one_off("Cohort_A")

    def test_a_listing_change_is_seen(self, one_offs):
        assert assets.one_offs() == []
        one_offs.add("cohort-c")
        assert assets.one_offs() == [("audit", "cohort-c")]


class TestAKindNeedsItsPlugIn:
    """Criterion 2."""

    def test_a_kind_folder_with_no_plug_in_fails_check_naming_it(self, one_offs):
        one_offs.add("cohort-a", kind="survey")
        found = validate_folders.problems()
        assert any(str(one_offs.root / "survey") in p and "plug-in" in p for p in found), found

    def test_a_registered_kind_passes(self, one_offs):
        one_offs.add("cohort-a")
        assert validate_folders.problems() == []


class TestSelectingByID:
    """Criteria 3, 11 and 12."""

    def test_its_configuration_state_paths_and_database(self, one_offs):
        from qa_tools.common import supply_db

        import yaml

        folder = one_offs.add("cohort-a")
        doc = yaml.safe_load((folder / "data-asset.yaml").read_text())
        doc["hierarchy"] = {"agencies": [{"id": "an-agency", "name": "An agency", "collections": [
            {"id": "a-collection", "name": "A collection", "short": "ac", "run_prefix": "ac_",
             "contract": "an-agency/a-collection-contract.yaml", "delivery_boundary": "directory",
             "datasets": [{"id": "a-table", "name": "A table", "table": "a_table"}]}]}]}
        (folder / "data-asset.yaml").write_text(yaml.safe_dump(doc))
        chosen = assets.select_one_off("cohort-a")
        assert chosen.folder == folder and chosen.kind == "audit" and chosen.is_one_off
        assert chosen.data == ROOT / "data" / "cohort-a"
        assert chosen.reports == ROOT / "reports" / "cohort-a"
        assert supply_db.asset_database() == "supply_cohort-a"
        assert assets.selected() == chosen and assets.why_not_selected() is None
        assert assets.ASSET_ENV not in os.environ, "never written into MOTHMAN_ASSET"

    def test_mothman_asset_set_beside_it_is_refused_before_any_configuration(
            self, one_offs, monkeypatch):
        from asset_model import config_yaml

        one_offs.add("cohort-a")
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        monkeypatch.setattr(config_yaml, "load", lambda *a, **k: pytest.fail("read config"))
        with pytest.raises(assets.OneOffRefused, match=r"MOTHMAN_ASSET is 'daily'"):
            assets.select_one_off("cohort-a")

    def test_an_enduring_asset_states_no_kind(self, monkeypatch):
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        assert assets.selected().kind is None


class TestOneIDNamespace:
    """Criterion 4."""

    def test_an_id_under_assets_and_a_kind_is_selected_as_neither(self, one_offs, monkeypatch):
        one_offs.add("daily")
        with pytest.raises(assets.OneOffRefused) as refused:
            assets.select_one_off("daily")
        assert str(ROOT / "assets" / "daily") in str(refused.value)
        assert str(one_offs.root / "audit" / "daily") in str(refused.value)
        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        with pytest.raises(assets.OneOffRefused):
            assets.selected()
        assert any("'daily' names 2 folders" in p for p in validate_folders.problems())

    def test_an_id_under_two_kinds(self, one_offs):
        from asset_model import one_off_kinds

        one_off_kinds.register(one_off_kinds.Kind("survey", "survey", "surveys", "Survey check"))
        try:
            one_offs.add("cohort-a")
            one_offs.add("cohort-a", kind="survey")
            with pytest.raises(assets.OneOffRefused):
                assets.select_one_off("cohort-a")
            assert any("'cohort-a' names 2 folders" in p for p in validate_folders.problems())
        finally:
            one_off_kinds.unregister("survey")


class TestFolderIdentity:
    """Criteria 5 and 13."""

    def test_a_data_asset_id_other_than_the_folder_fails(self, one_offs):
        one_offs.add("cohort-a", data_asset_id="cohort-b")
        found = validate_folders.problems()
        assert any("'cohort-b'" in p and "'cohort-a'" in p for p in found), found

    def test_the_enduring_assets_match_today(self):
        assert validate_folders.problems() == []

    def test_a_one_off_naming_no_project_fails(self, one_offs):
        one_offs.add("cohort-a", project=None)
        assert any("names no project" in p for p in validate_folders.problems())


def _child_selection():
    from asset_model import assets as a

    chosen = a.selected()
    return chosen.name, chosen.kind, str(a.one_offs_root()), os.environ.get(a.ASSET_ENV)


class TestAChildProcessActsForTheSameOneOff:
    """Criterion 7."""

    def test_handoff_carries_the_one_off_and_its_root(self, one_offs):
        one_offs.add("cohort-a")
        assets.select_one_off("cohort-a")
        with multiprocessing.get_context("spawn").Pool(
                1, initializer=assets.adopt, initargs=assets.handoff()) as pool:
            got = pool.apply(_child_selection)
        assert got == ("cohort-a", "audit", str(one_offs.root), None)


class TestNeverGitHub:
    """Criterion 14: no ticket, comment or API call for a one-off."""

    def test_no_ticket_service_whatever_the_environment(self, one_offs, monkeypatch):
        from qa_tools.common import environments, ticket_reconciler

        monkeypatch.setattr(environments, "current_or_none", lambda *a: environments.Environment(
            id="production", label="P", ticketing=True))
        monkeypatch.setattr(environments, "ticket_repository", lambda: "o/r")
        one_offs.add("cohort-a")
        assets.select_one_off("cohort-a")
        assert ticket_reconciler.service_from_env() is None

    @pytest.mark.parametrize("module", ["ticket_github", "ticket_sync", "leaderboard",
                                        "ci_usage"])
    def test_every_gh_boundary_refuses(self, one_offs, monkeypatch, module):
        import importlib

        ran = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: ran.append(a))
        one_offs.add("cohort-a")
        assets.select_one_off("cohort-a")
        mod = importlib.import_module(f"qa_tools.common.{module}")
        call = mod._gh if module == "ticket_github" else mod._run_gh
        with pytest.raises(assets.NeverGitHub):
            call(["issue", "list"])
        assert ran == [], "gh was started"

    def test_an_asset_still_reaches_gh(self, monkeypatch):
        from qa_tools.common import ci_usage

        monkeypatch.setenv(assets.ASSET_ENV, "daily")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("R", (), {"stdout": "ok"})())
        assert ci_usage._run_gh(["api", "x"]) == "ok"


# ---- the terminal, in a real non-TTY session (REQ-PIPE-363) ----------------

_DRIVER = """
import sys, runpy
from pathlib import Path
from asset_model import assets, one_off_kinds
if sys.argv[1]:
    assets.use_one_offs_root(Path(sys.argv[1]))
    one_off_kinds.register(one_off_kinds.Kind("audit", "audit", "audits", "Audit check"))
sys.argv = ["mothman", *sys.argv[2:]]
runpy.run_module("cli.app", run_name="__main__")
"""


def _mothman(*args, root: Path | None, asset: str | None = None):
    env = {k: v for k, v in os.environ.items() if k != assets.ASSET_ENV}
    if asset is not None:
        env[assets.ASSET_ENV] = asset
    return subprocess.run([sys.executable, "-c", _DRIVER, str(root or ""), *args], cwd=ROOT,
                          env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          timeout=300)


def _said(result) -> str:
    return re.sub(r"[│╭╮╰╯─\s]+", " ", result.stdout + result.stderr)


@pytest.fixture
def two_audits(one_offs):
    one_offs.add("cohort-a")
    one_offs.add("cohort-b")
    return one_offs.root


SENTENCE = "For one of 2 audits, use mothman one-off."


class TestTheOneOffSentence:
    """REQ-PIPE-363 criteria 4, 5, 6 and 11."""

    def test_help_ends_its_collections_line_with_it(self, two_audits):
        said = _said(_mothman("--help", root=two_audits))
        assert f"Set MOTHMAN_ASSET to one of: daily, quarterly. {SENTENCE}" in said

    def test_help_leaves_it_out_where_there_are_none(self, one_offs):
        said = _said(_mothman("--help", root=one_offs.root))
        assert "Set MOTHMAN_ASSET to one of: daily, quarterly." in said
        assert "use mothman one-off" not in said

    def test_an_unplaceable_command_says_it(self, two_audits):
        """Criterion 4."""
        result = _mothman("cp", "qa", root=two_audits)
        said = _said(result)
        assert result.returncode != 0
        assert f"Set it to one of: daily, quarterly. {SENTENCE} There is deliberately no default" \
            in said, said

    def test_an_asset_reading_command_says_it(self, two_audits):
        """Criterion 6."""
        result = _mothman("collections", root=two_audits)
        said = _said(result)
        assert result.returncode != 0 and SENTENCE in said, said

    def test_mistyped_with_none_leaves_it_out(self, one_offs):
        said = _said(_mothman("collections", root=one_offs.root, asset="dialy"))
        assert "'dialy', which names no asset folder" in said
        assert "use mothman one-off" not in said


class TestMothmanAssetNamingAOneOff:
    """REQ-PIPE-363 criterion 12 and REQ-PIPE-446 criterion 9: refused in the
    words Keith approved, and the one-off is not selected."""

    WORDS = ("MOTHMAN_ASSET is 'cohort-a', which is an audit, not an asset. A one-off is "
             "chosen by --id, with MOTHMAN_ASSET unset: mothman one-off <step> --id "
             "cohort-a. To run this command for an asset instead, set it to one of: daily, "
             "quarterly.")

    def test_an_asset_reading_command(self, two_audits):
        result = _mothman("collections", root=two_audits, asset="cohort-a")
        assert result.returncode != 0
        assert self.WORDS in _said(result), _said(result)

    def test_an_unplaceable_command(self, two_audits):
        result = _mothman("cp", "qa", root=two_audits, asset="cohort-a")
        assert self.WORDS in _said(result), _said(result)

    def test_in_process_it_selects_nothing(self, two_audits, monkeypatch):
        monkeypatch.setenv(assets.ASSET_ENV, "cohort-a")
        with pytest.raises(assets.OneOffRefused):
            assets.selected()
        with pytest.raises(assets.OneOffRefused):
            assets.select("cohort-a")


class TestTheOneOffGroup:
    """REQ-PIPE-363 criteria 5, 6 and 11; REQ-PIPE-446 criterion 8."""

    def test_it_runs_with_mothman_asset_unset(self, two_audits):
        result = _mothman("one-off", "list", root=two_audits)
        assert result.returncode == 0, _said(result)
        assert re.search(r"cohort-a\s+audit\s+A test project", result.stdout), result.stdout

    @pytest.mark.parametrize("stated", ["daily", "cohort-a"])
    def test_it_is_refused_with_mothman_asset_set(self, two_audits, stated):
        result = _mothman("one-off", "list", root=two_audits, asset=stated)
        assert result.returncode != 0
        assert f"MOTHMAN_ASSET is '{stated}'" in _said(result) and "unset" in _said(result)

    def test_the_bare_tui_needs_a_terminal(self, two_audits):
        result = _mothman("one-off", root=two_audits)
        assert result.returncode != 0 and "Traceback" not in _said(result)
        assert "mothman one-off list" in _said(result)

    def test_no_collection_group_is_built_for_a_one_off(self, two_audits):
        """Criterion 8: groups come from MOTHMAN_ASSET's asset alone, and a one-off
        is never named by it - so `--help` with one-offs present lists none."""
        out = _mothman("--help", root=two_audits).stdout
        assert not re.search(r"^\W*(bdm|cp|ed|lp)\s", out, re.M), out


pytestmark = pytest.mark.asset("daily")
