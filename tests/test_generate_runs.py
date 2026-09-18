"""Smoke test for generator/generate_runs.py: runs the real generator (it's
fast, seeded, and this repo's convention throughout has been to verify by
actually running things rather than mocking) and checks the resulting
manifest has the shape everything downstream depends on.

The real generation itself (generate_runs.main() - writes BDM's full real
120-delivery/176-run manifest + every real CSV to a real directory) happens
ONCE per test session (`manifest` fixture below, module-scoped - deliberately
NOT a plain module-level call, since pytest needs a real fixture to share
one real generation run across every test function in this file rather
than each one triggering its own ~9s regeneration of identical,
deterministic output - a real, measured ~43s/test-session win found
2026-09-18 while investigating why the local suite felt slow, not a
theoretical one). Every test below reads that one shared, real result -
none of them mutate it, so sharing is safe.

Isolated from the real production data/raw/ since 2026-09-18 (Keith's own
explicit call: "fix the issue where tests and production share an output
directory") - see the `raw_dir` fixture's own docstring."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from generator import generate_runs


@pytest.fixture(scope="module")
def raw_dir(tmp_path_factory):
    """Points generate_runs.OUT_DIR at a real tmp dir for the duration of
    this module's tests, instead of the repo's own data/raw/ - running
    this test file used to mutate the SAME directory ./run_pipeline.sh
    and qa_tools.bdm.orchestrate_bdm read from/write to for real, purely
    as a side effect of testing (harmless in outcome, since generation
    is fully deterministic, but a real coupling between test execution
    and production state that shouldn't exist). OUT_DIR is a plain
    module global generate_runs.main() reads at call time (not captured
    into a default arg), so reassigning it here works - module-scoped,
    not the standard function-scoped `monkeypatch` fixture, which can't
    be depended on from a module-scoped fixture (a real ScopeMismatch),
    hence the manual save/restore instead."""
    original = generate_runs.OUT_DIR
    path = tmp_path_factory.mktemp("bdm_raw")
    generate_runs.OUT_DIR = str(path)
    yield path
    generate_runs.OUT_DIR = original


@pytest.fixture(scope="module")
def manifest(raw_dir):
    generate_runs.main()
    with open(raw_dir / "manifest.json") as f:
        return json.load(f)


def test_manifest_has_one_entry_per_scheduled_delivery_at_minimum(manifest):
    delivery_ids = {e["delivery_id"] for e in manifest}
    assert len(delivery_ids) == len(generate_runs.RUN_PLAN)


def test_every_manifest_entry_has_a_real_file_on_disk(manifest, raw_dir):
    for entry in manifest:
        path = raw_dir / entry["file"]
        assert path.exists(), f"{entry['run_id']}: {path} missing"
        assert path.stat().st_size > 0


def test_severity_counts_match_run_plan(manifest):
    first_attempts = [e for e in manifest if e["attempt_number"] == 1]
    assert len(first_attempts) == len(generate_runs.RUN_PLAN)

    expected = [severity for (_, _, severity) in generate_runs.RUN_PLAN]
    # sort by run_index (a real int, matching RUN_PLAN's own generation
    # order), not delivery_id (a zero-padded string) - a plain string
    # sort broke for real once N_DELIVERIES crossed a fixed padding
    # width ("delivery_100" < "delivery_11"), which this test itself
    # caught (2026-09-17); see generate_runs.py's own comment on the
    # :02d -> :03d fix and qa_results_reader.py's natural-sort fix for
    # the two real (non-test) places the same bug class was reachable.
    actual = [e["dirty_severity"] for e in sorted(first_attempts, key=lambda e: e["run_index"])]
    assert actual == expected


def test_resupply_attempts_only_follow_red_first_attempts(manifest):
    by_delivery: dict[str, list[dict]] = {}
    for e in manifest:
        by_delivery.setdefault(e["delivery_id"], []).append(e)

    for delivery_id, attempts in by_delivery.items():
        attempts = sorted(attempts, key=lambda e: e["attempt_number"])
        if len(attempts) > 1:
            assert attempts[0]["dirty_severity"] == "red", \
                f"{delivery_id} has resupply attempts but first attempt wasn't red"
        for attempt in attempts[:-1]:
            assert attempt["dirty_severity"] == "red", \
                f"{delivery_id} attempt {attempt['attempt_number']} isn't red but chain continued"


def test_resupply_arrival_dates_always_fall_on_weekdays(manifest):
    for e in manifest:
        if e["is_resupply"]:
            arrived = datetime.fromisoformat(e["arrived_date"]).date()
            assert arrived.weekday() < 5, f"{e['run_id']} arrived on a weekend: {arrived}"


def test_supersedes_chain_is_well_formed(manifest):
    by_run_id = {e["run_id"]: e for e in manifest}
    for e in manifest:
        if e["supersedes_run_id"] is not None:
            assert e["supersedes_run_id"] in by_run_id, \
                f"{e['run_id']} supersedes a run_id not present in the manifest"
            prior = by_run_id[e["supersedes_run_id"]]
            assert prior["delivery_id"] == e["delivery_id"]
            assert prior["attempt_number"] == e["attempt_number"] - 1
