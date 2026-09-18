"""Tests for qa_tools/common/leaderboard.py (running-thoughts.md #3,
redesigned 2026-09-18 for the automation-tension follow-up to item #5
Thread B - a real person's own streak of clean GitHub-ticket
RESOLUTIONS, not clean QA RUNS). build_resolution_episodes()/
compute_resolution_streaks()/build_leaderboard() are pure over
already-fetched `gh`-shaped data, same plain-dict-fixture treatment
tests/test_acceptance_sync.py's own pure functions already get - no
real `gh`/network here at all."""
from __future__ import annotations

from qa_tools.common import leaderboard as lb


def _event(event, actor, created_at):
    return {"event": event, "actor": actor, "created_at": created_at}


class TestBuildResolutionEpisodes:
    def test_a_closed_event_never_reopened_is_a_clean_episode(self):
        raw_tickets = [{
            "number": 1, "labels": [{"name": "dataset:birth-registrations"}],
            "events": [_event("closed", "keithamoss", "2026-01-10T09:00:00Z")],
        }]
        episodes = lb.build_resolution_episodes(raw_tickets)
        assert episodes["birth-registrations"] == [
            {"closed_by": "keithamoss", "closed_at": "2026-01-10T09:00:00Z", "clean": True},
        ]

    def test_a_closed_event_later_reopened_is_a_dirty_episode(self):
        raw_tickets = [{
            "number": 1, "labels": [{"name": "dataset:birth-registrations"}],
            "events": [
                _event("closed", "keithamoss", "2026-01-10T09:00:00Z"),
                _event("reopened", "someoneelse", "2026-01-11T09:00:00Z"),
            ],
        }]
        episodes = lb.build_resolution_episodes(raw_tickets)
        assert episodes["birth-registrations"][0]["clean"] is False

    def test_a_reopen_only_taints_the_close_it_immediately_follows(self):
        """close -> reopen -> close again: the FIRST close is dirty (it
        really was reopened), the second is a fresh, clean episode of
        its own - a later reopen never retroactively taints an earlier,
        already-superseded close."""
        raw_tickets = [{
            "number": 1, "labels": [{"name": "dataset:birth-registrations"}],
            "events": [
                _event("closed", "a", "2026-01-01T09:00:00Z"),
                _event("reopened", "b", "2026-01-02T09:00:00Z"),
                _event("closed", "a", "2026-01-03T09:00:00Z"),
            ],
        }]
        episodes = lb.build_resolution_episodes(raw_tickets)["birth-registrations"]
        assert [ep["clean"] for ep in episodes] == [False, True]

    def test_events_across_multiple_tickets_for_the_same_dataset_are_merged_and_sorted(self):
        """A dataset can accumulate more than one real ticket over time
        (ticket_sync.py never reopens a CLOSED ticket - a fresh red/amber
        event opens a brand new issue instead) - every ticket carrying
        the same dataset:<id> label contributes to the same real
        resolution history, in real chronological order regardless of
        which issue number each close happened on."""
        raw_tickets = [
            {"number": 2, "labels": [{"name": "dataset:birth-registrations"}],
             "events": [_event("closed", "a", "2026-02-01T09:00:00Z")]},
            {"number": 1, "labels": [{"name": "dataset:birth-registrations"}],
             "events": [_event("closed", "a", "2026-01-01T09:00:00Z")]},
        ]
        episodes = lb.build_resolution_episodes(raw_tickets)["birth-registrations"]
        assert [ep["closed_at"] for ep in episodes] == ["2026-01-01T09:00:00Z", "2026-02-01T09:00:00Z"]

    def test_a_ticket_with_no_dataset_label_is_skipped(self):
        raw_tickets = [{"number": 1, "labels": [{"name": "qa-ticket"}],
                        "events": [_event("closed", "a", "2026-01-01T09:00:00Z")]}]
        assert lb.build_resolution_episodes(raw_tickets) == {}

    def test_a_ticket_never_closed_contributes_no_episodes(self):
        raw_tickets = [{"number": 1, "labels": [{"name": "dataset:birth-registrations"}], "events": []}]
        assert lb.build_resolution_episodes(raw_tickets) == {}


class TestComputeResolutionStreaks:
    def _episodes(self, *entries):
        return [{"closed_by": who, "closed_at": at, "clean": clean} for who, at, clean in entries]

    def test_a_persons_current_streak_counts_backward_from_their_own_latest_close(self):
        episodes = self._episodes(
            ("a", "2026-01-01T09:00:00Z", False),
            ("a", "2026-01-02T09:00:00Z", True),
            ("a", "2026-01-03T09:00:00Z", True),
        )
        streaks = lb.compute_resolution_streaks(episodes)
        assert streaks == {"a": {"streak": 2, "last_closed_at": "2026-01-03T09:00:00Z"}}

    def test_a_dirty_most_recent_close_gives_no_streak_entry_at_all(self):
        episodes = self._episodes(
            ("a", "2026-01-01T09:00:00Z", True),
            ("a", "2026-01-02T09:00:00Z", False),
        )
        streaks = lb.compute_resolution_streaks(episodes)
        assert streaks == {}

    def test_other_peoples_interleaved_closes_are_skipped_not_counted_against_this_person(self):
        episodes = self._episodes(
            ("a", "2026-01-01T09:00:00Z", True),
            ("b", "2026-01-02T09:00:00Z", False),
            ("a", "2026-01-03T09:00:00Z", True),
        )
        streaks = lb.compute_resolution_streaks(episodes)
        assert streaks["a"]["streak"] == 2
        assert "b" not in streaks


class TestBuildLeaderboard:
    def _raw(self, dataset_id, *closes):
        return [{
            "number": i + 1,
            "labels": [{"name": f"dataset:{dataset_id}"}],
            "events": [_event("closed", who, at)],
        } for i, (who, at) in enumerate(closes)]

    def test_only_people_with_a_real_people_yaml_github_entry_appear(self):
        raw_tickets = self._raw("birth-registrations", ("knownperson", "2026-01-01T09:00:00Z"), ("ghost", "2026-01-02T09:00:00Z"))
        people_config = {"people": {"known@example.com": {"name": "Known Person", "nickname": "KP", "github": "knownperson"}}}

        rows = lb.build_leaderboard(raw_tickets, people_config)

        assert len(rows) == 1
        assert rows[0]["name"] == "Known Person"
        assert rows[0]["streak"] == 1
        assert "email" not in rows[0]

    def test_sorted_by_streak_descending_across_datasets(self):
        raw_tickets = (
            self._raw("x", ("a", "2026-01-01T09:00:00Z"))
            + self._raw("y", ("a", "2026-01-01T09:00:00Z"), ("a", "2026-01-02T09:00:00Z"))
        )
        people_config = {"people": {"a@example.com": {"name": "A", "nickname": None, "github": "a"}}}

        rows = lb.build_leaderboard(raw_tickets, people_config)

        assert [r["streak"] for r in rows] == [2, 1]
        assert [r["dataset_id"] for r in rows] == ["y", "x"]

    def test_identity_is_resolved_by_github_login_not_email(self):
        """A ticket-close event carries a real GitHub login, never an
        email - unlike the original run-based design's run_by, there's
        no email to match people.yaml on at all here."""
        raw_tickets = self._raw("birth-registrations", ("knownperson", "2026-01-01T09:00:00Z"))
        people_config = {"people": {"known@example.com": {"name": "Known Person", "nickname": "KP", "github": "knownperson"}}}

        rows = lb.build_leaderboard(raw_tickets, people_config)

        assert rows[0]["github"] == "knownperson"
