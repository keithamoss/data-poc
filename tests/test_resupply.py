"""Smoke tests for generator/resupply.py's generic chain-orchestration
logic, using a trivial stub DatasetProvider rather than real data
generation - the whole point of that Protocol boundary (see the module's
own docstring) is that resupply orchestration can be tested without
knowing how a dataset's rows are actually made."""
from __future__ import annotations

import re

from datetime import date

import numpy as np
import pandas as pd

import generator.resupply as resupply
from generator.generate_runs import _manifest_entries_for_slot
from generator.resupply import MAX_ATTEMPTS, Delivery, _add_business_days, run_slot_chain


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
    attempts = list(run_slot_chain(
        StubProvider(), date(2026, 9, 1), seed=1, id_offset=0,
        n_rows=10, first_severity=None, previous_row_count=None,
    ))
    assert len(attempts) == 1
    assert attempts[0].severity is None
    assert attempts[0].received_date == date(2026, 9, 1)
    # A Delivery carries no attempt_number and no is_resupply: they were
    # RETIRED by REQ-GEN-042, not renamed. Whether an arrival is a
    # resupply is observed from its position in the slot, which is what
    # the chain order below already expresses.
    assert not hasattr(attempts[0], "attempt_number")
    assert not hasattr(attempts[0], "is_resupply")


def test_red_delivery_chain_terminates_and_dates_advance_on_business_days():
    attempts = list(run_slot_chain(
        StubProvider(), date(2026, 9, 1), seed=42, id_offset=0,
        n_rows=10, first_severity="red", previous_row_count=None,
    ))
    # Must terminate (either resolves or hits MAX_ATTEMPTS) - this is the
    # real risk with retry/chain logic: an off-by-one in the loop
    # condition could spin forever or never emit anything.
    assert 1 <= len(attempts) <= 8

    assert attempts[0].severity == "red"

    # POSITION IS THE ONLY RESUPPLY MARKER NOW. Everything after the
    # first arrival in a slot IS a resupply, which is exactly why the
    # flag was retired rather than renamed.
    for i, attempt in enumerate(attempts[1:], start=2):
        assert attempt.received_date.weekday() < 5, \
            f"delivery {i} arrived on a weekend: {attempt.received_date}"
        assert attempt.received_date > attempts[i - 2].received_date, \
            "received_date must strictly advance delivery over delivery"

    # Only the final attempt in a resolved chain may be non-red; every
    # attempt before it must be red (that's what triggers the next one).
    for attempt in attempts[:-1]:
        assert attempt.severity == "red"


def test_amber_delivery_never_chains():
    attempts = list(run_slot_chain(
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
    (see resupply.py's run_slot_chain docstring): the pre-fix code
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
    attempts = list(run_slot_chain(
        MarkingStubProvider(), date(2026, 9, 1), seed=1, id_offset=0,
        n_rows=10, first_severity="red", previous_row_count=None,
    ))
    assert len(attempts) == 2
    assert attempts[0].severity == "red"
    assert _is_dirtied(attempts[0].payload)
    assert attempts[1].severity is None
    assert not _is_dirtied(attempts[1].payload), \
        "resolved attempt still carries a dirty marker from the earlier red attempt"


class DictPayloadStubProvider:
    """A payload shaped like Child Protection's own (dict[str, DataFrame],
    one entry per real table) rather than Birth Registrations' bare
    DataFrame - real coverage for resupply.py's 2026-09-18 genericization
    (DatasetProvider/Delivery/run_slot_chain over T), not just
    inferred from generate_cp_runs.py's own integration test."""

    def generate(self, run_date, seed, n_rows, id_offset):
        return {"a": pd.DataFrame({"id": range(n_rows)}), "b": pd.DataFrame({"id": range(n_rows)})}

    def dirty(self, payload, severity, seed, previous_row_count):
        out = dict(payload)
        for name, df in out.items():
            marked = df.copy()
            marked["dirtied"] = True
            out[name] = marked
        return out

    def churn(self, payload, seed, run_date, id_offset):
        return {name: df.copy() for name, df in payload.items()}


def test_run_slot_chain_works_with_a_dict_of_tables_payload(monkeypatch):
    monkeypatch.setattr(resupply, "STILL_RED_PROB", 0.0)
    attempts = list(run_slot_chain(
        DictPayloadStubProvider(), date(2026, 9, 1), seed=1, id_offset=0,
        n_rows=10, first_severity="red", previous_row_count=None,
    ))
    assert len(attempts) == 2
    assert set(attempts[0].payload.keys()) == {"a", "b"}
    assert "dirtied" in attempts[0].payload["a"].columns
    assert "dirtied" not in attempts[1].payload["a"].columns, \
        "resolved attempt still carries a dirty marker from the earlier red attempt"


def test_run_slot_chain_accepts_a_custom_delay_curve():
    # A curve entirely OUTSIDE resupply.py's own default 1-10 day range -
    # if the custom delay_days/delay_weights weren't actually threaded
    # through, every arrived_date would still land within that default
    # range, which this test would never observe over enough seeds.
    custom_days = np.array([15, 20])
    custom_weights = np.array([0.5, 0.5])
    delivery_date = date(2026, 9, 1)

    saw_a_custom_range_delay = False
    for seed in range(30):
        attempts = list(run_slot_chain(
            StubProvider(), delivery_date, seed=seed, id_offset=0,
            n_rows=10, first_severity="red", previous_row_count=None,
            delay_days=custom_days, delay_weights=custom_weights,
        ))
        if len(attempts) > 1:
            gap = (attempts[1].received_date - delivery_date).days
            assert gap >= 15, f"seed={seed}: resupply arrived after only {gap} calendar days, outside the custom curve"
            saw_a_custom_range_delay = True
    assert saw_a_custom_range_delay, "no seed in this range produced a resupply to actually check the custom curve"


def test_always_red_chain_terminates_at_max_attempts(monkeypatch):
    # Forcing STILL_RED_PROB to 1 makes every resupply also red, so the
    # chain can only stop by hitting the hard MAX_ATTEMPTS ceiling - a
    # precise check (exact length, every attempt red) rather than the
    # loose 1 <= len <= 8 bound the earlier chain test uses.
    monkeypatch.setattr(resupply, "STILL_RED_PROB", 1.0)
    attempts = list(run_slot_chain(
        StubProvider(), date(2026, 9, 1), seed=3, id_offset=0,
        n_rows=10, first_severity="red", previous_row_count=None,
    ))
    assert len(attempts) == MAX_ATTEMPTS
    assert all(attempt.severity == "red" for attempt in attempts)


def test_same_seed_produces_identical_chain():
    def run():
        return list(run_slot_chain(
            MarkingStubProvider(), date(2026, 9, 1), seed=99, id_offset=0,
            n_rows=10, first_severity="red", previous_row_count=None,
        ))

    attempts_a, attempts_b = run(), run()
    assert len(attempts_a) == len(attempts_b)
    for a, b in zip(attempts_a, attempts_b):
        assert a.received_date == b.received_date
        assert a.severity == b.severity
        pd.testing.assert_frame_equal(a.payload.reset_index(drop=True), b.payload.reset_index(drop=True))


def _fake_delivery(received_date, severity, n_rows=5):
    return Delivery(received_date, severity, pd.DataFrame({"id": range(n_rows)}))


def test_every_delivery_filling_one_slot_names_that_slot_and_its_period():
    """One slot, many deliveries - the whole vocabulary change in one
    assertion. These used to share a `delivery_id` and a
    `delivery_date`, which is what made the word mean two things."""
    deliveries = [
        _fake_delivery(date(2026, 9, 1), "red"),
        _fake_delivery(date(2026, 9, 3), None),
    ]
    entries = _manifest_entries_for_slot(
        deliveries, slot_id="slot_006", period="2026-09-01",
        run_index_start=10, id_offset=600_000, seed=1006,
    )
    assert len(entries) == 2
    assert all(entry["slot_id"] == "slot_006" for entry in entries)
    assert all(entry["period"] == "2026-09-01" for entry in entries)
    assert all(entry["id_offset"] == 600_000 and entry["seed"] == 1006 for entry in entries)


def test_run_ids_carry_no_date_and_no_resupply_marker():
    """The identity half of REQ-GEN-042. These used to read
    `run_006_2026-09-01_resupply2`, which is why regenerating on a
    different calendar day wrote a whole second history beside the
    first rather than replacing it."""
    deliveries = [
        _fake_delivery(date(2026, 9, 1), "red"),
        _fake_delivery(date(2026, 9, 3), "red"),
        _fake_delivery(date(2026, 9, 8), None),
    ]
    entries = _manifest_entries_for_slot(
        deliveries, slot_id="slot_006", period="2026-09-01",
        run_index_start=10, id_offset=600_000, seed=1006,
    )
    assert [entry["run_id"] for entry in entries] == ["run_011", "run_012", "run_013"]
    assert [entry["run_index"] for entry in entries] == [11, 12, 13]
    assert [entry["dirty_severity"] for entry in entries] == ["red", "red", None]
    for entry in entries:
        assert "resupply" not in entry["run_id"]
        assert not re.search(r"\d{4}-\d{2}-\d{2}", entry["run_id"]), \
            f"{entry['run_id']} still carries a date"


def test_no_manifest_entry_carries_a_retired_field():
    """The NFR stated directly: nothing in the repo should be able to
    use the retired sense of "delivery" after this, and a grep for the
    old field names should come back empty. Asserted here on real
    output rather than trusted to a grep somebody remembers to run."""
    entries = _manifest_entries_for_slot(
        [_fake_delivery(date(2026, 9, 1), None)], slot_id="slot_001", period="2026-09-01",
        run_index_start=0, id_offset=0, seed=1,
    )
    for retired in ("delivery_id", "delivery_date", "attempt_number",
                    "is_resupply", "supersedes_run_id", "arrived_date"):
        assert retired not in entries[0], f"{retired} came back"
    for retired in ("slot_delivery_id", "slot_attempt_number", "slot_is_resupply"):
        assert retired not in entries[0], f"{retired} - retired fields must not return under a slot_ prefix"
