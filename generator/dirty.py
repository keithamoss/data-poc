"""
Configurable failure injection - deliberately broken records, applied on
top of an otherwise-clean generated dataset, so the QA pipeline built
earlier in this project (the Soda checks, the quarantine script, the
traffic-light dashboard) has real failures to catch instead of a
permanently-green demo.

This is intentionally a separate, later step from presentation.py's name
variation: that module models *expected* cross-system differences that a
healthy pipeline should tolerate; this module models genuine data quality
DEFECTS that the checks are supposed to flag. Keeping them apart means you
can generate realistic-but-clean data, or realistic-and-broken data,
independently of each other.

Each function returns a *new* DataFrame (never mutates the input) and takes
its own seed, so injecting failures is reproducible and composable - call
several of these in a row to build up a specific scenario.
"""
from __future__ import annotations
from datetime import date

import numpy as np
import pandas as pd


def inject_nulls(df: pd.DataFrame, column: str, rate: float, seed: int) -> pd.DataFrame:
    """Set `rate` of `column`'s values to null. Use this for the "null-rate
    creep" failure mode - e.g. bump place_of_birth_facility's null rate past
    its warn/fail thresholds to see the dataset-level rollup turn amber/red."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    mask = rng.random(len(out)) < rate
    out.loc[mask, column] = None
    return out


def inject_invalid_values(df: pd.DataFrame, column: str, invalid_pool: list, rate: float, seed: int) -> pd.DataFrame:
    """Overwrite `rate` of `column` with values drawn from `invalid_pool` -
    codes outside the column's documented valid-value set. This is the
    mechanism behind sex's `invalid_percent` check, and also behind the
    "has a new, unknown value appeared in a fixed-value-set column"
    scenario discussed earlier for concern_type/risk_rating-style columns."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    mask = rng.random(len(out)) < rate
    n = mask.sum()
    if n:
        out.loc[mask, column] = rng.choice(invalid_pool, size=n)
    return out


def inject_missing_expected_value(df: pd.DataFrame, column: str, value_to_suppress, replacement_pool: list,
                                    seed: int) -> pd.DataFrame:
    """The mirror image of inject_invalid_values: makes a previously-common,
    expected value silently STOP appearing (every existing occurrence of
    `value_to_suppress` is replaced with something else) - the "has an
    expected value disappeared" drift scenario, rather than "has a new
    value appeared"."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    mask = out[column] == value_to_suppress
    n = mask.sum()
    if n:
        out.loc[mask, column] = rng.choice(replacement_pool, size=n)
    return out


def inject_duplicate_rows(df: pd.DataFrame, rate: float, seed: int, near_duplicate_columns: list | None = None) -> pd.DataFrame:
    """Append near-duplicates of `rate` of the rows - e.g. a case worker
    double-submitting the same notification, or an upstream re-extract
    landing the same records twice. If near_duplicate_columns is given, a
    single character in one of those (string) columns is perturbed so the
    duplicate isn't byte-identical (closer to how real double-submission
    noise actually looks) - this exercises the `duplicateCheck` /
    uniqueness rule from the ODCS contract, not a trivial exact-copy case."""
    rng = np.random.default_rng(seed)
    n_dupe = int(len(df) * rate)
    if n_dupe == 0:
        return df.copy()
    sample = df.sample(n=n_dupe, random_state=seed).copy()
    if near_duplicate_columns:
        for col in near_duplicate_columns:
            if col not in sample.columns:
                continue
            vals = sample[col].astype(str).values.copy()
            for i in range(len(vals)):
                s = vals[i]
                if len(s) > 2 and rng.random() < 0.6:
                    j = rng.integers(1, len(s) - 1)
                    vals[i] = s[:j] + s[j + 1:]  # drop one character
            sample[col] = vals
    return pd.concat([df, sample], ignore_index=True)


def inject_nulls_in_subset(df: pd.DataFrame, column: str, eligible_mask, rate: float, seed: int) -> pd.DataFrame:
    """Like inject_nulls, but the null-injection candidates are only ever
    sampled from rows where `eligible_mask` is True - e.g. only
    investigations belonging to a Closed-case client are eligible to be
    "reopened" by this injector, matching a real process lapse (a case
    closed just before its investigation was actually finished) rather
    than corrupting an arbitrary, unrelated row."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    eligible_idx = out.index[eligible_mask]
    if len(eligible_idx) == 0 or rate == 0:
        return out
    mask = rng.random(len(eligible_idx)) < rate
    chosen = eligible_idx[mask]
    out.loc[chosen, column] = None
    return out


def inject_duplicate_values(df: pd.DataFrame, column: str, rate: float, seed: int) -> pd.DataFrame:
    """Overwrites `rate` of `column`'s values with another existing value
    from the same column - creates real, exact duplicate values (a source
    system accidentally reusing an ID) without touching any other column
    or duplicating a whole row, unlike inject_duplicate_rows' whole-record
    re-extract scenario."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    n = len(out)
    mask = rng.random(n) < rate
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return out
    donor_idx = rng.integers(0, n, size=len(idx))
    col_loc = out.columns.get_loc(column)
    out.iloc[idx, col_loc] = out.iloc[donor_idx][column].values
    return out


def inject_out_of_range_dates(df: pd.DataFrame, column: str, bad_date_pool: list, rate: float, seed: int) -> pd.DataFrame:
    """Overwrites `rate` of `column` with a date drawn from `bad_date_pool`
    (each one implausibly old - "before civil registration existed"
    territory, not just "unusual") - a type/format problem upstream
    producing a nonsensical date rather than a missing one. Deliberately
    kept to genuinely out-of-range but still-parseable dates: a literally
    unparseable string would silently downgrade the WHOLE column's
    inferred type for that run (confirmed empirically - DuckDB's
    read_csv_auto infers per-file, not per-row), corrupting every other
    check on the column too - flagged as a real follow-up, not built this
    round (see plans/qa-pipeline.md)."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    mask = rng.random(len(out)) < rate
    n = mask.sum()
    if n:
        out.loc[mask, column] = rng.choice(bad_date_pool, size=n)
    return out


def inject_extract_timestamp_disorder(df: pd.DataFrame, rate: float, seed: int) -> pd.DataFrame:
    """Shifts a fraction of extract_timestamp values to before their own
    row's date_registered - a clock-skew or backfill bug at the source,
    the scenario extract_timestamp's ordering/latency check is built to
    catch."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    mask = rng.random(len(out)) < rate
    n = int(mask.sum())
    if n == 0:
        return out
    shift = pd.to_timedelta(rng.integers(1, 5, size=n), unit="h")
    out.loc[mask, "extract_timestamp"] = pd.to_datetime(out.loc[mask, "date_registered"]) - shift
    return out


def truncate_rows(df: pd.DataFrame, rate: float, seed: int) -> pd.DataFrame:
    """Drops `rate` of rows entirely - a truncated or partially-failed
    extract, the scenario the real-tools row-count-growth check (and the
    ODCS contract's own rowCount mustBeBetween rule) are built to catch.
    Unlike every other injector in this module, this changes the ROW COUNT
    itself rather than corrupting values within existing rows."""
    rng = np.random.default_rng(seed)
    keep_mask = rng.random(len(df)) >= rate
    return df.loc[keep_mask].reset_index(drop=True)


def truncate_to_row_count(df: pd.DataFrame, target_rows: int, seed: int) -> pd.DataFrame:
    """Like truncate_rows, but calibrated against an absolute target row
    count rather than a self-referential rate - used for the row-count-
    growth check specifically, since that check compares against the
    PREVIOUS run's actual row count, and this dataset's own base row count
    already varies run to run (see generate_runs.py's RUN_PLAN) enough
    that a fixed drop-rate from THIS run's own count doesn't reliably land
    a specific percentage below whatever the previous run happened to be."""
    if target_rows >= len(df):
        return df.copy()
    rng = np.random.default_rng(seed)
    keep_idx = np.sort(rng.choice(len(df), size=target_rows, replace=False))
    return df.iloc[keep_idx].reset_index(drop=True)


def break_multiple_birth_siblings(df: pd.DataFrame, severity: str, seed: int) -> pd.DataFrame:
    """Drops one row from a fraction of real multiple-birth sibling pairs
    (daily_batch.py now generates genuine pairs - same date_of_birth,
    facility, and parent 1 - for every is_multiple_birth row) - the
    remaining twin's is_multiple_birth=True flag is left with no sibling
    row to match, the "one twin's registration never arrived" failure
    mode the sibling-match check is built to catch."""
    rate = 0.15 if severity == "amber" else 0.5
    rng = np.random.default_rng(seed)
    out = df.copy()
    twins = out[out["is_multiple_birth"]]
    groups = twins.groupby(
        ["date_of_birth", "place_of_birth_facility", "registering_parent_1_name"], dropna=False
    ).groups
    pairs = [idx for idx in groups.values() if len(idx) >= 2]
    n_break = int(len(pairs) * rate)
    if n_break == 0:
        return out
    chosen = rng.choice(len(pairs), size=n_break, replace=False)
    drop_idx = [pairs[i][0] for i in chosen]
    return out.drop(index=drop_idx).reset_index(drop=True)


def inject_drift_batch(df: pd.DataFrame, column: str, invalid_pool: list, batch_column: str,
                        onset_value, rate_after_onset: float, seed: int) -> pd.DataFrame:
    """Failure rate is 0 before `onset_value` in `batch_column` (e.g. a
    notification_date or extract batch id) and jumps to `rate_after_onset`
    from that point on - a step-change drift, as opposed to inject_invalid_
    values' flat rate across the whole dataset. Models "the source system
    changed on this date and every record after it is affected"."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    affected = out[batch_column] >= onset_value
    mask = affected & (rng.random(len(out)) < rate_after_onset)
    n = mask.sum()
    if n:
        out.loc[mask, column] = rng.choice(invalid_pool, size=n)
    return out


# --- ready-made presets tied to the checks already defined elsewhere in
#     this project (bdm-birth-registrations-soda-checks.yml, the CP concern
#     type / risk rating value sets) - apply with apply_dirty_presets(). ---
# Each value here contains a digit or a symbol outside a name's normal
# letters/period/space/hyphen alphabet - deliberately, so every one of
# them trips the name-format checks (contract/Soda/dbt regex has no
# lookahead support on DuckDB's RE2 engine, so it can only catch "outside
# the allowed character set", not "is a specific junk word" - see the
# contract's own comment on this).
# Deliberately no "N/A" here (a pre-existing gap this session's own
# _INVALID_SUBURB_POOL/_INVALID_POSTCODE_POOL null-sentinel bug also had -
# see those pools' comments below): the contract's own invalidValues
# description names "N/A" as this check's headline example of "a form
# submitted incomplete", but pandas'/DuckDB's CSV readers treat "N/A" as
# a null-sentinel string by default, so it would never actually reach the
# pattern check at all - it'd silently become a real NULL first and only
# ever be caught by the separate nullValues completeness check instead,
# contradicting the contract's own description of what this check catches.
_JUNK_TEXT_POOL = ["TEST1", "UNKNOWN9", "XXXX0", "Baby1", "N.A."]

# Plausible-looking but not-a-real-WA-suburb values - a mix of a common
# misspelling, a placeholder, and an out-of-jurisdiction-sounding entry -
# for place_of_birth_suburb's closed-value-set check (converted from a
# character-set regex - see plans/qa-pipeline.md #15's aggregate-invalid-
# values follow-up and the ODCS contract's matching rule for why).
#
# Deliberately NOT "N/A" (or "NA"/"NULL"/etc.) - a real bug, found live
# while verifying this preset's calibration: pandas' and DuckDB's CSV
# readers both treat "N/A" as a null-sentinel string by default, so an
# injected "N/A" silently becomes an actual NULL on read-back, not the
# literal string. That changes which check semantics apply: a SQL `NOT
# IN (...)` (dbt's accepted_values, Soda's invalid_percent) evaluates to
# NULL - not TRUE - for a NULL value, so the row is silently excluded
# from the WHERE clause and never counted as invalid at all, undercounting
# against the calibrated rate (confirmed: 4 of 18 injected postcode
# values disappeared this way, enough to flip a run from fail to warn -
# see _INVALID_POSTCODE_POOL below, which had the same bug). datacontract-
# cli's own Python-level check doesn't have this gap (it treats null as
# failing a validValues rule), so the three engines disagreed - not a
# real data-quality signal, just this injection choice colliding with a
# CSV-format-level null sentinel.
_INVALID_SUBURB_POOL = ["Freemantle", "Unknown", "TBC", "Perth Metro", "Not stated"]

# Out-of-range date_of_birth values - implausibly old (long before civil
# registration existed), not just "unusual" - see
# contract/bdm-birth-registrations-contract.yaml's matching type: sql rule
# (previously never actually exercised - nothing in this file injected a
# bad date_of_birth at all).
_BAD_DATE_OF_BIRTH_POOL = [date(1899, 1, 1), date(1850, 6, 15), date(1820, 11, 30), date(1750, 1, 1)]


def apply_birth_registrations_presets(df: pd.DataFrame, severity: str, seed: int,
                                       previous_row_count: int | None = None) -> pd.DataFrame:
    """severity: 'amber' or 'red' - matches the warn/fail bands in
    bdm-birth-registrations-soda-checks.yml exactly, so a QA run against
    this output should land in the band you asked for. Covers all of the
    checks this dataset's QA battery has calibrated presets for - the
    original 2 (sex, place_of_birth_facility) plus the newer battery
    (source_system_record_id duplicates, child_given_names format junk,
    extract_timestamp ordering, multiple-birth sibling records, and the
    row-count-growth check's truncation scenario).

    previous_row_count: the immediately preceding run's actual row count
    (generate_runs.py tracks this across its own loop) - when given, this
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
        df = truncate_to_row_count(df, target, seed + 6)

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

    df = inject_invalid_values(df, "sex", ["U", "O", "9"], rate_sex, seed)
    df = inject_nulls(df, "place_of_birth_facility", rate_facility_null, seed + 1)
    df = inject_duplicate_values(df, "source_system_record_id", rate_dup_id, seed + 2)
    df = inject_invalid_values(df, "child_given_names", _JUNK_TEXT_POOL, rate_junk_name, seed + 3)
    df = inject_extract_timestamp_disorder(df, rate_ts_disorder, seed + 4)
    df = break_multiple_birth_siblings(df, severity, seed + 5)
    df = inject_invalid_values(df, "place_of_birth_suburb", _INVALID_SUBURB_POOL, rate_suburb, seed + 7)
    df = inject_out_of_range_dates(df, "date_of_birth", _BAD_DATE_OF_BIRTH_POOL, rate_dob_range, seed + 8)
    return df


def apply_cp_notifications_presets(df: pd.DataFrame, severity: str, seed: int) -> pd.DataFrame:
    """Introduces an unknown concern_type code (an 'expected values are
    stable, but something new showed up' scenario) plus near-duplicate
    notifications (double-submission)."""
    rate = 0.01 if severity == "amber" else 0.05
    df = inject_invalid_values(df, "concern_type", ["Unspecified", "Pending classification", "Code 9"], rate, seed)
    df = inject_duplicate_rows(df, rate=0.015 if severity == "amber" else 0.05, seed=seed + 1,
                                near_duplicate_columns=["notification_id"])
    return df


def apply_cp_placements_presets(placements_df: pd.DataFrame, carers_df: pd.DataFrame,
                                 severity: str, seed: int) -> pd.DataFrame:
    """Reassigns a fraction of placements to a non-Approved carer - a real
    compliance lapse the placement/carer approval business rule
    (contract/child-protection-contract.yaml, dbt_project/tests/
    placement_carer_approval.sql) is built to catch. child_protection.py
    only ever assigns Approved carers by construction, so every violation
    on a run this preset touches is this preset's doing, not baseline
    noise - unlike the pre-fix generator, where the rule always failed.
    Reuses inject_invalid_values: a non-approved carer_id is still a
    structurally valid FK (a real cp_carers row), just one the business
    rule says shouldn't be used - the same "replace with values from a
    pool" mechanism, a different kind of pool."""
    rate = 0.02 if severity == "amber" else 0.08
    non_approved = carers_df.loc[carers_df["approval_status"] != "Approved", "carer_id"].values
    return inject_invalid_values(placements_df, "carer_id", list(non_approved), rate, seed)


# Not a real WA postcode from generator/names_au.py's SUBURBS pool - a mix
# of an obviously-placeholder value and out-of-range-looking numbers, for
# cp_clients.postcode's new closed-value-set check (previously had no
# invalid-value check at all - see plans/qa-pipeline.md #15).
#
# Deliberately NOT "N/A" - see _INVALID_SUBURB_POOL's comment above for
# the null-sentinel bug this pool originally had too (found via the same
# calibration check, on this same pool).
_INVALID_POSTCODE_POOL = ["0000", "9999", "TBC", "XXXX", "6000X"]


def apply_cp_clients_presets(clients_df: pd.DataFrame, severity: str, seed: int) -> pd.DataFrame:
    """Two new checks for cp_clients, previously untested: postcode's
    closed-value-set check, and a new out-of-range date_of_birth check
    (Child Protection had no date-range check at all before this - see
    contract/child-protection-soda-checks.yml and dbt_project/tests/
    cp_client_date_of_birth_range.sql).

    date_of_birth's rate is calibrated as an absolute count, not a
    percentage, against this table's actual ~527-row size - the amber
    rate lands under the check's own warn>10 threshold (Keith's own
    framing when this was scoped: "up to ten is tolerable"), the red rate
    clears the fail>20 threshold by a clear margin, not just barely."""
    rate_postcode = 0.006 if severity == "amber" else 0.03  # warn>0%, fail>3%, same band as BDM's suburb check
    rate_dob_range = 0.017 if severity == "amber" else 0.053  # ~9 rows amber (under warn>10), ~28 rows red (over fail>20)
    out = inject_invalid_values(clients_df, "postcode", _INVALID_POSTCODE_POOL, rate_postcode, seed)
    out = inject_out_of_range_dates(out, "date_of_birth", _BAD_DATE_OF_BIRTH_POOL, rate_dob_range, seed + 1)
    return out


def apply_cp_investigations_presets(investigations_df: pd.DataFrame, clients_df: pd.DataFrame,
                                     severity: str, seed: int) -> pd.DataFrame:
    """Reopens (nulls end_date on) a fraction of investigations belonging
    to a Closed-case client - a real process lapse the closed-case
    investigation hygiene business rule (contract/child-protection-
    contract.yaml, dbt_project/tests/closed_case_investigation_hygiene.sql)
    is built to catch. child_protection.py only ever closes a case once
    its own investigations have concluded by construction, so every
    violation on a run this preset touches is this preset's doing, not
    baseline noise - unlike the pre-fix generator, where the rule always
    failed."""
    rate = 0.03 if severity == "amber" else 0.10
    closed_client_ids = set(clients_df.loc[clients_df["case_status"] == "Closed", "cp_client_id"])
    eligible = investigations_df["cp_client_id"].isin(closed_client_ids) & investigations_df["end_date"].notna()
    return inject_nulls_in_subset(investigations_df, "end_date", eligible, rate, seed)
