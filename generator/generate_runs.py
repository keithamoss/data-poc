"""
Orchestrates multiple daily runs of the birth-registrations feed into
data/raw/ - the "generate a few different runs of synthetic data" part of
the brief, sized ~10 runs with most clean and 2-3 deliberately dirty (the
user's chosen default).

Each run is a separate simulated day's extract (see daily_batch.py for why
this is an event-flow generator, not a resample of a population snapshot).
Runs get non-overlapping id_offset blocks so registration_number /
source_system_record_id stay globally unique across the whole batch of
runs - this matters once they're all loaded into one SQLite table for
cross-run checks (drift, trend).

Dirty runs reuse dirty.py's apply_birth_registrations_presets(), which is
calibrated to land exactly in the amber/red bands defined in
bdm-birth-registrations-soda-checks.yml (sex invalid_percent,
place_of_birth_facility missing_percent) - so a run marked "dirty: amber"
here should genuinely trip the amber checks and nothing worse, and "dirty:
red" should trip the fail thresholds.
"""
from __future__ import annotations
import json
import os
from datetime import date, timedelta

from daily_batch import generate_daily_batch
from dirty import apply_birth_registrations_presets

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
ID_BLOCK = 100_000  # per-run id_offset spacing - well above any single run's row count

# (day offset from run 1, base row count, dirty severity or None)
# 10 runs, most clean, 2 amber + 1 red = 3 dirty, per the user's chosen default.
RUN_PLAN = [
    (0, 1_820, None),
    (1, 1_940, None),
    (2, 1_760, None),
    (3, 2_010, "amber"),
    (4, 1_880, None),
    (5, 1_790, None),
    (6, 1_950, "amber"),
    (7, 1_860, None),
    (8, 1_900, "red"),
    (9, 1_830, None),
]

START_DATE = date(2026, 9, 1)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = []

    for i, (day_offset, n_rows, severity) in enumerate(RUN_PLAN, start=1):
        run_date = START_DATE + timedelta(days=day_offset)
        seed = 1000 + i
        id_offset = i * ID_BLOCK

        df = generate_daily_batch(run_date, seed=seed, n_rows=n_rows, id_offset=id_offset)
        if severity:
            df = apply_birth_registrations_presets(df, severity=severity, seed=seed + 500)

        run_id = f"run_{i:02d}_{run_date.isoformat()}"
        out_path = os.path.join(OUT_DIR, f"{run_id}.csv")
        df.to_csv(out_path, index=False)

        manifest.append({
            "run_id": run_id,
            "run_index": i,
            "run_date": run_date.isoformat(),
            "n_rows_generated": int(len(df)),
            "dirty_severity": severity,  # None | "amber" | "red"
            "id_offset": id_offset,
            "seed": seed,
            "file": os.path.basename(out_path),
        })
        tag = f"DIRTY({severity})" if severity else "clean"
        print(f"{run_id}: {len(df):5d} rows  [{tag}]  -> {out_path}")

    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nWrote {len(manifest)} runs + manifest.json to {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
