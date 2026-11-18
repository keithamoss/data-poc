"""A dataset owes a subset of its baseline's rounds named in the baseline's own
terms - weekdays on a daily cadence rule, months on an authored calendar
(REQ-PIPE-346).

Each case edits ONE thing in a copy of the selected asset's real calendar:
the daily asset's Birth Registrations made weekly, or a quarterly dataset
given weekdays. Resolution is read through agreement.from_doc; the gate's
refusals through validate() over a copied asset folder; inheritance and the
terminal through the committed agreement, patched to the edited one.
"""
from __future__ import annotations

import copy
import shutil
from datetime import date, timedelta

import pytest
import yaml

import asset_folders
from asset_model import agreement, schedule, slots
from qa_tools.common.validate_schedule import Source, validate

DAILY_DS = "birth-registrations"
REASON = "A weekly register, sent on Mondays and Thursdays."


def _doc() -> dict:
    return yaml.safe_load((asset_folders.real_folder() / "calendar.yaml").read_text())


def _entry(doc, dataset_id):
    return next(e for e in doc["datasets"] if e["id"] == dataset_id)


def _owes(doc, dataset_id, days, reason=REASON):
    """Every participation version of `dataset_id` owes `days` - the restate
    rule wants each version complete."""
    entry = _entry(doc, dataset_id)
    entry["participation"]["versions"] = [
        {**v, "participates": list(days), **({"reason": reason} if reason else {})}
        for v in entry["participation"]["versions"]]
    return doc


def _agreement(doc):
    return agreement.from_doc(doc)


def _week_after_newest(agr, dataset_id) -> list[date]:
    """Seven consecutive days, Monday first, inside the newest version."""
    newest = agr.resolved_versions(dataset_id)[-1].effective_from
    monday = newest + timedelta(days=(7 - newest.weekday()) % 7)
    return [monday + timedelta(days=i) for i in range(7)]


@pytest.fixture
def gate(tmp_path):
    folder = tmp_path / "asset"
    shutil.copytree(asset_folders.real_folder(), folder)
    src = Source(folder / "data-asset.yaml", folder)

    def run(mutate):
        doc = _doc()
        mutate(doc)
        (folder / "calendar.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
        return validate(src)
    return run


def _text(errors):
    return "\n".join(f"{e.scope} | {e.problem} | {e.fix}" for e in errors)


@pytest.fixture
def weekly(monkeypatch):
    """The committed agreement, answered as Birth Registrations made weekly."""
    doc = _owes(_doc(), DAILY_DS, ["Monday", "thursday"])
    built = _agreement(doc)
    monkeypatch.setattr(agreement, "current", lambda: built)
    return built


@pytest.mark.asset("daily")
class TestAWeekdayListOnADailyCalendar:
    """Criteria 1, 2 and 4 (days_before)."""

    def test_it_supplies_only_on_the_weekdays_named(self):
        agr = _agreement(_owes(_doc(), DAILY_DS, ["Monday", "thursday"]))
        week = _week_after_newest(agr, DAILY_DS)
        got = [schedule.supplies_in_round(DAILY_DS, d, agr) for d in week]
        assert got == [True, False, False, True, False, False, False], list(zip(week, got))

    def test_its_slots_are_its_weekdays_only(self):
        agr = _agreement(_owes(_doc(), DAILY_DS, ["Monday"]))
        week = _week_after_newest(agr, DAILY_DS)
        found = [s for s in slots.slots_for_dataset(DAILY_DS, until=week[-1] + timedelta(days=1),
                                                     agreement=agr)
                 if week[0] <= s.round_date <= week[-1]]
        assert [s.round_date for s in found] == [week[0]]

    def test_a_round_due_the_evening_before_is_still_its_own_weekday(self):
        """With days_before 1 a Monday round is due on Sunday evening - and
        is still the Monday round (the requirement's third decision)."""
        doc = _owes(_doc(), DAILY_DS, ["Monday"])
        for v in _entry(doc, DAILY_DS)["participation"]["versions"]:
            v["days_before"] = 1
            v["expected_time"] = "22:00"
        agr = _agreement(doc)
        week = _week_after_newest(agr, DAILY_DS)
        assert schedule.supplies_in_round(DAILY_DS, week[0], agr)
        assert not schedule.supplies_in_round(DAILY_DS, week[6], agr)

    @pytest.mark.parametrize("value", ["Mon", "mon.", 0, 1, "Monday1"])
    def test_an_abbreviation_number_or_index_is_refused(self, value):
        doc = _owes(_doc(), DAILY_DS, [value])
        with pytest.raises(schedule.ScheduleConfigError, match="not a full weekday name"):
            _agreement(doc)

    def test_months_and_weekdays_in_one_list_are_refused(self):
        doc = _owes(_doc(), DAILY_DS, ["Monday", "February"])
        with pytest.raises(schedule.ScheduleConfigError, match="both months and weekdays"):
            _agreement(doc)


@pytest.mark.asset("daily")
class TestTheGateOnTheDailyAsset:
    """Criteria 3 and 4, against the daily cadence rule."""

    def test_a_weekday_list_passes(self, gate):
        errors = gate(lambda doc: _owes(doc, DAILY_DS, ["Monday", "Thursday"]))
        assert [e for e in errors if DAILY_DS in e.scope] == [], _text(errors)

    def test_months_on_the_daily_rule_are_refused_naming_weekdays(self, gate):
        errors = gate(lambda doc: _owes(doc, DAILY_DS, ["February"]))
        hits = [e for e in errors if DAILY_DS in e.scope and "February" in e.problem]
        assert hits, _text(errors)
        said = " ".join(f"{e.problem} {e.fix}" for e in hits)
        assert "participation version 1" in said and "weekdays" in said, said

    def test_an_abbreviation_is_refused(self, gate):
        errors = gate(lambda doc: _owes(doc, DAILY_DS, ["Mon"]))
        assert any(DAILY_DS in e.scope and "Mon" in e.problem for e in errors), _text(errors)

    def test_a_weekday_list_needs_a_reason(self, gate):
        errors = gate(lambda doc: _owes(doc, DAILY_DS, ["Monday"], reason=None))
        assert any(DAILY_DS in e.scope and "gives no reason" in e.problem for e in errors), \
            _text(errors)

    def test_an_inherit_newly_owing_weekdays_names_them(self, gate):
        def mutate(doc):
            _owes(doc, DAILY_DS, ["Monday"])
            versions = _entry(doc, DAILY_DS)["participation"]["versions"]
            versions[-1]["participates"] = "inherit"
            versions[-1].pop("reason")
            coll = next(c for c in doc["collections"] if c["id"] == "civil-registration")
            coll["participation_defaults"] = {"versions": [{
                "effective_from": versions[0]["effective_from"],
                "participates": ["Monday", "Thursday"], "reason": REASON,
                "changelog": [{"date": "2026-01-01", "author": "a test", "change": "a test"}]}]}
        errors = gate(mutate)
        hit = [e for e in errors if "newly owe" in e.problem]
        assert hit and "Thursday" in hit[0].problem and "[Monday]" in hit[0].fix, _text(errors)


@pytest.mark.asset("quarterly")
class TestTheGateOnAnAuthoredCalendar:
    """Criterion 3, the other way: weekdays against an authored calendar."""

    def test_weekdays_on_an_authored_calendar_are_refused_naming_months(self, gate):
        errors = gate(lambda doc: _owes(doc, "cp-case-workers", ["Monday"]))
        hits = [e for e in errors if "cp-case-workers" in e.scope and "Monday" in e.problem]
        assert hits, _text(errors)
        said = " ".join(f"{e.problem} {e.fix}" for e in hits)
        assert "participation version 1" in said and "months" in said, said

    def test_the_runtime_refuses_them_too(self):
        doc = copy.deepcopy(_doc())
        _owes(doc, "cp-case-workers", ["Monday"])
        agr = _agreement(doc)
        on = agr.resolved_versions("cp-case-workers")[-1].effective_from
        rnd = schedule.periods_for_calendar(
            schedule.calendar_for_dataset("cp-case-workers", agr).name, agreement=agr)
        later = next(r.date for r in rnd if r.date >= on)
        with pytest.raises(schedule.ScheduleConfigError, match="weekdays"):
            schedule.supplies_in_round("cp-case-workers", later, agr)


@pytest.mark.asset("daily")
class TestADayOwedNothingByWeekday:
    """Criterion 5: inherited like a quarter owed nothing by month."""

    def test_a_day_off_its_weekdays_inherits(self, weekly):
        from qa_tools.common import inheritance

        week = _week_after_newest(weekly, DAILY_DS)
        skipped, reason = inheritance._does_not_participate(DAILY_DS, week[1].isoformat())
        assert skipped, reason
        assert "Monday and Thursday" in reason, reason

    def test_a_day_on_them_is_owed(self, weekly):
        from qa_tools.common import inheritance

        week = _week_after_newest(weekly, DAILY_DS)
        assert inheritance._does_not_participate(DAILY_DS, week[3].isoformat()) == (False, "")


@pytest.mark.asset("daily")
class TestTheTerminalShowsTheWeekdays:
    """Criterion 6: in the form months are shown."""

    def test_participation_view_names_them(self, weekly):
        from qa_tools.common import participation_view

        week = _week_after_newest(weekly, DAILY_DS)
        got = participation_view.view(DAILY_DS, week[0], weekly)
        owes = next(v for v in got.values if v.label == "Owes")
        assert owes.text.startswith("Monday, Thursday - "), owes.text

    def test_schedule_show_names_them(self, weekly):
        from click.testing import CliRunner

        from cli.app import cli

        out = CliRunner().invoke(cli, ["schedule", "show", "--dataset", DAILY_DS])
        assert out.exit_code == 0, out.output
        assert "participates: Monday, Thursday" in " ".join(out.output.split()), out.output


@pytest.mark.asset("daily")
class TestTheBuildCarriesTheWeekdays:
    """REQ-DASH-347 criteria 1 to 3, the build's half: the SLA tile's versions
    carry the weekdays with the reason shown once, and a day owed nothing says
    its weekdays under their own key, never as months."""

    def test_the_sla_versions_carry_the_weekdays_and_the_reason(self, weekly):
        from pipeline import owed_nothing

        got = owed_nothing.sla_timeline(DAILY_DS, weekly)
        newest = got["versions"][-1]
        assert newest["cadence"]["weekdays"] == [0, 3], newest
        assert newest["reason"] == REASON, newest

    def test_a_day_owed_nothing_carries_weekdays_not_months(self, weekly):
        from pipeline import owed_nothing

        week = _week_after_newest(weekly, DAILY_DS)
        rows = owed_nothing.for_dataset(DAILY_DS, week[-1], weekly)
        tuesday = next(r for r in rows if r["period"] == week[1].isoformat())
        assert tuesday["kind"] == owed_nothing.PARTICIPATION, tuesday
        assert tuesday["weekdays"] == [0, 3] and tuesday["months"] is None, tuesday
        assert week[0].isoformat() not in {r["period"] for r in rows}


#: The daily asset by default; the authored-calendar cases name the quarterly.
pytestmark = pytest.mark.asset("daily")
