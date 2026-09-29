"""Tests for qa_tools/common/parallel_orchestrate.py's generic dispatch
logic, using fast stub workers rather than the real tools (which are
explicitly out of pytest's scope - see tests/test_build_dashboard_data.py's
own docstring). Covers the two behavioural guarantees Keith specifically
asked for when this was scoped (2026-09-14): results stay in manifest
order regardless of completion order, and a worker failure aborts the
whole batch rather than silently returning partial results."""
from __future__ import annotations

import time

import pytest

from qa_tools.common import parallel_orchestrate as po
from qa_tools.common.parallel_orchestrate import run_manifest

MANIFEST = [{"run_id": f"run_{i:02d}"} for i in range(6)]


def _echo_worker(entry: dict, tag: str) -> list[dict]:
    return [{"run_id": entry["run_id"], "tag": tag}]


def _slow_first_worker(entry: dict) -> list[dict]:
    # Earlier manifest entries finish LATER than later ones - if
    # run_manifest just concatenated results in completion order instead
    # of manifest order, this would catch it.
    i = int(entry["run_id"].rsplit("_", 1)[1])
    time.sleep(0.15 * (len(MANIFEST) - i) / len(MANIFEST))
    return [{"run_id": entry["run_id"]}]


def _failing_worker(entry: dict) -> list[dict]:
    if entry["run_id"] == "run_03":
        raise ValueError(f"synthetic failure for {entry['run_id']}")
    return [{"run_id": entry["run_id"]}]


@pytest.mark.parametrize("sequential", [True, False])
def test_results_stay_in_manifest_order_regardless_of_completion_order(sequential):
    results = run_manifest(MANIFEST, _slow_first_worker, sequential=sequential)
    assert [r["run_id"] for r in results] == [e["run_id"] for e in MANIFEST]


def test_worker_args_are_passed_through():
    results = run_manifest(MANIFEST, _echo_worker, "hello", sequential=True)
    assert all(r["tag"] == "hello" for r in results)


@pytest.mark.parametrize("sequential", [True, False])
def test_a_worker_failure_aborts_the_whole_batch(sequential):
    with pytest.raises(ValueError, match="run_03"):
        run_manifest(MANIFEST, _failing_worker, sequential=sequential)


def test_parallel_result_count_matches_manifest_size():
    results = run_manifest(MANIFEST, _echo_worker, "x", sequential=False, max_workers=3)
    assert len(results) == len(MANIFEST)


class TestArrivalsThatDependOnEachOther:
    """REQ-PIPE-075 criteria 1 and 7, and the defect that put this here.

    A supply is filed to the oldest slot no PROMOTION has filled. Filing
    every arrival up front means no slot is ever filled while the
    filings are being made - so on an empty database all 108 Child
    Protection supplies filed to 2023-Q1 and six promoted. Interleaved,
    they spread across all fifteen quarters and 67 promote.

    The hooks are what make that possible, and passing them has to force
    sequential execution: run N genuinely depends on run N-1's effects,
    so a process pool would race on them.
    """

    def test_each_entry_is_filed_run_and_promoted_before_the_next_begins(self):
        order = []
        po.run_manifest(
            [{"run_id": "a"}, {"run_id": "b"}],
            lambda entry: (order.append(f"run:{entry['run_id']}"), [])[1],
            before_each=lambda entry: order.append(f"before:{entry['run_id']}"),
            after_each=lambda entry, got: order.append(f"after:{entry['run_id']}"))
        assert order == ["before:a", "run:a", "after:a",
                          "before:b", "run:b", "after:b"]

    def test_the_hooks_see_that_entrys_own_results(self):
        seen = {}
        po.run_manifest(
            [{"run_id": "a"}, {"run_id": "b"}],
            lambda entry: [{"of": entry["run_id"]}],
            after_each=lambda entry, got: seen.__setitem__(entry["run_id"], got))
        assert seen == {"a": [{"of": "a"}], "b": [{"of": "b"}]}

    def test_hooks_force_sequential_even_when_parallel_was_asked_for(self):
        """Not a preference - a process pool would run these concurrently
        and each one's filing would see a database the one before it had
        not finished writing to."""
        in_flight, overlapped = [], []

        def worker(entry):
            in_flight.append(entry["run_id"])
            if len(in_flight) > 1:
                overlapped.append(tuple(in_flight))
            in_flight.remove(entry["run_id"])
            return []

        po.run_manifest([{"run_id": str(i)} for i in range(8)], worker,
                         sequential=False, before_each=lambda entry: None)
        assert overlapped == []

    def test_results_still_come_back_in_manifest_order(self):
        got = po.run_manifest(
            [{"run_id": "a"}, {"run_id": "b"}],
            lambda entry: [{"of": entry["run_id"]}],
            before_each=lambda entry: None)
        assert got == [{"of": "a"}, {"of": "b"}]
