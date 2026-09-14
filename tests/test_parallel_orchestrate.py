"""Tests for real_tools/parallel_orchestrate.py's generic dispatch logic,
using fast stub workers rather than the real tools (which are explicitly
out of pytest's scope - see tests/test_build_dashboard_data.py's own
docstring). Covers the two behavioural guarantees Keith specifically
asked for when this was scoped (2026-09-14): results stay in manifest
order regardless of completion order, and a worker failure aborts the
whole batch rather than silently returning partial results."""
from __future__ import annotations

import time

import pytest

from parallel_orchestrate import run_manifest

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
