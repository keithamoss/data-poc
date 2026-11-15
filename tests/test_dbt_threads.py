"""A run's dbt step runs its selected nodes side by side, from one named
threads setting, and what it records never depends on the order dbt's
threads finished in (REQ-PIPE-432 criteria 2, 3, 5 and 7)."""
from __future__ import annotations

import json
import os

import pytest

import qa_tools.tools.run_dbt as run_dbt
from fixture_ids import CP_DIRTY_RUN_ID, CP_REF_RUN_ID
from qa_tools.common import dbt_common, dbt_worker, supply_db

pytestmark = pytest.mark.asset("quarterly")

CORES = os.cpu_count() or 1
#: Above one wherever the machine allows it - the case criterion 7 names.
SIDE_BY_SIDE = min(4, CORES)


@pytest.fixture
def fresh_worker(monkeypatch, cp_duckdb_dir):
    monkeypatch.setattr(run_dbt, "write_qa_result", lambda *a, **k: None)
    dbt_worker.stop()
    yield
    dbt_worker.stop()


def _run_results(run_id: str) -> dict:
    with open(os.path.join(supply_db.dbt_target_path(run_id), "run_results.json")) as f:
        return json.load(f)


def _verdicts(results: list[dict]) -> list[tuple]:
    return [(r["check_id"], r["dataset_id"], r["status"], r["metric_value"],
             r.get("failing_sample_keys")) for r in results]


class TestTheThreadsSetting:

    def test_it_reaches_the_dbt_invocation(self, fresh_worker, monkeypatch):
        """Criterion 7: the setting is what dbt runs with - read from dbt's
        own record of the invocation, not from our arguments."""
        if CORES < 2:
            pytest.skip("needs two cores to set more than one thread")
        monkeypatch.setattr(dbt_common, "DBT_THREADS", 2)
        run_dbt.evaluate("child-protection", CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        assert _run_results(CP_REF_RUN_ID)["args"]["threads"] == 2

    def test_it_is_constant_for_a_workers_life(self, fresh_worker, monkeypatch):
        """Criterion 2: one value per worker, so its partial parse stays
        valid - a changed setting gets a new worker rather than a different
        value in the old one."""
        monkeypatch.setattr(dbt_common, "DBT_THREADS", 1)
        run_dbt.evaluate("child-protection", CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
        first = dbt_worker._worker[0]
        run_dbt.evaluate("child-protection", CP_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        assert dbt_worker._worker[0] is first, "an unchanged setting restarted the worker"
        if CORES >= 2:
            monkeypatch.setattr(dbt_common, "DBT_THREADS", 2)
            run_dbt.evaluate("child-protection", CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
            assert dbt_worker._worker[0] is not first
            assert first.poll() is not None, "the old worker was left running"
            assert _run_results(CP_REF_RUN_ID)["args"]["threads"] == 2

    @pytest.mark.parametrize("bad", [0, -1, CORES + 1, 1.5, "2", True, None])
    def test_a_value_outside_the_range_is_refused_before_dbt(self, monkeypatch, tmp_path, bad):
        """Criterion 3: refused by name, with the values allowed, and dbt is
        never started - never a dbt traceback."""
        dbt_worker.stop()
        monkeypatch.setattr(dbt_common, "DBT_THREADS", bad)

        def no_dbt(*a, **k):
            raise AssertionError("dbt was started for a refused setting")

        monkeypatch.setattr(dbt_worker, "_start", no_dbt)
        with pytest.raises(dbt_common.DbtThreadsRefused) as caught:
            dbt_worker.invoke(["build"], {}, str(tmp_path))
        said = str(caught.value)
        assert "DBT_THREADS" in said and repr(bad) in said
        assert f"a whole number from 1 to {CORES}" in said
        assert "Traceback" not in said

    def test_run_dbt_refuses_before_touching_the_database(self, monkeypatch, tmp_path):
        """Criterion 3: before dbt is invoked means before the worker's
        schemas are prepared too."""
        monkeypatch.setattr(dbt_common, "DBT_THREADS", 0)

        def no_db(*a, **k):
            raise AssertionError("the database was touched for a refused setting")

        monkeypatch.setattr(dbt_common, "_prepare_worker_schemas", no_db)
        with pytest.raises(dbt_common.DbtThreadsRefused):
            dbt_common.run_dbt("build", ["stg_x"], str(tmp_path), "p", "q", "r", run_id="x")


class TestVerdictsWithThreadsAboveOne:

    def test_two_runs_each_read_from_their_own_target(self, fresh_worker, monkeypatch):
        """Criterion 7: at more than one thread, each run's verdicts come
        from its own run_results.json and match what one thread records."""
        if CORES < 2:
            pytest.skip("needs two cores to set more than one thread")
        by_threads = {}
        for threads in (1, SIDE_BY_SIDE):
            monkeypatch.setattr(dbt_common, "DBT_THREADS", threads)
            ref = run_dbt.evaluate("child-protection", CP_REF_RUN_ID, "2026-01-01T09:00:00Z")
            dirty = run_dbt.evaluate("child-protection", CP_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
            assert {r["run_id"] for r in ref} == {CP_REF_RUN_ID}
            assert {r["run_id"] for r in dirty} == {CP_DIRTY_RUN_ID}
            for run_id in (CP_REF_RUN_ID, CP_DIRTY_RUN_ID):
                assert _run_results(run_id)["args"]["threads"] == threads
            by_threads[threads] = (_verdicts(ref), _verdicts(dirty))
        ref, dirty = by_threads[SIDE_BY_SIDE]
        assert ref and dirty
        assert not [v for v in ref if v[2] == "fail"], "the clean run failed at more threads"
        assert [v for v in dirty if v[2] == "fail"], "the dirty run passed at more threads"
        assert by_threads[SIDE_BY_SIDE] == by_threads[1]
        assert supply_db.dbt_target_path(CP_REF_RUN_ID) != supply_db.dbt_target_path(CP_DIRTY_RUN_ID)

    def test_what_is_recorded_is_in_unique_id_order_whatever_dbt_wrote(
            self, fresh_worker, monkeypatch):
        """Criterion 5: thread scheduling can never reorder what is recorded
        - here dbt's own results are reversed on disk before they are read."""
        recorded = []
        monkeypatch.setattr(run_dbt, "write_qa_result",
                            lambda *a, verified, **k: recorded.append((a[4], a[5], verified)))
        real = run_dbt.run_dbt

        def reversed_on_disk(command, select, target_path, *a, **k):
            real(command, select, target_path, *a, **k)
            path = os.path.join(target_path, "run_results.json")
            with open(path) as f:
                doc = json.load(f)
            doc["results"].reverse()
            with open(path, "w") as f:
                json.dump(doc, f)

        straight = run_dbt.evaluate("child-protection", CP_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        monkeypatch.setattr(run_dbt, "run_dbt", reversed_on_disk)
        flipped = run_dbt.evaluate("child-protection", CP_DIRTY_RUN_ID, "2026-04-01T09:00:00Z")
        assert len(straight) > 1
        assert _verdicts(flipped) == _verdicts(straight)
        for tool, raw, _verified in recorded:
            assert tool == "dbt"
            ids = [r["unique_id"] for r in raw["results"]]
            assert ids == sorted(ids), "the raw output was recorded in dbt's own order"
