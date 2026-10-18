"""Child Protection's generator provider (REQ-GEN-246): the collection's
rows, seed schedule and period plan. The slot loop, the bookkeeping,
delivery and receipt writing and injection placement are the shared
driver's (generator/driver.py); this module was generator/generate_cp_runs.py,
and everything below that is not the driver's moved here unchanged, so the
generated history is byte-identical.

IMPORTABLE WITHOUT pandas OR numpy (criterion 7): every tool import is
deferred to the function that needs it; RUN_PLAN, GROWN_RUN_PLAN and the
resupply delay curve are computed on first use.

Generates periodic Child Protection collection snapshots as real
deliveries - the "whole collection" counterpart to civil_registration.py's
daily birth-registrations feed. Each snapshot is ONE delivery holding
all six tables, because they arrive together as one extract.

Deliberately a different generation model from civil_registration.py, by design
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
all). Reuses civil_registration.py's own generic chain-orchestration engine
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
civil_registration.py's BirthRegistrationsProvider remains the BDM one,
unchanged. The dashboard-side supply-history UI needed NO changes for
this - Phase 7's own resupply-chain redesign (plans/conceptual-
design.md Thread A) already derives chain membership purely from real
per-run aggregate status, dataset-agnostic by construction ("nothing
about the model assumes BDM-only" - that file's own words, written
before this was actually built).
"""
from __future__ import annotations

import dataclasses
import functools
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from qa_tools.common import hierarchy
from generator.anchor_date import get_anchor_date
from generator.collections.base import Job, Plan, Provider
from qa_tools.common import asset_time, schedule

if TYPE_CHECKING:  # annotations only - never imported at module level
    import pandas as pd
    from generator.resupply import DatasetProvider

# Which dataset's calendar this collection is scheduled against. All six
# CP tables arrive together as one supply, so any of them names the same
# quarterly calendar - cp-clients is simply the first.
DATASET_ID = "cp-clients"


POPULATION_N = 70_000
N_CASE_WORKERS = 60
BASE_SEED = 5000  # distinct range from civil_registration.py's 1000s and generate.py's demo seeds

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
@functools.cache
def _cp_delay():
    """(_CP_DELAY_DAYS, _CP_DELAY_WEIGHTS), built on first use."""
    import numpy as np

    days = np.arange(5, 21)
    weights = 0.8 ** (days - 5)
    return days, weights / weights.sum()

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
# project's real data never extends past - see civil_registration.py's
# identical BDM-side convention). Ratio/shape below (first run clean,
# last run red, ~25% amber in between) is unchanged from the calendar-
# quarter version - only N_QUARTERS and _quarter_start()'s anchor month
# moved.
_RUN_PLAN_SEED = 5900  # distinct range from generation seeds (BASE_SEED+...)
N_QUARTERS = 15


def _build_run_plan(n: int, seed: int) -> list[tuple[int, str | None]]:
    import numpy as np

    rng = np.random.default_rng(seed)
    n_amber = max(1, round(n * 0.25))  # ~matches the original plan's 2/10 ratio
    # Two RED deliveries at a random position among every NON-FIRST slot
    # (2026-09-18, CP resupply simulation) - matches Birth Registrations'
    # own precedent (RUN_PLAN's own comment in civil_registration.py: "bumped
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


@functools.cache
def run_plan() -> list[tuple[int, str | None]]:
    """RUN_PLAN, drawn on first use (criterion 7)."""
    return _build_run_plan(N_QUARTERS, _RUN_PLAN_SEED)

# TEN YEARS MORE AT THE OLD END (REQ-GEN-207, Keith, 2026-10-15): forty
# quarters before the original fifteen, so the scenarios still to be planted
# each have a quarter of their own. DRAWN AND WRITTEN SEPARATELY (criterion 4):
# everything that counts from the oldest quarter - seeds, slot ids, run
# indices, delivery names, ambers - is the original fifteen's exactly as it was,
# because those are planned and written first, and the grown quarters take a
# run plan, seeds and slot ids of their own afterwards. The same mix as the
# original plan (Keith): about a quarter amber, two reds, the oldest clean.
GROWN_QUARTERS = 40
_GROWN_PLAN_SEED = 29000   # disjoint from _RUN_PLAN_SEED and every BASE_SEED offset
GROWN_BASE_SEED = 30000    # seeds 30001.. and their +500/+800/+900 offsets
@functools.cache
def grown_run_plan() -> list[tuple[int, str | None]]:
    """GROWN_RUN_PLAN, drawn on first use (criterion 7)."""
    return _build_run_plan(GROWN_QUARTERS, _GROWN_PLAN_SEED)


def __getattr__(name: str):
    """The plans and the delay curve as module attributes, computed when
    first asked for rather than at import (criterion 7)."""
    if name == "RUN_PLAN":
        return run_plan()
    if name == "GROWN_RUN_PLAN":
        return grown_run_plan()
    if name == "_CP_DELAY_DAYS":
        return _cp_delay()[0]
    if name == "_CP_DELAY_WEIGHTS":
        return _cp_delay()[1]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
_CASE_WORKERS = "cp-case-workers"


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
# as civil_registration.py's own START_DATE - un-stales the fixture generally
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
    import numpy as np
    import pandas as pd

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
    import numpy as np

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
        # AMBER BY CONSTRUCTION, on client postcodes alone (REQ-GEN-184
        # criteria 7 and 8): the preset dirtied two or three tables at rates
        # that read red. Red keeps the preset (criterion 10).
        if severity == "amber" and "cp_clients" in payload:
            from generator import targeting

            return targeting.cp_amber(payload, seed=seed)
        # Scoped to what this delivery actually CONTAINS - a partial
        # resupply has only the tables being resent (REQ-GEN-040).
        from generator import dirty as dirty_mod

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
        import numpy as np

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
        import numpy as np
        import pandas as pd

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
    import pandas as pd

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
    SLOT - the CP counterpart to civil_registration.py's own
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
            "received_at": None,  # filled in by received_at(), via the driver
            "dirty_severity": delivery_obj.severity,  # None | "amber" | "red" - this ARRIVAL's own outcome
            "seed": seed,
            "row_counts": {name: int(len(delivery_obj.payload[name])) for name in TABLES},
        })
    return entries



def _injected_chain(provider: DatasetProvider, injection, period, seed: int,
                    placement=None, drawn: str | None = None):
    """The arrivals ONE injected scenario needs, in place of the
    ordinary chain (REQ-GEN-044) - the Child Protection counterpart to
    civil_registration.py's own, and see that one's docstring for why an
    injected slot does not go through run_slot_chain().

    Each arrival after the first is CHURNED from the one before, which
    for this collection means the whole six-table payload moves on
    together - a corrected resupply of one table is still taken from a
    collection that did not stand still.
    """
    from generator.resupply import Delivery

    deliveries = []
    payload = provider.generate(period.date, seed=seed, n_rows=0, id_offset=0)
    for n, extra in enumerate(injection.arrivals):
        if n:
            payload = provider.churn(payload, seed=seed + 900 + n,
                                      run_date=period.date, id_offset=0)
        this = payload
        if extra.target is not None:
            # BUILT TO A TARGET, NEVER THE PRESET (REQ-GEN-184 criterion 1).
            from generator import targeting

            this, moved = targeting.cp_target(
                payload, extra.target, seed=seed + 800 + n,
                where=f"{injection.scenario_id}, its {extra.at} arrival")
            if placement is not None:
                placement.arrivals[n]["target"]["moved"] = moved
        elif extra.severity and extra.severity_tables:
            # ONLY THE TABLES NAMED (REQ-GEN-199 criterion 1): TS-75 is red by
            # cp_clients' own preset alone, the other five clean.
            only = {t: payload[t] for t in extra.severity_tables}
            this = {**payload, **provider.dirty(only, severity=extra.severity,
                                                 seed=seed + 800 + n,
                                                 previous_row_count=None)}
        elif extra.severity:
            this = provider.dirty(payload, severity=extra.severity,
                                   seed=seed + 800 + n, previous_row_count=None)
        severity = extra.severity
        if (not extra.severity and extra.target is None and n == 0
                and drawn == "amber" and injection.keeps_drawn_severity):
            # THE PERIOD'S OWN DRAWN SEVERITY, on the tables the scenario
            # does not shape (REQ-GEN-199, PROVISIONAL).
            this = provider.dirty(payload, severity=drawn, seed=seed + 800,
                                   previous_row_count=None)
            severity = drawn
        if extra.files:
            # TWO FILES FOR ONE TABLE (REQ-GEN-203 criterion 2): the pair's own
            # files, each with its own receipt, beside the other tables.
            deliveries.append(PairDelivery(
                received_date=period.date + timedelta(days=extra.day_offset),
                severity=severity, payload=this,
                files=_pair_files(provider, injection, extra, n, this, period, seed,
                                  placement)))
            continue
        deliveries.append(Delivery(
            received_date=period.date + timedelta(days=extra.day_offset),
            severity=severity, payload=this))
    return deliveries


@dataclasses.dataclass
class PairDelivery:
    """ONE DELIVERY CARRYING TWO FILES for one of its tables (REQ-GEN-203),
    Birth Registrations' PairDelivery for a six-table collection: `payload`
    is every table as built, which sizes and describes the delivery, and
    `files` the pair's own files - filename -> (CSV text, wall-clock receipt
    on received_date) - which replace their table's usual file."""

    received_date: date
    severity: str | None
    payload: dict
    files: dict


#: What a pair file of this collection may be. `next_day` is Birth
#: Registrations' - a quarterly extract is not sent a period early in one
#: delivery with its own.
PAIR_CONTENTS = ("extract", "duplicate", "corrected", "re_export")


def _re_exported(df: pd.DataFrame) -> pd.DataFrame:
    """The table re-pulled from the source system: the same rows, each
    extracted an hour later than the extract it repeats - so the rows differ
    while neither file is wrong (REQ-GEN-203, TS-42)."""
    import pandas as pd

    out = df.copy()
    out["extract_timestamp"] = pd.to_datetime(out["extract_timestamp"]) + pd.Timedelta(hours=1)
    return out


def _pair_files(provider, injection, extra, n: int, base: dict, period, seed: int,
                placement) -> dict:
    """A pair's files, built as the injection says (REQ-GEN-203): each file's
    content from its table as built, then its target or severity, then its
    named shapes. A SHAPE, NEVER A VERDICT - the pipeline decides."""
    from generator import scenario_injection, targeting

    day = period.date + timedelta(days=extra.day_offset)
    files: dict[str, tuple[str, str]] = {}
    previous = None
    for k, f in enumerate(extra.files):
        where = f"{injection.scenario_id}, its {extra.at} delivery, file {k + 1}"
        if f.content == "duplicate":
            if previous is None:
                raise scenario_injection.CannotPlace(
                    f"{where} is a duplicate of nothing - a duplicate follows the file it "
                    f"copies")
            csv = previous
        else:
            df = base[f.table]
            if f.content == "re_export":
                df = _re_exported(df)
            if f.target is not None:
                built, moved = targeting.cp_target({**base, f.table: df}, f.target,
                                                   seed=seed + 810 + k, where=where)
                df = built[f.table]
                if placement is not None:
                    placement.arrivals[n]["files"][k]["target"]["moved"] = moved
            elif f.severity:
                df = provider.dirty({f.table: df}, severity=f.severity, seed=seed + 820 + k,
                                    previous_row_count=None)[f.table]
            csv = df[[c for c in df.columns if not c.startswith("_")]].to_csv(index=False)
            for shape in f.shapes:
                csv = scenario_injection.shape_file(shape, csv)
        files[f.filename(day)] = (csv, f.at)
        previous = csv
    return files


def _pair_problems(injection) -> list[str]:
    """Why a Child Protection pair cannot be built as declared, before the
    first write (REQ-GEN-044 criterion 4)."""
    out = []
    for extra in injection.arrivals:
        if not extra.files:
            continue
        where = f"{injection.scenario_id}, its {extra.at} delivery"
        if extra.at != min(f.at for f in extra.files):
            out.append(f"{where}: the delivery's `at` is its earliest file's receipt, and "
                       f"its files arrive from {min(f.at for f in extra.files)}")
        for k, f in enumerate(extra.files, 1):
            if f.table not in TABLES:
                out.append(f"{where}, file {k}: names table {f.table!r}, which is not one "
                           f"of {', '.join(TABLES)}")
            if f.content not in PAIR_CONTENTS:
                out.append(f"{where}, file {k}: {f.content!r} is not a Child Protection "
                           f"pair file's content - one of {', '.join(PAIR_CONTENTS)}")
            if f.target is not None and f.target.verdict != "green" and f.table != "cp_clients":
                out.append(f"{where}, file {k}: a {f.target.verdict} target is built on "
                           f"client postcodes, and this file is {f.table}")
    return out


def generated_periods() -> list:
    """The periods this generator writes, oldest first - one delivery each:
    the grown quarters, then the original fifteen (REQ-GEN-207)."""
    return schedule.periods_for_dataset(
        DATASET_ID, until=get_anchor_date())[-(len(grown_run_plan()) + len(run_plan())):]


def original_periods() -> list:
    """The original fifteen, whose plan, seeds and slots are RUN_PLAN's."""
    return generated_periods()[-len(run_plan()):]


def grown_periods() -> list:
    """The quarters REQ-GEN-207 added before them, oldest first."""
    return generated_periods()[:-len(run_plan())]


def _drawn_by_period(periods) -> dict:
    """Each period's drawn severity by name, from whichever plan owns it."""
    plan, grown_plan = run_plan(), grown_run_plan()
    names = [p.name for p in periods]
    grown, original = names[:-len(plan)], names[-len(plan):]
    return {**dict(zip(grown[-len(grown_plan):], (s for _q, s in grown_plan))),
            **dict(zip(original, (s for _q, s in plan)))}


def _plan_injections(periods):
    """Where every Child Protection scenario lands, resolved BEFORE
    anything is written (REQ-GEN-044 criterion 4)."""
    # EVERY DATASET OF THE COLLECTION, not cp-clients alone: one delivery
    # carries all six tables, so an injection about any of them is placed
    # against the delivery's periods. Planning cp-clients' only skipped
    # TS-56 (cp-carers) without a word - criterion 4's silent absence.
    from generator import scenario_injection

    ours = {d.dataset_id for d in hierarchy.datasets_in_collection("child-protection")}
    mine = [i for i in scenario_injection.INJECTIONS if i.dataset_id in ours]
    # ONE DELIVERY PER PERIOD, so two injections may not share one whatever
    # their datasets: checked as if they were all one dataset's.
    scenario_injection.no_two_scenarios_share_a_period(
        [dataclasses.replace(i, dataset_id=DATASET_ID) for i in mine], {DATASET_ID: periods})
    resolved = [(injection, scenario_injection.resolve(injection, periods))
                for injection in mine]
    # EVERY TARGET CHECKED BEFORE THE FIRST WRITE (REQ-GEN-184 criterion 11).
    from generator import targeting

    # A TARGETED SUPPLY HAS GREEN LEAD-IN AND FOLLOWING QUARTERS (REQ-GEN-203
    # criterion 4, as REQ-GEN-185 for Birth Registrations), which lifted
    # post-build-review #156's refusal: resolve() above names them and refuses,
    # naming the scenario, where the history cannot hold them; _severities()
    # builds each as one clean delivery, and slot() writes it. Every delivery
    # is the same base collection, so it is sized to the lead-in by construction.
    for injection in mine:
        problems = _pair_problems(injection)
        if problems:
            raise scenario_injection.CannotPlace("; ".join(problems))
        for extra in injection.arrivals:
            for target in extra.targets:
                targeting.check_target(target, injection.dataset_id,
                                       f"{injection.scenario_id}, its {extra.at} arrival")
    by_period = {placement.period: (injection, placement)
                 for injection, placement in resolved}
    # A DRAWN RED ON A KEEPS-DRAWN QUARTER IS REFUSED (the critic's G2): the
    # scenario keeps only an amber, so a red would be planned and not written.
    for injection, placement in resolved:
        if injection.keeps_drawn_severity:
            drawn = _drawn_by_period(periods).get(placement.period)
            if drawn == "red":
                raise scenario_injection.CannotPlace(
                    f"{injection.scenario_id}: an ordinary red is drawn for {placement.period}, "
                    f"which this scenario keeps the drawn severity of - it keeps only an amber. "
                    f"Move the anchor to a quarter drawn clean or amber.")
    return resolved, by_period


def _severities(plan, periods, injected_by_period) -> list:
    """Each drawn severity, with every ordinary amber that cannot be
    generated where it was drawn - in a `hold` amber-setting era, or on a
    period an injected scenario owns, whose chain ignores the drawn
    severity - moved to a clean period that can take it, so the number
    generated equals the number drawn (REQ-GEN-184 criterion 9;
    post-build-review #154). The first period stays clean, and a lead-in or
    following period is one clean delivery (REQ-GEN-185)."""
    from generator import targeting

    green = frozenset(name for _inj, placement in injected_by_period.values()
                      for name in placement.built_green)
    # A SCENARIO THAT KEEPS ITS PERIOD'S DRAWN SEVERITY (REQ-GEN-199) can
    # carry an ordinary amber like any clean period.
    unavailable = frozenset(i for i, p in enumerate(periods)
                            if (p.name in injected_by_period
                                and not injected_by_period[p.name][0].keeps_drawn_severity)
                            or p.name in green)
    out = targeting.outside_hold([sev for _q, sev in plan[:len(periods)]],
                                 [p.date for p in periods], "cp-clients",
                                 keep_clean=frozenset({0}), unavailable=unavailable)
    # A LEAD-IN OR FOLLOWING PERIOD IS A SINGLE CLEAN DELIVERY (REQ-GEN-185):
    # a clean chain is one arrival, with no resupply.
    return [None if p.name in green else sev for p, sev in zip(periods, out)]


def _ordinary_severities(periods, injected_by_period) -> list:
    """The original fifteen quarters' severities (_severities). A drawn red on a
    lead-in or following quarter is refused naming the scenario, as in the
    grown quarters: that quarter is one clean delivery, so the red would be
    planned and never written."""
    from generator import scenario_injection

    drawn = {p.name: sev for p, (_q, sev) in zip(periods, run_plan())}
    for injection, placement in injected_by_period.values():
        for name in placement.built_green:
            if drawn.get(name) == "red":
                raise scenario_injection.CannotPlace(
                    f"{injection.scenario_id}: an ordinary red is drawn for {name}, which the "
                    f"scenario needs generated green - move its anchor to a quarter whose "
                    f"lead-in and following quarters are drawn clean or amber")
    return _severities(run_plan(), periods, injected_by_period)


def _grown_severities(periods, injected_by_period) -> list:
    """The grown quarters' severities (REQ-GEN-207), placed as the original
    fifteen's are (_severities) - a drawn amber moved off a scenario's
    quarter, its lead-in and following quarters clean (REQ-GEN-203 and 218
    plant scenarios here; post-build-review #207 D3 refused one until then).

    A DRAWN RED ON A SCENARIO'S QUARTER, OR ITS LEAD-IN OR FOLLOWING ONE, IS
    REFUSED naming the scenario: outside_hold moves ambers only, and the red
    chain would be swallowed by the scenario's own arrivals."""
    from generator import scenario_injection

    plan = grown_run_plan()
    drawn = {p.name: sev for p, (_q, sev) in zip(periods, plan)}
    for period, (injection, placement) in injected_by_period.items():
        for name in (period, *placement.built_green):
            if drawn.get(name) == "red":
                raise scenario_injection.CannotPlace(
                    f"{injection.scenario_id}: an ordinary red is drawn for the grown quarter "
                    f"{name}, which the scenario needs to itself - move its anchor to a "
                    f"quarter whose own and lead-in quarters are drawn clean or amber")
    return _severities(plan, periods, injected_by_period)


#: The largest offset any derivation adds to a slot's own seed: generate()'s
#: +5000 for the extract timestamps, above the resupply chain's +900, the
#: per-table presets' +600 and their own +19.
SEED_SPAN = 5999


class ChildProtection(Provider):
    """Child Protection's half of the shared driver (REQ-GEN-246): the old
    main()'s planning and per-slot decisions, unchanged, split across the
    driver's hooks."""

    collection_id = "child-protection"
    dataset_id = DATASET_ID
    seed_ranges = ((5000, 11100), (29000, 36100))
    # NO TARGET TRIAL: a six-table collection has no single target to try
    # (generator/validate_providers.py), its targeted supplies are green - the
    # delivery as built (REQ-GEN-203) - and ordinary ambers are compared after
    # the replay, never trialled (REQ-GEN-186, Keith 2026-10-11).
    target_trial = False
    target_datasets = (DATASET_ID,)
    target_levers = "client-postcodes"
    amber_dataset = DATASET_ID
    generating_note = f"population=70,000, {N_QUARTERS + GROWN_QUARTERS} quarterly snapshots"

    def seed_schedule(self) -> list[tuple[str, int, int]]:
        out = [("the population", BASE_SEED, BASE_SEED),
               ("the collection", BASE_SEED + 1000, BASE_SEED + 1000),
               ("the run plan", _RUN_PLAN_SEED, _RUN_PLAN_SEED),
               ("the grown quarters' plan", _GROWN_PLAN_SEED, _GROWN_PLAN_SEED)]
        out += [(f"cp_slot_{i:02d}", BASE_SEED + i, BASE_SEED + i + SEED_SPAN)
                for i in range(1, N_QUARTERS + 1)]
        out += [(f"cp_slot_{N_QUARTERS + j:02d}", GROWN_BASE_SEED + j,
                 GROWN_BASE_SEED + j + SEED_SPAN) for j in range(1, GROWN_QUARTERS + 1)]
        return out

    def generated_periods(self) -> list:
        return generated_periods()

    def plan(self) -> Plan:
        from synthetic_data_generator.child_protection import generate_child_protection_collection
        from synthetic_data_generator.population import generate_population

        print(f"Generating base Child Protection collection (population={POPULATION_N:,}, "
              f"seed={BASE_SEED})...")
        pop = generate_population(POPULATION_N, seed=BASE_SEED)
        base_tables = generate_child_protection_collection(pop, seed=BASE_SEED + 1000,
                                                           n_case_workers=N_CASE_WORKERS)
        for name in TABLES:
            print(f"  {name}: {len(base_tables[name]):,} rows")
        # The same quarterly calendar the pipeline judges these supplies
        # against - not a private copy of the cadence (REQ-GEN-042).
        periods = generated_periods()
        original, grown = original_periods(), grown_periods()

        # BEFORE THE FIRST WRITE (REQ-GEN-044 criterion 4).
        resolved_injections, injected_by_period = _plan_injections(periods)
        # ORDINARY AMBERS PLANNED BEFORE THE CLEAR TOO (post-build-review #155).
        # Each plan over its own periods (REQ-GEN-207 criterion 4).
        severities = _ordinary_severities(original, injected_by_period)
        grown_severities = _grown_severities(grown, injected_by_period)

        # THE ORIGINAL FIFTEEN FIRST, numbered and seeded exactly as before,
        # then the grown quarters (REQ-GEN-207 criterion 4).
        jobs = [Job(f"cp_slot_{i:02d}", BASE_SEED + i, severity, period)
                for i, (severity, period) in enumerate(zip(severities, original), start=1)]
        jobs += [Job(f"cp_slot_{len(original) + j:02d}", GROWN_BASE_SEED + j, severity, period)
                 for j, (severity, period) in enumerate(zip(grown_severities, grown), start=1)]
        return Plan(jobs=jobs, resolved=resolved_injections, injected_by_period=injected_by_period,
                    state={"provider": ChildProtectionProvider(base_tables), "original": original,
                           # A GROWN QUARTER CASE WORKERS OWES NOTHING IN CARRIES
                           # FIVE FILES (Keith, 2026-10-15): as a supplier sending
                           # twice a year would. The original fifteen keep sending
                           # all six, so their held shape stays.
                           "grown_names": {p.name for p in grown},
                           "green": frozenset(name for _inj, placement
                                              in injected_by_period.values()
                                              for name in placement.built_green),
                           "case_workers_owed": {p.name for p in schedule.periods_for_dataset(
                               _CASE_WORKERS) if p.expected}})

    def slot(self, plan: Plan, job: Job) -> list:
        from generator.resupply import run_slot_chain

        provider = plan.state["provider"]
        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None:
            return _injected_chain(provider, injected[0], job.period, job.seed,
                                   placement=injected[1], drawn=job.severity)
        if job.period.name in plan.state["green"]:
            # A GREEN LEAD-IN OR FOLLOWING QUARTER (REQ-GEN-203 criterion 4, as
            # REQ-GEN-185 criteria 1 and 3): once, on its own date, no resupply,
            # as built - a Child Protection green target is the delivery as built
            # (targeting.cp_target), so these are the bytes an ordinary clean
            # quarter writes.
            from generator import targeting
            from generator.resupply import Delivery

            payload, _moved = targeting.cp_target(
                provider.generate(job.period.date, seed=job.seed, n_rows=0, id_offset=0),
                targeting.Target("green"), seed=job.seed + 700,
                where=f"the green quarter {job.period.name}")
            return [Delivery(received_date=job.period.date, severity=None, payload=payload)]
        delay_days, delay_weights = _cp_delay()
        return list(run_slot_chain(
            provider, job.period.date, job.seed, id_offset=0, n_rows=0,
            first_severity=job.severity, previous_row_count=None,
            delay_days=delay_days, delay_weights=delay_weights,
        ))

    def entries(self, plan: Plan, job: Job, deliveries: list, run_index_start: int) -> list[dict]:
        return _cp_manifest_entries_for_slot(deliveries, job.slot_id, job.period.name,
                                             run_index_start, job.seed)

    def received_at(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict) -> str:
        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None:
            # THE SCENARIO'S OWN INSTANT.
            extra = injected[0].arrivals[n - 1]
            return asset_time.isoformat(asset_time.wall_clock(delivery_obj.received_date, extra.at))
        return _cp_received_at(delivery_obj.payload, delivery_obj.received_date,
                               f"received_at for {entry['run_id']}")

    def files(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict, name: str):
        from generator import receipt_instants, scenario_injection

        # ALL SIX TABLES IN ONE DELIVERY, because they arrive together as one
        # extract - six deliveries would be six arrivals that never happened
        # (REQ-GEN-043 criterion 11). Each filename matches its own dataset's
        # configured arrivalPattern.
        csvs = {}
        for table in TABLES:
            df = delivery_obj.payload[table]
            cols = [c for c in df.columns if not c.startswith("_")]
            csvs[f"{table}.csv"] = df[cols].to_csv(index=False)
        period = job.period.name
        if period in plan.state["grown_names"] and period not in plan.state["case_workers_owed"]:
            csvs.pop(f"{hierarchy.dataset(_CASE_WORKERS).table}.csv")
        first = asset_time.parse_instant(entry["received_at"], entry["run_id"])
        injected = plan.injected_by_period.get(period)
        if injected is not None:
            # THE SCENARIO'S OWN FILE SET AND ITS OWN INSTANT. Three of these
            # scenarios ARE a file set - an unreadable table, a duplicate
            # match, a rename nothing claims - so shaping the delivery is the
            # whole injection rather than a detail of it.
            csvs = scenario_injection.apply_file_shape(injected[0].arrivals[n - 1].file_shape, csvs)
            if not isinstance(delivery_obj, PairDelivery):
                return csvs, first
            # A PAIR'S FILES REPLACE THEIR TABLE'S, EACH AT ITS OWN RECEIPT
            # (REQ-GEN-203 criterion 2); the rest share the delivery's instant.
            for f in injected[0].arrivals[n - 1].files:
                csvs.pop(f"{f.table}.csv", None)
            received = {fn: first for fn in csvs}
            for fn, (csv, at) in delivery_obj.files.items():
                csvs[fn] = csv
                received[fn] = asset_time.wall_clock(delivery_obj.received_date, at)
            return csvs, received
        # EACH FILE ITS OWN INSTANT (REQ-GEN-044 criteria 12-14): mostly all
        # at once, as if unzipped, sometimes trickling in over ten minutes.
        return csvs, receipt_instants.instants_for(csvs, first, name)

    def describe(self, entry: dict, delivery_obj) -> str:
        return f"{entry['row_counts']['cp_notifications']:5d} notifications"

    def extra_placements(self, plan: Plan) -> list:
        from generator import scenario_injection

        # TS-79 IN THE SAME WRITE (REQ-GEN-199 criterion 20), over the
        # original fifteen (REQ-GEN-207 criterion 4).
        return scenario_injection.inheritance_placements(plan.state["original"])


PROVIDER = ChildProtection()
