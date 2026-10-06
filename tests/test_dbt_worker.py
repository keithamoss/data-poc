"""dbt runs in a long-lived worker process of its own, reading the project in
full once and partially after (REQ-PIPE-157, Keith 2026-10-06)."""
from __future__ import annotations

import os
import time

import pytest

import qa_tools.cp.run_dbt_cp as run_dbt_cp
from fixture_ids import CP_DIRTY_RUN_ID, CP_REF_RUN_ID
from qa_tools.common import dbt_worker, supply_db


@pytest.fixture
def fresh_worker(monkeypatch, cp_duckdb_dir):
    monkeypatch.setattr(run_dbt_cp, "write_qa_result", lambda *a, **k: None)
    dbt_worker.stop()
    yield
    dbt_worker.stop()


def _built(run_id: str) -> set[str]:
    with supply_db.connect(read_only=True, label="test-dbt-worker") as conn:
        return {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [supply_db.dbt_schema(run_id)]).fetchall()}


class TestOneWorkerPerProcess:

    def test_dbt_never_runs_in_this_interpreter(self, fresh_worker):
        """Criterion 5: not beside Soda Core, datacontract-cli or Evidently."""
        run_dbt_cp.evaluate_dbt_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        proc = dbt_worker._worker[0]
        assert proc.pid != os.getpid() and proc.poll() is None
        assert "dbt" not in {m.split(".")[0] for m in list(__import__("sys").modules)
                             if m.startswith("dbt.cli")}, "dbt was imported here"

    def test_later_runs_reuse_the_parse(self, fresh_worker):
        """Criterion 1: the first run parses in full; later ones are partial
        and markedly faster (measured 6.0s -> 3.8s on the full project)."""
        times = []
        for run_id in (CP_REF_RUN_ID, CP_DIRTY_RUN_ID, CP_REF_RUN_ID):
            s = time.monotonic()
            run_dbt_cp.evaluate_dbt_cp(run_id, "2026-01-01T09:00:00Z")
            times.append(time.monotonic() - s)
        assert os.path.exists(os.path.join(dbt_worker._worker[2], "partial_parse.msgpack"))
        assert max(times[1:]) < times[0], times

    def test_the_parse_survives_a_runs_tidy_up(self, fresh_worker):
        """NFR DISK: per-run target directories go with a run's schemas; the
        kept parse lives in the worker's own directory, which goes with it."""
        run_dbt_cp.evaluate_dbt_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        pp_dir = dbt_worker._worker[2]
        assert os.path.isdir(pp_dir)
        dbt_worker.stop()
        assert not os.path.exists(pp_dir)


class TestRunsStayApart:

    def test_a_model_one_run_excluded_is_not_found_built_from_the_last(
            self, fresh_worker, monkeypatch):
        """Criterion 2: the stable schema is emptied before every build."""
        run_dbt_cp.evaluate_dbt_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        assert "stg_cp_carers" in _built(CP_REF_RUN_ID)
        monkeypatch.setattr(run_dbt_cp, "_unreadable_in", lambda rid: frozenset({"cp_carers"}))
        run_dbt_cp.evaluate_dbt_cp(CP_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        built = _built(CP_DIRTY_RUN_ID)
        assert built and "stg_cp_carers" not in built

    def test_two_processes_never_share_a_schema(self):
        assert str(os.getpid()) in supply_db.dbt_worker_schema()
        assert supply_db.dbt_source_schema() != supply_db.dbt_worker_schema()


class TestTheKeptParse:

    def test_it_never_carries_the_database_password(self, fresh_worker):
        """NFR SECURITY: DBT_PG_PASSWORD is not a DBT_ENV_SECRET_ name, so dbt
        would not scrub it."""
        run_dbt_cp.evaluate_dbt_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        password = supply_db.connection_fields()["password"]
        blob = open(os.path.join(dbt_worker._worker[2], "partial_parse.msgpack"), "rb").read()
        assert password and password.encode() not in blob


class TestALostWorker:

    def test_one_that_died_idle_is_replaced_without_a_fuss(self, fresh_worker):
        run_dbt_cp.evaluate_dbt_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        first = dbt_worker._worker[0]
        first.kill()
        first.wait()
        assert run_dbt_cp.evaluate_dbt_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        assert dbt_worker._worker[0].pid != first.pid

    def test_one_lost_mid_request_is_reported_and_the_next_run_starts_another(
            self, fresh_worker, monkeypatch):
        """Killed after the liveness check, as if it died mid-run: reported as
        lost - never read as a run that produced nothing - and replaced."""
        run_dbt_cp.evaluate_dbt_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        proc = dbt_worker._worker[0]
        proc.kill()
        proc.wait()
        monkeypatch.setattr(proc, "poll", lambda: None)
        with pytest.raises(dbt_worker.WorkerLost):
            dbt_worker.invoke(["--version"], dict(os.environ), "/tmp")
        assert dbt_worker._worker is None
        assert run_dbt_cp.evaluate_dbt_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")


class TestNothingIsLeftBehind:

    def test_a_tidied_run_leaves_none_of_the_workers_schemas(self, fresh_worker):
        """Found by the whole-bootstrap comparison: each process left its
        sources schema behind - a leak with a tidier name."""
        run_dbt_cp.evaluate_dbt_cp(CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        with supply_db.connect(label="test-dbt-worker-tidy") as conn:
            supply_db.drop_run_schemas(conn, CP_REF_RUN_ID)
            left = [r[0] for r in conn.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname LIKE ?",
                [supply_db.dbt_worker_schema() + "%"]).fetchall()]
        assert left == []
