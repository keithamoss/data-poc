"""
Generates ONE day's birth-registration extract - a fresh batch of newborn
registrations, in the exact column shape of
contract/bdm-birth-registrations-contract.yaml.

This is deliberately a different generation model from the
synthetic-data-generator repo's population.py: that module builds a
whole-population snapshot (households, mixed ages, mortality) as the
shared spine for cross-agency identity linkage. A birth-registrations feed
is an EVENT FLOW, not a population snapshot - each daily file is a fresh
cohort of newborns, so this module generates that cohort directly rather
than trying to bend the household/population model to produce it. It reuses
the same reference name/geo pools and presentation/dirty-injection modules
(copied from that repo) for consistency and to avoid re-deriving them.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import date, timedelta

from names_au import build_name_pools, build_geo_pools
from presentation import present_identity_batch

FACILITY_SUFFIXES = ["Community Hospital", "Birth Centre", "District Hospital", "Regional Hospital"]


def generate_daily_batch(run_date: date, seed: int, n_rows: int, id_offset: int = 0) -> pd.DataFrame:
    """id_offset: added to the per-row counter used to mint registration_number/
    source_system_record_id, so IDs stay globally unique across multiple
    runs generated in the same pipeline (each run passes a different,
    non-overlapping offset - see generate_runs.py)."""
    rng = np.random.default_rng(seed)
    names = build_name_pools()
    suburb_names, postcodes, _, _ = build_geo_pools()
    n = n_rows

    sex = rng.choice(["M", "F", "X"], size=n, p=[0.492, 0.492, 0.016])
    given = np.empty(n, dtype=object)
    for sx, key in (("M", "male"), ("F", "female"), ("X", "unisex")):
        mask = sex == sx
        pool, w = names[key]
        given[mask] = rng.choice(pool, size=mask.sum(), p=w)
    fam_pool, fam_w = names["family"]
    family = rng.choice(fam_pool, size=n, p=fam_w)

    # this run's registrations cluster on run_date (i.e. date_registered == run_date);
    # date_of_birth precedes it by the usual few-day registration lag.
    reg_lag_days = rng.integers(0, 10, size=n)
    date_registered = np.array([run_date] * n, dtype=object)
    date_of_birth = np.array([run_date - timedelta(days=int(d)) for d in reg_lag_days], dtype=object)

    person_seq = np.arange(id_offset, id_offset + n)
    given_p, family_p, registration_number = present_identity_batch(
        given, family, person_seq, agency_prefix="BDM", seed=seed + 1)
    _, _, source_system_record_id = present_identity_batch(
        given, family, person_seq, agency_prefix="SRC", seed=seed + 2)

    facility_idx = rng.integers(0, len(suburb_names), size=n)
    suffix_idx = rng.integers(0, len(FACILITY_SUFFIXES), size=n)
    home_birth = rng.random(n) < 0.025
    facility = np.char.add(np.char.add(suburb_names[facility_idx], " "), np.array(FACILITY_SUFFIXES)[suffix_idx])
    facility = facility.astype(object)
    facility[home_birth] = None
    suburb = suburb_names[facility_idx]

    # parents - drawn independently (this is an event-flow generator, not a
    # household model, so parents aren't linked to any other table here)
    p1_given = np.empty(n, dtype=object)
    p1_sex = rng.choice(["M", "F"], size=n, p=[0.35, 0.65])
    for sx, key in (("M", "male"), ("F", "female")):
        mask = p1_sex == sx
        pool, w = names[key]
        p1_given[mask] = rng.choice(pool, size=mask.sum(), p=w)
    parent1_name = np.char.add(np.char.add(p1_given.astype(str), " "), family.astype(str)).astype(object)
    parent1_null = rng.random(n) < 0.02
    parent1_name[parent1_null] = None

    has_parent2 = rng.random(n) >= 0.276  # ~27.6% single-registration rate
    p2_given = np.empty(n, dtype=object)
    p2_sex = rng.choice(["M", "F"], size=n, p=[0.65, 0.35])
    for sx, key in (("M", "male"), ("F", "female")):
        mask = p2_sex == sx
        pool, w = names[key]
        p2_given[mask] = rng.choice(pool, size=mask.sum(), p=w)
    p2_family = rng.choice(fam_pool, size=n, p=fam_w)  # not always the same surname as parent1
    parent2_name = np.where(has_parent2,
                              np.char.add(np.char.add(p2_given.astype(str), " "), p2_family.astype(str)),
                              None)

    is_multiple_birth = rng.random(n) < 0.032
    extract_timestamp = pd.to_datetime(date_registered) + pd.to_timedelta(rng.integers(1, 20, size=n), unit="h")

    return pd.DataFrame({
        "registration_number": registration_number,
        "child_given_names": given_p,
        "child_family_name": family_p,
        "date_of_birth": pd.to_datetime(date_of_birth),
        "sex": sex,
        "place_of_birth_suburb": suburb,
        "place_of_birth_facility": facility,
        "date_registered": pd.to_datetime(date_registered),
        "registering_parent_1_name": parent1_name,
        "registering_parent_2_name": parent2_name,
        "is_multiple_birth": is_multiple_birth,
        "source_system_record_id": source_system_record_id,
        "extract_timestamp": extract_timestamp,
    })
