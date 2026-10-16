"""The before-and-after equivalence harness (REQ-TEST-239, the lean
version Keith signed 2026-10-16).

Everything here drives the real command or the real module. The one thing
this file does not do is a full capture - that is a from-empty bootstrap,
about half an hour - so the self-check (criterion 5) is the on-demand test
at the bottom."""
from __future__ import annotations

import json
import os
import subprocess

import pytest
from click.testing import CliRunner

from cli.app import cli
from qa_tools.common import equivalence as eq

#: A real commit from before `mothman env mark` existed (cli/env.py arrived
#: in 0d071d6), so its "mark" stage fails for real.
BEFORE_ENV_MARK = "58791fc"

_runner = CliRunner()


def _baseline(label, *, commit="HEAD", harness=eq.HARNESS_VERSION, s1=None, s4=None,
              s5=None, s7=None, seconds=100.0):
    commit = subprocess.run(["git", "rev-parse", commit], capture_output=True, text=True,
                            check=True, cwd=eq.ROOT).stdout.strip()
    return {"harness": harness, "normaliser": eq.NORMALISER_VERSION, "label": label,
            "commit": commit, "bootstrap_seconds": seconds, "timings": {},
            "surfaces": {"S1": s1 or {"qa.run": {"columns": ["run_key"],
                                                 "rows": [[["\"r1\""], 1]]}},
                         "S4": s4 or {"data/deliveries/x.csv": "aa"},
                         "S5": s5 or {"results.json": {"a": 1}},
                         "S7": s7 or {"help: mothman": "Usage: mothman"}}}


@pytest.fixture
def baselines(tmp_path, monkeypatch):
    monkeypatch.setenv("MOTHMAN_EQUIV_DIR", str(tmp_path))

    def write(label, **kw):
        (tmp_path / f"{label}.json").write_text(json.dumps(_baseline(label, **kw)))
    return write


class TestCompare:
    """Criteria 2 and 3."""

    def test_equal_baselines_compare_equal_and_exit_zero(self, baselines):
        baselines("a")
        baselines("b")
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code == 0, result.output
        assert result.output.count("same") == 4

    def test_a_difference_is_named_by_surface_and_exits_non_zero(self, baselines):
        baselines("a")
        baselines("b", s4={"data/deliveries/x.csv": "bb"}, seconds=130.0)
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code == 1
        assert "S4 generated-files: DIFFERS" in result.output
        assert "differs: data/deliveries/x.csv" in result.output
        assert "S1 recorded-results: same" in result.output
        assert "difference +30s" in result.output

    def test_it_prints_both_commits_and_the_commits_between(self, baselines):
        baselines("a", commit="HEAD~2")
        baselines("b")
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert "commits between: 2" in result.output

    def test_s1_rows_only_on_one_side_are_shown(self, baselines):
        baselines("a")
        baselines("b", s1={"qa.run": {"columns": ["run_key"], "rows": [[["\"r2\""], 1]]}})
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code == 1
        assert "only in A: run_key=\"r1\"" in result.output
        assert "only in B: run_key=\"r2\"" in result.output

    def test_surfaces_by_name_or_code(self, baselines):
        baselines("a")
        baselines("b", s4={"data/deliveries/x.csv": "bb"})
        for sel in (["--surfaces", "S1", "--surfaces", "help-and-menus"],
                    ["--surfaces", "recorded-results"]):
            result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b", *sel])
            assert result.exit_code == 0, result.output
            assert "S4" not in result.output

    def test_an_unknown_surface_is_refused_naming_the_four(self, baselines):
        baselines("a")
        baselines("b")
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b",
                                      "--surfaces", "S6"])
        assert result.exit_code != 0
        assert "S7 (help-and-menus)" in result.output

    def test_different_harness_versions_are_refused_naming_both(self, baselines):
        baselines("a")
        baselines("b", harness=eq.HARNESS_VERSION + 1)
        result = _runner.invoke(cli, ["debug", "equivalence", "compare", "a", "b"])
        assert result.exit_code != 0
        assert f"a: {eq.HARNESS_VERSION}" in result.output
        assert f"b: {eq.HARNESS_VERSION + 1}" in result.output

    def test_help_lists_all_four_surfaces_by_name_and_code(self):
        result = _runner.invoke(cli, ["debug", "equivalence", "--help"])
        for code, name, _ in eq.SURFACES:
            assert code in result.output and name in result.output


class TestCaptureRefuses:
    """Criteria 10, 11, 13 and 14 - every refusal before any work."""

    def test_the_real_database(self, baselines, monkeypatch):
        import psycopg

        info = psycopg.conninfo.conninfo_to_dict(os.environ["MOTHMAN_SUPPLY_DSN"])
        dsn = psycopg.conninfo.make_conninfo(**{**info, "dbname": "equiv_same"})
        monkeypatch.setenv("MOTHMAN_SUPPLY_DSN", dsn)
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref", "HEAD",
                                      "--label", "same"])
        assert result.exit_code != 0
        words = " ".join(result.output.replace("│", " ").split())
        assert "never writes to the real database" in words

    def test_a_real_asset(self, baselines, monkeypatch):
        monkeypatch.setattr("qa_tools.common.synthetic_reset.is_synthetic", lambda: False)
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref", "HEAD",
                                      "--label", "x"])
        assert result.exit_code != 0
        assert "not declared synthetic" in result.output

    def test_an_existing_label_without_yes(self, baselines):
        baselines("taken")
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref", "HEAD",
                                      "--label", "taken"])
        assert result.exit_code != 0
        assert "--yes" in result.output

    def test_a_ref_that_is_not_a_commit(self, baselines):
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref",
                                      "no-such-ref", "--label", "x"])
        assert result.exit_code != 0
        assert "no commit 'no-such-ref'" in result.output


def test_a_failed_capture_names_its_stage_and_leaves_nothing(baselines, tmp_path):
    """Criteria 12 and 14, for real: a commit from before `env mark` fails at
    the mark stage, and then no baseline, no worktree and no database remain."""
    import psycopg

    result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref",
                                  BEFORE_ENV_MARK, "--label", "pytest-fails"])
    assert result.exit_code != 0
    assert "stage 'mark'" in result.output
    assert not list(tmp_path.glob("pytest-fails*"))
    worktrees = subprocess.run(["git", "worktree", "list"], capture_output=True, text=True,
                               cwd=eq.ROOT).stdout
    assert "equiv-pytest-fails" not in worktrees
    admin, _scratch, name = eq._scratch_dsn("pytest-fails")
    with psycopg.connect(admin) as conn:
        assert not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                [name]).fetchall()


class TestTheSurfacesReadTheTree:
    def test_generated_files_hash_every_generated_file(self, tmp_path):
        (tmp_path / "data" / "deliveries" / "d1").mkdir(parents=True)
        (tmp_path / "data" / "deliveries" / "d1" / "a.csv").write_text("x")
        (tmp_path / "data" / "receipts").mkdir()
        (tmp_path / "data" / "receipts" / "r.json").write_text("{}")
        (tmp_path / "data" / "generator_bookkeeping.json").write_text("{}")
        got = eq.generated_files(tmp_path)
        assert set(got) == {"data/deliveries/d1/a.csv", "data/receipts/r.json",
                            "data/generator_bookkeeping.json"}

    def test_reports_drop_only_generated_at(self, tmp_path):
        (tmp_path / "reports").mkdir()
        (tmp_path / "reports" / "x.json").write_text(json.dumps(
            {"generated_at": "now", "datasets": [{"generated_at": "now", "id": "a"}]}))
        assert eq.reports(tmp_path) == {"x.json": {"datasets": [{"id": "a"}]}}

    def test_the_bootstraps_own_timings_line_is_read(self):
        out = "x\nTook Birth Registrations 593s, Child Protection 1642s\n"
        assert eq._timings(out) == {"Birth Registrations": 593.0, "Child Protection": 1642.0}


@pytest.mark.on_demand
def test_two_captures_of_one_commit_compare_equal(baselines):
    """Criterion 5, THE SELF-CHECK: the normaliser is quiet. Two full
    bootstraps - about an hour."""
    for label in ("self-check-a", "self-check-b"):
        result = _runner.invoke(cli, ["debug", "equivalence", "capture", "--ref", "HEAD",
                                      "--label", label, "--yes"])
        assert result.exit_code == 0, result.output
    result = _runner.invoke(cli, ["debug", "equivalence", "compare", "self-check-a",
                                  "self-check-b"])
    assert result.exit_code == 0, result.output
