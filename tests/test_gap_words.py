"""A gap in a dataset's supplies is counted in what the dataset owes
(post-build-review #493 M3; Keith, 2026-11-21): a weekly dataset's missed
Mondays are 'Mondays', not 'days' across the whole span; several owed weekdays
are 'owed days'; a daily feed keeps 'days'. The queue's words here and the
page's gapText() say the same."""
import pytest

from qa_tools.common.filing_queue import Gap

#: Mental Health, the weekly dataset this was seen on, is the daily asset's.
pytestmark = pytest.mark.asset("daily")


def _words(periods):
    return Gap(dataset_id="d", periods=tuple(periods), state="open").describe()


def test_a_weekly_datasets_missed_mondays_are_mondays():
    mondays = ["2026-09-21", "2026-09-28", "2026-10-05"]
    assert _words(mondays).startswith("3 Mondays with no supply, ")


def test_several_owed_weekdays_are_owed_days():
    # Monday, Wednesday, Friday, Monday.
    assert _words(["2026-09-21", "2026-09-23", "2026-09-25", "2026-09-28"]).startswith(
        "4 owed days with no supply, ")


def test_a_daily_feed_keeps_days():
    assert _words(["2026-09-21", "2026-09-22", "2026-09-23"]).startswith("3 days with no supply, ")


def test_one_missed_day_is_a_day():
    assert _words(["2026-09-21"]).startswith("1 day with no supply, ")


def test_periods_stay_periods():
    assert _words(["2026-Q1", "2026-Q2"]).startswith("2 periods with no supply, ")
