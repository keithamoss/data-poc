"""`mothman population --dirty`'s failure-injection presets, at LITERAL
per-row rates (REQ-GEN-392 criterion 9; QC, Keith 2026-11-14).

WHY HERE AND NOT generator/dirty.py. generator/dirty.py's presets derive
each fault's size from the bands of the checks it aims at, read through the
selected asset's check files (REQ-GEN-392). The population generator runs
with NO ASSET SELECTED and dirties both assets' tables in one process, and
its output is recorded nowhere - it is exploratory. So it keeps the rates
the presets carried before REQ-GEN-392, as exploratory defaults, and reads no
asset's bands. REJECTED: reading both assets' bands (a third exception to
REQ-PIPE-342 criterion 8), and requiring one asset.

The injectors themselves are generator/dirty.py's, imported rather than
copied (plans/qa-pipeline.md #17's dual-dirty.py bug). These two functions
are today's presets as they stood on 2026-11-15, the rates and comments
unchanged; the band each rate was once calibrated to is in its comment, and
nothing holds it there - which is acceptable only because nothing reads this
output as a QA history.
"""
from __future__ import annotations

import pandas as pd

from generator import dirty


def apply_birth_registrations_presets(df: pd.DataFrame, severity: str, seed: int,
                                       previous_row_count: int | None = None) -> pd.DataFrame:
    """severity: 'amber' or 'red' - matches the warn/fail bands in
    bdm-birth-registrations-soda-checks.yml exactly, so a QA run against
    this output should land in the band you asked for. Covers all of the
    checks this dataset's QA battery has calibrated presets for - the
    original 2 (sex, place_of_birth_facility), the next battery
    (source_system_record_id duplicates, child_given_names format junk,
    extract_timestamp ordering, multiple-birth sibling records, and the
    row-count-growth check's truncation scenario), and the plans/qa-
    pipeline.md #27 pass (2026-09-15, Keith's call): nulls on every
    previously-never-nulled required column, a duplicate-value injector
    for registration_number itself (the PK - previously never touched at
    all), and junk-format invalid values for child_family_name/
    registering_parent_1_name/registering_parent_2_name/source_system_
    record_id (previously only child_given_names ever got this
    treatment). BDM has no foreign keys to any other table, so unlike
    Child Protection's presets below, there's no dangling-FK category
    here at all.

    previous_row_count: the immediately preceding run's actual row count
    (civil_registration.py tracks this across its own loop) - when given, this
    run gets truncated down to a specific percentage below THAT number
    (10-25% for amber, past 25% for red - matching the row-count-growth
    check's own warn/fail bands) rather than a fixed self-referential
    rate, since that check compares against the previous run specifically
    and this dataset's own base row count already varies enough run to
    run that a fixed rate wouldn't reliably land in either band. None
    (the very first run, which has no previous run to under-cut) skips
    truncation entirely."""
    # applied FIRST, not last: every rate below is calibrated against this
    # run's FINAL row count (including dbt's own absolute-count thresholds
    # for sex/place_of_birth_facility, not just the percentage-based Soda/
    # datacontract-cli checks) - truncating afterwards would dilute those
    # absolute counts by the same fraction as the truncation itself,
    # pushing e.g. place_of_birth_facility's red-run null count below
    # dbt's error_if ">600" and silently downgrading fail to warn. Found
    # live: truncating last dropped that exact count from 769 to 526.
    if previous_row_count:
        drop_frac = 0.18 if severity == "amber" else 0.35  # warn>10%, fail>25% vs. previous run
        target = int(previous_row_count * (1 - drop_frac))
        df = dirty.truncate_to_row_count(df, target, seed + 6)

    # facility-null and sex rates are bumped up from this dataset's
    # original (pre-truncation) calibration specifically so their ABSOLUTE
    # counts still clear dbt's fixed thresholds (facility: warn_if ">300",
    # error_if ">600"; sex: error_if ">30") against a run that may now be
    # 18-35% smaller than before truncation existed - the PERCENTAGE-based
    # Soda/datacontract-cli checks land in the same bands either way.
    rate_sex = 0.008 if severity == "amber" else 0.035      # warn>0%, fail>2% (Soda); >0/>30 count (dbt)
    rate_facility_null = 0.30 if severity == "amber" else 0.55  # warn>15%, fail>35% (Soda); >300/>600 count (dbt)
    rate_dup_id = 0.004 if severity == "amber" else 0.02
    rate_junk_name = 0.006 if severity == "amber" else 0.03   # warn>0%, fail>3%
    rate_ts_disorder = 0.01 if severity == "amber" else 0.04
    rate_suburb = 0.006 if severity == "amber" else 0.03      # warn>0%, fail>3% (same band as junk names)
    # small counts on purpose - the ODCS date-range rule is single-tier
    # (mustBe: 0/error, no amber tolerance at all), so even the amber rate
    # is a genuine hard fail on this one check - kept small so it reads as
    # "a few genuinely bad records slipped through", not as the dominant
    # failure mode of an amber run.
    rate_dob_range = 0.003 if severity == "amber" else 0.015

    # #27 pass: never-nulled required columns - dbt's not_null tests on
    # all 6 of these have no warn_if/error_if config, so they hard-fail
    # on ANY null regardless of severity (the same single-tier situation
    # item 30 already found for date_of_birth) - only Soda's count-based
    # missing_count bands (warn>0/fail>5, where one exists) actually read
    # amber vs. red differently. Rates are small on purpose: these are
    # "a handful of records missing a required field", not a dominant
    # failure mode.
    rate_null_required = 0.0016 if severity == "amber" else 0.0063   # ~3 amber / ~12 red at n~1900
    rate_null_minor = 0.001 if severity == "amber" else 0.004        # ~2 amber / ~8 red - columns with no Soda missing_count band at all (source_system_record_id, is_multiple_birth), kept small regardless
    # #27 pass: registration_number - the PK itself, never touched by any
    # preset before this. Same rate as source_system_record_id's existing
    # duplicate-value injector above (a proven calibration for this same
    # check shape at this dataset's size).
    rate_dup_registration_number = rate_dup_id
    # #27 pass: junk-format invalid values on the 3 name columns that
    # never got this treatment (only child_given_names did) - same rate
    # as child_given_names' own rate_junk_name, same check shape (Soda
    # invalid_percent warn>0%/fail>3%, dbt matches_regex single-tier).
    rate_junk_name_other = rate_junk_name
    # source_system_record_id's OWN format check has a tighter Soda band
    # (warn>0%/fail>1%, vs. 3% for the name columns above) - smaller rate.
    rate_malformed_src_id = 0.003 if severity == "amber" else 0.02    # ~0.3% amber / ~2% red

    df = dirty.inject_invalid_values(df, "sex", ["U", "O", "9"], rate_sex, seed)
    df = dirty.inject_nulls(df, "place_of_birth_facility", rate_facility_null, seed + 1)
    df = dirty.inject_duplicate_values(df, "source_system_record_id", rate_dup_id, seed + 2)
    df = dirty.inject_invalid_values(df, "child_given_names", dirty._JUNK_TEXT_POOL, rate_junk_name, seed + 3)
    df = dirty.inject_extract_timestamp_disorder(df, rate_ts_disorder, seed + 4)
    df = dirty.break_multiple_birth_siblings(df, 0.15 if severity == "amber" else 0.5, seed + 5)
    df = dirty.inject_invalid_values(df, "place_of_birth_suburb", dirty._INVALID_SUBURB_POOL, rate_suburb, seed + 7)
    df = dirty.inject_out_of_range_dates(df, "date_of_birth", dirty._BAD_DATE_OF_BIRTH_POOL, rate_dob_range, seed + 8)
    df = dirty.inject_nulls(df, "date_of_birth", rate_null_required, seed + 9)
    df = dirty.inject_nulls(df, "date_registered", rate_null_required, seed + 10)
    df = dirty.inject_nulls(df, "is_multiple_birth", rate_null_minor, seed + 11)
    df = dirty.inject_nulls(df, "extract_timestamp", rate_null_required, seed + 12)
    df = dirty.inject_nulls(df, "source_system_record_id", rate_null_minor, seed + 13)
    df = dirty.inject_nulls(df, "registration_number", rate_null_required, seed + 14)
    df = dirty.inject_duplicate_values(df, "registration_number", rate_dup_registration_number, seed + 15)
    df = dirty.inject_invalid_values(df, "child_family_name", dirty._JUNK_TEXT_POOL, rate_junk_name_other, seed + 16)
    df = dirty.inject_invalid_values(df, "registering_parent_1_name", dirty._JUNK_TEXT_POOL, rate_junk_name_other, seed + 17)
    df = dirty.inject_invalid_values(df, "registering_parent_2_name", dirty._JUNK_TEXT_POOL, rate_junk_name_other, seed + 18)
    df = dirty.inject_invalid_values(df, "source_system_record_id", dirty._MALFORMED_SRC_ID_POOL, rate_malformed_src_id, seed + 19)
    return df


def apply_cp_notifications_presets(df: pd.DataFrame, clients_df: pd.DataFrame, workers_df: pd.DataFrame,
                                    severity: str, seed: int) -> pd.DataFrame:
    """Introduces an unknown concern_type code (an 'expected values are
    stable, but something new showed up' scenario) plus near-duplicate
    notifications (double-submission).

    plans/qa-pipeline.md #27 pass (2026-09-15): adds not_null on cp_
    client_id/assigned_worker_id (previously never nulled), invalid-value
    injection on source_type/risk_rating/outcome (real checks, never
    exercised), and - the new category this pass adds across all of CP -
    genuine dangling-FK injection on cp_client_id/assigned_worker_id:
    reassigns a fraction to an ID that doesn't exist in cp_clients/
    cp_case_workers at all, not just a still-real row that fails a
    business rule (see inject_dangling_foreign_key's own docstring for
    why this is a different failure mode from everything else in this
    module). `clients_df`/`workers_df` are the REAL (undirtied) parent
    tables the caller passes in specifically to build each dangling
    injector's `existing_ids` exclusion set from - see child_protection.py.
    py's main() for why it passes base_tables here, not this run's own
    (possibly already-dirtied-elsewhere) copies."""
    rate = 0.01 if severity == "amber" else 0.05
    rate_null = 0.003 if severity == "amber" else 0.012  # ~3 amber / ~12 red at n~987 - Soda missing_count warn>0/fail>5
    rate_invalid = 0.008 if severity == "amber" else 0.045  # ~8 amber / ~44 red - Soda warn>0%/fail>3%, dbt error_if>30 (n~987, 3%~30)
    # ~3 amber / ~10 red directly-injected, though the REAL observed
    # count often runs higher: cp_clients' own cp_client_id duplicate-
    # value injector (apply_cp_clients_presets) can incidentally make a
    # real ID vanish from that run's own materialized cp_clients table
    # (donor-overwrite, not removal - see inject_duplicate_values), which
    # makes every notification still referencing that now-gone ID
    # genuinely dangling too, on top of this injector's own direct
    # count (confirmed live: 12 direct + ~21 incidental = 33 on a real
    # red run). Doesn't matter for pass/fail here - both relationships/
    # reference checks are single-tier (any violation fails) - just
    # means the reported failing-row count is a real, honest number
    # larger than this rate alone would suggest.
    rate_dangling = 0.003 if severity == "amber" else 0.01

    df = dirty.inject_invalid_values(df, "concern_type", ["Unspecified", "Pending classification", "Code 9"], rate, seed)
    df = dirty.inject_duplicate_rows(df, rate=0.015 if severity == "amber" else 0.05, seed=seed + 1,
                                near_duplicate_columns=["notification_id"])
    df = dirty.inject_nulls(df, "cp_client_id", rate_null, seed + 2)
    df = dirty.inject_nulls(df, "assigned_worker_id", rate_null, seed + 3)
    df = dirty.inject_invalid_values(df, "source_type", ["Court", "Media report", "Unknown"], rate_invalid, seed + 4)
    df = dirty.inject_invalid_values(df, "risk_rating", ["Severe", "Unrated", "TBC"], rate_invalid, seed + 5)
    df = dirty.inject_invalid_values(df, "outcome", ["Pending review", "Escalated externally"], rate_invalid, seed + 6)
    df = dirty.inject_dangling_foreign_key(df, "cp_client_id", seed + 7, rate_dangling,
                                      "CPS-{:09d}", clients_df["cp_client_id"], id_max=1_000_000_000)
    df = dirty.inject_dangling_foreign_key(df, "assigned_worker_id", seed + 8, rate_dangling,
                                      "CPS-STAFF-{:05d}", workers_df["worker_id"], id_max=100_000)
    return df
