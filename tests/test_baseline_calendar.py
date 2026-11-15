"""One baseline calendar per data asset (REQ-PIPE-345).

Every dataset of an asset that does not declare no calendar is on the
asset's one baseline. Nothing may be faster than it: a slower dataset owes a
subset of the baseline's periods, stated under `participates`, and to go
faster the asset's baseline changes. These tests feed the schedule validator
a copy of the real quarterly configuration broken in each way criterion 3
names - a second calendar, a collection or dataset naming a calendar, a
dataset with authored dates of its own - and require the refusal with the
criterion's own words (criterion 7: proven by a test, not by a dataset).
They write calendar.yaml directly, never through tests/agreement_split.py,
whose one-file shape no longer carries a calendar per dataset.
"""
from __future__ import annotations

import shutil

import pytest
import yaml

from qa_tools.common import agreement, assets, schedule, validate_schedule
from qa_tools.common.validate_schedule import Source, validate

pytestmark = pytest.mark.asset("quarterly")

#: Criterion 3's words, which every refusal here carries.
RULE = ("a dataset may not be faster than its asset's baseline; a slower one owes a subset "
        "of the baseline's periods, stated under participates; to go faster, change the "
        "asset's baseline")


@pytest.fixture
def broken(tmp_path):
    """A writable copy of the real quarterly folder; call it with a function
    that mutates the parsed calendar.yaml, and get the validator's errors."""
    folder = tmp_path / "quarterly"
    shutil.copytree(assets.selected().folder, folder, symlinks=True)
    path = folder / "calendar.yaml"

    def apply(mutate):
        doc = yaml.safe_load(path.read_text())
        mutate(doc)
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return validate(Source(folder / "data-asset.yaml", folder))

    return apply


def _monthly() -> dict:
    return {"name": "monthly", "description": "A faster calendar than the asset's baseline.",
            "versions": [{"effective_from": "2023-01-01", "claim_window": "7d",
                          "changelog": [{"date": "2026-11-15", "author": "a test",
                                         "change": "a monthly calendar"}],
                          "dates": [{"period": f"2023-M{m:02d}", "date": f"2023-{m:02d}-01"}
                                    for m in range(1, 13)]}]}


def _collection(doc, cid):
    return next(c for c in doc["collections"] if c["id"] == cid)


def _dataset(doc, did):
    return next(d for d in doc["datasets"] if d["id"] == did)


def _refusals(errors, *needles):
    """The errors carrying criterion 3's rule and every needle, by text."""
    return [e for e in errors
            if RULE in f"{e.problem} {e.fix}"
            and all(n in f"{e.scope or ''} {e.problem} {e.fix}" for n in needles)]


class TestTheGateRefusesAnythingButOneBaseline:
    """Criterion 7, each of criterion 3's refusals."""

    def test_the_committed_configuration_passes(self):
        assert validate() == []

    def test_a_monthly_calendar_beside_the_quarterly_baseline_is_refused(self, broken):
        errors = broken(lambda doc: doc["calendars"].append(_monthly()))
        found = _refusals(errors, "asset 'quarterly'", "'monthly'", "'quarterly'")
        assert found, validate_schedule.__name__ + ": " + "\n".join(e.problem for e in errors)
        assert all(e.file == "calendar.yaml" for e in found)

    def test_a_collection_naming_a_calendar_is_refused(self, broken):
        def mutate(doc):
            doc["calendars"].append(_monthly())
            _collection(doc, "emergency-department")["calendar"] = "monthly"
        errors = broken(mutate)
        found = _refusals(errors, "asset 'quarterly'", "collection 'emergency-department'",
                          "'monthly'")
        assert found, "\n".join(e.problem for e in errors)
        assert all(e.file == "calendar.yaml" for e in found)

    def test_a_collection_naming_even_the_baseline_is_refused(self, broken):
        """Naming the baseline changes nothing today and is still refused:
        a collection that names a calendar is a second place a cadence is
        chosen, which criterion 2 retires."""
        errors = broken(lambda doc: _collection(doc, "child-protection").update(
            calendar="quarterly"))
        assert _refusals(errors, "asset 'quarterly'", "collection 'child-protection'"), \
            "\n".join(e.problem for e in errors)

    def test_a_dataset_naming_a_calendar_is_refused(self, broken):
        errors = broken(lambda doc: _dataset(doc, "cp-clients").update(calendar="quarterly"))
        assert _refusals(errors, "asset 'quarterly'", "dataset 'cp-clients'"), \
            "\n".join(e.problem for e in errors)

    def test_a_dataset_with_authored_dates_of_its_own_is_refused(self, broken):
        def mutate(doc):
            _dataset(doc, "cp-carers")["dates"] = {"versions": [{
                "effective_from": "2023-01-01",
                "changelog": [{"date": "2026-11-15", "author": "a test",
                               "change": "dates of its own"}],
                "dates": [{"period": "2023-X1", "date": "2023-03-15"}]}]}
        errors = broken(mutate)
        found = _refusals(errors, "asset 'quarterly'", "dataset 'cp-carers'", "dates")
        assert found, "\n".join(e.problem for e in errors)
        assert all(e.file == "calendar.yaml" for e in found)

    def test_each_refusal_is_its_own_error(self, broken):
        """All three at once: three refusals, none hiding another."""
        def mutate(doc):
            doc["calendars"].append(_monthly())
            _collection(doc, "emergency-department")["calendar"] = "monthly"
            _dataset(doc, "cp-carers")["dates"] = {"versions": [{
                "effective_from": "2023-01-01",
                "changelog": [{"date": "2026-11-15", "author": "a test",
                               "change": "dates of its own"}],
                "dates": [{"period": "2023-X1", "date": "2023-03-15"}]}]}
        errors = broken(mutate)
        assert len(_refusals(errors, "asset 'quarterly'")) == 3, \
            "\n".join(e.problem for e in errors)

    def test_a_hierarchy_dataset_naming_a_calendar_is_refused_in_its_own_file(self, broken,
                                                                              tmp_path):
        """data-asset.yaml's hierarchy names no calendar either."""
        folder = tmp_path / "quarterly"
        broken(lambda doc: None)
        path = folder / "data-asset.yaml"
        doc = yaml.safe_load(path.read_text())
        doc["hierarchy"]["agencies"][0]["collections"][0]["datasets"][0]["calendar"] = "quarterly"
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        errors = validate(Source(path, folder))
        found = _refusals(errors, "asset 'quarterly'")
        assert found and all(e.file == "data-asset.yaml" for e in found), \
            "\n".join(f"{e.file}: {e.problem}" for e in errors)


class TestEveryDatasetIsOnTheBaseline:
    """Criteria 1, 2 and 6: the baseline is asked for, never named."""

    def test_the_asset_has_one_baseline_and_every_calendared_dataset_is_on_it(self):
        agr = agreement.current()
        base = schedule.baseline(agr)
        assert base is not None and list(agr.calendars) == [base.name]
        from qa_tools.common import hierarchy

        on = [d.dataset_id for d in hierarchy.all_datasets()
              if schedule.no_calendar(d.dataset_id) is None]
        assert on, "the asset declares calendared datasets"
        assert {schedule.calendar_for_dataset(d).name for d in on} == {base.name}

    def test_a_calendar_named_on_a_collection_is_not_read(self, tmp_path):
        """Criterion 2: even where the file names another calendar on a
        collection (which the gate refuses), the reader puts the collection's
        datasets on the baseline."""
        doc = yaml.safe_load((assets.selected().folder / "calendar.yaml").read_text())
        _collection(doc, "emergency-department")["calendar"] = "elsewhere"
        agr = agreement.from_doc(doc)
        assert schedule.calendar_for_dataset("ed-presentations", agr).name == \
            schedule.baseline(agr).name

    def test_the_baseline_states_its_kind(self):
        """Criterion 6: whether the baseline is a cadence rule or authored
        dates is asked of the baseline, never read off its name."""
        base = schedule.baseline()
        assert base.kind == schedule.AUTHORED_DATES
        assert not base.is_cadence_rule

    @pytest.mark.asset("daily")
    def test_the_daily_baseline_states_its_kind(self):
        base = schedule.baseline()
        assert base.kind == schedule.CADENCE_RULE
        assert base.is_cadence_rule

    def test_two_calendars_leave_no_baseline_to_guess(self):
        """The reader never picks one of two: the gate refuses the file and
        a reader asked for the baseline raises."""
        doc = yaml.safe_load((assets.selected().folder / "calendar.yaml").read_text())
        doc["calendars"].append(_monthly())
        agr = agreement.from_doc(doc)
        with pytest.raises(schedule.ScheduleConfigError, match="one baseline"):
            schedule.baseline(agr)

    def test_an_asset_with_no_calendar_has_no_baseline(self):
        doc = yaml.safe_load((assets.selected().folder / "calendar.yaml").read_text())
        doc["calendars"] = []
        assert schedule.baseline(agreement.from_doc(doc)) is None


def _renamed_baseline(tmp_path, new_name: str):
    """Point the selected asset at a copy whose baseline calendar is renamed -
    so code that still tested the name would read a different calendar, or
    none (criterion 6: the names happen to match the asset ids after the
    split, which is exactly why a name test would read as working)."""
    import asset_folders

    real = assets.selected().folder / "calendar.yaml"
    doc = yaml.safe_load(real.read_text())
    doc["calendars"][0]["name"] = new_name
    folder = tmp_path / "renamed"
    folder.mkdir()
    (folder / "calendar.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    asset_folders.point(folder)
    assert schedule.baseline().name == new_name


class TestSharedCodeNamesNoCalendar:
    """Criterion 6, by behaviour: rename the baseline and the shared code
    that asked for it by name answers exactly as before."""

    @pytest.mark.asset("daily")
    def test_the_evening_before_supply_lands_in_its_period_whatever_the_baseline_is_called(
            self, tmp_path):
        """generator/scenario_injection.py: on the cadence-rule baseline a
        supply for day D received the evening before (REQ-GEN-044) belongs
        to D by its claim window, not to the calendar day it arrived on."""
        from generator import scenario_injection

        day, received = "2026-06-20", "2026-06-19T22:30:00+08:00"
        assert scenario_injection._lands_in("birth-registrations", day, received)
        _renamed_baseline(tmp_path, "every-day")
        assert scenario_injection._lands_in("birth-registrations", day, received)

    def test_child_protections_grown_periods_do_not_depend_on_the_baselines_name(
            self, tmp_path):
        """The Child Protection provider asks for the baseline rather than the
        calendar named 'quarterly'."""
        import collection_modules

        cp = collection_modules.provider_module("child-protection")
        before = [(p.period.name, p.round.name) for p in cp.drawn_grown_periods()]
        assert before
        _renamed_baseline(tmp_path, "every-quarter")
        assert [(p.period.name, p.round.name) for p in cp.drawn_grown_periods()] == before
