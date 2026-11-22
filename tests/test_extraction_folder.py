"""Opening an extraction generates one-offs/extraction/<id>/ from its recipe
alone (REQ-PIPE-440).

ALWAYS INTO A ONE-OFFS ROOT POINTED ELSEWHERE: no test generates into the
repository's own one-offs/, and none commits a real one-offs/extraction/<id>/
folder (Keith 2026-11-22). The package is tests/extraction_support.py's.
Driven through `mothman one-off open` (in-process, through Click's runner, with
the resolver pointed at the test's root) and then read back by the real
readers - the hierarchy, the calendar loader, the folders gate - with the
generated one-off selected by --id, as every later step selects it.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

import extraction_support as ex
from asset_model import assets

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def root(tmp_path, monkeypatch):
    one_offs = tmp_path / "one-offs"
    one_offs.mkdir()
    before = assets.use_one_offs_root(one_offs)
    monkeypatch.delenv(assets.ASSET_ENV, raising=False)
    yield one_offs
    assets.deselect_one_off()
    assets.restore(before)


def _said(result) -> str:
    import re

    return re.sub(r"[│╭╮╰╯─\s]+", " ", result.output)


def _open(package, *, ok=True):
    from cli.one_off import one_off_group

    result = CliRunner().invoke(one_off_group, ["open", "--kind", "extraction", str(package)])
    if ok:
        assert result.exit_code == 0, result.output
    return result


@pytest.fixture
def opened(root, tmp_path):
    _open(ex.package(tmp_path / "pkg"))
    return root / "extraction" / "cohort-2026-a"


class TestGeneratedFromTheRecipeAlone:
    """Criteria 1 to 4 and 10."""

    def test_the_folder_and_only_the_generated_files(self, opened):
        names = sorted(p.relative_to(opened).as_posix() for p in opened.rglob("*") if p.is_file())
        assert names == [
            "calendar.yaml", "data-asset.yaml",
            "dbt/dbt_project.yml",
            "dbt/models/cohort-study/sources.yml",
            "dbt/models/cohort-study/stg_cohort_people.sql",
            "dbt/models/cohort-study/stg_cohort_visits.sql",
            "dbt/packages.yml", "generated.sha256.json",
            "health-agency/cohort-study-contract.yaml", "presentation.yaml"]

    def test_nothing_of_the_template_and_no_adapter_or_synthetic_folder(self, opened):
        for absent in ("people.yaml", "synthetic", "collections"):
            assert not (opened / absent).exists(), absent

    def test_its_data_asset_yaml(self, opened):
        doc = yaml.safe_load((opened / "data-asset.yaml").read_text())
        assert doc["data_asset_id"] == "cohort-2026-a" and doc["project"] == "The 2026 cohort study"
        assert doc["recipe"]["format_version"] == 1 and len(doc["recipe"]["digest"]) == 64
        assert doc["recipe"]["filter"] == ex.RECIPE["filter"]
        (agency,) = doc["hierarchy"]["agencies"]
        (coll,) = agency["collections"]
        assert (agency["id"], coll["id"]) == ("health-agency", "cohort-study")
        people = coll["datasets"][0]
        assert people["arrival_pattern"] == r"people\.csv"
        assert people["columns"][0] == {"name": "person_id", "type": "string",
                                        "primary_identifier": True}
        assert people["cohort"] == [{"column": "first_seen", "lower": "2020-01-01",
                                     "upper": "2024-12-31"}]
        assert people["expected_rows"] == 3 and "expected_rows" not in coll["datasets"][1]

    def test_a_minimal_calendar(self, opened):
        assert yaml.safe_load((opened / "calendar.yaml").read_text()) == {
            "calendars": [], "datasets": [
                {"id": "cohort-people", "no_calendar": "never"},
                {"id": "cohort-visits", "no_calendar": "never", "derived": True}]}

    def test_the_dbt_project_reaches_dbt_shared_and_the_local_dbt_utils(self, opened):
        project = yaml.safe_load((opened / "dbt" / "dbt_project.yml").read_text())
        shared = (opened / "dbt" / project["macro-paths"][0]).resolve()
        assert shared == (ROOT / "dbt_shared" / "macros").resolve()
        packages = yaml.safe_load((opened / "dbt" / "packages.yml").read_text())
        assert packages == {"packages": [{"local": "{{ env_var('MOTHMAN_ONE_OFF_DBT_UTILS') }}"}]}

    def test_four_levels_up_in_the_repository_layout(self, tmp_path, monkeypatch):
        """Criterion 4's depth, from one-offs/extraction/<id>/dbt/ in the real
        layout - computed, never written to the repository."""
        from asset_model.kinds import extraction_folder as ef
        from asset_model.kinds import extraction_recipe as er

        pkg = er.read(str(ex.package(tmp_path / "pkg")))
        files = ef._dbt(pkg.recipe, ROOT / "one-offs" / "extraction" / "cohort-2026-a")
        project = yaml.safe_load(files["dbt/dbt_project.yml"])
        assert project["macro-paths"] == ["../../../../dbt_shared/macros"]

    def test_the_readers_read_it_as_a_one_off(self, opened):
        from asset_model import hierarchy, schedule
        from qa_tools.common import sample_data, validate_folders

        assets.select_one_off("cohort-2026-a")
        assert [d.dataset_id for d in hierarchy.all_datasets()] == ["cohort-people",
                                                                    "cohort-visits"]
        assert schedule.no_calendar("cohort-people") == schedule.NEVER
        assert schedule.is_derived("cohort-visits") and not schedule.is_derived("cohort-people")
        assert sample_data.supply_state("cohort-people") == "agreed"
        assert sample_data.supply_state("cohort-visits") == "in-development"
        assert validate_folders.problems() == []

    def test_the_schedule_gate_accepts_never_and_derived_in_a_one_off(self, opened):
        from qa_tools.common import validate_schedule

        assets.select_one_off("cohort-2026-a")
        found = validate_schedule.validate()
        assert [e for e in found if "never" in e.problem or "derived" in e.problem] == []

    def test_no_level_above_agency(self, opened):
        doc = yaml.safe_load((opened / "data-asset.yaml").read_text())
        assert set(doc["hierarchy"]) == {"agencies"}


class TestTheDigest:
    """Criterion 5."""

    def test_every_generated_file_is_recorded(self, opened):
        record = json.loads((opened / "generated.sha256.json").read_text())
        on_disk = {p.relative_to(opened).as_posix() for p in opened.rglob("*")
                   if p.is_file() and p.name != "generated.sha256.json"}
        assert set(record["files"]) == on_disk
        assert record["recipe_digest"] == yaml.safe_load(
            (opened / "data-asset.yaml").read_text())["recipe"]["digest"]


class TestRefused:
    """Criteria 6 and 7, before anything is generated."""

    def test_an_existing_folder_is_a_new_extraction(self, opened, tmp_path):
        result = _open(ex.package(tmp_path / "pkg2"), ok=False)
        assert result.exit_code != 0
        assert "already a folder" in _said(result) and "new extraction" in _said(result)

    def test_two_tables_claiming_one_placement(self, root, tmp_path):
        doc = ex.recipe()
        doc["tables"][1]["dataset"]["id"] = "cohort-people"
        result = _open(ex.package(tmp_path / "pkg", doc), ok=False)
        assert "both claim the dataset placement" in _said(result)
        assert not (root / "extraction").exists(), "nothing generated"

    def test_an_id_breaking_the_naming_rule(self, root, tmp_path):
        doc = ex.recipe()
        doc["tables"][0]["collection"]["id"] = "Cohort_Study"
        result = _open(ex.package(tmp_path / "pkg", doc), ok=False)
        assert "'Cohort_Study'" in _said(result)

    def test_an_id_already_an_asset(self, root, tmp_path):
        result = _open(ex.package(tmp_path / "pkg", ex.recipe(extraction_id="daily")), ok=False)
        assert "assets/daily" in _said(result)


class TestTheLoadRefuses:
    """Criteria 8, 9 and 12, through one_off_load.refusals - what the load
    (REQ-PIPE-442) asks first. git runs in a temporary repository with a
    temporary bare remote; nothing reaches GitHub."""

    def _git(self, *args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"})

    @pytest.fixture
    def repo(self, tmp_path, monkeypatch):
        """A repository holding one-offs/, with a bare remote it tracks."""
        repo, remote = tmp_path / "repo", tmp_path / "remote.git"
        self._git("init", "-q", "--bare", str(remote), cwd=tmp_path)
        repo.mkdir()
        self._git("init", "-q", "-b", "work", cwd=repo)
        self._git("remote", "add", "origin", str(remote), cwd=repo)
        (repo / "README").write_text("x")
        self._git("add", "README", cwd=repo)
        self._git("commit", "-q", "-m", "start", cwd=repo)
        self._git("push", "-q", "-u", "origin", "work", cwd=repo)
        one_offs = repo / "one-offs"
        one_offs.mkdir()
        (one_offs / "extraction" / "_template").mkdir(parents=True)
        (one_offs / "extraction" / "_template" / "people.yaml").write_text("people: {}\n")
        before = assets.use_one_offs_root(one_offs)
        monkeypatch.delenv(assets.ASSET_ENV, raising=False)
        yield repo
        assets.restore(before)

    @pytest.fixture
    def dbt_utils_ready(self, monkeypatch):
        from qa_tools.common import one_off_load

        monkeypatch.setattr(one_off_load, "dbt_utils_refusal", lambda: None)

    def _opened(self, repo, tmp_path):
        pkg = ex.package(tmp_path / "pkg")
        _open(pkg)
        return repo / "one-offs" / "extraction" / "cohort-2026-a", pkg

    def _refusals(self, repo, folder, pkg):
        from qa_tools.common import one_off_load

        return one_off_load.refusals(folder, str(pkg), repo / "one-offs" / "extraction" /
                                     "_template")

    def test_uncommitted_is_refused_with_the_commands(self, repo, tmp_path, dbt_utils_ready):
        folder, pkg = self._opened(repo, tmp_path)
        (found, *_rest) = self._refusals(repo, folder, pkg)
        assert "uncommitted changes or untracked files" in found
        assert "git add one-offs/extraction/cohort-2026-a" in found
        assert "git push origin work" in found and "only a pushed commit" in found

    def test_committed_but_unpushed_is_refused(self, repo, tmp_path, dbt_utils_ready):
        folder, pkg = self._opened(repo, tmp_path)
        self._git("add", "-A", cwd=repo)
        self._git("commit", "-q", "-m", "open", cwd=repo)
        found = self._refusals(repo, folder, pkg)
        assert found and "not on origin/work" in found[0] and "git push origin work" in found[0]

    def test_committed_and_pushed_loads(self, repo, tmp_path, dbt_utils_ready):
        folder, pkg = self._opened(repo, tmp_path)
        self._git("add", "-A", cwd=repo)
        self._git("commit", "-q", "-m", "open", cwd=repo)
        self._git("push", "-q", cwd=repo)
        assert self._refusals(repo, folder, pkg) == []

    def test_dbt_artefacts_are_not_uncommitted_changes(self, repo, tmp_path, dbt_utils_ready):
        """Criterion 11: the repository's own .gitignore keeps them out."""
        import shutil

        shutil.copy(ROOT / ".gitignore", repo / ".gitignore")
        folder, pkg = self._opened(repo, tmp_path)
        self._git("add", "-A", cwd=repo)
        self._git("commit", "-q", "-m", "open", cwd=repo)
        self._git("push", "-q", cwd=repo)
        for name in ("target", "logs", "dbt_packages"):
            (folder / "dbt" / name).mkdir()
            (folder / "dbt" / name / "x").write_text("dbt wrote this")
        (folder / "dbt" / "package-lock.yml").write_text("packages: []\n")
        assert self._refusals(repo, folder, pkg) == []

    def test_an_uncommitted_template_is_refused(self, repo, tmp_path, dbt_utils_ready):
        folder, pkg = self._opened(repo, tmp_path)
        self._git("add", "-A", cwd=repo)
        self._git("commit", "-q", "-m", "open", cwd=repo)
        self._git("push", "-q", cwd=repo)
        (repo / "one-offs" / "extraction" / "_template" / "people.yaml").write_text("edited\n")
        found = self._refusals(repo, folder, pkg)
        assert found and "the kind's template" in found[0]

    def test_a_changed_recipe_is_refused_naming_both_digests(self, repo, tmp_path,
                                                            dbt_utils_ready):
        folder, pkg = self._opened(repo, tmp_path)
        before = json.loads((folder / "generated.sha256.json").read_text())["recipe_digest"]
        (pkg / "recipe.json").write_text(json.dumps(ex.recipe(project="Another")))
        found = self._refusals(repo, folder, pkg)
        assert before in found[0] and "no longer matches" in found[0]


class TestTheLocalDbtUtils:
    """Criterion 12."""

    def test_no_copy_names_the_setup_command(self, tmp_path, monkeypatch):
        from qa_tools.common import one_off_load

        monkeypatch.setattr(one_off_load, "dbt_utils_path", lambda: tmp_path / "dbt_utils")
        assert "mothman one-off setup-dbt-utils" in one_off_load.dbt_utils_refusal()

    def test_setup_copies_the_locked_revision_without_a_fetch(self, tmp_path, monkeypatch):
        from qa_tools.common import one_off_load

        source = tmp_path / "asset_dbt_utils"
        source.mkdir()
        (source / "dbt_project.yml").write_text("name: dbt_utils\n")
        monkeypatch.setattr(one_off_load, "dbt_utils_path", lambda: tmp_path / "copy")
        monkeypatch.setattr(one_off_load, "_installed_from_an_asset", lambda: source)
        monkeypatch.setattr(one_off_load, "_fetch_locked",
                            lambda into: pytest.fail("a network fetch"))
        path = one_off_load.setup_dbt_utils()
        assert (path / "dbt_project.yml").is_file()
        assert one_off_load.dbt_utils_refusal() is None

    def test_another_revision_is_refused(self, tmp_path, monkeypatch):
        from qa_tools.common import one_off_load

        copy = tmp_path / "copy"
        copy.mkdir()
        (copy / one_off_load.MARKER).write_text(json.dumps({"revision": "0" * 40}))
        monkeypatch.setattr(one_off_load, "dbt_utils_path", lambda: copy)
        said = one_off_load.dbt_utils_refusal()
        assert "0" * 40 in said and one_off_load.locked_revision() in said

    def test_the_environment_names_the_path(self):
        from qa_tools.common import environments

        assert environments.get("sandbox").one_off_dbt_utils == "data/one-off-packages/dbt_utils"
        assert environments.get("ci").one_off_dbt_utils is None


pytestmark = pytest.mark.asset("daily")
