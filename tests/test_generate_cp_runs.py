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
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import generator_isolation
from generator import generate_cp_runs
from generator.generate_cp_runs import TABLES, ChildProtectionProvider, _pick_dirty_tables
from qa_tools.common import asset_time


@pytest.fixture(scope="module")
def raw_dir(tmp_path_factory):
    """Every one of generate_cp_runs' outputs, not just OUT_DIR - see
    tests/generator_isolation.py and BDM's own counterpart."""
    root = tmp_path_factory.mktemp("cp_gen")
    restore = generator_isolation.redirect(generate_cp_runs, root)
    yield Path(generate_cp_runs.OUT_DIR)
    restore()


@pytest.fixture(scope="module")
def manifest(raw_dir):
    """This generator's own BOOKKEEPING, which is the only place it is
    written now (REQ-GEN-043) - data/{raw,cp_raw}/manifest.json held a
    second copy of exactly this list and is retired. Still called
    `manifest` because every test below reads it as "the list of what
    was generated", which is what it is."""
    generate_cp_runs.main()
    with open(generate_cp_runs.BOOKKEEPING_PATH) as f:
        return json.load(f)[generate_cp_runs.DATASET_ID]


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


def test_generating_never_touches_the_real_delivery_tree(tmp_path, monkeypatch):
    """CP's counterpart to the same test in tests/test_generate_runs.py -
    see that one for the real bug this guards. Both generators write
    into ONE shared delivery tree, so one of them leaking is enough to
    rewrite the other's deliveries too."""
    import hashlib

    from qa_tools.common import delivery

    def _fingerprint(root):
        root = Path(root)
        if not root.is_dir():
            return []
        return [(str(p.relative_to(root)),
                 hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir",
                 p.stat().st_mtime_ns)
                for p in sorted(root.rglob("*"))]

    before = {name: _fingerprint(path)
              for name, path in (("deliveries", delivery.DELIVERIES_DIR),
                                  ("receipts", delivery.RECEIPTS_DIR))}
    assert before["deliveries"], "test precondition - the real delivery tree must exist to be protected"
    book_before = (delivery.BOOKKEEPING_PATH.read_bytes()
                   if delivery.BOOKKEEPING_PATH.exists() else None)

    monkeypatch.setattr(generate_cp_runs, "OUT_DIR", str(tmp_path / "cp_raw"))
    monkeypatch.setattr(generate_cp_runs, "DELIVERIES_DIR", tmp_path / "deliveries")
    monkeypatch.setattr(generate_cp_runs, "RECEIPTS_DIR", tmp_path / "receipts")
    monkeypatch.setattr(generate_cp_runs, "BOOKKEEPING_PATH", tmp_path / "bookkeeping.json")

    generate_cp_runs.main()

    assert list((tmp_path / "deliveries").iterdir()), "nothing was generated into the redirected tree"
    for name, path in (("deliveries", delivery.DELIVERIES_DIR), ("receipts", delivery.RECEIPTS_DIR)):
        assert _fingerprint(path) == before[name], f"the real {name} tree was written to by a test run"
    assert (delivery.BOOKKEEPING_PATH.read_bytes()
            if delivery.BOOKKEEPING_PATH.exists() else None) == book_before


# ---- Partial resupplies (REQ-GEN-040) --------------------------------
#
# These exercise the CAPABILITY, not the generated history. Partial
# deliveries are off in the real run until the staging overlay can load
# one (REQ-PIPE-035/036) - Keith's own sequencing call, 2026-09-23 - so
# every assertion about the shape lives here rather than in
# data/deliveries/.


def _fake_payload(names=None):
    """A payload shaped like a real CP one. resupply_subset() only ever
    chooses KEYS, so the frames need no realistic content - and giving
    them some would suggest this test says more than it does."""
    return {name: pd.DataFrame({"id": [1, 2, 3]}) for name in (names or TABLES)}


def test_pick_dirty_tables_is_scoped_to_what_the_delivery_contains():
    """A partial resupply of two tables must not have its failures
    drawn from all six - that produces an arrival the chain calls red
    whose files are clean."""
    available = ["cp_clients", "cp_notifications"]
    for seed in range(100):
        picked = _pick_dirty_tables(seed, available)
        assert picked <= set(available), f"seed={seed}: picked outside the delivery ({picked})"
        assert picked


def test_a_single_table_delivery_has_that_table_dirtied():
    """"Never 1" is an invariant about a six-table delivery, not a rule
    that a one-table one comes back clean."""
    for seed in range(50):
        assert _pick_dirty_tables(seed, ["cp_carers"]) == {"cp_carers"}


def test_scoping_does_not_change_a_whole_collection_draw():
    """The default has to be exactly what it was, because the real
    generated history is byte-identical across this change and that is
    the claim being made."""
    for seed in range(200):
        assert _pick_dirty_tables(seed) == _pick_dirty_tables(seed, list(TABLES))


def test_a_resupply_sends_back_only_tables_that_failed():
    provider = ChildProtectionProvider(_fake_payload())
    for seed in range(100):
        failed = _pick_dirty_tables(seed, list(TABLES))
        sent = provider.resupply_subset(_fake_payload(), previous_dirty_seed=seed, seed=seed + 1)
        assert set(sent) <= failed, f"seed={seed}: resent a table that never failed"
        assert sent, f"seed={seed}: resupplied nothing at all"


def test_a_resupply_is_never_the_whole_collection():
    """Criterion 2 - some of a collection's tables are resupplied and
    the rest are not. A failure is never wider than three of six, so a
    resupply cannot be."""
    provider = ChildProtectionProvider(_fake_payload())
    for seed in range(100):
        sent = provider.resupply_subset(_fake_payload(), previous_dirty_seed=seed, seed=seed + 1)
        assert set(sent) != set(TABLES), f"seed={seed}: resent the entire collection"


def test_a_resupply_can_carry_exactly_one_dataset():
    """Criterion 1 - a supply for one dataset with no supply for any
    other dataset in the same collection. This is the reason a resupply
    sends a SUBSET of what failed rather than all of it: a failure is
    never narrower than two tables, so resending the failed set exactly
    could never produce this."""
    provider = ChildProtectionProvider(_fake_payload())
    sizes = {len(provider.resupply_subset(_fake_payload(), previous_dirty_seed=s, seed=s + 1))
             for s in range(200)}
    assert 1 in sizes, "no seed in 200 produced a single-dataset supply"
    assert sizes - {1}, "every resupply was a single table - the subset is not varying"


def test_resupply_subset_is_reproducible():
    provider = ChildProtectionProvider(_fake_payload())
    first = sorted(provider.resupply_subset(_fake_payload(), previous_dirty_seed=11, seed=22))
    second = sorted(provider.resupply_subset(_fake_payload(), previous_dirty_seed=11, seed=22))
    assert first == second


def test_resupply_subset_holds_no_state_between_chains():
    """A provider instance is shared across every slot in a run. If
    what-failed were remembered on it rather than recomputed from the
    seed, two chains interleaved would contaminate each other - which
    holds only while slots happen to be walked one at a time."""
    provider = ChildProtectionProvider(_fake_payload())
    a_first = sorted(provider.resupply_subset(_fake_payload(), previous_dirty_seed=3, seed=9))
    provider.resupply_subset(_fake_payload(), previous_dirty_seed=77, seed=5)
    a_again = sorted(provider.resupply_subset(_fake_payload(), previous_dirty_seed=3, seed=9))
    assert a_first == a_again


def test_a_birth_registrations_supply_cannot_be_split():
    """One CSV is indivisible, and the provider says so rather than
    leaving the method off."""
    from generator.generate_runs import BirthRegistrationsProvider

    df = pd.DataFrame({"id": [1, 2, 3]})
    assert BirthRegistrationsProvider().resupply_subset(df, previous_dirty_seed=1, seed=2) is df


def test_a_partial_resupply_survives_as_a_real_delivery_on_disk(tmp_path, monkeypatch):
    """The end-to-end shape REQ-PIPE-035/036 will have to load: the
    real chain, the real provider's own subset rule, written through
    the real delivery format and read back by the real recogniser.

    Everything except the dirt is real. dirty() is stubbed because the
    per-table preset functions need genuine CP columns and this test is
    about which FILES a delivery carries, not what is wrong inside
    them - a distinction worth stating rather than implying.
    """
    from qa_tools.common import arrivals, delivery
    from generator import resupply as resupply_mod

    class ShapeOnlyProvider(ChildProtectionProvider):
        def dirty(self, payload, severity, seed, previous_row_count):
            return payload

    monkeypatch.setattr(resupply_mod, "STILL_RED_PROB", 0.0)
    deliveries_dir, receipts_dir = tmp_path / "deliveries", tmp_path / "receipts"

    arrivals_written = []
    for slot, seed in enumerate((3, 5, 9, 14, 21), start=1):
        chain = list(resupply_mod.run_slot_chain(
            ShapeOnlyProvider(_fake_payload()), date(2026, 2, 1), seed=seed, id_offset=0,
            n_rows=0, first_severity="red", previous_row_count=None,
            partial_resupply=True))
        for n, arrival in enumerate(chain, start=1):
            csvs = {f"{name}.csv": df.to_csv(index=False) for name, df in arrival.payload.items()}
            delivery.write_delivery(
                f"slot{slot}-arrival{n}", csvs,
                received_at=asset_time.parse_instant(
                    f"2026-02-{slot:02d}T0{n}:00:00+08:00", "test"),
                deliveries_dir=deliveries_dir, receipts_dir=receipts_dir)
            arrivals_written.append(arrival)

    found = arrivals.arrivals_for("child-protection", "cp_run_", deliveries_dir, receipts_dir)
    assert len(found) == len(arrivals_written), "every arrival must be recognised as its own delivery"

    sizes = [len(a.files_by_dataset) for a in found]
    assert 6 in sizes, "criterion 3 - a whole-collection delivery is still ONE delivery"
    assert any(0 < n < 6 for n in sizes), \
        "criterion 2 - some of a collection's tables resupplied and the rest not"
    assert 1 in sizes, "criterion 1 - a supply for one dataset and none of its siblings"

    # And every one of them is still placed as Child Protection, from
    # the filenames alone - a partial delivery is not an unplaceable one.
    assert all(a.collection_id == "child-protection" for a in found)
    assert arrivals.unplaceable(deliveries_dir, receipts_dir) == []
