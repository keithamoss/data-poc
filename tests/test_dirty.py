"""Regression test for a real bug found while calibrating the new suburb/
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

Fixed by dropping "N/A" from both pools (see dirty.py's own comments)."""
from __future__ import annotations

import io

import pandas as pd

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
