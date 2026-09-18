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

RESUPPLY SIMULATION. Keith's team's real practice: a delivery whose file
has a RED failing check (never amber - a warning alone doesn't trigger
this) gets a resupply request sent to the supplier, and a corrected (or
sometimes still-broken) resupply arrives some working days later - "no
single fixed resupply rate," by design. manifest.json gains
delivery_id/attempt_number/delivery_date/arrived_date/is_resupply/
supersedes_run_id fields, and one logical delivery can now produce
MULTIPLE manifest entries (one per attempt), each its own CSV.

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

manifest.json is written in GENERATION order (by delivery, then by
attempt within that delivery), not chronological arrival order - a
resupply for an early delivery can easily arrive after a later delivery's
own on-time first attempt. Any future consumer that needs "what actually
happened, in the order it happened" must sort by arrived_date itself.
"""
from __future__ import annotations
import json
import os
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from generator.anchor_date import get_anchor_date
from generator.daily_batch import generate_daily_batch
from generator.dirty import apply_birth_registrations_presets, inject_stale_delivery
from generator.resupply import MAX_ATTEMPTS, DatasetProvider, run_delivery_chain

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
ID_BLOCK = 100_000  # per-delivery id_offset spacing - well above any single delivery's row count

# (day offset from delivery 1, base row count, first-attempt dirty severity or None)
# 120 scheduled deliveries (widened again 2026-09-16, Keith's own call,
# same day as Thread C's as-of picker landed: the previous 60-delivery
# window barely cleared AS_OF_OFFSET_DAYS' own 60-day span - the DEFAULT
# as-of date, today minus 60, landed one day before this dataset's own
# earliest real run, so the flagship real dataset showed "no data" on
# the default view. 120 gives genuine margin beyond the 60-day offset,
# not just enough to scrape by - Keith's own words: "this will mean an
# occasional regeneration, but that's fine." Originally deepened from
# ~10 to 60 deliveries on 2026-09-16 too - see plans/dashboard.md #5's
# "deepening simulated history" follow-up, done together with widening
# Child Protection's cadence to quarterly since the two were explicitly
# parked as one piece of work) - same ~60/20/20 clean/amber/red ratio as
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
N_DELIVERIES = 120


def _build_run_plan(n: int, seed: int) -> list[tuple[int, int, str | None]]:
    rng = np.random.default_rng(seed)
    n_amber = round(n * 0.2)
    n_red = round(n * 0.2)
    n_clean_middle = n - n_amber - n_red - 2  # first/last carved out separately, always clean
    middle = [None] * n_clean_middle + ["amber"] * n_amber + ["red"] * n_red
    rng.shuffle(middle)
    severities = [None] + list(middle) + [None]

    row_counts = rng.integers(1_700, 2_050, size=n)
    return [(i, int(row_counts[i]), severities[i]) for i in range(n)]


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
START_DATE = get_anchor_date() - timedelta(days=N_DELIVERIES - 1)


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


def _manifest_entries_for_delivery(attempts: list, i: int, delivery_id: str, delivery_date: date,
                                    run_index_start: int, id_offset: int, seed: int) -> list[dict]:
    """Pure manifest-entry construction for one delivery's full attempt
    chain (run_id derivation, supersedes_run_id chaining across attempts)
    - no file I/O, so this is independently testable
    (tests/test_resupply.py) without needing main()'s own CSV writes or
    a real provider. main() calls this directly and only adds the
    file-writing side effect on top, so the two can't drift apart.
    `run_index_start` is the manifest's own running length *before* this
    delivery's entries (i.e. `len(manifest)`) - entries are 1-indexed
    from there, matching the original inline `len(manifest) + 1`."""
    entries = []
    previous_run_id = None
    for attempt in attempts:
        suffix = "" if attempt.attempt_number == 1 else f"_resupply{attempt.attempt_number - 1}"
        # :03d, not :02d - N_DELIVERIES=120 (widened 2026-09-16) needs 3
        # digits, and the padding must stay WIDE ENOUGH for every id to
        # sort correctly as a plain string: a real bug caught by
        # test_severity_counts_match_run_plan when this was still :02d
        # ("delivery_100" < "delivery_11" lexicographically) - the same
        # ids get string-sorted for real downstream too
        # (qa_tools/common/qa_results_reader.py's list_run_ids()/
        # read_qa_results(), which read the committed qa_results/ tree's
        # own directory names back). Current callers of those two
        # happen to re-sort by run_index/run_timestamp afterward so
        # nothing downstream was actually producing wrong output yet -
        # still a real, latent defect in what "sorted" means there, not
        # just this module's own test.
        run_id = f"run_{i:03d}_{delivery_date.isoformat()}{suffix}"
        entries.append({
            "run_id": run_id,
            "run_index": run_index_start + len(entries) + 1,
            "delivery_id": delivery_id,
            "delivery_date": delivery_date.isoformat(),
            "attempt_number": attempt.attempt_number,
            "arrived_date": attempt.arrived_date.isoformat(),
            "run_date": attempt.arrived_date.isoformat(),  # the date this attempt's file was actually received
            "is_resupply": attempt.is_resupply,
            "supersedes_run_id": previous_run_id,
            "n_rows_generated": int(len(attempt.payload)),
            "dirty_severity": attempt.severity,  # None | "amber" | "red" - this ATTEMPT's own outcome
            "id_offset": id_offset,
            "seed": seed,
            "file": f"{run_id}.csv",
        })
        previous_run_id = run_id
    return entries


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    provider: DatasetProvider = BirthRegistrationsProvider()
    manifest = []
    previous_row_count = None  # the last RESOLVED delivery's row count, for
    # the row-count-growth check's dirty preset - deliberately NOT updated
    # mid-chain: a viewer comparing "is this delivery's row count
    # reasonable" would check against the last good reference point, not
    # against an already-failed attempt of the same delivery.

    for i, (day_offset, n_rows, severity) in enumerate(RUN_PLAN, start=1):
        delivery_id = f"delivery_{i:03d}"
        delivery_date = START_DATE + timedelta(days=day_offset)
        seed = 1000 + i
        id_offset = i * ID_BLOCK

        attempts = list(run_delivery_chain(provider, delivery_date, seed, id_offset,
                                            n_rows, severity, previous_row_count))
        entries = _manifest_entries_for_delivery(attempts, i, delivery_id, delivery_date,
                                                  len(manifest), id_offset, seed)

        for attempt, entry in zip(attempts, entries):
            out_path = os.path.join(OUT_DIR, entry["file"])
            attempt.payload.to_csv(out_path, index=False)
            tag = f"DIRTY({attempt.severity})" if attempt.severity else "clean"
            resupply_tag = (f"  [resupply attempt {attempt.attempt_number - 1}, "
                             f"arrived {attempt.arrived_date.isoformat()}]") if attempt.attempt_number > 1 else ""
            print(f"{entry['run_id']}: {len(attempt.payload):5d} rows  [{tag}]{resupply_tag}  -> {out_path}")
            if attempt.severity == "red" and attempt.attempt_number >= MAX_ATTEMPTS:
                print(f"  -> still red after {attempt.attempt_number} attempts - "
                      f"giving up (hit MAX_ATTEMPTS={MAX_ATTEMPTS})")

        manifest.extend(entries)
        previous_row_count = len(attempts[-1].payload)  # this delivery's final (resolved-or-abandoned) row count

    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    n_red_chains = sum(1 for _, _, sev in RUN_PLAN if sev == "red")
    print(f"\nWrote {len(manifest)} attempts across {len(RUN_PLAN)} scheduled deliveries "
          f"({n_red_chains} of which went red and triggered a resupply chain) + manifest.json "
          f"to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
