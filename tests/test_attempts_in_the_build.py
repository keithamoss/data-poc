"""The build reads the record of every attempt (REQ-PIPE-411 criterion 12).

Driven through the real entry points: each run is opened and ended by
qa_results_writer (open_run, finish_run, close_attempt - what the
orchestrator's run step calls), the results file is rebuilt by
results_history.build_results_from_history, and the dashboard data built from
it by pipeline/build_dashboard_data. Nothing is written straight into a table.
"""
from __future__ import annotations

import json
import random
import uuid

import psycopg
import pytest

import rebuild_support
from pipeline import build_dashboard_data as bdd
from qa_tools.common import qa_results_reader, qa_results_writer, supply_db
from qa_tools.tools import results_history
from state_paths import fixed

CP = "child-protection"
AGENCY = "child-protection-family-support"
DS = "cp-clients"
WHEN = "2026-09-26T10:00:00+08:00"
BY = "tests@example.gov.au"
#: What a tool's message might quote from a supply - never published.
SECRET = "SECRET-ROW-VALUE-4471"

pytestmark = pytest.mark.asset("quarterly")


def _key() -> str:
    return "2099" + "".join(random.choice("0123456789") for _ in range(14))


def _supply() -> str:
    return f"{DS}@{_key()}"


def _timeout() -> BaseException:
    """A REAL lock timeout from one of this project's own connections."""
    table = f"pytest_build_lock_{uuid.uuid4().hex[:8]}"
    holder = supply_db.connect(reuse=False, label="test-build-lock-holder")
    try:
        holder.execute(f'CREATE TABLE public."{table}" (v int)')
        with holder.raw.transaction():
            holder.execute(f'LOCK TABLE public."{table}" IN ACCESS EXCLUSIVE MODE')
            ours = supply_db.connect(reuse=False, label="test-build-lock-timeout")
            try:
                ours.execute("SET lock_timeout = '50ms'")
                ours.execute(f'SELECT * FROM public."{table}"')
            except psycopg.errors.LockNotAvailable as exc:
                return exc
            finally:
                ours.close()
        raise AssertionError("no lock timeout")
    finally:
        holder.execute(f'DROP TABLE IF EXISTS public."{table}"')
        holder.close()


def _tries(run_id: str, *outcomes: str, supply: str | None = None, scope: str = "arrival",
           **purpose) -> str:
    """Each of `outcomes` an attempt at `run_id`, through the writer: 'C'
    completes it, 'X' crashes in a tool, 'Y' crashes outside one, 'T' times
    out, 'O' leaves it open (its process died)."""
    from qa_tools.tools import orchestrate

    stated = {"dataset_id": DS, "supply_id": supply, "scope": scope, **purpose}
    for outcome in outcomes:
        qa_results_writer.open_run(AGENCY, CP, run_id, WHEN, BY, purpose=stated)
        if outcome == "C":
            qa_results_writer.write_qa_result(
                AGENCY, CP, run_id, WHEN, "dataset_stats",
                {"arrival_record": {"run_id": run_id, "received_at": "2099-01-01T01:00:00+00:00",
                                    "delivery": "d"},
                 "row_counts": {}, "value_counts": {}, "check_aggregates": {}}, run_by=BY)
            qa_results_writer.finish_run(run_id)
        elif outcome == "X":
            failure = orchestrate.QaRunFailure(f"dbt-core failed - {SECRET}", tool="dbt-core",
                                               cause=ValueError(SECRET))
            qa_results_writer.close_attempt(run_id, failure)
        elif outcome == "Y":
            qa_results_writer.close_attempt(run_id, RuntimeError(SECRET))
        elif outcome == "T":
            qa_results_writer.close_attempt(run_id, _timeout())
        elif outcome == "O":
            # A process that died holding the attempt: its lock goes with it.
            attempt = qa_results_writer._open_attempts.pop(run_id)
            attempt._lock.close()
            attempt.ended = True
    return run_id


@pytest.fixture
def history(clean_qa_history, tmp_path, monkeypatch):
    monkeypatch.setattr(results_history, "reports_root", fixed(str(tmp_path / "reports")))
    monkeypatch.setattr(bdd, "reports_root", fixed(str(tmp_path / "reports")))

    class History:
        conn = clean_qa_history

        @staticmethod
        def facts() -> dict:
            return rebuild_support.rebuild(CP, tmp_path, monkeypatch)["run_facts"]

        @staticmethod
        def results_file() -> dict:
            return rebuild_support.rebuild(CP, tmp_path, monkeypatch)

        @staticmethod
        def page() -> dict:
            rebuild_support.rebuild(CP, tmp_path, monkeypatch)
            return {d["id"]: d for d in bdd.build_datasets(CP)}[DS]

    return History


def _run_id() -> str:
    return f"cp_clients__{_key()}"


class TestEachRunsRunTimeAndTries:
    """Criteria 2 and 3."""

    def test_one_completed_attempt_has_a_run_time_and_no_list(self, history):
        run = _tries(_run_id(), "C", supply=_supply())
        fact = history.facts()[run]
        assert isinstance(fact["run_time_ms"], int)
        assert "attempts" not in fact and fact["not_checked"] is False

    def test_a_crash_then_a_completion_lists_both_numbered_1_and_2(self, history):
        run = _tries(_run_id(), "X", "C", supply=_supply())
        tries = history.facts()[run]["attempts"]
        assert tries["count"] == 2 and tries["left_out"] == 0
        assert [(t["number"], t["outcome"], t["tool"], t["error_type"]) for t in tries["tries"]] == [
            (1, "TOOL-ERROR", "dbt-core", "ValueError"), (2, "COMPLETED", None, None)]
        assert all(t["run_time_ms"] is not None and t["began_at"] and t["ended_at"]
                   for t in tries["tries"])

    def test_nine_failed_attempts_show_the_first_the_newest_five_and_a_count(self, history):
        run = _tries(_run_id(), *"XYXYXYXYX", supply=_supply())
        tries = history.facts()[run]["attempts"]
        assert tries["count"] == 9
        assert [t["number"] for t in tries["tries"]] == [1, 5, 6, 7, 8, 9]
        assert tries["left_out"] == 3

    def test_run_seq_itself_never_leaves_the_database(self, history):
        run = _tries(_run_id(), "X", "C", supply=_supply())
        assert "run_seq" not in json.dumps(history.facts()[run])


class TestWhichRunsAreNotChecked:
    """Criteria 4, 5 and 7."""

    def test_an_arrival_whose_only_attempt_timed_out_is_not_checked_and_ranked(self, history):
        first = _tries(_run_id(), "C", supply=_supply())
        stuck = _tries(_run_id(), "T", supply=_supply())
        later = _tries(_run_id(), "C", supply=_supply())
        payload = history.results_file()
        facts = payload["run_facts"]
        assert facts[stuck]["not_checked"] is True
        assert facts[stuck]["run_time_ms"] is None
        assert facts[stuck]["attempts"]["tries"][0]["outcome"] == "TIMED-OUT"
        assert [facts[k]["rank"] for k in (first, stuck, later)] == [1, 2, 3]
        assert payload["not_checked"] == [stuck]
        assert not [r for r in payload["results"] if r["run_id"] == stuck]
        assert stuck not in {m["run_id"] for m in payload["runs"]}

    def test_a_decision_caused_full_recheck_that_crashed(self, history):
        supply = _supply()
        _tries(_run_id(), "C", supply=supply)
        recheck = _tries(f"cp_clients__recheck_{_key()}", "Y", supply=supply, scope="full",
                         caused_by_decision=424242)
        assert history.facts()[recheck]["not_checked"] is True

    def test_a_reloads_full_recheck_that_crashed(self, history):
        """TV1."""
        recheck = _tries(f"cp_clients__reload_{_key()}", "Y", supply=_supply(), scope="full",
                         caused_by_load=515151)
        assert history.facts()[recheck]["not_checked"] is True

    def test_a_readers_only_run_that_crashed_is_not(self, history):
        readers = _tries(f"cp_clients__readers_{_key()}", "Y", supply=_supply(),
                         scope="readers", caused_by_decision=7, reads_table="cp_clients",
                         period="2099-Q1")
        assert readers not in history.facts()

    def test_a_gate_application_run_that_crashed_is_not(self, history):
        gated = _tries(f"cp_clients__gate_{_key()}", "Y", supply=_supply(), scope="full",
                       caused_by_decision=8, gate_application=990001)
        assert gated not in history.facts()

    def test_a_run_that_completed_was_reopened_and_crashed_is_not_checked(self, history):
        """B2: the older completion must not stand as current."""
        run = _tries(_run_id(), "C", "X", supply=_supply())
        fact = history.facts()[run]
        assert fact["not_checked"] is True and fact["run_time_ms"] is None
        assert [t["outcome"] for t in fact["attempts"]["tries"]] == ["COMPLETED", "TOOL-ERROR"]

    def test_a_run_still_open_or_dead_unfound_is_not_checked(self, history):
        run = _tries(_run_id(), "O", supply=_supply())
        fact = history.facts()[run]
        assert fact["not_checked"] is True
        (only,) = fact["attempts"]["tries"]
        assert (only["outcome"], only["ended_at"], only["run_time_ms"]) == (None, None, None)

    def test_a_trials_attempts_are_not_emitted(self, history):
        trial = f"{supply_db.TRIAL_SCHEMA_PREFIX}{uuid.uuid4().hex[:10]}"
        qa_results_writer.open_run(AGENCY, CP, trial, WHEN, BY,
                                   purpose={"dataset_id": DS, "supply_id": None, "trial": True})
        qa_results_writer.close_attempt(trial, RuntimeError(SECRET))
        assert trial not in history.facts()


class TestNoMessageIsPublished:
    """Criterion 6 (TA Q5)."""

    def test_no_error_message_in_the_results_file_or_the_dashboard_data(self, history):
        _tries(_run_id(), "X", "C", supply=_supply())
        _tries(_run_id(), "Y", supply=_supply())
        payload = history.results_file()
        page = history.page()
        assert SECRET not in json.dumps(payload) and SECRET not in json.dumps(page)
        assert page["notChecked"] and page["runTimes"], "nothing about the runs was built"
        assert "error_message" not in json.dumps(page)

    def test_the_record_still_holds_it_for_the_terminal(self, history):
        run = _tries(_run_id(), "Y", supply=_supply())
        (ra,) = qa_results_reader.attempts_by_run(run_keys=[run]).values()
        assert ra.attempts[0]["error_message"] == SECRET


class TestTheDashboardData:
    """Criteria 2 to 4 at the page's data."""

    def test_each_listed_run_and_the_not_checked_ones(self, history):
        done = _tries(_run_id(), "X", "C", supply=_supply())
        stuck = _tries(_run_id(), "T", supply=_supply())
        page = history.page()
        (row,) = [r for r in page["runs"] if r["run_id"] == done]
        assert isinstance(row["run_time_ms"], int) and row["attempts"]["count"] == 2
        assert [n["run_id"] for n in page["notChecked"]] == [stuck]
        assert {t["run_id"] for t in page["runTimes"]} == {done, stuck}


class TestARefusedOlderFile:
    """Criterion 10: refused on the key absent, never on a null run time."""

    def test_a_file_written_before_this_is_refused_naming_the_rebuild(self, history):
        _tries(_run_id(), "C", supply=_supply())
        payload = history.results_file()
        for fact in payload["run_facts"].values():
            del fact["run_time_ms"]
        with open(results_history.results_path(CP), "w") as f:
            json.dump(payload, f)
        with pytest.raises(ValueError, match="mothman dashboard rebuild-results"):
            bdd.build_datasets(CP)

    def test_a_null_run_time_is_accepted(self, history):
        _tries(_run_id(), "Y", supply=_supply())
        assert history.page()["notChecked"][0]["run_time_ms"] is None


class TestTheSameHistoryBuildsTheSameBytes:
    """Criterion 11."""

    def test_twice(self, history):
        _tries(_run_id(), "X", "C", supply=_supply())
        _tries(_run_id(), "T", supply=_supply())
        first = json.dumps(history.page(), sort_keys=True, default=str)
        assert first == json.dumps(history.page(), sort_keys=True, default=str)


class TestPackageGatingReadsTheOneReader:
    """Criterion 1: pipeline/package_gating reads attempts through
    attempts_by_run, with its own query gone; its four forms are held by
    tests/test_package_gating.py."""

    def test_it_asks_the_reader(self, history, monkeypatch):
        from pipeline import package_gating

        asked = []
        real = qa_results_reader.attempts_by_run

        def spy(*a, **k):
            asked.append(k)
            return real(*a, **k)

        monkeypatch.setattr(qa_results_reader, "attempts_by_run", spy)
        with supply_db.connect(read_only=True, label="test-package-gating") as conn:
            package_gating.for_collection(conn, CP)
        assert asked and "dataset_ids" in asked[0]

