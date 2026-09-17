"""Smoke test for generator/generate_runs.py: runs the real generator (it's
fast, seeded, and this repo's convention throughout has been to verify by
actually running things rather than mocking) and checks the resulting
manifest has the shape everything downstream depends on."""
from __future__ import annotations

import json
import os
from datetime import datetime

from generator import generate_runs

RAW_DIR = generate_runs.OUT_DIR
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")


def _generate():
    generate_runs.main()
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def test_manifest_has_one_entry_per_scheduled_delivery_at_minimum():
    manifest = _generate()
    delivery_ids = {e["delivery_id"] for e in manifest}
    assert len(delivery_ids) == len(generate_runs.RUN_PLAN)


def test_every_manifest_entry_has_a_real_file_on_disk():
    manifest = _generate()
    for entry in manifest:
        path = os.path.join(RAW_DIR, entry["file"])
        assert os.path.exists(path), f"{entry['run_id']}: {path} missing"
        assert os.path.getsize(path) > 0


def test_severity_counts_match_run_plan():
    manifest = _generate()
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


def test_resupply_attempts_only_follow_red_first_attempts():
    manifest = _generate()
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


def test_resupply_arrival_dates_always_fall_on_weekdays():
    manifest = _generate()
    for e in manifest:
        if e["is_resupply"]:
            arrived = datetime.fromisoformat(e["arrived_date"]).date()
            assert arrived.weekday() < 5, f"{e['run_id']} arrived on a weekend: {arrived}"


def test_supersedes_chain_is_well_formed():
    manifest = _generate()
    by_run_id = {e["run_id"]: e for e in manifest}
    for e in manifest:
        if e["supersedes_run_id"] is not None:
            assert e["supersedes_run_id"] in by_run_id, \
                f"{e['run_id']} supersedes a run_id not present in the manifest"
            prior = by_run_id[e["supersedes_run_id"]]
            assert prior["delivery_id"] == e["delivery_id"]
            assert prior["attempt_number"] == e["attempt_number"] - 1
