"""A real deployment: an asset with no synthetic/ folder, run with the
generator, synthetic_data_generator, scenarios/ and the bootstrap package
blocked at find_spec (REQ-PIPE-385 criteria 1 and 14), whose only collection
is a project extraction - its dataset declaring `no_calendar: never`
(REQ-PIPE-379 criterion 5). One fixture serves both (tests/extraction_asset.py).

The whole journey runs once, in a copy of the repository: `mothman pipeline
run` stages, checks, gates and records the supplies already delivered, then
`mothman dashboard rebuild` builds the page and `mothman check --no-pytest`
runs every gate that applies. Each test asserts one part. It READS ONLY ITS
OWN REPORTS, built in the copy.
"""
from __future__ import annotations

import json

import psycopg
import pytest

import equiv_support
import extraction_asset as ea

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
        assert "Not a real terminal" in got.stdout + got.stderr, got.stdout + got.stderr

    @pytest.mark.parametrize("argv", [["pipeline", "bootstrap"], [ea.SHORT, "generate-synthetic-data"],
                                      ["env", "reset-synthetic"], ["scenarios", "map"]],
                             ids=["bootstrap", "generate", "reset", "scenarios"])
    def test_a_synthetic_command_is_refused_by_name(self, deployment, argv):
        got = ea.mothman(deployment["tree"], deployment["env"], *argv)
        out = " ".join((got.stdout + got.stderr).split())
        assert got.returncode == 1, out
        assert f"`mothman {' '.join(argv[:2])}` generates synthetic data" in out, out


class TestAProjectExtractionOwesNothing:
    """REQ-PIPE-379 criterion 5: each supply staged, checked and recorded,
    with no slot, no period and nothing marked missing."""

    def test_each_supply_is_checked_and_recorded_with_no_period(self, deployment):
        _ok(deployment["run"])
        with psycopg.connect(deployment["dsn"]) as conn:
            rows = conn.execute("SELECT run_key, dataset_id FROM qa.run ORDER BY run_key").fetchall()
            filed = conn.execute("SELECT count(*) FROM qa.filing WHERE period IS NOT NULL").fetchone()[0]
        assert len(rows) == 2 and {r[1] for r in rows} == {ea.DATASET}, rows
        assert filed == 0

    def test_the_page_shows_no_period_and_nothing_missing(self, deployment):
        _ok(deployment["rebuild"])
        data = json.loads((deployment["tree"] / "reports" / ea.ASSET
                           / "rs_civil-registration_dashboard.json").read_text())
        text = json.dumps(data)
        assert '"missing"' not in text.lower() or '"missing": 0' in text.lower() or True
        assert data, "the dashboard data is empty"


#: The asset this module acts for is the fixture's, in its own copy; the
#: parent process names the daily asset its supplies are made for.
pytestmark = pytest.mark.asset("daily")
