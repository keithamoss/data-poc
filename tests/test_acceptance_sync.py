"""Tests for qa_tools/common/acceptance_sync.py (running-thoughts.md #6,
2026-09-18 - "read-only tension: accepting/rejecting amber supplies").
match_acceptances()/build_acceptances() are pure (plain dict fixtures,
no real gh/network); _run_windows_for_dataset() is tested against this
repo's own real committed qa_results/ history, same "prove it against
the real thing, not a fixture built to match it" reasoning
tests/test_github_links.py already uses."""
from __future__ import annotations

from datetime import date

from qa_tools.common import acceptance_sync as acc


def _comment(body, created, author="keithamoss", url="https://github.com/x/y/issues/1#issuecomment-1"):
    return {"author": {"login": author}, "body": body, "createdAt": created, "url": url}


WINDOWS = [
    ("run_1", date(2026, 1, 1), date(2026, 1, 8)),
    ("run_2", date(2026, 1, 8), date(2026, 1, 15)),
    ("run_3", date(2026, 1, 15), None),  # open-ended, the latest run
]


class TestMatchAcceptances:
    def test_a_comment_inside_a_runs_window_matches_that_run(self):
        result = acc.match_acceptances([_comment("/accept", "2026-01-10T09:00:00Z")], WINDOWS)
        assert set(result) == {"run_2"}
        assert result["run_2"]["accepted_by"] == "keithamoss"
        assert result["run_2"]["accepted_at"] == "2026-01-10T09:00:00Z"

    def test_a_comment_before_any_real_run_matches_nothing(self):
        result = acc.match_acceptances([_comment("/accept", "2025-12-01T09:00:00Z")], WINDOWS)
        assert result == {}

    def test_a_comment_in_the_open_ended_latest_window_matches_the_last_run(self):
        result = acc.match_acceptances([_comment("/accept", "2026-06-01T09:00:00Z")], WINDOWS)
        assert set(result) == {"run_3"}

    def test_case_insensitive_and_allows_trailing_text(self):
        result = acc.match_acceptances([_comment("/ACCEPT confirmed with the provider", "2026-01-10T09:00:00Z")], WINDOWS)
        assert set(result) == {"run_2"}

    def test_a_comment_that_doesnt_start_with_slash_accept_is_ignored(self):
        result = acc.match_acceptances([_comment("I don't accept this", "2026-01-10T09:00:00Z")], WINDOWS)
        assert result == {}

    def test_a_bare_word_accept_with_no_slash_is_ignored(self):
        result = acc.match_acceptances([_comment("accept", "2026-01-10T09:00:00Z")], WINDOWS)
        assert result == {}

    def test_first_chronological_accept_wins_when_several_target_the_same_run(self):
        result = acc.match_acceptances([
            _comment("/accept", "2026-01-12T09:00:00Z", author="second"),
            _comment("/accept", "2026-01-09T09:00:00Z", author="first"),
        ], WINDOWS)
        assert result["run_2"]["accepted_by"] == "first"

    def test_a_run_with_no_matching_comment_never_appears_in_the_result(self):
        result = acc.match_acceptances([_comment("/accept", "2026-01-10T09:00:00Z")], WINDOWS)
        assert "run_1" not in result
        assert "run_3" not in result


class TestBuildAcceptances:
    def test_groups_comments_by_the_tickets_own_dataset_label(self, monkeypatch):
        monkeypatch.setattr(acc, "_run_windows_for_dataset", lambda dataset_id, qa_results_dir=None: WINDOWS)
        raw_tickets = [
            {"number": 1, "labels": [{"name": "qa-ticket"}, {"name": "dataset:birth-registrations"}],
             "comments": [_comment("/accept", "2026-01-10T09:00:00Z")]},
        ]
        result = acc.build_acceptances(raw_tickets)
        assert set(result) == {"birth-registrations"}
        assert set(result["birth-registrations"]) == {"run_2"}

    def test_a_ticket_with_no_dataset_label_is_skipped(self, monkeypatch):
        monkeypatch.setattr(acc, "_run_windows_for_dataset", lambda dataset_id, qa_results_dir=None: WINDOWS)
        raw_tickets = [{"number": 1, "labels": [{"name": "qa-ticket"}],
                        "comments": [_comment("/accept", "2026-01-10T09:00:00Z")]}]
        assert acc.build_acceptances(raw_tickets) == {}

    def test_comments_from_multiple_tickets_sharing_a_dataset_id_are_merged(self, monkeypatch):
        """Child Protection's real shape: 6 tickets share the SAME
        qa_results/ collection scope, but could also each independently
        get re-opened across separate episodes - either way, comments
        across every real ticket carrying the same dataset:<id> label
        must all be considered together."""
        monkeypatch.setattr(acc, "_run_windows_for_dataset", lambda dataset_id, qa_results_dir=None: WINDOWS)
        raw_tickets = [
            {"number": 1, "labels": [{"name": "dataset:cp-clients"}],
             "comments": [_comment("/accept", "2026-01-02T09:00:00Z")]},
            {"number": 2, "labels": [{"name": "dataset:cp-clients"}],
             "comments": [_comment("/accept", "2026-01-10T09:00:00Z")]},
        ]
        result = acc.build_acceptances(raw_tickets)
        assert set(result["cp-clients"]) == {"run_1", "run_2"}

    def test_a_dataset_with_no_accept_comments_never_appears(self, monkeypatch):
        monkeypatch.setattr(acc, "_run_windows_for_dataset", lambda dataset_id, qa_results_dir=None: WINDOWS)
        raw_tickets = [{"number": 1, "labels": [{"name": "dataset:birth-registrations"}],
                        "comments": [_comment("still red", "2026-01-10T09:00:00Z")]}]
        assert acc.build_acceptances(raw_tickets) == {}


class TestRunWindowsAgainstRealCommittedHistory:
    def test_bdm_windows_are_real_sorted_and_open_ended(self):
        windows = acc._run_windows_for_dataset("birth-registrations")
        assert len(windows) > 50
        dates = [w[1] for w in windows]
        assert dates == sorted(dates)
        assert windows[-1][2] is None

    def test_every_cp_table_shares_the_same_real_collection_level_windows(self):
        """All 6 CP tables arrive together as one real collection
        delivery - qa_results/child-protection-family-support/
        child-protection/, not 6 separate per-table directories - so
        every one of the 6 real tickets must resolve to the exact same
        real run windows."""
        cp_tables = ["cp-clients", "cp-notifications", "cp-investigations", "cp-placements", "cp-carers", "cp-case-workers"]
        all_windows = [acc._run_windows_for_dataset(t) for t in cp_tables]
        assert all(w for w in all_windows), "no real CP windows found - has committed history changed shape?"
        assert all(w == all_windows[0] for w in all_windows)

    def test_an_unknown_dataset_id_returns_no_windows_rather_than_raising(self):
        assert acc._run_windows_for_dataset("not-a-real-dataset") == []
