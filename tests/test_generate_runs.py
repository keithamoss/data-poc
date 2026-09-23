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

import re
from pathlib import Path

import json

import pytest

import generator_isolation
from generator import generate_runs
from qa_tools.common import asset_time


@pytest.fixture(scope="module")
def raw_dir(tmp_path_factory):
    """Points every one of generate_runs' outputs at a real tmp dir for
    the duration of this module's tests, instead of the repo's own
    data/raw/ (and, since REQ-GEN-043, data/deliveries/, data/receipts/
    and data/generator_bookkeeping.json - see tests/generator_isolation.py
    and the regression test at the bottom of this file) - running
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
    root = tmp_path_factory.mktemp("bdm_gen")
    restore = generator_isolation.redirect(generate_runs, root)
    yield Path(generate_runs.OUT_DIR)
    restore()


@pytest.fixture(scope="module")
def manifest(raw_dir):
    """This generator's own BOOKKEEPING, which is the only place it is
    written now (REQ-GEN-043) - data/{raw,cp_raw}/manifest.json held a
    second copy of exactly this list and is retired. Still called
    `manifest` because every test below reads it as "the list of what
    was generated", which is what it is."""
    generate_runs.main()
    with open(generate_runs.BOOKKEEPING_PATH) as f:
        return json.load(f)[generate_runs.DATASET_ID]


def test_manifest_has_one_entry_per_scheduled_slot_at_minimum(manifest):
    slot_ids = {e["slot_id"] for e in manifest}
    assert len(slot_ids) == len(generate_runs.RUN_PLAN)


def test_every_manifest_entry_has_a_real_file_on_disk(manifest, raw_dir):
    for entry in manifest:
        path = raw_dir / entry["file"]
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
    assert len(first_by_slot) == len(generate_runs.RUN_PLAN)

    expected = [severity for (_, severity) in generate_runs.RUN_PLAN]
    # Sort by run_index (a real int, matching RUN_PLAN's own generation
    # order), not slot_id (a zero-padded string) - a plain string sort
    # broke for real once the count crossed a fixed padding width
    # ("slot_100" < "slot_11"), which this test itself caught
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


def test_generating_never_touches_the_real_delivery_tree(tmp_path, monkeypatch):
    """Real bug, found 2026-09-23 by checking rather than assuming:
    redirecting generate_runs.OUT_DIR is no longer enough to isolate a
    test run, because REQ-GEN-043 gave the generator a second and third
    output - the delivery tree and the receipts beside it - and both
    default to the real ones under data/.

    So this module's own raw_dir fixture, whose whole purpose is that
    "tests and production share an output directory" never happens
    again (Keith's own call, 2026-09-18), had quietly stopped covering
    most of what the generator writes. Running the suite deleted and
    rewrote all 42 real Birth Registrations deliveries, their receipts,
    and the shared bookkeeping file. Deterministic, so the bytes came
    back identical and nothing ever noticed - but a run interrupted
    mid-write leaves the real tree half-deleted, and identical bytes
    are not the same thing as not having written them.

    Fingerprints the real tree, generates into tmp with every output
    redirected, and requires the real one to be untouched - including
    its modification times, which is the half a content hash misses.
    """
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
    # NO PRECONDITION THAT THE REAL TREE EXISTS, and that was a real
    # bug in this test's first version - it asserted one, passed
    # locally where data/deliveries/ is populated, and failed in CI
    # where that gitignored directory has never been generated. The
    # guarantee does not need the tree to exist: an untouched ABSENT
    # tree is still untouched, and a generator writing to its defaults
    # would bring it into existence, which the comparison below catches
    # either way.

    monkeypatch.setattr(generate_runs, "OUT_DIR", str(tmp_path / "raw"))
    monkeypatch.setattr(generate_runs, "DELIVERIES_DIR", tmp_path / "deliveries")
    monkeypatch.setattr(generate_runs, "RECEIPTS_DIR", tmp_path / "receipts")
    monkeypatch.setattr(generate_runs, "BOOKKEEPING_PATH", tmp_path / "bookkeeping.json")

    generate_runs.main()

    assert list((tmp_path / "deliveries").iterdir()), "nothing was generated into the redirected tree"
    assert _fingerprint(tmp_path / "deliveries"), "test precondition - the generator must have written somewhere"
    assert (tmp_path / "bookkeeping.json").exists()
    for name, path in (("deliveries", delivery.DELIVERIES_DIR), ("receipts", delivery.RECEIPTS_DIR)):
        assert _fingerprint(path) == before[name], f"the real {name} tree was written to by a test run"
    assert (delivery.BOOKKEEPING_PATH.read_bytes()
            if delivery.BOOKKEEPING_PATH.exists() else None) == book_before
