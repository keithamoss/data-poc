"""An extraction's two check layers, evaluated by all four real tools through
`mothman one-off load` (REQ-QAC-441), and the load itself (REQ-PIPE-442
criteria 3 to 5).

ONE REAL LOAD PER MODULE, read by every test: a small synthetic package in a
temporary git repository with a temporary bare remote (nothing reaches
GitHub), its one-offs root pointed there, its state under the test's own
temporary folder, and its database a throwaway supply_<id> on the test
server, named for this session's MOTHMAN_TEST_DB_TAG and dropped at the end.
Never supply_quarterly or supply_daily.

THE PACKAGE: two collections. `cohort-study` declares people.csv (three rows:
one empty identifier, one date outside the cohort, one value that is no
date) and visits.csv, which NEVER ARRIVES; `lab-study`
declares labs.csv, expecting ten rows and holding eight, seven of them with
a value that is no number. extra.csv is declared by nobody.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
import yaml
from click.testing import CliRunner

from asset_model import assets

pytestmark = pytest.mark.asset("daily")

ROOT = Path(__file__).resolve().parent.parent
TAG = "".join(c for c in os.environ.get("MOTHMAN_TEST_DB_TAG", "") if c.isalnum())[:8] or "t"

AGENCY = {"id": "health-agency", "name": "Health Agency"}


def _recipe(one_off_id: str, *, labs_expected: int = 10) -> dict:
    cohort = {"id": "cohort-study", "name": "Cohort Study"}
    labs = {"id": "lab-study", "name": "Lab Study"}
    return {
        "recipe_format_version": 1, "extraction_id": one_off_id,
        "project": "A test project", "filter": "Everyone first seen 2020 to 2024.",
        "tables": [
            {"file": "people.csv", "format": "csv", "agency": AGENCY, "collection": cohort,
             "dataset": {"id": "cohort-people", "name": "People", "table": "cohort_people"},
             "derived": False,
             "columns": [{"name": "person_id", "type": "string", "primary_identifier": True},
                         {"name": "first_seen", "type": "date", "primary_identifier": False}],
             "cohort": [{"column": "first_seen", "lower": "2020-01-01",
                         "upper": "2024-12-31"}],
             "expected_rows": 3},
            {"file": "visits.csv", "format": "csv", "agency": AGENCY, "collection": cohort,
             "dataset": {"id": "cohort-visits", "name": "Visits", "table": "cohort_visits"},
             "derived": False,
             "columns": [{"name": "visit_id", "type": "string", "primary_identifier": True}],
             "cohort": []},
            {"file": "labs.csv", "format": "csv", "agency": AGENCY, "collection": labs,
             "dataset": {"id": "lab-results", "name": "Lab results", "table": "lab_results"},
             "derived": False,
             "columns": [{"name": "lab_id", "type": "string", "primary_identifier": True},
                         {"name": "reading", "type": "number", "primary_identifier": False}],
             "cohort": [], "expected_rows": labs_expected},
        ]}


def _package(where: Path, one_off_id: str, **kw) -> Path:
    """The module docstring's package."""
    where.mkdir(parents=True)
    (where / "recipe.json").write_text(json.dumps(_recipe(one_off_id, **kw)))
    (where / "people.csv").write_text(
        "person_id,first_seen\np1,2021-01-01\np2,2030-06-01\n,2022-02-02\n")
    (where / "labs.csv").write_text(
        "lab_id,reading\n" + "".join(f"l{i},high\n" for i in range(1, 8)) + "l8,1.5\n")
    (where / "extra.csv").write_text("anything\n1\n")
    return where


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class World:
    """The temporary repository, one-offs root, state and server."""

    def __init__(self, base: Path):
        self.base = base
        self.id = f"x-{TAG.lower()}-{uuid.uuid4().hex[:6]}"
        self.repo, self.remote = base / "repo", base / "remote.git"
        self.root = self.repo / "one-offs"
        self.state = base / "state"
        self.package = _package(base / "pkg", self.id)
        _git("init", "-q", "--bare", str(self.remote), cwd=base)
        self.repo.mkdir()
        _git("init", "-q", "-b", "work", cwd=self.repo)
        _git("remote", "add", "origin", str(self.remote), cwd=self.repo)
        _git("config", "user.email", "tester@example.org", cwd=self.repo)
        _git("config", "user.name", "Tester", cwd=self.repo)
        (self.root / "extraction").mkdir(parents=True)
        # THE KIND'S REAL TEMPLATE, as committed - copied into the test's
        # repository because the load reads it from the one-offs root.
        shutil.copytree(ROOT / "one-offs" / "extraction" / "_template",
                        self.root / "extraction" / "_template")
        self.commit("start", push="-u")
        admin = os.environ["MOTHMAN_TEST_DSN"]
        info = psycopg.conninfo.conninfo_to_dict(admin)
        info.pop("dbname", None)
        self.server = "postgresql://{user}:{password}@{host}:{port}".format(**info)
        self.admin = admin

    def commit(self, message: str, push: str | None = None) -> None:
        _git("add", "-A", cwd=self.repo)
        _git("commit", "-q", "--allow-empty", "-m", message, cwd=self.repo)
        _git("push", "-q", *([push, "origin", "work"] if push else []), cwd=self.repo)

    @property
    def database(self) -> str:
        return f"supply_{self.id}"

    def dsn(self) -> str:
        info = psycopg.conninfo.conninfo_to_dict(self.admin)
        info["dbname"] = self.database
        return psycopg.conninfo.make_conninfo(**info)

    def query(self, sql: str, params=()) -> list:
        with psycopg.connect(self.dsn()) as conn:
            return conn.execute(sql, params).fetchall()

    def drop(self) -> None:
        with psycopg.connect(self.admin, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{self.database}" WITH (FORCE)')


def _point(world: World, mp) -> None:
    """The resolver at the world: its one-offs root, a one-off's state under
    the test's folder, no asset, the configured server and no DSN."""
    from qa_tools.common import supply_db

    assets.use_one_offs_root(world.root)
    real = assets._OneOffs.asset

    def asset(self, kind, name):
        found = real(self, kind, name)
        return replace(found, data=world.state / "data" / name,
                       reports=world.state / "reports" / name)

    mp.setattr(assets._OneOffs, "asset", asset)
    mp.delenv(assets.ASSET_ENV, raising=False)
    mp.delenv(supply_db.SUPPLY_DSN_ENV, raising=False)
    mp.setenv(supply_db.SERVER_ENV, world.server)
    mp.setenv("GIT_AUTHOR_EMAIL", "tester@example.org")


def _said(result) -> str:
    import re

    return re.sub(r"[│╭╮╰╯─\s]+", " ", result.output)


def _invoke(args):
    from cli.one_off import one_off_group

    result = CliRunner().invoke(one_off_group, args)
    return result


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    """One opened, committed, pushed and loaded extraction."""
    world = World(tmp_path_factory.mktemp("one-off-load"))
    with pytest.MonkeyPatch.context() as mp:
        _point(world, mp)
        try:
            opened = _invoke(["open", "--kind", "extraction", str(world.package)])
            assert opened.exit_code == 0, opened.output
            world.commit("open")
            world.loaded = _invoke(["load", "--id", world.id, str(world.package)])
            assert world.loaded.exit_code == 0, (world.loaded.output,
                                                 world.loaded.exception)
            world.runs_after_first = world.query("SELECT count(*) FROM qa.run")[0][0]
            world.resumed = _invoke(["load", "--id", world.id, str(world.package)])
            assets.release_claim()
            assets.deselect_one_off()
            # THE SAME RECIPE, OTHER DATA: a re-send the recipe digest cannot tell
            # from the first, which only the package's own digest refuses.
            world.resend = _package(world.base / "pkg2", world.id)
            (world.resend / "labs.csv").write_text("lab_id,reading\nl1,1.0\n")
            world.refused = _invoke(["load", "--id", world.id, str(world.resend)])
            yield world
        finally:
            assets.deselect_one_off()
            assets.use_one_offs_root(None)
            world.drop()


@pytest.fixture
def world(loaded, monkeypatch):
    _point(loaded, monkeypatch)
    yield loaded
    assets.deselect_one_off()
    assets.use_one_offs_root(None)


def _results(world, like: str) -> dict:
    """{(tool, check_id tail): (status, extra)} for the checks matching."""
    rows = world.query(
        "SELECT tool, check_id, status, extra FROM qa.check_result c JOIN qa.run r "
        "USING (run_key) WHERE r.completed_at IS NOT NULL AND check_id LIKE %s", [like])
    return {(t, ".".join(cid.split(".")[3:])): (s, e) for t, cid, s, e in rows}


def _folder(world) -> Path:
    return world.root / "extraction" / world.id


def _check_ids_in(folder: Path, one_off_id: str) -> set[str]:
    """Every check id written in a folder's YAML files."""
    import re

    pattern = re.compile(re.escape(one_off_id) + r"\.[A-Za-z0-9_.-]+_(?:dbt|soda|datacontract|evidently|file)\b")
    found = set()
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix in (".yml", ".yaml"):
            found |= set(pattern.findall(path.read_text()))
    return found


# ---- REQ-QAC-441 -------------------------------------------------------------

class TestTheDefaultLayerIsReadLive:
    """Criterion 1: defined once in the kind's template, read at each load,
    never copied into the folder."""

    def test_the_folder_holds_no_default_layer_check(self, world):
        folder = _folder(world)
        ids = _check_ids_in(folder, world.id)
        assert ids, "the folder must hold its recipe layer's checks"
        assert not [i for i in ids if "identifier_not_null" in i or "columns_arrived" in i]
        assert not (folder / "default-checks.yaml").exists()
        assert not (folder / "file-checks.yaml").exists()

    def test_the_load_materialised_it_into_scratch(self, world):
        workspace = world.state / "data" / world.id / "qa" / "config"
        ids = _check_ids_in(workspace, world.id)
        assert any(i.endswith("person_id.identifier_not_null_dbt") for i in ids)
        assert (workspace / "file-checks.yaml").is_file()

    def test_a_change_to_the_template_reaches_the_next_load(self, world, tmp_path):
        from qa_tools.common import one_off_checks

        template = world.root / "extraction" / "_template" / "default-checks.yaml"
        before = template.read_text()
        assets.select_one_off(world.id)
        try:
            template.write_text(before.replace("This value must never be empty.",
                                               "An identifier must never be empty."))
            workspace = one_off_checks.materialise()
            soda = (workspace / "health-agency" / "cohort-study-soda-checks.yml").read_text()
            assert "An identifier must never be empty." in soda
        finally:
            template.write_text(before)

    def test_a_template_without_its_default_layer_is_refused(self, world, tmp_path):
        from asset_model.kinds import extraction_checks

        with pytest.raises(extraction_checks.TemplateRefused, match="default-checks.yaml"):
            extraction_checks.read_template(tmp_path)


class TestTheDefaultLayerAsserts:
    """Criterion 2: every declared table arrived, every declared column, and no
    declared primary identifier null - evaluated by the tools that fit."""

    def test_an_empty_identifier_fails_in_all_four_tools(self, world):
        got = _results(world, "%cohort-people.person_id.identifier_not_null_%")
        assert {t for (t, _), (s, _e) in got.items() if s == "fail"} == \
            {"dbt", "soda", "datacontract", "evidently"}

    def test_a_present_identifier_passes(self, world):
        got = _results(world, "%lab-results.lab_id.identifier_not_null_%")
        assert {s for s, _e in got.values()} == {"pass"} and len(got) == 4

    def test_every_declared_column_arrived(self, world):
        got = _results(world, "%.columns_arrived_soda")
        assert {k[1].split(".")[0] for k in got} == {"cohort-people", "lab-results"}
        assert {s for s, _e in got.values()} == {"pass"}

    def test_an_arrived_table_passes_table_arrived(self, world):
        got = _results(world, "%.table_arrived_file")
        assert got[("file", "cohort-people.table_arrived_file")][0] == "pass"
        assert got[("file", "lab-results.table_arrived_file")][0] == "pass"


class TestWhatThePackageLacksOrAdds:
    """Criterion 3 (and REQ-PIPE-442 criterion 4): a declared table that did
    not arrive and an undeclared file are failing default-layer results, QA
    goes on, and the undeclared file is not filed."""

    def test_a_declared_table_that_never_arrived_fails(self, world):
        ((status, extra),) = _results(world, "%cohort-visits.table_arrived_file").values()
        assert status == "fail" and "visits.csv" in extra["finding"]

    def test_its_dataset_has_a_completed_run(self, world):
        rows = world.query("SELECT completed_at IS NOT NULL FROM qa.run WHERE run_key "
                           "LIKE 'cohort_visits__%%'")
        assert rows == [(True,)]

    def test_an_undeclared_file_fails_naming_it(self, world):
        got = _results(world, "%.undeclared_file")
        ((status, extra),) = got.values()
        assert status == "fail" and "extra.csv" in extra["finding"]
        # Against the first counted dataset (PROVISIONAL, one_off_package).
        assert list(got)[0][1].startswith("cohort-people.")

    def test_it_was_not_filed(self, world):
        deliveries = world.state / "data" / world.id / "deliveries"
        filed = {p.name for p in deliveries.rglob("*") if p.is_file()}
        assert filed == {"people.csv", "labs.csv"}

    def test_qa_carried_on_past_both(self, world):
        assert _results(world, "%lab-results.reading.declared_type_%")


class TestTheRecipeLayer:
    """Criteria 4 and 5: each declared type, each cohort bound and an expected
    row count, generated into the folder and evaluated."""

    def test_a_value_that_is_not_its_declared_type_fails(self, world):
        got = _results(world, "%lab-results.reading.declared_type_%")
        assert {t: s for (t, _), (s, _e) in got.items()} == \
            {"dbt": "fail", "soda": "fail", "datacontract": "fail"}

    def test_a_value_of_its_type_passes(self, world):
        got = _results(world, "%cohort-people.first_seen.declared_type_%")
        assert {s for s, _e in got.values()} == {"pass"} and len(got) == 3

    def test_a_value_outside_the_cohort_fails(self, world):
        got = _results(world, "%cohort-people.first_seen.cohort_bounds_%")
        assert {t: s for (t, _), (s, _e) in got.items()} == \
            {"dbt": "fail", "soda": "fail", "datacontract": "fail"}

    def test_an_exact_row_count_passes_and_fails(self, world):
        people = _results(world, "%cohort-people.expected_rows_%")
        labs = _results(world, "%lab-results.expected_rows_%")
        assert {t: s for (t, _), (s, _e) in people.items()} == \
            {"soda": "pass", "datacontract": "pass", "evidently": "pass"}
        assert {t: s for (t, _), (s, _e) in labs.items()} == \
            {"soda": "fail", "datacontract": "fail", "evidently": "fail"}

    def test_the_recipe_layer_is_in_the_folder(self, world):
        ids = _check_ids_in(_folder(world), world.id)
        for tail in ("lab-results.reading.declared_type_dbt",
                     "lab-results.reading.declared_type_soda",
                     "lab-results.reading.declared_type_datacontract",
                     "cohort-people.first_seen.cohort_bounds_dbt",
                     "lab-results.expected_rows_evidently"):
            assert f"{world.id}.health-agency.lab-study.{tail}" in ids or \
                f"{world.id}.health-agency.cohort-study.{tail}" in ids, tail


class TestSeparateFromTheRecurringDatasets:
    """Criterion 7: neither layer imports or shares an enduring asset's check."""

    def test_every_check_is_the_one_offs_own(self, world):
        workspace = world.state / "data" / world.id / "qa" / "config"
        ids = _check_ids_in(_folder(world), world.id) | _check_ids_in(workspace, world.id)
        assert ids and all(i.startswith(world.id + ".") for i in ids)
        rows = world.query("SELECT DISTINCT split_part(check_id, '.', 1) FROM qa.check_result")
        assert rows == [(world.id,)]


class TestTheSharedFileChecks:
    """Criterion 8: the root file-checks.yaml over every extraction file."""

    def test_each_arrived_file_was_screened_by_every_shared_check(self, world):
        from asset_model import config_yaml

        shared = [c["check"] for c in config_yaml.load(ROOT / "file-checks.yaml")["checks"]]
        for dataset in ("cohort-people", "lab-results"):
            got = _results(world, f"%.{dataset}.%_file")
            assert {k[1].split(".")[1].removesuffix("_file") for k in got} >= set(shared)


class TestFailingRowKeysOnly:
    """Criterion 9: up to FAILING_SAMPLE_LIMIT failing-row identifier keys per
    check, never row content."""

    def test_keys_are_identifiers_and_capped(self, world):
        from qa_tools.common.sample_keys import FAILING_SAMPLE_LIMIT

        got = _results(world, "%lab-results.reading.declared_type_%")
        for (tool, _), (_s, extra) in got.items():
            keys = extra.get("failing_sample_keys") or []
            assert len(keys) <= FAILING_SAMPLE_LIMIT, tool
            assert set(keys) <= {f"l{i}" for i in range(1, 8)}, (tool, keys)
            assert "high" not in json.dumps(extra), tool
        assert len(got[("dbt", "lab-results.reading.declared_type_dbt")][1]
                   ["failing_sample_keys"]) == FAILING_SAMPLE_LIMIT


# ---- REQ-PIPE-442 ------------------------------------------------------------

class TestTheLoad:
    """Criterion 3: its own database, marked as the one-off's, recording the
    package's digest and the commit, one delivery per collection."""

    def test_its_database_is_marked_as_the_one_offs(self, world):
        ((asset, env),) = world.query("SELECT data_asset_id, environment FROM "
                                      "qa.identity")
        assert asset == world.id and env == os.environ["MOTHMAN_ENVIRONMENT"]

    def test_it_records_the_package_digest_and_the_commit(self, world):
        from qa_tools.common import one_off_load

        ((digest, commit, deliveries),) = world.query(
            "SELECT package_digest, loaded_commit, deliveries FROM qa.one_off_load")
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=world.repo, text=True,
                              capture_output=True).stdout.strip()
        files = [p.name for p in world.package.iterdir()]
        assert digest == one_off_load.package_digest(str(world.package), files)
        assert commit == head
        assert sorted(deliveries) == ["cohort-study", "lab-study"]

    def test_one_delivery_per_collection(self, world):
        deliveries = world.state / "data" / world.id / "deliveries"
        held = {d.name: sorted(p.name for p in d.iterdir()) for d in deliveries.iterdir()}
        assert sorted(held.values()) == [["labs.csv"], ["people.csv"]]

    def test_it_ends_with_the_next_step(self, world):
        assert world.loaded.output.rstrip().endswith(
            f"mothman one-off publish --id {world.id}")


class TestResumeOrRefuse:
    """Criterion 5."""

    def test_the_same_package_is_resumed_not_refused(self, world):
        assert world.resumed.exit_code == 0, world.resumed.output
        assert "Resuming the load" in world.resumed.output
        assert world.query("SELECT count(*) FROM qa.run")[0][0] == world.runs_after_first

    def test_another_package_is_refused_as_a_new_one_off(self, world):
        assert world.refused.exit_code != 0
        assert "A re-send is a new one-off" in _said(world.refused)
        assert "Nothing was loaded" in _said(world.refused)


class TestTheLoadGatesItsFolder:
    """Criterion 3's gate (and REQ-PIPE-438 criterion 9's load half): a folder
    failing a gate its kind declares is refused, naming the gate and the
    folder, before any database is made."""

    def test_a_schedule_the_one_off_may_not_have_is_refused(self, tmp_path, monkeypatch):
        world = World(tmp_path)
        _point(world, monkeypatch)
        try:
            assert _invoke(["open", "--kind", "extraction", str(world.package)]).exit_code == 0
            calendar = _folder(world) / "calendar.yaml"
            doc = yaml.safe_load(calendar.read_text())
            doc["datasets"][0]["no_calendar"] = "not-yet-agreed"
            calendar.write_text(yaml.safe_dump(doc))
            world.commit("a hand edit")
            got = _invoke(["load", "--id", world.id, str(world.package)])
            assert got.exit_code != 0
            said = _said(got)
            assert "schedule" in said and world.id in said and "nothing was loaded" in said
            with psycopg.connect(world.admin) as conn:
                assert conn.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                    [world.database]).fetchone() is None
        finally:
            assets.deselect_one_off()
            assets.use_one_offs_root(None)
            world.drop()


class TestEveryGeneratedCheckCarriesItsWords:
    """Every check of both layers carries description and failure_indicates
    (docs/check-authoring-rules.md), read back by the same parser the
    lifecycle gate and the dashboard build read every check with - and holds
    to the rules a machine can hold it to: no figure (rule 3), no tool or
    method (rule 10), not its own column (rule 12), `supply` never
    `extract` (rule 13)."""

    def test_both_layers(self, world):
        import re

        from qa_tools.common import one_off_checks, validate_check_lifecycle

        assets.select_one_off(world.id)
        assets.use_workspace(one_off_checks.workspace_of(assets.selected()))
        try:
            # The two layers' own, not the shared file checks every asset runs.
            from asset_model import file_check_definitions as defs

            shared = tuple(f".{n}_file" for n in defs.NAMES)
            checks = [c for c in validate_check_lifecycle.collect_checks(None)
                      if c.check_id.startswith(world.id + ".")
                      and not c.check_id.endswith(shared)]
        finally:
            assets.use_workspace(None)
        assert len(checks) > 30, len(checks)
        tools = re.compile(r"dbt|soda|datacontract|evidently|accepted_range|not_null|"
                           r"expression_is_true|pg_input_is_valid|psi", re.I)
        for c in checks:
            column = c.check_id.split(".")[4] if c.check_id.count(".") == 5 else None
            for field in ("description", "failure_indicates"):
                text = (getattr(c, field) or "").strip()
                assert text, (c.check_id, field)
                assert not re.search(r"\d", text), (c.check_id, field, text)
                assert not tools.search(text), (c.check_id, field, text)
                assert not re.search(r"\bextracts?\b", text, re.I), (c.check_id, field, text)
                if column:
                    assert column not in text, (c.check_id, field, text)
            assert c.category, c.check_id


class TestTheEnvironmentLineNamesTheOneOff:
    """Criterion 13: 'One-off: <id> (extraction)', the kind in its display word,
    wherever the asset is named - the TUI's toolbar reads the same line."""

    def test_the_line(self, world):
        from cli import common

        assets.select_one_off(world.id)
        line = common.environment_statement()
        assert line.endswith(f" · One-off: {world.id} (extraction)"), line
        assert "Asset:" not in line


class TestTheToolsPanel:
    """Criterion 14: `mothman one-off` is listed in --help's Tools panel."""

    def test_it_is_listed(self, monkeypatch):
        import subprocess as sp
        import sys

        env = {k: v for k, v in os.environ.items() if k != assets.ASSET_ENV}
        env["COLUMNS"] = "200"
        out = sp.run([sys.executable, "-m", "cli.app", "--help"], cwd=ROOT, env=env,
                     capture_output=True, text=True).stdout
        tools = out[out.index("Tools"):]
        assert "one-off" in tools, out


class TestTheList:
    """Criteria 1 and 10: every one-off with its stage, its database's age and
    its next step, and every one-off database on the server - read from the
    folder, git and the server's list of databases, claiming no asset."""

    def test_a_loaded_one_off(self, world):
        got = _invoke(["list"])
        assert got.exit_code == 0, got.output
        line = next(ln for ln in got.output.splitlines() if ln.startswith(world.id))
        assert "extraction" in line and "loaded" in line and "A test project" in line
        assert f"mothman one-off publish --id {world.id}" in got.output
        assert f"  {world.database}  " in got.output
        assert assets.claimed() is None

    def test_an_opened_one_off_and_its_next_step(self, tmp_path, monkeypatch):
        other = World(tmp_path)
        _point(other, monkeypatch)
        try:
            assert _invoke(["open", "--kind", "extraction", str(other.package)]).exit_code == 0
            got = _invoke(["list"])
            line = next(ln for ln in got.output.splitlines() if ln.startswith(other.id))
            assert "opened" in line
            assert "git add" in got.output and "git push" in got.output
            other.commit("open", push=None)
            assert "pushed" in next(ln for ln in _invoke(["list"]).output.splitlines()
                                    if ln.startswith(other.id))
        finally:
            assets.use_one_offs_root(None)

    def test_none_says_so_and_names_open(self, tmp_path, monkeypatch):
        empty = tmp_path / "one-offs"
        empty.mkdir()
        assets.use_one_offs_root(empty)
        monkeypatch.delenv(assets.ASSET_ENV, raising=False)
        try:
            got = _invoke(["list"])
            assert "No one-offs found" in got.output
            assert "mothman one-off open --kind extraction <package>" in got.output
        finally:
            assets.use_one_offs_root(None)


class TestTheTui:
    """Criterion 2: bare `mothman one-off` opens a menu of its own, listing the
    one-offs and offering a new package; once one is chosen, every step acts
    on it for the rest of the session."""

    def test_choose_then_steps_act_on_it(self, world, monkeypatch):
        from cli import common, one_off

        asked = []
        answers = iter([lambda c: next(x for x in c if x.startswith(world.id)),
                        lambda c: "List every one-off", lambda c: None])

        def select(message, choices, hint, default=None):
            asked.append((message, list(choices)))
            return next(answers)(choices)

        monkeypatch.setattr(common, "select", select)
        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        got = _invoke([])
        assert got.exit_code == 0, got.output
        first, second = asked[0], asked[1]
        assert one_off.OPEN_NEW in first[1]
        assert any(c.startswith(world.id) and "[loaded]" in c for c in first[1])
        assert second[0] == f"{world.id}: which step?"
        assert assets.selected().name == world.id
        assert "another one-off needs a new session" in got.output


    def test_open_a_new_package_from_it(self, tmp_path, monkeypatch):
        from cli import common, one_off

        other = World(tmp_path)
        _point(other, monkeypatch)
        answers = iter([one_off.OPEN_NEW, "extraction"])
        monkeypatch.setattr(common, "select", lambda *a, **k: next(answers))
        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        try:
            got = CliRunner().invoke(one_off.one_off_group, [], input=f"{other.package}\n")
            assert got.exit_code == 0, got.output
            assert _folder(other).is_dir()
            assert f"mothman one-off load --id {other.id}" in got.output
        finally:
            assets.use_one_offs_root(None)


class TestTheDropIsOnlyEverAsked:
    """Criterion 9. READS SOURCE ON PURPOSE: 'nothing drops a one-off
    automatically' is an architecture rule with no behaviour to observe - the
    one removal function is called by the drop command and nothing else."""

    def test_only_the_drop_command_removes(self):
        callers = []
        for path in ROOT.rglob("*.py"):
            if any(p in path.parts for p in (".venv", "node_modules", "tests")):
                continue
            text = path.read_text(errors="ignore")
            if "one_off_lifecycle.remove(" in text:
                callers.append(path.relative_to(ROOT).as_posix())
        assert callers == ["cli/one_off.py"]
        source = (ROOT / "cli" / "one_off.py").read_text()
        body = source[source.index("def drop_command"):source.index("def setup_dbt_utils")]
        assert "one_off_lifecycle.remove(" in body
        assert source.count("one_off_lifecycle.remove(") == 1


class TestTheDrop:
    """Criteria 6 to 8, on the module's loaded one-off - so LAST in this module.
    The typed id only, the inventory with what each holds, 'Deleted' as each
    goes, the configuration kept, and a partial failure re-runnable."""

    def test_no_terminal_is_refused(self, world):
        got = _invoke(["drop", "--id", world.id])
        assert got.exit_code != 0
        said = _said(got)
        assert "no flag stands in for it" in said and "nothing was removed" in said
        assert world.query("SELECT 1")  # the database is still there

    def test_a_wrong_id_removes_nothing(self, world, monkeypatch):
        from cli import common

        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        got = CliRunner().invoke(__import__("cli.one_off", fromlist=["x"]).one_off_group,
                                 ["drop", "--id", world.id], input="wrong\n")
        assert "Did not match" in got.output and "nothing was removed" in got.output
        assert (world.state / "data" / world.id).is_dir()

    def test_the_typed_id_removes_each_item_and_a_failure_is_rerun(self, world, monkeypatch):
        from cli import common
        from cli.one_off import one_off_group
        from qa_tools.common import one_off_lifecycle

        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        (_folder(world) / "dbt" / "target").mkdir(exist_ok=True)
        (_folder(world) / "dbt" / "target" / "manifest.json").write_text("{}")
        # A results file, as a build of its page writes (REQ-DASH-444).
        reports = world.state / "reports" / world.id
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "results.json").write_text("{}")
        real = one_off_lifecycle.remove
        monkeypatch.setattr(one_off_lifecycle, "remove", lambda item: (
            (_ for _ in ()).throw(OSError("busy")) if item.kind == "database" else real(item)))
        first = CliRunner().invoke(one_off_group, ["drop", "--id", world.id],
                                   input=world.id + "\n")
        said = _said(first)
        assert f"the database {world.database}:" in said and "table(s)" in said \
            and "row(s)" in said
        assert f"data/{world.id}/" in said and f"reports/{world.id}/" in said \
            and "its dbt target" in said and "file(s)" in said
        assert first.exit_code != 0 and "could not be removed" in said and "again" in said
        assert f"Deleted data/{world.id}/" in said
        assert not (world.state / "data" / world.id).exists()
        monkeypatch.setattr(one_off_lifecycle, "remove", real)
        second = CliRunner().invoke(one_off_group, ["drop", "--id", world.id],
                                    input=world.id + "\n")
        assert second.exit_code == 0, second.output
        assert f"Deleted the database {world.database}" in second.output
        with psycopg.connect(world.admin) as conn:
            assert conn.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                [world.database]).fetchone() is None
        assert (_folder(world) / "data-asset.yaml").is_file()
        assert not (_folder(world) / "dbt" / "target").exists() and not reports.exists()
        assert second.output.rstrip().endswith("Next: mothman one-off list")
