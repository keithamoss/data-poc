"""
Generates periodic Child Protection collection snapshots into
data/cp_raw/ - the "whole collection" counterpart to generate_runs.py's
daily birth-registrations feed.

Deliberately a different generation model from generate_runs.py, by design
(see plans/wider.md action 2 and the AskUserQuestion decisions that shaped
this): Child Protection isn't a daily event feed, it's a periodic full
extract of the same underlying casework collection - the population and
the Child Protection tables are built ONCE (fixed seed), then re-extracted
10 times as weekly snapshots. Row counts stay roughly stable run to run,
which is what a real periodic extract of an active caseload would look
like, unlike birth-registrations' fresh-cohort-per-day model.

Dirty injection touches 4 of the 6 tables on amber/red runs:
cp_notifications (dirty.py's apply_cp_notifications_presets - an unknown
concern_type code, near-duplicate notifications), cp_placements
(apply_cp_placements_presets - a placement reassigned to a non-Approved
carer), cp_investigations (apply_cp_investigations_presets - a
closed-case investigation reopened), and cp_clients
(apply_cp_clients_presets - an unrecognised postcode, an out-of-range
date_of_birth). The other two tables (cp_carers, cp_case_workers) are
clean in every run - this mirrors how birth-registrations only
demonstrates dirty behaviour on a subset of its columns, not an
oversight.

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
"""
from __future__ import annotations
import json
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

from anchor_date import get_anchor_date

ROOT = os.path.join(os.path.dirname(__file__), "..")
GENERATOR_DIR = os.path.join(ROOT, "synthetic-data-generator")
sys.path.insert(0, GENERATOR_DIR)
sys.path.insert(0, os.path.join(GENERATOR_DIR, "reference"))

from population import generate_population  # noqa: E402
from child_protection import generate_child_protection_collection  # noqa: E402
# Re-affirmed at index 0 AFTER the population/child_protection imports
# above, not just once before them - a REAL bug, found live while adding
# apply_cp_clients_presets below: both this directory and
# synthetic-data-generator/ have their own dirty.py (kept manually in
# sync for the 3 shared CP presets - see this module's own docstring).
# Putting this insert before the imports above wasn't enough:
# synthetic-data-generator/population.py's own module-level code does
# `sys.path.insert(0, os.path.dirname(__file__))` as a side effect of
# being imported, which re-inserts synthetic-data-generator/ at index 0
# and silently undoes an earlier insert of this directory - confirmed by
# instrumenting this script directly and printing sys.path right before
# `import dirty` (it showed synthetic-data-generator/ back at index 0).
# So this has to run AFTER every import that could itself touch
# sys.path, immediately before `import dirty`, not just once up front.
# Caught this time because the new function simply didn't exist in the
# wrong file yet (a loud AttributeError) - a genuinely dangerous variant
# of the same bug wouldn't be loud at all: editing an EXISTING shared
# preset's behaviour here without updating the other copy would silently
# keep running the stale version, no error at all. See
# plans/qa-pipeline.md for the regression test this got.
sys.path.insert(0, os.path.dirname(__file__))
import dirty as dirty_mod  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "cp_raw")

POPULATION_N = 70_000
N_CASE_WORKERS = 60
BASE_SEED = 5000  # distinct range from generate_runs.py's 1000s and generate.py's demo seeds

TABLES = ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers", "cp_case_workers"]

# (week offset from run 1, dirty severity or None) - 10 weekly snapshots,
# same 7 clean / 2 amber / 1 red ratio as generate_runs.py's RUN_PLAN.
# Deliberately ends on the red run (unlike generate_runs.py, which ends
# clean): Keith wanted the dashboard's default/latest view to show real
# red on this collection specifically, not just buried a few runs back in
# the trend history - see plans/wider.md and the AskUserQuestion decision
# that shaped this ("make the latest run itself dirty" / "Child Protection
# only").
RUN_PLAN = [
    (0, None), (1, None), (2, None), (3, "amber"), (4, None),
    (5, None), (6, "amber"), (7, None), (8, None), (9, "red"),
]

# Rolling window ending on the anchor date ("today" by default, pinnable
# via GENERATOR_ANCHOR_DATE - see anchor_date.py), same fix and rationale
# as generate_runs.py's own START_DATE - un-stales the fixture generally
# (plans/qa-pipeline.md #3's follow-up covers both). No wall-clock-
# relative check depends on CP's dates today, unlike BDM's, but there's
# no reason to leave CP's snapshots drifting stale either. Keeps the
# "always a Monday" weekly-extract realism touch by anchoring to the most
# recent Monday on/before the anchor date, not the anchor date itself.
_anchor = get_anchor_date()
_last_monday = _anchor - timedelta(days=_anchor.weekday())
START_DATE = _last_monday - timedelta(weeks=9)


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


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Generating base Child Protection collection (population={POPULATION_N:,}, seed={BASE_SEED})...")
    pop = generate_population(POPULATION_N, seed=BASE_SEED)
    base_tables = generate_child_protection_collection(pop, seed=BASE_SEED + 1000, n_case_workers=N_CASE_WORKERS)
    for name in TABLES:
        print(f"  {name}: {len(base_tables[name]):,} rows")

    manifest = []
    for i, (week_offset, severity) in enumerate(RUN_PLAN, start=1):
        snapshot_date = START_DATE + timedelta(weeks=week_offset)
        run_id = f"cp_run_{i:02d}_{snapshot_date.isoformat()}"
        run_dir = os.path.join(OUT_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)

        tables = {name: base_tables[name].copy() for name in TABLES}
        if severity:
            tables["cp_notifications"] = dirty_mod.apply_cp_notifications_presets(
                tables["cp_notifications"], severity, seed=BASE_SEED + 4100 + i)
            tables["cp_placements"] = dirty_mod.apply_cp_placements_presets(
                tables["cp_placements"], tables["cp_carers"], severity, seed=BASE_SEED + 4200 + i)
            tables["cp_investigations"] = dirty_mod.apply_cp_investigations_presets(
                tables["cp_investigations"], tables["cp_clients"], severity, seed=BASE_SEED + 4300 + i)
            tables["cp_clients"] = dirty_mod.apply_cp_clients_presets(
                tables["cp_clients"], severity, seed=BASE_SEED + 4400 + i)

        row_counts = {}
        for name in TABLES:
            df = _add_extract_timestamp(tables[name], snapshot_date, None, seed=BASE_SEED + 5000 + i)
            cols = [c for c in df.columns if not c.startswith("_")]
            df[cols].to_csv(os.path.join(run_dir, f"{name}.csv"), index=False)
            row_counts[name] = int(len(df))

        manifest.append({
            "run_id": run_id,
            "run_index": i,
            "run_date": snapshot_date.isoformat(),
            "dirty_severity": severity,
            "seed": BASE_SEED + i,
            "row_counts": row_counts,
        })
        tag = f"DIRTY({severity})" if severity else "clean"
        print(f"{run_id}: {row_counts['cp_notifications']:5d} notifications  [{tag}]  -> {run_dir}")

    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nWrote {len(manifest)} snapshot runs + manifest.json to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
