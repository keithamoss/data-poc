"""Tests for qa_tools/common/runway.py (REQ-PIPE-053, the schedule half).

What this is really defending: an authored date list that runs out
stops producing periods, so nothing is owed, so nothing is overdue, and
the dashboard goes green and STAYS green. That is indistinguishable
from a healthy feed, which is why the requirement's own NFR calls it
the same false-green shape as the staleness bug.

Two states, different in kind, and the tests are grouped that way: low
runway warns and must never fail anything; an exhausted schedule is a
hard failure scoped to one dataset.
"""
from __future__ import annotations

from datetime import date

import pytest

from qa_tools.common import hierarchy, runway, schedule

# The real quarterly calendar's last authored date. Written as a
# constant so a test that goes stale when somebody authors 2028 fails
# with an obvious reason rather than a mystery.
LAST_QUARTERLY = date(2027, 11, 1)
BEFORE_ANY_RUNOUT = date(2023, 6, 1)
AFTER_EVERYTHING = date(2028, 6, 1)


class TestRunwayIsMeasuredInSlots:
    """Not in elapsed time, and the unit is the point rather than a
    detail: three months of runway on a quarterly calendar is ONE slot,
    which is already too late to act on."""

    def test_remaining_counts_slots_not_days(self):
        result = runway.calendar_runway("quarterly", date(2027, 6, 1))
        assert result.remaining == 1, "one Feb/August dataset slot left after mid-2027"

    def test_it_counts_the_dataset_that_runs_out_first(self):
        """cp-case-workers takes two months of four, so it runs out of
        slots twice as fast as its siblings - and it is the first one
        out that decides when this is worth saying."""
        as_of = date(2026, 9, 23)
        per_dataset = {}
        for dataset in hierarchy.all_datasets():
            if schedule.calendar_for_dataset(dataset.dataset_id).name != "quarterly":
                continue
            owed = [p for p in schedule.periods_for_dataset(dataset.dataset_id) if p.expected]
            per_dataset[dataset.dataset_id] = len([p for p in owed if p.date > as_of])
        assert runway.calendar_runway("quarterly", as_of).remaining == min(per_dataset.values())
        assert per_dataset["cp-case-workers"] < per_dataset["cp-clients"]

    def test_a_calendar_with_plenty_left_is_not_low(self):
        assert not runway.calendar_runway("quarterly", BEFORE_ANY_RUNOUT).is_low
        assert runway.low_runway(BEFORE_ANY_RUNOUT) == []

    def test_it_names_the_last_authored_period_and_how_many_datasets(self):
        result = runway.calendar_runway("quarterly", date(2026, 9, 23))
        assert result.last_date == LAST_QUARTERLY
        assert result.last_period == "2027-Q4"
        assert result.dataset_count == 6


class TestACadenceRuleNeverWarns:
    """A rule generates periods for ever, so warning about its runway
    would be warning about something that cannot happen - and a warning
    that can never be acted on teaches a reader to skip the class."""

    def test_the_daily_calendar_is_never_low(self):
        for as_of in (BEFORE_ANY_RUNOUT, date(2026, 9, 23), AFTER_EVERYTHING, date(2199, 1, 1)):
            assert "daily" not in [r.calendar_name for r in runway.low_runway(as_of)]

    def test_a_daily_dataset_is_never_exhausted(self):
        for as_of in (date(2026, 9, 23), AFTER_EVERYTHING, date(2199, 1, 1)):
            assert "birth-registrations" not in runway.exhausted_datasets(as_of)


class TestTheWarningNeverFailsAnything:
    def test_the_gate_still_exits_zero_while_warning(self, capsys):
        """The real committed configuration is ALREADY low on runway -
        two slots left - so this is not hypothetical."""
        from qa_tools.common.validate_schedule import main

        assert main() == 0
        assert "WARNING" in capsys.readouterr().err

    def test_every_warning_line_says_it_is_not_failing_the_build(self):
        """In TEXT, not by colour. A reader who cannot tell a warning
        from a failure treats both as noise, and the one that mattered
        goes with it."""
        lines = runway.warning_lines(date(2026, 9, 23))
        assert lines
        for line in lines:
            assert "not failing the build" in line

    def test_a_warning_names_the_file_a_person_must_edit(self):
        for line in runway.warning_lines(date(2026, 9, 23)):
            assert "contract/data-asset.yaml" in line
            assert "candidate-dates" in line, "and how to get the dates proposed"


class TestItWarnsOncePerCalendarNotOncePerDataset:
    """Thirty datasets on one authored calendar run out on the same day.
    Thirty warnings would be one fact repeated thirty times."""

    def test_six_datasets_on_one_calendar_produce_one_line(self):
        lines = runway.warning_lines(date(2026, 9, 23))
        assert len(lines) == 1
        assert lines[0].count("quarterly") >= 1

    def test_the_line_says_how_many_datasets_without_listing_them(self):
        """Refined 2026-09-25 by post-build-review #22, and the refinement
        is narrow: the rule was "name none of them", and it is now "name
        the ONE the number belongs to, and none of the others".

        The thing being avoided was never naming a dataset - it was one
        fact repeated thirty times. A minimum with no owner is
        unreproducible from the config, which is a different failure and
        the one #22 found. Naming exactly one costs nothing at thirty
        datasets and is what makes the figure checkable.
        """
        line = runway.warning_lines(date(2026, 9, 23))[0]
        assert "6 datasets name this calendar" in line
        named = [d.dataset_id for d in hierarchy.all_datasets() if d.dataset_id in line]
        assert named == ["cp-case-workers"], (
            f"exactly the driving dataset should be named, not {named}")

    def test_the_summary_counts_calendars_when_more_than_one_is_low(self, tmp_path, monkeypatch):
        import shutil

        import yaml

        contract_dir = tmp_path / "contract"
        shutil.copytree("contract", contract_dir)
        doc = yaml.safe_load((contract_dir / "data-asset.yaml").read_text())
        # A second authored calendar, also nearly out, with one dataset
        # on it. NEARLY out rather than fully out, and the dates below
        # were extended to 2028 on 2026-09-24 to make that true: it used
        # to carry a single 2023 date, which is EXHAUSTED at this test's
        # own as-of, not "nearly out" as this comment always said. That
        # went unnoticed while both states shared one summary sentence;
        # post-build-review #21 gave the exhausted state its own words,
        # and this assertion is about counting LOW calendars.
        doc["calendars"].append({
            "name": "annual", "description": "Once a year.",
            "versions": [{"effective_from": "2023-01-01", "changelog": ["initial"],
                           "claim_window": "14d",
                           "dates": [{"period": str(y), "date": f"{y}-03-01"}
                                      for y in range(2023, 2029)]}]})
        doc["hierarchy"]["agencies"][0]["collections"][0]["datasets"].append(
            {"id": "extra", "name": "Extra", "table": "extra", "calendar": "annual"})
        (contract_dir / "data-asset.yaml").write_text(yaml.safe_dump(doc))
        monkeypatch.setattr(schedule, "DATA_ASSET_YAML", contract_dir / "data-asset.yaml")
        monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", contract_dir / "data-asset.yaml")
        schedule._load.cache_clear()
        schedule._dataset_schedules.cache_clear()
        hierarchy._load.cache_clear()
        try:
            note = runway.summary(date(2026, 9, 23))
            assert "2 calendar(s) low on runway" in note
        finally:
            schedule._load.cache_clear()
            schedule._dataset_schedules.cache_clear()
            hierarchy._load.cache_clear()


class TestAnExhaustedScheduleIsScopedToItsOwnDatasets:
    def test_nothing_is_exhausted_while_dates_remain(self):
        assert runway.exhausted_datasets(date(2026, 9, 23)) == {}

    def test_every_quarterly_dataset_is_exhausted_once_the_dates_run_out(self):
        exhausted = runway.exhausted_datasets(AFTER_EVERYTHING)
        assert set(exhausted) == {"cp-clients", "cp-notifications", "cp-investigations",
                                   "cp-placements", "cp-carers", "cp-case-workers"}
        assert set(exhausted.values()) == {"quarterly"}

    def test_the_daily_dataset_carries_on(self):
        """Criterion: the failure is scoped to the affected dataset and
        must not stop any other. At thirty datasets, a check that stops
        everything is a check somebody disables wholesale."""
        assert "birth-registrations" not in runway.exhausted_datasets(AFTER_EVERYTHING)

    def test_a_dataset_runs_out_before_its_siblings_if_it_participates_less(self):
        """cp-case-workers' last slot is 2027-Q3, its siblings' is
        2027-Q4 - so there is a window where it alone is exhausted."""
        between = date(2027, 9, 1)
        exhausted = runway.exhausted_datasets(between)
        assert set(exhausted) == {"cp-case-workers"}

    def test_the_summary_says_how_many_datasets_cannot_be_processed(self):
        note = runway.summary(AFTER_EVERYTHING)
        assert "6 dataset(s) have no remaining slots" in note


class TestTheThresholdIsConfigurable:
    def test_a_calendar_may_set_its_own(self, tmp_path, monkeypatch):
        import shutil

        import yaml

        contract_dir = tmp_path / "contract"
        shutil.copytree("contract", contract_dir)
        path = contract_dir / "data-asset.yaml"
        doc = yaml.safe_load(path.read_text())
        next(c for c in doc["calendars"] if c["name"] == "quarterly")["runway_warning_slots"] = 1
        path.write_text(yaml.safe_dump(doc))
        monkeypatch.setattr(schedule, "DATA_ASSET_YAML", path)
        monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", path)
        schedule._load.cache_clear()
        schedule._dataset_schedules.cache_clear()
        hierarchy._load.cache_clear()
        try:
            # Two slots left, threshold now 1 - so no longer low.
            assert runway.low_runway(date(2026, 9, 23)) == []
        finally:
            schedule._load.cache_clear()
            schedule._dataset_schedules.cache_clear()
            hierarchy._load.cache_clear()

    def test_a_threshold_of_zero_is_rejected(self, tmp_path, monkeypatch):
        """A threshold that only fires once the schedule has already run
        out is a warning with nothing left to warn about."""
        import shutil

        import yaml

        contract_dir = tmp_path / "contract"
        shutil.copytree("contract", contract_dir)
        path = contract_dir / "data-asset.yaml"
        doc = yaml.safe_load(path.read_text())
        next(c for c in doc["calendars"] if c["name"] == "quarterly")["runway_warning_slots"] = 0
        path.write_text(yaml.safe_dump(doc))
        monkeypatch.setattr(schedule, "DATA_ASSET_YAML", path)
        schedule._load.cache_clear()
        try:
            with pytest.raises(schedule.ScheduleConfigError, match="runway_warning_slots"):
                schedule.calendars()
        finally:
            schedule._load.cache_clear()


class TestItTouchesNoData:
    def test_computing_runway_opens_nothing_under_data(self, monkeypatch):
        """This is what lets the dashboard show an exhausted schedule
        even though the run that would have reported it never
        happened."""
        from pathlib import Path

        opened = []
        real_open = Path.open

        def watching(self, *args, **kwargs):
            opened.append(str(self))
            return real_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", watching)
        runway.warning_lines(date(2026, 9, 23))
        runway.exhausted_datasets(date(2026, 9, 23))
        assert not [p for p in opened if "/data/" in p or p.endswith("duckdb")], opened


class TestExhaustedDoesNotWearTheMildStatesWords:
    """post-build-review #21, Keith's option (a), 2026-09-24.

    This module's own docstring calls low runway and an exhausted
    schedule "TWO STATES, DELIBERATELY DIFFERENT IN KIND". In the text
    they were the same state: both lines opened `WARNING (not failing
    the build)`, and the summary said a calendar with no runway at all
    was "low on runway".

    REQ-PIPE-053 criterion 14 asks a warning to be distinguished from a
    failure "in text as well as colour". Keith's call was to change the
    words now rather than wait for the filing layer, since nothing about
    the gate's behaviour changes - at the gate, neither state fails the
    build, and saying so stays.
    """

    # Past the real quarterly calendar's last authored period.
    AFTER = date(2028, 6, 1)

    def test_the_exhausted_line_does_not_open_with_the_word_warning(self):
        lines = runway.warning_lines(self.AFTER)
        assert lines, "precondition - the real config must be exhausted by this date"
        assert not lines[0].startswith("WARNING"), (
            f"the severest state opens with the mild state's word:\n  {lines[0]}")

    def test_the_exhausted_line_still_says_it_is_not_failing_the_build(self):
        """The label changes; the promise does not. A non-fatal warning
        that starts failing builds is one somebody turns off."""
        line = runway.warning_lines(self.AFTER)[0]
        assert "not failing the build" in line

    def test_the_summary_does_not_call_an_empty_calendar_low_on_runway(self):
        note = runway.summary(self.AFTER)
        assert note
        assert "low on runway" not in note, (
            f"a calendar with no future dates at all is not low on runway:\n  {note}")
        assert "cannot be processed" in note

    def test_a_merely_low_calendar_keeps_the_warning_wording(self):
        """The change must not leak into the state it is distinguishing
        from - today's real config is low, not exhausted."""
        line = runway.warning_lines(date(2026, 9, 23))[0]
        assert line.startswith("WARNING (not failing the build)")
        assert runway.summary(date(2026, 9, 23)).endswith("low on runway.")


class TestTheNumberCanBeCheckedAgainstTheFile:
    """post-build-review #22. The warning read:

        calendar 'quarterly' has only 2 future supply slot(s) left -
        its last authored period is 2027-Q4 on 2027-11-01, and
        6 datasets name it.

    Every clause is true and the sentence is not. `remaining` is the
    MIN across datasets - correctly, and runway.py's own docstring says
    why - but it was attributed to the calendar, paired with the
    CALENDAR's last period, and named neither the dataset driving it nor
    that a minimum had been taken. Open `data-asset.yaml`, count five
    future quarterly dates, and the tool's "2" is unreproducible.

    The 2 belongs to cp-case-workers, whose own last period is 2027-Q3.
    The dashboard side of REQ-PIPE-053 already made exactly this fix -
    "a dataset's message names its OWN last period, not its calendar's"
    - and the CLI side kept the old shape. At thirty datasets with mixed
    participation it is the normal case, not an edge one.
    """

    AS_OF = date(2026, 9, 25)

    def _line(self):
        lines = [x for x in runway.warning_lines(self.AS_OF) if "quarterly" in x]
        assert len(lines) == 1, lines
        return lines[0]

    def test_the_warning_names_the_dataset_the_number_belongs_to(self):
        assert "cp-case-workers" in self._line(), (
            "the number is the minimum across datasets and the sentence never "
            "says whose it is - so nobody can reproduce it from the config")

    def test_it_pairs_that_number_with_that_datasets_own_last_period(self):
        """2 future slots and 2027-Q4 are facts about different objects.
        cp-case-workers' own last period is 2027-Q3."""
        line = self._line()
        assert "2027-Q3" in line

    def test_the_calendars_own_last_period_is_still_available_but_not_conflated(self):
        """Not a deletion - the calendar's own horizon is worth knowing,
        it just is not the same fact."""
        assert "2027-Q4" in self._line()

    def test_the_driving_dataset_is_on_the_runway_itself_not_only_in_prose(self):
        """A caller that renders its own message - the dashboard does -
        needs the fact, not a sentence to parse back out."""
        r = runway.calendar_runway("quarterly", self.AS_OF)
        assert r.driving_dataset == "cp-case-workers"
        assert r.driving_last_period == "2027-Q3"
        assert r.remaining == 2
