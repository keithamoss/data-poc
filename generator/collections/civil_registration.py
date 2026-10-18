"""Civil Registration's generator provider (REQ-GEN-246): Birth
Registrations' rows, seed schedule and period plan. The slot loop, the
bookkeeping, delivery and receipt writing and injection placement are the
shared driver's (generator/driver.py); this module was
generator/generate_runs.py, and everything below that is not the driver's
moved here unchanged, so the generated history is byte-identical.

IMPORTABLE WITHOUT pandas OR numpy (criterion 7): every tool import is
deferred to the function that needs it, so reading PROVIDER's declarations
costs nothing. RUN_PLAN, SCHEDULED_DATES and START_DATE are computed on
first use for the same reason.

Orchestrates multiple daily deliveries of the birth-registrations feed -
the "generate a few different runs of synthetic data" part of the brief,
sized ~10 scheduled deliveries with most clean and a few deliberately dirty
(the user's chosen default).

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
import functools
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional

from generator.anchor_date import get_anchor_date
from generator.collections.base import Job, Plan, Provider
from qa_tools.common import asset_time, schedule

if TYPE_CHECKING:  # annotations only - never imported at module level
    import pandas as pd
    from generator.resupply import DatasetProvider

# Which dataset this generator produces - the one literal it needs, so
# it can look its own calendar up rather than carrying a private copy of
# the cadence (REQ-GEN-042).
DATASET_ID = "birth-registrations"


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
# by construction: the first is the orchestrator's own Evidently
# reference run (must be clean to be a meaningful baseline), the last
# being clean is the same deliberate framing choice as the original
# 10-run plan (Keith's own call, 2026-09-13) - Child Protection's own
# RUN_PLAN deliberately ends red instead, see that module's own comment
# for why.
_RUN_PLAN_SEED = 1900  # distinct range from per-delivery seeds (1000+i) and id_offset math
# 40, NOT 30 (Keith, 2026-10-11, REQ-GEN-185): planting TS-43 to TS-46 with
# their lead-ins and following days claims nearly every day from 2026-09-03
# to the anchor, and the ordinary reds' resends need ordinary days to land
# on. The extra ten are August days, before every scenario.
# 80, NOT 40 (Keith, 2026-10-13, REQ-GEN-196 criterion 20): seven
# contested-pair scenarios (TS-68 to TS-74), TS-78's six days and every
# existing scenario, with every ordinary red and amber still drawn. The
# extra forty are added at the OLD end (from 2026-07-05), so every existing
# negative anchor keeps its calendar date.
# 85, NOT 80 (Keith, 2026-10-13, post-build-review #172): the pairs sit apart
# with ordinary days between them, which left the ordinary reds no room to
# sit apart themselves - five more days, from 2026-06-30, so no two reds fall
# on neighbouring days.
N_DELIVERIES = 85

# THE EVENING-BEFORE ERA (REQ-GEN-044; Keith, 2026-10-15): twelve more days
# at the OLD end, in which a day's supply is due at 22:00 the evening before
# (contract/calendar.yaml's 2026-06-18 versions), so TS-3c, TS-3d and TS-10
# sit in the configuration that makes their outcomes right. GENERATED AFTER
# the 85 with seeds of their own, exactly as REQ-GEN-207 grew Child
# Protection: every existing delivery keeps its bytes, slot id and seed, and
# the 85's own severity plan is drawn over the 85 alone. The era carries no
# ordinary reds or ambers - its days are the scenarios' and the plain
# on-time supplies between them, and a red's resends would land on a
# scenario's day (PROVISIONAL, for Keith to sense-check).
GROWN_DAYS = 12
GROWN_BASE_SEED = 40000


# The clean/amber/red mix across the scheduled deliveries. Named rather
# than left as magic numbers in the function below because the RED share
# is the main lever on how big this dataset's committed history gets -
# only a red delivery starts a resupply chain, and a chain is several
# more runs (Keith, 2026-09-21, trimming the history toward ~145 runs
# from a measured 176 for one generation).
AMBER_SHARE = 0.2
RED_SHARE = 0.12  # was 0.2


def _build_run_plan(n: int, seed: int) -> list[tuple[int, str | None]]:
    import numpy as np

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


@functools.cache
def run_plan() -> list[tuple[int, str | None]]:
    """RUN_PLAN, drawn on first use (criterion 7)."""
    return _build_run_plan(N_DELIVERIES, _RUN_PLAN_SEED)

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


def start_date() -> date:
    """START_DATE: the first of the 85 scheduled dates, read at call time."""
    return _scheduled_dates(N_DELIVERIES)[0]


def __getattr__(name: str):
    """RUN_PLAN, SCHEDULED_DATES and START_DATE as module attributes,
    computed when first asked for rather than at import (criterion 7)."""
    if name == "RUN_PLAN":
        return run_plan()
    if name == "SCHEDULED_DATES":
        return _scheduled_dates(N_DELIVERIES)
    if name == "START_DATE":
        return start_date()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def _ordinary_severities(periods, injected_by_period, suppressed) -> list:
    """GENUINELY AMBER (REQ-GEN-184; Keith, 2026-10-11): each drawn severity,
    with every ordinary amber that cannot be generated where it was drawn -
    in a `hold` amber-setting era, or on a period an injected scenario owns
    or empties - moved to a clean period that can take it, so the number
    GENERATED equals the number drawn (criterion 9). Planned here, against
    the injections, rather than at import: moved blind, three of six were
    generated (post-build-review #154). Reds as drawn, except one a scenario
    needs the period of, which moves before the scenarios (criterion 10, as
    amended 2026-10-11); cleans as drawn; the bookends stay clean."""

    from generator import targeting

    green = _built_green(injected_by_period)
    unavailable = frozenset(i for i, p in enumerate(periods)
                            if p.name in injected_by_period or p.name in suppressed
                            or p.name in green)
    try:
        drawn = _reds_clear_of_scenarios([s for _n, s in run_plan()[:len(periods)]],
                                         unavailable, names=[p.name for p in periods])
        out = targeting.outside_hold(drawn, [p.date for p in periods], DATASET_ID,
                                     keep_clean=frozenset({0, len(periods) - 1}),
                                     unavailable=unavailable)
    except targeting.TargetError as exc:
        # NAMING THE SCENARIOS WHOSE CLAIMS LEFT NO ROOM (REQ-GEN-196
        # criterion 21), and what to do - never dropping one to fit.
        claimants = sorted({inj.scenario_id for inj, _p in injected_by_period.values()},
                           key=lambda sid: (len(sid), sid))
        raise targeting.TargetError(
            f"{str(exc).removesuffix(' - lengthen the history')} - the periods are claimed "
            f"by {', '.join(claimants)}: lengthen the history or move an anchor") from exc
    # A LEAD-IN OR FOLLOWING PERIOD IS GREEN (REQ-GEN-185). Belt and braces:
    # the red and amber drawn there have already been MOVED, not dropped,
    # since both treat it as unavailable.
    return [None if p.name in green else sev for p, sev in zip(periods, out)]


#: How many periods before the first scenario-claimed one an ordinary red
#: may not sit in: its resends need ordinary days to land on, and resend
#: delays are mostly one to three days (generator/resupply.py).
RED_CLEARANCE = 3


def _reds_clear_of_scenarios(severities: list, unavailable: frozenset[int],
                             names: Optional[list] = None) -> list:
    """Every ordinary red moved before the stretch the scenarios claim
    (REQ-GEN-185; Keith, 2026-10-11, lengthening the history to make room):
    a red's resends land on the next free weekdays, and inside that stretch
    there are none - on the first planted rebuild they landed on TS-2's,
    TS-1's, TS-45's and TS-46's days and ruined TS-45. Each moves to the
    latest clean period before the stretch, so the count is unchanged and
    the history stays a daily feed with its reds in it."""
    from generator import targeting

    if not unavailable:
        return list(severities)
    start = max(1, min(unavailable) - RED_CLEARANCE)
    out = list(severities)
    for i in range(start, len(out)):
        if out[i] != "red":
            continue
        # SPREAD, NOT PACKED (post-build-review #172): a red beside another
        # red has its resends land on that red's day - or on the same
        # instant as its neighbour's, which the generator refuses. A slot
        # with no red either side first; any clean slot only when none is.
        free = [j for j in range(start - 1, 0, -1) if out[j] is None]
        swap = next((j for j in free if "red" not in (out[j - 1], out[j + 1] if j + 1 < len(out) else None)),
                    free[0] if free else None)
        if swap is None:
            raise targeting.TargetError(
                f"{DATASET_ID}: the ordinary red drawn for {names[i] if names else i} falls among the "
                f"scenarios and no clean period before them is left to take it - "
                f"lengthen the history")
        out[i], out[swap] = None, "red"
    return out


def _built_green(injected_by_period) -> frozenset[str]:
    """Every period a targeted scenario needs generated green - its lead-in
    and the period after it (REQ-GEN-185 criteria 1 and 3)."""
    return frozenset(name for _inj, placement in injected_by_period.values()
                     for name in placement.built_green)


class BirthRegistrationsProvider:
    """The DatasetProvider for Birth Registrations - the only piece of
    this module that knows daily_batch.py/dirty.py's actual function
    signatures. Swapping the underlying generator later (per
    docs/synthetic-data-generation-tools-research.md) means writing a new
    class like this one, not touching resupply.py or the chain-walking
    loop in main() below."""

    def __init__(self, amber_dates: frozenset[date] = frozenset()):
        #: An ordinary amber is never also made stale: a stale delivery
        #: fails the freshness checks, which would make it red
        #: (REQ-GEN-184 criterion 4). main() sets it once ambers are planned.
        self.amber_dates = amber_dates

    def generate(self, run_date: date, seed: int, n_rows: int, id_offset: int) -> pd.DataFrame:
        from generator.daily_batch import generate_daily_batch
        from generator.dirty import inject_stale_delivery

        df = generate_daily_batch(run_date, seed=seed, n_rows=n_rows, id_offset=id_offset)
        # Phase 5f (plans/qa-pipeline.md #61): occasional whole-run
        # staleness, exempting the same two bookend deliveries severity
        # already exempts (see RUN_PLAN's own comment) - the first
        # (the orchestrator's Evidently reference run, must be a clean
        # baseline) and the last (deliberately fresh so the "current"
        # view reads healthy by default, same reason START_DATE's own
        # rolling window exists). A distinct seed offset (+50) from
        # daily_batch.py's own internal +1/+2 draws, so this coin flip
        # never correlates with the row content it's applied on top of.
        first = start_date()
        is_bookend = run_date in (first, first + timedelta(days=N_DELIVERIES - 1))
        if not is_bookend and run_date not in self.amber_dates:
            df = inject_stale_delivery(df, seed=seed + 50)
        return df

    def dirty(self, df: pd.DataFrame, severity: str, seed: int,
              previous_row_count: Optional[int]) -> pd.DataFrame:
        # AMBER BY CONSTRUCTION (REQ-GEN-184 criterion 6), never the preset,
        # which trips single-tier checks and reads red. Red keeps the preset
        # (criterion 10).
        from generator import targeting
        from generator.dirty import apply_birth_registrations_presets

        if severity == "amber":
            return targeting.bdm_amber(df, seed=seed, rows=previous_row_count)
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
        import numpy as np
        import pandas as pd

        from generator.daily_batch import generate_daily_batch

        rng = np.random.default_rng(seed)
        out = df.copy()

        # VOIDED REGISTRATIONS ARE SINGLE BIRTHS (Keith, 2026-10-11,
        # plans/running-thoughts.md #82): voiding one twin left its sibling
        # unmatched, and a resend drawn clean failed the three sibling
        # checks about four times in ten. The draw is unchanged, so the
        # same rows are voided as before wherever none was a twin.
        remove_mask = (rng.random(len(out)) < remove_rate) & \
            ~out["is_multiple_birth"].astype(bool).to_numpy()
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
    qa_tools/tools/dataset_stats.py's own earliest_extract already
    documents and filters against.
    """
    import pandas as pd

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



def _injected_chain(provider: DatasetProvider, injection, period, seed: int,
                    id_offset: int, n_rows: int, previous_row_count, placement=None):
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
    from generator import targeting
    from generator.resupply import Delivery

    deliveries = []
    payload = provider.generate(period.date, seed=seed, n_rows=n_rows, id_offset=id_offset)
    for n, extra in enumerate(injection.arrivals):
        if n and 0 < extra.day_offset <= injection.covers \
                and extra.day_offset != injection.arrivals[n - 1].day_offset:
            # A COVERED DAY'S OWN SUPPLY (REQ-GEN-199): that day's extract, with
            # the id block its own slot would have had - not a resend of D's.
            day = period.date + timedelta(days=extra.day_offset)
            payload = provider.generate(day, seed=seed + 50 * extra.day_offset,
                                        n_rows=n_rows,
                                        id_offset=id_offset + extra.day_offset * ID_BLOCK)
        elif n:
            payload = provider.churn(payload, seed=seed + 900 + n, run_date=period.date,
                                      id_offset=id_offset + (n + 1) * (ID_BLOCK // 10))
        if extra.files:
            deliveries.append(_pair_delivery(provider, injection, extra, n, payload, period,
                                             seed, id_offset, n_rows, previous_row_count,
                                             placement))
            continue
        this = payload
        if extra.target is not None:
            # BUILT TO A TARGET, NEVER THE PRESET (REQ-GEN-184 criterion 1),
            # the size of the supply before it (criterion 4), and what was
            # moved recorded on the placement for the scenario map
            # (criterion 12).

            this, moved = targeting.bdm_target(
                payload, extra.target, seed=seed + 800 + n,
                where=f"{injection.scenario_id}, its {extra.at} arrival",
                rows=previous_row_count)
            if placement is not None:
                placement.arrivals[n]["target"]["moved"] = moved
        elif extra.severity:
            this = provider.dirty(payload, severity=extra.severity, seed=seed + 800 + n,
                                   previous_row_count=previous_row_count)
        deliveries.append(Delivery(
            received_date=period.date + timedelta(days=extra.day_offset),
            severity=extra.severity, payload=this))
    return deliveries


@dataclass
class PairDelivery:
    """ONE DELIVERY CARRYING TWO FILES for one table (REQ-GEN-196), each with
    its own bytes and receipt. `payload` is the supply-shaped file, which
    sizes the day after - never a stray test file (the requirement's NFR)."""

    received_date: date
    severity: str | None
    payload: pd.DataFrame
    #: filename -> (CSV text, wall-clock receipt on received_date)
    files: dict


def _pair_delivery(provider, injection, extra, n: int, base, period, seed: int,
                   id_offset: int, n_rows: int, previous_row_count, placement):
    """A pair's two files, built as the injection says (REQ-GEN-196): each
    file's content, then its target or severity, then its named shape. A
    SHAPE, NEVER A VERDICT - the pipeline decides what each file reads as."""
    from generator import scenario_injection, targeting

    day = period.date + timedelta(days=extra.day_offset)
    where = f"{injection.scenario_id}, its {extra.at} delivery"
    files: dict[str, tuple[str, str]] = {}
    supply_shaped = None
    previous_csv = None
    for k, f in enumerate(extra.files):
        if f.content == "duplicate":
            if previous_csv is None:
                raise scenario_injection.CannotPlace(
                    f"{where}: file {k + 1} is a duplicate of nothing - a duplicate "
                    f"follows the file it copies")
            csv = previous_csv
        else:
            if f.content == "next_day":
                df = provider.generate(day + timedelta(days=1), seed=seed + 60 + k,
                                       n_rows=n_rows,
                                       id_offset=id_offset + (k + 5) * (ID_BLOCK // 10))
            else:  # extract, corrected - the day's own extract, as built
                df = base.copy()
            if f.target is not None:
                df, moved = targeting.bdm_target(
                    df, f.target, seed=seed + 810 + k, where=f"{where}, file {k + 1}",
                    rows=previous_row_count)
                if placement is not None:
                    placement.arrivals[n]["files"][k]["target"]["moved"] = moved
            elif f.severity:
                df = provider.dirty(df, severity=f.severity, seed=seed + 820 + k,
                                    previous_row_count=previous_row_count)
            # THE PAYLOAD IS A CLEAN FILE: it sizes the next green day, so a
            # file with a planted fault - a third of its rows gone - never is.
            if supply_shaped is None and not f.shapes and not f.severity:
                supply_shaped = df
            csv = df.to_csv(index=False)
            for shape in f.shapes:
                csv = scenario_injection.shape_file(shape, csv)
        files[f.filename(day)] = (csv, f.at)
        previous_csv = csv
    return PairDelivery(received_date=day, severity=extra.severity,
                        payload=supply_shaped if supply_shaped is not None else base,
                        files=files)


def _away_from_suppressed(deliveries, suppressed: set[str], taken_days: set[str],
                          last_day: date | None = None):
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
    from generator import scenario_injection
    from generator.resupply import Delivery

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
        if moved and last_day is not None and when > last_day:
            # PAST THE END OF THE HISTORY is not a place to put a resupply
            # quietly (REQ-GEN-185): say so, and how to make room.
            raise scenario_injection.CannotPlace(
                f"{item.received_date}'s arrival would be moved off the scenario days to "
                f"{when}, after the history ends on {last_day} - lengthen the history or "
                f"move the scenarios")
        if moved:
            taken_days.add(when.isoformat())
        out.append(item if when == item.received_date
                   else Delivery(received_date=when, severity=item.severity,
                                  payload=item.payload))
    return out


def generated_periods() -> list:
    """The periods this generator writes, oldest first: the evening-before
    era's twelve, then the 85."""
    return schedule.periods_for_dataset(
        DATASET_ID, until=get_anchor_date())[-(N_DELIVERIES + GROWN_DAYS):]


def original_periods() -> list:
    """The 85 periods generated before the evening-before era existed."""
    return generated_periods()[GROWN_DAYS:]


def grown_periods() -> list:
    """The evening-before era's twelve periods, oldest first (REQ-GEN-044)."""
    return generated_periods()[:GROWN_DAYS]


def _grown_row_counts() -> list[int]:
    """The era's row counts, from a seed of its own so the 85's plan is
    untouched."""
    import numpy as np

    rng = np.random.default_rng(GROWN_BASE_SEED - 1000)
    return [int(n) for n in rng.integers(1_700, 2_050, size=GROWN_DAYS)]


def _plan_injections(periods):
    """Where every Birth Registrations scenario lands, resolved BEFORE
    anything is written (REQ-GEN-044 criterion 4).

    All of it up front, deliberately: a scenario that cannot be placed
    must stop the generator rather than be discovered halfway through,
    because a half-written history is one somebody has to notice is
    half-written.
    """
    from generator import scenario_injection, targeting

    mine = scenario_injection.for_dataset(DATASET_ID)
    scenario_injection.no_two_scenarios_share_a_period(mine, {DATASET_ID: periods})
    resolved = [(injection, scenario_injection.resolve(injection, periods))
                for injection in mine]
    # EVERY TARGET CHECKED BEFORE THE FIRST WRITE (REQ-GEN-184 criterion 11).

    for injection in mine:
        for extra in injection.arrivals:
            for target in extra.targets:
                targeting.check_target(target, injection.dataset_id,
                                       f"{injection.scenario_id}, its {extra.at} arrival")
    by_period = {placement.period: (injection, placement)
                 for injection, placement in resolved}
    suppressed = {name for _, placement in resolved for name in placement.suppressed}
    # A GREEN LEAD-IN OR FOLLOWING PERIOD, AND EVERY SCENARIO'S OWN ANCHOR,
    # IS QUIET TOO (REQ-GEN-185 criterion 1): it keeps its own supply and no
    # other period's resend lands on it - on the first planted rebuild one
    # landed on TS-45's day before TS-45 did, filled it, and TS-45's own
    # supply was refused. TS-47's own day was only clear before by luck.
    # A COVERED PERIOD (REQ-GEN-199, TS-78) is the scenario's own as much as
    # its anchor: its supply is one of the scenario's arrivals, and no other
    # period's resend may land on it.
    quiet = {name for _, placement in resolved
             for name in (*placement.quiet, *placement.built_green, placement.period,
                          *placement.covered)}
    return resolved, by_period, suppressed, quiet


def _covered(injected_by_period) -> frozenset[str]:
    """Every period whose own supply is an injected scenario's arrival on
    that day (Injection.covers): no ordinary chain is written for it."""
    return frozenset(name for _inj, placement in injected_by_period.values()
                     for name in placement.covered)


def _days_to_avoid(period_name: str, suppressed: set[str], quiet: set[str]) -> set[str]:
    """The days this period's arrivals must be moved off: every
    suppressed day, and every QUIET day but its own - a quiet day keeps
    its own supply and refuses everybody else's."""
    return set(suppressed) | (set(quiet) - {period_name})


#: The largest offset any derivation adds to a slot's own seed: the
#: resupply chain's +900 and its attempt number, the presets' own +19, and a
#: covered day's +50 a day - inside 999 with room to spare.
SEED_SPAN = 999


class CivilRegistration(Provider):
    """Birth Registrations' half of the shared driver (REQ-GEN-246): the old
    main()'s planning and per-slot decisions, unchanged, split across the
    driver's hooks."""

    collection_id = "civil-registration"
    dataset_id = DATASET_ID
    seed_ranges = ((1000, 2100), (39000, 41100))
    target_trial = True
    target_datasets = (DATASET_ID,)
    target_levers = "null-rate"
    amber_dataset = DATASET_ID

    def seed_schedule(self) -> list[tuple[str, int, int]]:
        out = [("the run plan", _RUN_PLAN_SEED, _RUN_PLAN_SEED),
               ("the evening-before era's row counts", GROWN_BASE_SEED - 1000,
                GROWN_BASE_SEED - 1000)]
        out += [(f"slot_{i:03d}", 1000 + i, 1000 + i + SEED_SPAN)
                for i in range(1, N_DELIVERIES + 1)]
        out += [(f"slot_{N_DELIVERIES + j:03d}", GROWN_BASE_SEED + j, GROWN_BASE_SEED + j + SEED_SPAN)
                for j in range(1, GROWN_DAYS + 1)]
        return out

    def generated_periods(self) -> list:
        return generated_periods()

    def plan(self) -> Plan:
        provider = BirthRegistrationsProvider()
        periods = generated_periods()
        originals, grown = periods[GROWN_DAYS:], periods[:GROWN_DAYS]

        # BEFORE THE FIRST WRITE (REQ-GEN-044 criterion 4) - see
        # _plan_injections()'s own docstring.
        (resolved_injections, injected_by_period, suppressed_periods,
         quiet_periods) = _plan_injections(periods)
        # ORDINARY AMBERS PLANNED BEFORE THE CLEAR TOO (post-build-review #155).
        covered_periods = _covered(injected_by_period)
        severities = _ordinary_severities(originals, injected_by_period,
                                          suppressed_periods | covered_periods)
        # NEVER STALE: an ordinary amber, and a period whose injected supply is
        # built to a target (REQ-GEN-184 criterion 4) - a stale delivery fails
        # the freshness checks, whatever it was built to.
        green_periods = _built_green(injected_by_period)
        provider.amber_dates = frozenset(
            [p.date for p, sev in zip(originals, severities) if sev == "amber"]
            + [p.date for p in periods if p.name in green_periods]
            + [p.date for p in periods if p.name in injected_by_period and any(
                x.targets for x in injected_by_period[p.name][0].arrivals)]
            # A COVERED DAY'S OWN SUPPLY is built to a target too (REQ-GEN-199).
            + [p.date for p in periods if p.name in covered_periods]
            # THE NEXT DAY'S EXTRACT A PAIR SENDS EARLY is built to a target too
            # (REQ-GEN-196): never stale either.
            + [p.date + timedelta(days=1) for p in periods if p.name in injected_by_period
               and any(f.target is not None and f.content == "next_day"
                       for x in injected_by_period[p.name][0].arrivals for f in x.files)]
            # THE EVENING-BEFORE ERA IS NEVER STALE: its supplies are on time by
            # construction, and a stale one would read red (REQ-GEN-044).
            + [p.date for p in grown])

        # The 85 first, exactly as before; then the era, with its own seeds and
        # slot ids after theirs, so nothing the 85 wrote can move.
        jobs = []
        for i, ((drawn_rows, _drawn), severity, period) in enumerate(
                zip(run_plan(), severities, originals), start=1):
            jobs.append(Job(f"slot_{i:03d}", 1000 + i, severity, period,
                            {"i": i, "rows": drawn_rows, "in_era": False}))
        for j, (rows, period) in enumerate(zip(_grown_row_counts(), grown), start=1):
            i = N_DELIVERIES + j
            jobs.append(Job(f"slot_{i:03d}", GROWN_BASE_SEED + j, None, period,
                            {"i": i, "rows": rows, "in_era": True}))
        return Plan(jobs=jobs, resolved=resolved_injections,
                    injected_by_period=injected_by_period,
                    state={"provider": provider, "periods": periods,
                           "suppressed": suppressed_periods, "quiet": quiet_periods,
                           "covered": covered_periods, "green": green_periods,
                           #: Days a shifted arrival has already claimed - see
                           #: _away_from_suppressed(). Shared across slots,
                           #: because the collision it prevents is between them.
                           "shifted_onto": set(),
                           # the last RESOLVED delivery's row count, for the
                           # row-count-growth check's dirty preset - deliberately
                           # NOT updated mid-chain.
                           "previous_row_count": None})

    def slot(self, plan: Plan, job: Job) -> list | None:
        from generator.resupply import Delivery, run_slot_chain
        from generator import targeting

        st = plan.state
        provider = st["provider"]
        i, in_era, severity, period = job.extra["i"], job.extra["in_era"], job.severity, job.period
        if in_era and i == N_DELIVERIES + 1:
            st["previous_row_count"] = None  # the era is its own run of supplies
        previous_row_count = st["previous_row_count"]
        # AN ORDINARY AMBER IS THE SIZE OF THE SUPPLY BEFORE IT (Keith,
        # 2026-10-11): its own row-count check reads no change, and the next
        # supply compares against what it would have anyway (post-build-review
        # #154). Asked for at that size and trimmed to it exactly in dirty().
        n_rows = previous_row_count if severity == "amber" and previous_row_count \
            else job.extra["rows"]
        slot_date, seed = period.date, job.seed
        id_offset = i * ID_BLOCK
        job.extra["id_offset"] = id_offset

        # A SCENARIO MAY NEED A DAY TO CARRY NO SUPPLY AT ALL, which is an
        # arrival shape like any other - TS-2's supplier outage is two of them -
        # and the only way to express it is not to write one. The slot is
        # still owed; nothing fills it.
        if period.name in st["suppressed"]:
            print(f"{period.name}: no supply at all (an injected scenario needs this "
                  f"day empty)")
            return None
        if period.name in st["covered"]:
            # ITS SUPPLY IS THE SCENARIO'S (REQ-GEN-199): written with the
            # anchor's arrivals, so nothing more here. The size carries on.
            print(f"{period.name}: its supply is an injected scenario's arrival")
            return None

        injected = plan.injected_by_period.get(period.name)
        if period.name in st["green"]:
            # A GREEN LEAD-IN OR FOLLOWING SUPPLY (REQ-GEN-185 criteria 1 and
            # 3): once, on its own day, no resupply, built to green at the size
            # of the supply before it.
            if previous_row_count:
                n_rows = previous_row_count
            payload = provider.generate(slot_date, seed=seed, n_rows=n_rows,
                                        id_offset=id_offset)
            payload, _moved = targeting.bdm_target(
                payload, targeting.Target("green"), seed=seed + 700,
                where=f"the green period {period.name}", rows=previous_row_count)
            return [Delivery(received_date=slot_date, severity=None, payload=payload)]
        if injected is not None:
            if any(x.targets for x in injected[0].arrivals) and previous_row_count:
                n_rows = previous_row_count  # asked at that size, trimmed exactly
            return _injected_chain(provider, injected[0], period, seed, id_offset, n_rows,
                                   previous_row_count, placement=injected[1])
        if in_era:
            # ONE ON-TIME SUPPLY, THE EVENING BEFORE (REQ-GEN-044): no chain.
            payload = provider.generate(slot_date, seed=seed, n_rows=n_rows,
                                        id_offset=id_offset)
            return [Delivery(received_date=slot_date - timedelta(days=1),
                             severity=None, payload=payload)]
        return _away_from_suppressed(
            list(run_slot_chain(provider, slot_date, seed, id_offset,
                                n_rows, severity, previous_row_count)),
            _days_to_avoid(period.name, st["suppressed"], st["quiet"]),
            st["shifted_onto"], last_day=st["periods"][-1].date)

    def entries(self, plan: Plan, job: Job, deliveries: list, run_index_start: int) -> list[dict]:
        entries = _manifest_entries_for_slot(deliveries, job.slot_id, job.period.name,
                                             run_index_start, job.extra["id_offset"], job.seed)
        injected = plan.injected_by_period.get(job.period.name)
        if injected is not None and injected[0].covers:
            # A COVERED DAY'S SUPPLY IS THAT DAY'S (REQ-GEN-199): recorded
            # under its own period, which is what it is for.
            periods = plan.state["periods"]
            for delivery_obj, entry in zip(deliveries, entries):
                offset = (delivery_obj.received_date - job.period.date).days
                if 0 < offset <= injected[0].covers:
                    entry["period"] = periods[periods.index(job.period) + offset].name
                    entry["slot_id"] = f"slot_{job.extra['i'] + offset:03d}"
        return entries

    def received_at(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict) -> str:
        from qa_tools.common import slots

        period = job.period
        injected = plan.injected_by_period.get(period.name)
        if injected is not None:
            # THE SCENARIO'S OWN INSTANT, not the payload's earliest extract.
            # The whole of TS-1 is that the third file lands at 20:00 rather
            # than whenever the rows happen to say.
            extra = injected[0].arrivals[n - 1]
            return asset_time.isoformat(asset_time.wall_clock(delivery_obj.received_date, extra.at))
        if period.name in plan.state["green"]:
            # ON TIME (REQ-GEN-185 criterion 1; post-build-review #156): a
            # lead-in or following supply arrives inside its due time and
            # grace, at the midpoint.
            due = slots.slot_instants(DATASET_ID, period.date)
            return asset_time.isoformat(due.due_at + due.grace / 2)
        if job.extra["in_era"]:
            # AN HOUR BEFORE ITS DUE INSTANT, the evening before (REQ-GEN-044):
            # on time, and inside its own claim window, which opens at 18:00.
            due = slots.slot_instants(DATASET_ID, period.date)
            return asset_time.isoformat(due.due_at - timedelta(hours=1))
        # THE RECEIPT INSTANT IS THE DATA'S OWN: the earliest extract_timestamp
        # in the file that just landed - the same value
        # qa_tools/tools/dataset_stats.py computes downstream as
        # earliest_extract, so the bookkeeping and the warehouse cannot
        # disagree about when a supply turned up.
        return _received_at(delivery_obj.payload, delivery_obj.received_date,
                            f"received_at for {entry['run_id']}")

    def files(self, plan: Plan, job: Job, n: int, delivery_obj, entry: dict, name: str):
        if isinstance(delivery_obj, PairDelivery):
            files = {fn: csv for fn, (csv, _at) in delivery_obj.files.items()}
            # EACH FILE'S OWN RECEIPT (REQ-GEN-196): the pair is two arrivals'
            # worth of evidence in one delivery.
            received = {fn: asset_time.wall_clock(delivery_obj.received_date, at)
                        for fn, (_csv, at) in delivery_obj.files.items()}
            return files, received
        # A filename matching this dataset's own configured arrivalPattern.
        files = {f"birth_registrations_{delivery_obj.received_date.isoformat()}.csv":
                 delivery_obj.payload.to_csv(index=False)}
        return files, asset_time.parse_instant(entry["received_at"], entry["run_id"])

    def describe(self, entry: dict, delivery_obj) -> str:
        return f"{len(delivery_obj.payload):5d} rows"

    def after_slot(self, plan: Plan, job: Job, deliveries: list) -> None:
        # this slot's final (resolved-or-abandoned) row count
        plan.state["previous_row_count"] = len(deliveries[-1].payload)


PROVIDER = CivilRegistration()
