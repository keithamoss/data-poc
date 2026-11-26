"""mothman says how a QA run's try ended once (REQ-TEST-416 criterion 10).

Driven through orchestrate.run_one - the run step every arrival, re-check
and knock-on run goes through - with its tools replaced where a test needs
one to fail in a particular way, the counter an attempt's run time is read
from injected so every duration asserted is exact, and the reports that
follow a failure (the stage-failure report `mothman <short> qa` prints, the
processing pass's own line, the wizard's menu) driven for real behind it.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

from qa_tools.common import arrival_lifecycle, qa_results_writer, qa_store, run_summary, supply_db

ROOT = Path(__file__).resolve().parent.parent
COLLECTION = "child-protection"
WHEN = "2026-09-25T22:00:00+08:00"
BY = "tests@example.gov.au"
#: A message no other output carries, so "printed exactly once" is countable.
MESSAGE = "model cp_notifications_unique_7f3 depends on a node that was not found"

pytestmark = pytest.mark.asset("quarterly")


@pytest.fixture
def conn(clean_qa_history):
    supply_db.ensure_schemas(clean_qa_history)
    yield clean_qa_history


def _run_id() -> str:
    return "cp_notifications__2099" + "".join(random.choice("0123456789") for _ in range(14))


def _counting(monkeypatch, *readings: float) -> None:
    values = list(readings)
    monkeypatch.setattr(qa_results_writer, "_counter", lambda: values.pop(0))


class CompilationError(Exception):
    """Stands in for dbt's own exception type."""


def _raise(exc):
    def boom(*a, **k):
        raise exc
    return boom


def _dbt_fails(rid):
    from qa_tools.tools import orchestrate

    orchestrate._run_step(COLLECTION, "dbt-core", rid, _raise(CompilationError(MESSAGE)))


def _run(monkeypatch, run_id: str, then=None):
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
    table = f"pytest_summary_lock_{uuid.uuid4().hex[:8]}"
    holder = psycopg.connect(dsn)
    try:
        holder.execute(f'CREATE TABLE public."{table}" (v int)')
        holder.commit()
        holder.execute(f'LOCK TABLE public."{table}" IN ACCESS EXCLUSIVE MODE')
        ours = supply_db.connect(reuse=False, label="test-summary-lock-timeout")
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


def _summary(out: str, run_id: str) -> list[str]:
    """The lines that begin with the run id - the summary line - apart from
    run_one's own '--- <run> ---' header."""
    return [line for line in out.splitlines() if line.startswith(f"{run_id}: ")]


class TestEachSummaryLine:
    """Criterion 1."""

    def test_checked(self, conn, monkeypatch, capsys):
        _counting(monkeypatch, 0.0, 192.0)
        run_id = _run_id()
        _run(monkeypatch, run_id)
        assert _summary(capsys.readouterr().out, run_id) == [f"{run_id}: checked in 3m 12s"]

    def test_crashed_in_a_tool(self, conn, monkeypatch, capsys):
        from qa_tools.tools import orchestrate

        _counting(monkeypatch, 0.0, 64.0)
        run_id = _run_id()
        with pytest.raises(orchestrate.QaRunFailure):
            _run(monkeypatch, run_id, then=_dbt_fails)
        assert _summary(capsys.readouterr().out, run_id) == [
            f"{run_id}: crashed in dbt-core after 1m 04s (CompilationError)"]

    def test_timed_out(self, conn, monkeypatch, capsys, supply_dsn):
        _counting(monkeypatch, 0.0, 2700.0)
        run_id = _run_id()
        with pytest.raises(psycopg.errors.LockNotAvailable):
            _run(monkeypatch, run_id, then=lambda rid: _lock_timeout(supply_dsn))
        assert _summary(capsys.readouterr().out, run_id) == [
            f"{run_id}: timed out after 45m (LockNotAvailable)"]

    def test_ctrl_c_prints_stopped_after(self, conn, monkeypatch, capsys):
        _counting(monkeypatch, 0.0, 130.0)
        run_id = _run_id()
        with pytest.raises(KeyboardInterrupt):
            _run(monkeypatch, run_id, then=_raise(KeyboardInterrupt()))
        out = capsys.readouterr().out
        assert _summary(out, run_id) == [f"{run_id}: stopped after 2m 10s"]
        assert run_summary.NEXT_STEP not in out, "a stop is not a failed try"

    def test_a_failed_try_prints_its_message_beneath_once_then_the_next_step(
            self, conn, monkeypatch, capsys):
        from qa_tools.tools import orchestrate

        run_id = _run_id()
        with pytest.raises(orchestrate.QaRunFailure):
            _run(monkeypatch, run_id, then=_dbt_fails)
        out = capsys.readouterr().out.splitlines()
        at = next(i for i, line in enumerate(out) if line.startswith(f"{run_id}: crashed"))
        assert out[at + 1] == f"    {MESSAGE}"
        assert out[at + 2].strip() == run_summary.NEXT_STEP
        assert "\n".join(out).count(MESSAGE) == 1

    def test_slow_is_never_said(self, conn, monkeypatch, capsys):
        """Criterion 9: even for a run of hours."""
        _counting(monkeypatch, 0.0, 99000.0)
        run_id = _run_id()
        _run(monkeypatch, run_id)
        assert "slow" not in capsys.readouterr().out.lower()


class TestARetriedRunsLine:
    """Criterion 3."""

    def test_checked_on_the_second_try(self, conn, monkeypatch, capsys):
        from qa_tools.tools import orchestrate

        _counting(monkeypatch, 0.0, 64.0, 100.0, 292.0)
        run_id = _run_id()
        with pytest.raises(orchestrate.QaRunFailure):
            _run(monkeypatch, run_id, then=_dbt_fails)
        capsys.readouterr()
        _run(monkeypatch, run_id)
        assert _summary(capsys.readouterr().out, run_id) == [
            f"{run_id}: checked in 3m 12s, on the second try - the first crashed in "
            "dbt-core after 1m 04s"]

    def test_an_earlier_try_found_dead_has_no_time(self, conn, monkeypatch, capsys):
        run_id = _run_id()
        qa_store.begin_attempt(conn, run_id)  # a try whose process died
        _counting(monkeypatch, 0.0, 5.0)
        _run(monkeypatch, run_id)
        assert _summary(capsys.readouterr().out, run_id) == [
            f"{run_id}: checked in 5s, on the second try - the first did not finish, "
            "its run time unknown"]


class TestTheMessageIsPrintedOnce:
    """Criteria 2 and 8: the stage-failure report and the processing pass name
    the failure without repeating its message."""

    def _process(self, monkeypatch, run_id):
        steps = arrival_lifecycle.Steps(
            file_and_overlay=lambda arrival, among: None, entry_for=lambda arrival: {},
            run_one=lambda *a, **k: _run(monkeypatch, run_id, then=_dbt_fails),
            promote_after=lambda *a: None)
        arrival = SimpleNamespace(run_id=run_id, received_at=None, files_by_dataset={})
        return arrival_lifecycle.process(arrival, steps=steps, among=[], run_timestamp=WHEN,
                                         run_by=BY)

    def test_in_the_collections_qa_command(self, conn, monkeypatch, capsys):
        """`mothman cp qa`'s path: the lifecycle raises StageFailed, which the
        command reports through lifecycle_report.stage_failure."""
        from cli import lifecycle_report

        run_id = _run_id()
        with pytest.raises(arrival_lifecycle.StageFailed) as caught:
            self._process(monkeypatch, run_id)
        lifecycle_report.stage_failure(caught.value)
        out = capsys.readouterr().out
        assert out.count(MESSAGE) == 1, out
        assert f"STOPPED - {run_id}: the checks stage failed" in out

    def test_in_the_processing_pass(self, conn, monkeypatch, capsys):
        from qa_tools.common import delivery_log, processing_pass as pp, recheck
        from qa_tools.common import ticket_reconciler
        from qa_tools.tools import stage

        run_id = _run_id()
        arrival = SimpleNamespace(run_id=run_id, collection_id=COLLECTION,
                                  received_at=None, files_by_dataset={})
        monkeypatch.setattr(delivery_log, "record_all", lambda: None)
        monkeypatch.setattr(pp, "all_arrivals", lambda: [arrival])
        monkeypatch.setattr(pp, "unprocessed", lambda found, conn=None: list(found))
        monkeypatch.setattr(pp, "state_of", lambda a, rec: pp.UNCHECKED)
        monkeypatch.setattr(stage, "stage_arrival", lambda collection_id, a: None)
        monkeypatch.setattr(pp, "_one", lambda *a, **k: self._process(monkeypatch, run_id))
        monkeypatch.setattr(recheck, "run_all_owed", lambda **k: [])
        monkeypatch.setattr(ticket_reconciler, "service_from_env", lambda: None)
        said: list[str] = []
        report = pp.run_pass(run_by=BY, say=said.append)
        # `mothman pipeline process` then prints each failure (cli/pipeline.py).
        printed = capsys.readouterr().out + "\n".join(said) + "\n".join(
            f"FAILED {what}: {why}" for what, why in report.failures)
        assert report.failures, "the arrival failed"
        assert printed.count(MESSAGE) == 1, printed


_CHILD = """
import random, sys
from qa_tools.common import qa_results_writer
from qa_tools.tools import orchestrate

values = [0.0, 64.0]
qa_results_writer._counter = lambda: values.pop(0)

def boom():
    raise ValueError("the child's tool broke")

def inner(collection_id, entry, rid, run_timestamp, run_by, reference_run_id, on_step):
    qa_results_writer.open_run("a", "b", rid, run_timestamp, run_by)
    orchestrate._run_step(collection_id, "Soda Core", rid, boom)

orchestrate._run_one_inner = inner
try:
    orchestrate.run_one("child-protection", {"run_id": sys.argv[1]}, sys.argv[2], sys.argv[3])
except orchestrate.QaRunFailure:
    pass
"""


class TestTheSameWordsWithoutColour:
    """Criterion 6: NO_COLOR set and stdout a pipe - the same words."""

    def test_through_a_pipe_with_no_color(self, conn):
        run_id = _run_id()
        env = dict(os.environ, NO_COLOR="1")
        got = subprocess.run([sys.executable, "-c", _CHILD, run_id, WHEN, BY], cwd=ROOT,
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, timeout=120)
        assert got.returncode == 0, got.stderr
        lines = got.stdout.splitlines()
        at = lines.index(f"{run_id}: crashed in Soda Core after 1m 04s (ValueError)")
        assert lines[at + 1:at + 3] == ["    the child's tool broke",
                                         f"  {run_summary.NEXT_STEP}"]
        assert "\x1b[" not in got.stdout


class TestTheWizard:
    """Criterion 7: a failed try returns to the menu with its line and next
    step, and a kept run's panel says its run time."""

    def test_a_failed_try_returns_to_the_menu(self, conn, monkeypatch, capsys):
        from cli import app

        run_id = _run_id()
        monkeypatch.setattr(app, "_qa_menu", lambda: _run(monkeypatch, run_id, then=_dbt_fails))
        app._run_choice(app._MAIN_MENU_QA)  # returns: nothing escapes to end the session
        out = capsys.readouterr().out
        assert f"{run_id}: crashed in dbt-core after" in out
        assert run_summary.NEXT_STEP in out.replace("\n", " ") or run_summary.NEXT_STEP in out

    def test_a_failed_stage_returns_to_the_menu_without_the_message_again(
            self, conn, monkeypatch, capsys):
        from cli import app

        run_id = _run_id()
        monkeypatch.setattr(app, "_qa_menu",
                            lambda: TestTheMessageIsPrintedOnce()._process(monkeypatch, run_id))
        app._run_choice(app._MAIN_MENU_QA)
        out = capsys.readouterr().out
        assert out.count(MESSAGE) == 1 and "STOPPED" in out

    def test_an_unsaid_failure_still_escapes(self, monkeypatch):
        from cli import app

        monkeypatch.setattr(app, "_qa_menu", _raise(ValueError("not a try")))
        with pytest.raises(ValueError):
            app._run_choice(app._MAIN_MENU_QA)

    def test_the_recorded_panel_says_the_run_time(self, conn, monkeypatch, capsys):
        from cli import common

        _counting(monkeypatch, 0.0, 192.0)
        run_id = _run_id()
        _run(monkeypatch, run_id)
        capsys.readouterr()
        common.report_recorded(run_id, 3)
        assert "checked in 3m 12s" in capsys.readouterr().out
