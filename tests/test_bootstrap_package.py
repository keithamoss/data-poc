"""The bootstrap and replay machinery is a package of its own outside
qa_tools/, synthetic-only, reaching the generator through its one public
module and never cli/, and the real pipeline needs nothing of it (REQ-GEN-381,
signed by Keith 2026-11-14)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parent.parent

#: Criterion 1's modules, each now under bootstrap/ and none left in qa_tools/.
MOVED = ("bootstrap", "checkpoints", "replay_inputs", "target_agreement", "synthetic_reset",
         "scripted_corrections", "correction_replay", "replay_clock")


class TestOnePackageOutsideQaTools:
    """Criterion 1."""

    @pytest.mark.parametrize("name", MOVED)
    def test_each_module_is_in_bootstrap_and_not_in_qa_tools(self, name):
        assert (ROOT / "bootstrap" / f"{name}.py").is_file()
        assert not (ROOT / "qa_tools" / "common" / f"{name}.py").exists()

    def test_the_player_half_moved_and_the_reader_half_stayed(self):
        from bootstrap import decision_player
        from qa_tools.common import scripted_decisions

        assert hasattr(decision_player, "Player") and hasattr(decision_player, "StreamPlayer")
        assert not hasattr(scripted_decisions, "Player")
        assert hasattr(scripted_decisions, "load") and hasattr(scripted_decisions, "Script")


class TestTheBootstrapIsSyntheticOnly:
    """Criterion 2."""

    def test_refused_on_a_real_asset_before_anything_is_generated(self, monkeypatch):
        from asset_model import asset_time, assets
        from bootstrap import bootstrap as boot
        from bootstrap import generation

        generated = []
        monkeypatch.setattr(asset_time, "declared_synthetic", lambda: False)
        monkeypatch.setattr(generation, "generate_collection",
                            lambda *a, **k: generated.append(a))
        result = boot.bootstrap(force=True)
        assert result.refused and not result.populated and generated == []
        flat = " ".join(result.reason.split())
        assert assets.selected().name in flat
        assert f"{assets.config_dir()}/data-asset.yaml" in flat
        assert "nothing was generated" in flat
        assert "`mothman pipeline run`" in flat

    def test_the_command_refuses_with_it(self, monkeypatch):
        from asset_model import asset_time
        from cli import pipeline as pipeline_cli

        monkeypatch.setattr(asset_time, "declared_synthetic", lambda: False)
        got = CliRunner().invoke(pipeline_cli.pipeline_group, ["bootstrap"])
        assert got.exit_code == 1, got.output
        assert "is not declared synthetic" in " ".join(got.output.split())

    def test_there_is_no_wall_clock_branch_to_replay_on(self, monkeypatch):
        from asset_model import asset_time
        from bootstrap import replay_clock

        monkeypatch.setattr(asset_time, "declared_synthetic", lambda: False)
        with pytest.raises(asset_time.ClockInstallRefused):
            with replay_clock.replaying():
                pass


class TestPipelineRunNeedsNothingOfIt:
    """Criterion 5: streams and the history refusal are the pipeline's."""

    def test_pipeline_run_runs_with_the_bootstrap_package_absent(self, monkeypatch):
        from cli import dashboard as dashboard_cli
        from cli import pipeline as pipeline_cli
        from dashboard import snapshot_dashboard
        from qa_tools.common import streams
        from qa_tools.tools import orchestrate

        for name in [m for m in sys.modules if m == "bootstrap" or m.startswith("bootstrap.")]:
            monkeypatch.setitem(sys.modules, name, None)
        monkeypatch.setitem(sys.modules, "bootstrap", None)
        ran = []
        monkeypatch.setattr(streams, "holds_history", lambda conn: False)
        monkeypatch.setattr(orchestrate, "run_stream", lambda ids, **k: ran.extend(ids))
        monkeypatch.setattr(dashboard_cli, "_build_data", lambda: None)
        monkeypatch.setattr(dashboard_cli, "_embed", lambda: None)
        monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda: [])
        got = CliRunner().invoke(pipeline_cli.pipeline_group, ["run"])
        assert got.exit_code == 0, (got.output, got.exception)
        assert ran, "nothing was run - this would prove nothing"

    def test_the_knock_on_asks_the_pipelines_streams(self, monkeypatch):
        from qa_tools.common import knock_on, streams

        asked = []
        monkeypatch.setattr(streams, "streams", lambda names: asked.append(names) or [names])
        monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])
        knock_on.follow_up_stream("child-protection")
        assert asked


class TestTheGeneratorThroughItsPublicModule:
    """Criterion 3: the 7 reaches into cli.pipeline are gone."""

    def test_no_bootstrap_module_names_cli(self):
        """An architecture rule (rule 1's exception): the imports gate holds it
        repository-wide; this names the files."""
        import re

        statement = re.compile(r"^\s*(from cli\b|import cli\b)", re.M)
        found = [p.name for p in (ROOT / "bootstrap").glob("*.py")
                 if statement.search(p.read_text())]
        assert list((ROOT / "bootstrap").glob("*.py"))
        assert found == []

    def test_generation_runs_the_trial_the_caller_hands_in(self, monkeypatch):
        from bootstrap import generation
        from generator import public

        did = []
        monkeypatch.setattr(public, "require_generator", lambda cid: None)
        monkeypatch.setattr(public, "has_target_trial", lambda cid: True)
        monkeypatch.setattr(public, "generate", lambda cid: did.append(("generate", cid)))
        monkeypatch.setattr(public, "this_assets_scenarios", lambda: set())
        monkeypatch.setattr("qa_tools.common.scenario_map.write_map",
                            lambda **k: did.append("map"))
        generation.generate_collection("x", trial=True,
                                       try_targets=lambda cid: did.append(("trial", cid)))
        assert did == [("generate", "x"), ("trial", "x"), "map"]

    def test_a_trial_with_nothing_to_run_it_is_refused(self, monkeypatch):
        from bootstrap import generation
        from generator import public

        monkeypatch.setattr(public, "require_generator", lambda cid: None)
        monkeypatch.setattr(public, "has_target_trial", lambda cid: True)
        monkeypatch.setattr(public, "generate", lambda cid: pytest.fail("generated"))
        with pytest.raises(generation.TargetTrialUnavailable):
            generation.generate_collection("x", trial=True)


class TestTheCacheKeyFollowsTheCode:
    """Criterion 7."""

    def test_the_key_is_the_bumped_prefix(self):
        from bootstrap import replay_inputs

        assert replay_inputs.KEY_PREFIX == "bootstrap-v6-"
        assert replay_inputs.cache_key("quarterly").startswith("bootstrap-v6-")

    @pytest.mark.parametrize("package", ["bootstrap", "scenarios", "asset_model"])
    def test_a_change_to_a_moved_package_moves_the_key(self, package, monkeypatch):
        """A file under the package is an input, so editing it changes the
        cache key (post-build-review #361: this used to stop at 'is an
        input'). The edit is a changed content hash, as the test of an edited
        check file does in tests/test_replay_inputs.py."""
        from bootstrap import replay_inputs

        files = replay_inputs.input_files(replay_inputs.inputs("quarterly"))
        mine = sorted(f for f in files if f.startswith(f"{package}/"))
        assert mine, f"nothing under {package}/ is an input"
        before = replay_inputs.cache_key("quarterly")
        edited = dict(files, **{mine[0]: "edited"})
        monkeypatch.setattr(replay_inputs, "input_files", lambda patterns=None: dict(edited))
        assert replay_inputs.cache_key("quarterly") != before


#: The data asset this module's tests act for (C11, Keith 2026-11-02).
pytestmark = pytest.mark.asset("quarterly")
