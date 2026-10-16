"""REQ-GEN-186: a targeted supply's verdict is confirmed by the real tools.

Two comparisons (Keith, 2026-10-11): a TRIAL at generation for each
injected target, against its last lead-in, recording nothing (criteria 1,
2, 5); and, once a replay finishes, every targeted supply's RECORDED
verdict as the promotion gate reads it (criteria 3, 6). Both compare only
what a real tool produced (criterion 4).
"""
from __future__ import annotations

import dataclasses
import json

import pytest
from click.testing import CliRunner

from generator import targets
from qa_tools.common import target_agreement

DS = "birth-registrations"
PREFIX = "data-asset-1.registry-services.civil-registration.birth-registrations."


def _r(check: str, status: str, **extra) -> dict:
    return {"check_id": PREFIX + check, "dataset_id": DS, "status": status, **extra}


# ---- the comparison itself (criteria 2, 3, 4) ----

class TestComparing:

    def test_an_amber_that_warns_agrees(self):
        results = [_r("a.not_null_dbt", "pass"), _r("b.missing_percent_soda", "warn")]
        assert target_agreement.compare(DS, results, "amber", "TS-x", reads={}) is None

    def test_a_red_check_is_named_against_an_amber_target(self):
        results = [_r("a.not_null_dbt", "fail"), _r("b.missing_percent_soda", "warn")]
        found = target_agreement.compare(DS, results, "amber", "TS-x", reads={})
        assert found.verdict == "red" and found.checks == ("a.not_null_dbt red",)
        assert "TS-x" in str(found) and "built to amber" in str(found) and "read red" in str(found)

    def test_a_warning_is_named_against_a_green_target(self):
        found = target_agreement.compare(
            DS, [_r("a.not_null_dbt", "pass"), _r("b.missing_percent_soda", "warn")],
            "green", "lead-in", reads={})
        assert found.verdict == "amber" and found.checks == ("b.missing_percent_soda amber",)

    def test_an_amber_that_did_not_warn_names_the_rule_meant_to(self):
        results = [_r("place_of_birth_facility.not_null_dbt", "pass"), _r("sex.not_null_dbt", "pass")]
        found = target_agreement.compare(DS, results, "amber", "TS-43", reads={},
                                         rules=("place_of_birth_facility.completeness",))
        assert found.verdict == "green"
        assert found.checks == ("place_of_birth_facility.not_null_dbt green",)

    def test_a_gap_red_reads_as_its_measurement(self):
        """The gate's reading, not the page's (Keith, 2026-10-11): an ordinary
        amber after an unresolved red is not blamed for the gap."""
        results = [_r("a.missing_percent_soda", "warn"),
                   _r("row_count_growth_evidently", "fail", reference_gap=True,
                      measured_status="pass")]
        assert target_agreement.compare(DS, results, "amber", "amber", reads={}) is None

    def test_nothing_is_predicted(self):
        """Criterion 4: no results, no verdict - never a guess."""
        found = target_agreement.compare(DS, [], "green", "x", reads={})
        assert found.verdict is None and found.checks == ()


# ---- what the generator says it built (generator/targets.py) ----

def _book(tmp_path, bdm, cp=()):
    path = tmp_path / "book.json"
    path.write_text(json.dumps({"birth-registrations": bdm, "cp-clients": list(cp)}))
    return path


def _entry(period, delivery, at="14:30", severity=None):
    return {"run_id": delivery, "period": period, "delivery": delivery,
            "received_at": f"{period}T{at}:00+08:00", "dirty_severity": severity}


class TestWhatWasBuilt:

    def test_targets_lead_ins_and_ambers_in_both_collections(self, tmp_path):
        book = _book(tmp_path, [
            _entry("2026-08-20", "amb", severity="amber"),
            _entry("2026-09-03", "lead1"), _entry("2026-09-04", "lead2"),
            _entry("2026-09-05", "ts43", at="14:00"), _entry("2026-09-06", "after"),
            _entry("2026-09-07", "plain"),
        ], cp=[_entry("2024-Q1", "cpamb", severity="amber"), _entry("2024-Q2", "cpclean")])
        placed = tmp_path / "placed.json"
        placed.write_text(json.dumps({"placements": [{
            "scenario_id": "TS-43", "dataset": DS, "lead_in": ["2026-09-03", "2026-09-04"],
            "follow": ["2026-09-06"], "targets": [{"date": "2026-09-05", "at": "14:00",
                                                   "built_to": "amber",
                                                   "rules": ["place_of_birth_facility.completeness"]}]}]}))
        built = {b.delivery: b for b in targets.written(book, placed)}
        assert set(built) == {"amb", "lead1", "lead2", "ts43", "after", "cpamb"}
        assert built["ts43"].target == "amber" and built["ts43"].injected
        assert built["ts43"].reference == "lead2", "the LAST lead-in (REQ-GEN-185 c2)"
        assert built["ts43"].day == "2026-09-05"
        assert built["ts43"].rules == ("place_of_birth_facility.completeness",)
        assert {built[d].target for d in ("lead1", "lead2", "after")} == {"green"}
        assert not built["lead1"].injected
        assert built["amb"].target == "amber" and built["cpamb"].dataset_id == "cp-clients"

    def test_a_green_follow_with_no_target_is_still_compared(self, tmp_path):
        """#172 D1: a placement with no targets (TS-73's green_follow) skipped
        its green following day, so the day read RED on the page and nothing
        compared it with what it was built to."""
        book = _book(tmp_path, [_entry("2026-08-20", "pair", at="13:20"),
                                _entry("2026-08-21", "after")])
        placed = tmp_path / "placed.json"
        placed.write_text(json.dumps({"placements": [{
            "scenario_id": "TS-73", "dataset": DS, "lead_in": [],
            "follow": ["2026-08-21"], "targets": []}]}))
        built = {b.delivery: b for b in targets.written(book, placed)}
        assert set(built) == {"after"}
        assert built["after"].target == "green" and not built["after"].injected

    def test_a_record_the_placement_does_not_match_is_refused(self, tmp_path):
        book = _book(tmp_path, [_entry("2026-09-04", "lead2")])
        placed = tmp_path / "placed.json"
        placed.write_text(json.dumps({"placements": [{
            "scenario_id": "TS-43", "dataset": DS, "lead_in": ["2026-09-04"], "follow": [],
            "targets": [{"date": "2026-09-05", "at": "14:00", "built_to": "amber"}]}]}))
        with pytest.raises(ValueError, match="TS-43.*2026-09-05 14:00"):
            targets.written(book, placed)

    def test_nothing_generated_is_nothing_built(self, tmp_path):
        assert targets.written(tmp_path / "absent.json", tmp_path / "absent2.json") == []


# ---- the generation-time trial (criteria 1, 2, 5) ----

@pytest.fixture
def generated(tmp_path):
    """The real Birth Registrations generator, everything under tmp_path."""
    import generator_isolation
    from generator import generate_runs

    undo = generator_isolation.redirect(generate_runs, tmp_path)
    try:
        generate_runs.main()
        yield tmp_path
    finally:
        undo()


def _only_ts43(monkeypatch, built_to=None):
    real = targets.written

    def ts43(*a, **k):
        out = [b for b in real(*a, **k) if b.injected and b.scenario == "TS-43"]
        return [dataclasses.replace(b, target=built_to) for b in out] if built_to else out
    monkeypatch.setattr(targets, "written", ts43)


class TestTheTrialAtGeneration:
    """Through the real trial path, one target - about nine seconds each."""

    def test_a_target_the_tools_agree_with_passes_and_records_nothing(self, generated,
                                                                       monkeypatch):
        from cli import bdm
        from qa_tools.common import supply_db

        from qa_tools.common import qa_store

        _only_ts43(monkeypatch)
        with supply_db.connect() as conn:
            supply_db.ensure_schemas(conn)
            qa_store.ensure_schema(conn)
            before = conn.execute("SELECT count(*) FROM qa.run").fetchall()
        assert bdm.try_targets(say=lambda _m: None) == 1
        with supply_db.connect() as conn:
            assert conn.execute("SELECT count(*) FROM qa.run").fetchall() == before
        assert any((generated / "deliveries").iterdir()), "an agreeing trial removes nothing"

    def test_a_disagreement_fails_naming_it_and_removes_the_history(self, generated,
                                                                     monkeypatch):
        from cli import bdm

        _only_ts43(monkeypatch, built_to="green")  # it was built amber
        with pytest.raises(bdm.TargetTrialFailed) as raised:
            bdm.try_targets(say=lambda _m: None)
        message = raised.value.message
        assert "TS-43" in message and "built to green" in message and "read amber" in message
        assert "place_of_birth_facility" in message
        assert not any((generated / "deliveries").iterdir()), "criterion 2: not emitted"

    def test_no_lead_in_is_a_disagreement_not_a_crash(self, monkeypatch):
        from cli import bdm
        from generator import generate_runs

        lonely = targets.Built("TS-z's arrival", DS, "d", "amber", injected=True)
        monkeypatch.setattr(targets, "just_written", lambda: ([lonely], None))
        monkeypatch.setattr(generate_runs, "_previous_delivery_names", lambda: [])
        with pytest.raises(bdm.TargetTrialFailed, match="no lead-in"):
            bdm.try_targets(say=lambda _m: None)


class TestSkippingTheTrial:
    """Criterion 5: an explicit flag, said in the output."""

    def test_the_generate_command_says_it_skipped(self, monkeypatch):
        from cli import bdm
        from generator import generate_runs
        from qa_tools.common import scenario_map

        monkeypatch.setattr(generate_runs, "main", lambda: None)
        monkeypatch.setattr(scenario_map, "write_map", lambda: None)
        monkeypatch.setattr(bdm, "manifest_exists", lambda: False)
        monkeypatch.setattr(bdm, "try_targets", lambda **k: pytest.fail("the trial ran"))
        out = CliRunner().invoke(bdm.generate_synthetic_data_command, ["--skip-target-trial"])
        assert out.exit_code == 0, out.output
        assert "Target trial skipped" in out.output and "still runs" in out.output

    def test_by_default_the_trial_runs(self, monkeypatch):
        from cli import bdm
        from generator import generate_runs
        from qa_tools.common import scenario_map

        ran = []
        monkeypatch.setattr(generate_runs, "main", lambda: None)
        monkeypatch.setattr(scenario_map, "write_map", lambda: None)
        monkeypatch.setattr(bdm, "try_targets", lambda **k: ran.append(True))
        bdm.generate_synthetic_data()
        assert ran == [True]

    def test_the_bootstrap_flag_reaches_both_generators(self, monkeypatch):
        from qa_tools.common import bootstrap as boot

        seen = []
        monkeypatch.setattr("cli.bdm.generate_synthetic_data", lambda **k: seen.append(k))
        monkeypatch.setattr("cli.cp.generate_synthetic_data", lambda **k: seen.append(k))
        monkeypatch.setattr(boot, "_run_collection", lambda *a, **k: 0.0)
        monkeypatch.setattr(boot, "_record_deliveries", lambda: None)
        monkeypatch.setattr(boot, "_confirm_corrections", lambda say: None)
        monkeypatch.setattr(boot, "staged_table_count", lambda conn: 0)
        monkeypatch.setattr(boot, "holds_history", lambda conn: False)
        monkeypatch.setattr(boot, "targets_agree", lambda names: ())
        boot.bootstrap(sequential=True, skip_target_trial=True)
        assert seen == [{"trial": False}, {"trial": False}]


# ---- after a replay (criteria 3, 6) ----

class TestAfterAReplay:

    def test_a_disagreement_fails_the_bootstrap_naming_it(self, monkeypatch):
        from cli import pipeline
        from qa_tools.common import bootstrap as boot

        result = boot.BootstrapResult(populated=True, staged_before=0, staged_after=3,
                                      disagreements=("the ordinary amber for 2026-08-28 "
                                                     "(birth-registrations) was built to amber "
                                                     "and the real tools read red - x red",))
        monkeypatch.setattr(boot, "bootstrap", lambda **k: result)
        out = CliRunner().invoke(pipeline.bootstrap_command, [], env={"COLUMNS": "400"})
        said = " ".join(out.output.split())
        assert out.exit_code != 0
        assert "2026-08-28" in said and "nothing recorded was changed" in said

    def test_a_supply_with_nothing_recorded_is_a_disagreement(self):
        from qa_tools.common import supply_db

        missing = targets.Built("TS-z's arrival", DS, "no-such-delivery", "amber")
        with supply_db.connect() as conn:
            supply_db.ensure_schemas(conn)
            from qa_tools.common import qa_store
            qa_store.ensure_schema(conn)
            [found] = target_agreement.after_replay(conn, [missing])
        assert found.verdict is None and "nothing recorded" in found.checks[0]

    def test_every_targeted_supply_in_the_deployment_agrees_and_nothing_changes(
            self, deployment_history):
        """The real corpus: injected targets, lead-ins and following days, and
        every ordinary amber in both collections. Reading changes nothing
        (criterion 6)."""
        from cli.pipeline import generated_targets
        from qa_tools.common import supply_db

        built = generated_targets()
        if not built:
            pytest.skip("this checkout has no generated history")
        counted = ("decision", "filing", "check_result", "run")
        with supply_db.connect() as conn:
            before = {t: conn.execute(f"SELECT count(*) FROM qa.{t}").fetchall() for t in counted}
            found = target_agreement.after_replay(conn, built)
            after = {t: conn.execute(f"SELECT count(*) FROM qa.{t}").fetchall() for t in counted}
        assert [str(d) for d in found] == []
        assert before == after
        assert {b.dataset_id for b in built} == {DS, "cp-clients"}
        assert any(b.injected for b in built) and any(b.target == "green" for b in built)


class TestEveryBootstrapCallerFailsOnADisagreement:
    """Post-build-review #157 finding 1: the TUI's bootstrap menu printed
    "Ready" in green over a history where a supply read wrong."""

    def test_the_tui_menu_says_so_rather_than_ready(self, monkeypatch, capsys):
        from cli import app, common
        from qa_tools.common import bootstrap as boot

        result = boot.BootstrapResult(populated=True, staged_before=0, staged_after=3,
                                      disagreements=("TS-43's 2026-09-05 14:00 arrival "
                                                     "(birth-registrations) was built to "
                                                     "amber and the real tools read red",))
        monkeypatch.setattr(boot, "bootstrap", lambda **k: result)
        monkeypatch.setattr(common, "confirm", lambda *a, **k: True)
        app.console.width = 400
        app._bootstrap_menu()
        said = " ".join(capsys.readouterr().out.split())
        assert "Ready" not in said
        assert "did not read as built" in said and "TS-43" in said


class TestAResumeLeavesTheCallersDatabaseAlone:
    """Post-build-review #157 finding 3: a resume regenerated - running the
    trial - before switching to its own database, so the trial wrote (and
    discarded) a run in the database the person was pointed at, which a
    resume promises never to write to. It compares after its own replay,
    so it needs no trial."""

    def test_its_regeneration_runs_no_trial(self, monkeypatch):
        import types

        from qa_tools.common import bootstrap as boot
        from qa_tools.common import checkpoints, replay_inputs

        cp = types.SimpleNamespace(recorded=types.SimpleNamespace(readable=True, arrivals=[]),
                                   collection_id="civil-registration", before=3, name="ckpt")
        monkeypatch.setattr(checkpoints, "require_synthetic", lambda: None)
        monkeypatch.setattr(checkpoints, "find", lambda name: cp)
        monkeypatch.setattr(replay_inputs, "first_affected",
                            lambda recorded: types.SimpleNamespace(arrival=5, reason="changed"))
        seen = []

        class Stop(Exception):
            pass

        monkeypatch.setattr("cli.bdm.generate_synthetic_data", lambda **k: seen.append(k))
        monkeypatch.setattr("cli.cp.generate_synthetic_data", lambda **k: seen.append(k))
        monkeypatch.setattr(checkpoints, "copy_for_resume",
                            lambda c: (_ for _ in ()).throw(Stop()))
        with pytest.raises(Stop):
            boot.resume("ckpt")
        assert seen == [{"trial": False}, {"trial": False}]


class TestEveryFailureNamesWhatToLookAt:
    """Post-build-review #157 finding 6 (observability NFR): an ordinary
    amber that warned on nothing, or a quiet verdict, named no checks."""

    def test_an_amber_with_no_named_rule_that_warned_on_nothing_says_so(self):
        found = target_agreement.compare(DS, [_r("a.not_null_dbt", "pass")], "amber",
                                         "the ordinary amber for 2026-08-28", reads={})
        assert found.checks and "no check warned" in found.checks[0]

    def test_a_quiet_verdict_names_the_quiet_checks(self):
        # QUIET ONLY WHEN EVERY CONTRIBUTING CHECK IS (rollup_statuses); a
        # pass beside one quiet check reads green.
        results = [_r("sex.drift_psi_evidently", "nodata"),
                   _r("row_count_growth_evidently", "nodata")]
        found = target_agreement.compare(DS, results, "green", "lead-in", reads={})
        assert found is not None and any("drift_psi" in c for c in found.checks), found


class TestAfterAReplayWithADisagreement:
    """Coverage the critic found missing: recorded results that DISAGREE."""

    def test_it_is_reported_with_its_checks(self, monkeypatch):
        from qa_tools.common import delivery_log, promotion, qa_store

        built = targets.Built("the ordinary amber for 2026-08-28", DS, "upload-6018", "amber")
        monkeypatch.setattr(delivery_log, "supply_ids", lambda d, c: {("upload-6018", DS): "s"})
        monkeypatch.setattr(qa_store, "current_run", lambda c, d, s: "run_x")
        monkeypatch.setattr(promotion, "_declared_reads", lambda: {})
        monkeypatch.setattr(target_agreement, "recorded_results",
                            lambda c, r: [_r("sex.not_null_dbt", "fail")])
        [found] = target_agreement.after_replay(None, [built])
        assert found.verdict == "red" and found.checks == ("sex.not_null_dbt red",)


class TestARecordThatDoesNotAddUp:
    """Post-build-review #157 finding 7: a ValueError from targets.py escaped
    as a traceback - and after a replay, only once the bootstrap was done."""

    def test_after_a_replay_it_is_a_disagreement(self, monkeypatch):
        from qa_tools.common import bootstrap as boot

        def broken():
            raise ValueError("TS-43: the generator's record holds 0 supplies for 2026-09-04")
        monkeypatch.setattr("cli.pipeline.generated_targets", broken)
        [said] = boot.targets_agree(["bdm"])
        assert "TS-43" in said and "2026-09-04" in said

    def test_at_generation_it_fails_the_trial_cleanly(self, monkeypatch):
        from cli import bdm
        from generator import generate_runs

        def broken():
            raise ValueError("TS-43: no supply arriving 2026-09-05 14:00")
        monkeypatch.setattr(targets, "just_written", broken)
        monkeypatch.setattr(generate_runs, "_previous_delivery_names", lambda: [])
        with pytest.raises(bdm.TargetTrialFailed, match="TS-43"):
            bdm.try_targets(say=lambda _m: None)

    def test_the_scenario_map_is_written_only_once_the_trial_agrees(self, monkeypatch):
        from cli import bdm
        from generator import generate_runs
        from qa_tools.common import scenario_map

        wrote = []
        monkeypatch.setattr(generate_runs, "main", lambda: None)
        monkeypatch.setattr(scenario_map, "write_map", lambda: wrote.append(True))

        def disagree(**k):
            raise bdm.TargetTrialFailed("TS-43 did not read as built")
        monkeypatch.setattr(bdm, "try_targets", disagree)
        with pytest.raises(bdm.TargetTrialFailed):
            bdm.generate_synthetic_data()
        assert wrote == [], "the committed SCENARIOS.md is not rewritten for a history not emitted"


class TestAPipelineRunComparesToo:
    """Post-build-review #157 finding 2 (Keith, 2026-10-11: compare there
    too): `mothman pipeline run` replays the synthetic history and could
    publish it without comparing."""

    def _stub(self, monkeypatch, disagreements):
        from cli import dashboard as dashboard_cli
        from cli import pipeline
        from dashboard import snapshot_dashboard
        from qa_tools.common import bootstrap as boot

        calls = {"compared": [], "published": []}
        monkeypatch.setattr(boot, "holds_history", lambda conn: False)
        monkeypatch.setattr(pipeline, "_run_bdm", lambda s: None)
        monkeypatch.setattr(pipeline, "_run_cp", lambda s: None)
        monkeypatch.setattr(boot, "_confirm_corrections", lambda say: None)
        monkeypatch.setattr(boot, "targets_agree",
                            lambda names: calls["compared"].append(list(names)) or disagreements)
        monkeypatch.setattr(dashboard_cli, "_build_data", lambda: None)
        monkeypatch.setattr(dashboard_cli, "_embed", lambda: None)
        monkeypatch.setattr(dashboard_cli, "publish", lambda: calls["published"].append(True))
        monkeypatch.setattr(snapshot_dashboard, "sync_local_snapshots", lambda: [])
        return calls

    def test_a_disagreement_fails_the_run_and_publishes_nothing(self, monkeypatch):
        from cli import pipeline

        calls = self._stub(monkeypatch, ("TS-43's arrival was built to amber and read red",))
        out = CliRunner().invoke(pipeline.run_command, ["--publish"], env={"COLUMNS": "400"})
        said = " ".join(out.output.split())
        assert out.exit_code != 0 and "TS-43" in said and "did not read as built" in said
        assert calls["compared"] == [["bdm", "cp"]] and calls["published"] == []

    def test_agreement_lets_it_publish(self, monkeypatch):
        from cli import pipeline

        calls = self._stub(monkeypatch, ())
        out = CliRunner().invoke(pipeline.run_command, ["--collection", "bdm", "--publish"])
        assert out.exit_code == 0, out.output
        assert calls["compared"] == [["bdm"]] and calls["published"] == [True]
