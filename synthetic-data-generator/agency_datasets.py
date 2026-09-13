"""
Two more agency "views" of the master population, so the child-protection
subset demonstrably shows up under THREE different agencies with three
independently-presented names and three unrelated reference numbers:

  1. birth_registrations - the WHOLE population, in the same column shape
     as bdm-birth-registrations-contract.yaml (Registry Services / BDM).
  2. school_enrollment - a lightweight extract for the CP-flagged children
     only (Education) - kept small deliberately; it exists to prove the
     cross-agency linkage story, not to be a fully worked dataset itself.

Known scope simplifications (see README): registering_parent_*_name is only
populated for people whose *current* household role is "child" - adults'
own parents aren't modelled, so their birth record's parent fields are
blank. That's a real limitation of a snapshot-in-time population model, not
an oversight, and it isn't unrealistic - a lot of real historical civil-
registration data has sparse parent fields too.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from presentation import present_identity_batch
from reference.names_au import build_geo_pools

TODAY = pd.Timestamp("2026-09-13")
FACILITY_SUFFIXES = ["Community Hospital", "Birth Centre", "District Hospital", "Regional Hospital"]
PRIMARY_SCHOOL_SUFFIX = "Primary School"
SECONDARY_SCHOOL_SUFFIX = "District High School"


def _household_parent_names(population: pd.DataFrame) -> tuple[dict, dict]:
    """Two household_id -> 'Given Family' maps (first and second adult in
    the household), used as registering_parent_1/2 for that household's
    children. Vectorized - `.groupby().cumcount()` is a compiled
    aggregation, not a per-group Python callback, which is what actually
    matters at population scale (a groupby-and-iterate version of this was
    ~19s at 200k people in profiling; this is ~0.1s)."""
    adults = population.loc[population["household_role"] == "adult", ["household_id", "given_name", "family_name"]]
    adults = adults.sort_values("household_id", kind="stable")
    pos = adults.groupby("household_id").cumcount().values
    full_name = (adults["given_name"] + " " + adults["family_name"]).values
    hh_id_vals = adults["household_id"].values
    p1_map = dict(zip(hh_id_vals[pos == 0], full_name[pos == 0]))
    p2_map = dict(zip(hh_id_vals[pos == 1], full_name[pos == 1]))
    return p1_map, p2_map


def generate_birth_registrations(population: pd.DataFrame, seed: int = 55) -> pd.DataFrame:
    n = len(population)
    rng = np.random.default_rng(seed)
    suburb_names, postcodes, _, _ = build_geo_pools()

    given, family, registration_number = present_identity_batch(
        population["given_name"].values, population["family_name"].values, population["person_uid"].values,
        agency_prefix="BDM", seed=seed + 1)

    facility_idx = rng.integers(0, len(suburb_names), size=n)
    suffix_idx = rng.integers(0, len(FACILITY_SUFFIXES), size=n)
    home_birth = rng.random(n) < 0.025  # contract's documented nullable rate
    facility = np.char.add(np.char.add(suburb_names[facility_idx], " "), np.array(FACILITY_SUFFIXES)[suffix_idx])
    facility = facility.astype(object)
    facility[home_birth] = None

    date_registered = population["date_of_birth"].values + pd.to_timedelta(rng.integers(0, 10, size=n), unit="D")
    extract_timestamp = pd.to_datetime(date_registered) + pd.to_timedelta(rng.integers(1, 20, size=n), unit="h")
    is_multiple_birth = rng.random(n) < 0.032

    p1_map, p2_map = _household_parent_names(population)
    is_child = population["household_role"].values == "child"
    hh_ids = population["household_id"].values
    parent1 = pd.Series(hh_ids).map(p1_map).values
    parent2 = pd.Series(hh_ids).map(p2_map).values
    parent1 = np.where(is_child, parent1, None)
    parent2 = np.where(is_child, parent2, None)

    return pd.DataFrame({
        "registration_number": registration_number,
        "child_given_names": given,
        "child_family_name": family,
        "date_of_birth": population["date_of_birth"].values,
        "sex": population["sex"].values,
        "place_of_birth_suburb": population["suburb"].values,
        "place_of_birth_facility": facility,
        "date_registered": date_registered,
        "registering_parent_1_name": parent1,
        "registering_parent_2_name": parent2,
        "is_multiple_birth": is_multiple_birth,
        "source_system_record_id": [f"SRC-{i:09d}" for i in range(n)],
        "extract_timestamp": extract_timestamp,
        "_person_uid": population["person_uid"].values,
    })


def generate_school_enrollment(cp_clients: pd.DataFrame, seed: int = 77) -> pd.DataFrame:
    n = len(cp_clients)
    rng = np.random.default_rng(seed)
    given, family, student_id = present_identity_batch(
        cp_clients["given_name"].values, cp_clients["family_name"].values, cp_clients["_person_uid"].values,
        agency_prefix="EDU", seed=seed + 1)

    age_years = ((TODAY - cp_clients["date_of_birth"]).dt.days / 365.25).values
    year_level = np.clip(np.round(age_years - 5), 0, 12).astype(int)
    is_secondary = year_level >= 7
    school_suffix = np.where(is_secondary, SECONDARY_SCHOOL_SUFFIX, PRIMARY_SCHOOL_SUFFIX)
    school_name = np.array([f"{s} {suf}" for s, suf in zip(cp_clients["suburb"].values, school_suffix)], dtype=object)
    enrollment_date = TODAY - pd.to_timedelta(rng.integers(30, 365 * 3, size=n), unit="D")

    return pd.DataFrame({
        "student_id": student_id,
        "given_name": given,
        "family_name": family,
        "date_of_birth": cp_clients["date_of_birth"].values,
        "year_level": year_level,
        "school_name": school_name,
        "enrollment_date": enrollment_date,
        "_person_uid": cp_clients["_person_uid"].values,
    })
