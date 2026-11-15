"""The replay inside a bootstrap runs with the asset's configuration pinned
(REQ-GEN-399), and a bootstrap generates every collection under that one pin
(REQ-GEN-398 criteria 2 and 3), both signed by Keith 2026-11-14 as
speed-anchor v2.

The bootstrap is driven through its real entry point - `boot.bootstrap`, the
CLI command and the TUI menu - with the real tools stubbed out: what is under
test is the configuration the replay's readers are answered with, and what a
person is told.
"""
from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path

import pytest

import asset_folders
import dbsupport
from asset_model import arrivals, config_pin, slots
from bootstrap import bootstrap as boot

pytestmark = pytest.mark.asset("daily")

DATASET = "birth-registrations"
WHEN = ('expected_time: "22:00"', 'expected_time: "21:00"')
UNTIL = date(2026, 9, 1)


def edit_in_place(path: Path, old: str, new: str) -> None:
    assert len(old) == len(new)
    before = os.stat(path)
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


def _due_hour() -> int:
    """The hour Birth Registrations' first slot is due, as filing reads it."""
    return slots.slots_for_dataset(DATASET, until=UNTIL)[0].due_at.hour


@pytest.fixture
def calendar(tmp_path) -> Path:
    pointed = tmp_path / "pointed"
    pointed.mkdir()
    real = asset_folders.real_folder()
    (pointed / "calendar.yaml").write_text((real / "calendar.yaml").read_text(encoding="utf-8"),
                                           encoding="utf-8")
    asset_folders.point(pointed)
    return pointed / "calendar.yaml"


@pytest.fixture
def stubbed(calendar, tmp_path, monkeypatch):
    """A bootstrap of the daily asset into an empty database of its own, its
    generation and replay replaced by `on_generate` and `on_replay`."""
    from asset_model import delivery
    from qa_tools.common import supply_db

    dbsupport.use_empty_supply_db(monkeypatch)
    with supply_db.connect(label="test") as conn:
        supply_db.ensure_schemas(conn)
    # An empty tree of the test's own, never data/.
    monkeypatch.setattr(delivery, "default_deliveries_dir", lambda: tmp_path / "deliveries")
    monkeypatch.setattr(delivery, "default_receipts_dir", lambda: tmp_path / "receipts")
    calls: dict = {"generate": [], "replay": []}

    def generate(cid, **_k):
        calls["generate"].append(config_pin.installed())
        if calls.get("on_generate"):
            calls["on_generate"]()

    def run_pipeline(collection_id, **_k):
        calls["replay"].append(config_pin.installed())
        if calls.get("on_replay"):
            calls["on_replay"]()

    monkeypatch.setattr("bootstrap.generation.generate_collection", generate)
    monkeypatch.setattr("qa_tools.tools.orchestrate.run_pipeline", run_pipeline)
    monkeypatch.setattr("bootstrap.correction_replay.confirm_due", lambda **k: [])

    def targets(names):
        calls["targets"] = config_pin.installed()
        return ()
    monkeypatch.setattr(boot, "targets_agree", targets)
    return calls


class TestTheReplayReadsThePinnedConfiguration:
    """REQ-GEN-399 criteria 1, 6 and 7."""

    def test_a_calendar_edited_mid_replay_leaves_the_replay_as_pinned(self, stubbed,
                                                                      calendar):
        seen = []

        def replay():
            seen.append(_due_hour())
            edit_in_place(calendar, *WHEN)
            seen.append(_due_hour())
        stubbed["on_replay"] = replay
        result = boot.bootstrap(collection="all")
        assert result.populated
        assert seen == [22, 22], "an edit made mid-replay reached the replay's filing"

    def test_the_next_bootstrap_reads_the_edit(self, stubbed, calendar, monkeypatch):
        stubbed["on_replay"] = lambda: edit_in_place(calendar, *WHEN)
        boot.bootstrap(collection="all")
        assert config_pin.installed() is None
        dbsupport.use_empty_supply_db(monkeypatch)
        from qa_tools.common import supply_db

        with supply_db.connect(label="test") as conn:
            supply_db.ensure_schemas(conn)
        seen = []
        stubbed["on_replay"] = lambda: seen.append(_due_hour())
        boot.bootstrap(collection="all")
        assert seen == [21]

    def test_one_pin_from_generation_to_the_target_agreement(self, stubbed):
        """REQ-GEN-398 criterion 2 and REQ-GEN-399 criterion 6: the
        generation, the replay and the steps after it are under one pin,
        released only when the bootstrap returns."""
        result = boot.bootstrap(collection="all")
        pins = [*stubbed["generate"], *stubbed["replay"], stubbed["targets"]]
        assert all(p is not None for p in pins)
        assert len({id(p) for p in pins}) == 1
        assert pins[0].digest == result.pin_digest
        assert config_pin.installed() is None

    def test_a_pipeline_run_sees_an_edit_made_since_the_last_call(self, calendar,
                                                                   monkeypatch, tmp_path):
        """REQ-GEN-399 criterion 5: outside a bootstrap no pin, on a
        synthetic asset too."""
        from click.testing import CliRunner

        from asset_model import delivery
        from cli import dashboard as dashboard_cli
        from cli import pipeline
        from qa_tools.common import supply_db

        dbsupport.use_empty_supply_db(monkeypatch)
        with supply_db.connect(label="test") as conn:
            supply_db.ensure_schemas(conn)
        monkeypatch.setattr(delivery, "default_deliveries_dir", lambda: tmp_path / "d")
        monkeypatch.setattr(delivery, "default_receipts_dir", lambda: tmp_path / "r")
        seen = []

        def run_stream(ids, **_k):
            seen.append((config_pin.installed(), _due_hour()))
            edit_in_place(calendar, *WHEN)
            seen.append((config_pin.installed(), _due_hour()))
        monkeypatch.setattr("qa_tools.tools.orchestrate.run_stream", run_stream)
        monkeypatch.setattr(dashboard_cli, "_build_data", lambda: None)
        monkeypatch.setattr(dashboard_cli, "_embed", lambda: None)
        monkeypatch.setattr("dashboard.snapshot_dashboard.sync_local_snapshots", lambda: [])
        done = CliRunner().invoke(pipeline.run_command, [])
        assert done.exit_code == 0, done.output
        assert seen == [(None, 22), (None, 21)]


def _pid_and_pin(_n):
    time.sleep(0.5)
    held = config_pin.installed()
    return os.getpid(), None if held is None else held.digest


class TestEveryStreamProcessGetsTheSameSnapshot:
    """REQ-GEN-399 criteria 2 and 3."""

    def test_two_stream_processes_receive_the_same_digest(self, calendar):
        with config_pin.pinned() as snapshot:
            # An edit after the pin is taken never reaches a stream process.
            edit_in_place(calendar, *WHEN)
            with boot.stream_pool(2) as pool:
                got = list(pool.map(_pid_and_pin, range(4)))
        assert len({pid for pid, _ in got}) == 2, "the two processes were not both used"
        assert {digest for _, digest in got} == {snapshot.digest}

    def test_a_process_under_another_pin_is_named_with_the_files(self, calendar):
        with config_pin.pinned() as mine:
            pass
        edit_in_place(calendar, *WHEN)
        with config_pin.pinned():
            other = boot.pin_report()
        found = boot.pin_differences(mine, {"bdm": other})
        assert len(found) == 1
        assert "calendar.yaml" in found[0] and mine.digest[:12] in found[0]
        assert "Birth Registrations" in found[0]
        assert boot.pin_differences(mine, {"bdm": (mine.digest, {})}) == ()
        assert "no configuration pinned" in boot.pin_differences(mine, {"bdm": (None, {})})[0]

    def test_a_mismatch_fails_the_bootstrap_in_the_cli_and_the_tui(self, stubbed,
                                                                   monkeypatch):
        """Exit non-zero, no 'Ready', and the words CLI finding 10 asks for."""
        from click.testing import CliRunner

        from cli import app, common, pipeline

        wrong = ("Birth Registrations's process ran under abc, not def - differing: "
                 "assets/daily/calendar.yaml",)
        real = boot._populate

        def populate(**kwargs):
            result = real(**kwargs)
            import dataclasses
            return dataclasses.replace(result, pin_differences=wrong)
        monkeypatch.setattr(boot, "_populate", populate)
        done = CliRunner().invoke(pipeline.bootstrap_command, [])
        assert done.exit_code != 0
        message = boot.pin_mismatch_message(wrong)
        for words in ("fault in mothman's hand-off", "not anything you did",
                      "assets/daily/calendar.yaml", "kept but is not to be trusted",
                      "`mothman env reset-synthetic` then `mothman pipeline bootstrap`"):
            assert words in message
        assert "fault in mothman" in done.output

        dbsupport.use_empty_supply_db(monkeypatch)
        from qa_tools.common import supply_db

        with supply_db.connect(label="test") as conn:
            supply_db.ensure_schemas(conn)
        monkeypatch.setattr(common, "confirm", lambda *a, **k: True)
        said = []
        monkeypatch.setattr(app.console, "print",
                            lambda text="", *a, style=None, **k: said.append(str(text)))
        app._bootstrap_menu()
        assert any("fault in mothman" in s for s in said)
        assert not any(s.startswith("Ready") for s in said)


class TestWhatABootstrapSaysAtTheEnd:
    """REQ-GEN-399 criterion 4 and REQ-GEN-398 criterion 3."""

    def test_the_closing_lines_in_order(self, stubbed):
        from click.testing import CliRunner

        from cli import pipeline

        done = CliRunner().invoke(pipeline.bootstrap_command, [])
        assert done.exit_code == 0, done.output
        lines = [line for line in done.output.splitlines() if line.strip()]
        took = next(i for i, line in enumerate(lines) if line.startswith("Took "))
        budget = next(i for i, line in enumerate(lines)
                      if line.startswith((boot.WITHIN_BUDGET, boot.OVER_BUDGET)))
        pinned = next(i for i, line in enumerate(lines)
                      if line.startswith("Configuration pinned: "))
        closing = next(i for i, line in enumerate(lines) if "generated up to" in line)
        assert took < budget < pinned < closing
        assert lines[took].startswith("Took generation ")
        assert len(lines[pinned].split(": ", 1)[1].strip()) == 12
        assert "generated up to 2026-09-25 (the fixed test anchor)" in lines[closing]
        assert not [line for line in lines if line.endswith("...") and (
            line.startswith(("Took ", "Configuration pinned", "Populated", "Adding "))
            or line.startswith((boot.WITHIN_BUDGET, boot.OVER_BUDGET)))]

    def test_the_tui_passes_a_statement_through_without_trailing_off(self, stubbed,
                                                                     monkeypatch):
        from cli import app, common

        monkeypatch.setattr(common, "confirm", lambda *a, **k: True)
        said = []
        monkeypatch.setattr(app.console, "print",
                            lambda text="", *a, style=None, **k: said.append((str(text), style)))
        app._bootstrap_menu()
        texts = [t for t, _ in said]
        took = next(t for t in texts if t.startswith("Took "))
        assert not took.endswith("...")
        # WORK UNDER WAY STILL TRAILS OFF, as the CLI's _step has it.
        assert ("Running the real checks against every Birth Registrations supply...",
                "dim") in said, said
        pinned = next((t, s) for t, s in said if t.startswith("Configuration pinned: "))
        assert pinned[1] == "dim"
        assert any(t.startswith("Ready - ") and "generated up to" in t for t in texts)
        assert texts.index(pinned[0]) > next(i for i, t in enumerate(texts)
                                             if t.startswith((boot.WITHIN_BUDGET,
                                                              boot.OVER_BUDGET)))

    def test_no_tree_snapshot_is_left_installed(self, stubbed):
        boot.bootstrap(collection="all")
        assert arrivals.installed_tree() is None
