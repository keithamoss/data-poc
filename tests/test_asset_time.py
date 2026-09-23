"""Tests for qa_tools/common/asset_time.py - the asset's own clock
(REQ-PIPE-048).

Tested against the REAL contract/data-asset.yaml wherever the real
value matters, for the same reason tests/test_hierarchy.py gives: a
fixture would let the module and the real config drift apart while
every test stayed green. tmp_path is used only for the cases the real
file must never contain - a missing timezone, an invented zone name.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from qa_tools.common import asset_time


@pytest.fixture(autouse=True)
def _clear_cache():
    asset_time.asset_timezone.cache_clear()
    yield
    asset_time.asset_timezone.cache_clear()


def _repoint(tmp_path, monkeypatch, text):
    path = tmp_path / "data-asset.yaml"
    path.write_text(text)
    monkeypatch.setattr(asset_time, "DATA_ASSET_YAML", path)
    asset_time.asset_timezone.cache_clear()


class TestTheConfiguredZone:
    def test_it_reads_the_real_asset_timezone(self):
        assert asset_time.asset_timezone().key == "Australia/Perth"

    def test_now_is_aware_and_on_the_assets_clock(self):
        got = asset_time.now()
        assert got.tzinfo is not None
        assert got.utcoffset() == timedelta(hours=8)

    def test_a_missing_timezone_is_an_error_not_a_fallback(self, tmp_path, monkeypatch):
        """There is deliberately nothing to fall back TO - this
        requirement removed every hardcoded offset, and a default would
        put one back where nobody would look for it."""
        _repoint(tmp_path, monkeypatch, "data_asset_id: a\n")
        with pytest.raises(ValueError, match="timezone"):
            asset_time.asset_timezone()

    def test_a_zone_that_is_not_an_iana_name_is_named_in_the_error(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, "data_asset_id: a\ntimezone: AWST+8\n")
        with pytest.raises(ValueError, match="AWST"):
            asset_time.asset_timezone()


class TestParseInstant:
    def test_an_aware_string_round_trips(self):
        assert asset_time.parse_instant("2026-09-01T06:00:00+00:00", "x") == \
            datetime(2026, 9, 1, 6, 0, tzinfo=UTC)

    def test_a_duckdb_style_space_separator_is_accepted(self):
        assert asset_time.parse_instant("2026-09-01 06:00:00+00:00", "x") == \
            datetime(2026, 9, 1, 6, 0, tzinfo=UTC)

    def test_an_aware_datetime_is_returned_as_is(self):
        value = datetime(2026, 9, 1, 14, 0, tzinfo=asset_time.asset_timezone())
        assert asset_time.parse_instant(value, "x") is value

    def test_a_naive_value_raises_rather_than_being_guessed(self):
        with pytest.raises(asset_time.NaiveTimestampError):
            asset_time.parse_instant("2026-09-01T06:00:00", "x")

    def test_the_error_names_where_the_value_came_from(self):
        """A validation error a reader cannot act on is barely better
        than none, and the fix for this one is always at the source."""
        with pytest.raises(asset_time.NaiveTimestampError) as exc:
            asset_time.parse_instant(datetime(2026, 9, 1), "arrival.earliest_extract in run_007")
        assert "run_007" in str(exc.value)

    def test_the_error_rules_out_both_guesses_explicitly(self):
        """Saying only "no offset" invites the reader to assume UTC,
        which is the bug. The message names both readings it refuses."""
        with pytest.raises(asset_time.NaiveTimestampError) as exc:
            asset_time.parse_instant("2026-09-01T06:00:00", "x")
        message = str(exc.value)
        assert "UTC" in message and "Australia/Perth" in message

    def test_something_that_is_not_a_timestamp_at_all_says_so(self):
        with pytest.raises(ValueError, match="not an ISO timestamp"):
            asset_time.parse_instant("last Tuesday", "x")


class TestRecordSourceInstant:
    """The one place an assumption is allowed - see the module's own
    note on why its location is what makes it legitimate."""

    def test_a_naked_source_value_is_recorded_as_utc_and_says_so(self):
        assert asset_time.record_source_instant("2026-06-01 06:30:00", "x") == \
            "2026-06-01T06:30:00+00:00"

    def test_an_offset_the_supplier_stated_is_not_overwritten(self):
        """If a supplier ever does send an offset, it is theirs to state."""
        assert asset_time.record_source_instant("2026-06-01T06:30:00+08:00", "x") == \
            "2026-06-01T06:30:00+08:00"

    def test_a_missing_value_stays_missing(self):
        """A dataset with no rows must stay distinguishable from one
        that arrived at midnight."""
        assert asset_time.record_source_instant(None, "x") is None
        assert asset_time.record_source_instant("", "x") is None

    def test_what_it_records_is_readable_back_by_the_strict_parser(self):
        """The two halves of criterion 3 and 4 meeting: anything this
        writes must survive the loud reader, or the pipeline fails on
        its own output."""
        written = asset_time.record_source_instant("2026-06-01 06:30:00", "x")
        assert asset_time.parse_instant(written, "x") == datetime(2026, 6, 1, 6, 30, tzinfo=UTC)


class TestDatesAsInstants:
    def test_a_wall_clock_time_resolves_on_the_assets_clock(self):
        assert asset_time.wall_clock(date(2026, 9, 1), "14:00") == \
            datetime(2026, 9, 1, 6, 0, tzinfo=UTC)

    def test_end_of_day_is_the_last_instant_of_that_date_locally(self):
        got = asset_time.end_of_day(date(2026, 9, 1))
        assert got.utcoffset() == timedelta(hours=8)
        assert (got + timedelta(microseconds=1)) == asset_time.start_of_day(date(2026, 9, 2))

    def test_end_of_day_is_after_every_moment_of_its_own_day(self):
        """Criterion 6's actual purpose: a run at any hour of the as-of
        date counts as on or before it."""
        day = date(2026, 9, 1)
        end = asset_time.end_of_day(day)
        for hour in (0, 9, 14, 23):
            assert asset_time.wall_clock(day, f"{hour:02d}:00") <= end

    def test_as_of_instant_is_end_of_day_under_a_name_that_says_so(self):
        assert asset_time.as_of_instant(date(2026, 9, 1)) == asset_time.end_of_day(date(2026, 9, 1))

    def test_localise_changes_the_clock_not_the_instant(self):
        utc = datetime(2026, 9, 1, 6, 0, tzinfo=UTC)
        got = asset_time.localise(utc)
        assert got == utc
        assert got.hour == 14, "the same instant read on the asset's own clock"

    def test_localise_refuses_a_naive_value_like_everything_else(self):
        with pytest.raises(asset_time.NaiveTimestampError):
            asset_time.localise(datetime(2026, 9, 1, 6, 0))


class TestIsoformat:
    def test_it_refuses_to_serialise_a_naive_instant(self):
        """Storing one is what criterion 3 forbids, and the loud failure
        would otherwise land years later on whoever read the file."""
        with pytest.raises(asset_time.NaiveTimestampError):
            asset_time.isoformat(datetime(2026, 9, 1, 6, 0))

    def test_an_aware_instant_serialises_with_its_offset(self):
        assert asset_time.isoformat(datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc)).endswith("+00:00")
