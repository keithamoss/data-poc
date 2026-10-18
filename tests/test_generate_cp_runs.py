"""Smoke test for generator/collections/child_protection.py: runs the real generator
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
from generator.collections import child_protection as cp_provider
from generator.collections.child_protection import TABLES, ChildProtectionProvider, _pick_dirty_tables
from qa_tools.common import asset_time
from generator import driver


@pytest.fixture(scope="module")
def raw_dir(tmp_path_factory):
    """Every one of cp_provider' outputs - see
    tests/generator_isolation.py and BDM's own counterpart.

    YIELDS THE DELIVERY TREE since REQ-PIPE-102: Child Protection no
    longer writes a flat per-run CSV directory, so the deliveries ARE
    the generator's output. The fixture keeps its name because every
    test that depends on it depends on "where the generator wrote",
    not on the shape of what it wrote.
    """
    root = tmp_path_factory.mktemp("cp_gen")
    restore = generator_isolation.redirect(root)
    yield Path(driver.DELIVERIES_DIR)
    restore()


@pytest.fixture(scope="module")
def real_data_before(raw_dir):
    """The supply-shaped files under the REAL data/ before this module
    generates anything, so the generator's writes outside its redirected
    root can be seen afterwards."""
    return generator_isolation.supply_files_under_data()


@pytest.fixture(scope="module")
def manifest(raw_dir, real_data_before):
    """This generator's own BOOKKEEPING, which is the only place it is
    written now (REQ-GEN-043) - data/{raw,cp_raw}/manifest.json held a
    second copy of exactly this list and is retired. Still called
    `manifest` because every test below reads it as "the list of what
    was generated", which is what it is."""
    driver.generate("child-protection")
    with open(driver.BOOKKEEPING_PATH) as f:
        return json.load(f)[cp_provider.DATASET_ID]


def test_dirty_module_resolves_to_generators_own_copy():
    """The provider's presets come from generator/dirty.py, the one copy
    (2026-09-14: a duplicate once resolved first)."""
    from generator import dirty as dirty_mod

    dirty_dir = os.path.dirname(dirty_mod.__file__)
    generator_dir = os.path.dirname(os.path.dirname(cp_provider.__file__))
    assert os.path.normpath(dirty_dir) == os.path.normpath(generator_dir)
    assert hasattr(dirty_mod, "apply_cp_clients_presets")


def _emptied() -> set[str]:
    """The quarters another collection's correction alters, where Child
    Protection writes nothing (REQ-GEN-237 criterion 3)."""
    from generator import correction_claims

    emptied = correction_claims.foreign_altered("child-protection")
    assert emptied, "precondition: REQ-GEN-205's correction empties some quarters"
    return emptied


def test_manifest_has_one_entry_per_scheduled_slot_at_minimum(manifest):
    delivery_ids = {e["slot_id"] for e in manifest}
    # THE GROWN QUARTERS TOO (REQ-GEN-207): one slot per generated period,
    # less the quarters another collection's correction empties.
    assert len(delivery_ids) == (len(cp_provider.RUN_PLAN) + len(cp_provider.GROWN_RUN_PLAN)
                                 - len(_emptied()))


def _delivery_dir(raw_dir, entry):
    """Where this run's six CSVs are, now that the delivery is the only
    copy (REQ-PIPE-102).

    KEYED BY DELIVERY NAME, not run id. The generator used to write
    `<run_id>/<table>.csv` alongside the delivery; the delivery it
    already wrote is named by the supplier-shaped name the manifest
    entry carries, which is the thing recognition reads.
    """
    return raw_dir / entry["delivery"]


def _shape_of(entry, manifest) -> str | None:
    """The file shape an injected delivery was written in, by its position
    in its slot - None for an ordinary one (REQ-GEN-199's shapes leave a
    table out, or carry one alone, ON PURPOSE)."""
    from generator.anchor_date import get_anchor_date

    periods = cp_provider.schedule.periods_for_dataset(
        cp_provider.DATASET_ID, until=get_anchor_date())
    _, injected = cp_provider._plan_injections(periods)
    if entry["period"] not in injected:
        return None
    slot = sorted((e for e in manifest if e["slot_id"] == entry["slot_id"]),
                  key=lambda e: e["run_index"])
    return injected[entry["period"]][0].arrivals[slot.index(entry)].file_shape


def test_every_manifest_entry_has_real_files_on_disk(manifest, raw_dir):
    from generator import scenario_injection as si

    # A GROWN QUARTER CASE WORKERS OWES NOTHING IN CARRIES FIVE FILES (REQ-GEN-207).
    owed = {p.name for p in cp_provider.schedule.periods_for_dataset("cp-case-workers")
            if p.expected}
    grown = {p.name for p in cp_provider.grown_periods()}
    for entry in manifest:
        run_dir = _delivery_dir(raw_dir, entry)
        shape = _shape_of(entry, manifest)
        five = entry["period"] in grown - owed
        for table in (t for t in cp_provider.TABLES if si.carries(shape, t)
                      and not (five and t == "cp_case_workers")):
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
    emptied = _emptied()
    assert len(first_by_slot) == (len(cp_provider.RUN_PLAN) + len(cp_provider.GROWN_RUN_PLAN)
                                  - len(emptied))

    # AN INJECTED SLOT FOLLOWS ITS INJECTION, not the run plan (REQ-GEN-044):
    # the scenario replaces that period's chain with the arrivals it names.
    # Found when TS-12 landed on a slot the plan had as red (2026-10-05);
    # TS-38 had only agreed with the plan by coincidence.
    from generator.anchor_date import get_anchor_date
    schedule = cp_provider.schedule

    del schedule, get_anchor_date
    # GENERATION ORDER (REQ-GEN-207 criterion 4): the original fifteen, then
    # the grown quarters oldest first, each from its own plan.
    original, grown = cp_provider.original_periods(), cp_provider.grown_periods()
    _, injected = cp_provider._plan_injections(cp_provider.generated_periods())
    # THE PLANNED SEVERITY, ambers moved off periods that cannot take them
    # (REQ-GEN-184 criterion 9) - and a scenario that keeps its period's
    # drawn amber carries it (REQ-GEN-199).
    planned = (cp_provider._ordinary_severities(original, injected)
               + cp_provider._grown_severities(grown, injected))
    periods = original + grown

    def first_of(name, severity):
        injection = injected[name][0]
        own = injection.arrivals[0].severity
        if own is None and injection.keeps_drawn_severity and severity == "amber":
            return severity
        return own

    expected = [first_of(p.name, severity) if p.name in injected else severity
                for severity, p in zip(planned, periods) if p.name not in emptied]
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

    from generator.anchor_date import get_anchor_date

    periods = cp_provider.schedule.periods_for_dataset(
        cp_provider.DATASET_ID, until=get_anchor_date())
    _, injected = cp_provider._plan_injections(periods)
    for slot_id, deliveries in by_slot.items():
        deliveries = sorted(deliveries, key=lambda e: e["run_index"])
        # A SCENARIO WHOSE FIRST DELIVERY KEEPS ITS QUARTER'S DRAWN AMBER is
        # the only injected chain that continues after a non-red delivery
        # (REQ-GEN-199: TS-77's late file after its amber first delivery).
        if deliveries[0]["period"] in injected \
                and injected[deliveries[0]["period"]][0].keeps_drawn_severity:
            continue
        # NOR ONE WHOSE LATER DELIVERIES ITS SCENARIO SCRIPTS ITSELF after a
        # scripted file fault (REQ-GEN-044: TS-14's corrected Client Register,
        # weeks after TS-12's unreadable one) - not a resupply the drawn
        # severity chose, which is all this test is about.
        if deliveries[0]["period"] in injected:
            first = injected[deliveries[0]["period"]][0]
            if len(first.arrivals) > 1 and first.arrivals[0].file_shape:
                continue
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


def test_the_generator_writes_a_delivery_and_nothing_beside_it(manifest, raw_dir, real_data_before):
    """REQ-PIPE-102 criterion 2, by what generation leaves behind. The
    generator used to write each run as a flat CSV (data/raw/ or
    data/cp_raw/) AS WELL AS a real delivery. Its output root now holds
    the delivery tree, its receipts and the bookkeeping - and the
    scenario placements, which scenario_injection writes at the end of a
    run - and the real data/ tree gains no supply file at all."""
    root = raw_dir.parent
    written = {p.name for p in root.iterdir()}
    assert {"deliveries", "receipts", "generator_bookkeeping.json"} <= written, \
        f"the generator did not write a delivery, its receipts and its bookkeeping: {sorted(written)}"
    assert list((root / "deliveries").iterdir()), "no delivery was generated at all"
    beside = written - generator_isolation.GENERATOR_OUTPUTS
    assert not beside, f"the generator wrote something beside the delivery: {sorted(beside)}"
    elsewhere = generator_isolation.supply_files_under_data() - real_data_before
    assert not elsewhere, \
        f"the generator wrote a supply file into the real data/ tree: {sorted(map(str, elsewhere))}"


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
        run_dir = _delivery_dir(raw_dir, entry)
        if not (run_dir / "cp_clients.csv").exists():
            continue  # a delivery of another table alone (REQ-GEN-199)
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
        run_dir = _delivery_dir(raw_dir, entry)
        if not (run_dir / "cp_clients.csv").exists():
            continue  # a delivery of another table alone (REQ-GEN-199)
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
    book_before = (delivery.BOOKKEEPING_PATH.read_bytes()
                   if delivery.BOOKKEEPING_PATH.exists() else None)
    # THE SCENARIO PLACEMENTS TOO (post-build-review #225): Child
    # Protection's injected scenarios are written there on every
    # generation, and the redirects below once missed it.
    from generator import scenario_injection

    real_placements = scenario_injection.PLACEMENTS_PATH
    placements_before = (real_placements.stat().st_mtime_ns, real_placements.read_bytes()) \
        if real_placements.exists() else None
    # NO PRECONDITION THAT THE REAL TREE EXISTS, and that was a real
    # bug in this test's first version - it asserted one, passed
    # locally where data/deliveries/ is populated, and failed in CI
    # where that gitignored directory has never been generated. The
    # guarantee does not need the tree to exist: an untouched ABSENT
    # tree is still untouched, and a generator writing to its defaults
    # would bring it into existence, which the comparison below catches
    # either way.

    monkeypatch.setattr(driver, "DELIVERIES_DIR", tmp_path / "deliveries")
    monkeypatch.setattr(driver, "RECEIPTS_DIR", tmp_path / "receipts")
    monkeypatch.setattr(driver, "BOOKKEEPING_PATH", tmp_path / "bookkeeping.json")
    monkeypatch.setattr(scenario_injection, "PLACEMENTS_PATH", tmp_path / "scenario_placements.json")

    driver.generate("child-protection")

    assert list((tmp_path / "deliveries").iterdir()), "nothing was generated into the redirected tree"
    assert _fingerprint(tmp_path / "deliveries"), "test precondition - the generator must have written somewhere"
    for name, path in (("deliveries", delivery.DELIVERIES_DIR), ("receipts", delivery.RECEIPTS_DIR)):
        assert _fingerprint(path) == before[name], f"the real {name} tree was written to by a test run"
    assert (delivery.BOOKKEEPING_PATH.read_bytes()
            if delivery.BOOKKEEPING_PATH.exists() else None) == book_before
    assert ((real_placements.stat().st_mtime_ns, real_placements.read_bytes())
            if real_placements.exists() else None) == placements_before, \
        "the real scenario placements file was written to by a test run"


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
    from generator.collections.civil_registration import BirthRegistrationsProvider

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
    # ONE ARRIVAL PER FILE since REQ-PIPE-105 criterion 1, so what a
    # DELIVERY carried is read by grouping its arrivals - the delivery
    # is still the transport unit this test is about.
    per_delivery: dict[str, int] = {}
    for a in found:
        assert len(a.files_by_dataset) == 1, (a.run_id, a.files_by_dataset)
        per_delivery[a.delivery_name] = per_delivery.get(a.delivery_name, 0) + 1
    assert len(per_delivery) == len(arrivals_written), "every delivery must be recognised"

    sizes = list(per_delivery.values())
    assert 6 in sizes, "criterion 3 - a whole-collection delivery is still ONE delivery"
    assert any(0 < n < 6 for n in sizes), \
        "criterion 2 - some of a collection's tables resupplied and the rest not"
    assert 1 in sizes, "criterion 1 - a supply for one dataset and none of its siblings"

    # And every one of them is still placed as Child Protection, from
    # the filenames alone - a partial delivery is not an unplaceable one.
    assert all(a.collection_id == "child-protection" for a in found)
    assert arrivals.unplaceable(deliveries_dir, receipts_dir) == []


def test_the_original_fifteen_keep_their_slots_and_come_first(manifest):
    """REQ-GEN-207 criterion 4: everything counted from the oldest quarter is
    the original fifteen's as it was - slot ids 01 to 15 in their order and the
    first run indices - and the grown quarters are numbered after them, oldest
    first, from a seed range of their own."""
    original = [p.name for p in cp_provider.original_periods()]
    grown = [p.name for p in cp_provider.grown_periods()]
    assert len(grown) == cp_provider.GROWN_QUARTERS
    first = {}
    for e in sorted(manifest, key=lambda e: e["run_index"]):
        first.setdefault(e["slot_id"], e)
    by_slot = sorted(first.values(), key=lambda e: e["run_index"])
    emptied = _emptied()
    assert [e["period"] for e in by_slot] == [n for n in original + grown if n not in emptied]
    assert [e["slot_id"] for e in by_slot][:15] == [f"cp_slot_{i:02d}" for i in range(1, 16)]
    last_original = max(e["run_index"] for e in manifest if e["period"] in original)
    assert all(e["run_index"] > last_original for e in manifest if e["period"] in grown)
    # SEEDS: the original fifteen's plus every offset they take (+500 to +1000)
    # never reach the grown range.
    assert cp_provider.BASE_SEED + 15 + 1000 < cp_provider._GROWN_PLAN_SEED
    assert cp_provider._GROWN_PLAN_SEED < cp_provider.GROWN_BASE_SEED


def test_a_grown_delivery_leaves_case_workers_out_of_its_off_months(manifest, raw_dir):
    """REQ-GEN-207 (Keith, 2026-10-15): a grown delivery for a quarter
    cp-case-workers does not take part in carries five files, as a supplier
    sending twice a year would - the original fifteen keep sending all six,
    and their off-month Case Workers files stay held as before."""
    owed = {p.name for p in cp_provider.schedule.periods_for_dataset("cp-case-workers")
            if p.expected}
    grown = {p.name for p in cp_provider.grown_periods()}
    original = {p.name for p in cp_provider.original_periods()}
    off_grown = [e for e in manifest if e["period"] in grown and e["period"] not in owed]
    on_grown = [e for e in manifest if e["period"] in grown and e["period"] in owed]
    off_original = [e for e in manifest if e["period"] in original - owed
                    and _shape_of(e, manifest) is None]
    assert off_grown and on_grown and off_original
    for e in off_grown:
        assert not (_delivery_dir(raw_dir, e) / "cp_case_workers.csv").exists(), e["delivery"]
    for e in on_grown + off_original:
        assert (_delivery_dir(raw_dir, e) / "cp_case_workers.csv").exists(), e["delivery"]


class TestAScenarioInAGrownQuarter:
    """REQ-GEN-203 and REQ-GEN-218 plant scenarios in the grown quarters
    (REQ-GEN-207). Their plan moves a drawn amber off a scenario's quarter and
    keeps its lead-in and following quarters clean, as the original fifteen's
    does (post-build-review #207 D3, which refused it until now); a drawn red
    there is refused, naming the scenario, never swallowed."""

    @staticmethod
    def _plan(anchor, **kw):
        from generator import scenario_injection as si

        grown = cp_provider.grown_periods()
        injection = si.Injection("TS-99", "cp-clients", anchor, "a test", **kw)
        placed = si.resolve(injection, grown)
        # BEFORE IS THE PLAN WITH NO SCENARIO OF ITS OWN: the quarters another
        # collection's correction empties have moved their ambers already.
        before = cp_provider._grown_severities(grown, {})
        after = cp_provider._grown_severities(grown, {placed.period: (injection, placed)})
        return grown, placed, before, after

    @staticmethod
    def _index(grown, name):
        return [p.name for p in grown].index(name)

    def test_a_drawn_amber_moves_off_the_scenarios_quarter(self):
        drawn = [i for i, (_q, sev) in enumerate(cp_provider.grown_run_plan()) if sev == "amber"]
        grown, placed, before, after = self._plan(drawn[0])
        assert after[self._index(grown, placed.period)] is None
        assert after.count("amber") == before.count("amber")

    def test_a_clean_quarter_changes_nothing_else(self):
        clean = [i for i, sev in enumerate(cp_provider._grown_severities(
                     cp_provider.grown_periods(), {})) if sev is None and i > 0
                 and cp_provider.grown_periods()[i].name not in _emptied()]
        _grown, _placed, before, after = self._plan(clean[3])
        assert after == before

    def test_its_lead_in_and_following_quarters_are_clean(self):
        from generator import scenario_injection as si

        drawn = [i for i, (_q, sev) in enumerate(cp_provider.grown_run_plan()) if sev == "amber"]
        grown, placed, _before, after = self._plan(
            drawn[2] + 1, arrivals=(si.ExtraArrival(0, "08:00", target=si.Target("green")),), lead_in=1)
        assert placed.built_green
        for name in placed.built_green:
            assert after[self._index(grown, name)] is None, name

    def test_a_drawn_red_there_is_refused_naming_the_scenario(self):
        from generator import scenario_injection as si

        red = next(i for i, (_q, sev) in enumerate(cp_provider.grown_run_plan()) if sev == "red")
        with pytest.raises(si.CannotPlace) as refused:
            self._plan(red)
        assert "TS-99" in str(refused.value) and "red" in str(refused.value)

    def test_the_real_plan_passes(self):
        _, injected = cp_provider._plan_injections(cp_provider.generated_periods())
        grown = cp_provider.grown_periods()
        assert len(cp_provider._grown_severities(grown, injected)) == len(grown)
