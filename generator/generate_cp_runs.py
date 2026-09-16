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
"""
from __future__ import annotations
import json
import os
from datetime import date

import numpy as np
import pandas as pd

from generator.anchor_date import get_anchor_date
from generator import dirty as dirty_mod
from synthetic_data_generator.population import generate_population
from synthetic_data_generator.child_protection import generate_child_protection_collection

ROOT = os.path.join(os.path.dirname(__file__), "..")

OUT_DIR = os.path.join(ROOT, "data", "cp_raw")

POPULATION_N = 70_000
N_CASE_WORKERS = 60
BASE_SEED = 5000  # distinct range from generate_runs.py's 1000s and generate.py's demo seeds

TABLES = ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers", "cp_case_workers"]

# (quarter offset from run 1, dirty severity or None) - 16 quarterly
# snapshots spanning 4 years (widened from 10 WEEKLY snapshots,
# 2026-09-16, Keith's own call - see plans/wider.md's cadence-widening +
# history-depth follow-up notes: CP's own framing as "a periodic full
# extract" fits a quarterly re-extract more naturally than a weekly one
# for a real casework/investigation collection, and getting real
# quarterly-spaced history is also a meaningful stress test for the
# as-of/time-travel features, which need genuinely deep, sparse history
# to demonstrate against; 4 years rather than 3, Keith's own follow-up
# call, for even deeper history). Ratio scaled from the original 10-run
# plan's 7 clean / 2 amber / 1 red. Deliberately ends on the red run
# (unchanged from the original plan): Keith wanted the dashboard's
# default/latest view to show real red on this collection specifically,
# not just buried a few runs back in the trend history - see
# plans/wider.md and the AskUserQuestion decision that shaped this
# ("make the latest run itself dirty" / "Child Protection only"). First
# run stays clean - it's orchestrate_cp.py's own Evidently reference run.
_RUN_PLAN_SEED = 5900  # distinct range from generation seeds (BASE_SEED+...)
N_QUARTERS = 16


def _build_run_plan(n: int, seed: int) -> list[tuple[int, str | None]]:
    rng = np.random.default_rng(seed)
    n_amber = max(1, round(n * 0.25))  # ~matches the original plan's 2/10 ratio
    n_clean_middle = n - 2 - n_amber  # first (clean) & last (red) carved out separately
    middle = [None] * n_clean_middle + ["amber"] * n_amber
    rng.shuffle(middle)
    return list(enumerate([None] + list(middle) + ["red"]))


RUN_PLAN = _build_run_plan(N_QUARTERS, _RUN_PLAN_SEED)


def _quarter_start(d: date) -> date:
    """The first day of the calendar quarter containing `d` - a real
    periodic full-collection extract lands on quarter boundaries
    (Jan/Apr/Jul/Oct 1) more naturally than on an arbitrary day, same
    "keep it realistic" rationale the old weekly version applied via its
    own always-a-Monday alignment."""
    quarter_start_month = ((d.month - 1) // 3) * 3 + 1
    return date(d.year, quarter_start_month, 1)


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


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"Generating base Child Protection collection (population={POPULATION_N:,}, seed={BASE_SEED})...")
    pop = generate_population(POPULATION_N, seed=BASE_SEED)
    base_tables = generate_child_protection_collection(pop, seed=BASE_SEED + 1000, n_case_workers=N_CASE_WORKERS)
    for name in TABLES:
        print(f"  {name}: {len(base_tables[name]):,} rows")

    manifest = []
    for i, (quarter_offset, severity) in enumerate(RUN_PLAN, start=1):
        snapshot_date = _add_quarters(START_DATE, quarter_offset)
        run_id = f"cp_run_{i:02d}_{snapshot_date.isoformat()}"
        run_dir = os.path.join(OUT_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)

        tables = {name: base_tables[name].copy() for name in TABLES}
        if severity:
            # Reference tables passed to the dangling-FK injectors
            # (existing_ids exclusion sets, and cp_investigations' own
            # closed-case eligibility filter) are base_tables - the real,
            # never-dirtied source - not this run's own `tables` dict,
            # so a preset applied earlier in this block (e.g. cp_clients'
            # own PK-duplication further down) can never change what
            # another preset considers a "real" ID (duplication only ever
            # adds rows, never removes the original, so this is belt-and-
            # braces rather than a live bug either way - but base_tables
            # is the unambiguously correct thing to point at).
            tables["cp_notifications"] = dirty_mod.apply_cp_notifications_presets(
                tables["cp_notifications"], base_tables["cp_clients"], base_tables["cp_case_workers"],
                severity, seed=BASE_SEED + 4100 + i)
            tables["cp_placements"] = dirty_mod.apply_cp_placements_presets(
                tables["cp_placements"], tables["cp_carers"], base_tables["cp_clients"],
                severity, seed=BASE_SEED + 4200 + i)
            tables["cp_investigations"] = dirty_mod.apply_cp_investigations_presets(
                tables["cp_investigations"], tables["cp_clients"], base_tables["cp_notifications"],
                base_tables["cp_case_workers"], severity, seed=BASE_SEED + 4300 + i)
            tables["cp_clients"] = dirty_mod.apply_cp_clients_presets(
                tables["cp_clients"], severity, seed=BASE_SEED + 4400 + i)
            tables["cp_carers"] = dirty_mod.apply_cp_carers_presets(
                tables["cp_carers"], severity, seed=BASE_SEED + 4500 + i)
            tables["cp_case_workers"] = dirty_mod.apply_cp_case_workers_presets(
                tables["cp_case_workers"], severity, seed=BASE_SEED + 4600 + i)

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
