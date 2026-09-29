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
    and production state that shouldn't exist). Each output is a plain
    module global generate_runs.main() reads at call time (not captured
    into a default arg), so reassigning them here works - module-scoped,
    not the standard function-scoped `monkeypatch` fixture, which can't
    be depended on from a module-scoped fixture (a real ScopeMismatch),
    hence the manual save/restore instead."""
    root = tmp_path_factory.mktemp("bdm_gen")
    restore = generator_isolation.redirect(generate_runs, root)
    yield Path(generate_runs.DELIVERIES_DIR)
    restore()


@pytest.fixture(scope="module")
def deliveries_dir(raw_dir):
    """Where the generator's one copy actually goes (REQ-PIPE-102).
    Depends on raw_dir so the redirection above is already in place."""
    return Path(generate_runs.DELIVERIES_DIR)


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



def _injected_periods() -> tuple[set[str], set[str]]:
    """Which periods an injected scenario owns, and which it empties.

    RESOLVED THE SAME WAY THE GENERATOR RESOLVES THEM rather than
    hardcoded here, so moving an anchor moves both at once. Three of the
    invariants below are properties of the ORDINARY chain - one supply
    per slot, the planned severity, a resupply only after a red - and an
    injected scenario breaks each one ON PURPOSE. Excluding them by name
    would quietly stop covering a slot the day somebody renamed one.
    """
    from generator import scenario_injection as si
    from generator.anchor_date import get_anchor_date
    from qa_tools.common import schedule

    periods = schedule.periods_for_dataset(
        "birth-registrations", until=get_anchor_date())[-generate_runs.N_DELIVERIES:]
    placed = [si.resolve(i, periods) for i in si.for_dataset("birth-registrations")]
    return ({p.period for p in placed},
            {name for p in placed for name in p.suppressed})


def _ordinary_slots(manifest) -> dict[str, list[dict]]:
    """Every slot the ordinary chain produced, injected ones removed."""
    injected, _ = _injected_periods()
    by_slot: dict[str, list[dict]] = {}
    for entry in sorted(manifest, key=lambda e: e["run_index"]):
        if entry["period"] in injected:
            continue
        by_slot.setdefault(entry["slot_id"], []).append(entry)
    return by_slot


def test_manifest_has_one_entry_per_scheduled_slot_at_minimum(manifest):
    """Every scheduled slot gets a supply, EXCEPT the ones an injected
    scenario deliberately leaves empty (REQ-GEN-044). TS-2 is a supplier
    outage, and the only way to express two days with no supply at all
    is not to write one."""
    _, suppressed = _injected_periods()
    slot_ids = {e["slot_id"] for e in manifest}
    assert len(slot_ids) == len(generate_runs.RUN_PLAN) - len(suppressed)
    assert not ({e["period"] for e in manifest} & suppressed), (
        "a period an injected scenario needs empty carries a supply")


def test_every_manifest_entry_has_a_real_file_on_disk(manifest, deliveries_dir):
    """THE DELIVERY IS THE FILE ON DISK (REQ-PIPE-102, extended to
    Birth Registrations 2026-09-27). This used to look for a flat
    `data/raw/<run_id>.csv` written beside the delivery; the generator
    writes one copy now, and the manifest entry names the delivery it
    went into rather than a filename of its own."""
    for entry in manifest:
        run_dir = deliveries_dir / entry["delivery"]
        assert run_dir.is_dir(), f"{entry['run_id']}: {run_dir} missing"
        csvs = list(run_dir.glob("*.csv"))
        assert csvs, f"{entry['run_id']}: {run_dir} holds no CSV"
        assert all(c.stat().st_size > 0 for c in csvs)


def test_severity_counts_match_run_plan(manifest):
    """The FIRST delivery into each slot, in generation order.

    There is no attempt_number to filter on any more (REQ-GEN-042
    retired it), so "first" is read from position - the lowest run_index
    within each slot - which is how the rest of the system now decides
    it too."""
    first_by_slot = {slot: entries[0] for slot, entries in _ordinary_slots(manifest).items()}

    # AGAINST THE PLAN ENTRY FOR THAT SLOT'S OWN POSITION, rather than
    # against the whole plan in order: an injected scenario chooses its
    # own severities and a suppressed period has no entry at all, so the
    # two lists stopped being the same length (REQ-GEN-044). `slot_NNN`
    # is 1-indexed over the generated periods, which is the same order
    # RUN_PLAN is in.
    for slot_id, entry in first_by_slot.items():
        planned = generate_runs.RUN_PLAN[int(slot_id.split("_")[1]) - 1][1]
        assert entry["dirty_severity"] == planned, (
            f"{slot_id}: planned {planned!r}, generated {entry['dirty_severity']!r}")
    assert first_by_slot, "every slot was excluded - the exclusion is too wide"


def test_a_resupply_only_ever_follows_a_red_delivery(manifest):
    """Of the ORDINARY chain. TS-1's whole point is a third file landing
    after a resupply has already passed, so the injected slots are
    excluded here and asserted on their own terms below."""
    for slot_id, deliveries in _ordinary_slots(manifest).items():
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
    redirecting one of generate_runs' outputs is not enough to isolate a
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

    # THE SCENARIO PLACEMENTS ARE A FOURTH OUTPUT, and this test did not
    # know about them until 2026-09-29. Both generators call
    # scenario_injection.write_placements() at the end of a run, which
    # defaults to the real data/scenario_placements.json - so this test
    # asserted the real tree was untouched while quietly rewriting that
    # file on every run. It went unnoticed because the bootstrap ran
    # before every test and overwrote the partial file with a complete
    # one; CI's fast half does not bootstrap, and a Child Protection
    # scenario went missing from a file a Birth Registrations test had
    # truncated.
    from generator import scenario_injection

    placements_before = (scenario_injection.PLACEMENTS_PATH.read_bytes()
                          if scenario_injection.PLACEMENTS_PATH.exists() else None)

    monkeypatch.setattr(generate_runs, "DELIVERIES_DIR", tmp_path / "deliveries")
    monkeypatch.setattr(generate_runs, "RECEIPTS_DIR", tmp_path / "receipts")
    monkeypatch.setattr(generate_runs, "BOOKKEEPING_PATH", tmp_path / "bookkeeping.json")
    monkeypatch.setattr(scenario_injection, "PLACEMENTS_PATH",
                         tmp_path / "scenario_placements.json")

    generate_runs.main()

    assert list((tmp_path / "deliveries").iterdir()), "nothing was generated into the redirected tree"
    assert _fingerprint(tmp_path / "deliveries"), "test precondition - the generator must have written somewhere"
    assert (tmp_path / "bookkeeping.json").exists()
    for name, path in (("deliveries", delivery.DELIVERIES_DIR), ("receipts", delivery.RECEIPTS_DIR)):
        assert _fingerprint(path) == before[name], f"the real {name} tree was written to by a test run"
    assert (delivery.BOOKKEEPING_PATH.read_bytes()
            if delivery.BOOKKEEPING_PATH.exists() else None) == book_before
    assert (scenario_injection.PLACEMENTS_PATH.read_bytes()
            if scenario_injection.PLACEMENTS_PATH.exists() else None) \
        == placements_before, (
            "the real scenario_placements.json was written to by a test run")


class TestTheInjectedScenariosAreReallyThere:
    """REQ-GEN-044 criterion 1, against the REAL generated history.

    The three tests above exclude the injected slots so the ordinary
    chain's invariants still mean something. That exclusion is only
    honest if something else asserts the injected slots have the shape
    they were excluded FOR - otherwise a scenario could silently stop
    being generated and every remaining test would go green.
    """

    def test_the_forward_cascade_landed_as_three_files_on_one_day(self, manifest):
        """TS-1: 14:00 red, 16:00 clean, 20:00 into the now-filled slot."""
        from generator import scenario_injection as si

        ts1 = next(i for i in si.INJECTIONS if i.scenario_id == "TS-1")
        entries = sorted((e for e in manifest if e["period"] == _period_of(si, ts1)),
                         key=lambda e: e["run_index"])
        assert len(entries) == 3, [e["run_id"] for e in entries]
        assert [e["dirty_severity"] for e in entries] == ["red", None, None]
        times = [e["received_at"][11:16] for e in entries]
        assert times == ["14:00", "16:00", "20:00"], times

    def test_the_outage_left_two_days_with_nothing_at_all(self, manifest):
        """TS-2, and the half that is an ABSENCE - the easiest thing in
        this requirement to stop generating without anyone noticing."""
        _, suppressed = _injected_periods()
        assert len(suppressed) == 2, sorted(suppressed)
        present = {e["period"] for e in manifest}
        assert not (present & suppressed), sorted(present & suppressed)

    def test_nothing_arrives_on_a_suppressed_day_either(self, manifest):
        """Not just "that period has no supply of its own" - NOTHING
        arrives, resupplies of earlier periods included. The supplier is
        down. This is the half that was wrong on the first real run."""
        _, suppressed = _injected_periods()
        landed = {e["received_at"][:10] for e in manifest}
        assert not (landed & suppressed), sorted(landed & suppressed)


def _period_of(si, injection) -> str:
    from generator.anchor_date import get_anchor_date
    from qa_tools.common import schedule

    periods = schedule.periods_for_dataset(
        "birth-registrations", until=get_anchor_date())[-generate_runs.N_DELIVERIES:]
    return si.resolve(injection, periods).period
