"""Tests for qa_tools/common/leaderboard.py (running-thoughts.md #3,
redesigned 2026-09-18 for the automation-tension follow-up to item #5
Thread B - a real person's own streak of clean GitHub-ticket
RESOLUTIONS, not clean QA RUNS). build_resolution_episodes()/
compute_resolution_streaks()/build_leaderboard() are pure over
already-fetched `gh`-shaped data, same plain-dict-fixture treatment
tests/test_acceptance_sync.py's own pure functions already get - no
real `gh`/network here at all."""
from __future__ import annotations

import json

from qa_tools.common import leaderboard as lb


def _event(event, actor, created_at):
    return {"event": event, "actor": actor, "created_at": created_at}


class TestFetchTicketResolutionGhInvocation:
    """Real bug found on this project's first live `gh api` run
    (2026-09-18, CI run for commit 48b89a7): `gh api` silently switches
    an otherwise-GET request to POST the moment ANY `-f`/`-F` param is
    given (unless `-X GET` is also passed explicitly) - POSTing to the
    real, read-only Issue Events endpoint fails with a real 415.
    Confirmed directly against this repo's own real issue #8 while
    diagnosing: the same call via `-f per_page=100` returns 415, a plain
    GET with `?per_page=100` in the URL returns 200. Fixed by moving
    `per_page` into the URL's own query string, never via `-f`/`-F` -
    this test locks that in by asserting the real `gh` invocation never
    reaches for `-f`/`-F` again, without needing a real `gh`/network
    call itself."""

    def test_the_events_api_call_never_uses_f_flags(self, monkeypatch):
        calls = []

        def fake_run_gh(args):
            calls.append(args)
            if args[:2] == ["issue", "view"]:
                return json.dumps({"number": 1, "labels": []})
            return json.dumps([])

        monkeypatch.setattr(lb, "_run_gh", fake_run_gh)
        lb.fetch_ticket_resolution("owner", "repo", 1)

        events_call = next(c for c in calls if c[0] == "api")
        assert "-f" not in events_call
        assert "-F" not in events_call
        assert "per_page=100" in events_call[1]


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

    def _config(self, people, agency_assignments=None, dataset_assignments=None):
        """The real 3-key shape qa_tools.common.people.parse_people_config()
        returns (people/agency_assignments/dataset_assignments) -
        assignees_for() reads all three directly, so a bare {"people":
        ...} dict (this file's own pre-2026-09-19 fixture shape) would
        KeyError now that build_leaderboard() calls it."""
        return {
            "people": people,
            "agency_assignments": agency_assignments or {},
            "dataset_assignments": dataset_assignments or {},
        }

    def test_only_people_with_a_real_people_yaml_github_entry_appear_as_streak_holders(self):
        raw_tickets = self._raw("birth-registrations", ("knownperson", "2026-01-01T09:00:00Z"), ("ghost", "2026-01-02T09:00:00Z"))
        people_config = self._config({"known@example.com": {"name": "Known Person", "nickname": "KP", "github": "knownperson"}})

        rows = lb.build_leaderboard(raw_tickets, people_config, {})

        assert len(rows) == 1
        assert rows[0]["name"] == "Known Person"
        assert rows[0]["streak"] == 1
        assert "email" not in rows[0]

    def test_sorted_by_streak_descending_across_datasets(self):
        raw_tickets = (
            self._raw("x", ("a", "2026-01-01T09:00:00Z"))
            + self._raw("y", ("a", "2026-01-01T09:00:00Z"), ("a", "2026-01-02T09:00:00Z"))
        )
        people_config = self._config({"a@example.com": {"name": "A", "nickname": None, "github": "a"}})

        rows = lb.build_leaderboard(raw_tickets, people_config, {})

        assert [r["streak"] for r in rows] == [2, 1]
        assert [r["dataset_id"] for r in rows] == ["y", "x"]

    def test_identity_is_resolved_by_github_login_not_email(self):
        """A ticket-close event carries a real GitHub login, never an
        email - unlike the original run-based design's run_by, there's
        no email to match people.yaml on at all here."""
        raw_tickets = self._raw("birth-registrations", ("knownperson", "2026-01-01T09:00:00Z"))
        people_config = self._config({"known@example.com": {"name": "Known Person", "nickname": "KP", "github": "knownperson"}})

        rows = lb.build_leaderboard(raw_tickets, people_config, {})

        assert rows[0]["github"] == "knownperson"

    def test_a_dataset_assigned_person_with_no_streak_yet_appears_at_zero(self):
        """Keith's own ask, 2026-09-19: he saw an empty leaderboard on
        the real page despite real people already being in contract/
        people.yaml - correct at the time (nobody had closed a real
        ticket yet), but he wanted to see everyone listed at 0 rather
        than nobody at all."""
        people_config = self._config(
            {"known@example.com": {"name": "Known Person", "nickname": "KP", "github": "knownperson"}},
            agency_assignments={"registry-services": [
                {"email": "known@example.com", "name": "Known Person", "nickname": "KP", "github": "knownperson", "role": "qa"},
            ]},
        )

        rows = lb.build_leaderboard([], people_config, {"birth-registrations": "registry-services"})

        assert rows == [{
            "dataset_id": "birth-registrations", "name": "Known Person",
            "nickname": "KP", "github": "knownperson", "streak": 0,
        }]

    def test_an_assigned_person_with_no_github_still_appears_at_zero(self):
        """contract/people.yaml's own fictional placeholder people
        (Brian/Reg/Arthur) deliberately have no `github:` - they can
        never be real-assigned to a ticket, but should still show up on
        the roster at 0, same as the dashboard's existing "Owned by"
        badge already shows them regardless of github."""
        people_config = self._config(
            {"reg@example.com": {"name": "Reg", "nickname": "Reg", "github": None}},
            agency_assignments={"child-protection-family-support": [
                {"email": "reg@example.com", "name": "Reg", "nickname": "Reg", "github": None, "role": "peer_review"},
            ]},
        )

        rows = lb.build_leaderboard([], people_config, {"cp-clients": "child-protection-family-support"})

        assert rows == [{"dataset_id": "cp-clients", "name": "Reg", "nickname": "Reg", "github": None, "streak": 0}]

    def test_a_real_streak_holder_no_longer_assigned_to_the_dataset_still_appears(self):
        """A real earned streak isn't erased by a later org-chart
        change - the roster (assignees_for()) and the real ticket-close
        history (github_to_person) are two independent sources, unioned
        together, not one gating the other."""
        raw_tickets = self._raw("birth-registrations", ("exemployee", "2026-01-01T09:00:00Z"))
        people_config = self._config(
            {"ex@example.com": {"name": "Ex Employee", "nickname": None, "github": "exemployee"}},
            agency_assignments={"registry-services": []},
        )

        rows = lb.build_leaderboard(raw_tickets, people_config, {"birth-registrations": "registry-services"})

        assert rows == [{
            "dataset_id": "birth-registrations", "name": "Ex Employee",
            "nickname": None, "github": "exemployee", "streak": 1,
        }]

    def test_an_assigned_person_with_a_real_streak_appears_once_not_twice(self):
        """The roster row and the streak-holder row must be the SAME
        row for someone who's both assigned AND has a real streak - not
        a duplicate 0 row plus a separate real-streak row."""
        raw_tickets = self._raw("birth-registrations", ("knownperson", "2026-01-01T09:00:00Z"))
        people_config = self._config(
            {"known@example.com": {"name": "Known Person", "nickname": "KP", "github": "knownperson"}},
            agency_assignments={"registry-services": [
                {"email": "known@example.com", "name": "Known Person", "nickname": "KP", "github": "knownperson", "role": "qa"},
            ]},
        )

        rows = lb.build_leaderboard(raw_tickets, people_config, {"birth-registrations": "registry-services"})

        assert len(rows) == 1
        assert rows[0]["streak"] == 1

    def test_a_person_assigned_under_two_roles_to_the_same_dataset_appears_once(self):
        """Real bug found live, 2026-09-19: contract/people.yaml can
        assign the same person to the same agency under more than one
        role (Keith himself: registry-services qa AND manager) -
        assignees_for() returns one raw record per assignment entry, so
        without deduping, build_leaderboard() produced two identical
        rows for the same person/dataset (confirmed live via a real
        Playwright screenshot of the built dashboard's leaderboard
        panel: "#1 - K$" and "#2 - K$" both for Birth Registrations)."""
        people_config = self._config(
            {"known@example.com": {"name": "Known Person", "nickname": "KP", "github": "knownperson"}},
            agency_assignments={"registry-services": [
                {"email": "known@example.com", "name": "Known Person", "nickname": "KP", "github": "knownperson", "role": "qa"},
                {"email": "known@example.com", "name": "Known Person", "nickname": "KP", "github": "knownperson", "role": "manager"},
            ]},
        )

        rows = lb.build_leaderboard([], people_config, {"birth-registrations": "registry-services"})

        assert len(rows) == 1
