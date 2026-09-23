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
dirty.py/names_au.py/presentation.py entirely - see plans/publishing-
and-history.md #3. This test can no longer catch the original bug
(there's only one dirty.py to resolve to now), but still guards against
the pattern recurring.

Isolated from the real production data/cp_raw/ since 2026-09-18 (Keith's
own explicit call: "fix the issue where tests and production share an
output directory") - see the `raw_dir` fixture's own docstring
(tests/test_generate_runs.py's own identical fixture, BDM's
counterpart, has the full account)."""
from __future__ import annotations

import re

import json
import os

import pytest

from generator import generate_cp_runs
from generator.generate_cp_runs import TABLES, _pick_dirty_tables
from qa_tools.common import asset_time


@pytest.fixture(scope="module")
def raw_dir(tmp_path_factory):
    original = generate_cp_runs.OUT_DIR
    path = tmp_path_factory.mktemp("cp_raw")
    generate_cp_runs.OUT_DIR = str(path)
    yield path
    generate_cp_runs.OUT_DIR = original


@pytest.fixture(scope="module")
def manifest(raw_dir):
    generate_cp_runs.main()
    with open(raw_dir / "manifest.json") as f:
        return json.load(f)


def test_dirty_module_resolves_to_generators_own_copy():
    dirty_dir = os.path.dirname(generate_cp_runs.dirty_mod.__file__)
    assert os.path.normpath(dirty_dir) == os.path.normpath(os.path.dirname(generate_cp_runs.__file__))
    assert hasattr(generate_cp_runs.dirty_mod, "apply_cp_clients_presets")


def test_manifest_has_one_entry_per_scheduled_slot_at_minimum(manifest):
    delivery_ids = {e["slot_id"] for e in manifest}
    assert len(delivery_ids) == len(generate_cp_runs.RUN_PLAN)


def test_every_manifest_entry_has_real_files_on_disk(manifest, raw_dir):
    for entry in manifest:
        run_dir = raw_dir / entry["run_id"]
        for table in generate_cp_runs.TABLES:
            path = run_dir / f"{table}.csv"
            assert path.exists(), f"{entry['run_id']}: {path} missing"
            assert path.stat().st_size > 0


def test_severity_counts_match_run_plan(manifest):
    """The FIRST delivery into each slot, in generation order.

    There is no attempt_number to filter on any more (REQ-GEN-042
    retired it), so "first" is read from position - the lowest run_index
    within each slot - which is how the rest of the system now decides
    it too."""
    first_by_slot = {}
    for e in sorted(manifest, key=lambda e: e["run_index"]):
        first_by_slot.setdefault(e["slot_id"], e)
    assert len(first_by_slot) == len(generate_cp_runs.RUN_PLAN)

    expected = [severity for (_, severity) in generate_cp_runs.RUN_PLAN]
    # Sort by run_index (a real int, matching RUN_PLAN's own generation
    # order), not slot_id (a zero-padded string) - a plain string sort
    # broke for real once the count crossed a fixed padding width
    # ("cp_slot_100" < "cp_slot_11"), which this test itself caught
    # (2026-09-17).
    actual = [e["dirty_severity"]
              for e in sorted(first_by_slot.values(), key=lambda e: e["run_index"])]
    assert actual == expected


def test_a_resupply_only_ever_follows_a_red_delivery(manifest):
    by_slot: dict[str, list[dict]] = {}
    for e in manifest:
        by_slot.setdefault(e["slot_id"], []).append(e)

    for slot_id, deliveries in by_slot.items():
        deliveries = sorted(deliveries, key=lambda e: e["run_index"])
        if len(deliveries) > 1:
            assert deliveries[0]["dirty_severity"] == "red", \
                f"{slot_id} has more than one delivery but the first wasn't red"
        for delivery in deliveries[:-1]:
            assert delivery["dirty_severity"] == "red", \
                f"{slot_id}: {delivery['run_id']} isn't red but the chain continued"


def test_every_resupply_arrives_on_a_weekday(manifest):
    """A resupply is identified by POSITION - anything after the first
    arrival in a slot - because the is_resupply flag was retired rather
    than renamed. That is the same rule the dashboard has always used."""
    by_slot: dict[str, list[dict]] = {}
    for e in sorted(manifest, key=lambda e: e["run_index"]):
        by_slot.setdefault(e["slot_id"], []).append(e)

    checked = 0
    for deliveries in by_slot.values():
        for delivery in deliveries[1:]:
            received = asset_time.local_date(delivery["received_at"])
            assert received.weekday() < 5, \
                f"{delivery['run_id']} arrived on a weekend: {received}"
            checked += 1
    assert checked > 0, "no resupplies in the generated history to check"


def test_deliveries_in_one_slot_advance_in_time(manifest):
    """What the supersedes_run_id chain used to assert, re-expressed
    without it: the record itself orders the arrivals, so a pointer
    from each to its predecessor was bookkeeping the data already
    carried."""
    by_slot: dict[str, list[dict]] = {}
    for e in sorted(manifest, key=lambda e: e["run_index"]):
        by_slot.setdefault(e["slot_id"], []).append(e)

    for slot_id, deliveries in by_slot.items():
        instants = [asset_time.parse_instant(e["received_at"], e["run_id"]) for e in deliveries]
        assert instants == sorted(instants), \
            f"{slot_id}: deliveries are not in receipt order"
        assert len({e["period"] for e in deliveries}) == 1, \
            f"{slot_id}: deliveries disagree about which period they are for"


def test_no_manifest_entry_carries_a_retired_field(manifest):
    """The NFR stated directly, against real generated output: nothing
    should be able to use the retired sense of "delivery" after this."""
    retired = ("delivery_id", "delivery_date", "attempt_number", "is_resupply",
               "supersedes_run_id", "arrived_date", "run_date",
               "slot_attempt_number", "slot_is_resupply")
    for e in manifest:
        present = [f for f in retired if f in e]
        assert present == [], f"{e['run_id']} still carries {present}"


def test_no_run_id_carries_a_date(manifest):
    """The identity half. A dated run_id is what made a regeneration on
    a different calendar day write a second history beside the first."""
    for e in manifest:
        assert not re.search(r"\d{4}-\d{2}-\d{2}", e["run_id"]), \
            f"{e['run_id']} still carries a date"


def test_clean_runs_never_have_bad_cp_clients_values(manifest, raw_dir):
    """A clean delivery must never carry the out-of-range date_of_birth
    injector's marker - unlike a dirty one, which now only fails 2-3 of
    the 6 real tables (Keith's own call, 2026-09-18 dictated feedback:
    "only some tables... two or three could fail, and the rest could be
    fine"), so cp_clients specifically isn't guaranteed to be one of
    them on any given dirty run - see test_some_dirty_runs_inject_bad_
    cp_clients_values below for the positive case."""
    for entry in manifest:
        if entry["dirty_severity"] is not None:
            continue
        run_dir = raw_dir / entry["run_id"]
        with open(run_dir / "cp_clients.csv") as f:
            lines = f.read().splitlines()
        header = lines[0].split(",")
        dob_idx = header.index("date_of_birth")
        n_bad_dob = sum(1 for line in lines[1:] if line.split(",")[dob_idx] < "1900-01-01")
        assert n_bad_dob == 0, f"{entry['run_id']} is clean but has out-of-range dates of birth"


def test_some_dirty_runs_inject_bad_cp_clients_values(manifest, raw_dir):
    n_bad_runs = 0
    for entry in manifest:
        if entry["dirty_severity"] is None:
            continue
        run_dir = raw_dir / entry["run_id"]
        with open(run_dir / "cp_clients.csv") as f:
            lines = f.read().splitlines()
        header = lines[0].split(",")
        dob_idx = header.index("date_of_birth")
        n_bad_dob = sum(1 for line in lines[1:] if line.split(",")[dob_idx] < "1900-01-01")
        if n_bad_dob > 0:
            n_bad_runs += 1
    assert n_bad_runs > 0, "no dirty run across the whole real manifest ever touched cp_clients"


def test_dirty_only_picks_2_or_3_of_the_6_tables():
    """Direct unit coverage of the actual mechanism
    (_pick_dirty_tables(), which dirty() defers to) - real, load-bearing
    invariant: never 0/1 (that's not really "dirty"), never all 6
    (Keith's own call)."""
    saw_2 = saw_3 = False
    for seed in range(200):
        picked = _pick_dirty_tables(seed)
        assert picked <= set(TABLES)
        assert len(picked) in (2, 3), f"seed={seed}: picked {len(picked)} tables, expected 2 or 3"
        saw_2 |= len(picked) == 2
        saw_3 |= len(picked) == 3
    assert saw_2 and saw_3, "expected both 2-table and 3-table draws across 200 seeds"
