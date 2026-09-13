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

    extract_timestamp = pd.to_datetime(date_registered) + pd.to_timedelta(rng.integers(1, 20, size=n), unit="h")

    # twin_rate of rows below become the FIRST twin of a real sibling pair
    # (a second row is appended for each, below) - previously is_multiple_
    # birth was an independent random flag with no sibling row backing it
    # at all, so a "does a multiple-birth record have a matching sibling"
    # check would fail on every single flagged row, on every run, by
    # construction - the same "generator doesn't enforce the invariant"
    # gap already found and fixed for two Child Protection business rules
    # (see plans/qa-pipeline.md #9). ~half the previous 3.2% flat rate,
    # since each twin pair now contributes 2 flagged rows for every 1
    # chosen here - keeps the overall is_multiple_birth rate close to what
    # it was.
    twin_rate = 0.016
    is_multiple_birth = rng.random(n) < twin_rate
    twin_idx = np.where(is_multiple_birth)[0]

    base = pd.DataFrame({
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

    if len(twin_idx) == 0:
        return base

    # Sibling rows: same birth event (date_of_birth, facility/suburb,
    # date_registered, both parents), each its own registration with a
    # freshly drawn name/sex/IDs - real twins aren't identical rows, just
    # rows that share the event they were born into. person_seq for
    # siblings continues straight after the base batch's own range (still
    # well inside this run's id_offset block - see generate_runs.py's
    # ID_BLOCK), so registration_number/source_system_record_id stay
    # globally unique.
    n_sib = len(twin_idx)
    sib_seq = np.arange(id_offset + n, id_offset + n + n_sib)
    sib_sex = rng.choice(["M", "F", "X"], size=n_sib, p=[0.492, 0.492, 0.016])
    sib_given_raw = np.empty(n_sib, dtype=object)
    for sx, key in (("M", "male"), ("F", "female"), ("X", "unisex")):
        mask = sib_sex == sx
        pool, w = names[key]
        sib_given_raw[mask] = rng.choice(pool, size=mask.sum(), p=w)
    sib_family_raw = base["child_family_name"].values[twin_idx]  # same surname as the twin they're paired with

    sib_given_p, sib_family_p, sib_registration_number = present_identity_batch(
        sib_given_raw, sib_family_raw, sib_seq, agency_prefix="BDM", seed=seed + 3)
    _, _, sib_source_system_record_id = present_identity_batch(
        sib_given_raw, sib_family_raw, sib_seq, agency_prefix="SRC", seed=seed + 4)

    sibling = pd.DataFrame({
        "registration_number": sib_registration_number,
        "child_given_names": sib_given_p,
        "child_family_name": sib_family_p,
        "date_of_birth": base["date_of_birth"].values[twin_idx],
        "sex": sib_sex,
        "place_of_birth_suburb": base["place_of_birth_suburb"].values[twin_idx],
        "place_of_birth_facility": base["place_of_birth_facility"].values[twin_idx],
        "date_registered": base["date_registered"].values[twin_idx],
        "registering_parent_1_name": base["registering_parent_1_name"].values[twin_idx],
        "registering_parent_2_name": base["registering_parent_2_name"].values[twin_idx],
        "is_multiple_birth": True,
        "source_system_record_id": sib_source_system_record_id,
        "extract_timestamp": base["extract_timestamp"].values[twin_idx],
    })

    return pd.concat([base, sibling], ignore_index=True)
