"""Tests for cli/dashboard.py - the mothman CLI's dashboard rebuild chain
(plans/tooling.md #1 Phase 4). Each command does a lazy `from X import Y`
inside its own function body, so monkeypatching X's own attribute (not
cli.dashboard's) is what actually takes effect at call time - same
pattern as tests/test_cli_bdm.py's own real-tool-seam tests."""
from __future__ import annotations

from click.testing import CliRunner

import cli.dashboard as dashboard_cli

_runner = CliRunner()


def test_rebuild_results_calls_both_datasets_build_results_from_history(monkeypatch):
    import qa_tools.bdm.build_results_from_history as bdm_history
    import qa_tools.cp.build_results_from_history as cp_history

    called = []
    monkeypatch.setattr(bdm_history, "build_results_from_history", lambda: called.append("bdm"))
    monkeypatch.setattr(cp_history, "build_results_from_history", lambda: called.append("cp"))

    result = _runner.invoke(dashboard_cli.dashboard_group, ["rebuild-results"])

    assert result.exit_code == 0, result.output
    assert called == ["bdm", "cp"]


def test_build_data_writes_both_datasets_output(monkeypatch, tmp_path):
    import pipeline.build_dashboard_data as build_dashboard_data
    import pipeline.build_cp_dashboard_data as build_cp_dashboard_data

    bdm_out = tmp_path / "bdm.json"
    cp_out = tmp_path / "cp.json"
    monkeypatch.setattr(build_dashboard_data, "OUT_PATH", str(bdm_out))
    monkeypatch.setattr(build_dashboard_data, "build", lambda: {"dataset": "bdm"})
    monkeypatch.setattr(build_cp_dashboard_data, "OUT_PATH", str(cp_out))
    monkeypatch.setattr(build_cp_dashboard_data, "build", lambda: {"dataset": "cp"})

    result = _runner.invoke(dashboard_cli.dashboard_group, ["build-data"])

    assert result.exit_code == 0, result.output
    assert bdm_out.exists()
    assert cp_out.exists()


def test_embed_calls_the_real_embed_function(monkeypatch):
    import dashboard.embed_dashboard_data as embed_dashboard_data

    called = []
    monkeypatch.setattr(embed_dashboard_data, "embed", lambda: called.append(True))

    result = _runner.invoke(dashboard_cli.dashboard_group, ["embed"])

    assert result.exit_code == 0, result.output
    assert called == [True]


def test_validate_check_lifecycle_raises_click_exception_on_nonzero_exit(monkeypatch):
    import qa_tools.common.validate_check_lifecycle as validate_check_lifecycle

    monkeypatch.setattr(validate_check_lifecycle, "main", lambda: 1)

    result = _runner.invoke(dashboard_cli.dashboard_group, ["validate-check-lifecycle"])

    assert result.exit_code != 0
    assert "check-lifecycle validation failed" in result.output


def test_validate_check_lifecycle_succeeds_on_zero_exit(monkeypatch):
    import qa_tools.common.validate_check_lifecycle as validate_check_lifecycle

    monkeypatch.setattr(validate_check_lifecycle, "main", lambda: 0)

    result = _runner.invoke(dashboard_cli.dashboard_group, ["validate-check-lifecycle"])

    assert result.exit_code == 0, result.output


def test_validate_requirements_raises_click_exception_on_nonzero_exit(monkeypatch):
    import qa_tools.common.validate_requirements as validate_requirements

    monkeypatch.setattr(validate_requirements, "main", lambda: 1)

    result = _runner.invoke(dashboard_cli.dashboard_group, ["validate-requirements"])

    assert result.exit_code != 0
    assert "requirements validation failed" in result.output


def test_check_renders_raises_click_exception_on_nonzero_exit(monkeypatch):
    import dashboard.check_dashboard_renders as check_dashboard_renders

    monkeypatch.setattr(check_dashboard_renders, "main", lambda: 1)

    result = _runner.invoke(dashboard_cli.dashboard_group, ["check-renders"])

    assert result.exit_code != 0
    assert "dashboard render check failed" in result.output


def test_snapshot_default_syncs_local_copies_and_skips_taking_one(monkeypatch):
    import dashboard.snapshot_dashboard as snapshot_dashboard

    monkeypatch.delenv("SNAPSHOT_DASHBOARD", raising=False)
    monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda: ["a.html"])
    taken = []
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda: taken.append(True))

    result = _runner.invoke(dashboard_cli.dashboard_group, ["snapshot"])

    assert result.exit_code == 0, result.output
    assert taken == []
    assert "not set to 1" in result.output


def test_snapshot_env_flag_takes_a_snapshot(monkeypatch):
    import dashboard.snapshot_dashboard as snapshot_dashboard

    monkeypatch.setenv("SNAPSHOT_DASHBOARD", "1")
    monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda: [])
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda: "/fake/path.html.gz")

    result = _runner.invoke(dashboard_cli.dashboard_group, ["snapshot"])

    assert result.exit_code == 0, result.output
    assert "Dashboard snapshot written" in result.output


def test_snapshot_prepare_site_calls_prepare_deploy_site_and_skips_local_sync(monkeypatch, tmp_path):
    import dashboard.snapshot_dashboard as snapshot_dashboard

    called = []
    monkeypatch.setattr(snapshot_dashboard, "prepare_deploy_site", lambda site_dir: called.append(site_dir))

    def _fail_if_called():
        raise AssertionError("--prepare-site must not also sync local copies")
    monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", _fail_if_called)

    site_dir = str(tmp_path / "_site")
    result = _runner.invoke(dashboard_cli.dashboard_group, ["snapshot", "--prepare-site", site_dir])

    assert result.exit_code == 0, result.output
    assert len(called) == 1
    assert str(called[0]) == site_dir


def test_rebuild_chains_every_step_in_order_and_does_not_use_ctx_invoke(monkeypatch):
    """Regression coverage for the real ctx.invoke()+sys.exit() composition
    bug found while building this: chaining sub-commands via ctx.invoke()
    would abort the whole chain even on SUCCESS, since sys.exit(0) still
    raises SystemExit(0). rebuild_command must call the private _helper()
    functions directly instead."""
    calls = []
    monkeypatch.setattr(dashboard_cli, "_rebuild_results", lambda: calls.append("rebuild-results"))
    monkeypatch.setattr(dashboard_cli, "_build_data", lambda: calls.append("build-data"))
    monkeypatch.setattr(dashboard_cli, "_embed", lambda: calls.append("embed"))
    monkeypatch.setattr(dashboard_cli, "_validate_check_lifecycle", lambda: calls.append("validate-check-lifecycle"))
    monkeypatch.setattr(dashboard_cli, "_validate_requirements", lambda: calls.append("validate-requirements"))
    monkeypatch.setattr(dashboard_cli, "_check_renders", lambda: calls.append("check-renders"))

    result = _runner.invoke(dashboard_cli.dashboard_group, ["rebuild"])

    assert result.exit_code == 0, result.output
    assert calls == [
        "rebuild-results", "build-data", "embed",
        "validate-check-lifecycle", "validate-requirements", "check-renders",
    ]


def test_rebuild_stops_and_fails_when_a_gate_raises(monkeypatch):
    monkeypatch.setattr(dashboard_cli, "_rebuild_results", lambda: None)
    monkeypatch.setattr(dashboard_cli, "_build_data", lambda: None)
    monkeypatch.setattr(dashboard_cli, "_embed", lambda: None)

    import rich_click as click

    def _fail():
        raise click.ClickException("check-lifecycle validation failed - see output above.")
    monkeypatch.setattr(dashboard_cli, "_validate_check_lifecycle", _fail)

    def _fail_if_called():
        raise AssertionError("must not run steps after a failed gate")
    monkeypatch.setattr(dashboard_cli, "_validate_requirements", _fail_if_called)
    monkeypatch.setattr(dashboard_cli, "_check_renders", _fail_if_called)

    result = _runner.invoke(dashboard_cli.dashboard_group, ["rebuild"])

    assert result.exit_code != 0
    assert "check-lifecycle validation failed" in result.output
