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
single fixed resupply rate," by design. This module now simulates the
whole attempt chain for any delivery whose first attempt is red:
manifest.json gains delivery_id/attempt_number/delivery_date/arrived_date/
is_resupply/supersedes_run_id fields, and one logical delivery can now
produce MULTIPLE manifest entries (one per attempt), each its own CSV.

Scope, deliberately: this is a GENERATOR-LAYER change only.
real_tools/*.py, both dashboard builders, and the dashboard UI all still
assume "one manifest entry = one calendar day" and have NOT been updated
to understand attempt chains - that mismatch is intentional (see
plans/wider.md's synthetic-data-realism item), left as the concrete input
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

import numpy as np
import pandas as pd

from daily_batch import generate_daily_batch
from dirty import apply_birth_registrations_presets

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
ID_BLOCK = 100_000  # per-delivery id_offset spacing - well above any single delivery's row count

# (day offset from delivery 1, base row count, first-attempt dirty severity or None)
# 10 scheduled deliveries: most clean, 2 amber, 2 red - bumped from 1 red so
# the resupply-chain simulation below has more than one independent example
# to actually demonstrate variability (delay length, whether it resolves
# in one resupply or several), not just a single data point.
RUN_PLAN = [
    (0, 1_820, None),
    (1, 1_940, None),
    (2, 1_760, None),
    (3, 2_010, "amber"),
    (4, 1_880, None),
    (5, 1_790, "red"),
    (6, 1_950, "amber"),
    (7, 1_860, None),
    (8, 1_900, "red"),
    (9, 1_830, None),
]

START_DATE = date(2026, 9, 1)

# --- Resupply-chain calibration ------------------------------------------
MAX_ATTEMPTS = 8  # a hard ceiling so a pathological chain can't run forever
STILL_RED_PROB = 0.60  # per-attempt chance a resupply is ALSO red - a chain
# needing 5+ attempts to resolve happens ~13% of the time a delivery goes
# red at all (0.6**4), matching Keith's own framing: "sometimes, in a
# really bad scenario" - most resolve within 1-2 resupplies.

# Delay (in working days) until the next attempt arrives: skewed toward
# fast, geometrically decaying so days 1-3 carry ~79% of the probability
# mass and the remaining ~21% tails off out to day 10 - "most suppliers
# land either the next day or within three days, with a longish tail
# going out to around 10 working days" (Keith's own calibration).
_DELAY_DAYS = np.arange(1, 11)
_DELAY_WEIGHTS = 0.6 ** (_DELAY_DAYS - 1)
_DELAY_WEIGHTS = _DELAY_WEIGHTS / _DELAY_WEIGHTS.sum()


def _add_business_days(start: date, n: int) -> date:
    """start + n working days (Mon-Fri) - real supplier turnaround is
    quoted in working days, not calendar days. No public-holiday calendar
    is modelled - a known, documented simplification, not an oversight."""
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            added += 1
    return d


def _churn_rows(df: pd.DataFrame, seed: int, run_date: date, id_offset: int,
                 add_rate: float = 0.02, modify_rate: float = 0.02, remove_rate: float = 0.01) -> pd.DataFrame:
    """Between one attempt and the next, the source system hasn't been
    frozen - deliberately secondary, small-rate churn on top of whatever
    the dirty preset above does: a few more registrations have since been
    recorded (id_offset is a dedicated, unused sub-block of this
    delivery's own reserved ID range, so no collision with the original
    attempt's IDs), a few existing ones have been corrected by BDM staff
    (nudged extract_timestamp - the one field every row has that can shift
    without touching anything a QA check keys off), and a few have been
    voided. Keith's own framing: "largely the same rows... but also
    probably new rows that have been added or that had been changed or
    deleted since the first supply" - the resupply is not a fresh random
    draw of that day's data."""
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


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = []
    previous_row_count = None  # the last RESOLVED delivery's row count, for
    # the row-count-growth check's dirty preset - deliberately NOT updated
    # mid-chain (see the loop below): a viewer comparing "is this delivery's
    # row count reasonable" would check against the last good reference
    # point, not against an already-failed attempt of the same delivery.

    for i, (day_offset, n_rows, severity) in enumerate(RUN_PLAN, start=1):
        delivery_id = f"delivery_{i:02d}"
        delivery_date = START_DATE + timedelta(days=day_offset)
        seed = 1000 + i
        id_offset = i * ID_BLOCK

        df = generate_daily_batch(delivery_date, seed=seed, n_rows=n_rows, id_offset=id_offset)
        if severity:
            df = apply_birth_registrations_presets(df, severity=severity, seed=seed + 500,
                                                    previous_row_count=previous_row_count)

        attempt_number = 1
        arrived_date = delivery_date
        attempt_severity = severity
        supersedes_run_id = None

        while True:
            suffix = "" if attempt_number == 1 else f"_resupply{attempt_number - 1}"
            run_id = f"run_{i:02d}_{delivery_date.isoformat()}{suffix}"
            out_path = os.path.join(OUT_DIR, f"{run_id}.csv")
            df.to_csv(out_path, index=False)

            manifest.append({
                "run_id": run_id,
                "run_index": len(manifest) + 1,
                "delivery_id": delivery_id,
                "delivery_date": delivery_date.isoformat(),
                "attempt_number": attempt_number,
                "arrived_date": arrived_date.isoformat(),
                "run_date": arrived_date.isoformat(),  # the date this attempt's file was actually received
                "is_resupply": attempt_number > 1,
                "supersedes_run_id": supersedes_run_id,
                "n_rows_generated": int(len(df)),
                "dirty_severity": attempt_severity,  # None | "amber" | "red" - this ATTEMPT's own outcome
                "id_offset": id_offset,
                "seed": seed,
                "file": os.path.basename(out_path),
            })
            tag = f"DIRTY({attempt_severity})" if attempt_severity else "clean"
            resupply_tag = f"  [resupply attempt {attempt_number - 1}, arrived {arrived_date.isoformat()}]" if attempt_number > 1 else ""
            print(f"{run_id}: {len(df):5d} rows  [{tag}]{resupply_tag}  -> {out_path}")

            if attempt_severity != "red":
                break  # resolved (or was never red to begin with)
            if attempt_number >= MAX_ATTEMPTS:
                print(f"  -> still red after {attempt_number} attempts - giving up (hit MAX_ATTEMPTS={MAX_ATTEMPTS})")
                break

            resupply_rng = np.random.default_rng(seed + 700 + attempt_number)
            delay_days = int(resupply_rng.choice(_DELAY_DAYS, p=_DELAY_WEIGHTS))
            arrived_date = _add_business_days(arrived_date, delay_days)
            supersedes_run_id = run_id
            attempt_number += 1

            df = _churn_rows(df, seed=seed + 800 + attempt_number, run_date=delivery_date,
                              id_offset=id_offset + 50_000 + attempt_number * 100)
            if resupply_rng.random() < STILL_RED_PROB:
                df = apply_birth_registrations_presets(df, severity="red", seed=seed + 900 + attempt_number,
                                                        previous_row_count=previous_row_count)
                attempt_severity = "red"
            else:
                attempt_severity = None

        previous_row_count = len(df)  # this delivery's final (resolved-or-abandoned) row count

    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    n_red_chains = sum(1 for i, (_, _, sev) in enumerate(RUN_PLAN) if sev == "red")
    print(f"\nWrote {len(manifest)} attempts across {len(RUN_PLAN)} scheduled deliveries "
          f"({n_red_chains} of which went red and triggered a resupply chain) + manifest.json "
          f"to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
