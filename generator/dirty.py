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
def apply_birth_registrations_presets(df: pd.DataFrame, severity: str, seed: int) -> pd.DataFrame:
    """severity: 'amber' or 'red' - matches the warn/fail bands in
    bdm-birth-registrations-soda-checks.yml exactly, so a QA run against
    this output should land in the band you asked for."""
    rate_sex = 0.008 if severity == "amber" else 0.028      # warn>0%, fail>2%
    rate_facility_null = 0.20 if severity == "amber" else 0.40  # warn>15%, fail>35%
    df = inject_invalid_values(df, "sex", ["U", "O", "9"], rate_sex, seed)
    df = inject_nulls(df, "place_of_birth_facility", rate_facility_null, seed + 1)
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
