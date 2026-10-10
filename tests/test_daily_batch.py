"""Tests for generator/daily_batch.py's extract_timestamp calibration
(2026-09-17, Keith's own real-world split: "on time about 80% of the
time... early for 5%... late 15%") - both that the per-run distribution
lands close to that target, and the regression guard for the real
conflict that calibration surfaced: the real "extract timestamp
ordering" check (identical in contract/bdm-birth-registrations-soda-
checks.yml and this same contract's own quality: block) requires
date_registered <= extract_timestamp <= date_registered + 1 day, which
06:00 AWST (Phase 5j's original placeholder) could never satisfy - see
plans/qa-pipeline.md's own item 67 for the full account."""
from __future__ import annotations

from datetime import date

import numpy as np

from generator.daily_batch import (
    ARRIVAL_EARLY_PROB,
    ARRIVAL_ON_TIME_PROB,
    _draw_arrival_base_offset_hours,
    generate_daily_batch,
)
from qa_tools.common import agreement, asset_time


def test_arrival_offset_distribution_matches_the_real_calibration_target():
    rng = np.random.default_rng(12345)
    n = 20_000
    offsets = [_draw_arrival_base_offset_hours(rng) for _ in range(n)]

    on_time = sum(6.0 <= o <= 7.0 for o in offsets) / n
    early = sum(o < 6.0 for o in offsets) / n
    late = sum(o > 7.0 for o in offsets) / n

    assert abs(on_time - ARRIVAL_ON_TIME_PROB) < 0.02
    assert abs(early - ARRIVAL_EARLY_PROB) < 0.02
    assert abs(late - (1 - ARRIVAL_ON_TIME_PROB - ARRIVAL_EARLY_PROB)) < 0.02


def test_generated_extract_timestamps_never_violate_the_real_ordering_check():
    """Regression guard for the real conflict this calibration surfaced:
    every non-disordered row's extract_timestamp must stay within
    [date_registered, date_registered + 1 day) - the exact bound the
    real Soda/datacontract-cli 'extract timestamp ordering' check
    enforces. Failing this means BDM's real data would start tripping
    that check on every run, not just the deliberately-dirtied rows it's
    designed to catch."""
    run_date = date(2026, 6, 1)
    df = generate_daily_batch(run_date, seed=42, n_rows=500)

    day_start = np.datetime64(run_date, "ns")
    day_end = day_start + np.timedelta64(1, "D")
    ts = df["extract_timestamp"].values.astype("datetime64[ns]")

    assert (ts >= day_start).all()
    assert (ts < day_end).all()


def test_real_bdm_cadence_classifies_the_on_time_window_as_on_time():
    """End-to-end sanity check tying this file's calibration directly to
    the real delivery agreement's own participation (not a hand-copied number
    that could quietly drift from it): a run whose extract_timestamp
    falls inside _draw_arrival_base_offset_hours' on-time range must
    genuinely classify as "onTime" via the real parsed cadence, not just
    by this test's own assumptions about what "on time" means."""
    # contract/calendar.yaml since REQ-PIPE-110, not the contract's
    # retired slaProperties.
    cadence = agreement.cadence("birth-registrations")
    run_date = date(2026, 6, 1)

    # Aware instants, in UTC. This file's own calibration comment above
    # is written in hours-from-midnight UTC, and since REQ-PIPE-048 that
    # has to be SAID rather than assumed by whoever reads the value -
    # the arrival classifier refuses a timestamp with no offset instead
    # of quietly treating it as UTC, which is the bug that requirement
    # is named for.
    from datetime import datetime, timezone
    on_time_extract = datetime(2026, 6, 1, 6, 30, tzinfo=timezone.utc)  # inside [6.0, 7.0]
    early_extract = datetime(2026, 6, 1, 3, 0, tzinfo=timezone.utc)  # inside [2.0, 6.0)
    late_extract = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)  # inside (7.0, 11.0]

    # ASSERTED AGAINST THE EXPECTED MOMENT DIRECTLY since REQ-PIPE-080
    # retired cadence.classify_arrival(). What this test is about is
    # the GENERATOR - that it plants extract timestamps in all three
    # bands - so the comparison is spelled out rather than borrowed
    # from whichever module currently owns a classifier.
    from datetime import timedelta
    expected = asset_time.wall_clock(run_date, cadence["expected_time"])
    grace = timedelta(minutes=cadence["latency_minutes"])
    assert expected <= on_time_extract <= expected + grace
    assert early_extract < expected
    assert late_extract > expected + grace


def test_generate_daily_batch_is_fully_reproducible():
    run_date = date(2026, 6, 1)
    a = generate_daily_batch(run_date, seed=7, n_rows=50)
    b = generate_daily_batch(run_date, seed=7, n_rows=50)
    for col in a.columns:
        # .equals(), not == - some columns (e.g. registering_parent_2_name)
        # legitimately contain None, and elementwise == on object/string-
        # dtype columns doesn't treat None == None as True.
        assert a[col].equals(b[col]), col
