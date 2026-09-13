"""
The Child Protection Casework collection: six related tables drawn from the
subset of the master population flagged `has_child_protection_history`.

This is the "within-collection referential integrity" half of the brief -
cp_notifications -> cp_investigations -> cp_placements -> cp_carers all
carry real foreign keys back to cp_clients, exactly like a real casework
system's schema. The "same person, multiple agencies" half is handled by
generate.py, which also emits this same flagged child into the BDM birth
registrations table and a school-enrollment extract, each under its own
agency-minted ID and its own (independently) presented name spelling.

Category value sets below (concern_type, risk_rating, placement_type, ...)
are exactly the kind of closed-value-set column the QA pipeline's
traffic-light checks are built to watch - see dirty.py and the "Traffic-
light thresholds" section of the main report for how this ties back to it.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from presentation import present_identity_batch

TODAY = pd.Timestamp("2026-09-13")

CONCERN_TYPES = ["Neglect", "Physical abuse", "Emotional abuse", "Sexual abuse",
                  "Domestic violence exposure", "Parental substance use", "Parental mental health concern"]
CONCERN_WEIGHTS = [0.34, 0.12, 0.22, 0.04, 0.16, 0.08, 0.04]
RISK_RATINGS = ["Low", "Medium", "High", "Critical"]
RISK_WEIGHTS = [0.38, 0.34, 0.21, 0.07]
SOURCE_TYPES = ["School", "Police", "Health service", "Family member", "Neighbour", "Anonymous", "Self-report"]
SOURCE_WEIGHTS = [0.27, 0.18, 0.15, 0.14, 0.10, 0.11, 0.05]
NOTIFICATION_OUTCOMES = ["No further action", "Referred to family support", "Investigation opened"]
PLACEMENT_TYPES = ["Kinship care", "Foster care", "Residential care", "Family group home"]
PLACEMENT_WEIGHTS = [0.46, 0.34, 0.09, 0.11]
CARER_TYPES = ["Kinship", "Foster", "Residential-staff"]

WORKER_TEAMS = ["Metro North", "Metro South", "Metro East", "South West", "Great Southern",
                "Goldfields", "Kimberley", "Pilbara", "Wheatbelt", "Midwest-Gascoyne"]


def _rng(seed, salt):
    return np.random.default_rng(seed * 1_000_003 + salt)


def generate_case_workers(n_workers: int, seed: int) -> pd.DataFrame:
    rng = _rng(seed, 1)
    from reference.names_au import build_name_pools
    names = build_name_pools()
    sex = rng.choice(["M", "F"], size=n_workers, p=[0.32, 0.68])  # child-protection workforce skews female
    given_out = np.empty(n_workers, dtype=object)
    for sx, key in (("M", "male"), ("F", "female")):
        mask = sex == sx
        pool, w = names[key]
        given_out[mask] = rng.choice(pool, size=mask.sum(), p=w)
    fam_pool, fam_w = names["family"]
    family = rng.choice(fam_pool, size=n_workers, p=fam_w)
    worker_id = np.array([f"CPS-STAFF-{i:05d}" for i in range(n_workers)])
    team = rng.choice(WORKER_TEAMS, size=n_workers)
    return pd.DataFrame({
        "worker_id": worker_id, "given_name": given_out, "family_name": family, "team_region": team,
    })


def generate_child_protection_collection(population: pd.DataFrame, seed: int = 101,
                                          n_case_workers: int = 60) -> dict[str, pd.DataFrame]:
    """population: the full master registry (from population.py). Returns a
    dict of table_name -> DataFrame for the whole collection."""
    from reference.names_au import build_geo_pools
    suburb_names, postcodes, street_stems, street_types = build_geo_pools()

    flagged = population[population["has_child_protection_history"]].reset_index(drop=True)
    n = len(flagged)
    if n == 0:
        raise ValueError("no children flagged has_child_protection_history in this population sample - "
                          "try a larger --population (the flag rate is ~2.2% of children).")

    rng = _rng(seed, 2)

    # --- cp_clients ------------------------------------------------------
    given, family, cp_client_id = present_identity_batch(
        flagged["given_name"].values, flagged["family_name"].values, flagged["person_uid"].values,
        agency_prefix="CPS", seed=seed + 1)
    opened_lag_days = rng.integers(30, 365 * 4, size=n)
    opened_date = TODAY - pd.to_timedelta(np.minimum(opened_lag_days, (TODAY - flagged["date_of_birth"]).dt.days.values), unit="D")
    # Drawn here (not assigned yet) so every later draw from `rng` keeps
    # the exact same stream position/values as before this column existed
    # - only overridden further down, once cp_investigations exists: a
    # case can only become Closed once none of its investigations are
    # still open (closing a case with an active investigation would itself
    # be the "closed-case investigation hygiene" violation the QA
    # pipeline's business rule checks for - see that section below).
    case_status_candidate = rng.choice(["Open", "Closed"], size=n, p=[0.42, 0.58])

    cp_clients = pd.DataFrame({
        "cp_client_id": cp_client_id,
        "given_name": given, "family_name": family,
        "date_of_birth": flagged["date_of_birth"].values,
        "sex": flagged["sex"].values,
        "suburb": flagged["suburb"].values, "postcode": flagged["postcode"].values,
        "case_opened_date": opened_date,
        "_person_uid": flagged["person_uid"].values,   # internal join key only - see README
        "_household_id": flagged["household_id"].values,
    })

    # --- case workers ------------------------------------------------------
    workers = generate_case_workers(n_case_workers, seed)

    # --- cp_notifications (1-4 per client, more for higher-risk histories) --
    n_notifs_per_client = rng.choice([1, 2, 3, 4], size=n, p=[0.46, 0.30, 0.16, 0.08])
    notif_client_idx = np.repeat(np.arange(n), n_notifs_per_client)
    n_notifs = len(notif_client_idx)
    notif_rng = _rng(seed, 3)
    base_open = cp_clients["case_opened_date"].values[notif_client_idx]
    # notifications cluster in the weeks around case open (an earlier one is
    # often what opens the case; later ones are follow-ups on the same case)
    notif_date = pd.to_datetime(base_open) + pd.to_timedelta(notif_rng.integers(-14, 60, size=n_notifs), unit="D")
    notification_id = np.array([f"NOTIF-{i:08d}" for i in range(n_notifs)])
    concern_type = notif_rng.choice(CONCERN_TYPES, size=n_notifs, p=CONCERN_WEIGHTS)
    risk_rating = notif_rng.choice(RISK_RATINGS, size=n_notifs, p=RISK_WEIGHTS)
    source_type = notif_rng.choice(SOURCE_TYPES, size=n_notifs, p=SOURCE_WEIGHTS)
    outcome = notif_rng.choice(NOTIFICATION_OUTCOMES, size=n_notifs, p=[0.52, 0.30, 0.18])
    assigned_worker = notif_rng.choice(workers["worker_id"].values, size=n_notifs)

    cp_notifications = pd.DataFrame({
        "notification_id": notification_id,
        "cp_client_id": cp_clients["cp_client_id"].values[notif_client_idx],
        "notification_date": notif_date,
        "source_type": source_type,
        "concern_type": concern_type,
        "risk_rating": risk_rating,
        "assigned_worker_id": assigned_worker,
        "outcome": outcome,
    })

    # --- cp_investigations (only for notifications whose outcome escalated) -
    inv_mask = cp_notifications["outcome"].values == "Investigation opened"
    inv_src = cp_notifications.loc[inv_mask]
    n_inv = len(inv_src)
    inv_rng = _rng(seed, 4)
    investigation_id = np.array([f"INV-{i:08d}" for i in range(n_inv)])
    start_date = inv_src["notification_date"].values + pd.to_timedelta(inv_rng.integers(1, 14, size=n_inv), unit="D")
    duration = inv_rng.integers(14, 120, size=n_inv)
    end_date = start_date + pd.to_timedelta(duration, unit="D")
    still_open = inv_rng.random(n_inv) < 0.12
    end_date = pd.Series(end_date).where(~still_open, pd.NaT)
    substantiated = inv_rng.choice(["Substantiated", "Not substantiated", "Inconclusive"], size=n_inv, p=[0.41, 0.38, 0.21])
    lead_worker = inv_rng.choice(workers["worker_id"].values, size=n_inv)

    cp_investigations = pd.DataFrame({
        "investigation_id": investigation_id,
        "notification_id": inv_src["notification_id"].values,
        "cp_client_id": inv_src["cp_client_id"].values,
        "start_date": start_date,
        "end_date": end_date.values,
        "substantiated": substantiated,
        "lead_worker_id": lead_worker,
    })

    # --- case_status (deferred from the cp_clients block above, using the
    #     candidate values drawn there so no later draw from `rng` shifts):
    #     a client can only be Closed once none of their own investigations
    #     are still open. Clients with no investigation at all (most of
    #     them - only notifications with outcome 'Investigation opened'
    #     produce one) are unconstrained and just get the random draw.
    #     This is what makes the "closed-case investigation hygiene"
    #     business rule pass cleanly by construction on every clean run -
    #     dirty.py's apply_cp_investigations_presets (amber/red only) is
    #     what reintroduces a controlled number of violations. -----------
    clients_with_open_investigation = set(
        cp_investigations.loc[cp_investigations["end_date"].isna(), "cp_client_id"])
    case_status = np.where(
        np.isin(cp_client_id, list(clients_with_open_investigation)), "Open", case_status_candidate)
    cp_clients["case_status"] = case_status

    # --- cp_carers (kinship carers reuse a relative from the same household;
    #     foster/residential carers are unrelated people) --------------------
    carer_rng = _rng(seed, 5)
    # placements need carers to exist first - build a carer pool sized to plausible demand
    n_carers = max(20, int(n * 0.55))
    carer_type = carer_rng.choice(CARER_TYPES, size=n_carers, p=[0.40, 0.42, 0.18])
    from reference.names_au import build_name_pools
    names = build_name_pools()
    carer_sex = carer_rng.choice(["M", "F"], size=n_carers, p=[0.38, 0.62])
    carer_given = np.empty(n_carers, dtype=object)
    for sx, key in (("M", "male"), ("F", "female")):
        mask = carer_sex == sx
        pool, w = names[key]
        carer_given[mask] = carer_rng.choice(pool, size=mask.sum(), p=w)
    fam_pool, fam_w = names["family"]
    carer_family = carer_rng.choice(fam_pool, size=n_carers, p=fam_w)
    carer_id = np.array([f"CARER-{i:06d}" for i in range(n_carers)])
    approval_status = carer_rng.choice(["Approved", "Provisional", "Under review"], size=n_carers, p=[0.78, 0.14, 0.08])
    cp_carers = pd.DataFrame({
        "carer_id": carer_id, "given_name": carer_given, "family_name": carer_family,
        "carer_type": carer_type, "approval_status": approval_status,
    })

    # --- cp_placements (0-2 per client; only a subset of clients have any) --
    has_placement = carer_rng.random(n) < 0.40
    n_place_per_client = np.where(has_placement, carer_rng.choice([1, 2], size=n, p=[0.72, 0.28]), 0)
    place_client_idx = np.repeat(np.arange(n), n_place_per_client)
    n_place = len(place_client_idx)
    place_rng = _rng(seed, 6)
    placement_id = np.array([f"PLACE-{i:07d}" for i in range(n_place)])
    placement_type = place_rng.choice(PLACEMENT_TYPES, size=n_place, p=PLACEMENT_WEIGHTS)
    placement_start = pd.to_datetime(cp_clients["case_opened_date"].values[place_client_idx]) \
                       + pd.to_timedelta(place_rng.integers(5, 200, size=n_place), unit="D")
    place_duration = place_rng.integers(10, 900, size=n_place)
    placement_end = placement_start + pd.to_timedelta(place_duration, unit="D")
    ongoing = place_rng.random(n_place) < 0.22
    placement_end = pd.Series(placement_end).where(~ongoing, pd.NaT)
    # Only Approved carers are used for a placement by construction - this
    # is what makes the "placement/carer approval compliance" business
    # rule pass cleanly on every clean run. dirty.py's
    # apply_cp_placements_presets (amber/red only) is what reintroduces a
    # controlled number of violations.
    approved_carer_ids = cp_carers.loc[cp_carers["approval_status"] == "Approved", "carer_id"].values
    carer_for_placement = place_rng.choice(approved_carer_ids, size=n_place)
    place_suburb_idx = place_rng.integers(0, len(suburb_names), size=n_place)

    cp_placements = pd.DataFrame({
        "placement_id": placement_id,
        "cp_client_id": cp_clients["cp_client_id"].values[place_client_idx],
        "placement_type": placement_type,
        "carer_id": carer_for_placement,
        "placement_start": placement_start,
        "placement_end": placement_end.values,
        "placement_suburb": suburb_names[place_suburb_idx],
    })

    return {
        "cp_clients": cp_clients,
        "cp_notifications": cp_notifications,
        "cp_investigations": cp_investigations,
        "cp_placements": cp_placements,
        "cp_carers": cp_carers,
        "cp_case_workers": workers,
    }
