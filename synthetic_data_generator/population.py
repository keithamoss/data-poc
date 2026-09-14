"""
The master synthetic population registry.

This is the "shared spine" every agency-dataset generator draws from, so
that a single fake person can appear - consistently, at their true
attributes - across multiple agencies' datasets. It is never itself
"the output": nothing downstream should ship person_uid or these exact
field values verbatim. Downstream generators call `present_identity()`
(see presentation.py) to project a master record into an agency-specific,
realistically-imperfect view before writing it out.

Fully vectorized (numpy/pandas) so it scales to population-scale row
counts without a Python-level per-person loop - the only per-household-
TEMPLATE loop is over the 6 household templates below, not over
households or people. See README.md for the scaling story and the
chunked/streaming generation this feeds into (generate.py).

Known simplifications (documented rather than engineered around, since
this is illustrative test data, not a demographic model):
  - adult age and "has children" are correlated only loosely; a small
    share of parent/child age gaps will be tighter than 18 years.
  - everyone in a household shares one current address; address history
    and out-of-home-care placement overrides are layered on top by
    child_protection.py, not modelled here.
  - mortality is an age-band probability curve, not an actuarial table.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from generator.names_au import build_name_pools, build_geo_pools

TODAY = pd.Timestamp("2026-09-13")

# (role sequence per household) -> weight. "adult"/"child" only; sex assigned separately.
HOUSEHOLD_TEMPLATES = [
    (("adult",), 0.28),                          # single adult, no children
    (("adult", "adult"), 0.24),                  # couple, no children
    (("adult", "child"), 0.09),                  # single parent, 1 child
    (("adult", "child", "child"), 0.05),         # single parent, 2 children
    (("adult", "adult", "child"), 0.13),         # couple, 1 child
    (("adult", "adult", "child", "child"), 0.15),# couple, 2 children
    (("adult", "adult", "child", "child", "child"), 0.06),  # couple, 3 children
]

def _age_years(dob, at=TODAY):
    return ((at - dob).dt.days / 365.25)

def generate_population(n_people_target: int, seed: int = 42) -> pd.DataFrame:
    """Return a DataFrame of ~n_people_target synthetic people (exact count
    rounds down to a whole number of households, so it may land a handful
    under target)."""
    rng = np.random.default_rng(seed)
    names = build_name_pools()
    suburb_names, postcodes, street_stems, street_types = build_geo_pools()

    templates = [t[0] for t in HOUSEHOLD_TEMPLATES]
    weights = np.array([t[1] for t in HOUSEHOLD_TEMPLATES])
    weights = weights / weights.sum()
    avg_size = sum(len(t) * w for t, w in zip(templates, weights))
    n_households_guess = int(np.ceil(n_people_target / avg_size)) + 50  # small buffer

    template_idx = rng.choice(len(templates), size=n_households_guess, p=weights)
    sizes = np.array([len(templates[i]) for i in template_idx])
    cum = np.cumsum(sizes)
    # keep whole households only, up to the target
    keep = np.searchsorted(cum, n_people_target, side="right") + 1
    keep = min(keep, n_households_guess)
    template_idx = template_idx[:keep]
    sizes = sizes[:keep]
    n_households = keep
    household_id = np.arange(n_households)

    # --- bucket households by template (only len(templates) python-level
    #     iterations, however many millions of households there are) -----
    person_household_id = []
    person_role = []
    for t_i, template in enumerate(templates):
        mask = template_idx == t_i
        count = mask.sum()
        if count == 0:
            continue
        hh_ids = household_id[mask]
        L = len(template)
        person_household_id.append(np.repeat(hh_ids, L))
        person_role.append(np.tile(np.array(template), count))
    person_household_id = np.concatenate(person_household_id)
    person_role = np.concatenate(person_role)
    n_people = len(person_household_id)

    df = pd.DataFrame({
        "person_uid": np.arange(n_people, dtype=np.int64),
        "household_id": person_household_id,
        "household_role": person_role,
    })

    # --- sex: independent per person (allows same-sex couples & non-binary) ---
    df["sex"] = rng.choice(["M", "F", "X"], size=n_people, p=[0.492, 0.492, 0.016])

    # --- ages: adults first (household-level, broadcast to members), then children ---
    is_adult = df["household_role"].values == "adult"
    # vectorized "does this household contain a child" - a compiled groupby
    # aggregation ('max' on a boolean), not a per-group Python callback,
    # which is what actually matters at population scale (a lambda-based
    # .transform() here was the dominant cost at 300k+ rows in profiling).
    is_child_bool = pd.Series(df["household_role"].values == "child")
    has_child_in_hh = is_child_bool.groupby(df["household_id"].values).transform("max").values
    adult_age_mean = np.where(has_child_in_hh, 38, 48)
    adult_age_sd = np.where(has_child_in_hh, 8, 17)
    adult_ages = rng.normal(adult_age_mean, adult_age_sd)
    adult_ages = np.clip(adult_ages, 20, 92)
    child_ages = np.clip(rng.uniform(0, 17.99, size=n_people), 0, 17.99)
    age_years = np.where(is_adult, adult_ages, child_ages)
    dob_days_ago = (age_years * 365.25).astype(int)
    df["date_of_birth"] = TODAY - pd.to_timedelta(dob_days_ago, unit="D")

    # --- names ---
    def draw_names(sex_arr):
        out = np.empty(len(sex_arr), dtype=object)
        for sx, pool_key in (("M", "male"), ("F", "female"), ("X", "unisex")):
            mask = sex_arr == sx
            pool, w = names[pool_key]
            out[mask] = rng.choice(pool, size=mask.sum(), p=w)
        return out
    df["given_name"] = draw_names(df["sex"].values)

    fam_pool, fam_w = names["family"]
    household_surname = rng.choice(fam_pool, size=n_households, p=fam_w)
    df["family_name"] = household_surname[df["household_id"].values]
    # ~8% of children carry a different surname (blended family); ~22% of the
    # *second* adult listed in a couple keeps a surname independent of the
    # household's registered one (unmarried / kept-name couples).
    child_mask = df["household_role"].values == "child"
    override = rng.random(n_people) < np.where(child_mask, 0.08, 0.0)
    second_adult_mask = is_adult & (df.groupby("household_id").cumcount().values == 1)
    override |= second_adult_mask & (rng.random(n_people) < 0.22)
    n_override = override.sum()
    if n_override:
        df.loc[override, "family_name"] = rng.choice(fam_pool, size=n_override, p=fam_w)

    # --- household address (shared by all current members) ---
    suburb_idx = rng.integers(0, len(suburb_names), size=n_households)
    street_num = rng.integers(1, 240, size=n_households)
    stem_idx = rng.integers(0, len(street_stems), size=n_households)
    type_idx = rng.integers(0, len(street_types), size=n_households)
    hh_suburb = suburb_names[suburb_idx]
    hh_postcode = postcodes[suburb_idx]
    hh_street = np.char.add(np.char.add(street_num.astype(str), " "),
                             np.char.add(np.char.add(street_stems[stem_idx], " "), street_types[type_idx]))
    df["suburb"] = hh_suburb[df["household_id"].values]
    df["postcode"] = hh_postcode[df["household_id"].values]
    df["street_address"] = hh_street[df["household_id"].values]

    # --- mortality: age-band probability, vectorized ---
    age_arr = age_years
    p_deceased = np.clip((age_arr - 55) / 45, 0, 1) ** 2 * 0.55 + 0.0015
    df["is_deceased"] = rng.random(n_people) < p_deceased
    dod_lag_days = rng.integers(1, np.maximum(dob_days_ago, 2))
    df["date_of_death"] = pd.NaT
    dec_mask = df["is_deceased"].values
    df.loc[dec_mask, "date_of_death"] = TODAY - pd.to_timedelta(dob_days_ago[dec_mask] - dod_lag_days[dec_mask], unit="D")

    # --- child protection history flag: a small share of children (kept as
    #     a lifelong historical flag - it does not "expire" at 18) ---
    is_child_now = (age_years < 18) & (~df["is_deceased"].values)
    cp_prob = np.where(is_child_now, 0.022, 0.0)
    df["has_child_protection_history"] = rng.random(n_people) < cp_prob

    return df.reset_index(drop=True)


if __name__ == "__main__":
    import time
    t0 = time.time()
    pop = generate_population(50_000, seed=7)
    print(f"generated {len(pop):,} people in {time.time()-t0:.2f}s")
    print(pop.head(8).to_string())
    print("\nage distribution (years):")
    print(_age_years(pop["date_of_birth"]).describe())
    print("\nhousehold size distribution:")
    print(pop.groupby("household_id").size().value_counts().sort_index())
    print("\nsex distribution:\n", pop["sex"].value_counts(normalize=True))
    print("\ndeceased rate:", pop["is_deceased"].mean())
    print("child-protection-history rate among children:",
          pop.loc[_age_years(pop["date_of_birth"])<18, "has_child_protection_history"].mean())
