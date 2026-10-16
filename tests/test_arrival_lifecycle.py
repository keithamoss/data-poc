"""The one per-arrival lifecycle (REQ-PIPE-086 criterion 2).

The batch and the terminal's hand-filed routes both go through
arrival_lifecycle.process(); these pin what that function promises,
without the real tools, so the contract is checked in milliseconds and
the real-tool behaviour is left to the orchestrator and equivalence
tests.
"""
from __future__ import annotations

from types import SimpleNamespace

from qa_tools.bdm import orchestrate_bdm
from qa_tools.common import arrival_lifecycle
from qa_tools.cp import orchestrate_cp


def _recording_steps(log):
    return arrival_lifecycle.Steps(
        file_and_overlay=lambda a, among: log.append(("file", a.run_id, len(among))),
        entry_for=lambda a: {"run_id": a.run_id},
        run_one=lambda entry, ts, run_by, on_step=None: (
            log.append(("run", entry["run_id"], ts)) or [{"run_id": entry["run_id"]}]),
        promote_after=lambda a, got, run_by: log.append(("gate", a.run_id, len(got))))


A = SimpleNamespace(run_id="r1")
B = SimpleNamespace(run_id="r2")


class TestOneArrivalAtATime:
    def test_each_arrival_is_filed_checked_and_gated_before_the_next(self):
        log = []
        arrival_lifecycle.process_all([A, B], steps=_recording_steps(log),
                                      run_by="x", run_timestamp="T")
        assert [step[:2] for step in log] == [
            ("file", "r1"), ("run", "r1"), ("gate", "r1"),
            ("file", "r2"), ("run", "r2"), ("gate", "r2")]

    def test_every_arrival_sees_the_whole_pass_as_among(self):
        """A zip is filed whole (REQ-PIPE-105 criterion 5): file_and_overlay
        needs every arrival the caller knows of, not just the one in hand."""
        log = []
        arrival_lifecycle.process_all([A, B], steps=_recording_steps(log), run_by="x")
        assert [s[2] for s in log if s[0] == "file"] == [2, 2]

    def test_results_come_back_in_arrival_order(self):
        got = arrival_lifecycle.process_all([A, B], steps=_recording_steps([]), run_by="x")
        assert [r["run_id"] for r in got] == ["r1", "r2"]


class TestTimestamps:
    def test_the_batch_stamps_one_instant_for_the_pass(self):
        log = []
        arrival_lifecycle.process_all([A, B], steps=_recording_steps(log),
                                      run_by="x", run_timestamp="T")
        assert {s[2] for s in log if s[0] == "run"} == {"T"}

    def test_a_hand_filed_run_stamps_each_arrival_as_it_starts(self):
        log = []
        arrival_lifecycle.process_all([A], steps=_recording_steps(log), run_by="x")
        stamp = [s[2] for s in log if s[0] == "run"][0]
        assert stamp and stamp != "T"


class TestBothCollectionsSupplyTheirHalf:
    def test_each_orchestrator_declares_its_steps(self):
        for module in (orchestrate_bdm, orchestrate_cp):
            assert isinstance(module.STEPS, arrival_lifecycle.Steps), module.__name__

    def test_a_contested_birth_registrations_file_is_checked_not_refused(self):
        """One of the drifts the extraction removed: the hand-filed path
        called path_for() and so refused a contested file the batch would
        check (REQ-PIPE-105 criterion 6). Both now use entry_for()."""
        class Contested:
            run_id = "run_x"
            contested = {orchestrate_bdm.DATASET_ID}
            path = "/deliveries/run_x"

            def path_for(self, dataset_id):
                raise AssertionError("path_for refuses to choose between two files")

            def as_entry(self):
                return {"run_id": self.run_id}

        assert orchestrate_bdm.entry_for(Contested())["csv_path"] == "/deliveries/run_x"


class TestTheCollectionsHalvesForwardWhatTheyAreGiven:
    def test_child_protection_files_with_the_whole_pass_as_among(self, monkeypatch):
        """A zip is filed whole (REQ-PIPE-105 criterion 5) only while CP's
        half passes `among` through - nothing else would notice if it
        stopped (delivery-critic, sprint 1)."""
        seen = {}
        monkeypatch.setattr(orchestrate_cp, "file_and_overlay",
                            lambda arrival, among=None: seen.update(among=among))
        orchestrate_cp.STEPS.file_and_overlay(A, [A, B])
        assert seen["among"] == [A, B]

    def test_each_half_reaches_its_own_orchestrators_functions(self, monkeypatch):
        for module in (orchestrate_bdm, orchestrate_cp):
            calls = []
            monkeypatch.setattr(module, "_run_one",
                                lambda *a, **k: calls.append("run") or [])
            monkeypatch.setattr(module, "promote_after",
                                lambda *a, **k: calls.append("gate"))
            module.STEPS.run_one({"run_id": "r"}, "T", "x", on_step=None)
            module.STEPS.promote_after(A, [], "x")
            assert calls == ["run", "gate"], module.__name__
