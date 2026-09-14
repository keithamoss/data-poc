"""Smoke tests for generator/resupply.py's generic chain-orchestration
logic, using a trivial stub DatasetProvider rather than real data
generation - the whole point of that Protocol boundary (see the module's
own docstring) is that resupply orchestration can be tested without
knowing how a dataset's rows are actually made."""
from __future__ import annotations

from datetime import date

import pandas as pd

from resupply import _add_business_days, run_delivery_chain


def test_add_business_days_skips_weekends():
    # 2026-09-04 is a Friday
    assert _add_business_days(date(2026, 9, 4), 1) == date(2026, 9, 7)  # Monday
    assert _add_business_days(date(2026, 9, 4), 2) == date(2026, 9, 8)  # Tuesday
    for n in range(1, 15):
        result = _add_business_days(date(2026, 9, 1), n)
        assert result.weekday() < 5, f"{result} (n={n}) landed on a weekend"


class StubProvider:
    """Deterministic - no randomness, no real generation - just enough to
    exercise the chain-walking logic itself."""

    def generate(self, run_date, seed, n_rows, id_offset):
        return pd.DataFrame({"id": range(n_rows)})

    def dirty(self, df, severity, seed, previous_row_count):
        return df

    def churn(self, df, seed, run_date, id_offset):
        return df


def test_clean_delivery_yields_exactly_one_attempt():
    attempts = list(run_delivery_chain(
        StubProvider(), date(2026, 9, 1), seed=1, id_offset=0,
        n_rows=10, first_severity=None, previous_row_count=None,
    ))
    assert len(attempts) == 1
    assert attempts[0].attempt_number == 1
    assert attempts[0].is_resupply is False
    assert attempts[0].severity is None
    assert attempts[0].arrived_date == date(2026, 9, 1)


def test_red_delivery_chain_terminates_and_dates_advance_on_business_days():
    attempts = list(run_delivery_chain(
        StubProvider(), date(2026, 9, 1), seed=42, id_offset=0,
        n_rows=10, first_severity="red", previous_row_count=None,
    ))
    # Must terminate (either resolves or hits MAX_ATTEMPTS) - this is the
    # real risk with retry/chain logic: an off-by-one in the loop
    # condition could spin forever or never emit anything.
    assert 1 <= len(attempts) <= 8

    assert attempts[0].attempt_number == 1
    assert attempts[0].is_resupply is False
    assert attempts[0].severity == "red"

    for i, attempt in enumerate(attempts[1:], start=2):
        assert attempt.attempt_number == i
        assert attempt.is_resupply is True
        assert attempt.arrived_date.weekday() < 5, \
            f"attempt {i} arrived on a weekend: {attempt.arrived_date}"
        assert attempt.arrived_date > attempts[i - 2].arrived_date, \
            "arrived_date must strictly advance attempt over attempt"

    # Only the final attempt in a resolved chain may be non-red; every
    # attempt before it must be red (that's what triggers the next one).
    for attempt in attempts[:-1]:
        assert attempt.severity == "red"


def test_amber_delivery_never_chains():
    attempts = list(run_delivery_chain(
        StubProvider(), date(2026, 9, 1), seed=7, id_offset=0,
        n_rows=10, first_severity="amber", previous_row_count=None,
    ))
    assert len(attempts) == 1
    assert attempts[0].severity == "amber"
