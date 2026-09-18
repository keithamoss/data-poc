"""Smoke test for generator/generate_cp_runs.py: runs the real generator
(fast, seeded, this repo's convention throughout) and checks the
resulting manifest has the shape everything downstream depends on -
same pattern as tests/test_generate_runs.py (BDM's own counterpart),
module-scoped `manifest` fixture for the same reason (one real
generation run shared across every test in this file, not one per test).

Also holds a sanity check left over from a real import-resolution bug
(2026-09-14, since fixed at the root cause): generator/ and synthetic-
data-generator/ used to each have their own dirty.py (kept manually in
sync for 3 shared CP presets), and `import dirty` inside generate_cp_
runs.py silently resolved to the WRONG, stale one via an ad hoc
sys.path.insert dance - caught live via a loud AttributeError
(apply_cp_clients_presets didn't exist yet in the wrong file). The real
fix wasn't a smarter sys.path ordering (an earlier attempt at that
didn't hold up); it was making generator/ and synthetic_data_generator/
(hyphens renamed to be a real, importable package name) both proper
Python packages with real absolute imports, and deleting the duplicate
dirty.py/names_au.py/presentation.py entirely - see plans/wider.md's
package-layout entry. This test can no longer catch the original bug
(there's only one dirty.py to resolve to now), but still guards against
the pattern recurring."""
from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

from generator import generate_cp_runs

RAW_DIR = generate_cp_runs.OUT_DIR
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")


@pytest.fixture(scope="module")
def manifest():
    generate_cp_runs.main()
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def test_dirty_module_resolves_to_generators_own_copy():
    dirty_dir = os.path.dirname(generate_cp_runs.dirty_mod.__file__)
    assert os.path.normpath(dirty_dir) == os.path.normpath(os.path.dirname(generate_cp_runs.__file__))
    assert hasattr(generate_cp_runs.dirty_mod, "apply_cp_clients_presets")


def test_manifest_has_one_entry_per_scheduled_delivery_at_minimum(manifest):
    delivery_ids = {e["delivery_id"] for e in manifest}
    assert len(delivery_ids) == len(generate_cp_runs.RUN_PLAN)


def test_every_manifest_entry_has_real_files_on_disk(manifest):
    for entry in manifest:
        run_dir = os.path.join(RAW_DIR, entry["run_id"])
        for table in generate_cp_runs.TABLES:
            path = os.path.join(run_dir, f"{table}.csv")
            assert os.path.exists(path), f"{entry['run_id']}: {path} missing"
            assert os.path.getsize(path) > 0


def test_severity_counts_match_run_plan(manifest):
    first_attempts = [e for e in manifest if e["attempt_number"] == 1]
    assert len(first_attempts) == len(generate_cp_runs.RUN_PLAN)

    expected = [severity for (_, severity) in generate_cp_runs.RUN_PLAN]
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


def test_amber_and_red_runs_inject_bad_cp_clients_values(manifest):
    for entry in manifest:
        run_dir = os.path.join(RAW_DIR, entry["run_id"])
        with open(os.path.join(run_dir, "cp_clients.csv")) as f:
            lines = f.read().splitlines()
        header = lines[0].split(",")
        dob_idx = header.index("date_of_birth")
        n_bad_dob = sum(1 for line in lines[1:] if line.split(",")[dob_idx] < "1900-01-01")
        if entry["dirty_severity"] is None:
            assert n_bad_dob == 0, f"{entry['run_id']} is clean but has out-of-range dates of birth"
        else:
            assert n_bad_dob > 0, f"{entry['run_id']} is dirty but has no injected out-of-range dates of birth"
