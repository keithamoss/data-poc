"""
Orchestrates multiple daily deliveries of the birth-registrations feed into
data/raw/ - the "generate a few different runs of synthetic data" part of
the brief, sized ~10 scheduled deliveries with most clean and a few
deliberately dirty (the user's chosen default).

Each *delivery* is a separate simulated day's extract (see daily_batch.py
for why this is an event-flow generator, not a resample of a population
snapshot). Deliveries get non-overlapping id_offset blocks so
registration_number/source_system_record_id stay globally unique across
the whole batch - this matters once they're all loaded into one warehouse
for cross-run checks (drift, trend, row-count growth).

RESUPPLY SIMULATION. Keith's team's real practice: a supply whose file
has a RED failing check (never amber - a warning alone doesn't trigger
this) gets a resupply request sent to the supplier, and a corrected (or
sometimes still-broken) resupply arrives some working days later - "no
single fixed resupply rate," by design. So one SLOT - the logical
obligation, one (dataset, period) pair actually expected - can produce
MULTIPLE manifest entries, one per DELIVERY, each its own CSV.

Each entry carries `slot_id`, the `period` the supply is for, and its
own `received_at` instant. It carries NO is_resupply, supersedes_run_id
or attempt_number: those were RETIRED by REQ-GEN-042, not renamed. A
resupply is a delivery landing in a slot that already has one -
observed from the record, never asserted by whatever produced it.

The delay/retry/chaining BEHAVIOUR itself - business-day delay curve,
per-attempt still-red probability, MAX_ATTEMPTS - lives in resupply.py,
generic and knowing nothing about how a dataset's rows are made. This
module only supplies the Birth-Registrations-specific half: a
DatasetProvider wrapping daily_batch.py/dirty.py, plus this dataset's own
churn (small add/modify/remove drift between attempts). See
plans/publishing-and-history.md #2 for why this split exists - the anticipated future
replacement of daily_batch.py (per
docs/synthetic-data-generation-tools-research.md) only has to implement a
new DatasetProvider, not touch the resupply logic at all.

Scope, deliberately: this is a GENERATOR-LAYER change only.
qa_tools/*/*.py, both dashboard builders, and the dashboard UI all still
assume "one manifest entry = one calendar day" and have NOT been updated
to understand attempt chains - that mismatch is intentional (see
plans/data-generation.md #4), left as the concrete input
for designing what the reporting UI actually needs once delivery timing
has no fixed rate, rather than guessed at up front.

The bookkeeping is written in GENERATION order (by slot, then by
delivery within that slot), not in the order things actually arrived -
a resupply for an early slot can easily land after a later slot's own
on-time first delivery. Nothing downstream reads it, and that is the
point: the pipeline recognises arrivals from disk and orders them by
OUR receipt instant (REQ-GEN-043), so the two orders differ on purpose
rather than by accident. Anything that DID read this would have to
sort by received_at itself, which is the first sign it should not be
reading it.
"""
from __future__ import annotations
import json
import os
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from generator.anchor_date import get_anchor_date
from generator.daily_batch import generate_daily_batch
from generator.dirty import apply_birth_registrations_presets, inject_stale_delivery
from generator import delivery_names, scenario_injection
from generator.resupply import MAX_ATTEMPTS, Delivery, DatasetProvider, run_slot_chain
from qa_tools.common import arrivals, asset_time, delivery, hierarchy, schedule

# Which dataset this generator produces - the one literal it needs, so
# it can look its own calendar up rather than carrying a private copy of
# the cadence (REQ-GEN-042).
DATASET_ID = "birth-registrations"


# WHERE THIS GENERATOR WRITES, all of it, redirectable the same way
# (read at call time, never captured into a default arg).
#
# Redirecting one output directory used to isolate a test run. REQ-GEN-043
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

ID_BLOCK = 100_000  # per-delivery id_offset spacing - well above any single delivery's row count

# (day offset from delivery 1, base row count, first-attempt dirty severity or None)
# 30 scheduled deliveries - CUT TO A QUARTER on 2026-09-23 (Keith:
# "let's cut that down to a quarter while we're doing this development
# work, and then we can always punch it back up for a longer history
# later"). A development-speed setting, not a design one: every real
# pipeline run, every committed qa_results/ directory and every git
# walk over that tree scales with this number, and the supply-model
# build ahead regenerates the whole tree twice.
#
# WHY THIS IS SAFE NOW, AND WAS NOT BEFORE. It was 120 because the
# previous 60-delivery window "barely cleared AS_OF_OFFSET_DAYS' own
# 60-day span - the DEFAULT as-of date, today minus 60, landed one day
# before this dataset's own earliest real run, so the flagship real
# dataset showed 'no data' on the default view" (2026-09-16, Keith's
# own call). That constraint is GONE: AS_OF_OFFSET_DAYS was removed
# entirely on 2026-09-17 in favour of per-dataset cadence, and the
# dashboard's defaultInPlaceOn() is now simply today. Since START_DATE is
# anchored so the LAST delivery lands ON the anchor date, the default
# view shows fresh data at any N. Checked in the template rather than
# assumed, after a 2026-09-22 lesson about inferring behaviour from
# config instead of reading the code that consumes it.
#
# To raise it again, change this one number and regenerate - but
# re-read the paragraph above first, because a future as-of default
# that looks backwards would make N load-bearing again.
#
# (Originally deepened from ~10 to 60 deliveries on 2026-09-16 - see
# plans/dashboard.md #5's "deepening simulated history" follow-up, done
# together with widening Child Protection's cadence to quarterly since
# the two were explicitly parked as one piece of work) - same ~60/20/20
# clean/amber/red ratio as
# the original 10-delivery plan (which was itself bumped from a single
# red to 2 so the resupply-chain simulation below had more than one
# independent example to demonstrate variability), generated rather than
# hand-listed at this length. First and last deliveries are always clean
# by construction: the first is orchestrate_bdm.py's own Evidently
# reference run (must be clean to be a meaningful baseline), the last
# being clean is the same deliberate framing choice as the original
# 10-run plan (Keith's own call, 2026-09-13) - Child Protection's own
# RUN_PLAN deliberately ends red instead, see that module's own comment
# for why.
_RUN_PLAN_SEED = 1900  # distinct range from per-delivery seeds (1000+i) and id_offset math
N_DELIVERIES = 30


# The clean/amber/red mix across the scheduled deliveries. Named rather
# than left as magic numbers in the function below because the RED share
# is the main lever on how big this dataset's committed history gets -
# only a red delivery starts a resupply chain, and a chain is several
# more runs (Keith, 2026-09-21, trimming the history toward ~145 runs
# from a measured 176 for one generation).
AMBER_SHARE = 0.2
RED_SHARE = 0.12  # was 0.2


def _build_run_plan(n: int, seed: int) -> list[tuple[int, str | None]]:
    rng = np.random.default_rng(seed)
    n_amber = round(n * AMBER_SHARE)
    n_red = round(n * RED_SHARE)
    n_clean_middle = n - n_amber - n_red - 2  # first/last carved out separately, always clean
    middle = [None] * n_clean_middle + ["amber"] * n_amber + ["red"] * n_red
    rng.shuffle(middle)
    severities = [None] + list(middle) + [None]

    row_counts = rng.integers(1_700, 2_050, size=n)
    # (row count, severity) per scheduled slot. This used to carry a
    # day_offset as well; the calendar supplies the dates now
    # (REQ-GEN-042), so the plan carries only what it actually decides.
    return [(int(row_counts[i]), severities[i]) for i in range(n)]


RUN_PLAN = _build_run_plan(N_DELIVERIES, _RUN_PLAN_SEED)

# Rolling window ending on the anchor date ("today" by default, pinnable
# via GENERATOR_ANCHOR_DATE - see anchor_date.py) rather than a fixed
# calendar date - the fixed 2026-09-01 this used to be drifted further
# from real "now" every day, which is exactly why the Soda [recent] filter
# and the dbt/contract freshness checks on date_of_birth always resolved
# to 0 rows / "no recent data" once enough real time had passed (see
# plans/qa-pipeline.md #3). The last scheduled delivery (day_offset=
# N_DELIVERIES-1) lands ON the anchor date so those checks have real,
# robust margin - most of that delivery's rows have a date_of_birth
# within the freshness checks' 7-day window, not just a coin-flip few
# right on the boundary.
# THE SCHEDULE COMES FROM THE SHARED CONFIG, not from a private copy
# (REQ-GEN-042). contract/data-asset.yaml's `daily` calendar is the same
# one the pipeline judges these supplies against, so the generator
# cannot place a supply against one schedule while the pipeline measures
# it against another - a disagreement that would look like a model
# failure rather than a config duplication.
#
# The window ends ON the anchor so the Soda [recent] filter and the
# dbt/contract freshness checks on date_of_birth have real margin: most
# of the last supply's rows fall inside their 7-day window, rather than
# a coin-flip few right on the boundary (plans/qa-pipeline.md #3).
def _scheduled_dates(n: int) -> list[date]:
    anchor = get_anchor_date()
    periods = schedule.periods_for_dataset(DATASET_ID, until=anchor)
    if len(periods) < n:
        raise ValueError(
            f"the {schedule.calendar_for_dataset(DATASET_ID).name!r} calendar yields only "
            f"{len(periods)} periods up to {anchor}, but {n} supplies are planned")
    return [p.date for p in periods[-n:]]


SCHEDULED_DATES = _scheduled_dates(N_DELIVERIES)
START_DATE = SCHEDULED_DATES[0]


class BirthRegistrationsProvider:
    """The DatasetProvider for Birth Registrations - the only piece of
    this module that knows daily_batch.py/dirty.py's actual function
    signatures. Swapping the underlying generator later (per
    docs/synthetic-data-generation-tools-research.md) means writing a new
    class like this one, not touching resupply.py or the chain-walking
    loop in main() below."""

    def generate(self, run_date: date, seed: int, n_rows: int, id_offset: int) -> pd.DataFrame:
        df = generate_daily_batch(run_date, seed=seed, n_rows=n_rows, id_offset=id_offset)
        # Phase 5f (plans/qa-pipeline.md #61): occasional whole-run
        # staleness, exempting the same two bookend deliveries severity
        # already exempts (see RUN_PLAN's own comment) - the first
        # (orchestrate_bdm.py's Evidently reference run, must be a clean
        # baseline) and the last (deliberately fresh so the "current"
        # view reads healthy by default, same reason START_DATE's own
        # rolling window exists). A distinct seed offset (+50) from
        # daily_batch.py's own internal +1/+2 draws, so this coin flip
        # never correlates with the row content it's applied on top of.
        is_bookend = run_date in (START_DATE, START_DATE + timedelta(days=N_DELIVERIES - 1))
        if not is_bookend:
            df = inject_stale_delivery(df, seed=seed + 50)
        return df

    def dirty(self, df: pd.DataFrame, severity: str, seed: int,
              previous_row_count: Optional[int]) -> pd.DataFrame:
        return apply_birth_registrations_presets(df, severity=severity, seed=seed,
                                                  previous_row_count=previous_row_count)

    def resupply_subset(self, df: pd.DataFrame, previous_dirty_seed: int, seed: int) -> pd.DataFrame:
        """A Birth Registrations supply is ONE FILE, so there is no
        such thing as resending part of it (REQ-GEN-040).

        Implemented rather than left off, because the honest answer to
        "can this dataset deliver one table at a time" is no, and a
        dataset that says so is different from one nobody asked. The
        partial shape belongs to a collection of several tables, which
        is what Child Protection is and this is not.
        """
        return df

    def churn(self, df: pd.DataFrame, seed: int, run_date: date, id_offset: int,
              add_rate: float = 0.02, modify_rate: float = 0.02, remove_rate: float = 0.01) -> pd.DataFrame:
        """Between one attempt and the next, the source system hasn't been
        frozen - deliberately secondary, small-rate churn on top of
        whatever dirty() does: a few more registrations have since been
        recorded (id_offset is a dedicated, unused sub-block of this
        delivery's own reserved ID range, so no collision with the
        original attempt's IDs), a few existing ones have been corrected
        by BDM staff (nudged extract_timestamp - the one field every row
        has that can shift without touching anything a QA check keys
        off), and a few have been voided. Keith's own framing: "largely
        the same rows... but also probably new rows that have been added
        or that had been changed or deleted since the first supply" - the
        resupply is not a fresh random draw of that day's data."""
        rng = np.random.default_rng(seed)
        out = df.copy()

        remove_mask = rng.random(len(out)) < remove_rate
        out = out.loc[~remove_mask].reset_index(drop=True)

        modify_mask = rng.random(len(out)) < modify_rate
        modify_idx = np.where(modify_mask)[0]
        if len(modify_idx):
            shift = pd.to_timedelta(rng.integers(1, 6, size=len(modify_idx)), unit="h")
            out.loc[out.index[modify_idx], "extract_timestamp"] = (
                pd.to_datetime(out.loc[out.index[modify_idx], "extract_timestamp"]) + shift
            )

        n_add = int(round(len(out) * add_rate))
        if n_add:
            # date_registered = the delivery's own date (not this attempt's
            # arrival date) - these are records that should have been in the
            # original file but were missing from it, not new same-day
            # registrations that happen to have landed in the wrong file.
            extra = generate_daily_batch(run_date, seed=seed + 1, n_rows=n_add, id_offset=id_offset)
            out = pd.concat([out, extra], ignore_index=True)

        return out



def _received_at(payload, received_date: date, where: str) -> str:
    """This delivery's own receipt instant.

    THE DATE COMES FROM THE CHAIN, THE TIME OF DAY FROM THE DATA, and
    both halves are deliberate.

    The date has to be the chain's, because a resupply lands days after
    the slot it fills - that is the whole point of the two axes the
    supply model insists on, and taking the date from the payload would
    have collapsed them back together. Measured while building this:
    reading it off the payload alone gave all four deliveries in one
    slot the SAME receipt instant, days apart in reality.

    The time of day comes from the data because the arrival calibration
    already lives there (generator/daily_batch.py draws one
    characteristic offset per batch), so a separately invented time
    would be a second, drifting model of the same thing.

    Rows whose extract_timestamp precedes their own date_registered are
    excluded - those are `generator/dirty.py`'s deliberately disordered
    rows, planted for the "extract timestamp ordering" check to catch.
    Including them would let one corrupted row decide when the whole
    supply arrived, which is the exact bug
    qa_tools/bdm/dataset_stats.py's own earliest_extract already
    documents and filters against.
    """
    legitimate = payload["extract_timestamp"] >= pd.to_datetime(payload["date_registered"])
    stamps = payload.loc[legitimate, "extract_timestamp"]
    if stamps.empty:  # every row disordered - defensive, unreachable today
        stamps = payload["extract_timestamp"]
    earliest = pd.Timestamp(stamps.min()).to_pydatetime()
    return asset_time.record_source_instant(
        datetime.combine(received_date, earliest.time()), where)

def _manifest_entries_for_slot(deliveries: list, slot_id: str, period: str,
                                run_index_start: int, id_offset: int, seed: int) -> list[dict]:
    """Pure manifest-entry construction for the deliveries filling ONE
    SLOT - no file I/O, so this is independently testable
    (tests/test_resupply.py) without main()'s CSV writes or a real
    provider. main() calls this directly and only adds the file-writing
    side effect on top, so the two cannot drift apart.

    `run_index_start` is the manifest's own running length BEFORE this
    slot's entries, so entries are 1-indexed from there.

    THE RUN ID CARRIES NO DATE (REQ-GEN-042). It used to be
    `run_007_2026-09-14_resupply1`, which meant a regeneration on a
    different calendar day wrote a whole second history ALONGSIDE the
    first instead of replacing it - measured at the time: 352 committed
    run directories that were really 176 runs, each present twice under
    dates one day apart. A dateless id derived from the manifest
    position is deterministic given configuration and seed, so
    regenerating overwrites in place.

    Nor does it carry a resupply marker any more. Which arrival is a
    resupply is OBSERVED - a delivery landing in a slot that already has
    one - not asserted by the thing that produced it.
    """
    entries = []
    for delivery_obj in deliveries:
        # :03d, and the padding must stay WIDE ENOUGH for every id to
        # sort correctly as a plain string: a real bug caught by
        # test_severity_counts_match_run_plan when this was :02d
        # ("run_100" < "run_11" lexicographically). These ids are
        # string-sorted for real downstream, by
        # qa_tools/common/qa_results_reader.py's list_run_ids(), which
        # reads the committed qa_results/ tree's own directory names.
        run_index = run_index_start + len(entries) + 1
        run_id = f"run_{run_index:03d}"
        entries.append({
            "run_id": run_id,
            "run_index": run_index,
            # The logical obligation this arrival fills. One slot, many
            # deliveries - which is why this is not called delivery_id
            # any more.
            "slot_id": slot_id,
            # The two axes the supply model insists are different: which
            # period a supply is FOR, and when it actually turned up.
            # A single delivery_date conflated them.
            "period": period,
            "received_at": None,  # filled in by main() from the payload's own earliest extract
            "n_rows_generated": int(len(delivery_obj.payload)),
            "dirty_severity": delivery_obj.severity,  # None | "amber" | "red" - this ARRIVAL's own outcome
            "id_offset": id_offset,
            "seed": seed,
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

def _injected_chain(provider: DatasetProvider, injection, period, seed: int,
                    id_offset: int, n_rows: int, previous_row_count):
    """The arrivals ONE injected scenario needs, in place of the ordinary
    chain (REQ-GEN-044 criteria 1 and 6).

    THE SCENARIO SAYS HOW MANY ARRIVALS AND WHAT EACH ONE IS, where
    `run_slot_chain()` decides both from a random draw. That is the whole
    difference: an injected scenario is a shape somebody specified, and a
    chain that sometimes produced it would demonstrate nothing on the run
    where it did not.

    SHAPES, NOT VERDICTS (criterion 6). `severity` here is what the
    GENERATOR injects into the rows - the same lever the ordinary chain
    pulls - so the QA tools still decide whether a supply is red. It is
    not a recorded verdict and nothing downstream reads it as one.

    Each arrival after the first is CHURNED from the one before, exactly
    as a real resupply is: the source system was not frozen between
    them, and a fresh random draw would make the third file unrelated to
    the first two, which is not what a resupply is.
    """
    deliveries = []
    payload = provider.generate(period.date, seed=seed, n_rows=n_rows, id_offset=id_offset)
    for n, extra in enumerate(injection.arrivals):
        if n:
            payload = provider.churn(payload, seed=seed + 900 + n, run_date=period.date,
                                      id_offset=id_offset + (n + 1) * (ID_BLOCK // 10))
        this = payload
        if extra.severity:
            this = provider.dirty(payload, severity=extra.severity, seed=seed + 800 + n,
                                   previous_row_count=previous_row_count)
        deliveries.append(Delivery(
            received_date=period.date + timedelta(days=extra.day_offset),
            severity=extra.severity, payload=this))
    return deliveries


def _away_from_suppressed(deliveries, suppressed: set[str], taken_days: set[str]):
    """Move any arrival that would land on a day the supplier is down.

    THE SCENARIO SAYS THE SUPPLIER IS DOWN, not that one particular
    period went unfilled - so nothing from them arrives those days,
    including a RESUPPLY of some earlier period whose delay happened to
    land there. Suppressing the period's own chain and leaving the
    resupply is the half-measure that made TS-2 demonstrate something
    else on the first real run: two days meant to be empty, one of them
    carrying run_032.

    Shifted forward rather than dropped, because a resupply that never
    arrives at all is a different scenario again - the supplier came
    back and sent it late, which is what an outage actually produces.

    AND ON A WEEKDAY, which `run_slot_chain()` already guarantees for
    every resupply it schedules and this was quietly undoing - it pushed
    one off a Thursday/Friday outage straight onto the Saturday.
    `tests/test_generate_runs.py`'s own weekday invariant caught it.

    THE BACKLOG ARRIVES IN SEQUENCE, ONE DAY EACH, and that is not
    flavour - it is a correctness fix found by the pipeline refusing to
    run. Two resupplies shifted off a two-day outage both landed on the
    first day back, and a receipt instant is the payload's own earliest
    extract, which churn leaves unchanged - so both got the SAME instant,
    both got the same physical staged table name, and loading the second
    dropped the first. The run then failed with
    `relation "qa_run_032.birth_registrations" does not exist`, which
    names nothing about the real cause. `taken_days` is shared across
    slots because the collision is between them.
    """
    if not suppressed:
        return deliveries
    out = []
    for item in deliveries:
        when = item.received_date
        moved = False
        while (when.isoformat() in suppressed
               or (moved and (when.isoformat() in taken_days or when.weekday() >= 5))):
            when += timedelta(days=1)
            moved = True
        if moved:
            taken_days.add(when.isoformat())
        out.append(item if when == item.received_date
                   else Delivery(received_date=when, severity=item.severity,
                                  payload=item.payload))
    return out


def _no_two_arrivals_share_an_instant(manifest: list[dict]) -> None:
    """Refuse a history where two supplies claim one receipt instant.

    A STAGED TABLE IS NAMED FOR ITS ARRIVAL, so two supplies at the same
    instant claim one physical table and loading the second DROPs the
    first - the failure this guard exists for was real, and what it
    reported was a missing relation several steps downstream rather than
    anything about a duplicate instant. Loud here, where the cause is
    still visible.
    """
    seen: dict[str, str] = {}
    for entry in manifest:
        instant = entry.get("received_at")
        if instant in seen:
            raise ValueError(
                f"{entry['run_id']} and {seen[instant]} both claim receipt instant "
                f"{instant}. A staged table is named for its arrival, so these two "
                f"would claim one table and the second would drop the first.")
        seen[instant] = entry["run_id"]


def _plan_injections(periods):
    """Where every Birth Registrations scenario lands, resolved BEFORE
    anything is written (REQ-GEN-044 criterion 4).

    All of it up front, deliberately: a scenario that cannot be placed
    must stop the generator rather than be discovered halfway through,
    because a half-written history is one somebody has to notice is
    half-written.
    """
    mine = scenario_injection.for_dataset(DATASET_ID)
    scenario_injection.no_two_scenarios_share_a_period(mine, {DATASET_ID: periods})
    resolved = [(injection, scenario_injection.resolve(injection, periods))
                for injection in mine]
    by_period = {placement.period: (injection, placement)
                 for injection, placement in resolved}
    suppressed = {name for _, placement in resolved for name in placement.suppressed}
    return resolved, by_period, suppressed


def main() -> None:
    provider: DatasetProvider = BirthRegistrationsProvider()
    manifest = []
    # Delivery names are arbitrary BY DESIGN, which means they can
    # collide - and a collision would write two arrivals into one
    # directory, silently merging deliveries that never arrived
    # together. Uniqueness is enforced rather than hoped for.
    # Clear what THIS generator wrote last time, so a regeneration
    # overwrites its own history rather than accumulating beside it
    # (REQ-GEN-042), then seed uniqueness from whatever the OTHER
    # generator has on disk so two arrivals can never share a
    # directory (REQ-GEN-043).
    delivery.remove_deliveries(_previous_delivery_names(), DELIVERIES_DIR, RECEIPTS_DIR)
    taken_names: set[str] = delivery.existing_delivery_names(DELIVERIES_DIR)
    previous_row_count = None  # the last RESOLVED delivery's row count, for
    # the row-count-growth check's dirty preset - deliberately NOT updated
    # mid-chain: a viewer comparing "is this delivery's row count
    # reasonable" would check against the last good reference point, not
    # against an already-failed attempt of the same delivery.

    periods = schedule.periods_for_dataset(DATASET_ID, until=get_anchor_date())[-N_DELIVERIES:]

    # BEFORE THE FIRST WRITE (REQ-GEN-044 criterion 4) - see
    # _plan_injections()'s own docstring.
    resolved_injections, injected_by_period, suppressed_periods = _plan_injections(periods)
    #: Days a shifted arrival has already claimed - see
    #: _away_from_suppressed(). Shared across slots, because the
    #: collision it prevents is between them.
    shifted_onto: set[str] = set()

    for i, ((n_rows, severity), period) in enumerate(zip(RUN_PLAN, periods), start=1):
        slot_id = f"slot_{i:03d}"
        slot_date = period.date
        seed = 1000 + i
        id_offset = i * ID_BLOCK

        # A SCENARIO MAY NEED A DAY TO CARRY NO SUPPLY AT ALL, which is
        # an arrival shape like any other - TS-2's supplier outage is
        # two of them - and the only way to express it is not to write
        # one. The slot is still owed; nothing fills it.
        if period.name in suppressed_periods:
            print(f"{period.name}: no supply at all (an injected scenario needs this "
                  f"day empty)")
            continue

        injected = injected_by_period.get(period.name)
        if injected is not None:
            deliveries = _injected_chain(provider, injected[0], period, seed,
                                          id_offset, n_rows, previous_row_count)
        else:
            deliveries = _away_from_suppressed(
                list(run_slot_chain(provider, slot_date, seed, id_offset,
                                     n_rows, severity, previous_row_count)),
                suppressed_periods, shifted_onto)
        entries = _manifest_entries_for_slot(deliveries, slot_id, period.name,
                                              len(manifest), id_offset, seed)

        for n, (delivery_obj, entry) in enumerate(zip(deliveries, entries), start=1):
            # ONE WRITE, NOT TWO (REQ-PIPE-102, extended to Birth
            # Registrations 2026-09-27 at Keith's ask). This used to
            # write a flat `data/raw/<run_id>.csv` here AND a real
            # delivery below - the same rows twice, able to disagree.
            # Only the delivery is an arrival: the whole QA chain
            # reads deliveries, and the flat copy had no reader left.
            # data/raw/ WENT TOO, later the same day: the
            # `--local-file` path stages the operator's file where it
            # already is, so nothing needed a drop directory.
            # THE RECEIPT INSTANT IS THE DATA'S OWN, not a separately
            # invented one: the earliest extract_timestamp in the file
            # that just landed. That is the same value
            # qa_tools/bdm/dataset_stats.py computes downstream as
            # earliest_extract, so the manifest and the warehouse cannot
            # disagree about when a supply turned up.
            if injected is not None:
                # THE SCENARIO'S OWN INSTANT, not the payload's earliest
                # extract. The whole of TS-1 is that the third file lands
                # at 20:00 rather than whenever the rows happen to say -
                # an arrival time derived from the data would put it
                # wherever the generator's row timestamps fell, which is
                # the one thing this scenario is not free to vary.
                extra = injected[0].arrivals[n - 1]
                entry["received_at"] = asset_time.isoformat(
                    asset_time.wall_clock(delivery_obj.received_date, extra.at))
                injected[1].arrivals[n - 1]["delivery"] = None  # set below, with the name
            else:
                entry["received_at"] = _received_at(
                    delivery_obj.payload, delivery_obj.received_date,
                    f"received_at for {entry['run_id']}")

            # AND AS A REAL DELIVERY (REQ-GEN-043): one directory, an
            # arbitrary supplier-shaped name, a filename matching this
            # dataset's own configured arrivalPattern, and a receipt
            # record written OUTSIDE it. See docs/delivery-format.md.
            name = delivery_names.delivery_name(slot_date, seed, attempt=n, taken=taken_names)
            taken_names.add(name)
            entry["delivery"] = name
            if injected is not None:
                # THE DELIVERY NAME, NOT THE GENERATOR'S OWN RUN ID, and
                # this is a correction worth keeping. The first version
                # recorded `entry["run_id"]` and was wrong on the first
                # real run: run identity comes from RECEIPT ORDER over
                # recognised deliveries (REQ-GEN-043), not from this
                # manifest's numbering, and suppressing two days made the
                # two disagree by exactly the two slots removed. The
                # placement said run_036 and the real supply was run_034.
                # A name is stable under both, and the run ids are
                # resolved from recognition below - observed rather than
                # predicted.
                injected[1].arrivals[n - 1]["delivery"] = name
            delivery.write_delivery(
                name,
                {f"birth_registrations_{delivery_obj.received_date.isoformat()}.csv":
                    delivery_obj.payload.to_csv(index=False)},
                received_at=asset_time.parse_instant(entry["received_at"], entry["run_id"]),
                deliveries_dir=DELIVERIES_DIR, receipts_dir=RECEIPTS_DIR,
                # STORAGE, because in this PoC the generator IS storage
                # (REQ-PIPE-105 criterion 4). It is standing in for the
                # moment our own object store took a supplier's file, the
                # same way its CSVs stand in for the supplier's extract -
                # so the receipt says what it is simulating rather than
                # claiming our clock stamped a 2023 instant this morning.
                received_from=delivery.RECEIVED_FROM_STORAGE)

            tag = f"DIRTY({delivery_obj.severity})" if delivery_obj.severity else "clean"
            resupply_tag = (f"  [resupply {n - 1}, received "
                             f"{delivery_obj.received_date.isoformat()}]") if n > 1 else ""
            print(f"{entry['run_id']}: {len(delivery_obj.payload):5d} rows  [{tag}]{resupply_tag}"
                  f"  -> {name}/")
            if delivery_obj.severity == "red" and n >= MAX_ATTEMPTS:
                print(f"  -> still red after {n} deliveries - "
                      f"giving up (hit MAX_ATTEMPTS={MAX_ATTEMPTS})")

        manifest.extend(entries)
        previous_row_count = len(deliveries[-1].payload)  # this slot's final (resolved-or-abandoned) row count

    # NO manifest.json ANY MORE (REQ-GEN-043). It held exactly the
    # list below, which _write_bookkeeping() also holds - two copies of
    # the same bookkeeping, in two files, able to disagree. Nothing in
    # the pipeline had read it since arrivals became recognised rather
    # than declared, so the only thing it could still do was tempt
    # somebody to wire it back up.
    _no_two_arrivals_share_an_instant(manifest)
    _write_bookkeeping(manifest)
    # WHERE EVERY SCENARIO LANDED (criterion 7), written once the run
    # ids exist - qa_tools/common/scenario_map.py reads exactly this.
    if resolved_injections:
        placed = [placement for _, placement in resolved_injections]
        recognised = arrivals.arrivals_for(
            hierarchy.dataset(DATASET_ID).collection_id, "run_",
            DELIVERIES_DIR, RECEIPTS_DIR)
        # AGAINST WHAT RECOGNITION FOUND, not against what was meant to
        # be written - see each function's own docstring.
        scenario_injection.check_suppressed_days_are_empty(placed, recognised)
        scenario_injection.resolve_run_ids(placed, recognised)
        written = scenario_injection.write_placements(placed, merge=True)
        print(f"Recorded {len(resolved_injections)} injected scenario placement(s) "
              f"-> {written}")
    n_red_chains = sum(1 for _, sev in RUN_PLAN if sev == "red")
    print(f"\nWrote {len(manifest)} deliveries across {len(RUN_PLAN)} scheduled slots "
          f"({n_red_chains} of which went red and triggered a resupply chain) "
          f"to {os.path.abspath(DELIVERIES_DIR)}")


if __name__ == "__main__":
    main()
