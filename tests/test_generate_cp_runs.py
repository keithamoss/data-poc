"""Smoke test for generator/generate_cp_runs.py, plus a sanity check left
over from a real import-resolution bug (2026-09-14, since fixed at the
root cause): generator/ and synthetic-data-generator/ used to each have
their own dirty.py (kept manually in sync for 3 shared CP presets), and
`import dirty` inside generate_cp_runs.py silently resolved to the WRONG,
stale one via an ad hoc sys.path.insert dance - caught live via a loud
AttributeError (apply_cp_clients_presets didn't exist yet in the wrong
file). The real fix wasn't a smarter sys.path ordering (an earlier
attempt at that didn't hold up); it was making generator/ and
synthetic_data_generator/ (hyphens renamed to be a real, importable
package name) both proper Python packages with real absolute imports, and
deleting the duplicate dirty.py/names_au.py/presentation.py entirely -
see plans/wider.md's package-layout entry. This test can no longer catch
the original bug (there's only one dirty.py to resolve to now), but still
guards against the pattern recurring."""
from __future__ import annotations

import json
import os

from generator import generate_cp_runs

RAW_DIR = generate_cp_runs.OUT_DIR
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")


def _generate():
    generate_cp_runs.main()
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def test_dirty_module_resolves_to_generators_own_copy():
    dirty_dir = os.path.dirname(generate_cp_runs.dirty_mod.__file__)
    assert os.path.normpath(dirty_dir) == os.path.normpath(os.path.dirname(generate_cp_runs.__file__))
    assert hasattr(generate_cp_runs.dirty_mod, "apply_cp_clients_presets")


def test_manifest_has_one_entry_per_run():
    manifest = _generate()
    assert len(manifest) == len(generate_cp_runs.RUN_PLAN)


def test_dirty_severity_matches_run_plan():
    manifest = _generate()
    expected = [severity for (_, severity) in generate_cp_runs.RUN_PLAN]
    actual = [e["dirty_severity"] for e in sorted(manifest, key=lambda e: e["run_index"])]
    assert actual == expected


def test_amber_and_red_runs_inject_bad_cp_clients_values():
    manifest = _generate()
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
