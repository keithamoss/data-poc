"""Tests for pipeline/cadence.py - real per-dataset delivery cadence
(plans/qa-pipeline.md Phase 5j), replacing AS_OF_OFFSET_DAYS."""
from __future__ import annotations
from datetime import date, datetime, timezone

import pytest

from qa_tools.common import asset_time
from pipeline import cadence
from generator.generate_cp_runs import _quarter_start


DAILY = {"type": "daily", "expected_time": "06:00", "latency_minutes": 60}
WEEKLY_MON = {"type": "weekly", "weekday": 0, "expected_time": "09:00", "latency_minutes": 120}
QUARTERLY = {
    "type": "quarterly", "anchor_months": [2, 5, 8, 11], "day_of_month": 1,
    "expected_time": "09:00", "latency_minutes": 480,
}


def test_cycle_start_daily_is_always_the_given_date():
    assert cadence.cycle_start(DAILY, date(2026, 9, 17)) == date(2026, 9, 17)


def test_cycle_start_weekly_finds_the_most_recent_target_weekday():
    # 2026-09-17 is a Thursday (weekday()==3); most recent Monday (0) before it is 2026-09-14
    assert cadence.cycle_start(WEEKLY_MON, date(2026, 9, 17)) == date(2026, 9, 14)


def test_cycle_start_weekly_on_the_target_weekday_itself():
    monday = date(2026, 9, 14)
    assert cadence.cycle_start(WEEKLY_MON, monday) == monday


def test_cycle_start_quarterly_resolves_the_exact_anchor_month():
    assert cadence.cycle_start(QUARTERLY, date(2026, 8, 1)) == date(2026, 8, 1)
    assert cadence.cycle_start(QUARTERLY, date(2026, 9, 17)) == date(2026, 8, 1)


def test_cycle_start_quarterly_handles_the_year_boundary():
    # a January date's quarter is really the PRIOR November's - same
    # case generate_cp_runs.py's own _quarter_start() was verified
    # against before this generalized it
    assert cadence.cycle_start(QUARTERLY, date(2026, 1, 15)) == date(2025, 11, 1)


def test_cycle_start_quarterly_agrees_with_the_real_generator_function():
    # cadence.cycle_start() generalizes generator/generate_cp_runs.py's
    # own _quarter_start() (hardcoded Feb/May/Aug/Nov, day 1) - for
    # CP's real config, the two must agree exactly across a real range
    # of dates, not just the couple of cases spelled out above.
    d = date(2023, 1, 1)
    end = date(2027, 12, 31)
    step_days = 11  # every 11 days - not a multiple of anything cadence-relevant, so this exercises a real spread of dates without checking all ~1800
    checked = 0
    while d <= end:
        assert cadence.cycle_start(QUARTERLY, d) == _quarter_start(d), f"disagreement at {d}"
        d = date.fromordinal(d.toordinal() + step_days)
        checked += 1
    assert checked > 100


def test_expected_moment_is_the_wall_clock_time_in_the_assets_zone():
    # 09:00 in Perth (UTC+8) on 2026-08-01 -> 01:00 UTC same day.
    # Asserted as a UTC instant deliberately: aware datetimes compare by
    # instant, so this holds whichever zone the value is expressed in,
    # and it is the same number the pre-REQ-PIPE-048 offset arithmetic
    # produced.
    got = cadence.expected_moment(QUARTERLY, date(2026, 8, 1))
    assert got == datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)


def test_expected_moment_rolls_back_a_day_for_early_local_times():
    # 02:00 in Perth is BEFORE midnight UTC the same day - 18:00 UTC the
    # day before. The wrap case generator/daily_batch.py's own comment
    # calls out, where an early expected_time once made "on time"
    # structurally unreachable.
    early_am = {"type": "daily", "expected_time": "02:00", "latency_minutes": 0}
    got = cadence.expected_moment(early_am, date(2026, 8, 1))
    assert got == datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)


def test_classify_arrival_on_time_exactly_at_the_expected_moment():
    ts = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)  # exactly 09:00 AWST
    assert cadence.classify_arrival(QUARTERLY, date(2026, 8, 1), ts) == "onTime"


def test_classify_arrival_late_past_the_grace_window():
    from datetime import timedelta
    ts = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc) + timedelta(minutes=QUARTERLY["latency_minutes"] + 1)
    assert cadence.classify_arrival(QUARTERLY, date(2026, 8, 1), ts) == "late"


def test_classify_arrival_within_grace_window_is_on_time():
    from datetime import timedelta
    ts = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc) + timedelta(minutes=QUARTERLY["latency_minutes"])
    assert cadence.classify_arrival(QUARTERLY, date(2026, 8, 1), ts) == "onTime"


def test_classify_arrival_early_before_the_expected_moment():
    ts = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)  # before 01:00 UTC = 09:00 AWST 1 Aug
    assert cadence.classify_arrival(QUARTERLY, date(2026, 8, 1), ts) == "early"


def test_classify_arrival_refuses_a_naive_timestamp_rather_than_guessing():
    """REQ-PIPE-048 reversed this test's own former assertion, and that
    is the point of it. It used to read
    `test_classify_arrival_handles_naive_timestamps_as_utc` and pass a
    tz-less value expecting "onTime" - pinning the very behaviour the
    requirement is named for. A supply that arrived at 10pm in Perth,
    stored without an offset and read as UTC, is judged against the
    following afternoon.

    Guessing UTC is not safer than guessing local time; it is the same
    mistake with a different sign. So the value is refused, and the
    error names where it came from, because the fix is always at the
    source."""
    ts = datetime(2026, 8, 1, 1, 0)  # no tzinfo
    with pytest.raises(asset_time.NaiveTimestampError) as exc:
        cadence.classify_arrival(QUARTERLY, date(2026, 8, 1), ts,
                                  where="arrival.earliest_extract in run_007/dataset_stats.json")
    assert "run_007/dataset_stats.json" in str(exc.value), "the error must name its source"


def test_classify_arrival_resolves_the_right_cycle_for_a_late_resupply():
    # a resupply dated a few days after the anchor should still resolve
    # to the SAME quarter's expected moment, not roll forward into the
    # next quarter
    from datetime import timedelta
    resupply_date = date(2026, 8, 4)
    ts = datetime(2026, 8, 4, 1, 0, tzinfo=timezone.utc)
    assert cadence.classify_arrival(QUARTERLY, resupply_date, ts) == "late"
    # sanity: still measured against 1 Aug's expected moment, not 4 Aug's
    expected = cadence.expected_moment(QUARTERLY, date(2026, 8, 1))
    assert ts - expected > timedelta(minutes=QUARTERLY["latency_minutes"])


def test_parse_cadence_from_contract_daily(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_text("""
slaProperties:
  - property: cadenceType
    value: daily
  - property: expectedTime
    value: "06:00"
  - property: latency
    value: 60
    unit: min
""")
    got = cadence.parse_cadence_from_contract(str(path))
    assert got == {"type": "daily", "expected_time": "06:00", "latency_minutes": 60}


def test_parse_cadence_from_contract_quarterly(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_text("""
slaProperties:
  - property: cadenceType
    value: quarterly
  - property: cadenceAnchorMonths
    value: "2,5,8,11"
  - property: cadenceDayOfMonth
    value: 1
  - property: expectedTime
    value: "09:00"
  - property: latency
    value: 480
    unit: min
""")
    got = cadence.parse_cadence_from_contract(str(path))
    assert got == {
        "type": "quarterly", "anchor_months": [2, 5, 8, 11], "day_of_month": 1,
        "expected_time": "09:00", "latency_minutes": 480,
    }


def test_parse_cadence_from_contract_weekly(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_text("""
slaProperties:
  - property: cadenceType
    value: weekly
  - property: cadenceWeekday
    value: 0
  - property: expectedTime
    value: "09:00"
  - property: latency
    value: 120
    unit: min
""")
    got = cadence.parse_cadence_from_contract(str(path))
    assert got == {"type": "weekly", "weekday": 0, "expected_time": "09:00", "latency_minutes": 120}
