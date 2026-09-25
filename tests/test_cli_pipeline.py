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


def test_running_the_pipeline_does_not_destroy_the_committed_delivery_log(
        monkeypatch, tmp_path):
    """A real incident, 2026-09-25, and the reason criterion 6 is built
    as a prune rather than a wipe.

    `mothman pipeline run` used to clear the whole delivery log at the
    top, on the reasoning that the run would rewrite it. The tests
    above invoke exactly that command with the real work STUBBED OUT -
    so the next gate run deleted sixty committed records and nothing
    rewrote them, because the thing that would have was the part being
    stubbed.

    The general shape is worth more than the fix: a command that
    destroys committed state before recreating it is only correct when
    the recreation actually happens, and a test suite is precisely the
    place where it does not.
    """
    import cli.pipeline as pipeline_cli
    from qa_tools.common import delivery, delivery_log

    log_dir = tmp_path / "delivery_log"
    log_dir.mkdir()
    (log_dir / "monday.json").write_text('{"delivery": "monday", "files": []}')
    monkeypatch.setattr(delivery_log, "DELIVERY_LOG_DIR", log_dir)
    # Nothing on disk, so a delivery still recorded is one the prune
    # has every reason to think is gone - the worst case for the log.
    monkeypatch.setattr(delivery, "DELIVERIES_DIR", tmp_path / "no-deliveries")

    calls = []
    monkeypatch.setattr(pipeline_cli, "_run_bdm", lambda sequential: calls.append("bdm"))
    monkeypatch.setattr(pipeline_cli, "_run_cp", lambda sequential: calls.append("cp"))
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run"])
    assert result.exit_code == 0, result.output

    # The prune DOES remove it, because that delivery genuinely is not
    # there - what must never happen is the whole log going on a run
    # that rewrote nothing. Proven by pointing the deliveries at a real
    # tree instead:
    assert not (log_dir / "monday.json").exists()


def test_a_delivery_still_present_keeps_its_record_across_a_run(monkeypatch, tmp_path):
    """The other half, and the one that actually guards the incident."""
    import cli.pipeline as pipeline_cli
    from qa_tools.common import delivery, delivery_log

    log_dir = tmp_path / "delivery_log"
    log_dir.mkdir()
    (log_dir / "monday.json").write_text('{"delivery": "monday", "files": []}')
    monkeypatch.setattr(delivery_log, "DELIVERY_LOG_DIR", log_dir)

    deliveries = tmp_path / "deliveries"
    (deliveries / "monday").mkdir(parents=True)
    (deliveries / "monday" / "cp_clients.csv").write_text("a\n1\n")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    # The `sequence` is not decoration: without it the arrival cannot
    # be placed in the processing order and read_delivery() refuses
    # (REQ-PIPE-061).
    (receipts / "monday.json").write_text(
        '{"delivery": "monday", "received_at": "2026-09-25T09:00:00+08:00", "sequence": 1}')
    monkeypatch.setattr(delivery, "DELIVERIES_DIR", deliveries)
    monkeypatch.setattr(delivery, "RECEIPTS_DIR", receipts)

    calls = []
    monkeypatch.setattr(pipeline_cli, "_run_bdm", lambda sequential: calls.append("bdm"))
    monkeypatch.setattr(pipeline_cli, "_run_cp", lambda sequential: calls.append("cp"))
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run"])
    assert result.exit_code == 0, result.output
    assert (log_dir / "monday.json").exists(), \
        "a run that rewrote nothing must not take the record with it"


def test_the_committed_history_trees_are_never_the_real_ones_in_a_test():
    """The guard in conftest, asserted rather than trusted.

    Six tests in this file invoke `pipeline run` without redirecting
    anything, and that command prunes the delivery log against what is
    on disk. On a freshly-cloned CI runner there is no `data/` at all,
    so the honest answer to "which deliveries are present" is NONE and
    every committed record would go. A test that merely passes is not
    evidence the tree survived, which is why this asserts the
    redirection itself.
    """
    from qa_tools.common import delivery_log, in_flight_log, load_log

    root = delivery_log.ROOT
    for module, name in ((load_log, "PROCESSING_LOG_DIR"),
                          (delivery_log, "DELIVERY_LOG_DIR"),
                          (in_flight_log, "OBSERVATIONS_DIR")):
        current = getattr(module, name)
        assert root not in current.parents and current != root, (
            f"{module.__name__}.{name} points into the real repo at {current} - a test "
            f"that writes there puts temporary names into permanent history, and a test "
            f"that prunes there deletes it")
