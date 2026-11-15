"""datacontract-cli's library call runs in a long-lived worker process of its
own while a run's tools overlap, and everything else of the step stays in the
run's process (REQ-PIPE-431)."""
from __future__ import annotations

import os
import random
import time

import pytest

import qa_tools.tools.run_datacontract as run_datacontract
from fixture_ids import CP_DIRTY_RUN_ID, CP_REF_RUN_ID
from qa_tools.common import (
    asked_for, bulk_recheck, datacontract_common, datacontract_worker, left_out,
    parallel_orchestrate, replay_clock, supply_db, tool_worker,
)

pytestmark = pytest.mark.asset("quarterly")


@pytest.fixture
def staged(monkeypatch, cp_duckdb_dir):
    """The CP fixture's runs staged; nothing recorded; a fresh worker."""
    monkeypatch.setattr(run_datacontract.asked_for, "record", lambda *a, **k: None)
    monkeypatch.setattr(parallel_orchestrate, "TOOLS_CONCURRENTLY", True)
    datacontract_worker.stop()
    yield
    datacontract_worker.stop()


@pytest.fixture
def recorded(monkeypatch):
    """What run_datacontract records, with the process and the clock it was
    recorded in."""
    seen = []
    monkeypatch.setattr(run_datacontract, "write_qa_result", lambda *a, verified, **k: seen.append(
        {"pid": os.getpid(), "at": replay_clock.now(), "raw": a[5], "verified": verified}))
    return seen


def _clone(source: str, table: str) -> str:
    from conftest import clone_run_views

    run_id = f"{table}__{random.randrange(10**17, 10**18)}"
    with supply_db.connect(label="test-dc-worker") as conn:
        clone_run_views(conn, source, run_id)
    return run_id


def _verdicts(results):
    return sorted((r["check_id"], r["status"], r["metric_value"], r.get("row_count_total"),
                   repr(r.get("failing_sample_keys"))) for r in results)


def _not_here(*a, **k):
    raise AssertionError("datacontract-cli's library call ran in the run's own process")


class TestTheLibraryCallRunsInAWorker:

    def test_in_another_process_and_recorded_in_this_one(self, staged, recorded, monkeypatch):
        """Criteria 1, 2 and 9: the call is not made here; the records are."""
        monkeypatch.setattr(parallel_orchestrate, "TOOLS_CONCURRENTLY", False)
        sequential = run_datacontract.evaluate("child-protection", CP_DIRTY_RUN_ID,
                                               "2026-04-01T09:00:00Z")
        monkeypatch.setattr(parallel_orchestrate, "TOOLS_CONCURRENTLY", True)
        monkeypatch.setattr(datacontract_common, "run_against_warehouse", _not_here)
        worked = run_datacontract.evaluate("child-protection", CP_DIRTY_RUN_ID,
                                           "2026-04-01T09:00:00Z")
        proc = datacontract_worker._WORKER.state[0]
        assert proc.pid != os.getpid() and proc.poll() is None
        assert [r["status"] for r in worked].count("fail"), "the dirty run passed in the worker"
        assert _verdicts(worked) == _verdicts(sequential)
        assert [r["pid"] for r in recorded] == [os.getpid(), os.getpid()]
        # THE RAW OUTPUT IS THE TOOL'S OWN, as it was recorded in-process -
        # bar the run's own timestamps and id.
        volatile = {"runId", "timestampStart", "timestampEnd", "logs", "checks"}
        first, second = (r["raw"] for r in recorded)
        assert {k: v for k, v in first.items() if k not in volatile} == \
            {k: v for k, v in second.items() if k not in volatile}
        assert len(first["checks"]) == len(second["checks"])

    def test_one_worker_reused_across_runs(self, staged, recorded):
        """Criterion 1: started on first use and reused."""
        run_datacontract.evaluate("child-protection", CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        first = datacontract_worker._WORKER.state[0]
        run_datacontract.evaluate("child-protection", CP_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        assert datacontract_worker._WORKER.state[0] is first

    def test_the_credentials_never_reach_a_command_line(self, staged, recorded):
        """Criterion 3: the password goes through the request's environment."""
        from psycopg import conninfo

        run_datacontract.evaluate("child-protection", CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        proc = datacontract_worker._WORKER.state[0]
        password = conninfo.conninfo_to_dict(supply_db.supply_db_dsn()).get("password")
        assert password
        with open(f"/proc/{proc.pid}/cmdline", "rb") as f:
            assert password.encode() not in f.read()
        assert tool_worker.KEY_ENV not in os.environ

    def test_a_replayed_runs_records_carry_the_replay_clock(self, staged, recorded, monkeypatch):
        """Criterion 9: recorded where the process-wide replay clock runs."""
        monkeypatch.setattr(replay_clock, "_is_synthetic", lambda: True)
        replay_clock.start()
        try:
            replay_clock.anchor("2016-03-01T09:00:00+08:00")
            run_datacontract.evaluate("child-protection", CP_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        finally:
            replay_clock.stop()
        assert datacontract_worker._WORKER.state is not None, "the call did not go to the worker"
        [one] = recorded
        assert one["at"].year == 2016

    def test_a_recheck_trials_scope_survives(self, staged, recorded, monkeypatch):
        """Criteria 2 and 9: the trial-owner registry lives in this process,
        so the scope it gives reaches the worker as options."""
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"datacontract"}))
        trial = f"trial_rc_{random.randrange(10**8, 10**9)}"
        from conftest import clone_run_views

        with supply_db.connect(label="test-dc-worker") as conn:
            # A re-check trial's own staging schema, as bulk_recheck makes it.
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.staging_schema_for(trial)}"')
            clone_run_views(conn, CP_DIRTY_RUN_ID, trial)
        monkeypatch.setitem(bulk_recheck._TRIAL_OWNERS, trial, ("cp-placements", "cp_placements"))
        monkeypatch.setattr(datacontract_common, "run_against_warehouse", _not_here)
        got = run_datacontract.evaluate("child-protection", trial, "2026-04-01T09:00:00Z")
        left_out.take(trial)
        asked = set(asked_for.for_run(trial, "child-protection", "datacontract"))
        assert got and {r["check_id"] for r in got} <= asked
        assert {r["dataset_id"] for r in got} == {"cp-placements"}


class TestALostWorker:

    def test_one_killed_mid_request_fails_only_that_step_and_the_next_run_succeeds(
            self, staged, recorded):
        """Criterion 6 (stopped mid-run) and criterion 9."""
        run_datacontract.evaluate("child-protection", CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        proc, conn = datacontract_worker._WORKER.state[:2]

        class KilledOnReceipt:
            def send(self, message):
                conn.send(message)
                proc.kill()
                proc.wait()

            def __getattr__(self, name):
                return getattr(conn, name)

        datacontract_worker._WORKER.state = (proc, KilledOnReceipt())
        with pytest.raises(datacontract_worker.DatacontractWorkerFailed) as caught:
            run_datacontract.evaluate("child-protection", CP_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        said = str(caught.value)
        assert "datacontract-cli" in said and "stopped mid-run" in said
        assert "data was not the cause" in said
        assert "other tools' results are recorded but do not stand" in said
        assert "next run starts a new worker" in said
        assert datacontract_worker._WORKER.state is None, "the dead worker was kept"
        got = run_datacontract.evaluate("child-protection", CP_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        assert got and datacontract_worker._WORKER.state[0].pid != proc.pid

    def test_one_that_cannot_start_says_it_will_fail_the_same_way(self, staged, monkeypatch):
        """Criterion 6 (did not start): a worker that exits instead of
        connecting is reported, never waited on for ever."""
        monkeypatch.setattr(tool_worker, "START_TIMEOUT_S", 5)
        monkeypatch.setattr(datacontract_worker, "_start", lambda: tool_worker.spawn(
            "qa_tools.common.no_such_module_for_this_test", [], "datacontract-cli",
            cwd=str(supply_db.ROOT)))
        with pytest.raises(datacontract_worker.DatacontractWorkerFailed) as caught:
            run_datacontract.evaluate("child-protection", CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        said = str(caught.value)
        assert "datacontract-cli" in said and "did not start" in said
        assert "data was not the cause" in said
        assert "fail the same way" in said and "check that" in said
        assert datacontract_worker._WORKER.state is None

    def test_a_tool_error_in_the_worker_is_raised_here_as_itself(self, staged, monkeypatch):
        """A selection the tool cannot honour is refused as it was in-process
        (REQ-PIPE-190 criterion 7), not reported as a lost worker."""
        P = "quarterly.child-protection-family-support.child-protection"
        run_id = _clone(CP_DIRTY_RUN_ID, "cp_clients")
        monkeypatch.setattr(asked_for, "SCOPED", frozenset({"datacontract"}))
        monkeypatch.setattr(asked_for, "for_run",
                            lambda *a, **k: [f"{P}.cp-clients.no_such_datacontract"])
        with pytest.raises(datacontract_common.SelectionRefused, match="no_such"):
            run_datacontract.evaluate("child-protection", run_id, "2026-04-01T09:00:00Z")
        assert datacontract_worker._WORKER.state[0].poll() is None, "the worker died of it"


class TestSequential:

    def test_the_sequential_mode_runs_in_process(self, staged, recorded, monkeypatch):
        """Criterion 8: no worker at all."""
        monkeypatch.setattr(parallel_orchestrate, "TOOLS_CONCURRENTLY", False)
        called = []
        real = datacontract_common.run_against_warehouse
        monkeypatch.setattr(datacontract_common, "run_against_warehouse",
                            lambda *a, **k: called.append(os.getpid()) or real(*a, **k))
        assert run_datacontract.evaluate("child-protection", CP_REF_RUN_ID,
                                         "2026-01-01T09:00:00Z")
        assert called == [os.getpid()]
        assert datacontract_worker._WORKER.state is None


# ---- the three lanes of a run (criteria 4, 5 and 8) ----

class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *a, **k):
        return self

    def fetchall(self):
        return []

    def fetchone(self):
        return (None,)

    def close(self):
        pass


@pytest.fixture
def lanes(monkeypatch, tmp_path):
    """A run of the shared orchestrator with every tool faked, each tool
    taking the time and raising the error a test gives it."""
    from qa_tools.tools import orchestrate

    spec = {"delay": {}, "raise": {}, "log": [], "finished": []}

    def tool(name):
        def evaluate(*a, **k):
            spec["log"].append((name, "start", time.monotonic()))
            time.sleep(spec["delay"].get(name, 0))
            spec["finished"].append(name)
            if name in spec["raise"]:
                raise RuntimeError(f"{name} broke")
            return [{"tool": name}]
        return evaluate

    for mod, name in ((orchestrate.run_dbt, "dbt"), (orchestrate.run_soda, "soda"),
                      (orchestrate.run_datacontract, "datacontract"),
                      (orchestrate.run_evidently, "evidently")):
        monkeypatch.setattr(mod, "evaluate", tool(name))
    monkeypatch.setattr(orchestrate.dataset_stats, "compute_dataset_stats", lambda *a, **k: {})
    monkeypatch.setattr(orchestrate, "write_qa_result", lambda *a, **k: None)
    monkeypatch.setattr(orchestrate, "open_run", lambda *a, **k: None)
    monkeypatch.setattr(orchestrate, "finish_run", lambda *a, **k: None)
    monkeypatch.setattr(orchestrate.asked_for, "check_nothing_missing", lambda *a, **k: None)
    monkeypatch.setattr(orchestrate.supply_db, "connect", lambda *a, **k: _FakeConn())
    monkeypatch.setattr(orchestrate.supply_db, "readable_in",
                        lambda conn, run_id: frozenset({"birth_registrations"}))

    def run():
        return orchestrate._run_one_inner(
            "civil-registration", {"run_id": "run_005"}, "run_005", "2099-01-05T00:00:00Z",
            "test@example.com", "run_01_2099-01-01", None)

    spec["run"] = run
    return spec


@pytest.mark.asset("daily")
class TestThreeLanes:

    def test_all_three_lanes_at_once_and_results_in_tool_order(self, lanes, monkeypatch):
        """Criterion 4: datacontract-cli finishes first, and the results are
        still dbt, Soda Core, datacontract-cli, Evidently."""
        monkeypatch.setattr(parallel_orchestrate, "TOOLS_CONCURRENTLY", True)
        lanes["delay"].update(dbt=0.6, soda=0.3, evidently=0.3, datacontract=0.05)
        started = time.monotonic()
        got = lanes["run"]()
        took = time.monotonic() - started
        assert [r["tool"] for r in got if "tool" in r] == ["dbt", "soda", "datacontract",
                                                          "evidently"]
        assert lanes["finished"][0] == "datacontract"
        assert took < 0.6 + 0.3 + 0.3 + 0.05 - 0.2, "the lanes did not overlap"
        starts = {name: at for name, what, at in lanes["log"]}
        assert abs(starts["datacontract"] - starts["soda"]) < 0.2

    @pytest.mark.parametrize("broken,reported", [
        ({"datacontract", "evidently"}, "datacontract-cli"),
        ({"soda", "datacontract"}, "Soda Core"),
        ({"dbt", "datacontract"}, "dbt-core"),
    ])
    def test_two_lanes_failing_report_the_earliest_tool(self, lanes, monkeypatch, broken,
                                                         reported):
        """Criterion 5: the tool earliest in tool order, whichever failed
        first in time, and no lane left running behind the exception."""
        from qa_tools.tools import orchestrate

        monkeypatch.setattr(parallel_orchestrate, "TOOLS_CONCURRENTLY", True)
        lanes["raise"].update({name: True for name in broken})
        # The later tool fails sooner, so timing alone would pick it.
        lanes["delay"].update(dbt=0.4, soda=0.2, datacontract=0.05, evidently=0.0)
        with pytest.raises(orchestrate.QaRunFailure) as caught:
            lanes["run"]()
        assert f": {reported} failed" in str(caught.value)
        assert "dbt" in lanes["finished"], "the dbt lane was left running"

    def test_the_sequential_mode_runs_all_four_in_tool_order(self, lanes, monkeypatch):
        """Criterion 8: one after another, in this process."""
        monkeypatch.setattr(parallel_orchestrate, "TOOLS_CONCURRENTLY", False)
        lanes["delay"].update(dbt=0.05, datacontract=0.0)
        got = lanes["run"]()
        assert [r["tool"] for r in got if "tool" in r] == ["dbt", "soda", "datacontract",
                                                          "evidently"]
        assert lanes["finished"] == ["dbt", "soda", "datacontract", "evidently"]


@pytest.mark.parametrize("command", ["bootstrap", "resume", "run"])
def test_sequential_help_names_datacontract_cli_too(command):
    """Criterion 7: `--sequential` says what it turns off."""
    from cli.pipeline import pipeline_group

    [option] = [p for p in pipeline_group.commands[command].params if p.name == "sequential"]
    assert "datacontract-cli" in option.help and "one after another" in option.help
