"""Tests for cli/pipeline.py - `mothman pipeline run`, the real
replacement for the retired run_pipeline.sh (plans/tooling.md #1 Phase
4). This is the real gap Phase 4's own original plan text got wrong:
orchestrate_bdm.py's/orchestrate_cp.py's own run_pipeline()/
run_pipeline_cp() batch-mode functions (as opposed to run_single(),
already wrapped by `mothman bdm/cp qa`) had no mothman command until
this one. Every real call here is monkeypatched - run_pipeline()/
run_pipeline_cp() write real, permanent qa_results/ history as a side
effect (same as any other real pipeline run) and must never run for
real under pytest."""
from __future__ import annotations

from click.testing import CliRunner

import cli.pipeline as pipeline_cli

_runner = CliRunner()


def _patch_dashboard_build_embed(monkeypatch, calls):
    from cli import dashboard as dashboard_cli
    monkeypatch.setattr(dashboard_cli, "_build_data", lambda: calls.append("build-data"))
    monkeypatch.setattr(dashboard_cli, "_embed", lambda: calls.append("embed"))


def _patch_snapshot(monkeypatch, calls):
    import dashboard.snapshot_dashboard as snapshot_dashboard
    monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda: calls.append("sync") or [])
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda: calls.append("snapshot") or "/fake.html.gz")


def test_run_default_dataset_runs_both_bdm_and_cp(monkeypatch):
    from cli import bdm, cp
    import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
    import qa_tools.cp.orchestrate_cp as orchestrate_cp

    calls = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: calls.append("bdm-generate"))
    monkeypatch.setattr(orchestrate_bdm, "run_pipeline",
                         lambda sequential=False: calls.append(("bdm-run", sequential)))
    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: calls.append("cp-generate"))
    monkeypatch.setattr(orchestrate_cp, "run_pipeline_cp",
                         lambda sequential=False: calls.append(("cp-run", sequential)))
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run"])

    assert result.exit_code == 0, result.output
    assert calls == [
        "bdm-generate", ("bdm-run", False),
        "cp-generate", ("cp-run", False),
        "build-data", "embed", "sync",
    ]


def test_run_dataset_bdm_only_never_touches_cp(monkeypatch):
    from cli import bdm, cp
    import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm

    calls = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: calls.append("bdm-generate"))
    monkeypatch.setattr(orchestrate_bdm, "run_pipeline", lambda sequential=False: calls.append("bdm-run"))

    def _fail_if_called():
        raise AssertionError("--dataset bdm must not touch Child Protection")
    monkeypatch.setattr(cp, "generate_synthetic_data", _fail_if_called)
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run", "--collection", "bdm"])

    assert result.exit_code == 0, result.output
    assert calls == ["bdm-generate", "bdm-run", "build-data", "embed", "sync"]


def test_run_dataset_cp_only_never_touches_bdm(monkeypatch):
    from cli import bdm, cp
    import qa_tools.cp.orchestrate_cp as orchestrate_cp

    calls = []

    def _fail_if_called():
        raise AssertionError("--dataset cp must not touch Birth Registrations")
    monkeypatch.setattr(bdm, "generate_synthetic_data", _fail_if_called)

    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: calls.append("cp-generate"))
    monkeypatch.setattr(orchestrate_cp, "run_pipeline_cp", lambda sequential=False: calls.append("cp-run"))
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run", "--collection", "cp"])

    assert result.exit_code == 0, result.output
    assert calls == ["cp-generate", "cp-run", "build-data", "embed", "sync"]


def test_run_sequential_flag_forwards_to_both_orchestrators(monkeypatch):
    from cli import bdm, cp
    import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
    import qa_tools.cp.orchestrate_cp as orchestrate_cp

    seen = {}
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: None)
    monkeypatch.setattr(orchestrate_bdm, "run_pipeline", lambda sequential=False: seen.__setitem__("bdm", sequential))
    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: None)
    monkeypatch.setattr(orchestrate_cp, "run_pipeline_cp", lambda sequential=False: seen.__setitem__("cp", sequential))
    _patch_dashboard_build_embed(monkeypatch, [])
    _patch_snapshot(monkeypatch, [])

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run", "--sequential"])

    assert result.exit_code == 0, result.output
    assert seen == {"bdm": True, "cp": True}


def test_run_snapshot_flag_takes_a_real_snapshot(monkeypatch):
    from cli import bdm, cp
    import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
    import qa_tools.cp.orchestrate_cp as orchestrate_cp

    calls = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: None)
    monkeypatch.setattr(orchestrate_bdm, "run_pipeline", lambda sequential=False: None)
    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: None)
    monkeypatch.setattr(orchestrate_cp, "run_pipeline_cp", lambda sequential=False: None)
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run", "--snapshot"])

    assert result.exit_code == 0, result.output
    assert "sync" in calls
    assert "snapshot" in calls
    assert "Dashboard snapshot written" in result.output


def test_run_without_snapshot_flag_only_syncs_local_copies(monkeypatch):
    from cli import bdm, cp
    import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
    import qa_tools.cp.orchestrate_cp as orchestrate_cp

    calls = []
    monkeypatch.setattr(bdm, "generate_synthetic_data", lambda: None)
    monkeypatch.setattr(orchestrate_bdm, "run_pipeline", lambda sequential=False: None)
    monkeypatch.setattr(cp, "generate_synthetic_data", lambda: None)
    monkeypatch.setattr(orchestrate_cp, "run_pipeline_cp", lambda sequential=False: None)
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run"])

    assert result.exit_code == 0, result.output
    assert calls[-1] == "sync"
    assert "snapshot" not in calls
