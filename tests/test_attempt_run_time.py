"""Every attempt's real run time, and how a tool's failure is recorded
(REQ-PIPE-409 criterion 11, REQ-PIPE-410 criterion 9).

Driven through orchestrate.run_one - the one entry every arrival, re-check
and knock-on run goes through - with its tools replaced where a test needs
one to fail in a particular way, against this worker's own database. THE
COUNTER IS INJECTED (qa_results_writer._counter), so every run time asserted
here is exact: nothing sleeps, and nothing reads the clock to work one out.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from qa_tools.common import parallel_orchestrate, qa_results_writer, qa_store, supply_db

COLLECTION = "child-protection"
WHEN = "2026-09-25T22:00:00+08:00"
BY = "tests@example.gov.au"
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=timezone(timedelta(hours=8)))

pytestmark = pytest.mark.asset("quarterly")


@pytest.fixture
def conn(clean_qa_history):
    supply_db.ensure_schemas(clean_qa_history)
    yield clean_qa_history


def _run_id() -> str:
    return "cp_notifications__2099" + "".join(random.choice("0123456789") for _ in range(14))


class _Counter:
    """A monotonic counter that reads the values it is given, in turn."""

    def __init__(self, *readings: float) -> None:
        self.readings = list(readings)

    def __call__(self) -> float:
        return self.readings.pop(0)


def _counting(monkeypatch, *readings: float) -> _Counter:
    counter = _Counter(*readings)
    monkeypatch.setattr(qa_results_writer, "_counter", counter)
    return counter


def _run(monkeypatch, run_id: str, then=None):
    """orchestrate.run_one with its tools replaced by `then` - opened for real
    first, and finished for real where `then` returns."""
    from qa_tools.tools import orchestrate

    def inner(collection_id, entry, rid, run_timestamp, run_by, reference_run_id, on_step):
        qa_results_writer.open_run("a", "b", rid, run_timestamp, run_by)
        if then is not None:
            then(rid)
        qa_results_writer.finish_run(rid)
        return []

    monkeypatch.setattr(orchestrate, "_run_one_inner", inner)
    return orchestrate.run_one(COLLECTION, {"run_id": run_id}, WHEN, BY)


def _lock_timeout(dsn: str) -> None:
    """A REAL lock timeout on one of this project's own connections."""
    table = f"pytest_runtime_lock_{uuid.uuid4().hex[:8]}"
    holder = psycopg.connect(dsn)
    try:
        holder.execute(f'CREATE TABLE public."{table}" (v int)')
        holder.commit()
        holder.execute(f'LOCK TABLE public."{table}" IN ACCESS EXCLUSIVE MODE')
        ours = supply_db.connect(reuse=False, label="test-runtime-lock-timeout")
        try:
            ours.execute("SET lock_timeout = '50ms'")
            ours.execute(f'SELECT * FROM public."{table}"')
        finally:
            ours.close()
    finally:
        holder.rollback()
        holder.execute(f'DROP TABLE IF EXISTS public."{table}"')
        holder.commit()
        holder.close()


def _attempts(conn, run_id: str) -> list[dict]:
    got = qa_store.attempts_of(conn, run_id)
    assert got, f"no attempt recorded for {run_id}"
    return got


class CompilationError(Exception):
    """Stands in for dbt's own exception type - what a dbt-core step raises."""


def _tool(tool: str, call):
    """One tool's step, as the run step makes it."""
    from qa_tools.tools import orchestrate

    return lambda rid: orchestrate._run_step(COLLECTION, tool, rid, call)


def _raise(exc: BaseException):
    def boom():
        raise exc
    return boom


# ---------------------------------------------------------------------------
# REQ-PIPE-409: the run time
# ---------------------------------------------------------------------------

class TestEveryEndedAttemptRecordsItsRunTime:

    def test_a_completed_attempt_records_the_counters_milliseconds(self, conn, monkeypatch):
        _counting(monkeypatch, 100.0, 103.25)
        run_id = _run_id()
        _run(monkeypatch, run_id)
        (only,) = _attempts(conn, run_id)
        assert (only["outcome"], only["elapsed_ms"]) == (qa_store.COMPLETED, 3250)

    def test_a_replay_clock_moving_days_records_the_real_milliseconds(self, conn, monkeypatch):
        """Criterion 5: the stamps are the replay's, the run time is not."""
        from bootstrap import replay_clock

        _counting(monkeypatch, 10.0, 10.5)
        run_id = _run_id()
        with replay_clock.replaying():
            replay_clock.anchor(LONG_AGO)
            _run(monkeypatch, run_id,
                 then=lambda rid: replay_clock.advance_to(LONG_AGO + timedelta(days=6)))
        (only,) = _attempts(conn, run_id)
        assert only["elapsed_ms"] == 500
        # THE STAMPS STILL COME FROM THE ONE CLOCK (criterion 6).
        assert only["ended_at"] - only["began_at"] > timedelta(days=5, hours=23)
        assert only["began_at"] < LONG_AGO + timedelta(minutes=5)

    def test_an_attempt_found_dead_keeps_no_run_time(self, conn):
        """Criterion 3, at the recorder: begin_attempt closes the dead one with
        neither an end nor a run time."""
        run_key = _run_id()
        qa_store.begin_attempt(conn, run_key)
        qa_store.begin_attempt(conn, run_key)
        dead, _ = _attempts(conn, run_key)
        assert (dead["outcome"], dead["ended_at"], dead["elapsed_ms"]) == (
            qa_store.INTERRUPTED, None, None)

    def test_a_crashed_attempt_records_its_own(self, conn, monkeypatch):
        _counting(monkeypatch, 0.0, 2.0)
        run_id = _run_id()
        with pytest.raises(RuntimeError):
            _run(monkeypatch, run_id, then=lambda rid: _raise(RuntimeError("not a tool"))())
        (only,) = _attempts(conn, run_id)
        assert (only["outcome"], only["elapsed_ms"]) == (qa_store.CRASHED, 2000)

    def test_a_timed_out_attempt_records_its_own(self, conn, monkeypatch, supply_dsn):
        _counting(monkeypatch, 5.0, 5.75)
        run_id = _run_id()
        with pytest.raises(psycopg.errors.LockNotAvailable):
            _run(monkeypatch, run_id, then=lambda rid: _lock_timeout(supply_dsn))
        (only,) = _attempts(conn, run_id)
        assert (only["outcome"], only["elapsed_ms"]) == (qa_store.TIMED_OUT, 750)

    def test_an_interrupted_attempt_with_an_end_records_its_own(self, conn, monkeypatch):
        _counting(monkeypatch, 1.0, 1.001)
        run_id = _run_id()
        with pytest.raises(KeyboardInterrupt):
            _run(monkeypatch, run_id, then=lambda rid: _raise(KeyboardInterrupt())())
        (only,) = _attempts(conn, run_id)
        assert (only["outcome"], only["elapsed_ms"]) == (qa_store.INTERRUPTED, 1)

    def test_a_crash_then_a_completion_takes_the_completed_ones(self, conn, monkeypatch):
        _counting(monkeypatch, 0.0, 9.0, 20.0, 21.5)
        run_id = _run_id()
        with pytest.raises(RuntimeError):
            _run(monkeypatch, run_id, then=lambda rid: _raise(RuntimeError("first"))())
        _run(monkeypatch, run_id)
        got = _attempts(conn, run_id)
        assert [a["elapsed_ms"] for a in got] == [9000, 1500]
        assert qa_store.run_time_ms(got) == 1500

    def test_a_completed_run_reopened_and_crashed_has_no_run_time(self, conn, monkeypatch):
        """Criterion 7 (B2): the newest attempt, or none."""
        _counting(monkeypatch, 0.0, 1.0, 5.0, 7.0)
        run_id = _run_id()
        _run(monkeypatch, run_id)
        with pytest.raises(RuntimeError):
            _run(monkeypatch, run_id, then=lambda rid: _raise(RuntimeError("reopened"))())
        got = _attempts(conn, run_id)
        assert [a["outcome"] for a in got] == [qa_store.COMPLETED, qa_store.CRASHED]
        assert qa_store.run_time_ms(got) is None

    def test_a_run_whose_newest_attempt_is_still_open_has_no_run_time(self, conn):
        run_key = _run_id()
        qa_store.begin_attempt(conn, run_key)
        assert qa_store.run_time_ms(_attempts(conn, run_key)) is None


class TestTheTableHoldsTheRunTimeToItsEnd:
    """Criterion 8: the database itself refuses a run time without an end,
    an end without one, and a negative one."""

    @pytest.mark.parametrize("assignment", [
        "ended_at = now(), outcome = 'COMPLETED'",
        "elapsed_ms = 5",
        "ended_at = now(), outcome = 'COMPLETED', elapsed_ms = -1",
    ])
    def test_refused(self, conn, assignment):
        run_key = _run_id()
        seq = qa_store.begin_attempt(conn, run_key)
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(f'UPDATE "{qa_store.SCHEMA}".run_attempt SET {assignment} '
                         "WHERE run_key = ? AND run_seq = ?", [run_key, seq])

    def test_a_tool_error_must_name_its_tool_and_nothing_else_may(self, conn):
        run_key = _run_id()
        seq = qa_store.begin_attempt(conn, run_key)
        with pytest.raises(psycopg.errors.CheckViolation):
            qa_store.end_attempt(conn, run_key, seq, qa_store.TOOL_ERROR, elapsed_ms=1,
                                 error_type="X", error_message="m")
        with pytest.raises(psycopg.errors.CheckViolation):
            qa_store.end_attempt(conn, run_key, seq, qa_store.CRASHED, elapsed_ms=1,
                                 error_type="X", error_message="m", tool="dbt-core")

    def test_the_schema_is_at_least_version_51(self):
        """Version 51 brought this shape in; a later bump (52, the history
        anchor, REQ-GEN-404) is work succeeding, not this shape going
        (CLAUDE.md test rule 4)."""
        assert qa_store.SCHEMA_VERSION >= 51


# ---------------------------------------------------------------------------
# REQ-PIPE-410: which tool, and how
# ---------------------------------------------------------------------------

class TestAToolsFailureIsAToolError:

    def test_a_dbt_core_failure_is_tool_error_naming_dbt_core_with_dbts_type(
            self, conn, monkeypatch):
        from qa_tools.tools import orchestrate

        run_id = _run_id()
        with pytest.raises(orchestrate.QaRunFailure):
            _run(monkeypatch, run_id,
                 then=_tool("dbt-core", _raise(CompilationError("model cp_x failed to compile"))))
        (only,) = _attempts(conn, run_id)
        assert (only["outcome"], only["tool"], only["error_type"], only["error_message"]) == (
            qa_store.TOOL_ERROR, "dbt-core", "CompilationError", "model cp_x failed to compile")
        assert only["elapsed_ms"] is not None

    def test_a_non_tool_exception_still_crashes_with_no_tool(self, conn, monkeypatch):
        run_id = _run_id()
        with pytest.raises(ValueError):
            _run(monkeypatch, run_id, then=lambda rid: _raise(ValueError("the reconciliation"))())
        (only,) = _attempts(conn, run_id)
        assert (only["outcome"], only["tool"], only["error_type"]) == (
            qa_store.CRASHED, None, "ValueError")

    def test_a_lock_timeout_inside_a_tool_step_is_timed_out_with_its_message(
            self, conn, monkeypatch, supply_dsn):
        from qa_tools.tools import orchestrate

        run_id = _run_id()
        with pytest.raises(orchestrate.QaRunFailure):
            _run(monkeypatch, run_id,
                 then=_tool("Soda Core", lambda: _lock_timeout(supply_dsn)))
        (only,) = _attempts(conn, run_id)
        assert (only["outcome"], only["tool"], only["error_type"]) == (
            qa_store.TIMED_OUT, None, "LockNotAvailable")
        assert "lock timeout" in only["error_message"]

    def test_two_tools_failing_records_dbt_cores_lock_timeout_not_the_others(
            self, conn, monkeypatch, supply_dsn):
        """B3: both lanes fail; dbt-core ranks first and its failure was a lock
        timeout, so the attempt is TIMED-OUT with dbt-core's error."""
        from qa_tools.tools import orchestrate

        def lanes(rid):
            dbt = lambda: orchestrate._run_step(  # noqa: E731
                COLLECTION, "dbt-core", rid, lambda: _lock_timeout(supply_dsn))
            soda = lambda: orchestrate._run_step(  # noqa: E731
                COLLECTION, "Soda Core", rid, _raise(ValueError("soda broke")))
            parallel_orchestrate.side_by_side([dbt], soda, concurrent=True,
                                              rank=orchestrate._tool_rank)

        run_id = _run_id()
        with pytest.raises(orchestrate.QaRunFailure) as caught:
            _run(monkeypatch, run_id, then=lanes)
        assert caught.value.tool == "dbt-core"
        (only,) = _attempts(conn, run_id)
        assert (only["outcome"], only["error_type"]) == (qa_store.TIMED_OUT, "LockNotAvailable")

    def test_the_tool_and_cause_come_from_fields_never_the_chain(
            self, conn, monkeypatch, supply_dsn):
        """B3, its other half: dbt-core's own failure is a plain error while
        another tool's lock timeout sits in its context - as a lane's
        re-raise can leave it. The attempt names dbt-core and its error."""
        from qa_tools.tools import orchestrate

        def tangled(rid):
            try:
                orchestrate._run_step(COLLECTION, "Soda Core", rid,
                                      lambda: _lock_timeout(supply_dsn))
            except orchestrate.QaRunFailure:
                # Raised while Soda's failure is being handled, so Soda's
                # failure becomes dbt-core's __context__.
                orchestrate._run_step(COLLECTION, "dbt-core", rid,
                                      _raise(CompilationError("dbt's own")))

        run_id = _run_id()
        with pytest.raises(orchestrate.QaRunFailure) as caught:
            _run(monkeypatch, run_id, then=tangled)
        assert caught.value.tool == "dbt-core"
        assert isinstance(caught.value.__context__.__context__, orchestrate.QaRunFailure)
        (only,) = _attempts(conn, run_id)
        assert (only["outcome"], only["tool"], only["error_type"], only["error_message"]) == (
            qa_store.TOOL_ERROR, "dbt-core", "CompilationError", "dbt's own")

    def test_the_retry_completes_with_both_attempts_kept(self, conn, monkeypatch):
        from qa_tools.tools import orchestrate

        run_id = _run_id()
        with pytest.raises(orchestrate.QaRunFailure):
            _run(monkeypatch, run_id, then=_tool("Evidently", _raise(KeyError("ref"))))
        _run(monkeypatch, run_id)
        got = _attempts(conn, run_id)
        assert [(a["outcome"], a["tool"]) for a in got] == [
            (qa_store.TOOL_ERROR, "Evidently"), (qa_store.COMPLETED, None)]
        assert got[0]["run_seq"] < got[1]["run_seq"]

    def test_each_tool_is_named_by_the_run_steps_one_string(self):
        from qa_tools.tools import orchestrate

        assert orchestrate._TOOL_ORDER == ("dbt-core", "Soda Core", "datacontract-cli",
                                           "Evidently")
