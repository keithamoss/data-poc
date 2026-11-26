"""Tests for cli/pipeline.py - `mothman pipeline run`, the real
replacement for the retired run_pipeline.sh (plans/tooling.md #1 Phase
4). Every real call here is monkeypatched - the batch writes real,
permanent QA history as a side effect (same as any other real pipeline
run) and must never run for real under pytest.

THE REAL PATH ON EVERY ASSET (CLI A, SETTLED by Keith 2026-11-14;
REQ-PIPE-385 criterion 4; REQ-PIPE-383 criteria 5 and 6): `pipeline run`
generates nothing, plays no scripted decision, compares no targets and
confirms no correction - it processes what has arrived, by stream, and builds
the dashboard. A replayed history is `mothman pipeline bootstrap`'s."""
from __future__ import annotations

from state_paths import fixed
import pytest
from click.testing import CliRunner

import cli.pipeline as pipeline_cli
from asset_model import collections
from qa_tools.common import streams
from qa_tools.tools import orchestrate

_runner = CliRunner()


class _Shorts:
    """Collection id -> short, for the asset the test runs under (read when
    asked, so a test of either asset gets its own - the asset split)."""

    def __getitem__(self, collection_id):
        return {c.id: c.short for c in collections.all_collections()}[collection_id]


_SHORT = _Shorts()


def _others(short):
    """Every other collection the selected asset holds, by short."""
    return [c.short for c in collections.all_collections() if c.short != short]


@pytest.fixture(autouse=True)
def _nothing_synthetic_is_reached(monkeypatch):
    """CLI A: generating, comparing targets and confirming corrections are the
    bootstrap's alone, so any of them reached by `pipeline run` fails the test."""
    from bootstrap import bootstrap as boot
    from bootstrap import correction_replay
    from cli.collection_cli import of as _cli_of

    def _never(what):
        def fail(*_a, **_k):
            raise AssertionError(f"`pipeline run` reached {what} - CLI A says it never does")
        return fail
    for c in collections.all_collections():
        monkeypatch.setattr(_cli_of(c.short), "generate_synthetic_data", _never("generation"))
    monkeypatch.setattr("generator.driver.generate", _never("the generator"))
    monkeypatch.setattr(boot, "targets_agree", _never("the target comparison"))
    monkeypatch.setattr(correction_replay, "confirm_due", _never("correction confirmation"))


@pytest.fixture(autouse=True)
def _a_stream_goes_through_the_stubbed_run_pipeline(monkeypatch):
    """A STREAM (REQ-PIPE-262) runs each of its collections through whatever
    run_pipeline the test stubbed, unless the test stubs run_stream itself -
    so a test that stubs only run_pipeline never reaches the real tools."""
    monkeypatch.setattr(orchestrate, "run_stream",
                        lambda collection_ids, sequential=False, **_: [
                            orchestrate.run_pipeline(c, sequential=sequential)
                            for c in collection_ids])


@pytest.fixture(autouse=True)
def _no_history_yet(monkeypatch):
    """These tests stub the real work, on a worker database other modules
    have already written history into - so `pipeline run` would refuse
    (REQ-PIPE-144 criterion 39). They are about what a run DOES, so they
    run as though on an empty database; the refusal has its own tests."""
    monkeypatch.setattr(streams, "holds_history", lambda conn: False)


class TestARunIsTheRealPath:
    """CLI A and REQ-PIPE-383 criteria 5 and 6."""

    def _run(self, monkeypatch, *args):
        calls = []
        monkeypatch.setattr(orchestrate, "run_stream",
                            lambda ids, sequential=False, **k: calls.append(
                                ("+".join(_SHORT[c] for c in ids), k.get("player"))))
        _patch_dashboard_build_embed(monkeypatch, calls)
        _patch_snapshot(monkeypatch, calls)
        result = _runner.invoke(pipeline_cli.pipeline_group, ["run", *args])
        assert result.exit_code == 0, result.output
        return calls, result

    def test_it_generates_compares_and_confirms_nothing_and_passes_no_player(
            self, monkeypatch):
        calls, _ = self._run(monkeypatch)
        runs = [c for c in calls if isinstance(c, tuple)]
        assert runs and all(player is None for _key, player in runs), runs

    def test_on_a_synthetic_asset_it_says_it_played_no_scripted_decision(self, monkeypatch):
        from asset_model import asset_time

        assert asset_time.declared_synthetic(), "the suite's assets are synthetic"
        _calls, result = self._run(monkeypatch)
        flat = " ".join(result.output.split())
        assert ("Scripted decisions are played only by `mothman pipeline bootstrap` - "
                "this run played none.") in flat

    def test_on_a_real_asset_it_says_nothing_of_scripted_decisions(self, monkeypatch):
        from asset_model import asset_time

        monkeypatch.setattr(asset_time, "declared_synthetic", lambda: False)
        _calls, result = self._run(monkeypatch)
        assert "Scripted decisions" not in result.output

    def test_its_help_says_nothing_of_synthetic_data_manifests_or_targets(self):
        for args in (["run", "--help"], ["--help"]):
            got = _runner.invoke(pipeline_cli.pipeline_group, args)
            assert got.exit_code == 0, got.output
            if args == ["--help"]:
                # The group's own help lists every subcommand, the bootstrap's
                # among them; only its own description is held to CLI A.
                text = pipeline_cli.pipeline_group.help.lower()
            else:
                text = got.output.lower()
            for word in ("synthetic", "manifest", "regenerat", "target"):
                assert word not in text, (args, word)


class TestARunOverRecordedHistoryIsRefused:
    """REQ-PIPE-144 criterion 39."""

    def test_it_refuses_and_runs_nothing(self, monkeypatch):
        monkeypatch.setattr(streams, "holds_history", lambda conn: True)
        calls = []
        monkeypatch.setattr(orchestrate, "run_stream", lambda ids, **k: calls.append(ids))
        result = _runner.invoke(pipeline_cli.pipeline_group, ["run"])
        assert result.exit_code != 0 and calls == []
        flat = " ".join(result.output.split())
        assert "already holds QA history" in flat and "reset-synthetic" in flat


def _patch_dashboard_build_embed(monkeypatch, calls):
    from cli import dashboard as dashboard_cli
    monkeypatch.setattr(dashboard_cli, "_build_data", lambda: calls.append("build-data"))
    monkeypatch.setattr(dashboard_cli, "_embed", lambda: calls.append("embed"))


def _patch_snapshot(monkeypatch, calls):
    import dashboard.snapshot_dashboard as snapshot_dashboard
    monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda: calls.append("sync") or [])
    monkeypatch.setattr(snapshot_dashboard, "take_snapshot", lambda: calls.append("snapshot") or "/fake.html.gz")


def test_run_default_dataset_runs_every_stream(monkeypatch):
    """Every registered collection, by stream in hierarchy order - collections
    sharing a calendar run as ONE stream (REQ-PIPE-262)."""
    calls = []
    shorts = [c.short for c in collections.all_collections()]
    monkeypatch.setattr(orchestrate, "run_stream",
                        lambda collection_ids, sequential=False, **_:
                        calls.append(("+".join(_SHORT[c] for c in collection_ids) + "-run",
                                      sequential)))
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run"])

    assert result.exit_code == 0, result.output
    expected = [("+".join(group) + "-run", False) for group in streams.streams(shorts)]
    assert any(len(g) > 1 for g in streams.streams(shorts)), "no merged stream exercised"
    assert calls == [*expected, "build-data", "embed", "sync"]


@pytest.mark.asset("daily")
def test_run_dataset_bdm_only_never_touches_cp(monkeypatch):
    """--collection bdm runs Birth Registrations and nothing else its asset
    holds (the asset split: Child Protection is another asset's now)."""
    calls = []
    monkeypatch.setattr(orchestrate, "run_pipeline",
                        lambda collection_id, sequential=False:
                        calls.append(f"{_SHORT[collection_id]}-run"))
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run", "--collection", "bdm"])

    assert result.exit_code == 0, result.output
    assert calls == ["bdm-run", "build-data", "embed", "sync"]


def test_run_dataset_cp_only_never_touches_bdm(monkeypatch):
    """--collection cp runs Child Protection and nothing else its asset holds
    (the asset split: its siblings are Emergency Department and Linkage
    Products; Birth Registrations is another asset's)."""
    assert _others("cp"), "no sibling collection - this would prove nothing"
    calls = []
    monkeypatch.setattr(orchestrate, "run_pipeline",
                        lambda collection_id, sequential=False:
                        calls.append(f"{_SHORT[collection_id]}-run"))
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run", "--collection", "cp"])

    assert result.exit_code == 0, result.output
    assert calls == ["cp-run", "build-data", "embed", "sync"]


def test_run_sequential_flag_forwards_to_both_orchestrators(monkeypatch):

    seen = {}
    shorts = [c.short for c in collections.all_collections()]
    monkeypatch.setattr(orchestrate, "run_stream",
                        lambda collection_ids, sequential=False, **_:
                        seen.update({_SHORT[c]: sequential for c in collection_ids}))
    _patch_dashboard_build_embed(monkeypatch, [])
    _patch_snapshot(monkeypatch, [])

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run", "--sequential"])

    assert result.exit_code == 0, result.output
    assert seen == {short: True for short in shorts}


def test_run_snapshot_flag_takes_a_real_snapshot(monkeypatch):

    calls = []
    monkeypatch.setattr(orchestrate, "run_pipeline", lambda collection_id, sequential=False: None)
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run", "--snapshot"])

    assert result.exit_code == 0, result.output
    assert "sync" in calls
    assert "snapshot" in calls
    assert "Dashboard snapshot written" in result.output


def test_run_without_snapshot_flag_only_syncs_local_copies(monkeypatch):

    calls = []
    monkeypatch.setattr(orchestrate, "run_pipeline", lambda collection_id, sequential=False: None)
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run"])

    assert result.exit_code == 0, result.output
    assert calls[-1] == "sync"
    assert "snapshot" not in calls


def _log_one(conn, name):
    """One delivery record, by the shortest real route.

    Written through the module rather than as an INSERT, so these tests
    keep exercising the writer they are about rather than a hand-rolled
    copy of its schema.
    """
    from types import SimpleNamespace

    from asset_model import asset_time, delivery as delivery_tree
    from qa_tools.common import delivery_log

    return delivery_log.record(
        SimpleNamespace(name=name, files=[], anomalies=[],
                        received_at=asset_time.parse_instant(
                            "2026-01-01T09:00:00+08:00", name),
                        # Which clock stamped it (REQ-PIPE-105 criterion 4).
                        # OUR_CLOCK because this fixture is the one taking
                        # the instant, which is the weaker claim and the
                        # honest one.
                        received_from=delivery_tree.RECEIVED_FROM_OUR_CLOCK),
        SimpleNamespace(by_dataset={}, contested={}, collections=[]),
        conn=conn)


def test_running_the_pipeline_does_not_destroy_the_committed_delivery_log(
        monkeypatch, tmp_path, clean_delivery_log):
    """A real incident, 2026-09-25 - and, since REQ-PIPE-144 criterion 19,
    the stronger rule: a run deletes NO delivery record at all, even one
    whose files are no longer on disk (in production, every delivery's
    files move on).

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
    from qa_tools.common import delivery_log
    from asset_model import delivery as delivery_tree

    # A record for a delivery, straight into this worker's own database
    # - REQ-PIPE-089 made the delivery log a table, so there is no
    # directory to point anywhere and no file to hand-write.
    _log_one(clean_delivery_log, "monday")
    # Nothing on disk, so a delivery still recorded is one the prune
    # has every reason to think is gone - the worst case for the log.
    monkeypatch.setattr(delivery_tree, "default_deliveries_dir", fixed(tmp_path / "no-deliveries"))

    calls = []
    monkeypatch.setattr(orchestrate, "run_stream", lambda ids, **k: calls.extend(ids))
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run"])
    assert result.exit_code == 0, result.output

    # KEPT, though its files are gone: a delivery record is history.
    assert [r["delivery"] for r in delivery_log.records()] == ["monday"]


@pytest.mark.asset("quarterly")
def test_a_delivery_still_present_keeps_its_record_across_a_run(
        monkeypatch, tmp_path, clean_delivery_log):
    """The other half, and the one that actually guards the incident."""
    import cli.pipeline as pipeline_cli
    from qa_tools.common import delivery, delivery_log
    from asset_model import delivery as delivery_tree

    # A record for a delivery, straight into this worker's own database
    # - REQ-PIPE-089 made the delivery log a table, so there is no
    # directory to point anywhere and no file to hand-write.
    _log_one(clean_delivery_log, "monday")

    deliveries = tmp_path / "deliveries"
    (deliveries / "monday").mkdir(parents=True)
    (deliveries / "monday" / "cp_clients.csv").write_text("a\n1\n")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    # The `sequence` is not decoration: without it the arrival cannot
    # be placed in the processing order and read_delivery() refuses
    # (REQ-PIPE-061).
    delivery.write_receipts("monday", "2026-09-25T09:00:00+08:00", receipts,
                            files=["cp_clients.csv"], sequence=1)
    monkeypatch.setattr(delivery_tree, "default_deliveries_dir", fixed(deliveries))
    monkeypatch.setattr(delivery_tree, "default_receipts_dir", fixed(receipts))

    calls = []
    monkeypatch.setattr(orchestrate, "run_stream", lambda ids, **k: calls.extend(ids))
    _patch_dashboard_build_embed(monkeypatch, calls)
    _patch_snapshot(monkeypatch, calls)

    result = _runner.invoke(pipeline_cli.pipeline_group, ["run"])
    assert result.exit_code == 0, result.output
    assert [r["delivery"] for r in delivery_log.records()] == ["monday"], \
        "a run that rewrote nothing must not take the record with it"


def test_the_committed_history_trees_are_never_the_real_ones_in_a_test():
    """The guard in conftest, asserted rather than trusted.

    Six tests in this file invoke `pipeline run` without redirecting
    anything, and that command USED TO prune the delivery log against
    what was on disk (it deletes nothing since REQ-PIPE-144). On a freshly-cloned CI runner there is no `data/` at all,
    so the honest answer to "which deliveries are present" is NONE and
    every committed record would go. A test that merely passes is not
    evidence the tree survived, which is why this asserts the
    redirection itself.
    """
    from qa_tools.common import delivery_log, in_flight_log

    root = delivery_log.ROOT
    # Neither load_log nor delivery_log nor filing is here any more:
    # REQ-PIPE-089 moved the first two records into the database and
    # REQ-PIPE-104 the third. There is no tree of any of them left to
    # point anywhere, and a test writing one now writes to its own
    # worker's database, which cannot be the real one.
    #
    # ONE ENTRY LEFT, which is worth saying because a single-item loop
    # invites being flattened: `observations/in_flight/` is the last
    # committed tree a test can still write into, and the loop is what
    # this assertion will grow back through when another appears.
    for module, name in ((in_flight_log, "OBSERVATIONS_DIR"),):
        current = getattr(module, name)
        assert root not in current.parents and current != root, (
            f"{module.__name__}.{name} points into the real repo at {current} - a test "
            f"that writes there puts temporary names into permanent history, and a test "
            f"that prunes there deletes it")


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
