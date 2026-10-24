"""What a run records about what it read, and about each attempt at it
(REQ-PIPE-279 criteria 1 to 8 and 23; tests 10 and 19 to 25 of criteria
27 and 28).

Two halves of one record, both written at run time and both read later
without the code of the day:

  - qa.check_read: for every cross-table result, the supply of EVERY table
    its check reads, its own included, and in what state - so placement
    and the gate filter on what a result read rather than on days, times
    or run ids;
  - qa.run.run_seq and qa.run_attempt: the order runs were OPENED, and
    every attempt at one with how it ended - so a timed-out or crashed
    attempt is still on record once its retry has replaced its results.

Driven through the real entry points - qa_results_writer.write_qa_result,
orchestrate.run_one, the `mothman debug` command, trial.discard - against
this worker's own database. A run's tools are replaced where a test needs
one to fail in a particular way; nothing else is.
"""
from __future__ import annotations

import os
import random
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psycopg
import pytest

from qa_tools.common import qa_results_writer, qa_store, supply_db
from qa_tools.common import tables_read as tr

ROOT = Path(__file__).resolve().parent.parent
AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-25T22:00:00+08:00"
BY = "tests@example.gov.au"
CHECK = "data-asset-1.child-protection-family-support.child-protection"
#: Real check ids from this repo's own sources, asserted present below so a
#: renamed check cannot turn these tests into ones about nothing.
CLIENT_REF = f"{CHECK}.cp-notifications.cp_client_id.relationships_dbt"
WORKER_REF = f"{CHECK}.cp-notifications.assigned_worker_id.relationships_dbt"
ESCALATION = f"{CHECK}.cp-notifications.notification_id.escalation_completeness_dbt"


def _key() -> str:
    return "2099" + "".join(random.choice("0123456789") for _ in range(14))


def _run_id(table: str = "cp_notifications") -> str:
    return f"{table}__{_key()}"


@pytest.fixture
def conn(clean_qa_history):
    supply_db.ensure_schemas(clean_qa_history)
    yield clean_qa_history


@pytest.fixture(autouse=True)
def _real_declarations():
    tr.forget_declared_reads()
    reads = tr.declared_reads()
    for check, table in ((CLIENT_REF, "cp_clients"), (WORKER_REF, "cp_case_workers"),
                         (ESCALATION, "cp_investigations")):
        assert reads.get(check) == [table], f"{check} no longer declares it reads {table}"


def _resolve(conn, run_id: str, **kw) -> None:
    supply_db.record_resolution(conn, supply_db.Resolution(
        run_id=run_id, schema=supply_db.run_schema(run_id), **kw))


def _result(check_id: str, dataset_id: str = "cp-notifications", status: str = "pass") -> dict:
    return {"check_id": check_id, "check_name": check_id.rsplit(".", 1)[-1],
            "dataset_id": dataset_id, "status": status}


def _write(run_id: str, *records: dict) -> None:
    qa_results_writer.write_qa_result(AGENCY, COLLECTION, run_id, WHEN, "dbt", {"raw": True},
                                      verified=[dict(r) for r in records])


def _reads(conn, run_id: str) -> dict[str, dict[str, tuple]]:
    """check id -> {table: (state, supply id, contested, contested files)}."""
    out: dict[str, dict[str, tuple]] = {}
    for check, table, state, supply, contested, files in conn.execute(
            f'SELECT c.check_id, k.logical_table, k.state, k.supply_id, k.contested, '
            f'k.contested_files FROM "{qa_store.SCHEMA}".check_read k '
            f'JOIN "{qa_store.SCHEMA}".check_result c ON c.id = k.check_result_id '
            "WHERE c.run_key = ? ORDER BY c.check_id, k.logical_table", [run_id]).fetchall():
        out.setdefault(check, {})[table] = (state, supply, contested, list(files or []))
    return out


def _period_and_staged(own_key: str) -> dict:
    """A notifications run that read its own table from staging and Clients
    from the period, both with the supply they held."""
    return {
        "resolved": {"cp_notifications": f"cp_notifications__{own_key}", "cp_clients": "cp_clients"},
        "supply_of": {"cp_notifications": f"cp-notifications@{own_key}",
                      "cp_clients": "cp-clients@20990101010000000000"},
        "source": {"cp_notifications": "staging", "cp_clients": "period"},
    }


class TestEveryTableACrossTableCheckReadsIsRecorded:
    """Criterion 1: one row per table the check reads, its own included,
    with the state and the supply - in the result's own transaction."""

    def test_its_own_table_and_the_table_it_declares_are_both_recorded(self, conn, finish_runs):
        run_id = _run_id()
        key = run_id.split("__", 1)[1]
        _resolve(conn, run_id, **_period_and_staged(key))
        _write(run_id, _result(CLIENT_REF))
        assert _reads(conn, run_id) == {CLIENT_REF: {
            "cp_clients": (qa_store.READ, "cp-clients@20990101010000000000", False, []),
            "cp_notifications": (qa_store.READ, f"cp-notifications@{key}", False, []),
        }}

    def test_a_held_table_is_recorded_by_its_supply_id_never_its_name(self, conn):
        run_id = _run_id()
        res = _period_and_staged(run_id.split("__", 1)[1])
        _resolve(conn, run_id, **res, held={"cp_case_workers": "cp_case_workers__20990101"},
                 held_supply={"cp_case_workers": "cp-case-workers@20990101"})
        _write(run_id, _result(WORKER_REF))
        assert _reads(conn, run_id)[WORKER_REF]["cp_case_workers"] == (
            qa_store.HELD, "cp-case-workers@20990101", False, [])

    def test_an_absent_table_is_recorded_as_absent_with_no_supply(self, conn):
        run_id = _run_id()
        _resolve(conn, run_id, **_period_and_staged(run_id.split("__", 1)[1]),
                 absent=["cp_investigations"])
        _write(run_id, _result(ESCALATION))
        assert _reads(conn, run_id)[ESCALATION]["cp_investigations"] == (
            qa_store.ABSENT, None, False, [])

    def test_a_contested_table_is_the_supply_it_fell_through_to_flagged_contested(self, conn):
        run_id = _run_id()
        res = _period_and_staged(run_id.split("__", 1)[1])
        files = ["cp_clients__20990201__1", "cp_clients__20990201__2"]
        _resolve(conn, run_id, **res, ambiguous={"cp_clients": files})
        _write(run_id, _result(CLIENT_REF))
        assert _reads(conn, run_id)[CLIENT_REF]["cp_clients"] == (
            qa_store.READ, "cp-clients@20990101010000000000", True, files)

    def test_a_trials_table_belongs_to_no_supply(self, conn):
        from qa_tools.common import trial

        run_id = trial.trial_run_id()
        supply_db.ensure_staging(conn, run_id)
        try:
            _resolve(conn, run_id, resolved={"cp_notifications": "cp_notifications__t",
                                             "cp_clients": "cp_clients__t"})
            _write(run_id, _result(CLIENT_REF))
            assert {t: v[0] for t, v in _reads(conn, run_id)[CLIENT_REF].items()} == {
                "cp_clients": qa_store.NO_SUPPLY, "cp_notifications": qa_store.NO_SUPPLY}
        finally:
            trial.discard(conn, run_id)

    def test_recording_the_result_again_replaces_its_reads(self, conn):
        run_id = _run_id()
        _resolve(conn, run_id, **_period_and_staged(run_id.split("__", 1)[1]))
        _write(run_id, _result(CLIENT_REF, status="fail"))
        _write(run_id, _result(CLIENT_REF))
        (count,) = conn.execute(
            f'SELECT count(*) FROM "{qa_store.SCHEMA}".check_read k '
            f'JOIN "{qa_store.SCHEMA}".check_result c ON c.id = k.check_result_id '
            "WHERE c.run_key = ?", [run_id]).fetchone()
        assert count == 2

    def test_a_single_table_result_records_no_reads(self, conn):
        run_id = _run_id()
        _write(run_id, _result(f"{CHECK}.cp-notifications.notification_id.not_null_dbt"))
        assert _reads(conn, run_id) == {}


class TestACrossTableResultWithNoReadIsRefused:
    """Criterion 4, test 10: the swallowed exception goes."""

    def test_a_run_with_no_recorded_resolution_is_refused(self, conn):
        run_id = _run_id()
        with pytest.raises(qa_store.UnrecordableRead):
            _write(run_id, _result(CLIENT_REF))
        assert not conn.execute(
            f'SELECT 1 FROM "{qa_store.SCHEMA}".check_result WHERE run_key = ?',
            [run_id]).fetchall()

    def test_a_table_read_with_no_supply_outside_a_trial_is_refused(self, conn):
        run_id = _run_id()
        _resolve(conn, run_id, resolved={"cp_notifications": "cp_notifications__x",
                                         "cp_clients": "cp_clients__x"})
        with pytest.raises(qa_store.UnrecordableRead, match="cp_clients"):
            _write(run_id, _result(CLIENT_REF))

    def test_a_held_table_with_no_supply_id_is_refused(self, conn):
        run_id = _run_id()
        _resolve(conn, run_id, **_period_and_staged(run_id.split("__", 1)[1]),
                 held={"cp_case_workers": "cp_case_workers__20990101"})
        with pytest.raises(qa_store.UnrecordableRead, match="cp_case_workers"):
            _write(run_id, _result(WORKER_REF))

    def test_the_store_refuses_a_cross_table_result_offered_with_no_reads(self, conn):
        qa_store.record_run(conn, run_key="r279", agency_id="a", collection_id="b",
                            run_timestamp=WHEN)
        with pytest.raises(qa_store.UnrecordableRead):
            qa_store.record_results(conn, "r279", [_result(CLIENT_REF)], tool="dbt",
                                    agency_id="a", collection_id="b",
                                    scope=qa_store.CROSS_TABLE_SCOPE)


class TestAStagedTablesSupplyDoesNotRenameWhatWasRead:
    """Criterion 2, architect S2: `logical in supply_of` used to mean "a
    period table", and a staged table carrying its supply would have been
    recorded under a stamped name it was never read as."""

    def test_a_staged_tables_physical_name_is_unchanged(self, conn):
        """A settled pair's `#1` staged as `__2` is the case a stamped name
        gets wrong: stamping it from its supply id reads `__1`."""
        run_id = _run_id()
        key = run_id.split("__", 1)[1]
        _resolve(conn, run_id,
                 resolved={"cp_notifications": f"cp_notifications__{key}",
                           "cp_clients": "cp_clients__20990101010000000000__2"},
                 supply_of={"cp_notifications": f"cp-notifications@{key}",
                            "cp_clients": "cp-clients@20990101010000000000#1"},
                 source={"cp_notifications": "staging", "cp_clients": "staging"})
        _write(run_id, _result(CLIENT_REF))
        (extra,) = conn.execute(
            f'SELECT extra FROM "{qa_store.SCHEMA}".check_result WHERE run_key = ?',
            [run_id]).fetchone()
        assert extra[tr.RESULT_FIELD] == {"cp_clients": "cp_clients__20990101010000000000__2"}

    def test_the_run_level_record_carries_a_staged_tables_supply_and_source(self, conn):
        run_id = _run_id("cp_clients")
        key = run_id.split("__", 1)[1]
        res = supply_db.Resolution(run_id=run_id, schema=supply_db.run_schema(run_id),
                                   resolved={"cp_clients": f"cp_clients__{key}"},
                                   supply_of={"cp_clients": f"cp-clients@{key}"},
                                   source={"cp_clients": "staging"})
        qa_results_writer.write_qa_result(AGENCY, COLLECTION, run_id, WHEN,
                                          qa_results_writer.TABLES_READ_TOOL, res.as_record())
        assert conn.execute(
            f'SELECT physical_table, supply, source FROM "{qa_store.SCHEMA}".tables_read '
            "WHERE run_key = ?", [run_id]).fetchall() == [
                (f"cp_clients__{key}", f"cp-clients@{key}", "staging")]

    def test_the_resolution_keeps_its_source_and_held_supply_when_read_back(self, conn):
        run_id = _run_id()
        _resolve(conn, run_id, **_period_and_staged(run_id.split("__", 1)[1]),
                 held={"cp_case_workers": "cp_case_workers__1"},
                 held_supply={"cp_case_workers": "cp-case-workers@1"})
        back = supply_db.resolution_for(conn, run_id)
        assert back.source == {"cp_notifications": "staging", "cp_clients": "period"}
        assert back.held_supply == {"cp_case_workers": "cp-case-workers@1"}
        assert set(back.supply_of) == {"cp_notifications", "cp_clients"}


class TestASingleTableResultIsAboutItsRunsOwnDataset:
    """Criterion 3."""

    def test_another_datasets_single_table_result_is_refused(self, conn):
        qa_store.record_run(conn, run_key="r279b", agency_id="a", collection_id="b",
                            run_timestamp=WHEN)
        qa_store.set_run_purpose(conn, "r279b", dataset_id="cp-notifications", supply_id=None)
        with pytest.raises(qa_store.WrongDataset, match="cp-clients"):
            qa_store.record_results(conn, "r279b", [_result("x.y", dataset_id="cp-clients")],
                                    tool="dbt", agency_id="a", collection_id="b")

    def test_its_own_datasets_is_recorded(self, conn):
        qa_store.record_run(conn, run_key="r279c", agency_id="a", collection_id="b",
                            run_timestamp=WHEN)
        qa_store.set_run_purpose(conn, "r279c", dataset_id="cp-clients", supply_id=None)
        assert qa_store.record_results(conn, "r279c", [_result("x.y", dataset_id="cp-clients")],
                                       tool="dbt", agency_id="a", collection_id="b") == 1


# ---------------------------------------------------------------------------
# run_seq and the attempts (criteria 5 to 8)
# ---------------------------------------------------------------------------

def _attempts(conn, run_key: str) -> list[dict]:
    return qa_store.attempts_of(conn, run_key)


def _seq(conn, run_key: str):
    return conn.execute(f'SELECT run_seq FROM "{qa_store.SCHEMA}".run WHERE run_key = ?',
                        [run_key]).fetchone()[0]


def _run(monkeypatch, run_id: str, then=None):
    """orchestrate.run_one, the one entry every arrival, re-check and
    knock-on run goes through, with its tools replaced by `then` - opened
    for real first, and finished for real where `then` returns."""
    from qa_tools.tools import orchestrate

    def inner(collection_id, entry, rid, run_timestamp, run_by, reference_run_id, on_step):
        qa_results_writer.open_run("a", "b", rid, run_timestamp, run_by)
        if then is not None:
            then(rid)
        qa_results_writer.finish_run(rid)
        return []

    monkeypatch.setattr(orchestrate, "_run_one_inner", inner)
    return orchestrate.run_one(COLLECTION, {"run_id": run_id}, WHEN, BY)


class TestAnArrivalRunsSupplyIsTheOneItsResolutionRecords:
    """post-build-review #262 D2: open_run states an arrival run's supply
    from the run's recorded resolution - the supply its own table held -
    never by matching the run id's stamp against filed supply ids, which
    picked a pair's `#1` for whichever of the two the run was about."""

    def test_the_resolved_supply_is_recorded_not_the_first_by_name(self, conn):
        import filing_support

        key = _key()
        run_id = f"cp_notifications__{key}"
        one, two = f"cp-notifications@{key}#1", f"cp-notifications@{key}#2"
        delivery = f"pytest-d2-{key}"
        conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".delivery (name, received_at, '
                     "received_instant) VALUES (?, ?, ?)", [delivery, WHEN, WHEN])
        for supply in (one, two):
            filing_support.place(conn, "cp-notifications", supply, "2099-Q1", delivery)
        _resolve(conn, run_id, resolved={"cp_notifications": f"{run_id}__2"},
                 supply_of={"cp_notifications": two}, source={"cp_notifications": "staging"})
        qa_results_writer.open_run(AGENCY, COLLECTION, run_id, WHEN, BY,
                                   dataset_id="cp-notifications")
        qa_results_writer.close_attempt(run_id, None)
        assert conn.execute(f'SELECT dataset_id, supply_id FROM "{qa_store.SCHEMA}".run '
                            "WHERE run_key = ?", [run_id]).fetchone() == ("cp-notifications", two)

    def test_a_refused_files_arrival_is_its_filed_supplys(self, conn):
        """The load refused the file, so nothing was staged and the own table
        is absent - but the supply was filed, and this is its arrival: the
        supply its delivery's file, received at the arrival's instant, is."""
        import filing_support

        key = _key()
        run_id = f"cp_notifications__{key}"
        delivery = f"pytest-d2-{key}"
        conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".delivery (name, received_at, '
                     "received_instant) VALUES (?, ?, ?)", [delivery, WHEN, WHEN])
        conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".delivery_file (delivery, filename, '
                     "dataset_id, received_at, received_instant, received_from, "
                     "receipt_sequence) VALUES (?, 'n.csv', 'cp-notifications', ?, ?, "
                     "'our-clock', 0)", [delivery, WHEN, WHEN])
        filing_support.place(conn, "cp-notifications", f"cp-notifications@{key}", "2099-Q1",
                             delivery)
        _resolve(conn, run_id, absent=["cp_notifications"])
        qa_results_writer.open_run(AGENCY, COLLECTION, run_id, WHEN, BY,
                                   dataset_id="cp-notifications", delivery=delivery,
                                   received_at=WHEN)
        qa_results_writer.close_attempt(run_id, None)
        assert conn.execute(f'SELECT supply_id, period FROM "{qa_store.SCHEMA}".run '
                            "WHERE run_key = ?", [run_id]).fetchone() == (
            f"cp-notifications@{key}", "2099-Q1")

    def test_a_run_whose_own_table_resolved_to_no_supply_records_none(self, conn):
        """An absent own table never filed: the run is for its dataset, about
        no supply."""
        run_id = _run_id()
        _resolve(conn, run_id, absent=["cp_notifications"])
        qa_results_writer.open_run(AGENCY, COLLECTION, run_id, WHEN, BY,
                                   dataset_id="cp-notifications")
        qa_results_writer.close_attempt(run_id, None)
        assert conn.execute(f'SELECT dataset_id, supply_id FROM "{qa_store.SCHEMA}".run '
                            "WHERE run_key = ?", [run_id]).fetchone() == ("cp-notifications", None)

    def test_the_dataset_is_the_one_given_never_the_run_ids(self, conn):
        """Keith, 2026-10-24 (provisional #23 decided): an arrival run's
        dataset is passed in by the orchestrator, which knows it from the
        arrival, and never read off the run id."""
        run_id = _run_id("cp_clients")
        _resolve(conn, run_id, absent=["cp_notifications"])
        qa_results_writer.open_run(AGENCY, COLLECTION, run_id, WHEN, BY,
                                   dataset_id="cp-notifications")
        qa_results_writer.close_attempt(run_id, None)
        assert conn.execute(f'SELECT dataset_id FROM "{qa_store.SCHEMA}".run '
                            "WHERE run_key = ?", [run_id]).fetchone() == ("cp-notifications",)

    def test_a_run_given_no_dataset_records_none_whatever_its_id_says(self, conn):
        """A trial's or a fixture's run: no dataset, and the id is not asked."""
        run_id = _run_id()
        qa_results_writer.open_run(AGENCY, COLLECTION, run_id, WHEN, BY)
        qa_results_writer.close_attempt(run_id, None)
        assert conn.execute(f'SELECT dataset_id, supply_id FROM "{qa_store.SCHEMA}".run '
                            "WHERE run_key = ?", [run_id]).fetchone() == (None, None)

    def test_the_orchestrator_passes_the_arrivals_dataset(self, conn, monkeypatch):
        from qa_tools.tools import orchestrate

        seen = {}
        monkeypatch.setattr(orchestrate, "open_run",
                            lambda *a, **k: seen.update(k) or (_ for _ in ()).throw(SystemExit))
        with pytest.raises(SystemExit):
            orchestrate._run_one_inner(COLLECTION, {"run_id": "x", "dataset_id": "cp-clients",
                                                    "delivery": "d", "received_at": WHEN},
                                       "x", WHEN, BY, None, None)
        assert (seen["dataset_id"], seen["delivery"], seen["received_at"]) == (
            "cp-clients", "d", WHEN)


class TestRunSeqIsDrawnWhenARunIsOpened:
    """Criterion 5."""

    def test_writes_before_the_run_is_opened_draw_none(self, conn):
        run_id = _run_id()
        _write(run_id, _result(f"{CHECK}.cp-notifications.notification_id.not_null_dbt"))
        assert _seq(conn, run_id) is None

    def test_a_reopened_run_draws_a_new_one_after_anything_opened_between(
            self, conn, monkeypatch):
        first, between = _run_id(), _run_id("cp_clients")
        _run(monkeypatch, first)
        was = _seq(conn, first)
        _run(monkeypatch, between)
        _run(monkeypatch, first)
        assert was < _seq(conn, between) < _seq(conn, first)

    def test_a_run_without_one_cannot_be_completed(self, conn):
        qa_store.record_run(conn, run_key="r279d", agency_id="a", collection_id="b",
                            run_timestamp=WHEN, run_by=BY, environment="test")
        with pytest.raises(qa_store.UnattributedRun, match="run_seq"):
            qa_store.complete_run(conn, "r279d")


def _lock_timeout(conn_dsn: str) -> None:
    """A REAL lock timeout on one of this project's own connections: a
    table another session holds, read with a short lock_timeout."""
    table = f"pytest_attempt_lock_{uuid.uuid4().hex[:8]}"
    holder = psycopg.connect(conn_dsn)
    try:
        holder.execute(f'CREATE TABLE public."{table}" (v int)')
        holder.commit()
        holder.execute(f'LOCK TABLE public."{table}" IN ACCESS EXCLUSIVE MODE')
        ours = supply_db.connect(reuse=False, label="test-lock-timeout")
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


class TestEveryAttemptIsRecorded:
    """Criterion 6, tests 19 to 21."""

    def test_a_lock_timeout_then_a_retry_is_two_attempts(self, conn, monkeypatch, supply_dsn):
        """Test 19."""
        run_id = _run_id()
        with pytest.raises(psycopg.errors.LockNotAvailable):
            _run(monkeypatch, run_id, then=lambda rid: _lock_timeout(supply_dsn))
        _run(monkeypatch, run_id)
        got = _attempts(conn, run_id)
        assert [a["outcome"] for a in got] == [qa_store.TIMED_OUT, qa_store.COMPLETED]
        assert all(a["began_at"] and a["ended_at"] for a in got)
        assert got[0]["run_seq"] < got[1]["run_seq"] == _seq(conn, run_id)

    def test_a_lock_timeout_wrapped_by_another_exception_still_timed_out(
            self, conn, monkeypatch, supply_dsn):
        run_id = _run_id()

        def wrapped(rid):
            try:
                _lock_timeout(supply_dsn)
            except psycopg.Error as exc:
                raise RuntimeError("while reading the period") from exc

        with pytest.raises(RuntimeError):
            _run(monkeypatch, run_id, then=wrapped)
        assert [a["outcome"] for a in _attempts(conn, run_id)] == [qa_store.TIMED_OUT]

    def test_a_crash_in_a_tool_is_kept_after_its_retry_records(self, conn, monkeypatch):
        """Test 20."""
        from qa_tools.tools import orchestrate

        run_id = _run_id()

        def boom():
            raise ValueError("x" * 3000)

        with pytest.raises(orchestrate.QaRunFailure):
            _run(monkeypatch, run_id,
                 then=lambda rid: orchestrate._run_step(COLLECTION, "dbt-core", rid, boom))
        _run(monkeypatch, run_id, then=lambda rid: _write(
            rid, _result(f"{CHECK}.cp-notifications.notification_id.not_null_dbt")))
        crashed, completed = _attempts(conn, run_id)
        assert crashed["outcome"] == qa_store.CRASHED
        assert crashed["error_type"] == "QaRunFailure"
        assert crashed["ended_at"] is not None
        assert crashed["error_message"].startswith(f"{COLLECTION} run {run_id}: dbt-core failed")
        assert len(crashed["error_message"]) == 1000
        assert completed["outcome"] == qa_store.COMPLETED

    def test_a_keyboard_interrupt_is_interrupted_never_crashed(self, conn, monkeypatch):
        """Test 21, its first half."""
        run_id = _run_id()

        def stop(rid):
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            _run(monkeypatch, run_id, then=stop)
        (only,) = _attempts(conn, run_id)
        assert only["outcome"] == qa_store.INTERRUPTED
        assert only["ended_at"] is not None

    def test_a_census_failure_after_completion_does_not_change_the_outcome(
            self, conn, monkeypatch):
        from qa_tools.common import census

        def broken(*a, **k):
            raise RuntimeError("census broke")

        monkeypatch.setattr(census, "take", broken)
        run_id = _run_id()
        _run(monkeypatch, run_id)
        assert [a["outcome"] for a in _attempts(conn, run_id)] == [qa_store.COMPLETED]


#: A process that opens an attempt of the run named on its command line,
#: through orchestrate.run_one, says so, and waits to be stopped.
_CHILD = """
import sys, time
from qa_tools.tools import orchestrate
from qa_tools.common import qa_results_writer

def inner(collection_id, entry, rid, run_timestamp, run_by, reference_run_id, on_step):
    qa_results_writer.open_run("a", "b", rid, run_timestamp, run_by)
    print("ready", flush=True)
    time.sleep(120)

orchestrate._run_one_inner = inner
orchestrate.run_one("child-protection", {"run_id": sys.argv[1]}, sys.argv[2], sys.argv[3])
"""


def _child(run_id: str) -> subprocess.Popen:
    proc = subprocess.Popen([sys.executable, "-c", _CHILD, run_id, WHEN, BY], cwd=ROOT,
                            env=dict(os.environ), stdout=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if line.strip() == "ready":
            return proc
        if proc.poll() is not None:
            break
    proc.kill()
    raise AssertionError(f"the child never opened its attempt (exit {proc.poll()})")


def _until_released(conn, run_id: str) -> None:
    deadline = time.monotonic() + 30
    while qa_store.attempt_running(conn, run_id):
        assert time.monotonic() < deadline, "the dead process's lock was never released"
        time.sleep(0.05)


class TestAStopFromOutside:
    """Criteria 6 and 7, tests 21 to 23, in real processes - a signal and a
    kill are things that happen to a process, not to a function."""

    def test_sigterm_is_interrupted_with_its_end_time(self, conn):
        """Test 21, its second half."""
        run_id = _run_id()
        proc = _child(run_id)
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=60)
        (only,) = _attempts(conn, run_id)
        assert only["outcome"] == qa_store.INTERRUPTED
        assert only["ended_at"] is not None

    def test_a_killed_attempt_is_closed_interrupted_with_no_end_by_its_retry(
            self, conn, monkeypatch):
        """Test 22."""
        run_id = _run_id()
        proc = _child(run_id)
        proc.kill()
        proc.wait(timeout=60)
        (dead,) = _attempts(conn, run_id)
        assert dead["outcome"] is None, "nothing may close it before the retry takes the lock"
        _until_released(conn, run_id)
        _run(monkeypatch, run_id)
        dead, retry = _attempts(conn, run_id)
        assert (dead["outcome"], dead["ended_at"]) == (qa_store.INTERRUPTED, None)
        assert retry["outcome"] == qa_store.COMPLETED

    def test_an_attempt_running_elsewhere_is_reported_and_left_alone(self, conn, monkeypatch):
        """Test 23."""
        run_id = _run_id()
        proc = _child(run_id)
        try:
            assert run_id in qa_store.incomplete_runs(conn)
            assert qa_store.attempt_running(conn, run_id)
            with pytest.raises(qa_store.AttemptInProgress):
                _run(monkeypatch, run_id)
            (still,) = _attempts(conn, run_id)
            assert (still["outcome"], still["ended_at"]) == (None, None)
        finally:
            proc.kill()
            proc.wait(timeout=60)

    def test_a_refused_attempt_leaves_the_live_attempts_schemas_and_scratch(
            self, conn, monkeypatch):
        """Test 23, and post-build-review #262 D1: the refused process gives
        back only what IT opened. It used to discard the run's schemas and
        dbt target in run_one's finally, which are the live attempt's."""
        run_id = _run_id()
        schema = supply_db.run_schema(run_id)
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        target = supply_db.dbt_target_path(run_id)
        target.mkdir(parents=True, exist_ok=True)
        proc = _child(run_id)
        try:
            with pytest.raises(qa_store.AttemptInProgress):
                _run(monkeypatch, run_id)
            assert conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = ?",
                                [schema]).fetchall(), "the live attempt's run schema went"
            assert target.is_dir(), "the live attempt's dbt target went"
            assert qa_store.attempt_running(conn, run_id)
        finally:
            proc.kill()
            proc.wait(timeout=60)
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            shutil.rmtree(target, ignore_errors=True)

    def test_a_refused_attempt_leaves_a_live_trials_run_and_attempts(self, conn, monkeypatch):
        """D1's trial half: trial.discard deletes the run and its attempts."""
        from qa_tools.common import trial

        run_id = trial.trial_run_id()
        proc = _child(run_id)
        try:
            with pytest.raises(qa_store.AttemptInProgress):
                _run(monkeypatch, run_id)
            assert conn.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".run WHERE run_key = ?',
                                [run_id]).fetchone()[0] == 1
            (still,) = _attempts(conn, run_id)
            assert still["outcome"] is None and qa_store.attempt_running(conn, run_id)
        finally:
            proc.kill()
            proc.wait(timeout=60)


class TestADebugWriteIntoAnEvaluatedRunIsRefused:
    """Criterion 8, test 24."""

    def _evaluated(self, monkeypatch) -> str:
        run_id = _run_id()
        _run(monkeypatch, run_id, then=lambda rid: _write(
            rid, _result(f"{CHECK}.cp-notifications.notification_id.not_null_dbt")))
        return run_id

    def _results(self, conn, run_id: str) -> list:
        return conn.execute(
            f'SELECT check_id, status FROM "{qa_store.SCHEMA}".check_result '
            "WHERE run_key = ? ORDER BY id", [run_id]).fetchall()

    def test_mothman_debug_run_dbt_is_refused_and_changes_nothing(self, conn, monkeypatch):
        from click.testing import CliRunner

        import cli.debug as debug_cli
        from qa_tools.tools import run_dbt

        run_id = self._evaluated(monkeypatch)
        before, seq = self._results(conn, run_id), _seq(conn, run_id)
        called = []
        monkeypatch.setattr(run_dbt, "evaluate", lambda *a, **k: called.append(a) or [])
        got = CliRunner().invoke(debug_cli.debug_group,
                                 ["run-dbt", "--collection", "cp", "--run-id", run_id])
        assert got.exit_code != 0
        assert "already evaluated" in got.output
        assert not called, "the tool ran before the refusal"
        assert (self._results(conn, run_id), _seq(conn, run_id)) == (before, seq)

    def test_the_store_refuses_the_write_itself(self, conn, monkeypatch):
        run_id = self._evaluated(monkeypatch)
        before = self._results(conn, run_id)
        with pytest.raises(qa_store.NoOpenAttempt, match="already evaluated"):
            _write(run_id, _result(f"{CHECK}.cp-notifications.notification_id.not_null_dbt",
                                   status="fail"))
        assert self._results(conn, run_id) == before


class TestTheOtherWritersAndReadersOfAnAttempt:
    """post-build-review #262 F5: a file check's write is refused into an
    evaluated run like any other, a debug runner is refused while another
    process holds the run's attempt, and what a run carries is never
    silently read as nothing."""

    def test_a_file_check_write_into_an_evaluated_run_is_refused(self, conn, monkeypatch):
        run_id = _run_id()
        _run(monkeypatch, run_id)
        with pytest.raises(qa_store.NoOpenAttempt, match="already evaluated"):
            qa_store.record_file_results(
                conn, run_id, [_result(f"{CHECK}.cp-notifications.x.encoding_file")],
                agency_id=AGENCY, collection_id=COLLECTION, supply_state=qa_store.AGREED,
                load_attempt=-1, delivery="d", filename="f.csv")

    def test_a_file_check_write_before_the_run_is_opened_is_allowed(self, conn):
        """At staging, as the pipeline writes them: no run_seq yet."""
        run_id = _run_id()
        qa_store.record_run(conn, run_key=run_id, agency_id=AGENCY, collection_id=COLLECTION,
                            run_timestamp=WHEN, run_by=BY, environment="test")
        assert qa_store.record_file_results(
            conn, run_id, [_result(f"{CHECK}.cp-notifications.x.encoding_file")],
            agency_id=AGENCY, collection_id=COLLECTION, supply_state=qa_store.AGREED,
            load_attempt=-1, delivery="d", filename="f.csv") == 1

    def test_a_debug_runner_is_refused_while_another_process_holds_the_attempt(
            self, conn, monkeypatch):
        from click.testing import CliRunner

        import cli.debug as debug_cli
        from qa_tools.tools import run_dbt

        run_id = _run_id()
        proc = _child(run_id)
        try:
            called = []
            monkeypatch.setattr(run_dbt, "evaluate", lambda *a, **k: called.append(a) or [])
            got = CliRunner().invoke(debug_cli.debug_group,
                                     ["run-dbt", "--collection", "cp", "--run-id", run_id])
            assert got.exit_code != 0
            assert "being evaluated" in got.output
            assert not called, "the tool ran before the refusal"
        finally:
            proc.kill()
            proc.wait(timeout=60)

    def test_what_a_run_carries_is_never_read_as_nothing_on_a_failure(self, monkeypatch):
        """carried_for used to return {} on ANY exception, so an unreachable
        database read as 'this run carries nothing' and the run evaluated
        - and recorded - checks its sibling owns."""
        from qa_tools.common import carried

        def refuse(*a, **k):
            raise psycopg.OperationalError("no database here")

        monkeypatch.setattr(supply_db, "connect", refuse)
        with pytest.raises(psycopg.OperationalError):
            carried.carried_for(_run_id())


class TestADiscardedTrialTakesItsAttempts:
    """Criterion 6's one exception, test 25."""

    def test_the_discard_succeeds_and_its_attempts_go(self, conn, monkeypatch):
        from qa_tools.common import trial

        run_id = trial.trial_run_id()
        _run(monkeypatch, run_id)
        assert not conn.execute(f'SELECT 1 FROM "{qa_store.SCHEMA}".run WHERE run_key = ?',
                                [run_id]).fetchall(), "run_one's own discard did not run"
        assert _attempts(conn, run_id) == []

    def test_a_direct_discard_of_a_trial_with_attempts(self, conn, monkeypatch):
        from qa_tools.common import trial

        run_id = trial.trial_run_id()
        qa_results_writer.open_run("a", "b", run_id, WHEN, BY)
        qa_results_writer.finish_run(run_id)
        assert len(_attempts(conn, run_id)) == 1
        trial.discard(conn, run_id)
        assert _attempts(conn, run_id) == []
