"""The rolling anchor at the bootstrap, the generate command, the reset and
`mothman env current` (REQ-GEN-404, REQ-GEN-405, REQ-GEN-408, REQ-DASH-407;
signed by Keith 2026-11-14 as speed-anchor v2)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from click.testing import CliRunner

from asset_model import history_anchor
from bootstrap import anchoring, bootstrap, generation, replay_inputs, synthetic_reset
from qa_tools.common import qa_store, supply_db

FIXED = history_anchor.FIXED_TEST_ANCHOR
LATER = date(2026, 11, 13)


def _history(conn) -> None:
    import filing_support
    from asset_model.assignment import Assignment

    filing_support.file(Assignment(dataset_id="cp-clients", supply_id="cp-clients@x",
                                   slot="2026-Q1", branch="open-slot-unfilled",
                                   considered=("2026-Q1",)))


class TestWhichAnchorABootstrapUses:
    """REQ-GEN-405 criteria 2, 4 and 9; REQ-GEN-404 criterion 5."""

    def test_without_a_flag_it_is_the_fixed_anchor_on_every_environment(self, monkeypatch):
        for env in ("test", "ci", "sandbox", "dev"):
            monkeypatch.setenv("MOTHMAN_ENVIRONMENT", env)
            assert anchoring.chosen_without_roll(None) == anchoring.Chosen(FIXED, "fixed")

    def test_a_roll_or_another_anchor_is_refused_under_test_and_ci(self, monkeypatch):
        for env in ("test", "ci"):
            monkeypatch.setenv("MOTHMAN_ENVIRONMENT", env)
            with pytest.raises(anchoring.AnchorRefused, match="always use the fixed test anchor"):
                anchoring.requested(None, True)
            with pytest.raises(anchoring.AnchorRefused, match="always use the fixed test anchor"):
                anchoring.requested("2026-10-01", False)
            anchoring.requested(FIXED.isoformat(), False)  # the fixed one is allowed

    def test_both_flags_together_are_refused(self, monkeypatch):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        with pytest.raises(anchoring.AnchorRefused, match="both given"):
            anchoring.requested("2026-10-01", True)

    def test_the_cli_says_both_flags_are_a_usage_error(self):
        from cli.pipeline import pipeline_group

        result = CliRunner().invoke(pipeline_group, ["bootstrap", "--anchor", "2026-10-01",
                                                     "--roll-anchor"])
        assert result.exit_code == 2
        assert "--anchor" in result.output and "--roll-anchor" in result.output

    def test_the_help_carries_the_three_examples(self):
        """REQ-GEN-405 criterion 7."""
        from cli.pipeline import pipeline_group

        out = CliRunner().invoke(pipeline_group, ["bootstrap", "--help"]).output
        for example in ("mothman pipeline bootstrap  ", "bootstrap --roll-anchor",
                        "bootstrap --anchor 2026-11-13"):
            assert example in out, out

    def test_the_bootstrap_refuses_the_retired_variable(self, monkeypatch):
        monkeypatch.setenv("GENERATOR_ANCHOR_DATE", "2026-10-01")
        result = bootstrap.bootstrap()
        assert result.refused and "--anchor" in result.reason

    def test_the_bootstrap_refuses_a_future_anchor(self, monkeypatch):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "sandbox")
        result = bootstrap.bootstrap(anchor="2099-01-01")
        assert result.refused and "is after today" in result.reason


class TestTheRoll:
    """REQ-GEN-405 criteria 3 and 5 (SA Q5), with a pinned clock for today."""

    NOW = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)  # 09:00 in Perth

    def test_today_on_the_assets_clock_when_every_receipt_has_passed(self):
        chosen = anchoring.roll(now=self.NOW,
                                latest_receipt_at=lambda d: self.NOW - timedelta(hours=1))
        assert chosen == anchoring.Chosen(
            date(2026, 11, 16), "rolled",
            "Generating up to today, 2026-11-16 on Perth's clock (--roll-anchor).")

    def test_the_day_before_when_todays_last_receipt_is_still_to_come(self):
        late = datetime(2026, 11, 16, 6, 30, tzinfo=timezone.utc)  # 14:30 Perth

        def latest(candidate):
            return late if candidate == date(2026, 11, 16) else self.NOW - timedelta(days=1)

        chosen = anchoring.roll(now=self.NOW, latest_receipt_at=latest)
        assert chosen.anchor == date(2026, 11, 15)
        assert chosen.said == ("Rolling to 2026-11-15: a receipt is still planned for "
                               "14:30 today, Perth time.")

    def test_the_latest_receipt_is_read_off_every_receipt_file(self, tmp_path):
        folder = tmp_path / "receipts" / "d1"
        folder.mkdir(parents=True)
        (folder / "a.json").write_text('{"received_at": "2026-11-16T06:30:00+00:00"}')
        (folder / "b.json").write_text('{"received_at": "2026-11-16T01:00:00+00:00"}')
        assert anchoring.latest_receipt(tmp_path) == datetime(2026, 11, 16, 6, 30,
                                                              tzinfo=timezone.utc)


class TestAPopulatedDatabase:
    """REQ-GEN-405 criterion 6, and the anchor recorded in the qa schema
    (REQ-GEN-404 criterion 4)."""

    def test_a_roll_is_refused_naming_the_recorded_anchor(self, private_supply_dsn,
                                                          monkeypatch):
        # A DEMO ENVIRONMENT'S RULES, ON THE TEST'S OWN DATABASE (marked test).
        monkeypatch.setattr(anchoring, "environment", lambda: "sandbox")
        with supply_db.connect(label="test-anchor") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
            qa_store.record_history_anchor(conn, FIXED)
        result = bootstrap.bootstrap(roll_anchor=True)
        assert result.refused
        assert "--roll-anchor" in result.reason and "anchor: 2026-09-25" in result.reason
        assert "`mothman env reset-synthetic`" in result.reason

    def test_none_recorded_is_said(self, private_supply_dsn, monkeypatch):
        monkeypatch.setattr(anchoring, "environment", lambda: "sandbox")
        with supply_db.connect(label="test-anchor") as conn:
            qa_store.ensure_schema(conn)
            _history(conn)
        result = bootstrap.bootstrap(anchor="2026-10-01")
        assert result.refused and "anchor: not recorded" in result.reason

    def test_one_history_one_anchor(self, private_supply_dsn):
        with supply_db.connect(label="test-anchor") as conn:
            qa_store.ensure_schema(conn)
            assert qa_store.history_anchor(conn) is None
            qa_store.record_history_anchor(conn, LATER)
            qa_store.record_history_anchor(conn, LATER)
            assert qa_store.history_anchor(conn) == LATER
            with pytest.raises(ValueError, match="one database holds one history"):
                qa_store.record_history_anchor(conn, FIXED)


class TestTheGenerateCommand:
    """REQ-GEN-404 criteria 5, 7 and 8 (SR3)."""

    def test_a_bare_generate_is_refused_on_a_mismatch_with_the_anchor_file(
            self, tmp_path, monkeypatch):
        monkeypatch.setattr(history_anchor, "path", lambda: tmp_path / history_anchor.FILE)
        history_anchor.write(LATER)
        with pytest.raises(anchoring.AnchorRefused) as caught:
            generation.generate_on_its_own("child-protection", trial=False)
        said = str(caught.value)
        assert "2026-11-13" in said and "2026-09-25" in said
        assert "`mothman env reset-synthetic` then `mothman pipeline bootstrap`" in said

    def test_the_cli_refuses_it_as_a_refusal_not_a_traceback(self, tmp_path, monkeypatch):
        from cli.app import cli

        monkeypatch.setattr(history_anchor, "path", lambda: tmp_path / history_anchor.FILE)
        history_anchor.write(LATER)
        result = CliRunner().invoke(cli, ["cp", "generate-synthetic-data", "--yes"])
        assert result.exit_code == 1, result.output
        assert "Nothing was written" in " ".join(result.output.replace("│", " ").split())

    def test_a_future_anchor_is_refused_by_the_command(self):
        from cli.app import cli

        result = CliRunner().invoke(cli, ["cp", "generate-synthetic-data", "--yes",
                                          "--anchor", "2099-01-01"])
        assert result.exit_code == 1 and "is after today" in result.output


class TestTheCacheKey:
    """REQ-GEN-404 criterion 11, REQ-GEN-405 criterion 11."""

    def test_the_same_on_two_wall_clock_dates(self, monkeypatch):
        monkeypatch.setenv("MOTHMAN_PINNED_NOW", "2026-09-26T00:00:00+00:00")
        first = replay_inputs.cache_key()
        monkeypatch.setenv("MOTHMAN_PINNED_NOW", "2027-03-01T00:00:00+00:00")
        assert replay_inputs.cache_key() == first == replay_inputs.cache_key(anchor=FIXED)

    def test_another_anchor_never_matches_the_fixed_key(self):
        fixed = replay_inputs.cache_key()
        with history_anchor.anchored(LATER):
            rolled = replay_inputs.cache_key()
        assert rolled != fixed and rolled.startswith(fixed) and "2026-11-13" in rolled


class TestTheResume:
    """REQ-GEN-404 criterion 6: a resume regenerates at the anchor recorded for
    the history it resumes, never today's - and refuses where none is."""

    def _checkpoint(self, monkeypatch, anchor):
        from bootstrap import checkpoints

        cp = type("Cp", (), {"collection_id": "child-protection", "before": 3,
                             "recorded": type("R", (), {"readable": True})()})()
        monkeypatch.setattr(checkpoints, "require_synthetic", lambda: None)
        monkeypatch.setattr(checkpoints, "find", lambda _name: cp)
        monkeypatch.setattr(checkpoints, "require_names_fit", lambda *_a: None)
        monkeypatch.setattr(checkpoints, "recorded_anchor", lambda _cp: anchor)
        monkeypatch.setattr(bootstrap, "reads_others", lambda _s: None)
        return cp

    def test_it_regenerates_at_the_recorded_anchor_on_a_later_day(self, monkeypatch):
        self._checkpoint(monkeypatch, LATER)
        monkeypatch.setenv("MOTHMAN_PINNED_NOW", "2027-01-20T00:00:00+00:00")
        seen = []

        def at(*_a):
            from generator.anchor_date import get_anchor_date

            seen.append(get_anchor_date())
            return bootstrap.ResumeResult(replayed=False, reason="stopped by the test")

        monkeypatch.setattr(bootstrap, "_resume_at", at)
        bootstrap._resume("mothman_ckpt_x", False, None)
        assert seen == [LATER]

    def test_none_recorded_is_refused(self, monkeypatch):
        self._checkpoint(monkeypatch, None)
        result = bootstrap._resume("mothman_ckpt_x", False, None)
        assert result.refused and "records no anchor" in result.reason
        assert "`mothman env reset-synthetic` then `mothman pipeline bootstrap`" in result.reason


class TestTheResetDeletesTheGeneratedFiles:
    """REQ-GEN-408 criteria 1 to 7, against a data folder of the test's own
    (tests/conftest.py's _reset_deletes_no_real_files)."""

    def _generated(self, written=("d1",), extra=()):
        import json

        root = synthetic_reset.data_dir()
        for name in written + extra:
            (root / "deliveries" / name).mkdir(parents=True)
            (root / "deliveries" / name / "f.csv").write_text("x")
            (root / "receipts" / name).mkdir(parents=True)
            (root / "receipts" / name / "f.csv.json").write_text("{}")
        (root / "generator_bookkeeping.json").write_text(json.dumps(
            {"cp-clients": [{"delivery": n} for n in written], "_anchor": "2026-09-25"}))
        (root / "scenario_placements.json").write_text("{}")
        history_anchor.write(FIXED, root / history_anchor.FILE)
        return root

    def test_the_new_phrase_names_the_files(self):
        assert synthetic_reset.confirmation_phrase() == (
            f"delete all QA history and generated files for {synthetic_reset.asset_id()}")

    def test_the_command_lists_and_deletes_every_generated_file(self, private_supply_dsn):
        from cli.env import env_group

        root = self._generated()
        result = CliRunner().invoke(env_group, ["reset-synthetic"],
                                    input=synthetic_reset.confirmation_phrase() + "\n")
        assert result.exit_code == 0, result.output
        flat = " ".join(result.output.split())
        assert "deliveries: 1 file(s)" in flat and "receipts: 1 file(s)" in flat
        assert "generated up to 2026-09-25 - `mothman pipeline bootstrap --anchor 2026-09-25`" \
               in flat
        assert "`mothman pipeline bootstrap --roll-anchor`" in flat
        assert not any(p.exists() for p in synthetic_reset.generated_paths())
        assert root.exists()

    def test_a_hand_filed_folder_refuses_before_the_phrase(self, private_supply_dsn):
        from cli.env import env_group

        self._generated(extra=("handfiled-abc",))
        result = CliRunner().invoke(env_group, ["reset-synthetic"],
                                    input=synthetic_reset.confirmation_phrase() + "\n")
        assert result.exit_code == 1
        assert "handfiled-abc" in result.output and "Type" not in result.output
        assert all(p.exists() for p in synthetic_reset.generated_paths())

    def test_a_symlinked_data_folder_is_refused(self, private_supply_dsn, tmp_path,
                                                monkeypatch):
        real = tmp_path / "elsewhere"
        real.mkdir()
        link = tmp_path / "linked"
        link.symlink_to(real)
        monkeypatch.setattr(synthetic_reset, "data_dir", lambda: link)
        monkeypatch.setattr(synthetic_reset, "expected_data_dir", lambda: link)
        (real / "receipts").mkdir()
        with pytest.raises(synthetic_reset.UnsafeFiles, match="symbolic link"):
            synthetic_reset.refuse_unsafe()
        with supply_db.connect(label="test-anchor") as conn:
            with pytest.raises(synthetic_reset.UnsafeFiles):
                synthetic_reset.reset(conn, synthetic_reset.confirmation_phrase())
        assert (real / "receipts").exists()

    def test_a_folder_that_is_not_this_assets_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(synthetic_reset, "data_dir", lambda: tmp_path / "other")
        with pytest.raises(synthetic_reset.UnsafeFiles, match="not this asset's data folder"):
            synthetic_reset.refuse_unsafe()

    def test_a_part_that_cannot_be_deleted_is_named(self, monkeypatch):
        import shutil

        self._generated()

        def stuck(_path):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(shutil, "rmtree", stuck)
        deleted, remains = synthetic_reset.delete_generated()
        assert any("deliveries" in r for r in remains)
        assert any("generator_bookkeeping.json" in d for d in deleted)


class TestEnvCurrentSaysTheAnchor:
    """REQ-DASH-407 criterion 8: from the anchor file, no database."""

    def test_with_the_fixed_anchor(self, tmp_path, monkeypatch):
        from cli.env import env_group

        monkeypatch.setattr(history_anchor, "path", lambda: tmp_path / history_anchor.FILE)
        history_anchor.write(FIXED)
        out = CliRunner().invoke(env_group, ["current"]).output
        assert "Synthetic data generated up to 2026-09-25 (the fixed test anchor)" in out

    def test_with_a_rolled_one(self, tmp_path, monkeypatch):
        from cli.env import env_group

        monkeypatch.setattr(history_anchor, "path", lambda: tmp_path / history_anchor.FILE)
        history_anchor.write(LATER)
        out = " ".join(CliRunner().invoke(env_group, ["list"]).output.split())
        assert ("Synthetic data generated up to 2026-11-13 (rolled; the deployment-half "
                "tests refuse it)") in out

    def test_without_an_anchor_file(self, tmp_path, monkeypatch):
        from cli.env import env_group

        monkeypatch.setattr(history_anchor, "path", lambda: tmp_path / "absent")
        result = CliRunner().invoke(env_group, ["current"])
        assert result.exit_code == 0
        assert "there is no anchor file" in " ".join(result.output.split())


class TestTheClosingLine:
    """REQ-GEN-399 criterion 4 and REQ-DASH-407 criterion 7."""

    def _said(self, how, up_to="2026-11-13"):
        result = bootstrap.BootstrapResult(populated=True, staged_before=0, staged_after=7,
                                           generated_up_to=(up_to, how))
        return bootstrap.closing_line(result)

    def test_fixed(self):
        assert self._said("fixed", "2026-09-25") == (
            "7 staged table(s) in this environment, generated up to 2026-09-25 "
            "(the fixed test anchor).")

    def test_rolled(self):
        assert self._said("rolled") == (
            "7 staged table(s) in this environment, generated up to 2026-11-13 (rolled to "
            "today on Perth's clock; `--anchor 2026-11-13` reproduces it).")


class TestTheDeploymentHalfRefusesAnotherAnchor:
    """REQ-GEN-405 criterion 8: checked once per asset's database before any
    test runs, stopping the session with one message - never per test, never
    a skip."""

    class _Item:
        def __init__(self, asset):
            self.asset = asset

        def get_closest_marker(self, name):
            import types

            if name == "asset":
                return types.SimpleNamespace(args=(self.asset,))
            if name == "needs_deployment":
                return object()
            return None

    def _check(self, monkeypatch, found):
        import conftest

        monkeypatch.setattr(conftest, "deployment_dsn_for", lambda a: f"dsn-{a}")
        reads = []
        monkeypatch.setattr(conftest, "recorded_anchor_of",
                            lambda dsn: reads.append(dsn) or found)
        items = [self._Item("quarterly")] * 40 + [self._Item("daily")] * 2
        try:
            conftest._refuse_a_deployment_at_another_anchor(items)
        except pytest.UsageError as exc:
            return str(exc), reads
        return None, reads

    def test_a_rolled_history_stops_the_session_once(self, monkeypatch):
        said, reads = self._check(monkeypatch, LATER)
        assert reads == ["dsn-daily", "dsn-quarterly"], "one read per asset's database"
        assert said.count("2026-11-13") == 2 and said.count("not a code fault") == 2
        assert "40 test(s) need it" in said and "2 test(s) need it" in said
        assert "mothman env reset-synthetic` then `MOTHMAN_ASSET=quarterly mothman pipeline " \
               "bootstrap`" in said and "replaces a rolled demo" in said

    def test_an_unrecorded_history_is_refused_too(self, monkeypatch):
        said, _ = self._check(monkeypatch, None)
        assert "none recorded - bootstrapped before REQ-GEN-404" in said

    def test_the_fixed_anchor_passes(self, monkeypatch):
        said, _ = self._check(monkeypatch, FIXED)
        assert said is None


class TestPastTheLastAuthoredRound:
    """REQ-GEN-406 criterion 6: the quarterly calendar's last authored round is
    2027-11-01 (assets/quarterly/calendar.yaml)."""

    def test_an_anchor_after_it_is_refused_naming_what_to_do(self):
        with pytest.raises(anchoring.AnchorRefused) as caught:
            anchoring.refuse_past_the_last_round(date(2027, 12, 1))
        said = str(caught.value)
        assert "last authored round, 2027-11-01" in said and "calendar.yaml" in said
        assert "mothman schedule candidate-dates --calendar" in said and "--year 2027" in said
        assert "`mothman pipeline bootstrap` without --roll-anchor" in said

    def test_an_anchor_before_it_is_not(self):
        anchoring.refuse_past_the_last_round(date(2027, 11, 1))


class TestOffsetDates:
    """REQ-GEN-406 criterion 3: an offset from the anchor, resolved in
    asset_model's one parse, per anchor, and refused on a real asset."""

    def test_resolved_against_the_installed_anchor_per_anchor(self):
        from asset_model import config_yaml

        text = 'a: !anchor -99\nb: !anchor "version {+0}"\nc: "2013-01-01"\n'
        assert config_yaml.parse(text) == {"a": "2026-06-18", "b": "version 2026-09-25",
                                           "c": "2013-01-01"}
        with history_anchor.anchored(LATER):
            assert config_yaml.parse(text)["a"] == "2026-08-06"
        assert config_yaml.parse(text)["a"] == "2026-06-18"

    def test_a_built_value_is_per_anchor_too(self):
        from asset_model import config_yaml

        store = config_yaml.Built()
        text = "a: !anchor 0\n"

        def build():
            return config_yaml.parse(text)["a"]

        assert store.get("k", text, build) == "2026-09-25"
        with history_anchor.anchored(LATER):
            assert store.get("k", text, build) == "2026-11-13"

    def test_refused_on_an_asset_that_is_not_synthetic(self, monkeypatch):
        from asset_model import asset_time, config_yaml

        monkeypatch.setattr(asset_time, "declared_synthetic", lambda: False)
        with pytest.raises(config_yaml.OffsetRefused, match=r"cal.yaml, line 2"):
            config_yaml.parse("x: 1\na: !anchor -3\n", name="cal.yaml", remember=False)


#: The data asset this module's tests act for (C11).
pytestmark = pytest.mark.asset("quarterly")
