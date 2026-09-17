"""Smoke tests for generator/resupply.py's generic chain-orchestration
logic, using a trivial stub DatasetProvider rather than real data
generation - the whole point of that Protocol boundary (see the module's
own docstring) is that resupply orchestration can be tested without
knowing how a dataset's rows are actually made."""
from __future__ import annotations

from datetime import date

import pandas as pd

import generator.resupply as resupply
from generator.generate_runs import _manifest_entries_for_delivery
from generator.resupply import MAX_ATTEMPTS, Attempt, _add_business_days, run_delivery_chain


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


class MarkingStubProvider:
    """Like StubProvider, but dirty() leaves a detectable, persistent
    marker on the rows it touches, and churn() carries that marker
    forward unchanged - lets a test assert defect-freedom on resolution
    (a resolved attempt's df must carry NO marker) instead of just
    checking chain shape. Real regression coverage for the 2026-09-15 bug
    (see resupply.py's run_delivery_chain docstring): the pre-fix code
    threaded a single `df` through the whole loop, so a resolved attempt
    could still carry a marker set by an earlier red attempt in the same
    chain, rather than being a fresh view of the (never-dirtied) clean
    lineage."""

    def generate(self, run_date, seed, n_rows, id_offset):
        return pd.DataFrame({"id": range(n_rows)})

    def dirty(self, df, severity, seed, previous_row_count):
        out = df.copy()
        out["dirtied"] = True
        return out

    def churn(self, df, seed, run_date, id_offset):
        return df.copy()


def _is_dirtied(df: pd.DataFrame) -> bool:
    return "dirtied" in df.columns and bool(df["dirtied"].any())


def test_resolved_attempt_carries_no_dirty_marker(monkeypatch):
    # Forcing STILL_RED_PROB to 0 makes the resupply deterministically
    # resolve, giving an exact 2-attempt chain: [red, resolved]. Before
    # the 2026-09-15 fix, the resolved attempt's df was `churn(df)` of
    # the SAME df the red attempt had already been dirty()'d into, so it
    # still carried the marker - this is the exact defect this test
    # exists to catch (see plans/qa-pipeline.md #31).
    monkeypatch.setattr(resupply, "STILL_RED_PROB", 0.0)
    attempts = list(run_delivery_chain(
        MarkingStubProvider(), date(2026, 9, 1), seed=1, id_offset=0,
        n_rows=10, first_severity="red", previous_row_count=None,
    ))
    assert len(attempts) == 2
    assert attempts[0].severity == "red"
    assert _is_dirtied(attempts[0].df)
    assert attempts[1].severity is None
    assert not _is_dirtied(attempts[1].df), \
        "resolved attempt still carries a dirty marker from the earlier red attempt"


def test_always_red_chain_terminates_at_max_attempts(monkeypatch):
    # Forcing STILL_RED_PROB to 1 makes every resupply also red, so the
    # chain can only stop by hitting the hard MAX_ATTEMPTS ceiling - a
    # precise check (exact length, every attempt red) rather than the
    # loose 1 <= len <= 8 bound the earlier chain test uses.
    monkeypatch.setattr(resupply, "STILL_RED_PROB", 1.0)
    attempts = list(run_delivery_chain(
        StubProvider(), date(2026, 9, 1), seed=3, id_offset=0,
        n_rows=10, first_severity="red", previous_row_count=None,
    ))
    assert len(attempts) == MAX_ATTEMPTS
    assert all(attempt.severity == "red" for attempt in attempts)
    assert attempts[-1].attempt_number == MAX_ATTEMPTS


def test_same_seed_produces_identical_chain():
    def run():
        return list(run_delivery_chain(
            MarkingStubProvider(), date(2026, 9, 1), seed=99, id_offset=0,
            n_rows=10, first_severity="red", previous_row_count=None,
        ))

    attempts_a, attempts_b = run(), run()
    assert len(attempts_a) == len(attempts_b)
    for a, b in zip(attempts_a, attempts_b):
        assert a.attempt_number == b.attempt_number
        assert a.arrived_date == b.arrived_date
        assert a.is_resupply == b.is_resupply
        assert a.severity == b.severity
        pd.testing.assert_frame_equal(a.df.reset_index(drop=True), b.df.reset_index(drop=True))


def _fake_attempt(attempt_number, arrived_date, is_resupply, severity, n_rows=5):
    return Attempt(attempt_number, arrived_date, is_resupply, severity,
                    pd.DataFrame({"id": range(n_rows)}))


def test_manifest_entries_share_delivery_id_and_date():
    attempts = [
        _fake_attempt(1, date(2026, 9, 1), False, "red"),
        _fake_attempt(2, date(2026, 9, 3), True, None),
    ]
    entries = _manifest_entries_for_delivery(
        attempts, i=6, delivery_id="delivery_06", delivery_date=date(2026, 9, 1),
        run_index_start=10, id_offset=600_000, seed=1006,
    )
    assert len(entries) == 2
    assert all(entry["delivery_id"] == "delivery_06" for entry in entries)
    assert all(entry["delivery_date"] == "2026-09-01" for entry in entries)
    assert all(entry["id_offset"] == 600_000 and entry["seed"] == 1006 for entry in entries)


def test_manifest_entries_chain_run_ids_and_supersedes():
    attempts = [
        _fake_attempt(1, date(2026, 9, 1), False, "red"),
        _fake_attempt(2, date(2026, 9, 3), True, "red"),
        _fake_attempt(3, date(2026, 9, 8), True, None),
    ]
    entries = _manifest_entries_for_delivery(
        attempts, i=6, delivery_id="delivery_06", delivery_date=date(2026, 9, 1),
        run_index_start=10, id_offset=600_000, seed=1006,
    )
    assert [entry["run_id"] for entry in entries] == [
        "run_006_2026-09-01", "run_006_2026-09-01_resupply1", "run_006_2026-09-01_resupply2",
    ]
    assert entries[0]["supersedes_run_id"] is None
    assert entries[1]["supersedes_run_id"] == entries[0]["run_id"]
    assert entries[2]["supersedes_run_id"] == entries[1]["run_id"]
    assert [entry["run_index"] for entry in entries] == [11, 12, 13]
    assert [entry["dirty_severity"] for entry in entries] == ["red", "red", None]
    assert [entry["is_resupply"] for entry in entries] == [False, True, True]
