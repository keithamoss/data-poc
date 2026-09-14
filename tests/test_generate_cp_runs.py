"""Smoke test for generator/generate_cp_runs.py, plus a regression test for
a real import-resolution bug: generator/ and synthetic-data-generator/ each
have their own dirty.py (kept manually in sync for 3 shared CP presets -
see generate_cp_runs.py's own docstring), and `import dirty` inside
generate_cp_runs.py silently resolved to the WRONG (synthetic-data-
generator/) copy, because synthetic-data-generator/population.py's own
module-level code does `sys.path.insert(0, os.path.dirname(__file__))` as
a side effect of being imported - re-inserting synthetic-data-generator/
at sys.path[0] and undoing an earlier, one-off attempt to prioritise
generator/'s own directory. Caught live via a loud AttributeError
(apply_cp_clients_presets didn't exist yet in the wrong file) - the fix
moves generator/'s own directory re-insertion to immediately before
`import dirty`, after every import that could itself touch sys.path."""
from __future__ import annotations

import json
import os

import generate_cp_runs

RAW_DIR = generate_cp_runs.OUT_DIR
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.json")


def _generate():
    generate_cp_runs.main()
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def test_dirty_module_resolves_to_generators_own_copy():
    # The regression itself: without the fix, dirty_mod.__file__ resolves
    # to synthetic-data-generator/dirty.py, and apply_cp_clients_presets
    # (only ever added to generator/dirty.py) is missing.
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
