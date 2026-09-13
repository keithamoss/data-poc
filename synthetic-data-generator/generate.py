#!/usr/bin/env python3
"""
CLI entrypoint: builds the master population registry, the Child Protection
Casework collection (6 related tables), and two more agencies' views of the
same people (BDM birth registrations, school enrollment) - then writes
everything to CSV, with an optional --dirty mode that seeds known QA
failure modes into the output.

    python3 generate.py --population 200000 --outdir output/demo
    python3 generate.py --population 3000000 --outdir output/full_scale --dirty amber

Output layout:
    <outdir>/public/...        what a downstream QA/test consumer would get -
                                agency-shaped tables only, no cross-agency
                                join keys, exactly like real agency data.
    <outdir>/internal/...      the master registry and a linkage answer key
                                (person_uid -> every agency's own ID for
                                that person) - for validating your own
                                entity-resolution or the generator itself.
                                Never ship this alongside the public/ files
                                in a real test exercise - that's the answer
                                key, not test data.

See README.md for the scaling story (this has been timed at 3,000,000
people in ~18s on a single core - see the "Scale" section) and for how
--dirty ties back to the Soda checks already defined for this project.
"""
from __future__ import annotations
import argparse
import os
import time
import sys

import pandas as pd

from population import generate_population, _age_years
from child_protection import generate_child_protection_collection
from agency_datasets import generate_birth_registrations, generate_school_enrollment
import dirty as dirty_mod

PUBLIC_COLUMNS = {
    "birth_registrations": [c for c in
        ["registration_number","child_given_names","child_family_name","date_of_birth","sex",
         "place_of_birth_suburb","place_of_birth_facility","date_registered",
         "registering_parent_1_name","registering_parent_2_name","is_multiple_birth",
         "source_system_record_id","extract_timestamp"]],
    "cp_clients": ["cp_client_id","given_name","family_name","date_of_birth","sex","suburb","postcode",
                    "case_opened_date","case_status"],
    "school_enrollment": ["student_id","given_name","family_name","date_of_birth","year_level",
                            "school_name","enrollment_date"],
}


def build(population_n: int, seed: int, n_case_workers: int, dirty: str):
    t0 = time.time()
    pop = generate_population(population_n, seed=seed)
    print(f"  population registry: {len(pop):,} people in {time.time()-t0:.1f}s")

    t1 = time.time()
    cp_tables = generate_child_protection_collection(pop, seed=seed + 1000, n_case_workers=n_case_workers)
    print(f"  child protection collection: {len(cp_tables['cp_clients']):,} clients, "
          f"{len(cp_tables['cp_notifications']):,} notifications, "
          f"{len(cp_tables['cp_investigations']):,} investigations, "
          f"{len(cp_tables['cp_placements']):,} placements in {time.time()-t1:.1f}s")

    t2 = time.time()
    birth_reg = generate_birth_registrations(pop, seed=seed + 2000)
    school = generate_school_enrollment(cp_tables["cp_clients"], seed=seed + 3000)
    print(f"  birth_registrations ({len(birth_reg):,} rows) + school_enrollment "
          f"({len(school):,} rows) in {time.time()-t2:.1f}s")

    if dirty != "none":
        t3 = time.time()
        birth_reg = dirty_mod.apply_birth_registrations_presets(birth_reg, dirty, seed=seed + 4000)
        cp_tables["cp_notifications"] = dirty_mod.apply_cp_notifications_presets(
            cp_tables["cp_notifications"], dirty, seed=seed + 4100)
        print(f"  applied '{dirty}' failure-injection presets in {time.time()-t3:.1f}s")

    return pop, cp_tables, birth_reg, school


def build_linkage_answer_key(cp_tables, birth_reg, school) -> pd.DataFrame:
    key = cp_tables["cp_clients"][["_person_uid", "cp_client_id"]].rename(columns={"_person_uid": "person_uid"})
    key = key.merge(birth_reg[["_person_uid", "registration_number"]].rename(columns={"_person_uid": "person_uid"}),
                     on="person_uid", how="left")
    key = key.merge(school[["_person_uid", "student_id"]].rename(columns={"_person_uid": "person_uid"}),
                     on="person_uid", how="left")
    return key


def write_outputs(outdir, pop, cp_tables, birth_reg, school, answer_key):
    public_dir = os.path.join(outdir, "public")
    internal_dir = os.path.join(outdir, "internal")
    os.makedirs(public_dir, exist_ok=True)
    os.makedirs(internal_dir, exist_ok=True)

    birth_reg[PUBLIC_COLUMNS["birth_registrations"]].to_csv(os.path.join(public_dir, "birth_registrations.csv"), index=False)
    school[PUBLIC_COLUMNS["school_enrollment"]].to_csv(os.path.join(public_dir, "school_enrollment.csv"), index=False)
    for name in ["cp_clients", "cp_notifications", "cp_investigations", "cp_placements", "cp_carers", "cp_case_workers"]:
        df = cp_tables[name]
        cols = PUBLIC_COLUMNS.get(name, [c for c in df.columns if not c.startswith("_")])
        df[cols].to_csv(os.path.join(public_dir, f"{name}.csv"), index=False)

    pop.to_csv(os.path.join(internal_dir, "population_master.csv"), index=False)
    answer_key.to_csv(os.path.join(internal_dir, "linkage_answer_key.csv"), index=False)

    return public_dir, internal_dir


def print_cross_agency_demo(answer_key, birth_reg, cp_tables, school, n=3):
    sample = answer_key.dropna(subset=["registration_number", "cp_client_id", "student_id"]).head(n)
    if sample.empty:
        print("  (no client had all three record types in this sample - try a larger --population)")
        return
    for _, row in sample.iterrows():
        b = birth_reg.loc[birth_reg["_person_uid"] == row["person_uid"]].iloc[0]
        c = cp_tables["cp_clients"].loc[cp_tables["cp_clients"]["_person_uid"] == row["person_uid"]].iloc[0]
        s = school.loc[school["_person_uid"] == row["person_uid"]].iloc[0]
        print(f"  person_uid {row['person_uid']} (internal only, never published):")
        print(f"    Registry Services / BDM  -> {b['registration_number']}: "
              f"\"{b['child_given_names']} {b['child_family_name']}\", DOB {b['date_of_birth'].date()}")
        print(f"    Child & Family Safety    -> {c['cp_client_id']}: "
              f"\"{c['given_name']} {c['family_name']}\", DOB {c['date_of_birth'].date()}")
        print(f"    Education                -> {s['student_id']}: "
              f"\"{s['given_name']} {s['family_name']}\", DOB {s['date_of_birth'].date()}")
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--population", type=int, default=200_000,
                     help="Target size of the master population (default 200,000; WA's real population is ~2.9M - see README for full-scale timing)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--case-workers", type=int, default=60)
    ap.add_argument("--dirty", choices=["none", "amber", "red"], default="none",
                     help="Seed known QA failure modes into birth_registrations/sex, "
                          "birth_registrations/place_of_birth_facility, and cp_notifications/concern_type")
    ap.add_argument("--outdir", default="output/demo")
    ap.add_argument("--demo-examples", type=int, default=3, help="How many cross-agency identity examples to print")
    args = ap.parse_args()

    print(f"Generating synthetic population (target {args.population:,}, seed={args.seed}, dirty={args.dirty})...")
    pop, cp_tables, birth_reg, school = build(args.population, args.seed, args.case_workers, args.dirty)

    answer_key = build_linkage_answer_key(cp_tables, birth_reg, school)
    public_dir, internal_dir = write_outputs(args.outdir, pop, cp_tables, birth_reg, school, answer_key)

    print(f"\nWrote public agency tables to {public_dir}/")
    print(f"Wrote master registry + linkage answer key to {internal_dir}/ (ground truth - do not distribute as test data)")

    if args.demo_examples:
        print(f"\n--- {args.demo_examples} people who appear in all three agencies, shown with their master identity resolved ---")
        print_cross_agency_demo(answer_key, birth_reg, cp_tables, school, n=args.demo_examples)


if __name__ == "__main__":
    main()
