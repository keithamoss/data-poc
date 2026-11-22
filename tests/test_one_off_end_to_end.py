"""A real recipe package, run end to end through `mothman one-off --id` to a
published page (REQ-TEST-437 criteria 1 to 4 and 6), and what each step of
that journey proves of the requirements it runs through: publishing
(REQ-PIPE-443), the page's kind-neutral shape (REQ-DASH-444) and the
extraction's recipe display (REQ-DASH-447).

THE PACKAGE IS COMMITTED: tests/fixtures/extraction_package/ - a recipe and
four CSV files. people.csv is counted, three rows against an expected three,
one with an empty identifier and one with a date outside the cohort;
summary.csv is a DERIVED PRODUCT, one value of it no integer; labs.csv is
counted and clean, two rows against an expected two; extra.csv is declared by
nobody; visits.csv is declared and ABSENT. The journey copies it and gives the
copy this session's own id (MOTHMAN_TEST_DB_TAG), so two test sessions never
share a database; the recipe's digest is the copy's.

ONE JOURNEY PER MODULE, read by every test: the package opened into a
temporary one-offs root inside a temporary git repository with a temporary
bare remote (never the real one-offs/ tree, never the real remote), loaded
into a throwaway supply_<id> on the test server, published to a temporary
destination - undecided, then released, then withheld - and dropped. Every
step's output, and a copy of each page published, is kept for the tests.
Nothing in it is a bootstrap, and nothing reaches GitHub: every `gh` boundary
and every subprocess is watched throughout.

NOT HERE: a cross-table relationship between the derived table and a counted
one (criteria 1 and 2) - recipe format version 1 declares none (REQ-QAC-441
criterion 6, unowned), so the fixture cannot carry one. Criterion 5's second
test is tests/test_not_yet_agreed_beside_calendared.py.
"""
# READS ONLY ITS OWN REPORTS: every reports/ path here is under this module's
# own temporary state root, never the real tree.
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest
import yaml
from click.testing import CliRunner

from asset_model import assets

from test_one_off_load import World, _point, _said

pytestmark = pytest.mark.asset("daily")

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "extraction_package"
FILES = ("recipe.json", "people.csv", "summary.csv", "labs.csv", "extra.csv")


def _package(where: Path, one_off_id: str, *, labs: str | None = None) -> Path:
    """A copy of the committed fixture package under this session's id."""
    where.mkdir(parents=True)
    for name in FILES:
        shutil.copyfile(FIXTURE / name, where / name)
    recipe = json.loads((where / "recipe.json").read_text())
    recipe["extraction_id"] = one_off_id
    (where / "recipe.json").write_text(json.dumps(recipe, indent=1))
    if labs is not None:
        (where / "labs.csv").write_text(labs)
    return where


def _invoke(args, *, input=None):
    from cli.one_off import one_off_group

    return CliRunner().invoke(one_off_group, args, input=input)


def _reset():
    assets.release_claim()
    assets.deselect_one_off()


class Journey(World):
    """The World of test_one_off_load, with the committed fixture package, a
    destination of its own and a watch on GitHub."""

    def __init__(self, base: Path):
        super().__init__(base)
        self.package = _package(base / "fixture-pkg", self.id)
        self.dest = base / "destination"
        (self.root / "extraction" / "_template" / "publishing.yaml").write_text(
            f"destination: {self.dest}\n")
        self.commit("the test's destination")
        self.said: dict[str, object] = {}
        self.pages: dict[str, str] = {}
        self.github: list[str] = []
        self.hosting: list[str] = []

    @property
    def page(self) -> Path:
        return self.dest / f"{self.id}.html"

    def keep(self, name: str) -> None:
        self.pages[name] = self.page.read_text(encoding="utf-8")
        shutil.copyfile(self.page, self.dest / f"_{name}.html")


def _watch_github(journey: Journey, mp) -> None:
    """Every GitHub boundary and every `gh` subprocess, recorded."""
    real_refuse = assets.refuse_github

    def refuse(what):
        journey.github.append(what)
        return real_refuse(what)

    mp.setattr(assets, "refuse_github", refuse)
    # EVERY SUBPROCESS GOES THROUGH Popen - run, check_output and the rest
    # among them - so a subclass of it sees every one, and stays a class for
    # whatever checks inheritance against it.
    class Watched(subprocess.Popen):
        def __init__(self, args, *a, **kw):
            first = args[0] if isinstance(args, (list, tuple)) and args else str(args).split(" ")[0]
            if os.path.basename(str(first)) == "gh":
                journey.github.append(" ".join(map(str, args)))
            super().__init__(args, *a, **kw)

    mp.setattr(subprocess, "Popen", Watched)
    # AND THE RECURRING ASSETS' HOSTING (REQ-PIPE-443 criterion 10).
    from dashboard import hosting, snapshot_dashboard

    for module, name in ((hosting, "upload"), (hosting, "wrangler"), (hosting, "find_wrangler"),
                         (snapshot_dashboard, "take_snapshot"),
                         (snapshot_dashboard, "page_fingerprint")):
        mp.setattr(module, name, lambda *a, __n=name, **kw: journey.hosting.append(__n))


def _step(journey, name, args, **kw):
    got = _invoke(args, **kw)
    journey.said[name] = got
    _reset()
    return got


@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    from cli import common
    from qa_tools.common import filing, supply_db
    from qa_tools.tools import orchestrate

    from qa_tools.common import git_identity

    j = Journey(tmp_path_factory.mktemp("one-off-journey"))
    with pytest.MonkeyPatch.context() as mp:
        _point(j, mp)
        # THE TEST'S DECIDER, named in its copy of the template's people.yaml.
        mp.setattr(git_identity, "get_run_by", lambda: "tester@example.org")
        _watch_github(j, mp)
        try:
            folder = j.root / "extraction" / j.id
            opened = _step(j, "open", ["open", "--kind", "extraction", str(j.package)])
            assert opened.exit_code == 0, opened.output
            # NOT COMMITTED, then COMMITTED BUT NOT PUSHED (REQ-PIPE-440 c9).
            _step(j, "uncommitted", ["load", "--id", j.id, str(j.package)])
            subprocess.run(["git", "add", "-A"], cwd=j.repo, check=True)
            subprocess.run(["git", "commit", "-qm", "open"], cwd=j.repo, check=True)
            _step(j, "unpushed", ["load", "--id", j.id, str(j.package)])
            subprocess.run(["git", "push", "-q", "origin", "work"], cwd=j.repo, check=True)
            # THE KIND'S TEMPLATE UNCOMMITTED (Keith, v6 Q1).
            people = j.root / "extraction" / "_template" / "people.yaml"
            before = people.read_text()
            people.write_text(before + "# an edit nobody committed\n")
            _step(j, "template-uncommitted", ["load", "--id", j.id, str(j.package)])
            people.write_text(before)
            # MOTHMAN_ASSET SET BESIDE --id, and NAMING THE ONE-OFF to a command
            # outside `mothman one-off` (REQ-PIPE-446 criteria 3 and 9).
            mp.setenv(assets.ASSET_ENV, "daily")
            _step(j, "asset-set", ["load", "--id", j.id, str(j.package)])
            mp.setenv(assets.ASSET_ENV, j.id)
            from cli.app import cli

            j.said["asset-names-it"] = CliRunner().invoke(cli, ["dashboard", "rebuild-results"])
            _reset()
            mp.delenv(assets.ASSET_ENV)
            # AN ID ALREADY UNDER assets/ (REQ-PIPE-439 criterion 7).
            clash = _package(j.base / "clash-pkg", "daily")
            _step(j, "id-clash", ["open", "--kind", "extraction", str(clash)])
            # A LOAD STOPPED PARTWAY, then resumed by loading again (REQ-PIPE-442 c5).
            real_run = orchestrate.run_arrivals

            def stop_at_the_labs(collection_id, *a, **kw):
                if collection_id == "lab-study":
                    raise RuntimeError("the test stopped the load here")
                return real_run(collection_id, *a, **kw)

            mp.setattr(orchestrate, "run_arrivals", stop_at_the_labs)
            _step(j, "stopped", ["load", "--id", j.id, str(j.package)])
            mp.setattr(orchestrate, "run_arrivals", real_run)
            _step(j, "resumed", ["load", "--id", j.id, str(j.package)])
            # A DIFFERENT PACKAGE WITH THE SAME ID (REQ-PIPE-442 c5).
            other = _package(j.base / "other-pkg", j.id, labs="lab_id,reading\nl9,9.5\n")
            _step(j, "other-package", ["load", "--id", j.id, str(other)])
            # WHAT WAS RECORDED, before anything is dropped.
            assets.select_one_off(j.id)
            j.filings = {d: filing.filings_of(d) for d in
                         ("cohort-people", "cohort-summary", "lab-results", "cohort-visits")}
            with supply_db.connect(read_only=True, label="test-journey") as conn:
                j.results = conn.execute(
                    "SELECT c.dataset_id, c.check_id, c.status FROM qa.check_result c "
                    "JOIN qa.run r USING (run_key) WHERE r.completed_at IS NOT NULL").fetchall()
            _reset()
            # DROPPED UNPUBLISHED, with the typed id - then loaded again.
            real_tty = common.require_tty
            mp.setattr(common, "require_tty", lambda hint: None)
            (folder / "dbt" / "target").mkdir(exist_ok=True)
            # A results file, as a build of its page would write one.
            (j.state / "reports" / j.id).mkdir(parents=True, exist_ok=True)
            (j.state / "reports" / j.id / "results.json").write_text("{}")
            (folder / "dbt" / "target" / "manifest.json").write_text("{}")
            j.before_drop = {
                "data": (j.state / "data" / j.id).is_dir(),
                "reports": (j.state / "reports" / j.id).is_dir(),
                "target": (folder / "dbt" / "target").is_dir()}
            _step(j, "drop-wrong-id", ["drop", "--id", j.id], input="nope\n")
            j.after_wrong_id = (j.state / "data" / j.id).is_dir()
            mp.setattr(common, "require_tty", real_tty)
            _step(j, "drop-no-terminal", ["drop", "--id", j.id])
            mp.setattr(common, "require_tty", lambda hint: None)
            _step(j, "drop-unpublished", ["drop", "--id", j.id], input=j.id + "\n")
            j.after_drop = {
                "database": _database_exists(j),
                "data": (j.state / "data" / j.id).exists(),
                "reports": (j.state / "reports" / j.id).exists(),
                "target": (folder / "dbt" / "target").exists(),
                "configuration": (folder / "data-asset.yaml").is_file()}
            _step(j, "reloaded", ["load", "--id", j.id, str(j.package)])
            # PUBLISHED UNDECIDED - in an environment that does not publish the
            # recurring assets' dashboards, whose gate is not a one-off's.
            from qa_tools.common import environments

            j.environment_publishes = environments.current().publishes
            _step(j, "publish-no-terminal", ["publish", "--id", j.id])
            _step(j, "publish-undecided", ["publish", "--id", j.id, "--yes"])
            j.keep("undecided")
            # RELEASED, then published again over its own page.
            _step(j, "release", ["decide", "--id", j.id, "--decision", "release", "--reason",
                                 "Every finding is explained in the project's notes.", "--yes"])
            _step(j, "publish-released", ["publish", "--id", j.id, "--yes"])
            j.keep("released")
            # ANOTHER PACKAGE'S PAGE AT THE ADDRESS is never written over.
            shutil.move(j.page, j.dest / "_held.html")
            j.page.write_text(j.pages["released"].replace(
                _identity(j.pages["released"])["package_digest"], "0" * 64))
            j.foreign_before = j.page.read_text()
            _step(j, "publish-over-another", ["publish", "--id", j.id, "--yes"])
            j.foreign_after = j.page.read_text()
            shutil.move(j.dest / "_held.html", j.page)
            # LOADING A PUBLISHED ONE-OFF (REQ-PIPE-443 criterion 7).
            _step(j, "load-published", ["load", "--id", j.id, str(j.package)])
            # WITHHELD AFTER THE LAST PUBLISH: the drop warns and offers to
            # publish first (criterion 9) - accepted - then takes the typed id.
            _step(j, "withhold", ["decide", "--id", j.id, "--decision", "withhold", "--reason",
                                  "The cohort bounds fail: two people fall outside the "
                                  "recipe's dates and must be explained first.", "--yes"])
            mp.setattr(common, "confirm", lambda message, yes=False, default=False, **kw: True)
            # THE RECIPE FILE GONE before this last publish: the page reads what
            # the recipe declared from the committed folder (REQ-DASH-447 c4).
            shutil.move(j.package, j.base / "package-moved-away")
            _step(j, "drop-published", ["drop", "--id", j.id], input=j.id + "\n")
            j.keep("withheld")
            j.final = {"database": _database_exists(j), "page": j.page.is_file()}
            if os.environ.get("JOURNEY_DEBUG"):
                for k, v in j.said.items():
                    print(f"===== {k} exit={v.exit_code} exc={v.exception!r}\n{v.output[-1500:]}")
            yield j
        finally:
            _reset()
            assets.use_one_offs_root(None)
            j.drop()


def _database_exists(j) -> bool:
    with psycopg.connect(j.admin) as conn:
        return conn.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                            [j.database]).fetchone() is not None


def _identity(page: str) -> dict:
    from qa_tools.common import one_off_publish

    return one_off_publish.identity_of(page)


def _out(j, step) -> str:
    return _said(j.said[step])


# ---- REQ-TEST-437 criterion 6, first: the fixture holds what it claims -------

class TestTheFixtureHoldsWhatItClaims:
    def test_a_calendar_less_dataset_and_recorded_results(self, journey):
        folder = journey.root / "extraction" / journey.id
        calendar = yaml.safe_load((folder / "calendar.yaml").read_text())
        assert [d for d in calendar["datasets"] if d.get("no_calendar")], "no calendar-less dataset"
        assert journey.results, "no recorded result"


# ---- REQ-TEST-437 criterion 3: the refusals, the resume and the drop --------

class TestTheRefusals:
    def test_an_uncommitted_folder(self, journey):
        got = journey.said["uncommitted"]
        assert got.exit_code != 0 and "uncommitted changes or untracked files" in _out(journey, "uncommitted")

    def test_an_unpushed_commit(self, journey):
        assert journey.said["unpushed"].exit_code != 0
        assert "is not on origin/work" in _out(journey, "unpushed")

    def test_an_uncommitted_template(self, journey):
        said = _out(journey, "template-uncommitted")
        assert journey.said["template-uncommitted"].exit_code != 0
        assert "the kind's template" in said and "uncommitted changes" in said

    def test_mothman_asset_set(self, journey):
        said = _out(journey, "asset-set")
        assert journey.said["asset-set"].exit_code != 0
        assert "MOTHMAN_ASSET is 'daily'" in said

    def test_mothman_asset_naming_the_one_off(self, journey):
        # REFUSED AS NAMING NO ASSET FOLDER (REQ-PIPE-446 criterion 9), in the
        # one-off half of REQ-PIPE-363's wording (Keith, v6 Q2).
        got = journey.said["asset-names-it"]
        said = _said(got)
        assert got.exit_code != 0 and "not an asset" in said and "daily, quarterly" in said

    def test_an_id_already_under_assets(self, journey):
        said = _out(journey, "id-clash")
        assert journey.said["id-clash"].exit_code != 0 and "'daily' is already a folder" in said

    def test_a_different_package_with_the_same_id(self, journey):
        said = _out(journey, "other-package")
        assert journey.said["other-package"].exit_code != 0
        assert "already holds another package" in said and "A re-send is a new one-off" in said


class TestAStoppedLoadIsResumed:
    def test_stopped_then_resumed(self, journey):
        assert journey.said["stopped"].exit_code != 0
        resumed = journey.said["resumed"]
        assert resumed.exit_code == 0, resumed.output
        assert "Resuming the load into" in resumed.output


class TestTheDrop:
    def test_it_is_refused_with_no_terminal(self, journey):
        said = _out(journey, "drop-no-terminal")
        assert journey.said["drop-no-terminal"].exit_code != 0 and "no flag stands in" in said

    def test_a_wrong_id_removes_nothing(self, journey):
        assert "Did not match" in journey.said["drop-wrong-id"].output
        assert journey.after_wrong_id

    def test_the_typed_id_removes_everything_but_the_configuration(self, journey):
        assert all(journey.before_drop.values()), journey.before_drop
        assert journey.after_drop == {"database": False, "data": False, "reports": False,
                                      "target": False, "configuration": True}

    def test_the_same_package_loads_again_after_an_unpublished_drop(self, journey):
        got = journey.said["reloaded"]
        assert got.exit_code == 0, got.output
        assert f"Created supply_{journey.id}" in got.output


# ---- REQ-TEST-437 criterion 2: what was checked and recorded ------------------

class TestWhatWasRecorded:
    def test_each_table_with_no_slot_and_no_period(self, journey):
        from asset_model import assignment

        for dataset in ("cohort-people", "cohort-summary", "lab-results"):
            records = journey.filings[dataset]
            assert records, dataset
            assert all(r["slot"] is None and r["branch"] == assignment.NO_PERIOD
                       for r in records), (dataset, records)

    def test_the_row_count_was_checked(self, journey):
        counted = {(d, s) for d, cid, s in journey.results if ".expected_rows_" in cid}
        assert ("cohort-people", "pass") in counted and ("lab-results", "pass") in counted

    def test_the_undeclared_file_failed_and_was_not_filed(self, journey):
        assert any(cid.endswith("undeclared_file") and s == "fail"
                   for _d, cid, s in journey.results)
        filed = [p.name for p in (journey.state / "data").rglob("extra.csv")]
        assert filed == []


class TestNoGitHub:
    """Criterion 4: no GitHub API call at any step."""

    def test_none(self, journey):
        assert journey.said, "the journey ran no step"
        assert journey.github == []


# ---- REQ-PIPE-443: publishing ------------------------------------------------

class TestPublishing:
    def test_it_confirms_with_the_address_the_decision_and_the_unchecked(self, journey):
        said = _out(journey, "publish-undecided")
        assert f"to: {journey.page}" in said
        assert "Decision in force: none recorded" in said
        assert "Datasets not yet checked: 0." in said

    def test_no_terminal_and_no_yes_is_refused(self, journey):
        got = journey.said["publish-no-terminal"]
        assert got.exit_code != 0 and "pass --yes" in _said(got)
        assert "undecided" in journey.pages  # and the later --yes did publish

    def test_it_prints_the_address(self, journey):
        assert f"Published -> {journey.page}" in journey.said["publish-undecided"].output

    def test_one_page_named_by_the_id_with_fonts_beside_it(self, journey):
        names = sorted(p.name for p in journey.dest.iterdir() if not p.name.startswith("_"))
        assert names == ["fonts", f"{journey.id}.html"]
        assert any((journey.dest / "fonts").glob("*.woff2"))
        page = journey.pages["undecided"]
        assert 'src="data/' not in page and "data-mothman-key=" in page

    def test_a_second_publish_replaces_its_own_page(self, journey):
        assert journey.said["publish-released"].exit_code == 0
        assert "replacing its own page" in _out(journey, "publish-released")
        assert _identity(journey.pages["released"])["decisions"] == 1

    def test_another_packages_page_is_never_written_over(self, journey):
        got = journey.said["publish-over-another"]
        assert got.exit_code != 0 and "another package" in _said(got)
        assert journey.foreign_after == journey.foreign_before

    def test_a_published_one_off_is_not_loaded_again(self, journey):
        said = _out(journey, "load-published")
        assert journey.said["load-published"].exit_code != 0
        assert "already published at" in said and "A re-send is a new one-off" in said

    def test_a_decision_after_publishing_says_the_page_is_behind(self, journey):
        said = _out(journey, "withhold")
        assert "still shows the earlier state" in said
        assert f"mothman one-off publish --id {journey.id}" in said

    def test_the_unpublished_drop_warned_no_record_would_remain(self, journey):
        said = _out(journey, "drop-unpublished")
        assert "has no published page" in said and "no record of its QA results or decisions" in said
        assert journey.said["drop-unpublished"].exit_code == 0

    def test_the_stale_page_drop_warned_and_published_first(self, journey):
        said = _out(journey, "drop-published")
        assert "does not show the latest decision" in said
        assert said.index("Published ->") < said.index("Deleted the database")
        current = [d for d in _one_off(journey.pages["withheld"])["decisions"] if d["current"]]
        assert current[0]["decision"] == "withhold"
        assert journey.final == {"database": False, "page": True}

    def test_not_the_recurring_assets_publish(self, journey):
        """Criteria 2 and 10: no publish-environment gate - the suite's
        environment publishes nothing - and no snapshot, fingerprint, upload
        or wrangler."""
        assert journey.environment_publishes is False
        assert "undecided" in journey.pages
        assert journey.hosting == []

    def test_no_snapshot_archived(self, journey):
        tracked = subprocess.run(["git", "status", "--porcelain", "dashboard/snapshots"],
                                 cwd=ROOT, capture_output=True, text=True).stdout
        assert tracked == ""

    def test_next_steps(self, journey):
        tail = journey.said["publish-undecided"].output.rstrip().splitlines()[-3:]
        assert tail == ["Next: record a decision, or drop it:",
                        f"  mothman one-off decide --id {journey.id}",
                        f"  mothman one-off drop --id {journey.id}"]


def _one_off(page: str) -> dict:
    found = re.search(r"const ONE_OFF = (.*?);\n", page)
    return json.loads(found.group(1).replace("<\\/", "</"))


class TestThePagesRecords:
    """REQ-DASH-444 criteria 6 and 8, and REQ-DASH-447 criterion 1, from what
    each page embeds."""

    def test_both_commits_and_the_publication(self, journey):
        for name in ("undecided", "released"):
            got = _one_off(journey.pages[name])
            assert re.fullmatch(r"[0-9a-f]{7}", got["builtAt"]), got
            assert re.fullmatch(r"[0-9a-f]{7}", got["checkedAt"]), got
            assert got["address"] == str(journey.page) and got["publishedAt"]

    def test_every_decision_newest_first(self, journey):
        got = _one_off(journey.pages["withheld"])["decisions"]
        assert [d["decision"] for d in got] == ["withhold", "release"]
        assert got[0]["current"] and not got[1]["current"]
        assert got[1]["replacedBy"] == got[0]["at"]

    def test_no_vendor_reference(self, journey):
        for name, page in journey.pages.items():
            assert "vendor/" not in page, name


# ---- the rendered pages (REQ-DASH-444, REQ-DASH-447, REQ-DASH-436 c3 c5 c6,
# REQ-PIPE-438 c5, REQ-TEST-437 c2) ---------------------------------------

AG, CO, LA = "health-agency", "cohort-study", "lab-study"
VIEWS = {"home": "", "agency": f"#/agency/{AG}",
         "people": f"#/agency/{AG}/collection/{CO}/dataset/cohort-people",
         "summary": f"#/agency/{AG}/collection/{CO}/dataset/cohort-summary",
         "visits": f"#/agency/{AG}/collection/{CO}/dataset/cohort-visits",
         "labs": f"#/agency/{AG}/collection/{LA}/dataset/lab-results"}


def _open(page, journey, which: str, route: str = "", *, errors=None, failed=None):
    """Cold-load one of the journey's kept pages at a route - a real load, as a
    reader following a shared deep link does."""
    if errors is not None:
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
    if failed is not None:
        page.on("requestfailed", lambda r: failed.append(r.url))
    page.goto(f"file://{journey.dest / f'_{which}.html'}{route}")
    page.wait_for_function("Number(document.documentElement.dataset.renderCount || 0) >= 1")
    return page


def _line(page) -> str:
    return page.locator("[data-one-off-decision-line]").inner_text().strip()


class TestEveryViewNamesItselfAndCarriesTheDecision:
    """REQ-DASH-444 criteria 1, 2, 3, 5 and 8, and REQ-TEST-437 criterion 2's
    pages: on every view, cold-loaded."""

    @pytest.mark.parametrize("view", list(VIEWS))
    def test_undecided(self, page, journey, view):
        errors, failed = [], []
        _open(page, journey, "undecided", VIEWS[view], errors=errors, failed=failed)
        rec = _one_off(journey.pages["undecided"])
        assert page.title().endswith(f" · {journey.id} · The fixture study · QA report")
        assert page.locator(".masthead h1").inner_text() == rec["siteName"]
        assert page.locator("#masthead-asset").text_content() == "One-off extraction"
        assert _line(page) == ("No release decision recorded. This page reports QA results only; "
                               "it does not release or withhold the data.")
        self._above_the_qa_result(page)
        provenance = page.locator("[data-one-off-provenance]").inner_text()
        assert f"to {journey.page}" in provenance
        assert f"built at {rec['builtAt']}" in provenance and f"checked at {rec['checkedAt']}" in provenance
        assert "A decision recorded after it was published appears only on a later publish." in provenance
        assert errors == [] and failed == []

    @pytest.mark.parametrize("view", ["home", "people", "labs"])
    def test_released(self, page, journey, view):
        errors = []
        _open(page, journey, "released", VIEWS[view], errors=errors)
        line = _line(page)
        assert re.fullmatch(r"Released by Tess Ter, .+: Every finding is explained in the "
                            r"project's notes\.", line), line
        assert page.locator("[data-one-off-decision] .pill").count() == 0
        self._above_the_qa_result(page)
        assert errors == []

    def test_withheld_says_its_reason_in_full(self, page, journey):
        _open(page, journey, "withheld", VIEWS["people"])
        assert _line(page).startswith("Withheld by Tess Ter, ")
        assert _line(page).endswith(": The cohort bounds fail: two people fall outside the "
                                    "recipe's dates and must be explained first.")

    @staticmethod
    def _above_the_qa_result(page):
        line = page.locator("[data-one-off-decision]").bounding_box()
        label = page.locator(".qa-result-label").first
        if label.count():
            assert line["y"] < label.bounding_box()["y"]
        assert page.locator("#view > [data-one-off-decision]").count() == 1


class TestTheHomeView:
    def test_every_decision_newest_first(self, page, journey):
        _open(page, journey, "withheld")
        entries = page.locator("[data-one-off-decision-entry]").all_inner_texts()
        assert len(entries) == 2
        assert entries[0].startswith("Withheld by Tess Ter") and entries[0].endswith("Current")
        assert entries[1].startswith("Released by Tess Ter")
        assert re.search(r"Replaced by the decision of \d", entries[1]), entries[1]

    def test_the_recipe_summary_and_no_repeats(self, page, journey):
        _open(page, journey, "released")
        folder = journey.root / "extraction" / journey.id
        recipe = yaml.safe_load((folder / "data-asset.yaml").read_text())["recipe"]
        assert page.locator("[data-recipe-version]").inner_text() == "1"
        assert page.locator("[data-recipe-digest]").inner_text() == recipe["digest"]
        assert page.locator("[data-recipe-filter]").inner_text() == recipe["filter"]
        summary = page.locator("[data-recipe-summary]").inner_text()
        assert journey.id not in summary and "The fixture study" not in summary

    def test_the_undeclared_file_is_named_once(self, page, journey):
        """Keith 2026-11-22 ('first dataset + home'): counted on the first
        counted dataset, and named once on the home view."""
        _open(page, journey, "released")
        found = page.locator("[data-undeclared-files]")
        assert found.count() == 1
        assert found.locator("[data-undeclared-names]").inner_text() == "extra.csv"
        assert "People" in found.inner_text()
        _open(page, journey, "released", VIEWS["people"])
        assert page.locator("[data-undeclared-files]").count() == 0

    def test_the_qa_result_label(self, page, journey):
        _open(page, journey, "released")
        assert page.locator(".card .qa-result-label").first.inner_text() == "QA result"
        _open(page, journey, "released", VIEWS["agency"])
        assert "QA result" in page.locator(".dataset-table thead").first.text_content()


class TestTheControlsAOneOffHasNot:
    """REQ-DASH-444 criterion 9 and REQ-DASH-436 criterion 5."""

    def test_no_development_tools_date_or_period(self, page, journey):
        _open(page, journey, "released")
        for control in ("in-place-on-btn", "period-btn", "activity-btn", "changelog-btn",
                        "requirements-btn", "scenarios-btn", "feedback-btn", "leaderboard-btn",
                        "plans-btn", "demo-btn", "snapshots-btn"):
            assert not page.locator(f"#{control}").is_visible(), control
        assert page.locator("#theme-btn").is_visible()

    def test_no_trends_sparklines_run_comparison_or_supply_history(self, page, journey):
        _open(page, journey, "released", VIEWS["agency"])
        assert page.locator(".datasets-trend-slot, .spark-wrap, svg.tile-spark").count() == 0
        _open(page, journey, "released", VIEWS["people"])
        assert page.locator(".supply-history, .spark-wrap, .datasets-trend-slot").count() == 0
        assert "In the warehouse" not in page.locator("#view").inner_text()
        page.locator(".col-tile").first.click()
        page.locator(".check-card").first.click()
        panel = page.locator("#check-panel-body").inner_text()
        assert "Over time" not in panel and "compared run" not in panel


class TestAddressesAOneOffCannotAnswer:
    """REQ-DASH-436 criterion 6: the nearest view, a notice, never blank."""

    @pytest.mark.parametrize("route,lands", [
        ("#/plans", "Agencies"), ("#/demo", "Agencies"), ("#/scenarios", "Agencies"),
        ("#/feedback", "Agencies"), ("?panel=requirements", "Agencies"),
        ("?panel=snapshots#/agency/health-agency", "Health Agency"),
        ("?cmp=1" + VIEWS["people"], "People"),
        ("?in-place-on=2026-01-01" + VIEWS["labs"], "Lab results"),
        ("?period=2026-Q1", "Agencies"),
        (f"#/agency/{AG}/collection/{CO}/period/2026-Q1", "Health Agency")])
    def test_the_nearest_view_with_a_notice(self, page, journey, route, lands):
        errors = []
        _open(page, journey, "released", route, errors=errors)
        assert "This page has no" in page.locator("[data-one-off-notice]").inner_text()
        assert page.locator("#view h2").first.inner_text().startswith(lands)
        for removed in ("panel=", "cmp=", "in-place-on=", "period=", "#/plans", "#/demo"):
            assert removed not in page.url
        assert errors == []


class TestEachDatasetOnThePage:
    """REQ-DASH-436 criteria 2 and 3, REQ-PIPE-438 criterion 5 and REQ-TEST-437
    criterion 2: real verdicts, the absent table Fail, the derived product out."""

    def _row(self, page, dataset):
        return page.locator(f"tr:has(a[href*='dataset/{dataset}'])")

    def test_verdicts(self, page, journey):
        _open(page, journey, "released", VIEWS["agency"])
        assert "Fail" in self._row(page, "cohort-people").locator(".pill").first.inner_text()
        assert "Fail" in self._row(page, "cohort-visits").locator(".pill").first.inner_text()
        assert "No data" not in self._row(page, "cohort-visits").inner_text()
        assert "Pass" in self._row(page, "lab-results").locator(".pill").first.inner_text()

    def test_the_derived_product(self, page, journey):
        _open(page, journey, "released", VIEWS["agency"])
        assert "Derived product, not counted in the extraction's status" in \
            self._row(page, "cohort-summary").inner_text()
        assert "derived product" in page.locator(".not-counted-why").first.inner_text()


class TestLayers:
    """REQ-DASH-444 criterion 10 and REQ-DASH-447 criterion 3."""

    def test_two_names_only(self, page, journey):
        _open(page, journey, "released", VIEWS["people"])
        names = {t.strip() for t in page.locator("#view .layer-chip").all_text_contents()}
        assert names == {"Default check", "Recipe check"}, names


class TestTheTablesDeclaration:
    """REQ-DASH-447 criteria 2 to 4, read from the committed folder - the
    package's recipe was moved away before the withheld page was published."""

    def test_people(self, page, journey):
        _open(page, journey, "withheld", VIEWS["people"])
        section = page.locator("[data-declaration='cohort-people']")
        assert "Health Agency › Cohort Study › People" in section.locator("[data-declared-placement]").inner_text()
        assert section.locator("[data-declared-derived]").inner_text() == "No"
        assert "first_seen: from 2020-01-01 to 2024-12-31" in section.locator("[data-declared-cohort]").inner_text()
        assert section.locator("[data-declared-expected-rows]").inner_text().startswith("3")
        person = section.locator("[data-declared-column='person_id']").inner_text()
        assert "string" in person and "Primary identifier" in person
        first_seen = section.locator("[data-declared-column='first_seen']")
        assert "date" in first_seen.inner_text()
        assert {t.strip() for t in first_seen.locator(".layer-chip").all_text_contents()} == {"Recipe check"}
        assert section.locator("[data-declared-cohort] .layer-chip").count() >= 1

    def test_the_derived_summary(self, page, journey):
        _open(page, journey, "withheld", VIEWS["summary"])
        section = page.locator("[data-declaration='cohort-summary']")
        assert "Derived product, not counted in the extraction's status" in \
            section.locator("[data-declared-derived]").inner_text()
        assert section.locator("[data-declared-expected-rows]").inner_text() == \
            "The recipe gave no expected row count"


class TestTheTuiOffersPublish:
    """REQ-PIPE-442 criterion 2 (and REQ-PIPE-446 criterion 8): the TUI's step
    menu has publish, and choosing it runs the publish for the chosen one-off."""

    def test_publish_from_the_menu(self, journey, monkeypatch):
        import click

        from cli import common
        from cli import one_off as module

        _point(journey, monkeypatch)
        asked, ran = [], []

        def select(message, choices, hint, default=None):
            asked.append(list(choices))
            if message == "Which one-off?":
                return next(c for c in choices if c.startswith(journey.id))
            return "Publish its page" if len(asked) == 2 else None

        monkeypatch.setattr(common, "select", select)
        monkeypatch.setattr(module, "publish_command",
                            lambda one_off_id, yes: ran.append((one_off_id, yes)))
        with click.Context(module.one_off_group) as ctx:
            module._tui(ctx)
        _reset()
        assert "Publish its page" in asked[1]
        assert ran == [(journey.id, False)]


class TestAnUnknownDeciderIsToldWhichFile:
    """A DEFECT FOUND ON THIS JOURNEY (2026-11-22): the refusal of a decider
    not in people.yaml named the ONE-OFF'S FOLDER's people.yaml, which does not
    exist and must not - adding one there would break its digest. It names the
    kind's template's, which is where a one-off's people are read from
    (REQ-PIPE-435 criterion 4)."""

    def test_the_template_is_named(self, journey, monkeypatch):
        from qa_tools.common import git_identity

        _point(journey, monkeypatch)
        monkeypatch.setattr(git_identity, "get_run_by", lambda: "nobody@example.org")
        got = _invoke(["decide", "--id", journey.id, "--decision", "release", "--reason", "x",
                       "--yes"])
        _reset()
        said = _said(got).replace(" ", "")
        template = str(journey.root / "extraction" / "_template" / "people.yaml").replace(" ", "")
        assert got.exit_code != 0 and template in said, said


class TestAnS3Destination:
    """REQ-PIPE-443 criterion 1's other destination: an S3 prefix, through the
    boto3 client's own calls - the page and its fonts/ under the prefix, read
    back as the record of what was published. No S3 is reachable here, so the
    client is a stand-in holding objects in memory; the calls are boto3's."""

    class Bucket:
        def __init__(self):
            self.objects = {}

        def put_object(self, Bucket, Key, Body, **kw):
            self.objects[(Bucket, Key)] = Body

        def get_object(self, Bucket, Key):
            import io

            if (Bucket, Key) not in self.objects:
                error = Exception("NoSuchKey")
                error.response = {"Error": {"Code": "NoSuchKey"}}
                raise error
            return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def test_written_and_read_back(self, tmp_path):
        from asset_model import one_off_publishing
        from qa_tools.common import one_off_publish

        (tmp_path / "publishing.yaml").write_text("destination: s3://qa-pages/extractions/\n")
        dest = one_off_publishing.read(tmp_path)
        assert (dest.bucket, dest.prefix) == ("qa-pages", "extractions")
        bucket = self.Bucket()
        assert one_off_publish.read_page(dest, "x-1", s3_client=bucket) is None
        page = tmp_path / "x-1.html"
        page.write_text("<html>" + one_off_publish.meta_tag({"one_off_id": "x-1"}) + "</html>")
        address = one_off_publish.write_page(dest, page, "x-1", s3_client=bucket)
        assert address == "s3://qa-pages/extractions/x-1.html"
        keys = {k for _b, k in bucket.objects}
        assert "extractions/x-1.html" in keys
        assert any(k.startswith("extractions/fonts/") and k.endswith(".woff2") for k in keys)
        back = one_off_publish.read_page(dest, "x-1", s3_client=bucket)
        assert one_off_publish.identity_of(back) == {"one_off_id": "x-1"}
