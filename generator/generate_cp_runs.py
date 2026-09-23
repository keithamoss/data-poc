"""
Generates periodic Child Protection collection snapshots into
data/cp_raw/ - the "whole collection" counterpart to generate_runs.py's
daily birth-registrations feed.

Deliberately a different generation model from generate_runs.py, by design
(see plans/dashboard.md #1 and the AskUserQuestion decisions that shaped
this): Child Protection isn't a daily event feed, it's a periodic full
extract of the same underlying casework collection - the population and
the Child Protection tables are built ONCE (fixed seed), then re-extracted
10 times as weekly snapshots. Row counts stay roughly stable run to run,
which is what a real periodic extract of an active caseload would look
like, unlike birth-registrations' fresh-cohort-per-day model.

Dirty injection touches all 6 tables on amber/red runs (plans/qa-
pipeline.md #27, 2026-09-15 - previously only 4: cp_carers/cp_case_
workers were deliberately clean in every run, a real gap closed once it
was scoped rather than an oversight left in place). Each preset function
in generator/dirty.py now covers not just its table's original "traffic
light demo" check but every real check on that table that had never
actually been exercised failing before: cp_notifications
(apply_cp_notifications_presets - an unknown concern_type code,
near-duplicate notifications, nulls on required columns, invalid values
on source_type/risk_rating/outcome, and genuine dangling foreign keys on
cp_client_id/assigned_worker_id), cp_placements
(apply_cp_placements_presets - a placement reassigned to a non-Approved
carer, nulls, an invalid placement_type, a duplicated placement_id, and
dangling FKs on cp_client_id/carer_id), cp_investigations
(apply_cp_investigations_presets - a closed-case investigation reopened,
nulls, a duplicated investigation_id, and dangling FKs on all 3 of this
table's real FKs), cp_clients (apply_cp_clients_presets - an
unrecognised postcode, an out-of-range date_of_birth, nulls, an invalid
sex, a duplicated cp_client_id), cp_carers and cp_case_workers
(apply_cp_carers_presets/apply_cp_case_workers_presets - each just a
duplicated PK, the only real check either table has that dirty.py had
never touched).

The dangling-FK injectors are a genuinely new failure mode, not a
calibration tweak: every preset in this module used to deliberately
avoid ever pointing a foreign key at a row that doesn't exist at all
(dbt's `relationships` tests and Soda's `values in ... must exist in
...` reference checks used to pass 0/0 on every run, dirty or clean -
see dbt_project/models/staging/schema.yml's and contract/child-
protection-soda-checks.yml's own comments, both updated alongside this).
That was a deliberate scoping choice (2026-09-13), not an oversight -
Keith's own call (2026-09-15) reversed it once item 27's audit made the
gap concrete.

child_protection.py's own generation logic makes all three of these
tables' cross-table business rules (escalation completeness,
placement/carer approval compliance, closed-case investigation hygiene -
see contract/child-protection-contract.yaml) pass cleanly by construction
on a clean run; the three dirty presets above are what reintroduce a
controlled, non-zero violation count on amber/red runs, the same
traffic-light pattern as concern_type.

extract_timestamp isn't a column child_protection.py produces (unlike
agency_datasets.py's birth_registrations, which has one) - added here per
snapshot instead, since "when was this extract pulled" is a property of
the QA-pipeline scenario, not the core generator.

RESUPPLY SIMULATION (2026-09-18, item 80/plans/qa-pipeline.md - "CP
resupply simulation," queued in plans/running-thoughts.md since the
Phase 7 resupply-chain redesign found CP had zero resupply concept at
all). Reuses generate_runs.py's own generic chain-orchestration engine
(generator/resupply.py) - a scheduled quarterly delivery that rolls red
now gets a real resupply attempt some working days later, possibly
still red, exactly like Birth Registrations' daily feed - rather than
CP forking its own parallel chain-walking logic. The one real
architectural wrinkle: resupply.py's DatasetProvider used to assume a
single pd.DataFrame payload (Birth Registrations' shape); CP's own
payload is a whole delivery's worth of tables at once. Generalized
(same 2026-09-18 change) to a generic `T` instead of forking the
module - see resupply.py's own docstring for the full account.
ChildProtectionProvider below is the CP-specific plug-in;
generate_runs.py's BirthRegistrationsProvider remains the BDM one,
unchanged. The dashboard-side supply-history UI needed NO changes for
this - Phase 7's own resupply-chain redesign (plans/conceptual-
design.md Thread A) already derives chain membership purely from real
per-run aggregate status, dataset-agnostic by construction ("nothing
about the model assumes BDM-only" - that file's own words, written
before this was actually built).
"""
from __future__ import annotations
import json
import os
from datetime import date, datetime

import numpy as np
import pandas as pd

from qa_tools.common import hierarchy
from generator.anchor_date import get_anchor_date
from generator import dirty as dirty_mod
from generator import delivery_names
from generator.resupply import MAX_ATTEMPTS, DatasetProvider, run_slot_chain
from qa_tools.common import asset_time, delivery, schedule

# Which dataset's calendar this collection is scheduled against. All six
# CP tables arrive together as one supply, so any of them names the same
# quarterly calendar - cp-clients is simply the first.
DATASET_ID = "cp-clients"
from synthetic_data_generator.population import generate_population
from synthetic_data_generator.child_protection import generate_child_protection_collection

ROOT = os.path.join(os.path.dirname(__file__), "..")

OUT_DIR = os.path.join(ROOT, "data", "cp_raw")

# WHERE THIS GENERATOR WRITES, all of it, redirectable the same way
# OUT_DIR is (read at call time, never captured into a default arg).
#
# Redirecting OUT_DIR alone used to isolate a test run. REQ-GEN-043
# gave the generator two more outputs - the delivery tree and the
# receipts beside it - plus a shared bookkeeping file, and all three
# defaulted to the real ones under data/. So the module's own
# isolation, which exists because "tests and production share an
# output directory" was a real problem once (Keith, 2026-09-18),
# quietly stopped covering most of what gets written. Named here so
# there is one place to redirect and one place to notice a fourth.
DELIVERIES_DIR = delivery.DELIVERIES_DIR
RECEIPTS_DIR = delivery.RECEIPTS_DIR
BOOKKEEPING_PATH = delivery.BOOKKEEPING_PATH


POPULATION_N = 70_000
N_CASE_WORKERS = 60
BASE_SEED = 5000  # distinct range from generate_runs.py's 1000s and generate.py's demo seeds

# The six CP tables, in the order contract/data-asset.yaml declares
# them - resolved, not restated (REQ-QAC-039).
TABLES = [d.table for d in hierarchy.datasets_in_collection("child-protection")]

# Resupply timing - deliberately NOT Birth Registrations' own curve
# (mostly 1-3 business days, tailing to 10): a corrected full quarterly
# collection re-extract is a bigger real turnaround than a single day's
# file. Keith's own calibration (2026-09-18, AskUserQuestion): "2-4
# weeks, mostly 1-2." Geometric decay per business day over a 5-20 day
# (1-4 week) range lands ~76% of the mass within the first 10 business
# days (2 weeks), tailing to 20 (4 weeks) - matches that framing without
# claiming false precision on the exact shape.
_CP_DELAY_DAYS = np.arange(5, 21)
_CP_DELAY_WEIGHTS = 0.8 ** (_CP_DELAY_DAYS - 5)
_CP_DELAY_WEIGHTS = _CP_DELAY_WEIGHTS / _CP_DELAY_WEIGHTS.sum()

# (quarter offset from run 1, dirty severity or None) - 15 quarterly
# snapshots spanning ~4 years, Feb/May/Aug/Nov-anchored (re-anchored
# 2026-09-17, Keith's own call, plans/qa-pipeline.md item 59's follow-on
# discussion: "1 February being the expected date of supply, then
# working forwards in three month increments from there" - replacing
# the previous CALENDAR-quarter anchor, Jan/Apr/Jul/Oct 1, set
# 2026-09-16 - see plans/dashboard.md #5's cadence-widening notes for that
# still-accurate earlier history: weekly -> quarterly, 10 -> 16 runs,
# 3 -> 4 years deep). This is a RE-ANCHOR of an already-quarterly
# cadence, not a weekly-to-quarterly conversion - only the day-of-quarter
# the boundary falls on changes (Feb 1 vs. Jan 1), which shifts every
# run's date and drops the count from 16 to 15: 4 years of Feb-anchored
# quarters ending on the last one at or before "today" (2026-09-17) is
# 2023-02-01 through 2026-08-01 (2026-11-01 would be the 16th, but that's
# in the future relative to the fixture's own "today," which this
# project's real data never extends past - see generate_runs.py's
# identical BDM-side convention). Ratio/shape below (first run clean,
# last run red, ~25% amber in between) is unchanged from the calendar-
# quarter version - only N_QUARTERS and _quarter_start()'s anchor month
# moved.
_RUN_PLAN_SEED = 5900  # distinct range from generation seeds (BASE_SEED+...)
N_QUARTERS = 15


def _build_run_plan(n: int, seed: int) -> list[tuple[int, str | None]]:
    rng = np.random.default_rng(seed)
    n_amber = max(1, round(n * 0.25))  # ~matches the original plan's 2/10 ratio
    # Two RED deliveries at a random position among every NON-FIRST slot
    # (2026-09-18, CP resupply simulation) - matches Birth Registrations'
    # own precedent (RUN_PLAN's own comment in generate_runs.py: "bumped
    # from a single red to 2 so the resupply-chain simulation... had more
    # than one independent example to demonstrate variability") - one
    # resupply chain that's already resolved by the time history ends,
    # not just the currently-open one. The LAST delivery is no longer
    # forced red (Keith's own call, 2026-09-18: "no need for the latest
    # one to always fail... happy for it to be random") - only the FIRST
    # stays forced clean, a real technical need (orchestrate_cp.py's own
    # Evidently reference run), not just a framing choice.
    n_red = 2
    n_clean_rest = (n - 1) - n_amber - n_red  # only the first is carved out separately
    rest = [None] * n_clean_rest + ["amber"] * n_amber + ["red"] * n_red
    rng.shuffle(rest)
    return list(enumerate([None] + rest))


RUN_PLAN = _build_run_plan(N_QUARTERS, _RUN_PLAN_SEED)


def _quarter_start(d: date) -> date:
    """The first day of the Feb/May/Aug/Nov-anchored quarter containing
    `d` - Keith's own explicit anchor (2026-09-17): "1 February being
    the expected date of supply, then working forwards in three month
    increments." NOT calendar quarters (Jan/Apr/Jul/Oct), which this
    replaced. Computed on a continuous months-since-year-0 index rather
    than per-case month arithmetic, so the year boundary (a January or
    December date's quarter actually starts the PRIOR November) falls
    out of the same formula instead of needing special-casing - verified
    against both a January date (2026-01-15 -> 2025-11-01, the Nov-Jan
    quarter it's really in) and the exact anchor month (2026-09-17 ->
    2026-08-01) before trusting it."""
    total_months = d.year * 12 + (d.month - 1)  # 0 = Jan of year 0
    feb_offset = 1  # February = month index 1 within a year (Jan=0)
    quarter_index = (total_months - feb_offset) // 3
    start_total_months = quarter_index * 3 + feb_offset
    year, month = start_total_months // 12, start_total_months % 12 + 1
    return date(year, month, 1)


def _add_quarters(d: date, n: int) -> date:
    total_months = (d.month - 1) + n * 3
    year = d.year + total_months // 12
    month = total_months % 12 + 1
    return date(year, month, 1)


# Rolling window ending on the anchor date ("today" by default, pinnable
# via GENERATOR_ANCHOR_DATE - see anchor_date.py), same fix and rationale
# as generate_runs.py's own START_DATE - un-stales the fixture generally
# (plans/qa-pipeline.md #3's follow-up covers both). No wall-clock-
# relative check depends on CP's dates today, unlike BDM's, but there's
# no reason to leave CP's snapshots drifting stale either.
_anchor = get_anchor_date()
START_DATE = _add_quarters(_quarter_start(_anchor), -(N_QUARTERS - 1))


def _add_extract_timestamp(df: pd.DataFrame, snapshot_date: date, date_col: str | None, seed: int) -> pd.DataFrame:
    """extract_timestamp = snapshot_date + a few hours, same convention
    agency_datasets.py uses for birth_registrations - not tied to any
    per-row date column, since this is a whole-collection re-extract, not
    a per-record event timestamp."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    base = pd.Timestamp(snapshot_date)
    out["extract_timestamp"] = base + pd.to_timedelta(rng.integers(1, 8, size=len(out)), unit="h")
    return out


def _pick_dirty_tables(seed: int, available: list[str] | None = None) -> set[str]:
    """Which 2-3 of the 6 real tables actually fail on a given dirty
    delivery/attempt - not all of them (Keith's own call, 2026-09-18
    dictated feedback: "it should be possible for only some tables in
    CP to fail... two or three could fail, and the rest could be
    fine") - a real data-quality incident rarely touches every table in
    a collection at once. Picked fresh per dirty() call (so a resupply
    attempt that's still red can plausibly fail a DIFFERENT subset than
    its first attempt did, not the same one every time), seeded off
    that call's own `seed` so it stays reproducible. A separate,
    directly-testable pure function rather than inlined into dirty()
    itself, so this real invariant (never 0/1, never all 6) can be unit
    tested without needing realistic fake table content just to satisfy
    the real per-table preset functions' own column requirements.

    `available` narrows the pick to the tables actually being sent
    (REQ-GEN-040). A partial resupply ships two of the six, and picking
    2-3 out of all six would usually land on tables that are not in the
    delivery at all - producing an arrival the chain calls red whose
    files are clean. Defaulting to every table keeps a whole-collection
    delivery drawing exactly the numbers it drew before, so this
    signature change moves nothing about today's generated history.
    Where only one table is being sent, that one is dirtied: "never 1"
    is an invariant about a six-table delivery, not a rule that a
    single-table one must come back clean."""
    tables = list(TABLES if available is None else available)
    rng = np.random.default_rng(seed)
    n_dirty = min(int(rng.integers(2, 4)), len(tables))  # 2 or 3, or all of a smaller delivery
    return set(rng.choice(tables, size=n_dirty, replace=False))


# Churn (resupply attempt N -> N+1) touches only these three "activity"
# tables - cp_clients/cp_carers/cp_case_workers are comparatively stable
# reference entities that don't meaningfully move within a resupply's
# short (weeks, not months) window, so they pass through unchanged
# rather than getting a token, meaningless nudge. Deliberately no REMOVE
# step (unlike Birth Registrations' own churn()), found the hard way
# 2026-09-18: independently dropping ~1% of rows from cp_notifications
# and cp_investigations broke the escalation-completeness business rule
# for real (an "Investigation opened" notification whose matching
# investigation got independently removed) on what should have been a
# genuinely clean resupply attempt - a real bug, caught by the
# aggregate-status pill reading red on a dirty_severity:null run, not
# assumed away. child_protection.py's own generation keeps every cross-
# table business rule clean BY CONSTRUCTION (this file's own top
# docstring); an uncoordinated per-table remove breaks that invariant,
# so churn stays modify-only - real drift (a timestamp nudge) without
# ever risking a spurious cross-table violation.
_CHURN_TABLES = ["cp_notifications", "cp_investigations", "cp_placements"]
_CHURN_MODIFY_RATE = 0.02


class ChildProtectionProvider:
    """The DatasetProvider (generator/resupply.py) for Child Protection -
    payload is a dict[str, pd.DataFrame], one entry per real table
    (TABLES), not a single DataFrame like Birth Registrations' own
    provider - see resupply.py's own docstring for why that module is
    now generic over this. Reference tables passed to the dangling-FK
    injectors and cp_investigations' closed-case eligibility filter
    stay pinned to `self.base_tables` (the true, never-dirtied source)
    for every attempt in a chain, not whatever a given attempt's own
    (possibly churned) payload happens to look like - a deliberate
    simplification consistent with a resupply's own "the same
    underlying collection, corrected" framing (plans/conceptual-
    design.md Thread A's whole redesign rationale), not a fresh random
    draw of the population each attempt."""

    def __init__(self, base_tables: dict[str, pd.DataFrame]):
        self.base_tables = base_tables

    def generate(self, run_date: date, seed: int, n_rows: int, id_offset: int) -> dict[str, pd.DataFrame]:
        # extract_timestamp is set exactly once, here, before any dirty()/
        # churn() - a row dirty() later duplicates (e.g. cp_notifications'
        # near-duplicate-submission injector) inherits its source row's
        # timestamp rather than a fresh independent draw - a real but
        # minor imprecision (a genuine double-submission would usually
        # arrive at a distinct moment) that no real check here actually
        # depends on (nothing validates extract_timestamp variance across
        # near-duplicate rows, and the MIN/MAX arrival-lag stats are
        # unaffected by a duplicate sharing an already-present value).
        return {name: _add_extract_timestamp(self.base_tables[name], run_date, None, seed=seed + 5000)
                for name in TABLES}

    def dirty(self, payload: dict[str, pd.DataFrame], severity: str, seed: int,
              previous_row_count: int | None) -> dict[str, pd.DataFrame]:
        # Scoped to what this delivery actually CONTAINS - a partial
        # resupply has only the tables being resent (REQ-GEN-040).
        present = [t for t in TABLES if t in payload]
        dirty_tables = _pick_dirty_tables(seed, present)
        tables = dict(payload)
        base = self.base_tables
        if "cp_notifications" in dirty_tables:
            tables["cp_notifications"] = dirty_mod.apply_cp_notifications_presets(
                tables["cp_notifications"], base["cp_clients"], base["cp_case_workers"],
                severity, seed=seed + 100)
        if "cp_placements" in dirty_tables:
            tables["cp_placements"] = dirty_mod.apply_cp_placements_presets(
                # cp_carers is a REFERENCE here, not the table being
                # dirtied, so a partial resupply that does not contain
                # it falls back to the true source - which is what the
                # class docstring says reference tables are anyway.
                tables["cp_placements"], tables.get("cp_carers", base["cp_carers"]), base["cp_clients"],
                severity, seed=seed + 200)
        if "cp_investigations" in dirty_tables:
            tables["cp_investigations"] = dirty_mod.apply_cp_investigations_presets(
                tables["cp_investigations"], base["cp_clients"], base["cp_notifications"],
                base["cp_case_workers"], severity, seed=seed + 300)
        if "cp_clients" in dirty_tables:
            tables["cp_clients"] = dirty_mod.apply_cp_clients_presets(
                tables["cp_clients"], severity, seed=seed + 400)
        if "cp_carers" in dirty_tables:
            tables["cp_carers"] = dirty_mod.apply_cp_carers_presets(
                tables["cp_carers"], severity, seed=seed + 500)
        if "cp_case_workers" in dirty_tables:
            tables["cp_case_workers"] = dirty_mod.apply_cp_case_workers_presets(
                tables["cp_case_workers"], severity, seed=seed + 600)
        return tables

    def resupply_subset(self, payload: dict[str, pd.DataFrame], previous_dirty_seed: int,
                         seed: int) -> dict[str, pd.DataFrame]:
        """The tables a resupply actually sends back - SOME of what
        failed, not all of it, and not the whole collection
        (REQ-GEN-040, Keith's own call 2026-09-23).

        A supplier told three tables are wrong does not necessarily
        return all three at once; they fix what they can and the rest
        follows. Modelling it that way is what produces two shapes the
        model has to handle and the generator could not previously
        make: a delivery carrying SOME of a collection's tables, and a
        delivery carrying exactly ONE - a supply for one dataset with
        no supply for any of its siblings.

        Rejected resending exactly the failed set, which is the simpler
        and arguably more typical single behaviour: it can never
        produce a one-table delivery, because a failure is never
        narrower than two tables by construction (_pick_dirty_tables).

        What failed is RECOMPUTED from the seed that dirtied the
        arrival being corrected, never remembered on this object - see
        DatasetProvider.resupply_subset()'s own docstring for why a
        provider shared across every slot must not carry per-chain
        state.
        """
        present = [t for t in TABLES if t in payload]
        failed = sorted(_pick_dirty_tables(previous_dirty_seed, present))
        if not failed:  # defensive - a chain only resupplies what went red
            return payload
        rng = np.random.default_rng(seed)
        n_sent = int(rng.integers(1, len(failed) + 1))
        sent = set(rng.choice(failed, size=n_sent, replace=False))
        return {name: df for name, df in payload.items() if name in sent}

    def churn(self, payload: dict[str, pd.DataFrame], seed: int, run_date: date,
              id_offset: int) -> dict[str, pd.DataFrame]:
        """Between one attempt and the next, the underlying casework
        hasn't frozen either - a small-rate extract_timestamp nudge on
        the three "activity" tables, as if a few records were re-pulled
        slightly later in the same re-extract. Deliberately NO add or
        remove step (unlike Birth Registrations' own churn(), which does
        add/modify/remove): CP's population and casework are built ONCE
        from a fixed seed, so adding rows would mean running the
        population-linked generator further - a documented
        simplification, not an oversight - and independently REMOVING
        rows from related tables real-broke a real cross-table business
        rule (see _CHURN_TABLES' own comment above) - the modify-only
        version can never do that, since it never changes which rows
        exist, only when they were extracted."""
        rng = np.random.default_rng(seed)
        out = dict(payload)
        # Always the WHOLE collection: run_slot_chain churns the clean
        # lineage forward and only then asks what part of it is being
        # resent, so churn never sees a partial payload (REQ-GEN-040).
        for table in _CHURN_TABLES:
            df = out[table].copy()
            modify_mask = rng.random(len(df)) < _CHURN_MODIFY_RATE
            modify_idx = np.where(modify_mask)[0]
            if len(modify_idx):
                shift = pd.to_timedelta(rng.integers(1, 6, size=len(modify_idx)), unit="h")
                df.loc[df.index[modify_idx], "extract_timestamp"] = (
                    pd.to_datetime(df.loc[df.index[modify_idx], "extract_timestamp"]) + shift
                )
            out[table] = df
        return out



def _cp_received_at(payload: dict, received_date: date, where: str) -> str:
    """This delivery's own receipt instant, across all six tables.

    Same rule as Birth Registrations' own `_received_at`, for the same
    reasons: the DATE comes from the chain, because a resupply lands
    days after the slot it fills, and the TIME OF DAY comes from the
    data, because the arrival calibration already lives there. Taking
    both from the payload would give every arrival in one slot the same
    instant, days apart in reality.

    Across six tables, the earliest legitimate extract wins - the
    collection arrives as one supply, so it has one receipt instant.
    """
    earliest = None
    for name in TABLES:
        df = payload[name]
        if "extract_timestamp" not in df.columns:
            continue
        stamps = pd.to_datetime(df["extract_timestamp"], errors="coerce").dropna()
        if stamps.empty:
            continue
        candidate = pd.Timestamp(stamps.min()).to_pydatetime()
        if earliest is None or candidate < earliest:
            earliest = candidate
    if earliest is None:  # no table carries one - defensive
        return asset_time.record_source_instant(
            datetime.combine(received_date, datetime.min.time()), where)
    return asset_time.record_source_instant(
        datetime.combine(received_date, earliest.time()), where)

def _cp_manifest_entries_for_slot(deliveries: list, slot_id: str, period: str,
                                       run_index_start: int, seed: int) -> list[dict]:
    """Pure manifest-entry construction for the deliveries filling ONE
    SLOT - the CP counterpart to generate_runs.py's own
    _manifest_entries_for_slot(), same dateless run_id convention, but
    `row_counts` (one count per real table) instead of a single
    `n_rows_generated`/`file`, since CP writes one directory of 6 CSVs
    per delivery rather than one CSV."""
    entries = []
    for delivery_obj in deliveries:
        # Dateless and derived from the manifest position, so a
        # regeneration overwrites in place instead of writing a second
        # history beside the first (REQ-GEN-042). No resupply marker
        # either - which arrival is a resupply is observed from the
        # record, not asserted by whatever produced it.
        run_index = run_index_start + len(entries) + 1
        run_id = f"cp_run_{run_index:03d}"
        entries.append({
            "run_id": run_id,
            "run_index": run_index,
            "slot_id": slot_id,
            "period": period,
            "received_at": None,  # filled in by main() from the payload's own earliest extract
            "dirty_severity": delivery_obj.severity,  # None | "amber" | "red" - this ARRIVAL's own outcome
            "seed": seed,
            "row_counts": {name: int(len(delivery_obj.payload[name])) for name in TABLES},
        })
    return entries



def _write_bookkeeping(manifest: list[dict]) -> None:
    """The generator's own record, OUTSIDE every delivery (criterion 6).

    Which slot each delivery was built to fill, which scenario it came
    from, what severity was injected - real and worth keeping, because
    it is how a test asserts that recognition got the right answer.

    NO PIPELINE, QA OR DASHBOARD-BUILD MODULE MAY READ IT (criterion 7).
    One that did would be making filing decisions from a declaration
    rather than from arrival plus slot state, which is the
    supplier-declared manifest Thread B rejected wearing our own badge.
    The generator reads it back for one purpose only: to delete what it
    wrote last time, so a regeneration overwrites rather than
    accumulates.
    """
    path = BOOKKEEPING_PATH
    book = {}
    if path.exists():
        with open(path) as f:
            book = json.load(f)
    book[DATASET_ID] = manifest
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(book, f, indent=2)


def _previous_delivery_names() -> list[str]:
    """What this generator wrote last time, from its own bookkeeping."""
    path = BOOKKEEPING_PATH
    if not path.exists():
        return []
    with open(path) as f:
        book = json.load(f)
    return [e["delivery"] for e in book.get(DATASET_ID, []) if e.get("delivery")]

def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Generating base Child Protection collection (population={POPULATION_N:,}, seed={BASE_SEED})...")
    pop = generate_population(POPULATION_N, seed=BASE_SEED)
    base_tables = generate_child_protection_collection(pop, seed=BASE_SEED + 1000, n_case_workers=N_CASE_WORKERS)
    for name in TABLES:
        print(f"  {name}: {len(base_tables[name]):,} rows")

    provider: DatasetProvider = ChildProtectionProvider(base_tables)
    manifest = []
    # Arbitrary names can collide, and a collision would merge two
    # arrivals into one directory. Enforced, not hoped for.
    # Clear what THIS generator wrote last time, so a regeneration
    # overwrites its own history rather than accumulating beside it
    # (REQ-GEN-042), then seed uniqueness from whatever the OTHER
    # generator has on disk so two arrivals can never share a
    # directory (REQ-GEN-043).
    delivery.remove_deliveries(_previous_delivery_names(), DELIVERIES_DIR, RECEIPTS_DIR)
    taken_names: set[str] = delivery.existing_delivery_names(DELIVERIES_DIR)
    # The same quarterly calendar the pipeline judges these supplies
    # against - not a private copy of the cadence (REQ-GEN-042). A
    # generator carrying its own would place supplies against one
    # schedule while the pipeline measured them against another, and the
    # disagreement would read as a model failure rather than a config
    # duplication.
    periods = schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date())[-len(RUN_PLAN):]

    for i, ((_, severity), period) in enumerate(zip(RUN_PLAN, periods), start=1):
        snapshot_date = period.date
        slot_id = f"cp_slot_{i:02d}"
        seed = BASE_SEED + i

        deliveries = list(run_slot_chain(
            provider, snapshot_date, seed, id_offset=0, n_rows=0,
            first_severity=severity, previous_row_count=None,
            delay_days=_CP_DELAY_DAYS, delay_weights=_CP_DELAY_WEIGHTS,
        ))
        entries = _cp_manifest_entries_for_slot(deliveries, slot_id, period.name, len(manifest), seed)

        for n, (delivery_obj, entry) in enumerate(zip(deliveries, entries), start=1):
            run_dir = os.path.join(OUT_DIR, entry["run_id"])
            os.makedirs(run_dir, exist_ok=True)
            csvs = {}
            for name in TABLES:
                df = delivery_obj.payload[name]
                cols = [c for c in df.columns if not c.startswith("_")]
                df[cols].to_csv(os.path.join(run_dir, f"{name}.csv"), index=False)
                csvs[f"{name}.csv"] = df[cols].to_csv(index=False)
            entry["received_at"] = _cp_received_at(
                delivery_obj.payload, delivery_obj.received_date, f"received_at for {entry['run_id']}")

            # AND AS A REAL DELIVERY (REQ-GEN-043). All six tables in
            # ONE directory, because they arrive together as one
            # extract - six deliveries would be six arrivals that never
            # happened (criterion 11). Each filename matches its own
            # dataset's configured arrivalPattern, so which dataset a
            # file belongs to is derivable from the name alone.
            dname = delivery_names.delivery_name(snapshot_date, seed, attempt=n, taken=taken_names)
            taken_names.add(dname)
            entry["delivery"] = dname
            delivery.write_delivery(
                dname, csvs,
                received_at=asset_time.parse_instant(entry["received_at"], entry["run_id"]),
                deliveries_dir=DELIVERIES_DIR, receipts_dir=RECEIPTS_DIR)

            tag = f"DIRTY({delivery_obj.severity})" if delivery_obj.severity else "clean"
            resupply_tag = (f"  [resupply {n - 1}, received "
                             f"{delivery_obj.received_date.isoformat()}]") if n > 1 else ""
            print(f"{entry['run_id']}: {entry['row_counts']['cp_notifications']:5d} notifications  "
                  f"[{tag}]{resupply_tag}  -> {dname}/")
            if delivery_obj.severity == "red" and n >= MAX_ATTEMPTS:
                print(f"  -> still red after {n} deliveries - "
                      f"giving up (hit MAX_ATTEMPTS={MAX_ATTEMPTS})")

        manifest.extend(entries)

    # NO manifest.json ANY MORE (REQ-GEN-043). It held exactly the
    # list below, which _write_bookkeeping() also holds - two copies of
    # the same bookkeeping, in two files, able to disagree. Nothing in
    # the pipeline had read it since arrivals became recognised rather
    # than declared, so the only thing it could still do was tempt
    # somebody to wire it back up.
    _write_bookkeeping(manifest)
    n_red_slots = sum(1 for _, sev in RUN_PLAN if sev == "red")
    print(f"\nWrote {len(manifest)} deliveries across {len(RUN_PLAN)} scheduled slots "
          f"({n_red_slots} of which went red and triggered a resupply chain) "
          f"to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
