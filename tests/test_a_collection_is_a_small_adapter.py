"""REQ-TEST-249: adding a collection is a small adapter.

The fake Widget Register (tests/fake_collection.py) is added to a COPY of
the tracked working tree - its configuration, check files, dbt models, QA
adapter and generator provider, nothing else - and followed from generation
to a rendered dataset page, with `mothman` run from the copy against a
scratch database of its own. The repository's own contract/, data/ and
reports/ are never touched (criterion 6).

ON DEMAND (the requirement's TEST COST NFR): it bootstraps, so it runs in
CI's on-demand job beside the bootstrap-equivalence test, never in the fast
half. The copy reuses this checkout's interpreter, dbt packages and browser.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest

import fake_collection
import tree_copy
from conftest import mark_test_database

pytestmark = pytest.mark.on_demand

ROOT = tree_copy.ROOT
ADMIN_DSN_ENV = "MOTHMAN_TEST_DSN"
SCRATCH_DB = "a_collection_is_a_small_adapter"
ENGINES = ("dbt-core", "Soda Core", "datacontract-cli", "Evidently")


def _snapshot(path: Path) -> dict:
    """Every file under `path` with its size and modification time - what
    "wrote nothing here" is checked against (criterion 6)."""
    if not path.exists():
        return {}
    return {str(p.relative_to(path)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in path.rglob("*") if p.is_file()}


def _fresh_database() -> str:
    admin = os.environ[ADMIN_DSN_ENV]
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{SCRATCH_DB}"')
        mark_test_database(conn, SCRATCH_DB)
    info = psycopg.conninfo.conninfo_to_dict(admin)
    info["dbname"] = SCRATCH_DB
    return psycopg.conninfo.make_conninfo(**info)


class Copy:
    """The copy, its environment, and what each step said."""

    def __init__(self, tree: Path, dsn: str):
        self.tree, self.dsn = tree, dsn
        self.env = {**os.environ, "MOTHMAN_SUPPLY_DSN": dsn, "MOTHMAN_ENVIRONMENT": "test",
                    "NO_COLOR": "1", "COLUMNS": "200"}
        self.seconds: dict[str, float] = {}

    def mothman(self, *argv: str, step: str) -> subprocess.CompletedProcess:
        start = time.perf_counter()
        done = subprocess.run([sys.executable, "-m", "cli.app", *argv], cwd=self.tree,
                              env=self.env, capture_output=True, text=True, timeout=1800)
        self.seconds[step] = round(time.perf_counter() - start, 1)
        assert done.returncode == 0, f"{step} failed:\n{done.stdout[-4000:]}\n{done.stderr[-4000:]}"
        return done

    def results(self) -> list[dict]:
        doc = json.loads((self.tree / "reports" / "results_widget_register.json").read_text())
        return doc["results"] if isinstance(doc, dict) else doc


@pytest.fixture(scope="module")
def copy(tmp_path_factory):
    """The whole journey, once: copy, add, generate and bootstrap, keep one
    more supply by hand, build the dashboard. Each test asserts one part."""
    before = {name: _snapshot(ROOT / name) for name in ("data", "reports")}
    tree = tree_copy.copy_tracked_tree(tmp_path_factory.mktemp("small_adapter") / "tree")
    fake_collection.install(tree)
    problems = fake_collection.additions_only(tree)  # before anything runs in it

    # What a person adding a collection already has: this checkout's dbt
    # packages, and a repository to commit to (the build links to a commit).
    (tree / "dbt_project" / "dbt_packages").symlink_to(ROOT / "dbt_project" / "dbt_packages")
    git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    subprocess.run([*git, "add", "-A"], cwd=tree, check=True, capture_output=True)
    subprocess.run([*git, "commit", "-qm", "the copy, with a collection added"], cwd=tree, check=True)

    c = Copy(tree, _fresh_database())
    c.additions = problems
    c.bootstrap = c.mothman("pipeline", "bootstrap", "--collection", fake_collection.SHORT,
                            "--skip-target-trial", step="bootstrap")
    c.bootstrapped = c.results()

    kept = tmp_path_factory.mktemp("kept") / f"{fake_collection.TABLE}.csv"
    newest = sorted((tree / "data" / "deliveries").glob(f"*/{fake_collection.TABLE}.csv"))[-1]
    kept.write_bytes(newest.read_bytes())
    c.qa = c.mothman(fake_collection.SHORT, "qa", "--file", str(kept), "--commit",
                     "--originally-received", "not-known", step="qa")

    for step in ("rebuild-results", "build-data", "embed"):
        c.mothman("dashboard", step, step=step)
    c.html = tree / "dashboard" / "qa-reporting-dashboard.html"
    c.before = before
    yield c
    with psycopg.connect(os.environ[ADMIN_DSN_ENV], autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)')


class TestTheCopyIsTheTreeWithACollectionAdded:
    """Criteria 1 and 3."""

    def test_the_fake_is_kept_under_tests_in_a_collections_own_places(self):
        files = fake_collection.own_files()
        for kind in ("contract.yaml", "soda-checks.yml", "evidently-checks.yml"):
            assert f"contract/widget-agency/widget-register-{kind}" in files
        assert any(f.startswith("dbt_project/models/widget-register/") for f in files)
        assert "qa_tools/collections/widget_register.py" in files
        assert "generator/collections/widget_register.py" in files
        assert all(f.startswith(fake_collection.OWN_PATHS) for f in files)

    def test_it_differs_by_additions_only(self, copy):
        assert copy.additions == []

    def test_the_check_would_catch_an_edit_to_a_real_collection(self, tmp_path):
        tree = fake_collection.install(tree_copy.copy_tracked_tree(tmp_path / "tree"))
        hierarchy = tree / "contract" / "data-asset.yaml"
        hierarchy.write_text(hierarchy.read_text().replace("short: cp ", "short: cpx", 1))
        (tree / "qa_tools" / "tools" / "stray.py").write_text("")
        said = fake_collection.additions_only(tree)
        assert any("data-asset.yaml" in p and "replaced" in p for p in said), said
        assert any("qa_tools/tools/stray.py" in p for p in said), said


class TestItGoesAllTheWay:
    """Criteria 2 and 4."""

    def test_the_bootstrap_records_results_from_all_four_tools(self, copy):
        engines = {r.get("engine") or r.get("tool") for r in copy.bootstrapped}
        for engine in ENGINES:
            assert any(e and e.startswith(engine) for e in engines), (engine, engines)
        statuses = {r["status"] for r in copy.bootstrapped}
        assert {"pass", "fail"} <= statuses, "the dirty quarter should fail, the rest pass"

    def test_qa_keeps_a_supply_and_records_its_results(self, copy):
        assert "Kept." in copy.qa.stdout and "its results are recorded" in copy.qa.stdout
        assert len(copy.results()) > len(copy.bootstrapped)

    def test_its_dataset_page_renders_each_status_as_its_tool_recorded_it(self, copy):
        from playwright.sync_api import sync_playwright

        url = (f"file://{copy.html}#/agency/{fake_collection.AGENCY_ID}/collection/"
               f"{fake_collection.COLLECTION_ID}/dataset/{fake_collection.DATASET_ID}")
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_PATH"))
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.wait_for_function("() => Number(document.documentElement.dataset.renderCount || 0) > 0")
            shown = page.locator("#view").inner_text()
            found = page.evaluate("""(id) => {
              const raw = COLLECTION_DATA[id];
              let compared = 0; const wrong = [];
              for (const d of raw.datasets) {
                const built = buildRealDataset(d);
                d.columns.forEach((rc, ci) => rc.checks.forEach((ck, ki) => {
                  const b = built.columns[ci].checks[ki];
                  ck.history.forEach((h, hi) => {
                    if (!h.status) return;
                    compared++;
                    const got = historyStatus(b.history[hi], b);
                    if (got !== h.status) wrong.push([ck.check_id, h.run_id, h.status, got]);
                  });
                }));
              }
              return {compared, wrong};
            }""", fake_collection.COLLECTION_ID)
            browser.close()
        assert errors == []
        assert "Widget Register" in shown and "Department of Widgets" in shown, shown[:500]
        assert found["compared"] > 0, "the page holds no recorded verdict to compare"
        assert found["wrong"] == []


class TestNothingReachesTheRepository:
    """Criterion 6."""

    def test_the_real_hierarchy_never_names_it(self, copy):
        assert fake_collection.COLLECTION_ID not in (ROOT / "contract" / "data-asset.yaml").read_text()
        assert copy.tree != ROOT

    @pytest.mark.parametrize("name", ["data", "reports"])
    def test_nothing_is_written_under_the_real_tree(self, copy, name):
        assert _snapshot(ROOT / name) == copy.before[name]


def test_how_long_it_took(copy):
    """The measured time goes in the requirement's evidence (TEST COST NFR)."""
    print(f"\nREQ-TEST-249 step times: {copy.seconds}")
    assert copy.seconds["bootstrap"] > 0
