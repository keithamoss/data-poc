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
    if "is_multiple_birth" in out.columns:
        # ONE LAG PER BIRTH EVENT (post-build-review #380): twins are matched
        # on date_of_birth, facility and parent 1, and a replayed feed
        # replays the event whole - a lag per row split every pair, so every
        # stale supply also failed the sibling checks. Each twin takes the
        # lag of its pair's first row; every other row's draw is unchanged.
        twin = out["is_multiple_birth"].fillna(False).astype(bool).to_numpy()
        key = out.groupby(["date_of_birth", "place_of_birth_facility",
                           "registering_parent_1_name"], dropna=False, sort=False).ngroup().to_numpy()
        first: dict[int, int] = {}
        for i in np.where(twin)[0]:
            lag_days[i] = lag_days[first.setdefault(key[i], i)]
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
    already varies run to run (see civil_registration.py's RUN_PLAN) enough
    that a fixed drop-rate from THIS run's own count doesn't reliably land
    a specific percentage below whatever the previous run happened to be."""
    if target_rows >= len(df):
        return df.copy()
    rng = np.random.default_rng(seed)
    keep_idx = np.sort(rng.choice(len(df), size=target_rows, replace=False))
    return df.iloc[keep_idx].reset_index(drop=True)


def break_multiple_birth_siblings(df: pd.DataFrame, rate: float, seed: int) -> pd.DataFrame:
    """Drops one row from a fraction of real multiple-birth sibling pairs
    (daily_batch.py now generates genuine pairs - same date_of_birth,
    facility, and parent 1 - for every is_multiple_birth row) - the
    remaining twin's is_multiple_birth=True flag is left with no sibling
    row to match, the "one twin's registration never arrived" failure
    mode the sibling-match check is built to catch. `rate` is the share of
    pairs broken - population's literal rate (synthetic_data_generator/
    dirty_presets.py); the Birth Registrations preset plants an exact count
    instead (REQ-GEN-392)."""
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
#     type / risk rating value sets). ---
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


# Not a real WA postcode from generator/names_au.py's SUBURBS pool - a mix
# of an obviously-placeholder value and out-of-range-looking numbers, for
# cp_clients.postcode's new closed-value-set check (previously had no
# invalid-value check at all - see plans/qa-pipeline.md #15).
#
# Deliberately NOT "N/A" - see _INVALID_SUBURB_POOL's comment above for
# the null-sentinel bug this pool originally had too (found via the same
# calibration check, on this same pool).
_INVALID_POSTCODE_POOL = ["0000", "9999", "TBC", "XXXX", "6000X"]


# ---- the presets: every fault's size derived from its aimed bands ----------
#
# REQ-GEN-392 (Keith, Q5 of 2026-11-14): each preset declares, in one table,
# the rule or rules each of its faults aims at, by check_bands' rule key
# (generator/targeting.rule_key) - as Linkage Products' GEO_FAULT_AIMS does -
# and generator/fault_sizing.py works each fault's size out from those rules'
# warn and fail bands at the frame's own row count. A band edited in a check
# file moves the fault with it; there is no literal rate left to drift.
#
# EXACT COUNTS (392 Q3 (ii)): each fault plants exactly its derived count of
# faulty rows, never a per-row probability, each injector keeping its own
# seed. Rows one fault has touched are never touched by another on the same
# column, so each count is the count a check reads.
#
# THE LITERALS LEFT ARE NOT BANDS (criterion 8): the invalid-value pools
# above, the stale-delivery coin flip (inject_stale_delivery's whole-run
# rate) and its 15-45 day lag, extract_timestamp disorder's 1-4 hour shift,
# the dangling-id formats and ranges, and the seed offsets. Each is named in
# REQ-GEN-392's decisions with why.

from generator import fault_sizing  # noqa: E402

#: Birth Registrations' faults and the rules each aims at (criterion 1).
BIRTH_REGISTRATIONS_AIMS = {
    "truncation": ("(table).timeliness.drop",),
    "sibling_break": ("Multiple-birth sibling match",),
    "sex_invalid": ("sex.conformity",),
    "facility_null": ("place_of_birth_facility.completeness",),
    "source_id_duplicate": ("source_system_record_id.uniqueness",),
    "given_names_junk": ("child_given_names.conformity",),
    "timestamp_disorder": ("Supply timestamp ordering",),
    "suburb_invalid": ("place_of_birth_suburb.conformity",),
    "date_of_birth_out_of_range": ("Date of birth in a plausible range",),
    "date_of_birth_null": ("date_of_birth.completeness",),
    "date_registered_null": ("date_registered.completeness",),
    "multiple_birth_null": ("is_multiple_birth.completeness",),
    "extract_timestamp_null": ("extract_timestamp.completeness",),
    "source_id_null": ("source_system_record_id.completeness",),
    "registration_number_null": ("registration_number.completeness",),
    "registration_number_duplicate": ("registration_number.uniqueness",),
    "family_name_junk": ("child_family_name.conformity",),
    "parent_1_junk": ("registering_parent_1_name.conformity",),
    "parent_2_junk": ("registering_parent_2_name.conformity",),
    "source_id_malformed": ("source_system_record_id.conformity",),
}

#: Child Protection's notifications. The duplicate submission aims at the key
#: rule Soda and the contract count in duplicated KEYS; dbt's unique test
#: counts the ROWS in duplicated groups, a different quantity and so a
#: different rule (check_bands' docstring) that the same rows also move.
CP_NOTIFICATIONS_AIMS = {
    "duplicate_submission": ("notification_id.uniqueness",),
    "concern_type_invalid": ("concern_type.conformity",),
    "client_null": ("cp_client_id.completeness",),
    "worker_null": ("assigned_worker_id.completeness",),
    "source_type_invalid": ("source_type.conformity",),
    "risk_rating_invalid": ("risk_rating.conformity",),
    "outcome_invalid": ("outcome.conformity",),
    "client_dangling": ("Client reference",),
    "worker_dangling": ("Assigned worker reference",),
}

CP_PLACEMENTS_AIMS = {
    "carer_not_approved": ("Carer approval compliance",),
    "client_null": ("cp_client_id.completeness",),
    "start_null": ("placement_start.completeness",),
    "suburb_null": ("placement_suburb.completeness",),
    "placement_id_duplicate": ("placement_id.uniqueness",),
    "placement_type_invalid": ("placement_type.conformity",),
    "client_dangling": ("Client reference",),
    "carer_dangling": ("Carer reference",),
}

CP_CLIENTS_AIMS = {
    "postcode_invalid": ("postcode.conformity",),
    "date_of_birth_out_of_range": ("Date of birth in a plausible range",),
    "given_name_null": ("given_name.completeness",),
    "family_name_null": ("family_name.completeness",),
    "date_of_birth_null": ("date_of_birth.completeness",),
    "suburb_null": ("suburb.completeness",),
    "case_opened_null": ("case_opened_date.completeness",),
    "client_id_duplicate": ("cp_client_id.uniqueness",),
    "sex_invalid": ("sex.conformity",),
}

CP_INVESTIGATIONS_AIMS = {
    "closed_case_reopened": ("Closed-case hygiene",),
    "start_null": ("start_date.completeness",),
    "lead_worker_null": ("lead_worker_id.completeness",),
    "investigation_id_duplicate": ("investigation_id.uniqueness",),
    "notification_dangling": ("Notification reference",),
    "client_dangling": ("Client reference",),
    "lead_worker_dangling": ("Lead worker reference",),
}

CP_CARERS_AIMS = {"carer_id_duplicate": ("carer_id.uniqueness",)}

CP_CASE_WORKERS_AIMS = {"worker_id_duplicate": ("worker_id.uniqueness",)}


class _Planter:
    """One preset's faults on one frame: each sized from its aims table and
    planted as an exact count (REQ-GEN-392 criteria 2-7).

    `protected` rows are never faulted - Birth Registrations' twins, whose
    sibling check matches on the very columns these faults change, so a
    fault aimed elsewhere cannot also break a pair. The sibling fault itself
    is the one that reads them."""

    def __init__(self, df: pd.DataFrame, table: str, severity: str, preset: str,
                 aims: dict, catalogue=None, protected=None):
        from asset_model import hierarchy

        self.df = df.reset_index(drop=True)
        self.dataset_id = hierarchy.dataset_for_table(table).dataset_id
        self.severity, self.preset, self.aims = severity, preset, aims
        self.cat = catalogue if catalogue is not None else fault_sizing.catalogue()
        self.protected = set() if protected is None else set(self.df.index[protected])
        self.touched: dict[str, set] = {}

    def where(self, fault: str) -> str:
        return f"{self.preset}, fault {fault}"

    def refuse(self, fault: str, why: str) -> fault_sizing.FaultSizeError:
        """Every refusal names the preset, the fault, the rules it aims at
        and their bands (criterion 7; post-build-review #383)."""
        return fault_sizing.refusal(self.cat, self.dataset_id, self.aims[fault], self.where(fault),
                                    f"{self.severity}: {why}")

    def size(self, fault: str, rows: int | None = None) -> int:
        return fault_sizing.size(self.cat, self.dataset_id, self.aims[fault], self.severity,
                                 len(self.df) if rows is None else rows, self.where(fault))

    def to_plant(self, fault: str, already: int) -> int:
        """How many MORE faulty rows make the derived TOTAL (post-build-review
        #381): rows the frame already carries count towards it, as
        targeting._set_nulls sizes a total. Refused where what is already
        there lands somewhere other than asked - past an amber band, say -
        since a preset only adds faults, never repairs them."""
        want = self.size(fault)
        n = max(0, want - already)
        fault_sizing.lands(self.cat, self.dataset_id, self.aims[fault], self.severity,
                           already + n, len(self.df), self.where(fault))
        return n

    def _eligible(self, column: str, also=(), mask=None) -> list:
        out = self.df
        ok = out[column].notna()
        for col in also:
            ok &= out[col].notna()
        if mask is not None:
            ok &= mask.reindex(out.index, fill_value=False).astype(bool)
        skip = self.protected.union(*(self.touched.get(c, set()) for c in (column, *also)))
        return [i for i in out.index[ok] if i not in skip]

    def _choose(self, fault: str, eligible: list, n: int, seed: int):
        rng = np.random.default_rng(seed)
        if n > len(eligible):
            raise self.refuse(fault, f"{n} rows are needed and only {len(eligible)} of the "
                                     f"frame's {len(self.df)} rows are eligible - the band cannot "
                                     f"be reached at this row count")
        return rng, np.sort(rng.choice(np.array(eligible, dtype=object), size=n, replace=False)) \
            if n else np.array([], dtype=object)

    def _mark(self, labels, *columns) -> None:
        for col in columns:
            self.touched.setdefault(col, set()).update(labels)

    def _dup_keys(self, column: str) -> int:
        s = self.df[column].dropna()
        return int(s[s.duplicated(keep=False)].nunique())

    def nulls(self, fault: str, column: str, seed: int, mask=None, reserve=()) -> None:
        """`reserve`: other columns of the chosen rows that later faults must
        leave alone, because the aimed rule reads them too - the hygiene
        rule joins a reopened investigation to its client (post-build-review
        #382)."""
        missing = self.df[column].isna()
        if mask is not None:
            missing &= mask.reindex(self.df.index, fill_value=False).astype(bool)
        n = self.to_plant(fault, int(missing.sum()))
        rng, chosen = self._choose(fault, self._eligible(column, mask=mask), n, seed)
        if n:
            if self.df[column].dtype.kind in "biu":
                self.df[column] = self.df[column].astype(object)
            self.df.loc[chosen, column] = None
        self._mark(chosen, column, *reserve)

    def values(self, fault: str, column: str, pool: list, seed: int,
               distinct: bool = False) -> None:
        """Values drawn from `pool` - invalid codes, junk text, an impossible
        date, a non-approved carer; a row already holding one of them counts
        towards the total. `distinct`: for an identifier, no value is drawn
        twice, so the fault never also plants a duplicated key."""
        n = self.to_plant(fault, int(self.df[column].isin(list(pool)).sum()))
        rng, chosen = self._choose(fault, self._eligible(column), n, seed)
        if n:
            if not pool or (distinct and n > len(pool)):
                raise self.refuse(fault, f"{n} rows are needed and its value pool holds "
                                         f"{len(set(pool))} distinct values")
            draw = rng.choice(np.array(pool, dtype=object), size=n, replace=not distinct)
            if self.df[column].dtype.kind in "biu":
                self.df[column] = self.df[column].astype(object)
            self.df.loc[chosen, column] = draw
        self._mark(chosen, column)

    def duplicate_values(self, fault: str, column: str, seed: int) -> None:
        """`n` duplicated keys exactly: `n` rows take the values of `n` other,
        distinct rows, and both halves are left alone by later faults.

        THE TARGET'S OWN ID IS OVERWRITTEN, so a row in another table that
        referenced it now references nothing - Child Protection's clients
        duplicate, the notifications, placements and investigations that
        named the overwritten client go dangling in the same delivery. Kept
        on purpose (PROVISIONAL, overnight 2026-11-16, REQ-GEN-392's
        decisions): those are other tables' rules, and adding a donor copy
        instead would change the row count after every other fault was
        sized."""
        n = self.to_plant(fault, self._dup_keys(column))
        rng, chosen = self._choose(fault, self._eligible(column), 2 * n, seed)
        if n:
            order = rng.permutation(len(chosen))
            targets, donors = chosen[order[:n]], chosen[order[n:]]
            self.df.loc[targets, column] = self.df.loc[donors, column].to_numpy()
        self._mark(chosen, column)

    def dangling(self, fault: str, column: str, seed: int, id_format: str, existing_ids,
                 id_max: int) -> None:
        existing = set(existing_ids)
        col = self.df[column]
        n = self.to_plant(fault, int((col.notna() & ~col.isin(existing)).sum()))
        rng, chosen = self._choose(fault, self._eligible(column), n, seed)
        made: list = []
        while len(made) < n:
            candidate = id_format.format(rng.integers(0, id_max))
            if candidate not in existing and candidate not in made:
                made.append(candidate)
        if n:
            self.df.loc[chosen, column] = made
        self._mark(chosen, column)

    def timestamp_disorder(self, fault: str, seed: int) -> None:
        """extract_timestamp moved one to four hours before its own row's
        date_registered - and that row's date_registered then left alone, so
        a later null cannot hide the disorder."""
        before = (pd.to_datetime(self.df["extract_timestamp"])
                  < pd.to_datetime(self.df["date_registered"]))
        n = self.to_plant(fault, int(before.sum()))
        rng, chosen = self._choose(fault, self._eligible("extract_timestamp", ("date_registered",)),
                                   n, seed)
        if n:
            shift = pd.to_timedelta(rng.integers(1, 5, size=n), unit="h")
            self.df.loc[chosen, "extract_timestamp"] = (
                pd.to_datetime(self.df.loc[chosen, "date_registered"]) - shift).to_numpy()
        self._mark(chosen, "extract_timestamp", "date_registered")

    def duplicate_rows(self, fault: str, key: str, seed: int) -> None:
        """`n` rows submitted twice, every column the same - `n` duplicated
        keys exactly."""
        n = self.to_plant(fault, self._dup_keys(key))
        rng, chosen = self._choose(fault, self._eligible(key), n, seed)
        if n:
            copies = self.df.loc[chosen]
            self.df = pd.concat([self.df, copies], ignore_index=True)
            self._mark(range(len(self.df) - n, len(self.df)), key)
        self._mark(chosen, key)


def _twins(df: pd.DataFrame) -> pd.Series:
    return df["is_multiple_birth"].fillna(False).astype(bool)


def apply_birth_registrations_presets(df: pd.DataFrame, severity: str, seed: int,
                                       previous_row_count: int | None = None,
                                       catalogue=None) -> pd.DataFrame:
    """severity: 'amber' or 'red'. Every fault in BIRTH_REGISTRATIONS_AIMS,
    each sized from its aimed rules' bands (REQ-GEN-392): a Warn at the
    middle of the amber band, a Fail at the lowest failing count plus the
    band's width, a single-tier rule nothing for a Warn and FAIL_ROWS for a
    Fail. `catalogue`: check_bands' catalogue, read once per generation by
    the caller; read here when not given.

    The ordinary amber no longer comes here (REQ-GEN-184's
    targeting.bdm_amber builds it); a Fail supply does, and so does any
    caller asking for amber by hand.

    THE ROW COUNT CHANGES FIRST - truncation, then the broken twin pairs -
    so every other fault is sized at the frame's own final row count.
    Truncation is sized against `previous_row_count`, the supply before it,
    which is what the drop check compares against; None (the very first
    supply) skips it. Only single-birth rows are cut, and no column fault
    touches a twin, so the sibling check reads exactly the pairs broken on
    purpose."""
    planter = _Planter(df, "birth_registrations", severity, "apply_birth_registrations_presets",
                       BIRTH_REGISTRATIONS_AIMS, catalogue, protected=_twins(df).to_numpy())
    p = planter
    if previous_row_count:
        cut = p.size("truncation", rows=previous_row_count)
        need = len(p.df) - (previous_row_count - cut)
        if need > 0:
            _rng, drop = p._choose("truncation", [i for i in p.df.index if i not in p.protected],
                                   need, seed + 6)
            p.df = p.df.drop(index=drop)
        fault_sizing.lands(p.cat, p.dataset_id, BIRTH_REGISTRATIONS_AIMS["truncation"], severity,
                           previous_row_count - len(p.df), previous_row_count,
                           p.where("truncation"))
    # Twin pairs broken: one row of each dropped, its sibling left orphaned.
    twins = p.df[_twins(p.df)]
    groups = twins.groupby(["date_of_birth", "place_of_birth_facility",
                            "registering_parent_1_name"], dropna=False).groups
    pairs = [idx for idx in groups.values() if len(idx) >= 2]
    n_break = p.to_plant("sibling_break", sum(1 for idx in groups.values() if len(idx) == 1))
    if n_break > len(pairs):
        raise p.refuse("sibling_break", f"{n_break} broken twin pairs are needed and the frame "
                                        f"holds {len(pairs)}")
    if n_break:
        rng = np.random.default_rng(seed + 5)
        chosen = rng.choice(len(pairs), size=n_break, replace=False)
        p.df = p.df.drop(index=[pairs[i][0] for i in chosen])
    p.df = p.df.reset_index(drop=True)
    p.protected = set(p.df.index[_twins(p.df).to_numpy()])

    p.values("sex_invalid", "sex", ["U", "O", "9"], seed)
    p.nulls("facility_null", "place_of_birth_facility", seed + 1)
    p.duplicate_values("source_id_duplicate", "source_system_record_id", seed + 2)
    p.values("given_names_junk", "child_given_names", _JUNK_TEXT_POOL, seed + 3)
    p.timestamp_disorder("timestamp_disorder", seed + 4)
    p.values("suburb_invalid", "place_of_birth_suburb", _INVALID_SUBURB_POOL, seed + 7)
    p.values("date_of_birth_out_of_range", "date_of_birth", _BAD_DATE_OF_BIRTH_POOL, seed + 8)
    p.nulls("date_of_birth_null", "date_of_birth", seed + 9)
    p.nulls("date_registered_null", "date_registered", seed + 10)
    p.nulls("multiple_birth_null", "is_multiple_birth", seed + 11)
    p.nulls("extract_timestamp_null", "extract_timestamp", seed + 12)
    p.nulls("source_id_null", "source_system_record_id", seed + 13)
    p.nulls("registration_number_null", "registration_number", seed + 14)
    p.duplicate_values("registration_number_duplicate", "registration_number", seed + 15)
    p.values("family_name_junk", "child_family_name", _JUNK_TEXT_POOL, seed + 16)
    p.values("parent_1_junk", "registering_parent_1_name", _JUNK_TEXT_POOL, seed + 17)
    p.values("parent_2_junk", "registering_parent_2_name", _JUNK_TEXT_POOL, seed + 18)
    p.values("source_id_malformed", "source_system_record_id", _MALFORMED_SRC_ID_POOL, seed + 19,
             distinct=True)
    return p.df


def apply_cp_notifications_presets(df: pd.DataFrame, clients_df: pd.DataFrame, workers_df: pd.DataFrame,
                                    severity: str, seed: int, catalogue=None) -> pd.DataFrame:
    """Every fault in CP_NOTIFICATIONS_AIMS, sized from its bands
    (REQ-GEN-392). The duplicate submission comes first, so every other
    fault is sized at the frame's final row count. `clients_df`/
    `workers_df` are the REAL (undirtied) parent tables, so a dangling id is
    guaranteed absent from them - see child_protection.py's dirty() for why
    it passes base_tables here."""
    p = _Planter(df, "cp_notifications", severity, "apply_cp_notifications_presets",
                 CP_NOTIFICATIONS_AIMS, catalogue)
    p.duplicate_rows("duplicate_submission", "notification_id", seed + 1)
    p.values("concern_type_invalid", "concern_type",
             ["Unspecified", "Pending classification", "Code 9"], seed)
    p.nulls("client_null", "cp_client_id", seed + 2)
    p.nulls("worker_null", "assigned_worker_id", seed + 3)
    p.values("source_type_invalid", "source_type", ["Court", "Media report", "Unknown"], seed + 4)
    p.values("risk_rating_invalid", "risk_rating", ["Severe", "Unrated", "TBC"], seed + 5)
    p.values("outcome_invalid", "outcome", ["Pending review", "Escalated externally"], seed + 6)
    p.dangling("client_dangling", "cp_client_id", seed + 7, "CPS-{:09d}",
               clients_df["cp_client_id"], id_max=1_000_000_000)
    p.dangling("worker_dangling", "assigned_worker_id", seed + 8, "CPS-STAFF-{:05d}",
               workers_df["worker_id"], id_max=100_000)
    return p.df


def apply_cp_placements_presets(placements_df: pd.DataFrame, carers_df: pd.DataFrame, clients_df: pd.DataFrame,
                                 severity: str, seed: int, catalogue=None) -> pd.DataFrame:
    """Every fault in CP_PLACEMENTS_AIMS, sized from its bands
    (REQ-GEN-392). The carer-approval fault reassigns placements to a
    non-Approved carer - still a real cp_carers row, so a business-rule
    breach rather than a dangling reference; child_protection.py only ever
    assigns Approved carers, so every breach is this fault's. `clients_df`
    is the caller's real, undirtied cp_clients table."""
    p = _Planter(placements_df, "cp_placements", severity, "apply_cp_placements_presets",
                 CP_PLACEMENTS_AIMS, catalogue)
    non_approved = list(carers_df.loc[carers_df["approval_status"] != "Approved", "carer_id"].values)
    p.values("carer_not_approved", "carer_id", non_approved, seed)
    p.nulls("client_null", "cp_client_id", seed + 1)
    p.nulls("start_null", "placement_start", seed + 2)
    p.nulls("suburb_null", "placement_suburb", seed + 3)
    p.duplicate_values("placement_id_duplicate", "placement_id", seed + 4)
    p.values("placement_type_invalid", "placement_type",
             ["Group home", "Independent living", "Unplaced"], seed + 5)
    p.dangling("client_dangling", "cp_client_id", seed + 6, "CPS-{:09d}",
               clients_df["cp_client_id"], id_max=1_000_000_000)
    p.dangling("carer_dangling", "carer_id", seed + 7, "CARER-{:06d}", carers_df["carer_id"],
               id_max=1_000_000)
    return p.df


def apply_cp_clients_presets(clients_df: pd.DataFrame, severity: str, seed: int,
                             catalogue=None) -> pd.DataFrame:
    """Every fault in CP_CLIENTS_AIMS, sized from its bands (REQ-GEN-392).
    case_status has no accepted-values check of its own in any tool, only
    a literal inside the closed-case hygiene rule, so nothing here aims at
    it."""
    p = _Planter(clients_df, "cp_clients", severity, "apply_cp_clients_presets",
                 CP_CLIENTS_AIMS, catalogue)
    p.values("postcode_invalid", "postcode", _INVALID_POSTCODE_POOL, seed)
    p.values("date_of_birth_out_of_range", "date_of_birth", _BAD_DATE_OF_BIRTH_POOL, seed + 1)
    p.nulls("given_name_null", "given_name", seed + 2)
    p.nulls("family_name_null", "family_name", seed + 3)
    p.nulls("date_of_birth_null", "date_of_birth", seed + 4)
    p.nulls("suburb_null", "suburb", seed + 5)
    p.nulls("case_opened_null", "case_opened_date", seed + 6)
    p.duplicate_values("client_id_duplicate", "cp_client_id", seed + 7)
    p.values("sex_invalid", "sex", ["U", "O", "9"], seed + 8)
    return p.df


def apply_cp_investigations_presets(investigations_df: pd.DataFrame, clients_df: pd.DataFrame,
                                     notifications_df: pd.DataFrame, workers_df: pd.DataFrame,
                                     severity: str, seed: int, catalogue=None) -> pd.DataFrame:
    """Every fault in CP_INVESTIGATIONS_AIMS, sized from its bands
    (REQ-GEN-392). The hygiene fault reopens (nulls end_date on) an
    investigation belonging to a Closed-case client - child_protection.py
    only closes a case once its investigations have concluded, so every
    breach is this fault's. The parent tables are the caller's REAL,
    undirtied ones."""
    p = _Planter(investigations_df, "cp_investigations", severity,
                 "apply_cp_investigations_presets", CP_INVESTIGATIONS_AIMS, catalogue)
    closed = set(clients_df.loc[clients_df["case_status"] == "Closed", "cp_client_id"])
    p.nulls("closed_case_reopened", "end_date", seed, mask=p.df["cp_client_id"].isin(closed),
            reserve=("cp_client_id",))
    p.nulls("start_null", "start_date", seed + 1)
    p.nulls("lead_worker_null", "lead_worker_id", seed + 2)
    p.duplicate_values("investigation_id_duplicate", "investigation_id", seed + 3)
    p.dangling("notification_dangling", "notification_id", seed + 4, "NOTIF-{:08d}",
               notifications_df["notification_id"], id_max=100_000_000)
    p.dangling("client_dangling", "cp_client_id", seed + 5, "CPS-{:09d}",
               clients_df["cp_client_id"], id_max=1_000_000_000)
    p.dangling("lead_worker_dangling", "lead_worker_id", seed + 6, "CPS-STAFF-{:05d}",
               workers_df["worker_id"], id_max=100_000)
    return p.df


def apply_cp_carers_presets(carers_df: pd.DataFrame, severity: str, seed: int,
                            catalogue=None) -> pd.DataFrame:
    """carer_id duplicated, sized from its bands (REQ-GEN-392)."""
    p = _Planter(carers_df, "cp_carers", severity, "apply_cp_carers_presets", CP_CARERS_AIMS,
                 catalogue)
    p.duplicate_values("carer_id_duplicate", "carer_id", seed)
    return p.df


def apply_cp_case_workers_presets(workers_df: pd.DataFrame, severity: str, seed: int,
                                  catalogue=None) -> pd.DataFrame:
    """worker_id duplicated, sized from its bands (REQ-GEN-392)."""
    p = _Planter(workers_df, "cp_case_workers", severity, "apply_cp_case_workers_presets",
                 CP_CASE_WORKERS_AIMS, catalogue)
    p.duplicate_values("worker_id_duplicate", "worker_id", seed)
    return p.df
