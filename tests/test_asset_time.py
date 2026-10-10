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
    asset_time.timezone_versions.cache_clear()
    yield
    asset_time.timezone_versions.cache_clear()


def _repoint(tmp_path, monkeypatch, text):
    path = tmp_path / "data-asset.yaml"
    path.write_text(text)
    monkeypatch.setattr(asset_time, "DATA_ASSET_YAML", path)
    asset_time.timezone_versions.cache_clear()


def _versions(*pairs) -> str:
    """A data-asset.yaml naming only timezone versions: (from, zone) pairs."""
    body = "".join(
        f"    - effective_from: \"{start}\"\n      zone: {zone}\n      changelog:\n"
        f"        - {{date: \"{start}\", author: pytest, change: test}}\n"
        for start, zone in pairs)
    return f"data_asset_id: a\ntimezone:\n  versions:\n{body}"


class TestTheConfiguredZone:
    def test_it_reads_the_real_asset_timezone(self):
        assert asset_time.zone_on(date(2026, 9, 1)).key == "Australia/Perth"
        assert asset_time.zone_now().key == "Australia/Perth"

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
            asset_time.zone_now()

    def test_a_zone_that_is_not_an_iana_name_is_named_in_the_error(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _versions(("1970-01-01", "AWST")))
        with pytest.raises(ValueError, match="AWST"):
            asset_time.zone_now()


class TestParseInstant:
    def test_an_aware_string_round_trips(self):
        assert asset_time.parse_instant("2026-09-01T06:00:00+00:00", "x") == \
            datetime(2026, 9, 1, 6, 0, tzinfo=UTC)

    def test_a_duckdb_style_space_separator_is_accepted(self):
        assert asset_time.parse_instant("2026-09-01 06:00:00+00:00", "x") == \
            datetime(2026, 9, 1, 6, 0, tzinfo=UTC)

    def test_an_aware_datetime_is_returned_as_is(self):
        value = datetime(2026, 9, 1, 14, 0, tzinfo=asset_time.zone_on(date(2026, 9, 1)))
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


class TestTheTimezoneIsVersioned:
    """REQ-PIPE-112: every reader asks 'as at when', and a date no version
    covers is an error rather than the nearest version."""

    def test_a_single_unversioned_value_is_refused(self, tmp_path, monkeypatch):
        """Criterion 1 - the old `timezone: <name>` shape is not read."""
        _repoint(tmp_path, monkeypatch, "data_asset_id: a\ntimezone: Australia/Perth\n")
        with pytest.raises(ValueError, match="effective-dated versions"):
            asset_time.zone_now()

    def test_a_fixed_utc_offset_is_refused(self, tmp_path, monkeypatch):
        """Criterion 1 - an offset is one zone's answer for one moment."""
        _repoint(tmp_path, monkeypatch, _versions(("1970-01-01", "+08:00")))
        with pytest.raises(ValueError, match="fixed UTC offset"):
            asset_time.zone_now()

    def test_there_is_no_bare_lookup(self):
        """Criterion 6 and NFR 2: removed, not deprecated."""
        assert not hasattr(asset_time, "asset_timezone")

    def test_each_date_reads_its_own_version(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _versions(("2020-01-01", "Australia/Perth"),
                                                  ("2027-01-01", "Australia/Sydney")))
        assert asset_time.zone_on(date(2026, 12, 31)).key == "Australia/Perth"
        assert asset_time.zone_on(date(2027, 1, 1)).key == "Australia/Sydney"
        # A wall-clock time is read in the zone in force on ITS date (criterion 3).
        assert asset_time.wall_clock(date(2026, 12, 31), "09:00").utcoffset() == timedelta(hours=8)
        assert asset_time.wall_clock(date(2027, 1, 2), "09:00").utcoffset() == timedelta(hours=11)

    def test_a_version_starts_at_the_start_of_its_own_day_in_its_own_zone(self, tmp_path,
                                                                           monkeypatch):
        """Criterion 2 - so every instant belongs to exactly one version.
        Sydney is on +11:00 in January, so its 2027-01-01 begins at
        2026-12-31T13:00Z, while Perth's 2027-01-01 would begin 16:00Z."""
        _repoint(tmp_path, monkeypatch, _versions(("2020-01-01", "Australia/Perth"),
                                                  ("2027-01-01", "Australia/Sydney")))
        before = datetime(2026, 12, 31, 12, 59, tzinfo=UTC)
        after = datetime(2026, 12, 31, 13, 0, tzinfo=UTC)
        assert asset_time.zone_at(before).key == "Australia/Perth"
        assert asset_time.zone_at(after).key == "Australia/Sydney"
        # Shown and reduced to a date in the version in force AT it (criterion 4).
        assert asset_time.local_date(after) == date(2027, 1, 1)
        assert asset_time.local_date(before) == date(2026, 12, 31)

    def test_a_date_before_every_version_fails_loudly(self, tmp_path, monkeypatch):
        """Criterion 7 - never the oldest version instead."""
        _repoint(tmp_path, monkeypatch, _versions(("2020-01-01", "Australia/Perth")))
        with pytest.raises(asset_time.NoTimezoneVersion, match="2019-12-31"):
            asset_time.zone_on(date(2019, 12, 31))
        with pytest.raises(asset_time.NoTimezoneVersion):
            asset_time.zone_at(datetime(2019, 12, 31, 12, tzinfo=UTC))

    def test_a_stored_instant_keeps_its_meaning_when_a_version_is_added(self, tmp_path,
                                                                        monkeypatch):
        """Criterion 9 - only computed instants follow the versions."""
        stored = "2026-06-01T09:00:00+08:00"
        before = asset_time.parse_instant(stored, "x")
        _repoint(tmp_path, monkeypatch, _versions(("2020-01-01", "Australia/Perth"),
                                                  ("2026-07-01", "Australia/Sydney")))
        assert asset_time.parse_instant(stored, "x") == before


class TestDaylightSaving:
    """NFR 4: a zone that observes daylight saving, since the real asset's
    does not and so can never find these bugs. Sydney springs forward at
    02:00 on 2026-10-04 and falls back at 03:00 on 2026-04-05."""

    @pytest.fixture(autouse=True)
    def sydney(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _versions(("2020-01-01", "Australia/Sydney")))

    def test_a_time_in_the_spring_forward_gap_does_not_exist(self):
        assert "does not exist" in asset_time.wall_clock_problem(date(2026, 10, 4), "02:30")
        with pytest.raises(ValueError, match="does not exist"):
            asset_time.wall_clock(date(2026, 10, 4), "02:30")

    def test_a_time_in_the_fall_back_overlap_occurs_twice(self):
        assert "occurs twice" in asset_time.wall_clock_problem(date(2026, 4, 5), "02:30")
        with pytest.raises(ValueError, match="occurs twice"):
            asset_time.wall_clock(date(2026, 4, 5), "02:30")

    def test_an_ordinary_time_on_a_transition_day_is_fine(self):
        assert asset_time.wall_clock_problem(date(2026, 10, 4), "09:00") is None
        assert asset_time.wall_clock(date(2026, 10, 4), "09:00").utcoffset() == timedelta(hours=11)
        assert asset_time.wall_clock(date(2026, 10, 3), "09:00").utcoffset() == timedelta(hours=10)

    def test_a_day_is_23_hours_on_spring_forward(self):
        start = asset_time.start_of_day(date(2026, 10, 4))
        end = asset_time.end_of_day(date(2026, 10, 4))
        # IN UTC: Python subtracts two times sharing a tzinfo on the WALL
        # clock, which would say 24 hours on a 23-hour day.
        assert end.astimezone(UTC) - start.astimezone(UTC) == \
            timedelta(hours=23) - timedelta(microseconds=1)

    def test_a_version_change_across_a_transition(self, tmp_path, monkeypatch):
        """Perth until the day after Sydney springs forward, then Sydney."""
        _repoint(tmp_path, monkeypatch, _versions(("2020-01-01", "Australia/Perth"),
                                                  ("2026-10-05", "Australia/Sydney")))
        assert asset_time.wall_clock_problem(date(2026, 10, 4), "02:30") is None  # Perth that day
        assert asset_time.wall_clock(date(2026, 10, 5), "09:00").utcoffset() == timedelta(hours=11)
