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
from datetime import date, timedelta

import numpy as np
import pandas as pd


def inject_nulls(df: pd.DataFrame, column: str, rate: float, seed: int) -> pd.DataFrame:
    """Set `rate` of `column`'s values to null. Use this for the "null-rate
    creep" failure mode - e.g. bump place_of_birth_facility's null rate past
    its warn/fail thresholds to see the dataset-level rollup turn amber/red.

    Real bug found 2026-09-15 (plans/qa-pipeline.md #27, first hit
    nulling is_multiple_birth - a bool column): a numpy bool/int dtype
    column can't natively hold None/NaN, so `out.loc[mask, column] =
    None` raised `pandas.errors.LossySetitemError` instead of nulling
    anything - every prior caller of this function happened to target an
    already-nullable (object/datetime) column, so this was never hit
    before. Upcasting to object first when needed fixes it generically,
    not just for that one call site. Unconditional on `mask` having any
    True values, deliberately - confirmed live that pandas validates the
    assigned scalar against the column's dtype before applying the
    (possibly all-False) boolean selection, so this raises even when
    nothing would actually be set."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    mask = rng.random(len(out)) < rate
    if out[column].dtype.kind in "biu":  # bool/int/uint can't hold None natively
        out[column] = out[column].astype(object)
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


def inject_stale_delivery(df: pd.DataFrame, seed: int, rate: float = 0.05) -> pd.DataFrame:
    """Occasional WHOLE-RUN staleness (Phase 5f, plans/qa-pipeline.md #61,
    Keith's call: occasional, independent of severity tier - not a preset,
    not per-row). Simulates an upstream feed that kept arriving on
    schedule but with old or replayed date_of_birth values - the real
    scenario the 3 freshness checks (dbt's recency singular test, Soda's
    matching failed-rows check, datacontract-cli's custom_sql equivalent)
    exist to catch, now that all 3 are anchored to date_registered
    instead of real wall-clock CURRENT_DATE (see each check's own
    comment for why anchoring alone, with no genuine staleness scenario
    to catch, would have just made them trivially pass every run instead
    of trivially fail).

    Unlike every rate-based injector above, this is a single coin flip
    for the WHOLE run, not a per-row rate: `rate` of runs get EVERY row's
    date_of_birth pushed 15-45 days before its own date_registered - well
    past the checks' 7-day window. date_registered itself is deliberately
    left untouched (still equals run_date, per daily_batch.py) - a
    genuinely stale delivery still gets processed "today", it's the
    underlying birth data that's old."""
    rng = np.random.default_rng(seed)
    if rng.random() >= rate:
        return df.copy()
    out = df.copy()
    lag_days = rng.integers(15, 46, size=len(out))
    out["date_of_birth"] = [d - timedelta(days=int(n)) for d, n in zip(out["date_registered"], lag_days)]
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


def inject_dangling_foreign_key(df: pd.DataFrame, column: str, seed: int, rate: float,
                                  id_format: str, existing_ids, id_max: int = 1_000_000_000) -> pd.DataFrame:
    """Overwrites `rate` of `column` with a well-formed-looking but
    genuinely nonexistent ID (built from `id_format`, e.g. "CPS-{:09d}") -
    the "the referenced row was never in this extract" failure mode a
    real relationships/reference check (dbt's `relationships`, Soda's
    `values in ... must exist in ...`) is built to catch. Different in
    kind from inject_invalid_values' "reassigned to a still-real row"
    business-rule violation (see apply_cp_placements_presets/apply_cp_
    investigations_presets): this actually breaks referential integrity,
    which every preset in this module deliberately avoided until
    plans/qa-pipeline.md #27's dangling-FK gap was scoped to close it
    (2026-09-15, Keith's call).

    `existing_ids`: the real ID universe for the referenced table (e.g.
    `set(cp_clients_df["cp_client_id"])`) - candidates are drawn until
    one misses this set, so an injected value is guaranteed dangling
    rather than merely improbable to collide. `id_max` bounds the random
    numeric suffix - pass the referenced table's own ID-minting range
    (e.g. 100_000 for a 5-digit worker_id) so a dangling value still
    looks plausible in that column's format, not just structurally valid
    with an implausibly huge suffix."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    mask = rng.random(len(out)) < rate
    n = int(mask.sum())
    if n == 0:
        return out
    existing = set(existing_ids)
    dangling: list[str] = []
    seen = set()
    while len(dangling) < n:
        candidate = id_format.format(rng.integers(0, id_max))
        if candidate not in existing and candidate not in seen:
            seen.add(candidate)
            dangling.append(candidate)
    out.loc[mask, column] = dangling
    return out


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

# Well-formed-LOOKING but not '^SRC-[0-9]{9}$' values - wrong digit count,
# a letter in the digit section, or a missing/misplaced hyphen - for
# source_system_record_id's own format check (plans/qa-pipeline.md #27:
# previously this column only ever got exact-value DUPLICATION via
# inject_duplicate_values below, never a malformed value, despite having
# its own format check in every one of contract/Soda/dbt). None of these
# are null-sentinel strings (see _INVALID_SUBURB_POOL's comment above for
# why that would matter).
_MALFORMED_SRC_ID_POOL = ["SRC-12345", "SRC-1234567890", "SRC12345678", "SRCX-123456789", "SRC-ABCDEFGHI"]


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

    df = inject_invalid_values(df, "sex", ["U", "O", "9"], rate_sex, seed)
    df = inject_nulls(df, "place_of_birth_facility", rate_facility_null, seed + 1)
    df = inject_duplicate_values(df, "source_system_record_id", rate_dup_id, seed + 2)
    df = inject_invalid_values(df, "child_given_names", _JUNK_TEXT_POOL, rate_junk_name, seed + 3)
    df = inject_extract_timestamp_disorder(df, rate_ts_disorder, seed + 4)
    df = break_multiple_birth_siblings(df, severity, seed + 5)
    df = inject_invalid_values(df, "place_of_birth_suburb", _INVALID_SUBURB_POOL, rate_suburb, seed + 7)
    df = inject_out_of_range_dates(df, "date_of_birth", _BAD_DATE_OF_BIRTH_POOL, rate_dob_range, seed + 8)
    df = inject_nulls(df, "date_of_birth", rate_null_required, seed + 9)
    df = inject_nulls(df, "date_registered", rate_null_required, seed + 10)
    df = inject_nulls(df, "is_multiple_birth", rate_null_minor, seed + 11)
    df = inject_nulls(df, "extract_timestamp", rate_null_required, seed + 12)
    df = inject_nulls(df, "source_system_record_id", rate_null_minor, seed + 13)
    df = inject_nulls(df, "registration_number", rate_null_required, seed + 14)
    df = inject_duplicate_values(df, "registration_number", rate_dup_registration_number, seed + 15)
    df = inject_invalid_values(df, "child_family_name", _JUNK_TEXT_POOL, rate_junk_name_other, seed + 16)
    df = inject_invalid_values(df, "registering_parent_1_name", _JUNK_TEXT_POOL, rate_junk_name_other, seed + 17)
    df = inject_invalid_values(df, "registering_parent_2_name", _JUNK_TEXT_POOL, rate_junk_name_other, seed + 18)
    df = inject_invalid_values(df, "source_system_record_id", _MALFORMED_SRC_ID_POOL, rate_malformed_src_id, seed + 19)
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
    injector's `existing_ids` exclusion set from - see generate_cp_runs.
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

    df = inject_invalid_values(df, "concern_type", ["Unspecified", "Pending classification", "Code 9"], rate, seed)
    df = inject_duplicate_rows(df, rate=0.015 if severity == "amber" else 0.05, seed=seed + 1,
                                near_duplicate_columns=["notification_id"])
    df = inject_nulls(df, "cp_client_id", rate_null, seed + 2)
    df = inject_nulls(df, "assigned_worker_id", rate_null, seed + 3)
    df = inject_invalid_values(df, "source_type", ["Court", "Media report", "Unknown"], rate_invalid, seed + 4)
    df = inject_invalid_values(df, "risk_rating", ["Severe", "Unrated", "TBC"], rate_invalid, seed + 5)
    df = inject_invalid_values(df, "outcome", ["Pending review", "Escalated externally"], rate_invalid, seed + 6)
    df = inject_dangling_foreign_key(df, "cp_client_id", seed + 7, rate_dangling,
                                      "CPS-{:09d}", clients_df["cp_client_id"], id_max=1_000_000_000)
    df = inject_dangling_foreign_key(df, "assigned_worker_id", seed + 8, rate_dangling,
                                      "CPS-STAFF-{:05d}", workers_df["worker_id"], id_max=100_000)
    return df


def apply_cp_placements_presets(placements_df: pd.DataFrame, carers_df: pd.DataFrame, clients_df: pd.DataFrame,
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
    pool" mechanism, a different kind of pool.

    plans/qa-pipeline.md #27 pass (2026-09-15): adds not_null on cp_
    client_id/placement_start/placement_suburb (previously never nulled),
    a duplicate-value injector for placement_id (the PK - never touched
    before), invalid-value injection on placement_type (a real check,
    never exercised), and genuine dangling-FK injection on this table's
    2 real FKs (cp_client_id/carer_id) - see apply_cp_notifications_
    presets' own docstring for why this is different from the non-
    Approved-carer reassignment above (still a real cp_carers row, just
    a non-compliant one) and why `clients_df` needs to be the caller's
    real, undirtied cp_clients table."""
    rate = 0.02 if severity == "amber" else 0.08
    rate_null = 0.009 if severity == "amber" else 0.04  # ~2 amber / ~10 red at n~242 - Soda missing_count warn>0/fail>5
    rate_dup = 0.008 if severity == "amber" else 0.025  # ~2 amber / ~6 red - Soda duplicate_count warn>0/fail>3
    rate_invalid = 0.01 if severity == "amber" else 0.07  # ~2 amber / ~17 red - Soda warn>0%/fail>3%, dbt error_if>10
    rate_dangling = 0.008 if severity == "amber" else 0.025  # ~2 amber / ~6 red direct - real count can run higher (see apply_cp_notifications_presets' rate_dangling comment); doesn't affect pass/fail, these checks are single-tier

    non_approved = carers_df.loc[carers_df["approval_status"] != "Approved", "carer_id"].values
    out = inject_invalid_values(placements_df, "carer_id", list(non_approved), rate, seed)
    out = inject_nulls(out, "cp_client_id", rate_null, seed + 1)
    out = inject_nulls(out, "placement_start", rate_null, seed + 2)
    out = inject_nulls(out, "placement_suburb", rate_null, seed + 3)
    out = inject_duplicate_values(out, "placement_id", rate_dup, seed + 4)
    out = inject_invalid_values(out, "placement_type", ["Group home", "Independent living", "Unplaced"], rate_invalid, seed + 5)
    out = inject_dangling_foreign_key(out, "cp_client_id", seed + 6, rate_dangling,
                                       "CPS-{:09d}", clients_df["cp_client_id"], id_max=1_000_000_000)
    out = inject_dangling_foreign_key(out, "carer_id", seed + 7, rate_dangling,
                                       "CARER-{:06d}", carers_df["carer_id"], id_max=1_000_000)
    return out


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
    clears the fail>20 threshold by a clear margin, not just barely.

    plans/qa-pipeline.md #27 pass (2026-09-15): adds every other
    previously-never-exercised check on this table - not_null on given_
    name/family_name/date_of_birth/suburb/case_opened_date (all single-
    tier in dbt, count-banded warn>0/fail>5 in Soda), a duplicate-value
    injector for cp_client_id (the PK - never touched before), and an
    invalid-value injector for sex (already had a real check, just never
    exercised). case_status is explicitly NOT included here despite
    being named in item 27's own audit - it turns out to have no
    accepted_values check anywhere (contract, Soda, or dbt), only a
    literal-value reference inside the closed-case-investigation-hygiene
    business rule, so there is no check here to exercise; flagged back
    to Keith rather than silently invented."""
    rate_postcode = 0.006 if severity == "amber" else 0.03  # warn>0%, fail>3%, same band as BDM's suburb check
    rate_dob_range = 0.017 if severity == "amber" else 0.053  # ~9 rows amber (under warn>10), ~28 rows red (over fail>20)
    rate_null = 0.006 if severity == "amber" else 0.023  # ~3 amber / ~12 red at n~527 - Soda missing_count warn>0/fail>5
    rate_dup_client_id = 0.004 if severity == "amber" else 0.02  # ~2 amber / ~10 red - Soda duplicate_count warn>0/fail>3
    rate_sex = 0.005 if severity == "amber" else 0.04  # ~3 amber (under dbt error_if>15) / ~21 red (over it and Soda's fail>2%)

    out = inject_invalid_values(clients_df, "postcode", _INVALID_POSTCODE_POOL, rate_postcode, seed)
    out = inject_out_of_range_dates(out, "date_of_birth", _BAD_DATE_OF_BIRTH_POOL, rate_dob_range, seed + 1)
    out = inject_nulls(out, "given_name", rate_null, seed + 2)
    out = inject_nulls(out, "family_name", rate_null, seed + 3)
    out = inject_nulls(out, "date_of_birth", rate_null, seed + 4)
    out = inject_nulls(out, "suburb", rate_null, seed + 5)
    out = inject_nulls(out, "case_opened_date", rate_null, seed + 6)
    out = inject_duplicate_values(out, "cp_client_id", rate_dup_client_id, seed + 7)
    out = inject_invalid_values(out, "sex", ["U", "O", "9"], rate_sex, seed + 8)
    return out


def apply_cp_investigations_presets(investigations_df: pd.DataFrame, clients_df: pd.DataFrame,
                                     notifications_df: pd.DataFrame, workers_df: pd.DataFrame,
                                     severity: str, seed: int) -> pd.DataFrame:
    """Reopens (nulls end_date on) a fraction of investigations belonging
    to a Closed-case client - a real process lapse the closed-case
    investigation hygiene business rule (contract/child-protection-
    contract.yaml, dbt_project/tests/closed_case_investigation_hygiene.sql)
    is built to catch. child_protection.py only ever closes a case once
    its own investigations have concluded by construction, so every
    violation on a run this preset touches is this preset's doing, not
    baseline noise - unlike the pre-fix generator, where the rule always
    failed.

    plans/qa-pipeline.md #27 pass (2026-09-15): adds not_null on start_
    date/lead_worker_id (previously never nulled), a duplicate-value
    injector for investigation_id (the PK - never touched before), and
    genuine dangling-FK injection on all 3 of this table's real FKs
    (notification_id/cp_client_id/lead_worker_id) - see apply_cp_
    notifications_presets' own docstring for why this is a different
    failure mode from the business-rule reopening above, and why
    `notifications_df`/`workers_df` (like `clients_df` already did) need
    to be the caller's REAL, undirtied parent tables."""
    rate = 0.03 if severity == "amber" else 0.10
    rate_null = 0.012 if severity == "amber" else 0.05  # ~2 amber / ~9 red at n~181 - Soda missing_count warn>0/fail>5
    rate_dup = 0.011 if severity == "amber" else 0.03  # ~2 amber / ~5 red - Soda duplicate_count warn>0/fail>3
    rate_dangling = 0.011 if severity == "amber" else 0.03  # ~2 amber / ~5 red direct - real count can run higher (see apply_cp_notifications_presets' rate_dangling comment); doesn't affect pass/fail, these checks are single-tier

    closed_client_ids = set(clients_df.loc[clients_df["case_status"] == "Closed", "cp_client_id"])
    eligible = investigations_df["cp_client_id"].isin(closed_client_ids) & investigations_df["end_date"].notna()
    out = inject_nulls_in_subset(investigations_df, "end_date", eligible, rate, seed)
    out = inject_nulls(out, "start_date", rate_null, seed + 1)
    out = inject_nulls(out, "lead_worker_id", rate_null, seed + 2)
    out = inject_duplicate_values(out, "investigation_id", rate_dup, seed + 3)
    out = inject_dangling_foreign_key(out, "notification_id", seed + 4, rate_dangling,
                                       "NOTIF-{:08d}", notifications_df["notification_id"], id_max=100_000_000)
    out = inject_dangling_foreign_key(out, "cp_client_id", seed + 5, rate_dangling,
                                       "CPS-{:09d}", clients_df["cp_client_id"], id_max=1_000_000_000)
    out = inject_dangling_foreign_key(out, "lead_worker_id", seed + 6, rate_dangling,
                                       "CPS-STAFF-{:05d}", workers_df["worker_id"], id_max=100_000)
    return out


def apply_cp_carers_presets(carers_df: pd.DataFrame, severity: str, seed: int) -> pd.DataFrame:
    """New (plans/qa-pipeline.md #27, 2026-09-15): cp_carers was never
    touched by any preset before this - generate_cp_runs.py's own
    docstring used to describe this as deliberate ("the other two tables
    are clean in every run"), but that was only ever true because nothing
    had scoped closing the gap, not because there was no real check to
    exercise (carer_id has a real unique test in both dbt and Soda). Adds
    a duplicate-value injector for carer_id, the same shape as every
    other PK-duplication injector in this module."""
    rate_dup = 0.007 if severity == "amber" else 0.025  # ~2 amber / ~7 red at n~289 - Soda duplicate_count warn>0/fail>3
    return inject_duplicate_values(carers_df, "carer_id", rate_dup, seed)


def apply_cp_case_workers_presets(workers_df: pd.DataFrame, severity: str, seed: int) -> pd.DataFrame:
    """New (plans/qa-pipeline.md #27, 2026-09-15) - see apply_cp_carers_
    presets' own docstring for why cp_case_workers is getting its first
    preset here too. worker_id has a real unique test in both dbt and
    Soda; this table is small (~60 rows), so the rates below are tuned
    up from the usual "duplicate_count" calibration to still land a
    believable handful of duplicates at that size."""
    rate_dup = 0.025 if severity == "amber" else 0.08  # ~1-2 amber / ~5 red at n~60 - Soda duplicate_count warn>0/fail>3
    return inject_duplicate_values(workers_df, "worker_id", rate_dup, seed)
