"""Tests for qa_tools/common/schedule.py - delivery calendars
(REQ-PIPE-049).

Against the REAL contract/data-asset.yaml wherever the real config is
the point, for the reason tests/test_hierarchy.py gives: a fixture
would let the module and the real calendars drift apart while every
test stayed green. tmp_path is used for the shapes the real file must
never contain - a duplicate period, a cadence rule carrying months, a
calendar version with no changelog.

The rejections matter more than the acceptances here. A schedule that
quietly accepts config it cannot honour produces a dataset expecting
something other than what its author wrote, and nothing ever says so.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import yaml

from qa_tools.common import hierarchy, schedule


def _clear():
    schedule._load.cache_clear()
    schedule._dataset_schedules.cache_clear()
    hierarchy._load.cache_clear()


@pytest.fixture(autouse=True)
def _clear_caches():
    _clear()
    yield
    _clear()


def _repoint(tmp_path, monkeypatch, doc):
    """Repoints BOTH readers at a synthetic config.

    schedule.calendar_for_dataset() resolves the dataset through the
    hierarchy on purpose - a dataset named in schedule config and absent
    from the tree has to be a detectable error - so a test that moved
    only one of the two would be testing a state the real system cannot
    reach.
    """
    path = tmp_path / "data-asset.yaml"
    path.write_text(yaml.safe_dump(doc))
    monkeypatch.setattr(schedule, "DATA_ASSET_YAML", path)
    monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", path)
    _clear()


def _calendar_doc(**version_overrides):
    version = {"effective_from": "2023-01-01", "changelog": ["2023-01-01: initial"],
               "claim_window": "14d",
               "dates": [{"period": "2026-Q1", "date": "2026-02-01"}]}
    version.update(version_overrides)
    return {"data_asset_id": "data-asset-1",
            "calendars": [{"name": "c", "versions": [version]}],
            "hierarchy": {"agencies": [{"id": "a", "name": "A", "collections": [
                {"id": "col", "name": "Col", "contract": "c.yaml", "datasets": [
                    {"id": "d", "name": "D", "table": "t", "calendar": "c"}]}]}]}}


class TestTheRealCalendars:
    def test_both_real_calendars_load(self):
        names = {c.name for c in schedule.calendars()}
        assert names == {"quarterly", "daily"}

    def test_quarterly_is_authored_dates_and_daily_is_a_rule(self):
        """Not a compromise between two shapes - they ARE different
        shapes. 365 enumerated daily dates would be absurd and the
        agreement genuinely is "every day"; four quarterly dates a year
        are known well in advance and the real agreement is "closest
        business day to the 1st", which no day-of-month rule states."""
        assert not schedule.calendar("quarterly").current.is_cadence_rule
        assert schedule.calendar("daily").current.cadence_rule == "daily"

    def test_every_real_dataset_names_a_calendar_that_exists(self):
        for entry in hierarchy.all_datasets():
            assert schedule.calendar_for_dataset(entry.dataset_id).name in {"quarterly", "daily"}

    def test_the_quarterly_dates_match_the_cadence_the_data_is_generated_against(self):
        """The authored dates and generator/generate_cp_runs.py's own
        Feb/May/Aug/Nov anchor must agree, or the schedule judges
        supplies against dates nothing ever delivered on."""
        months = {p.date.month for p in schedule.calendar("quarterly").current.periods}
        assert months == {2, 5, 8, 11}
        assert {p.date.day for p in schedule.calendar("quarterly").current.periods} == {1}

    def test_the_authored_dates_cover_the_committed_history(self):
        """A period for every real CP delivery, or the history has
        supplies belonging to periods the calendar does not define."""
        periods = {p.date for p in schedule.calendar("quarterly").current.periods}
        for year in (2023, 2024, 2025, 2026):
            for month in (2, 5, 8, 11):
                assert date(year, month, 1) in periods


class TestParticipation:
    def test_saying_nothing_means_every_period(self):
        """The reading that makes ~30 datasets tolerable to configure."""
        assert schedule.delivery_months("cp-clients") is None
        assert len(schedule.periods_for_dataset("cp-clients")) == 20

    def test_a_dataset_naming_months_gets_only_those(self):
        assert schedule.delivery_months("cp-case-workers") == (2, 8)
        months = {p.date.month for p in schedule.periods_for_dataset("cp-case-workers")}
        assert months == {2, 8}

    def test_month_names_are_case_insensitive(self):
        assert schedule.parse_month_name("february", "x") == 2
        assert schedule.parse_month_name("FEBRUARY", "x") == 2

    @pytest.mark.parametrize("bad", ["Feb", "2", 2, "Febuary", "", "Q1"])
    def test_abbreviations_numbers_and_positions_are_rejected(self, bad):
        """An INDEX breaks silently the moment a calendar is edited or
        reordered; a name simply stops matching. Two accepted forms
        would mean config reading differently across thirty datasets
        for no gain."""
        with pytest.raises(schedule.ScheduleConfigError, match="full month name"):
            schedule.parse_month_name(bad, "x")

    def test_months_on_a_cadence_calendar_are_an_error_not_ignored(self, tmp_path, monkeypatch):
        """Accepted-and-discarded config is how a dataset ends up
        expecting something other than what its author wrote."""
        doc = _calendar_doc(dates=None, cadence={"rule": "daily"})
        doc["hierarchy"]["agencies"][0]["collections"][0]["datasets"][0]["delivery_months"] = ["February"]
        _repoint(tmp_path, monkeypatch, doc)
        with pytest.raises(schedule.ScheduleConfigError, match="cadence rule"):
            schedule.periods_for_dataset("d", until=date(2023, 1, 5))


class TestOverridingRatherThanSubsetting:
    def test_a_dataset_may_replace_its_calendars_dates_outright(self, tmp_path, monkeypatch):
        doc = _calendar_doc()
        doc["hierarchy"]["agencies"][0]["collections"][0]["datasets"][0]["dates"] = [
            {"period": "own-1", "date": "2026-03-15"}]
        _repoint(tmp_path, monkeypatch, doc)
        got = schedule.periods_for_dataset("d")
        assert [p.name for p in got] == ["own-1"]

    def test_overriding_and_subsetting_at_once_is_an_error(self, tmp_path, monkeypatch):
        """They mean different things, and carrying both leaves no way
        to tell which the author meant."""
        doc = _calendar_doc()
        ds = doc["hierarchy"]["agencies"][0]["collections"][0]["datasets"][0]
        ds["dates"] = [{"period": "own-1", "date": "2026-03-15"}]
        ds["delivery_months"] = ["February"]
        _repoint(tmp_path, monkeypatch, doc)
        with pytest.raises(schedule.ScheduleConfigError, match="never both"):
            schedule.periods_for_dataset("d")


class TestNotExpectedPeriods:
    def test_a_not_expected_period_is_shown_not_dropped(self, tmp_path, monkeypatch):
        """"We agreed there would be no November file" and "we forgot to
        configure November" must not look the same six months later."""
        doc = _calendar_doc()
        doc["hierarchy"]["agencies"][0]["collections"][0]["datasets"][0]["not_expected"] = [
            {"period": "2026-Q1", "reason": "Agency system migration - agreed with the supplier."}]
        _repoint(tmp_path, monkeypatch, doc)
        got = schedule.periods_for_dataset("d")
        assert len(got) == 1, "the period must still appear"
        assert got[0].expected is False
        assert "migration" in got[0].not_expected_reason

    def test_a_reason_is_required(self, tmp_path, monkeypatch):
        doc = _calendar_doc()
        doc["hierarchy"]["agencies"][0]["collections"][0]["datasets"][0]["not_expected"] = [
            {"period": "2026-Q1"}]
        _repoint(tmp_path, monkeypatch, doc)
        with pytest.raises(schedule.ScheduleConfigError, match="no `reason:`"):
            schedule.periods_for_dataset("d")


class TestClaimWindow:
    def test_a_duration_carries_its_own_unit(self):
        assert schedule.parse_duration("14d", "x") == timedelta(days=14)
        assert schedule.parse_duration("4h", "x") == timedelta(hours=4)

    @pytest.mark.parametrize("bad", ["14", "14 days", "2w", "14D", "-1d", "1.5d", ""])
    def test_anything_else_is_rejected_rather_than_coerced(self, bad):
        """A new parser is a new thing to get wrong, so it stays as
        small as it can be. One form per unit."""
        with pytest.raises(schedule.ScheduleConfigError, match="not a duration"):
            schedule.parse_duration(bad, "x")

    def test_the_default_tracks_the_calendars_own_scale(self):
        """The reason the default sits on the CALENDAR and not on the
        asset root: an asset-root default would hand Birth
        Registrations a 14-day claim window on a daily feed."""
        assert schedule.claim_window("cp-clients") == timedelta(days=14)
        assert schedule.claim_window("birth-registrations") == timedelta(hours=4)

    def test_a_dataset_may_override_it_in_its_own_contract(self):
        assert schedule.claim_window("cp-clients", "3d") == timedelta(days=3)

    def test_an_unparseable_override_names_the_dataset(self):
        with pytest.raises(schedule.ScheduleConfigError, match="cp-clients"):
            schedule.claim_window("cp-clients", "3 days")


class TestVersioningAndEffectiveDates:
    def test_a_supply_is_judged_against_the_version_in_force_then(self):
        """Editing next year's dates must never retroactively move a
        date a past supply was already judged against."""
        cal = schedule.calendar("quarterly")
        assert cal.version_in_force(date(2026, 5, 1)) is cal.versions[0]

    def test_a_date_before_any_version_is_an_error(self):
        cal = schedule.calendar("quarterly")
        with pytest.raises(schedule.ScheduleConfigError, match="no version in force"):
            cal.version_in_force(date(2000, 1, 1))

    def test_a_version_with_no_changelog_entry_is_rejected(self, tmp_path, monkeypatch):
        """A calendar is a governance artefact. A version nobody wrote a
        reason for is a date change nobody can account for."""
        _repoint(tmp_path, monkeypatch, _calendar_doc(changelog=[]))
        with pytest.raises(schedule.ScheduleConfigError, match="changelog"):
            schedule.calendars()

    def test_a_version_with_no_effective_from_is_rejected(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _calendar_doc(effective_from=None))
        with pytest.raises(schedule.ScheduleConfigError, match="effective_from"):
            schedule.calendars()

    def test_versions_are_ordered_by_effective_from_not_file_order(self, tmp_path, monkeypatch):
        doc = _calendar_doc()
        doc["calendars"][0]["versions"] = [
            {"effective_from": "2027-01-01", "changelog": ["later"], "claim_window": "1d",
             "dates": [{"period": "p2", "date": "2027-02-01"}]},
            {"effective_from": "2023-01-01", "changelog": ["earlier"], "claim_window": "14d",
             "dates": [{"period": "p1", "date": "2023-02-01"}]},
        ]
        _repoint(tmp_path, monkeypatch, doc)
        cal = schedule.calendar("c")
        assert cal.current.effective_from == date(2027, 1, 1)
        assert cal.version_in_force(date(2024, 1, 1)).changelog == ("earlier",)


class TestMalformedCalendars:
    def test_a_period_authored_twice_is_an_error(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _calendar_doc(dates=[
            {"period": "2026-Q1", "date": "2026-02-01"},
            {"period": "2026-Q1", "date": "2026-02-02"}]))
        with pytest.raises(schedule.ScheduleConfigError, match="authored twice"):
            schedule.calendars()

    def test_dates_running_backwards_are_an_error(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _calendar_doc(dates=[
            {"period": "a", "date": "2026-05-01"},
            {"period": "b", "date": "2026-02-01"}]))
        with pytest.raises(schedule.ScheduleConfigError, match="forwards in time"):
            schedule.calendars()

    def test_both_dates_and_a_cadence_rule_is_an_error(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _calendar_doc(cadence={"rule": "daily"}))
        with pytest.raises(schedule.ScheduleConfigError, match="never both and never neither"):
            schedule.calendars()

    def test_neither_dates_nor_a_cadence_rule_is_an_error(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _calendar_doc(dates=None))
        with pytest.raises(schedule.ScheduleConfigError, match="never both and never neither"):
            schedule.calendars()

    def test_an_unsupported_cadence_rule_says_what_is_supported(self, tmp_path, monkeypatch):
        _repoint(tmp_path, monkeypatch, _calendar_doc(dates=None, cadence={"rule": "fortnightly"}))
        with pytest.raises(schedule.ScheduleConfigError, match="fortnightly"):
            schedule.calendars()

    def test_an_unknown_calendar_name_lists_the_real_ones(self):
        with pytest.raises(schedule.UnknownCalendarError, match="quarterly"):
            schedule.calendar("Quarterly")

    def test_a_dataset_the_hierarchy_does_not_define_is_caught_here_too(self):
        """REQ-QAC-039's criterion, applied to schedule config: a
        dataset named in one place and absent from the other must be a
        detectable error, never a silent mismatch."""
        with pytest.raises(hierarchy.UnknownDatasetError):
            schedule.calendar_for_dataset("cp_clients")

    def test_a_dataset_naming_no_calendar_is_an_error(self, tmp_path, monkeypatch):
        doc = _calendar_doc()
        del doc["hierarchy"]["agencies"][0]["collections"][0]["datasets"][0]["calendar"]
        _repoint(tmp_path, monkeypatch, doc)
        with pytest.raises(schedule.ScheduleConfigError, match="names no `calendar:`"):
            schedule.calendar_for_dataset("d")


class TestCandidateDates:
    def test_it_proposes_the_same_months_and_day_as_the_authored_pattern(self):
        got = schedule.candidate_dates("quarterly", 2029)
        assert [p.date for p, _ in got] == [
            date(2029, 2, 1), date(2029, 5, 1), date(2029, 8, 1), date(2029, 11, 1)]

    def test_it_carries_the_period_naming_pattern_forward(self):
        got = schedule.candidate_dates("quarterly", 2029)
        assert [p.name for p, _ in got] == ["2029-Q1", "2029-Q2", "2029-Q3", "2029-Q4"]

    def test_a_weekend_is_FLAGGED_not_silently_moved(self):
        """Moving it would be this function deciding something it has no
        standing to decide. The real agreement is often "the closest
        business day", and which side of the weekend that falls on is
        the supplier's answer, not ours - which is the same reason the
        dates are authored at all."""
        got = dict((p.date, note) for p, note in schedule.candidate_dates("quarterly", 2026))
        assert got[date(2026, 2, 1)], "1 Feb 2026 is a Sunday and must carry a note"
        assert "Sunday" in got[date(2026, 2, 1)]
        assert not got[date(2026, 5, 1)], "1 May 2026 is a Friday and needs no note"

    def test_a_cadence_rule_calendar_has_nothing_to_extend(self):
        assert schedule.candidate_dates("daily", 2029) == []

    def test_a_name_it_cannot_confidently_rewrite_is_left_blank_for_a_human(self, tmp_path, monkeypatch):
        """A period name is authored precisely because only the people
        who agreed it know what they call it, so guessing wrongly is
        worse than not guessing."""
        _repoint(tmp_path, monkeypatch, _calendar_doc(dates=[
            {"period": "spring collection", "date": "2026-02-01"}]))
        (period, note), = schedule.candidate_dates("c", 2029)
        assert period.name == "2029-?"
        assert "name it from" in note


class TestNothingIsComputedFromAHolidayCalendar:
    def test_the_authored_dates_are_returned_verbatim(self):
        """Criterion 15, and the point of the whole design: the dates
        ARE the agreement. A calendar library predicts what was probably
        agreed; it does not constitute it."""
        import yaml as _yaml
        raw = _yaml.safe_load(schedule.DATA_ASSET_YAML.read_text())
        authored = [(d["period"], str(d["date"]))
                    for c in raw["calendars"] if c["name"] == "quarterly"
                    for d in c["versions"][0]["dates"]]
        loaded = [(p.name, p.date.isoformat())
                  for p in schedule.calendar("quarterly").current.periods]
        assert loaded == authored

    def test_no_holiday_library_is_imported_by_this_module(self):
        source = schedule.DATA_ASSET_YAML.parent.parent / "qa_tools" / "common" / "schedule.py"
        text = source.read_text()
        for banned in ("import holidays", "from holidays", "workalendar", "business_calendar"):
            assert banned not in text, f"{banned} would make evaluation depend on a holiday library"
