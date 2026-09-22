"""Tests for qa_tools/common/acceptance_sync.py (running-thoughts.md #6,
"read-only tension: accepting/rejecting amber supplies"). `/accept` was
built 2026-09-18; `/reject` added 2026-09-19 once Keith resolved the
amber-governance question itself (plans/conceptual-design.md Thread A)
via AskUserQuestion: option 3, an explicit per-run human decision,
most-recent-comment-wins on conflict. match_decisions()/build_decisions()
are pure (plain dict fixtures, no real gh/network); _run_windows_for_
dataset() is tested against this repo's own real committed qa_results/
history, same "prove it against the real thing, not a fixture built to
match it" reasoning tests/test_github_links.py already uses."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from qa_tools.common import acceptance_sync as acc


def _comment(body, created, author="keithamoss", url="https://github.com/x/y/issues/1#issuecomment-1"):
    return {"author": {"login": author}, "body": body, "createdAt": created, "url": url}


WINDOWS = [
    ("run_1", date(2026, 1, 1), date(2026, 1, 8)),
    ("run_2", date(2026, 1, 8), date(2026, 1, 15)),
    ("run_3", date(2026, 1, 15), None),  # open-ended, the latest run
]


class TestMatchDecisions:
    def test_a_comment_inside_a_runs_window_matches_that_run(self):
        result = acc.match_decisions([_comment("/accept", "2026-01-10T09:00:00Z")], WINDOWS)
        assert set(result) == {"run_2"}
        assert result["run_2"]["decision"] == "accept"
        assert result["run_2"]["decided_by"] == "keithamoss"
        assert result["run_2"]["decided_at"] == "2026-01-10T09:00:00Z"

    def test_a_reject_comment_matches_the_same_way_as_accept(self):
        result = acc.match_decisions([_comment("/reject", "2026-01-10T09:00:00Z")], WINDOWS)
        assert set(result) == {"run_2"}
        assert result["run_2"]["decision"] == "reject"

    def test_a_comment_before_any_real_run_matches_nothing(self):
        result = acc.match_decisions([_comment("/accept", "2025-12-01T09:00:00Z")], WINDOWS)
        assert result == {}

    def test_a_comment_in_the_open_ended_latest_window_matches_the_last_run(self):
        result = acc.match_decisions([_comment("/accept", "2026-06-01T09:00:00Z")], WINDOWS)
        assert set(result) == {"run_3"}

    def test_case_insensitive_and_allows_trailing_text(self):
        result = acc.match_decisions([_comment("/ACCEPT confirmed with the provider", "2026-01-10T09:00:00Z")], WINDOWS)
        assert set(result) == {"run_2"}

    def test_reject_is_also_case_insensitive_and_allows_trailing_text(self):
        result = acc.match_decisions([_comment("/REJECT - data still wrong", "2026-01-10T09:00:00Z")], WINDOWS)
        assert set(result) == {"run_2"}
        assert result["run_2"]["decision"] == "reject"

    def test_a_comment_that_doesnt_start_with_slash_accept_is_ignored(self):
        result = acc.match_decisions([_comment("I don't accept this", "2026-01-10T09:00:00Z")], WINDOWS)
        assert result == {}

    def test_a_bare_word_accept_with_no_slash_is_ignored(self):
        result = acc.match_decisions([_comment("accept", "2026-01-10T09:00:00Z")], WINDOWS)
        assert result == {}

    def test_a_bare_word_reject_with_no_slash_is_ignored(self):
        result = acc.match_decisions([_comment("reject", "2026-01-10T09:00:00Z")], WINDOWS)
        assert result == {}

    def test_the_most_recent_decision_wins_when_several_target_the_same_run(self):
        result = acc.match_decisions([
            _comment("/accept", "2026-01-12T09:00:00Z", author="second"),
            _comment("/accept", "2026-01-09T09:00:00Z", author="first"),
        ], WINDOWS)
        assert result["run_2"]["decided_by"] == "second"

    def test_a_later_reject_overrides_an_earlier_accept_on_the_same_run(self):
        """Keith's own explicit call, 2026-09-19: if a run's window
        carries both an /accept and a /reject, whichever happened LAST
        wins, regardless of which command it was - not "reject always
        wins" or "accept always wins"."""
        result = acc.match_decisions([
            _comment("/accept", "2026-01-09T09:00:00Z", author="first"),
            _comment("/reject", "2026-01-12T09:00:00Z", author="second"),
        ], WINDOWS)
        assert result["run_2"] == {
            "decision": "reject", "decided_by": "second",
            "decided_at": "2026-01-12T09:00:00Z",
            "comment_url": "https://github.com/x/y/issues/1#issuecomment-1",
        }

    def test_a_later_accept_overrides_an_earlier_reject_on_the_same_run(self):
        result = acc.match_decisions([
            _comment("/reject", "2026-01-09T09:00:00Z", author="first"),
            _comment("/accept", "2026-01-12T09:00:00Z", author="second"),
        ], WINDOWS)
        assert result["run_2"]["decision"] == "accept"
        assert result["run_2"]["decided_by"] == "second"

    def test_a_run_with_no_matching_comment_never_appears_in_the_result(self):
        result = acc.match_decisions([_comment("/accept", "2026-01-10T09:00:00Z")], WINDOWS)
        assert "run_1" not in result
        assert "run_3" not in result


class TestBuildDecisions:
    def test_groups_comments_by_the_tickets_own_dataset_label(self, monkeypatch):
        monkeypatch.setattr(acc, "_run_windows_for_dataset", lambda dataset_id, qa_results_dir=None: WINDOWS)
        raw_tickets = [
            {"number": 1, "labels": [{"name": "qa-ticket"}, {"name": "dataset:birth-registrations"}],
             "comments": [_comment("/accept", "2026-01-10T09:00:00Z")]},
        ]
        result = acc.build_decisions(raw_tickets)
        assert set(result) == {"birth-registrations"}
        assert set(result["birth-registrations"]) == {"run_2"}

    def test_a_ticket_with_no_dataset_label_is_skipped(self, monkeypatch):
        monkeypatch.setattr(acc, "_run_windows_for_dataset", lambda dataset_id, qa_results_dir=None: WINDOWS)
        raw_tickets = [{"number": 1, "labels": [{"name": "qa-ticket"}],
                        "comments": [_comment("/accept", "2026-01-10T09:00:00Z")]}]
        assert acc.build_decisions(raw_tickets) == {}

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
             "comments": [_comment("/reject", "2026-01-10T09:00:00Z")]},
        ]
        result = acc.build_decisions(raw_tickets)
        assert set(result["cp-clients"]) == {"run_1", "run_2"}

    def test_a_dataset_with_no_decision_comments_never_appears(self, monkeypatch):
        monkeypatch.setattr(acc, "_run_windows_for_dataset", lambda dataset_id, qa_results_dir=None: WINDOWS)
        raw_tickets = [{"number": 1, "labels": [{"name": "dataset:birth-registrations"}],
                        "comments": [_comment("still red", "2026-01-10T09:00:00Z")]}]
        assert acc.build_decisions(raw_tickets) == {}


class TestRunWindowsAgainstRealCommittedHistory:
    def test_bdm_windows_are_real_sorted_and_open_ended(self):
        # The floor is DERIVED from the committed tree, not written down.
        # It used to be `> 50`, chosen when BDM's history was 352 runs;
        # cutting it to 30 deliveries on 2026-09-23 left 32 windows and
        # this failed for a reason unrelated to what it tests. What the
        # assertion actually means is "every committed run produced a
        # window" - so count the runs and say that.
        committed_runs = len(list(
            (Path(__file__).resolve().parent.parent / "qa_results"
             / "registry-services" / "civil-registration").iterdir()))
        windows = acc._run_windows_for_dataset("birth-registrations")
        assert len(windows) > 0, "no windows at all - committed history missing?"
        assert len(windows) <= committed_runs, (
            f"{len(windows)} windows from {committed_runs} committed runs - "
            "a window per run is the ceiling, so more means duplicates"
        )
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


class TestRunWindowsWithTiedArrivedDates:
    """Real bug found live, 2026-09-19, while adding /reject test
    coverage against real current committed history: this project's own
    full BDM pipeline regeneration (same day) left MOST real runs
    sharing their own arrived_date with another real run (352 real runs,
    only 123 distinct dates, AS THE TREE STOOD THEN - BDM's history was
    cut to 30 deliveries on 2026-09-23, so today's counts are smaller;
    the tie condition this class covers is unaffected, since it is
    produced by resupplies arriving on a day another run also arrived) - this module's own long-documented intent
    ("resolve to whichever sorts first") turns out not to match what the
    code actually did: the FIRST tied entry got window_end ==
    window_start (a zero-width, structurally unmatchable window, since
    `created >= start and created < end` can never be true when
    start==end), so a same-day comment silently resolved to whichever
    run sorted SECOND (or last, for 3+-way ties) - the opposite of the
    documented intent, and a real run a human could never actually
    accept/reject via a same-day comment."""

    def _fake_stats(self, arrived_dates_by_run):
        def read_dataset_stats(agency, dataset, run_id, qa_results_dir=None):
            return {"manifest_entry": {"arrived_date": arrived_dates_by_run[run_id]}}
        return read_dataset_stats

    def test_the_first_of_two_same_day_runs_gets_a_real_non_empty_window(self, monkeypatch):
        arrived = {"run_a": "2026-01-10", "run_b": "2026-01-10", "run_c": "2026-01-15"}
        monkeypatch.setattr(acc, "list_run_ids", lambda agency, dataset, qa_results_dir=None: ["run_a", "run_b", "run_c"])
        monkeypatch.setattr(acc, "read_dataset_stats", self._fake_stats(arrived))

        windows = acc._run_windows_for_dataset("birth-registrations")

        by_run = {run_id: (start, end) for run_id, start, end in windows}
        assert by_run["run_a"] == (date(2026, 1, 10), date(2026, 1, 15))

    def test_the_second_of_two_same_day_runs_is_simply_omitted_not_given_a_broken_window(self, monkeypatch):
        arrived = {"run_a": "2026-01-10", "run_b": "2026-01-10", "run_c": "2026-01-15"}
        monkeypatch.setattr(acc, "list_run_ids", lambda agency, dataset, qa_results_dir=None: ["run_a", "run_b", "run_c"])
        monkeypatch.setattr(acc, "read_dataset_stats", self._fake_stats(arrived))

        windows = acc._run_windows_for_dataset("birth-registrations")

        assert "run_b" not in {run_id for run_id, _, _ in windows}

    def test_a_same_day_comment_matches_the_run_that_sorts_first(self, monkeypatch):
        arrived = {"run_a": "2026-01-10", "run_b": "2026-01-10", "run_c": "2026-01-15"}
        monkeypatch.setattr(acc, "list_run_ids", lambda agency, dataset, qa_results_dir=None: ["run_a", "run_b", "run_c"])
        monkeypatch.setattr(acc, "read_dataset_stats", self._fake_stats(arrived))
        windows = acc._run_windows_for_dataset("birth-registrations")

        result = acc.match_decisions([_comment("/accept", "2026-01-10T09:00:00Z")], windows)

        assert set(result) == {"run_a"}
