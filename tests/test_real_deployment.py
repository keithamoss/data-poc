"""A real deployment: an asset with no synthetic/ folder, run with the
generator, synthetic_data_generator, scenarios/ and the bootstrap package
blocked at find_spec (REQ-PIPE-385 criteria 1, 14 and 15; the fixture is
tests/real_asset.py).

The whole journey runs once, in a copy of the repository: `mothman pipeline
run` stages, checks, gates and records the supplies already delivered, then
`mothman dashboard rebuild` builds the page and `mothman check --no-pytest`
runs every gate that applies. Each test asserts one part.
READS ONLY ITS OWN REPORTS, built in the copy.
"""
from __future__ import annotations

import json

import psycopg
import pytest

import equiv_support
import real_asset as ea

SCRATCH_DB = "real_deployment"



@pytest.fixture(scope="module")
def deployment(tmp_path_factory, bdm_delivery_dirs):
    deliveries, receipts = bdm_delivery_dirs
    tree = ea.make(tmp_path_factory.mktemp("real_deployment"), deliveries, receipts)
    dsn = ea.fresh_database(SCRATCH_DB)
    environ = ea.env(tree, dsn)
    done = {"tree": tree, "dsn": dsn, "env": environ}
    done["run"] = ea.mothman(tree, environ, "pipeline", "run")
    done["rebuild"] = ea.mothman(tree, environ, "dashboard", "rebuild")
    done["check"] = ea.mothman(tree, environ, "check", "--no-pytest", timeout=2400)
    yield done
    equiv_support.drop_database(SCRATCH_DB)


def _ok(step) -> None:
    assert step.returncode == 0, f"exit {step.returncode}:\n{step.stdout[-6000:]}\n{step.stderr[-4000:]}"


class TestItRunsWithTheSyntheticSideAbsent:
    """REQ-PIPE-385 criteria 1 and 14."""

    def test_the_blocked_packages_are_absent_there(self, deployment):
        probe = ea.mothman(deployment["tree"], deployment["env"], "--help")
        _ok(probe)
        import subprocess
        import sys

        found = subprocess.run(
            [sys.executable, "-c", "import importlib.util as u; print([n for n in "
             f"{ea.BLOCKED!r} if u.find_spec(n) is not None])"],
            cwd=deployment["tree"], env=deployment["env"], capture_output=True, text=True)
        assert found.stdout.strip() == "[]", found.stdout + found.stderr

    def test_pipeline_run_processes_what_arrived(self, deployment):
        _ok(deployment["run"])
        with psycopg.connect(deployment["dsn"]) as conn:
            runs = conn.execute("SELECT count(*) FROM qa.run").fetchone()[0]
            results = conn.execute("SELECT count(*) FROM qa.check_result").fetchone()[0]
        assert runs == 2 and results > 0, (runs, results)

    def test_the_dashboard_builds(self, deployment):
        _ok(deployment["rebuild"])
        html = (deployment["tree"] / "dashboard" / "qa-reporting-dashboard.html").read_text()
        assert "const SCENARIO_MAP = [];" in html
        assert "const ASSET_SYNTHETIC = false;" in html

    def test_every_gate_that_applies_passes(self, deployment):
        check = deployment["check"]
        _ok(check)
        flat = " ".join(check.stdout.split())
        assert "Every gate that applies passed except the Python suite, which was skipped - " \
               "not applicable (no synthetic/ folder): providers, scenarios, scenario map." in flat, \
            check.stdout[-3000:]

    @pytest.mark.parametrize("argv", [["--help"], ["pipeline", "--help"], [ea.SHORT, "--help"]],
                             ids=["root", "pipeline", "collection"])
    def test_help_lists_no_synthetic_command(self, deployment, argv):
        got = ea.mothman(deployment["tree"], deployment["env"], *argv)
        _ok(got)
        for word in ("generate-synthetic-data", "bootstrap", "resume", "checkpoint", "cache-key",
                     "scenarios", "population", "reset-synthetic"):
            assert f" {word} " not in f" {' '.join(got.stdout.split())} ", (word, got.stdout)

    def test_bare_mothman_without_a_terminal_gives_its_flag_hint(self, deployment):
        got = ea.mothman(deployment["tree"], deployment["env"])
        assert got.returncode != 0
        assert "Traceback" not in got.stderr and "ImportError" not in got.stderr, got.stderr
        said = " ".join((got.stdout + got.stderr).split())
        assert "This needs a real interactive terminal" in said, said

    @pytest.mark.parametrize("argv", [["pipeline", "bootstrap"], [ea.SHORT, "generate-synthetic-data"],
                                      ["env", "reset-synthetic"], ["scenarios", "map"]],
                             ids=["bootstrap", "generate", "reset", "scenarios"])
    def test_a_synthetic_command_is_refused_by_name(self, deployment, argv):
        got = ea.mothman(deployment["tree"], deployment["env"], *argv)
        out = " ".join((got.stdout + got.stderr).split())
        assert got.returncode == 1, out
        # A synthetic GROUP is refused by its own name, whatever follows it.
        named = argv[:1] if argv[0] == "scenarios" else argv[:2]
        assert f"`mothman {' '.join(named)}` generates synthetic data" in out, out


#: The asset this module acts for is the fixture's, in its own copy; the
#: parent process names the daily asset its supplies are made for.
pytestmark = pytest.mark.asset("daily")


DS_PATH = f"#/agency/{ea.AGENCY}/collection/{ea.COLLECTION}/dataset/{ea.DATASET}"


@pytest.fixture
def built_page(deployment):
    _ok(deployment["rebuild"])
    return deployment["tree"] / "dashboard" / "qa-reporting-dashboard.html"


def _scenario_words(page) -> list[str]:
    """Every visible text or accessible name in the header and the current
    view that mentions a scenario."""
    return page.evaluate("""() => {
      const out = [];
      for (const root of [document.querySelector('header'), document.getElementById('view')]) {
        if (!root) continue;
        for (const el of root.querySelectorAll('*')) {
          if (el.closest('[hidden]') || el.offsetParent === null) continue;
          const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ');
          const name = el.getAttribute('aria-label') || el.getAttribute('title') || '';
          for (const t of [own, name]) if (/scenario/i.test(t)) out.push(t.trim());
        }
      }
      return out;
    }""")


class TestThePageOfARealDeployment:
    """REQ-PIPE-385 criterion 15, in a real browser: no scenario control, tab,
    link, count, jump bar or label in the header or the drill-down pages, no
    synthetic wording in the footer, and every old scenario address lands on
    the not-found page with its parameter removed."""

    def test_no_scenario_surface_on_any_page(self, page, built_page):
        page.goto(built_page.as_uri())
        assert page.locator("#scenarios-btn").is_hidden()
        footer = " ".join(page.locator("footer").inner_text().split())
        assert "against each agency's supplies" in footer and "synthetic" not in footer.lower()
        for route in ("#/", f"#/agency/{ea.AGENCY}", DS_PATH):
            page.goto(built_page.as_uri() + route)
            assert page.locator("#view h2").count() >= 1, route
            assert _scenario_words(page) == [], route
        page.goto(built_page.as_uri() + DS_PATH)
        column = page.evaluate("() => { const ctx = resolveContext(STATE); "
                               "return ctx.ds.columns[0] && columnKey(ctx.ds.columns[0]); }")
        assert column, "the dataset has no column to open"
        page.goto(built_page.as_uri() + f"{DS_PATH}/column/{column}")
        assert _scenario_words(page) == []

    @pytest.mark.parametrize("address, param", [
        ("#/scenarios", None), ("?panel=scenarios" + DS_PATH, "panel"),
        ("?scenario=ts-1" + DS_PATH, "scenario")], ids=["route", "panel", "scenario"])
    def test_an_old_scenario_address_is_not_found(self, page, built_page, address, param):
        page.goto(built_page.as_uri() + address)
        assert page.locator("#view h2").first.inner_text() == "Page not found"
        assert page.title().startswith("Page not found")
        assert page.locator("#route-announcer").inner_text() == "Page not found"
        if param:
            assert f"{param}=" not in page.evaluate("location.search")
            page.reload()
            assert page.locator("#view h2").first.inner_text() != "Page not found"

    def test_the_same_page_with_a_map_shows_the_button_the_tab_and_a_working_jump(
            self, page, built_page, tmp_path):
        entry = {"id": "TS-1", "mode": "INJECT", "title": "A placed scenario",
                 "section": "Fixture", "demonstrates": "It lands on the dataset.",
                 "breaksAs": None, "config": None, "requirements": [],
                 "coordinates": {"dataset": ea.DATASET, "supplies": [], "period": "",
                                 "inPlaceOn": "2026-01-02", "subject": "verdict-line"}}
        html = built_page.read_text().replace(
            "const SCENARIO_MAP = [];", f"const SCENARIO_MAP = {json.dumps([entry])};", 1)
        with_map = built_page.with_name("with-map.html")
        with_map.write_text(html)
        page.goto(with_map.as_uri())
        assert page.locator("#scenarios-btn").is_visible()
        page.locator("#scenarios-btn").click()
        assert page.locator("#view h2").first.inner_text() == "Scenarios"
        page.locator("[data-scenario]").first.click()
        assert ea.DATASET in page.evaluate("location.hash")
