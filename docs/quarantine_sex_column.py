#!/usr/bin/env python3
"""
Row-level quarantine for the `sex` column of the BDM birth-registrations feed.

Demonstrates the two behaviors discussed alongside the Soda Core traffic-light
checks (bdm-birth-registrations-soda-checks.yml):

  - quarantine:  split the batch - valid rows proceed, invalid rows are
                 written to a separate dead-letter table, nothing blocks.
  - block_run:   any invalid row aborts the whole batch - nothing loads.

Which one applies is configurable per check via ON_FAIL below, mirroring the
red/amber/green thresholds in the Soda file: below WARN_THRESHOLD is green,
between WARN and FAIL is amber (quarantine still happens, just louder), at or
above FAIL_THRESHOLD is treated as the harder failure.

This part - the actual split - is plain pandas and IS executed/tested below.
The section at the bottom shows how the same boolean mask would come from
Great Expectations' `unexpected_index_list` instead of a hand-written mask;
that part is written to match the documented GX 1.x API but NOT executed -
great_expectations isn't pip-installable in this environment (same
network-constraints note as the rest of this thread). Confirm it against a
real GX install before relying on it.
"""

from __future__ import annotations

import pandas as pd

VALID_SEX_VALUES = {"M", "F", "X"}
WARN_THRESHOLD = 0.0    # >0% invalid -> amber
FAIL_THRESHOLD = 0.02   # >2% invalid -> red
ON_FAIL = "quarantine"  # "quarantine" or "block_run" - the per-check policy


class ContractViolation(Exception):
    """Raised when ON_FAIL == 'block_run' and the fail threshold is breached."""


def split_by_validity(df: pd.DataFrame, column: str, valid_values: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (valid_rows, invalid_rows) based on set membership - the same
    check Soda's `invalid_percent(sex)` runs, just as a row-level Python mask
    instead of an aggregate SQL metric."""
    is_valid = df[column].isin(valid_values)
    return df[is_valid].copy(), df[~is_valid].copy()


def traffic_light(invalid_rate: float) -> str:
    if invalid_rate > FAIL_THRESHOLD:
        return "red"
    if invalid_rate > WARN_THRESHOLD:
        return "amber"
    return "green"


def process_batch(df: pd.DataFrame, column: str = "sex", on_fail: str = ON_FAIL) -> pd.DataFrame:
    valid_rows, invalid_rows = split_by_validity(df, column, VALID_SEX_VALUES)
    invalid_rate = len(invalid_rows) / len(df) if len(df) else 0.0
    status = traffic_light(invalid_rate)

    print(f"[{status.upper()}] {column}: {len(invalid_rows)}/{len(df)} invalid ({invalid_rate:.1%})")
    if not invalid_rows.empty:
        print(f"  invalid values seen: {sorted(invalid_rows[column].unique())}")

    if status == "red" and on_fail == "block_run":
        raise ContractViolation(
            f"{column}: {invalid_rate:.1%} invalid exceeds fail threshold "
            f"({FAIL_THRESHOLD:.1%}) and on_fail='block_run' - aborting, nothing loads."
        )

    # quarantine path (also taken for amber, and for red when ON_FAIL='quarantine'):
    # valid rows proceed untouched; invalid rows are routed elsewhere instead
    # of silently riding along in the main table or silently being dropped.
    if not invalid_rows.empty:
        invalid_rows.to_csv("quarantine_sex.csv", mode="a", header=False, index=False)
        print(f"  -> {len(invalid_rows)} row(s) written to quarantine_sex.csv")

    return valid_rows  # this is what actually proceeds to the main table


def make_batch(n_invalid: int, n_total: int = 200) -> pd.DataFrame:
    n_valid = n_total - n_invalid
    sex = (["M", "F"] * ((n_valid + 1) // 2))[:n_valid] + ["U"] * n_invalid
    return pd.DataFrame({
        "registration_number": [f"BDM-{100000000 + i}" for i in range(n_total)],
        "sex": sex,
    })


if __name__ == "__main__":
    print("--- scenario 1: green (0 invalid) ---")
    process_batch(make_batch(n_invalid=0))

    print("\n--- scenario 2: amber (1/200 = 0.5% invalid, above warn, below fail) ---")
    process_batch(make_batch(n_invalid=1))

    print("\n--- scenario 3: red, on_fail='quarantine' (6/200 = 3% invalid) ---")
    valid = process_batch(make_batch(n_invalid=6), on_fail="quarantine")
    print(f"    {len(valid)} row(s) still proceed to the main table despite the red status.")

    print("\n--- scenario 4: red, on_fail='block_run' (6/200 = 3% invalid) ---")
    try:
        process_batch(make_batch(n_invalid=6), on_fail="block_run")
    except ContractViolation as e:
        print(f"    aborted, as expected: {e}")


# ---------------------------------------------------------------------------
# How this maps onto Great Expectations, for reference.
#
# NOT executed - great_expectations isn't pip-installable in this
# environment, so this is written to match the documented GX 1.x API rather
# than a script that's actually been run. Confirm it against a real
# installation before relying on it; treat split_by_validity() above (plain
# pandas, executed and tested) as the part you can trust as-is.
#
# The one thing GX gets you that the hand-written mask above doesn't: the
# same expectation you'd already be running for CI-gate validation (per the
# ODCS/Soda checks) can hand back the failing row indices directly, so you
# aren't maintaining the valid-values list in two places.
#
#   import great_expectations as gx
#
#   context = gx.get_context()
#   validator = context.sources.pandas_default.read_dataframe(df)
#
#   result = validator.expect_column_values_to_be_in_set(
#       column="sex",
#       value_set=["M", "F", "X"],
#       result_format="COMPLETE",   # needed to get unexpected_index_list back
#   )
#
#   bad_indices = result.result["unexpected_index_list"]
#   invalid_rows = df.loc[bad_indices]
#   valid_rows = df.drop(index=bad_indices)
#
# From there, the red/amber/green and quarantine/block_run logic above
# applies unchanged - it only cares about the valid/invalid split, not which
# tool produced it.
# ---------------------------------------------------------------------------
