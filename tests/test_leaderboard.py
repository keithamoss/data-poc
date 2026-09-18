"""Tests for qa_tools/common/leaderboard.py (running-thoughts.md #3,
2026-09-18 - "gamification MVP"). compute_streaks()/build_leaderboard()
are pure over already-loaded data; _person_runs() is tested against a
real temp qa_results/ tree (matching test_changelog.py's own real-
committed-history pattern) since it's the one function that actually
reads from disk."""
from __future__ import annotations

from qa_tools.common import leaderboard
from qa_tools.common.qa_results_writer import write_qa_result


def _write_run(qa_results_dir, agency, dataset, run_id, run_by, run_timestamp="2026-01-01T09:00:00+00:00"):
    write_qa_result(agency, dataset, run_id, run_timestamp, "dataset_stats",
                     {"manifest_entry": {"run_id": run_id}}, run_by=run_by, results_dir=qa_results_dir)


class TestPersonRuns:
    def test_reads_real_run_by_per_run_in_chronological_order(self, tmp_path):
        _write_run(tmp_path, "registry-services", "birth-registrations", "run_1", "a@example.com")
        _write_run(tmp_path, "registry-services", "birth-registrations", "run_2", "b@example.com")

        runs = leaderboard._person_runs("birth-registrations", qa_results_dir=tmp_path)

        assert [r["run_id"] for r in runs] == ["run_1", "run_2"]
        assert [r["run_by"] for r in runs] == ["a@example.com", "b@example.com"]

    def test_an_unknown_dataset_id_returns_no_runs_rather_than_raising(self, tmp_path):
        assert leaderboard._person_runs("not-a-real-dataset", qa_results_dir=tmp_path) == []


def _check(warn, fail, *history):
    return {"warn": warn, "fail": fail, "retired_as_of": None,
            "history": [{"run_id": run_id, "value": value} for run_id, value in history]}


def _dataset_json(*history_entries):
    return {"columns": [{"checks": [_check(1, 2, *history_entries)]}]}


class TestComputeStreaks:
    def test_a_persons_current_streak_counts_backward_from_their_own_latest_run(self, tmp_path, monkeypatch):
        monkeypatch.setattr(leaderboard, "_person_runs", lambda dataset_id, qa_results_dir=None: [
            {"run_id": "run_1", "run_by": "a@example.com"},
            {"run_id": "run_2", "run_by": "a@example.com"},
            {"run_id": "run_3", "run_by": "a@example.com"},
        ])
        dataset_json = _dataset_json(("run_1", 3), ("run_2", 0), ("run_3", 0))  # run_1 red, run_2/3 green
        streaks = leaderboard.compute_streaks("birth-registrations", dataset_json)
        # last_run_id is this person's own MOST RECENT run in the streak
        # (run_3), not the oldest one still inside it (run_2).
        assert streaks == {"a@example.com": {"streak": 2, "last_run_id": "run_3"}}

    def test_amber_does_not_break_the_streak(self, tmp_path, monkeypatch):
        monkeypatch.setattr(leaderboard, "_person_runs", lambda dataset_id, qa_results_dir=None: [
            {"run_id": "run_1", "run_by": "a@example.com"},
            {"run_id": "run_2", "run_by": "a@example.com"},
        ])
        dataset_json = _dataset_json(("run_1", 1.5), ("run_2", 0))  # amber then green
        streaks = leaderboard.compute_streaks("birth-registrations", dataset_json)
        assert streaks["a@example.com"]["streak"] == 2

    def test_a_red_most_recent_run_gives_no_streak_entry_at_all(self, tmp_path, monkeypatch):
        monkeypatch.setattr(leaderboard, "_person_runs", lambda dataset_id, qa_results_dir=None: [
            {"run_id": "run_1", "run_by": "a@example.com"},
            {"run_id": "run_2", "run_by": "a@example.com"},
        ])
        dataset_json = _dataset_json(("run_1", 0), ("run_2", 3))  # green then red
        streaks = leaderboard.compute_streaks("birth-registrations", dataset_json)
        assert streaks == {}

    def test_other_peoples_interleaved_runs_are_skipped_not_counted_against_this_person(self, tmp_path, monkeypatch):
        monkeypatch.setattr(leaderboard, "_person_runs", lambda dataset_id, qa_results_dir=None: [
            {"run_id": "run_1", "run_by": "a@example.com"},
            {"run_id": "run_2", "run_by": "b@example.com"},  # someone else's red run, in between
            {"run_id": "run_3", "run_by": "a@example.com"},
        ])
        dataset_json = _dataset_json(("run_1", 0), ("run_2", 3), ("run_3", 0))
        streaks = leaderboard.compute_streaks("birth-registrations", dataset_json)
        # a@example.com's OWN sequence (run_1, run_3) is both green - b's red run_2
        # never touches a's own streak at all.
        assert streaks["a@example.com"]["streak"] == 2
        # b's own single run was red - no entry.
        assert "b@example.com" not in streaks


class TestBuildLeaderboard:
    def test_only_people_with_a_real_people_yaml_entry_appear(self, monkeypatch):
        monkeypatch.setattr(leaderboard, "compute_streaks", lambda dataset_id, dataset_json, qa_results_dir=None: {
            "known@example.com": {"streak": 5, "last_run_id": "run_5"},
            "unknown@example.com": {"streak": 3, "last_run_id": "run_3"},
        })
        people_config = {"people": {"known@example.com": {"name": "Known Person", "nickname": "KP", "github": "knownperson"}}}

        rows = leaderboard.build_leaderboard({"birth-registrations": {}}, people_config)

        assert len(rows) == 1
        assert rows[0]["name"] == "Known Person"
        assert "email" not in rows[0]

    def test_sorted_by_streak_descending_across_datasets(self, monkeypatch):
        def fake_streaks(dataset_id, dataset_json, qa_results_dir=None):
            return {"a@example.com": {"streak": 2 if dataset_id == "x" else 9, "last_run_id": "r"}}
        monkeypatch.setattr(leaderboard, "compute_streaks", fake_streaks)
        people_config = {"people": {"a@example.com": {"name": "A", "nickname": None, "github": "a"}}}

        rows = leaderboard.build_leaderboard({"x": {}, "y": {}}, people_config)

        assert [r["streak"] for r in rows] == [9, 2]
        assert [r["dataset_id"] for r in rows] == ["y", "x"]
