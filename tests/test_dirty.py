"""Tests for generator/dirty.py's failure-injection machinery.

The first section (test_invalid_value_pools_contain_no_null_sentinel_strings
/ test_injected_invalid_suburb_values_survive_a_csv_round_trip /
test_injected_invalid_postcode_values_survive_a_csv_round_trip) is a
regression test for a real bug found while calibrating the new suburb/
postcode closed-value-set dirty presets (2026-09-14): both
_INVALID_SUBURB_POOL and _INVALID_POSTCODE_POOL originally included the
literal string "N/A" as an injected invalid value. pandas' and DuckDB's
CSV readers both recognise "N/A" as a null-sentinel string by default, so
after a write-then-read-back round trip (exactly what the real pipeline
does: dirty.py writes a CSV, then pandas/DuckDB reads it back for the
real tools) the injected "N/A" silently became an actual NULL, not the
string. That matters because dbt's accepted_values and Soda's
invalid_percent both check via a SQL `NOT IN (...)`, which evaluates to
NULL (not TRUE) for a NULL input - so the row was silently dropped from
the WHERE clause and never counted as invalid, undercounting against the
calibrated rate (confirmed live: 4 of 18 injected postcode values on one
run disappeared this way, enough to flip dbt's accepted_values result
from fail to warn - datacontract-cli's own Python-level check didn't have
this gap, so the three engines actively disagreed on the same run).
Fixed by dropping "N/A" from both pools (see dirty.py's own comments).

The rest of the file (added 2026-09-15, scoped via AskUserQuestion) is a
general test battery for the injector functions themselves - up to this
point their correctness (rate produces the right fraction, only the
intended column/rows are touched, the module's own documented "never
mutates the input" contract) had no automated coverage at all, unlike
that one specific CSV round-trip bug above; confidence came entirely from
real pipeline runs and the calibration comments scattered through
dirty.py, the same gap resupply.py had before its own 2026-09-15 fix (see
plans/qa-pipeline.md #31). Deliberately does NOT try to prove dirty.py's
presets actually exercise every check the two datasets define - that's
the separate, much bigger breadth gap logged as plans/qa-pipeline.md #27
(still [todo], not what this battery is for)."""
from __future__ import annotations

import io

import pandas as pd
import pytest

from generator import dirty

PANDAS_DEFAULT_NA_VALUES = {
    "", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan",
    "1.#IND", "1.#QNAN", "<NA>", "N/A", "NA", "NULL", "NaN", "None",
    "n/a", "nan", "null",
}


def test_invalid_value_pools_contain_no_null_sentinel_strings():
    for pool_name in ("_INVALID_SUBURB_POOL", "_INVALID_POSTCODE_POOL", "_JUNK_TEXT_POOL"):
        pool = getattr(dirty, pool_name, None)
        if pool is None:
            continue
        offenders = [v for v in pool if isinstance(v, str) and v in PANDAS_DEFAULT_NA_VALUES]
        assert not offenders, f"{pool_name} contains a null-sentinel string that a CSV round trip silently drops: {offenders}"


def test_injected_invalid_suburb_values_survive_a_csv_round_trip():
    df = pd.DataFrame({"place_of_birth_suburb": ["Perth"] * 20})
    dirty_df = dirty.inject_invalid_values(df, "place_of_birth_suburb", dirty._INVALID_SUBURB_POOL, rate=1.0, seed=1)

    csv_bytes = dirty_df.to_csv(index=False)
    round_tripped = pd.read_csv(io.StringIO(csv_bytes))

    assert round_tripped["place_of_birth_suburb"].isna().sum() == 0


def test_injected_invalid_postcode_values_survive_a_csv_round_trip():
    df = pd.DataFrame({"postcode": ["6000"] * 20})
    dirty_df = dirty.inject_invalid_values(df, "postcode", dirty._INVALID_POSTCODE_POOL, rate=1.0, seed=1)

    csv_bytes = dirty_df.to_csv(index=False)
    round_tripped = pd.read_csv(io.StringIO(csv_bytes), dtype={"postcode": str})

    assert round_tripped["postcode"].isna().sum() == 0


# --- core injector battery -------------------------------------------------
# Large-ish n so a seeded-random rate check has real statistical power
# without being so large the suite gets slow. `_approx` gives a generous
# tolerance deliberately - these tests exist to catch a real logic bug
# (rate not applied, applied twice, wrong comparison operator, wrong
# column), not to pin down dirty.py's exact calibration numbers, which
# already have their own extensive commentary in the module itself.
_N = 4000


def _approx(actual: int, expected: float, rel: float = 0.25, floor: int = 5):
    assert abs(actual - expected) <= max(floor, expected * rel), \
        f"actual={actual} too far from expected={expected} (tolerance rel={rel}, floor={floor})"


def _base_df(n: int = _N) -> pd.DataFrame:
    return pd.DataFrame({
        "sex": ["M"] * n,
        "place_of_birth_facility": [f"Facility {i % 20}" for i in range(n)],
        "source_system_record_id": [f"SRC-{i:09d}" for i in range(n)],
        "child_given_names": ["Alex"] * n,
        "date_registered": pd.to_datetime(["2026-09-01"] * n),
        "extract_timestamp": pd.to_datetime(["2026-09-01 12:00:00"] * n),
        "place_of_birth_suburb": ["Perth"] * n,
        "date_of_birth": pd.to_datetime(["2026-08-25"] * n),
        # #27 pass columns - registration_number/child_family_name/the two
        # parent-name columns/is_multiple_birth are only needed by the
        # apply_birth_registrations_presets tests further down, but living
        # here means every core-injector test above gets them for free too.
        "registration_number": [f"BDM-{i:09d}" for i in range(n)],
        "child_family_name": ["Smith"] * n,
        "registering_parent_1_name": ["Jordan Smith"] * n,
        "registering_parent_2_name": ["Alex Smith"] * n,
        "is_multiple_birth": [False] * n,
    })


CORE_INJECTOR_CALLS = [
    ("inject_nulls", lambda df: dirty.inject_nulls(df, "place_of_birth_facility", 0.3, seed=1)),
    ("inject_invalid_values", lambda df: dirty.inject_invalid_values(df, "sex", ["U", "O"], 0.3, seed=1)),
    ("inject_missing_expected_value",
     lambda df: dirty.inject_missing_expected_value(df, "sex", "M", ["F"], seed=1)),
    ("inject_duplicate_rows", lambda df: dirty.inject_duplicate_rows(df, rate=0.1, seed=1)),
    ("inject_nulls_in_subset",
     lambda df: dirty.inject_nulls_in_subset(df, "place_of_birth_facility", df["sex"] == "M", 0.3, seed=1)),
    ("inject_duplicate_values",
     lambda df: dirty.inject_duplicate_values(df, "source_system_record_id", 0.3, seed=1)),
    ("inject_out_of_range_dates",
     lambda df: dirty.inject_out_of_range_dates(df, "date_of_birth", dirty._BAD_DATE_OF_BIRTH_POOL, 0.3, seed=1)),
    ("inject_extract_timestamp_disorder",
     lambda df: dirty.inject_extract_timestamp_disorder(df, 0.3, seed=1)),
    ("truncate_rows", lambda df: dirty.truncate_rows(df, 0.3, seed=1)),
    ("truncate_to_row_count", lambda df: dirty.truncate_to_row_count(df, len(df) // 2, seed=1)),
    ("inject_stale_delivery", lambda df: dirty.inject_stale_delivery(df, seed=1, rate=1.0)),
]


@pytest.mark.parametrize("name,call", CORE_INJECTOR_CALLS, ids=[c[0] for c in CORE_INJECTOR_CALLS])
def test_core_injectors_never_mutate_their_input(name, call):
    # dirty.py's own module docstring: "Each function returns a *new*
    # DataFrame (never mutates the input)" - a real, load-bearing contract
    # for the resupply-chain code (generator/resupply.py) that calls
    # dirty() repeatedly against a shared clean lineage (see #31's fix) -
    # a mutating injector would corrupt that lineage for every later
    # attempt in the chain, not just the one that called it.
    df = _base_df(200)
    original = df.copy(deep=True)
    call(df)
    pd.testing.assert_frame_equal(df, original)


def test_inject_nulls_rate_and_column():
    df = _base_df()
    out = dirty.inject_nulls(df, "place_of_birth_facility", rate=0.3, seed=1)
    _approx(out["place_of_birth_facility"].isna().sum(), 0.3 * len(df))
    # no other column touched
    for col in df.columns.drop("place_of_birth_facility"):
        pd.testing.assert_series_equal(out[col], df[col])


def test_inject_nulls_handles_non_nullable_dtypes():
    # Regression test for a real bug found 2026-09-15 (plans/qa-
    # pipeline.md #27): a numpy bool (or int) dtype column can't natively
    # hold None, so nulling one used to raise pandas.errors.
    # LossySetitemError instead of injecting anything - first hit adding
    # is_multiple_birth (bool) as a never-nulled-before target. Every
    # prior caller happened to target an already-nullable column, so this
    # was never exercised until now.
    df = pd.DataFrame({"is_multiple_birth": [True, False] * 2000})
    out = dirty.inject_nulls(df, "is_multiple_birth", rate=0.3, seed=1)
    _approx(out["is_multiple_birth"].isna().sum(), 0.3 * len(df))
    non_null = out["is_multiple_birth"].dropna()
    assert set(non_null.unique()).issubset({True, False})


def test_inject_invalid_values_rate_and_pool_membership():
    df = _base_df()
    pool = ["U", "O", "9"]
    out = dirty.inject_invalid_values(df, "sex", pool, rate=0.3, seed=1)
    changed = out["sex"] != df["sex"]
    _approx(changed.sum(), 0.3 * len(df))
    assert set(out.loc[changed, "sex"]).issubset(set(pool))
    assert (out.loc[~changed, "sex"] == "M").all()


def test_inject_missing_expected_value_removes_every_occurrence():
    df = _base_df()
    df.loc[df.index[:1000], "sex"] = "F"  # 1000 "F", rest "M"
    out = dirty.inject_missing_expected_value(df, "sex", "F", ["X"], seed=1)
    assert (out["sex"] == "F").sum() == 0
    assert (out["sex"] == "X").sum() == 1000
    assert (out["sex"] == "M").sum() == len(df) - 1000


def test_inject_duplicate_rows_appends_exact_copies_without_near_duplicate_columns():
    df = _base_df()
    out = dirty.inject_duplicate_rows(df, rate=0.1, seed=1)
    n_dupe = int(len(df) * 0.1)
    assert len(out) == len(df) + n_dupe
    appended = out.iloc[len(df):]
    original_ids = set(df["source_system_record_id"])
    assert appended["source_system_record_id"].isin(original_ids).all()


def test_inject_duplicate_rows_perturbs_near_duplicate_columns():
    df = _base_df()
    out = dirty.inject_duplicate_rows(df, rate=1.0, seed=1, near_duplicate_columns=["source_system_record_id"])
    n_dupe = len(df)  # rate=1.0
    assert len(out) == len(df) + n_dupe
    appended_ids = out.iloc[len(df):]["source_system_record_id"]
    original_ids = set(df["source_system_record_id"])
    # ~60% of appended rows should have one character dropped from the id,
    # which (given 4000 distinct 13-char ids) essentially never collides
    # back into the original id set by chance.
    unperturbed_fraction = appended_ids.isin(original_ids).mean()
    assert 0.25 < unperturbed_fraction < 0.55, \
        f"expected ~40% of appended rows to be byte-identical copies (60% perturbed), got {unperturbed_fraction:.2f}"


def test_inject_nulls_in_subset_only_touches_eligible_rows():
    df = _base_df()
    eligible = df.index < len(df) // 2
    out = dirty.inject_nulls_in_subset(df, "place_of_birth_facility", eligible, rate=1.0, seed=1)
    assert out.loc[eligible, "place_of_birth_facility"].isna().all()
    assert (out.loc[~eligible, "place_of_birth_facility"] == df.loc[~eligible, "place_of_birth_facility"]).all()


def test_inject_duplicate_values_creates_real_duplicates_from_existing_values():
    df = _base_df()
    out = dirty.inject_duplicate_values(df, "source_system_record_id", rate=1.0, seed=1)
    # every resulting value must have existed in the original column...
    assert out["source_system_record_id"].isin(df["source_system_record_id"]).all()
    # ...and with rate=1.0 reassigning every row to a random donor, real
    # duplicate values are all but certain to appear.
    assert out["source_system_record_id"].duplicated().sum() > 0


def test_inject_out_of_range_dates_rate_and_pool_membership():
    df = _base_df()
    pool = dirty._BAD_DATE_OF_BIRTH_POOL
    out = dirty.inject_out_of_range_dates(df, "date_of_birth", pool, rate=0.3, seed=1)
    changed = out["date_of_birth"] != df["date_of_birth"]
    _approx(changed.sum(), 0.3 * len(df))
    assert set(pd.to_datetime(out.loc[changed, "date_of_birth"]).dt.date).issubset(set(pool))


def test_inject_extract_timestamp_disorder_only_shifts_affected_rows_before_registration():
    df = _base_df()
    out = dirty.inject_extract_timestamp_disorder(df, rate=0.3, seed=1)
    changed = out["extract_timestamp"] != df["extract_timestamp"]
    _approx(changed.sum(), 0.3 * len(df))
    assert (out.loc[changed, "extract_timestamp"] < out.loc[changed, "date_registered"]).all()
    assert (out.loc[~changed, "extract_timestamp"] == df.loc[~changed, "extract_timestamp"]).all()


def test_inject_stale_delivery_pushes_every_row_past_the_freshness_window_when_triggered():
    # Phase 5f (plans/qa-pipeline.md #61): rate=1.0 forces the whole-run
    # coin flip to trigger deterministically (rng.random() is always
    # strictly < 1.0), so every row should end up well past the 3
    # freshness checks' 7-day window - date_registered untouched.
    df = _base_df()
    out = dirty.inject_stale_delivery(df, seed=1, rate=1.0)
    lag_days = (pd.to_datetime(out["date_registered"]) - pd.to_datetime(out["date_of_birth"])).dt.days
    assert (lag_days > 7).all()
    assert (lag_days >= 15).all() and (lag_days <= 45).all()
    assert (out["date_registered"] == df["date_registered"]).all()


def test_inject_stale_delivery_is_a_noop_when_the_coin_flip_misses():
    # rate=0.0 guarantees the flip never triggers (rng.random() is
    # always >= 0.0) - the whole point of this being a single per-run
    # coin flip, not a per-row rate like every other injector, is that a
    # miss must leave the run entirely untouched.
    df = _base_df()
    out = dirty.inject_stale_delivery(df, seed=1, rate=0.0)
    pd.testing.assert_frame_equal(out, df)


def test_truncate_rows_drops_approximately_the_requested_fraction():
    df = _base_df()
    out = dirty.truncate_rows(df, rate=0.3, seed=1)
    _approx(len(df) - len(out), 0.3 * len(df))
    # every surviving row is a genuine original row, not a new/altered one
    assert out["source_system_record_id"].isin(df["source_system_record_id"]).all()


def test_truncate_to_row_count_hits_the_exact_target():
    df = _base_df()
    target = len(df) // 2
    out = dirty.truncate_to_row_count(df, target, seed=1)
    assert len(out) == target
    assert out["source_system_record_id"].isin(df["source_system_record_id"]).all()
    assert out["source_system_record_id"].is_unique


def test_truncate_to_row_count_is_a_noop_when_target_exceeds_length():
    df = _base_df(100)
    out = dirty.truncate_to_row_count(df, target_rows=500, seed=1)
    pd.testing.assert_frame_equal(out, df)


def test_break_multiple_birth_siblings_drops_the_expected_number_of_pairs():
    # 40 real twin pairs (matching date_of_birth/facility/parent1, exactly
    # 2 rows each) plus 20 non-twin singles the injector must leave alone.
    n_pairs = 40
    rows = []
    for i in range(n_pairs):
        for _twin in range(2):
            rows.append({
                "is_multiple_birth": True,
                "date_of_birth": pd.Timestamp("2026-08-01") + pd.Timedelta(days=i),
                "place_of_birth_facility": f"Facility {i}",
                "registering_parent_1_name": f"Parent {i}",
            })
    for i in range(20):
        rows.append({
            "is_multiple_birth": False,
            "date_of_birth": pd.Timestamp("2026-08-01") + pd.Timedelta(days=100 + i),
            "place_of_birth_facility": f"Solo Facility {i}",
            "registering_parent_1_name": f"Solo Parent {i}",
        })
    df = pd.DataFrame(rows)

    out = dirty.break_multiple_birth_siblings(df, severity="red", seed=1)  # rate=0.5
    expected_broken = int(n_pairs * 0.5)
    assert len(df) - len(out) == expected_broken

    remaining_twins = out[out["is_multiple_birth"]]
    groups = remaining_twins.groupby(
        ["date_of_birth", "place_of_birth_facility", "registering_parent_1_name"], dropna=False
    ).size()
    orphaned = (groups == 1).sum()
    intact_pairs = (groups == 2).sum()
    assert orphaned == expected_broken
    assert intact_pairs == n_pairs - expected_broken
    # non-twin rows are never touched
    assert (~out["is_multiple_birth"]).sum() == 20


def test_inject_drift_batch_never_affects_rows_before_onset():
    n = 2000
    df = pd.DataFrame({
        "sex": ["M"] * n,
        "batch_id": list(range(n)),
    })
    onset = n // 2
    out = dirty.inject_drift_batch(df, "sex", ["U"], "batch_id", onset_value=onset,
                                    rate_after_onset=0.4, seed=1)
    before = out["batch_id"] < onset
    after = ~before
    assert (out.loc[before, "sex"] == "M").all()
    changed_after = (out.loc[after, "sex"] != "M").sum()
    _approx(changed_after, 0.4 * after.sum())


# --- dataset-specific presets -----------------------------------------------
# These compose the core injectors above at calibrated rates per severity -
# tested here for the property that actually matters at this level (red is
# measurably worse than amber, and previous_row_count truncation lands
# exactly on its computed target), not by re-deriving every rate dirty.py's
# own extensive inline comments already document.

def _clean_bdm_df(n: int = 4000) -> pd.DataFrame:
    df = _base_df(n)
    # give break_multiple_birth_siblings real pairs to work with, same
    # shape as test_break_multiple_birth_siblings_drops_the_expected_number_of_pairs
    is_multi = [False] * n
    for i in range(0, 200, 2):
        is_multi[i] = is_multi[i + 1] = True
        df.loc[i, "registering_parent_1_name"] = f"Parent {i}"
        df.loc[i + 1, "registering_parent_1_name"] = f"Parent {i}"
        df.loc[i + 1, "date_of_birth"] = df.loc[i, "date_of_birth"]
        df.loc[i + 1, "place_of_birth_facility"] = df.loc[i, "place_of_birth_facility"]
    df.loc[df.index[200:], "registering_parent_1_name"] = [f"Solo {i}" for i in range(n - 200)]
    df["is_multiple_birth"] = is_multi
    return df


def test_birth_registrations_preset_red_is_worse_than_amber():
    df = _clean_bdm_df()
    amber = dirty.apply_birth_registrations_presets(df, severity="amber", seed=1)
    red = dirty.apply_birth_registrations_presets(df, severity="red", seed=1)

    amber_facility_null_rate = amber["place_of_birth_facility"].isna().mean()
    red_facility_null_rate = red["place_of_birth_facility"].isna().mean()
    assert red_facility_null_rate > amber_facility_null_rate

    amber_invalid_sex = (~amber["sex"].isin(["M", "F"])).sum()
    red_invalid_sex = (~red["sex"].isin(["M", "F"])).sum()
    assert red_invalid_sex > amber_invalid_sex


def test_birth_registrations_preset_truncates_to_exact_band_target():
    # No multi-birth pairs here (unlike _clean_bdm_df) - isolates
    # truncation as the ONLY row-count-changing step in the preset.
    # break_multiple_birth_siblings also drops rows when real twin pairs
    # exist (see test_birth_registrations_preset_red_is_worse_than_amber),
    # so with pairs present the final count is the truncation target minus
    # however many more pairs it breaks - not testable as an exact number
    # without re-deriving that step's own randomness here too.
    df = _base_df()
    df["is_multiple_birth"] = False
    df["registering_parent_1_name"] = [f"Parent {i}" for i in range(len(df))]

    amber = dirty.apply_birth_registrations_presets(df, severity="amber", seed=1, previous_row_count=4000)
    red = dirty.apply_birth_registrations_presets(df, severity="red", seed=1, previous_row_count=4000)
    assert len(amber) == int(4000 * (1 - 0.18))
    assert len(red) == int(4000 * (1 - 0.35))


def _cp_clients_df(n: int = 2000) -> pd.DataFrame:
    return pd.DataFrame({
        "cp_client_id": [f"CPS-{i:09d}" for i in range(n)],
        "given_name": ["Alex"] * n,
        "family_name": ["Smith"] * n,
        "date_of_birth": pd.to_datetime(["2020-01-01"] * n),
        "sex": ["M"] * n,
        "suburb": ["Perth"] * n,
        "postcode": ["6000"] * n,
        "case_opened_date": pd.to_datetime(["2024-01-01"] * n),
        "case_status": ["Open"] * n,
    })


def _cp_case_workers_df(n: int = 60) -> pd.DataFrame:
    return pd.DataFrame({"worker_id": [f"CPS-STAFF-{i:05d}" for i in range(n)]})


def test_cp_notifications_preset_red_is_worse_than_amber():
    n = 2000
    clients_df = _cp_clients_df()
    workers_df = _cp_case_workers_df()
    df = pd.DataFrame({
        "notification_id": [f"NOTIF-{i:06d}" for i in range(n)],
        "cp_client_id": clients_df["cp_client_id"].values[:n],
        "assigned_worker_id": workers_df["worker_id"].sample(n, replace=True, random_state=1).values,
        "concern_type": ["Neglect"] * n,
        "source_type": ["School"] * n,
        "risk_rating": ["Low"] * n,
        "outcome": ["No further action"] * n,
    })
    amber = dirty.apply_cp_notifications_presets(df, clients_df, workers_df, severity="amber", seed=1)
    red = dirty.apply_cp_notifications_presets(df, clients_df, workers_df, severity="red", seed=1)

    amber_invalid = (~amber["concern_type"].isin(["Neglect"])).sum()
    red_invalid = (~red["concern_type"].isin(["Neglect"])).sum()
    assert red_invalid > amber_invalid
    # duplicate_rows appends rows, so red (higher dup rate) ends up longer
    assert len(red) > len(amber) >= n

    # #27 pass: nulls, invalid values, and dangling FKs all worse in red
    for col in ("cp_client_id", "assigned_worker_id"):
        assert amber[col].isna().sum() < red[col].isna().sum()
    for col in ("source_type", "risk_rating", "outcome"):
        original = {"source_type": "School", "risk_rating": "Low", "outcome": "No further action"}[col]
        assert (amber[col] != original).sum() < (red[col] != original).sum()
    client_ids = set(clients_df["cp_client_id"])
    worker_ids = set(workers_df["worker_id"])
    amber_dangling = amber["cp_client_id"].notna() & ~amber["cp_client_id"].isin(client_ids)
    red_dangling = red["cp_client_id"].notna() & ~red["cp_client_id"].isin(client_ids)
    assert amber_dangling.sum() < red_dangling.sum()
    amber_dangling_w = amber["assigned_worker_id"].notna() & ~amber["assigned_worker_id"].isin(worker_ids)
    red_dangling_w = red["assigned_worker_id"].notna() & ~red["assigned_worker_id"].isin(worker_ids)
    assert amber_dangling_w.sum() < red_dangling_w.sum()


def test_cp_placements_preset_reassigns_only_to_non_approved_carers():
    n = 2000
    clients_df = _cp_clients_df()
    placements_df = pd.DataFrame({
        "placement_id": [f"PLACE-{i:06d}" for i in range(n)],
        "cp_client_id": clients_df["cp_client_id"].values[:n],
        "carer_id": ["CARER-APPROVED"] * n,
        "placement_type": ["Kinship care"] * n,
        "placement_start": pd.to_datetime(["2024-01-01"] * n),
        "placement_suburb": ["Perth"] * n,
    })
    carers_df = pd.DataFrame({
        "carer_id": ["CARER-APPROVED", "CARER-PENDING", "CARER-SUSPENDED"],
        "approval_status": ["Approved", "Pending", "Suspended"],
    })
    amber = dirty.apply_cp_placements_presets(placements_df, carers_df, clients_df, severity="amber", seed=1)
    red = dirty.apply_cp_placements_presets(placements_df, carers_df, clients_df, severity="red", seed=1)

    non_approved = {"CARER-PENDING", "CARER-SUSPENDED"}
    amber_reassigned = amber["carer_id"].isin(non_approved).sum()
    red_reassigned = red["carer_id"].isin(non_approved).sum()
    assert red_reassigned > amber_reassigned > 0
    # a still-real (business-rule-violating) carer_id, or nulled, or a
    # genuine dangling value - never anything else
    carer_ids = set(carers_df["carer_id"])
    for out in (amber, red):
        assert (out["carer_id"].isna() | out["carer_id"].isin(carer_ids) | ~out["carer_id"].isin(carer_ids)).all()

    # #27 pass: nulls, invalid placement_type, and dangling cp_client_id/carer_id all worse in red
    for col in ("cp_client_id", "placement_start", "placement_suburb"):
        assert amber[col].isna().sum() < red[col].isna().sum()
    assert (amber["placement_type"] != "Kinship care").sum() < (red["placement_type"] != "Kinship care").sum()
    client_ids = set(clients_df["cp_client_id"])
    amber_dangling_c = amber["cp_client_id"].notna() & ~amber["cp_client_id"].isin(client_ids)
    red_dangling_c = red["cp_client_id"].notna() & ~red["cp_client_id"].isin(client_ids)
    assert amber_dangling_c.sum() < red_dangling_c.sum()


def test_cp_clients_preset_red_is_worse_than_amber():
    df = _cp_clients_df()
    amber = dirty.apply_cp_clients_presets(df, severity="amber", seed=1)
    red = dirty.apply_cp_clients_presets(df, severity="red", seed=1)

    amber_bad_postcode = (amber["postcode"] != "6000").sum()
    red_bad_postcode = (red["postcode"] != "6000").sum()
    assert red_bad_postcode > amber_bad_postcode

    amber_bad_dob = (amber["date_of_birth"] != df["date_of_birth"]).sum()
    red_bad_dob = (red["date_of_birth"] != df["date_of_birth"]).sum()
    assert red_bad_dob > amber_bad_dob

    # #27 pass: nulls, cp_client_id duplication, invalid sex all worse in red
    for col in ("given_name", "family_name", "date_of_birth", "suburb", "case_opened_date"):
        assert amber[col].isna().sum() < red[col].isna().sum()
    assert amber["cp_client_id"].duplicated().sum() < red["cp_client_id"].duplicated().sum()
    assert (~amber["sex"].isin(["M", "F", "X"])).sum() < (~red["sex"].isin(["M", "F", "X"])).sum()


def test_cp_investigations_preset_only_reopens_closed_case_investigations():
    n = 1000
    workers_df = _cp_case_workers_df()
    notifications_df = pd.DataFrame({"notification_id": [f"NOTIF-{i:06d}" for i in range(n)]})
    investigations_df = pd.DataFrame({
        "investigation_id": [f"INV-{i:06d}" for i in range(n)],
        "notification_id": notifications_df["notification_id"].values,
        "cp_client_id": [f"CLIENT-{i % 200:04d}" for i in range(n)],
        "start_date": pd.to_datetime(["2025-01-01"] * n),
        "end_date": pd.to_datetime(["2026-01-01"] * n),
        "lead_worker_id": workers_df["worker_id"].sample(n, replace=True, random_state=1).values,
    })
    # half the clients are Closed, half Open
    clients_df = pd.DataFrame({
        "cp_client_id": [f"CLIENT-{i:04d}" for i in range(200)],
        "case_status": ["Closed" if i < 100 else "Open" for i in range(200)],
    })
    closed_ids = set(clients_df.loc[clients_df["case_status"] == "Closed", "cp_client_id"])

    out = dirty.apply_cp_investigations_presets(
        investigations_df, clients_df, notifications_df, workers_df, severity="red", seed=1)  # rate=0.10
    reopened = out["end_date"].isna()

    assert reopened.sum() > 0
    assert out.loc[reopened, "cp_client_id"].isin(closed_ids).all(), \
        "a reopened (end_date nulled) investigation belongs to a client whose case isn't Closed"
    # never touches investigations belonging to an Open-case client's end_date
    open_ids = set(clients_df.loc[clients_df["case_status"] == "Open", "cp_client_id"])
    assert not out.loc[out["cp_client_id"].isin(open_ids), "end_date"].isna().any()

    # #27 pass: nulls, investigation_id duplication, and dangling FKs
    amber = dirty.apply_cp_investigations_presets(
        investigations_df, clients_df, notifications_df, workers_df, severity="amber", seed=1)
    for col in ("start_date", "lead_worker_id"):
        assert amber[col].isna().sum() < out[col].isna().sum()
    assert amber["investigation_id"].duplicated().sum() < out["investigation_id"].duplicated().sum()
    notif_ids = set(notifications_df["notification_id"])
    client_ids = set(clients_df["cp_client_id"])
    worker_ids = set(workers_df["worker_id"])
    amber_dangling = (
        (amber["notification_id"].notna() & ~amber["notification_id"].isin(notif_ids)).sum()
        + (amber["cp_client_id"].notna() & ~amber["cp_client_id"].isin(client_ids)).sum()
        + (amber["lead_worker_id"].notna() & ~amber["lead_worker_id"].isin(worker_ids)).sum()
    )
    red_dangling = (
        (out["notification_id"].notna() & ~out["notification_id"].isin(notif_ids)).sum()
        + (out["cp_client_id"].notna() & ~out["cp_client_id"].isin(client_ids)).sum()
        + (out["lead_worker_id"].notna() & ~out["lead_worker_id"].isin(worker_ids)).sum()
    )
    assert amber_dangling < red_dangling


def test_cp_carers_and_case_workers_presets_duplicate_their_pk():
    carers_df = pd.DataFrame({"carer_id": [f"CARER-{i:06d}" for i in range(2000)]})
    amber = dirty.apply_cp_carers_presets(carers_df, severity="amber", seed=1)
    red = dirty.apply_cp_carers_presets(carers_df, severity="red", seed=1)
    assert amber["carer_id"].duplicated().sum() < red["carer_id"].duplicated().sum()
    assert amber["carer_id"].isin(carers_df["carer_id"]).all()

    workers_df = pd.DataFrame({"worker_id": [f"CPS-STAFF-{i:05d}" for i in range(300)]})
    amber_w = dirty.apply_cp_case_workers_presets(workers_df, severity="amber", seed=1)
    red_w = dirty.apply_cp_case_workers_presets(workers_df, severity="red", seed=1)
    assert amber_w["worker_id"].duplicated().sum() < red_w["worker_id"].duplicated().sum()
    assert amber_w["worker_id"].isin(workers_df["worker_id"]).all()


def test_inject_dangling_foreign_key_never_collides_with_existing_ids():
    existing = {f"CARER-{i:06d}" for i in range(2000)}
    df = pd.DataFrame({"carer_id": list(existing)})
    out = dirty.inject_dangling_foreign_key(df, "carer_id", seed=1, rate=0.3, id_format="CARER-{:06d}",
                                             existing_ids=existing, id_max=1_000_000)
    changed = out["carer_id"] != df["carer_id"]
    _approx(changed.sum(), 0.3 * len(df))
    assert not out.loc[changed, "carer_id"].isin(existing).any(), \
        "an injected dangling value collided with a real existing_id"
    assert (out.loc[~changed, "carer_id"] == df.loc[~changed, "carer_id"]).all()


def test_inject_dangling_foreign_key_never_mutates_its_input():
    existing = {f"CARER-{i:06d}" for i in range(200)}
    df = pd.DataFrame({"carer_id": list(existing)})
    original = df.copy(deep=True)
    dirty.inject_dangling_foreign_key(df, "carer_id", seed=1, rate=0.3, id_format="CARER-{:06d}",
                                       existing_ids=existing, id_max=1_000_000)
    pd.testing.assert_frame_equal(df, original)
