"""Smoke test for generator/collections/civil_registration.py: runs the real generator (it's
fast, seeded, and this repo's convention throughout has been to verify by
actually running things rather than mocking) and checks the resulting
manifest has the shape everything downstream depends on.

The real generation itself (driver.generate("civil-registration") - writes BDM's full real
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
from datetime import date, timedelta
from pathlib import Path

import json

import pytest

import generator_isolation
from generator.collections import civil_registration as generate_runs
from generator import scenario_injection as si
from qa_tools.common import asset_time
from generator import driver


@pytest.fixture(scope="module")
def raw_dir(tmp_path_factory):
    """Points every one of generate_runs' outputs at a real tmp dir for
    the duration of this module's tests, instead of the repo's own
    data/raw/ (and, since REQ-GEN-043, data/deliveries/, data/receipts/
    and data/generator_bookkeeping.json - see tests/generator_isolation.py
    and the regression test at the bottom of this file) - running
    this test file used to mutate the SAME directory ./run_pipeline.sh
    and qa_tools.tools.orchestrate read from/write to for real, purely
    as a side effect of testing (harmless in outcome, since generation
    is fully deterministic, but a real coupling between test execution
    and production state that shouldn't exist). Each output is a plain
    module global driver.generate("civil-registration") reads at call time (not captured
    into a default arg), so reassigning them here works - module-scoped,
    not the standard function-scoped `monkeypatch` fixture, which can't
    be depended on from a module-scoped fixture (a real ScopeMismatch),
    hence the manual save/restore instead."""
    root = tmp_path_factory.mktemp("bdm_gen")
    restore = generator_isolation.redirect(root)
    yield Path(driver.DELIVERIES_DIR)
    restore()


@pytest.fixture(scope="module")
def deliveries_dir(raw_dir):
    """Where the generator's one copy actually goes (REQ-PIPE-102).
    Depends on raw_dir so the redirection above is already in place."""
    return Path(driver.DELIVERIES_DIR)


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
    driver.generate("civil-registration")
    with open(driver.BOOKKEEPING_PATH) as f:
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

    periods = generate_runs.generated_periods()
    placed = [si.resolve(i, periods) for i in si.for_dataset("birth-registrations")]
    # A COVERED PERIOD is the scenario's own as much as its anchor
    # (REQ-GEN-199, TS-78): its supply is one of the scenario's arrivals.
    return ({p.period for p in placed} | _covered_periods(),
            {name for p in placed for name in p.suppressed})


def _covered_periods() -> set[str]:
    """Periods whose own supply is written with an injected scenario's
    anchor (Injection.covers), so no slot of their own appears."""
    from generator import scenario_injection as si

    periods = generate_runs.generated_periods()
    return {name for i in si.for_dataset("birth-registrations")
            for name in si.resolve(i, periods).covered}


def _planned_severities() -> list:
    """Each slot's severity as the generator plans it - the draw, with
    ordinary ambers moved off periods that cannot carry one (REQ-GEN-184
    criterion 9) - resolved the same way main() resolves it."""

    periods = generate_runs.generated_periods()
    _r, by_period, suppressed, _q = generate_runs._plan_injections(periods)
    return generate_runs._ordinary_severities(generate_runs.original_periods(),
                                              by_period, suppressed)


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
    assert len(slot_ids) == (len(generate_runs.RUN_PLAN) + generate_runs.GROWN_DAYS
                             + generate_runs.END_DAYS - len(suppressed))
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
    planned_all = _planned_severities()
    for slot_id, entry in first_by_slot.items():
        index = int(slot_id.split("_")[1]) - 1
        # The evening-before era's slots come after the 85's and carry no
        # ordinary severity (REQ-GEN-044).
        planned = planned_all[index] if index < len(planned_all) else None
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

    monkeypatch.setattr(driver, "DELIVERIES_DIR", tmp_path / "deliveries")
    monkeypatch.setattr(driver, "RECEIPTS_DIR", tmp_path / "receipts")
    monkeypatch.setattr(driver, "BOOKKEEPING_PATH", tmp_path / "bookkeeping.json")
    monkeypatch.setattr(scenario_injection, "PLACEMENTS_PATH",
                         tmp_path / "scenario_placements.json")

    driver.generate("civil-registration")

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
        from generator import scenario_injection as si

        periods = generate_runs.generated_periods()
        ts2 = next(i for i in si.INJECTIONS if i.scenario_id == "TS-2")
        suppressed = set(si.resolve(ts2, periods).suppressed)
        assert len(suppressed) == 2, sorted(suppressed)
        present = {e["period"] for e in manifest}
        assert not (present & suppressed), sorted(present & suppressed)

    def test_nothing_arrives_on_a_suppressed_day_either(self, manifest):
        """Not just "that period has no supply of its own" - NOTHING
        arrives, resupplies of earlier periods included. The supplier is
        down. This is the half that was wrong on the first real run."""
        from generator import scenario_injection as si

        _, suppressed = _injected_periods()
        assert suppressed, "precondition: some scenario suppresses a day"
        # By the day's CLAIM WINDOW, not the calendar day of receipt: in the
        # evening-before era (REQ-GEN-044) a day's supply arrives the evening
        # before, on the calendar day of the period before it.
        landed = {(day, e["run_id"]) for day in suppressed for e in manifest
                  if si._lands_in("birth-registrations", day, e["received_at"])}
        assert not landed, sorted(landed)


def _period_of(si, injection) -> str:

    periods = generate_runs.generated_periods()
    return si.resolve(injection, periods).period


class TestOrdinaryAmbersAsGenerated:
    """REQ-GEN-184 criterion 9 and Keith's 2026-10-11 answer on size,
    asserted on what the generator WROTE rather than on the plan
    (post-build-review #154: the plan said six ambers and three were
    generated, because ambers were moved onto days an injected scenario
    owns or empties)."""

    def test_every_drawn_ordinary_amber_is_generated(self, manifest):
        drawn = generate_runs._build_run_plan(generate_runs.N_DELIVERIES,
                                              generate_runs._RUN_PLAN_SEED)
        first = [entries[0] for entries in _ordinary_slots(manifest).values()]
        assert sum(e["dirty_severity"] == "amber" for e in first) == \
            [s for _n, s in drawn].count("amber")

    def test_an_amber_is_the_size_of_the_supply_before_it(self, manifest):
        """Keith, 2026-10-11: so neither the amber's own row-count check
        nor the next clean supply's moves because of it."""
        ordered = sorted(manifest, key=lambda e: e["run_index"])
        injected, _ = _injected_periods()
        checked = 0
        for prev_slot, slot in zip(_slot_runs(ordered), _slot_runs(ordered)[1:]):
            first = slot[0]
            if first["dirty_severity"] == "amber" and first["period"] not in injected:
                assert first["n_rows_generated"] == prev_slot[-1]["n_rows_generated"], first
                checked += 1
        assert checked, "no ordinary amber followed a supply"


def _slot_runs(ordered):
    out: dict[str, list] = {}
    for e in ordered:
        out.setdefault(e["slot_id"], []).append(e)
    return list(out.values())


class TestAResendKeepsEveryTwinsSibling:
    """plans/running-thoughts.md #82 (Keith, 2026-10-11: void singles only):
    churn() voided 1% of rows at random, and when one was a twin its
    sibling was left unmatched - a resend drawn clean then failed the three
    sibling checks, about four seeds in ten on the real tools."""

    @staticmethod
    def _unmatched(df):
        twins = df[df["is_multiple_birth"].astype(bool)]
        keys = ["date_of_birth", "place_of_birth_facility", "registering_parent_1_name"]
        sizes = twins.fillna({k: "<null>" for k in keys}).groupby(keys)["registration_number"] \
            .transform("count")
        return int((sizes < 2).sum())

    @pytest.mark.parametrize("seed", range(12))
    def test_no_twin_is_left_without_its_sibling(self, seed):
        from datetime import date as d

        p = generate_runs.BirthRegistrationsProvider()
        first = p.generate(d(2026, 9, 19), seed=1101, n_rows=2000, id_offset=0)
        assert self._unmatched(first) == 0, "precondition: the batch itself is whole"
        resend = p.churn(first, seed=3000 + seed, run_date=d(2026, 9, 19), id_offset=500_000)
        assert self._unmatched(resend) == 0


def test_every_lead_in_and_following_supply_arrives_on_time(manifest):
    """REQ-GEN-185 criterion 1, on the real history (post-build-review #156:
    TS-45's lead-in 09-16 arrived 16:55, after due plus grace, and was
    recorded late - its arrival instant came from the rows)."""
    from datetime import date as d

    from generator import scenario_injection as si
    from qa_tools.common import asset_time, slots

    placements = json.loads(Path(si.PLACEMENTS_PATH).read_text())
    if isinstance(placements, dict):
        placements = placements.get("placements", placements)
    if isinstance(placements, dict):
        placements = list(placements.values())
    green = {p for rec in placements for p in (*rec.get("lead_in", []), *rec.get("follow", []))}
    assert green, "precondition: the planted scenarios have lead-ins"
    for entry in manifest:
        if entry["period"] in green:
            due = slots.slot_instants("birth-registrations", d.fromisoformat(entry["period"]))
            got = asset_time.parse_instant(entry["received_at"], "received_at")
            assert due.due_at <= got <= due.due_at + due.grace, (entry["period"], got)


class TestAPairsPayloadIsItsCleanFile:
    """REQ-GEN-196, found on the first bootstrap: a pair's PAYLOAD - the size
    the next green day is built to - was its first unshaped file, which for
    TS-70 and TS-73 is the extract with a planted fault, a third of its rows
    gone. Every green day after it shrank to match and read red on row-count
    growth: thirteen targeted supplies disagreed with what they were built to."""

    @pytest.mark.parametrize("sid", ["TS-70", "TS-73"])
    def test_a_faulty_first_file_does_not_set_the_size(self, sid):
        from datetime import date
        from types import SimpleNamespace

        from generator import scenario_injection as si

        injection = next(i for i in si.INJECTIONS if i.scenario_id == sid)
        (extra,) = [a for a in injection.arrivals if a.files]
        provider = generate_runs.BirthRegistrationsProvider()
        day = date(2026, 8, 11)
        base = provider.generate(day, seed=7, n_rows=1800, id_offset=0)
        pair = generate_runs._pair_delivery(
            provider, injection, extra, 0, base, SimpleNamespace(date=day, round_date=day), seed=7,
            id_offset=0, n_rows=1800, previous_row_count=len(base), placement=None)
        assert len(pair.payload) == len(base)


class TestARefusalNamesTheScenarios:
    """REQ-GEN-196 criterion 21: an ordinary red or amber with no clean
    period left because of the scenarios' claims refuses before anything is
    written, NAMING the scenarios and saying to lengthen the history or move
    an anchor - it used to name only the drawn day."""

    @pytest.mark.parametrize("severity", ["red", "amber"])
    def test_it_names_them_and_says_what_to_do(self, monkeypatch, severity):
        from generator import targeting

        plan = [(n, severity) for n, _ in generate_runs.RUN_PLAN]
        monkeypatch.setattr(generate_runs, "run_plan", lambda: plan)
        periods = generate_runs.generated_periods()
        _r, by_period, suppressed, _q = generate_runs._plan_injections(periods)
        with pytest.raises(targeting.TargetError) as refused:
            generate_runs._ordinary_severities(generate_runs.original_periods(),
                                               by_period, suppressed)
        said = str(refused.value)
        assert "TS-68" in said and "TS-1" in said, said
        assert "lengthen the history or move an anchor" in said, said


class TestNoResendIsPushedFarFromItsDay:
    """#172 D1: the pairs' days once made 4-18 August one solid quiet block,
    and three late-July reds had their resends pushed past it, 22 to 27
    days late - one became 19 August's supply and turned TS-73's green
    following day red. A resend lands within days of its slot (the ordinary
    delays are one to three days, at most five here)."""

    LIMIT_DAYS = 10

    def test_every_arrival_is_within_ten_days_of_its_slot(self, manifest):
        from datetime import date

        late = [(e["run_id"], e["period"], e["received_at"][:10]) for e in manifest
                if (date.fromisoformat(e["received_at"][:10])
                    - date.fromisoformat(e["period"])).days > self.LIMIT_DAYS]
        assert manifest, "the generated history is empty"
        assert late == [], late


class TestTheEveningBeforeEra:
    """REQ-GEN-044's evening-before era (Keith, 2026-10-15): twelve more days
    at the OLD end, generated after the 85 with seeds of their own, in which a
    day's supply is due at 22:00 the evening before."""

    def test_the_85_keep_their_slots_and_seeds_and_come_first(self, manifest):
        originals = [e for e in manifest
                     if int(e["slot_id"].split("_")[1]) <= generate_runs.N_DELIVERIES]
        assert originals, "precondition: the 85 were generated"
        assert manifest[:len(originals)] == originals, "the 85 are written first"
        names = {p.name for p in generate_runs.original_periods()}
        assert {e["period"] for e in originals} <= names

    def test_the_era_is_twelve_days_before_the_85(self):
        grown = generate_runs.grown_periods()
        assert len(grown) == generate_runs.GROWN_DAYS == 12
        assert grown[-1].date + timedelta(days=1) == generate_runs.original_periods()[0].date

    def test_every_era_supply_arrives_the_evening_before_on_time(self, manifest):
        from qa_tools.common import asset_time, slots

        era = {p.name for p in generate_runs.grown_periods()}
        scenario_days = {si.resolve(i, generate_runs.generated_periods()).period
                         for i in si.for_dataset("birth-registrations")}
        ordinary = [e for e in manifest if e["period"] in era - scenario_days]
        assert len(ordinary) >= 6, "precondition: the era's ordinary days were written"
        for entry in ordinary:
            due = slots.slot_instants("birth-registrations", date.fromisoformat(entry["period"]))
            received = asset_time.parse_instant(entry["received_at"], entry["run_id"])
            assert due.claim_opens_at <= received <= due.due_at, entry
            assert received.date() == date.fromisoformat(entry["period"]) - timedelta(days=1)

    @pytest.mark.parametrize("scenario_id", ["TS-3c", "TS-3d", "TS-10a", "TS-10b"])
    def test_each_evening_before_scenario_sits_in_the_era(self, scenario_id):
        injection = next(i for i in si.INJECTIONS if i.scenario_id == scenario_id)
        placement = si.resolve(injection, generate_runs.generated_periods())
        era = {p.name for p in generate_runs.grown_periods()}
        assert placement.period in era, placement.period
        assert set(placement.suppressed) <= era
