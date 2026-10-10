"""The delivery agreement in its own file (REQ-PIPE-110).

Two halves. The loader - one file read into one immutable value, passed
as an argument, so two agreements can sit side by side in a process. And
the schedule gate's refusals of the new file's shape, each broken in ONE
way against a copy of the real configuration, the same discipline
tests/test_validate_schedule.py follows for the asset file.

The tests that were here before this module existed lived in
tests/test_cadence.py and exercised pipeline/cadence.py's reading of each
contract's slaProperties, which this requirement deletes outright.
"""
from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from qa_tools.common import agreement, schedule, slots
from qa_tools.common.validate_schedule import Source, validate

REAL_CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"


# ---- the loader ------------------------------------------------------

class TestTheDashboardCadenceComesFromTheAgreement:
    """Criterion 17 - the per-dataset delivery-time label the builders
    embed, read from contract/calendar.yaml."""

    def test_birth_registrations_is_daily_at_two_with_an_hour_of_grace(self):
        assert agreement.cadence("birth-registrations") == {
            "type": "daily", "expected_time": "14:00", "latency_minutes": 60}

    def test_child_protection_is_quarterly_on_the_first_at_nine(self):
        assert agreement.cadence("cp-clients") == {
            "type": "quarterly", "anchor_months": [2, 5, 8, 11], "day_of_month": 1,
            "expected_time": "09:00", "latency_minutes": 480}

    def test_every_real_dataset_has_one(self):
        from qa_tools.common import hierarchy

        for entry in hierarchy.all_datasets():
            assert agreement.cadence(entry.dataset_id)["expected_time"]


class TestOneLoaderOneImmutableValue:
    """Criterion 31."""

    def test_the_value_cannot_be_changed_in_place(self):
        current = agreement.current()
        with pytest.raises(Exception):
            current.datasets["birth-registrations"] = None
        with pytest.raises(Exception):
            current.calendars = {}

    def test_two_agreements_can_be_held_side_by_side(self, tmp_path):
        """What REQ-PIPE-111's freeze and REQ-PIPE-169's preview need: the
        agreement before a change and after it, in one process, each
        answering for itself."""
        doc = yaml.safe_load((REAL_CONTRACT_DIR / "calendar.yaml").read_text())
        entry = next(d for d in doc["datasets"] if d["id"] == "cp-clients")
        entry["participation"]["versions"][0] = {
            **entry["participation"]["versions"][0], "claim_window": "2h"}
        path = tmp_path / "calendar.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False))

        before, after = agreement.current(), agreement.load(path)
        old = slots.slots_for_dataset("cp-clients", agreement=before)[0]
        new = slots.slots_for_dataset("cp-clients", agreement=after)[0]
        assert old.due_at == new.due_at
        assert old.claim_opens_at == old.due_at - timedelta(days=14)
        assert new.claim_opens_at == new.due_at - timedelta(hours=2)

    def test_reading_it_opens_nothing_under_data(self, monkeypatch):
        """Criterion 23."""
        import builtins

        opened = []
        real_open = builtins.open

        def watching(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", watching)
        agreement.load(agreement.CALENDAR_YAML)
        assert opened and not [p for p in opened if "/data/" in p], opened


class TestParticipation:
    def test_case_workers_owes_february_and_august_only(self):
        """Criterion 5's worked example, now stated as `participates`."""
        months = {p.date.month for p in schedule.periods_for_dataset("cp-case-workers")}
        assert months == {2, 8}

    def test_saying_nothing_owes_every_period(self):
        """Criterion 6."""
        months = {p.date.month for p in schedule.periods_for_dataset("cp-clients")}
        assert months == {2, 5, 8, 11}

    def test_before_the_first_version_nothing_is_owed_yet(self, tmp_path):
        """Criterion 30 - and criterion 27: the first version's
        effective_from IS the date a dataset began owing."""
        doc = yaml.safe_load((REAL_CONTRACT_DIR / "calendar.yaml").read_text())
        entry = next(d for d in doc["datasets"] if d["id"] == "cp-clients")
        entry["participation"]["versions"][0] = {
            **entry["participation"]["versions"][0], "effective_from": "2025-01-01"}
        path = tmp_path / "calendar.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        moved = agreement.load(path)

        assert schedule.owes_from("cp-clients", moved) == date(2025, 1, 1)
        periods = schedule.periods_for_dataset("cp-clients", agreement=moved)
        assert min(p.date for p in periods) == date(2025, 2, 1)
        assert moved.participation_on("cp-clients", date(2024, 12, 31)) is None

    def test_a_participation_version_decides_the_periods_on_its_own_dates(self, tmp_path):
        """A later version narrowing the months governs only the periods
        on or after its own effective_from."""
        doc = yaml.safe_load((REAL_CONTRACT_DIR / "calendar.yaml").read_text())
        entry = next(d for d in doc["datasets"] if d["id"] == "cp-clients")
        first = entry["participation"]["versions"][0]
        entry["participation"]["versions"] = [first, {
            **first, "effective_from": "2026-01-01", "participates": ["February"],
            "reason": "a test",
            "changelog": [{"date": "2026-01-01", "author": "a test", "change": "narrowed"}]}]
        path = tmp_path / "calendar.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        periods = schedule.periods_for_dataset("cp-clients", agreement=agreement.load(path))
        assert {p.date.month for p in periods if p.date.year == 2025} == {2, 5, 8, 11}
        assert {p.date.month for p in periods if p.date.year == 2026} == {2}


# ---- the gate's refusals --------------------------------------------

@pytest.fixture
def broken(tmp_path):
    """A copy of the real contract directory, and a helper that applies
    one change to its calendar.yaml (or, with `asset=True`, its
    data-asset.yaml) and returns the gate's errors."""
    contract_dir = tmp_path / "contract"
    shutil.copytree(REAL_CONTRACT_DIR, contract_dir)
    src = Source(contract_dir / "data-asset.yaml", contract_dir)

    def apply(mutate, asset=False):
        path = contract_dir / ("data-asset.yaml" if asset else "calendar.yaml")
        doc = yaml.safe_load(path.read_text())
        mutate(doc)
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return validate(src)

    apply.contract_dir = contract_dir
    return apply


def _entry(doc, dataset_id):
    return next(d for d in doc["datasets"] if d["id"] == dataset_id)


def _first(doc, dataset_id):
    return _entry(doc, dataset_id)["participation"]["versions"][0]


def _text(errors):
    return "\n".join(f"{e.file} | {e.scope} | {e.problem} | {e.fix}" for e in errors)


class TestTheGateRefusesTheNewShapeBroken:
    def test_the_untouched_copy_passes(self, broken):
        assert broken(lambda doc: None) == []

    def test_a_plain_string_changelog_entry_is_refused(self, broken):
        """Criteria 12 and 13."""
        def mutate(doc):
            _first(doc, "cp-clients")["changelog"] = ["2026-10-11: moved"]
        errors = broken(mutate)
        assert errors and all(e.file == "calendar.yaml" for e in errors), _text(errors)

    def test_delivery_months_is_refused_naming_participates(self, broken):
        """Criterion 14 - in the asset file, where it used to live."""
        def mutate(doc):
            doc["hierarchy"]["agencies"][1]["collections"][0]["datasets"][5][
                "delivery_months"] = ["February", "August"]
        errors = broken(mutate, asset=True)
        assert any("delivery_months" in e.problem and "participates" in e.fix
                   and "calendar.yaml" in e.fix for e in errors), _text(errors)

    def test_delivery_months_is_refused_in_the_calendar_file_too(self, broken):
        def mutate(doc):
            _entry(doc, "cp-case-workers")["delivery_months"] = ["February"]
        errors = broken(mutate)
        assert any("delivery_months" in e.problem for e in errors), _text(errors)

    def test_owes_from_is_refused_naming_the_first_version(self, broken):
        """Criterion 28."""
        def mutate(doc):
            _entry(doc, "cp-clients")["owes_from"] = "2023-01-01"
        errors = broken(mutate)
        assert any("owes_from" in e.problem and "first participation version" in e.fix
                   for e in errors), _text(errors)

    def test_a_contract_stating_sla_properties_is_refused(self, broken):
        """Criterion 16, and it is never read."""
        path = broken.contract_dir / "child-protection-contract.yaml"
        doc = yaml.safe_load(path.read_text())
        doc["slaProperties"] = [{"property": "latency", "value": 30, "unit": "min"}]
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        errors = broken(lambda d: None)
        assert any(e.file == "child-protection-contract.yaml" and "slaProperties" in e.problem
                   and "calendar.yaml" in e.fix for e in errors), _text(errors)

    def test_a_dataset_the_hierarchy_does_not_hold_is_refused(self, broken):
        """Criterion 18, one direction."""
        def mutate(doc):
            doc["datasets"].append({**_entry(doc, "cp-clients"), "id": "cp-nobody"})
        errors = broken(mutate)
        assert any("cp-nobody" in (e.scope or "") and "hierarchy" in e.problem
                   for e in errors), _text(errors)

    def test_a_collection_the_hierarchy_does_not_hold_is_refused(self, broken):
        def mutate(doc):
            doc["collections"].append({"id": "nowhere", "calendar": "daily"})
        errors = broken(mutate)
        assert any("nowhere" in (e.scope or "") for e in errors), _text(errors)

    def test_a_dataset_on_no_calendar_at_all_is_refused_naming_both_files(self, broken):
        """Criterion 18, the other direction: take the collection's
        calendar away and the dataset is on nothing."""
        def mutate(doc):
            doc["collections"] = [c for c in doc["collections"]
                                  if c["id"] != "civil-registration"]
        errors = broken(mutate)
        hit = [e for e in errors if "birth-registrations" in (e.scope or "")]
        assert hit and "calendar.yaml" in hit[0].problem + hit[0].fix, _text(errors)

    def test_some_months_with_no_reason_is_refused(self, broken):
        """Criterion 8."""
        def mutate(doc):
            _first(doc, "cp-case-workers").pop("reason")
        errors = broken(mutate)
        assert any("no reason" in e.problem for e in errors), _text(errors)

    @pytest.mark.parametrize("key", ["expected_time", "grace"])
    def test_a_version_with_no_expected_time_or_grace_is_refused(self, broken, key):
        """Criterion 29."""
        def mutate(doc):
            _first(doc, "birth-registrations").pop(key)
        errors = broken(mutate)
        assert any(key in e.problem and "birth-registrations" in (e.scope or "")
                   for e in errors), _text(errors)

    def test_a_version_that_drops_a_value_its_predecessor_stated_is_refused(self, broken):
        """Criterion 33 - restate, never inherit silently."""
        def mutate(doc):
            first = _first(doc, "cp-case-workers")
            second = {k: v for k, v in first.items() if k not in ("participates", "reason")}
            second["effective_from"] = "2026-01-01"
            second["changelog"] = [{"date": "2026-01-01", "author": "a test",
                                    "change": "dropped the months"}]
            _entry(doc, "cp-case-workers")["participation"]["versions"].append(second)
        errors = broken(mutate)
        assert any("leaves out" in e.problem and "participates" in e.problem
                   and "2026-01-01" in e.problem for e in errors), _text(errors)

    def test_two_versions_on_one_date_are_refused(self, broken):
        """Criterion 34."""
        def mutate(doc):
            versions = _entry(doc, "cp-clients")["participation"]["versions"]
            versions.append(dict(versions[0]))
        errors = broken(mutate)
        assert any("not after it" in e.problem for e in errors), _text(errors)

    def test_own_dates_reusing_a_calendar_period_name_are_refused(self, broken):
        """Criterion 35."""
        def mutate(doc):
            _entry(doc, "cp-carers")["dates"] = {"versions": [{
                "effective_from": "2023-01-01",
                "changelog": [{"date": "2023-01-01", "author": "a test", "change": "own"}],
                "dates": [{"period": "2024-Q1", "date": "2024-02-03"}]}]}
        errors = broken(mutate)
        assert any("2024-Q1" in e.problem for e in errors), _text(errors)


class TestTheContractsDetection:
    def test_a_contract_is_recognised_by_its_kind(self):
        """Criterion 32 - neither real contract states slaProperties any
        more, and both are still checked as contracts."""
        for name in ("bdm-birth-registrations-contract.yaml",
                     "child-protection-contract.yaml"):
            doc = yaml.safe_load((REAL_CONTRACT_DIR / name).read_text())
            assert doc["kind"] == "DataContract"
            assert "slaProperties" not in doc


class TestAnAssetWithNoCalendarsAtAll:
    def test_an_empty_list_of_calendars_is_accepted(self, broken):
        """Criterion 36 - the project-extraction shape: every dataset has
        supplies and no cadence, so the asset has no calendar to name."""
        from qa_tools.common import hierarchy

        def mutate(doc):
            doc["calendars"] = []
            doc["collections"] = []
            doc["datasets"] = [{"id": d.dataset_id, "no_calendar": "never"}
                               for d in hierarchy.all_datasets()]
        errors = broken(mutate)
        assert errors == [], _text(errors)


class TestDaysBeforeAtTheGate:
    """REQ-PIPE-113 criterion 1's whole number of days, at the gate."""

    @pytest.mark.parametrize("value", [-1, "1", 1.5])
    def test_a_value_that_is_not_a_whole_number_is_refused(self, broken, value):
        def mutate(doc):
            _first(doc, "cp-clients")["days_before"] = value
        errors = broken(mutate)
        assert any("days_before" in (e.problem + (e.field or "")) for e in errors), _text(errors)

    def test_a_version_that_drops_days_before_is_refused(self, broken):
        """REQ-PIPE-110 criterion 33, now that days before exists."""
        def mutate(doc):
            first = _first(doc, "cp-clients")
            first["days_before"] = 1
            second = {k: v for k, v in first.items() if k != "days_before"}
            second["effective_from"] = "2026-01-01"
            second["changelog"] = [{"date": "2026-01-01", "author": "a test",
                                    "change": "dropped days before"}]
            _entry(doc, "cp-clients")["participation"]["versions"].append(second)
        errors = broken(mutate)
        assert any("leaves out" in e.problem and "days_before" in e.problem
                   for e in errors), _text(errors)


class TestCriticFindingsOn110:
    """delivery-critic, 2026-10-11, on REQ-PIPE-110 as built (9bc389e).
    Each was a real gap against a signed criterion; each test failed
    before its fix."""

    def test_a_dataset_listed_twice_is_refused_not_last_one_wins(self, broken):
        def mutate(doc):
            doc["datasets"].append({**_entry(doc, "cp-clients")})
            doc["datasets"][-1]["participation"]["versions"][0] = {
                **_first(doc, "cp-clients"), "expected_time": "17:00"}
        errors = broken(mutate)
        assert any("cp-clients" in (e.scope or "") and "twice" in e.problem
                   for e in errors), _text(errors)

    def test_a_collection_listed_twice_is_refused(self, broken):
        def mutate(doc):
            doc["collections"].append({"id": "child-protection", "calendar": "daily"})
        errors = broken(mutate)
        assert any("child-protection" in (e.scope or "") and "twice" in e.problem
                   for e in errors), _text(errors)

    def test_a_not_expected_period_listed_twice_is_refused(self, broken):
        def mutate(doc):
            _entry(doc, "cp-clients")["not_expected"] = [
                {"period": "2026-Q1", "reason": "one"}, {"period": "2026-Q1", "reason": "two"}]
        errors = broken(mutate)
        assert any("2026-Q1" in e.problem and "twice" in e.problem for e in errors), _text(errors)

    def test_the_loader_refuses_a_duplicate_dataset_too(self, tmp_path):
        doc = yaml.safe_load((REAL_CONTRACT_DIR / "calendar.yaml").read_text())
        doc["datasets"].append(dict(_entry(doc, "cp-clients")))
        path = tmp_path / "calendar.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        with pytest.raises(schedule.ScheduleConfigError, match="twice"):
            agreement.load(path)

    def test_months_on_an_older_version_against_a_cadence_rule_are_refused(self, broken):
        """Criterion 7: EACH participation version, against every calendar
        version it overlaps - not the newest alone."""
        def mutate(doc):
            first = _first(doc, "birth-registrations")
            first.update({"participates": ["August"], "reason": "a test"})
            second = {k: v for k, v in first.items() if k not in ("participates", "reason")}
            second.update({"effective_from": "2026-09-01", "participates": "all",
                           "reason": "back to every day",
                           "changelog": [{"date": "2026-09-01", "author": "a test",
                                          "change": "every day"}]})
            _entry(doc, "birth-registrations")["participation"]["versions"].append(second)
        errors = broken(mutate)
        assert any("birth-registrations" in (e.scope or "") and "cadence" in e.problem
                   for e in errors), _text(errors)

    def test_a_dataset_on_a_calendar_with_no_entry_is_refused(self, broken):
        """Criterion 3 - its collection names a calendar, so it is on one,
        and it has no participation."""
        def mutate(doc):
            doc["datasets"] = [d for d in doc["datasets"] if d["id"] != "cp-carers"]
        errors = broken(mutate)
        assert any("cp-carers" in (e.scope or "") and "participation" in e.problem
                   for e in errors), _text(errors)

    def test_a_month_typo_on_an_older_version_is_a_gate_error_not_a_traceback(self, broken):
        def mutate(doc):
            first = _first(doc, "cp-case-workers")
            second = dict(first, effective_from="2026-01-01", changelog=[
                {"date": "2026-01-01", "author": "a test", "change": "second"}])
            first["participates"] = ["Febuary", "August"]
            _entry(doc, "cp-case-workers")["participation"]["versions"].append(second)
        errors = broken(mutate)
        assert any("Febuary" in e.problem for e in errors), _text(errors)

    def test_an_impossible_expected_time_is_refused(self, broken):
        def mutate(doc):
            _first(doc, "cp-clients")["expected_time"] = "25:99"
        errors = broken(mutate)
        assert any("expected_time" in (e.problem + (e.field or "")) for e in errors), _text(errors)

    def test_a_missing_due_time_names_the_periods_and_where_it_looked(self, broken):
        """Criterion 29's message."""
        def mutate(doc):
            _first(doc, "cp-clients").pop("grace")
        errors = broken(mutate)
        hit = [e for e in errors if "grace" in e.problem and "cp-clients" in (e.scope or "")]
        assert hit, _text(errors)
        assert "2023-Q1" in hit[0].problem and "2023-02-01" in hit[0].problem, hit[0].problem
        assert "participation versions" in hit[0].problem, hit[0].problem
        assert "no a " not in hit[0].problem

    def test_a_plain_string_changelog_is_told_the_structured_shape(self, broken):
        def mutate(doc):
            _first(doc, "cp-clients")["changelog"] = ["2026-10-11: moved"]
        errors = broken(mutate)
        assert any("author" in e.fix for e in errors), _text(errors)

    def test_a_dataset_on_no_calendar_names_both_files(self, broken):
        """Criterion 18 says both files."""
        def mutate(doc):
            doc["collections"] = [c for c in doc["collections"]
                                  if c["id"] != "civil-registration"]
        errors = broken(mutate)
        hit = [e for e in errors if "birth-registrations" in (e.scope or "")]
        assert hit, _text(errors)
        both = hit[0].problem + hit[0].fix
        assert "calendar.yaml" in both and "data-asset.yaml" in both, both

    def test_a_datasets_own_calendar_beats_its_collections(self, tmp_path):
        """Criterion 11, which had no test of its own."""
        doc = yaml.safe_load((REAL_CONTRACT_DIR / "calendar.yaml").read_text())
        _entry(doc, "cp-clients")["calendar"] = "daily"
        path = tmp_path / "calendar.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        moved = agreement.load(path)
        assert moved.calendar_name_for("cp-clients") == "daily"
        assert moved.calendar_name_for("cp-carers") == "quarterly"


def test_the_runtime_refuses_older_months_against_a_cadence_rule_too(tmp_path):
    """Criterion 7 at runtime as well as at the gate: an older version's
    months against the daily rule used to drop those days silently."""
    doc = yaml.safe_load((REAL_CONTRACT_DIR / "calendar.yaml").read_text())
    first = _first(doc, "birth-registrations")
    first.update({"participates": ["August"], "reason": "a test"})
    second = dict(first, effective_from="2026-09-01", participates="all", changelog=[
        {"date": "2026-09-01", "author": "a test", "change": "every day"}])
    _entry(doc, "birth-registrations")["participation"]["versions"].append(second)
    path = tmp_path / "calendar.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    with pytest.raises(schedule.ScheduleConfigError, match="cadence rule"):
        schedule.periods_for_dataset("birth-registrations", until=date(2026, 9, 10),
                                     agreement=agreement.load(path))


class TestACorrectionMustBeComplete:
    """REQ-PIPE-111 criterion 4: every field, or the configuration is
    refused."""

    @pytest.mark.parametrize("missing", ["change_reference", "date", "author", "approver",
                                         "reason", "changes"])
    def test_each_field_is_required(self, broken, missing):
        def mutate(doc):
            correction = {"change_reference": "CAB-1", "date": "2026-10-11", "author": "a",
                          "approver": "fpycnkgvmt@privaterelay.appleid.com", "reason": "r",
                          "changes": [{"item": "x", "old": 1, "new": 2}]}
            correction.pop(missing)
            next(c for c in doc["calendars"] if c["name"] == "quarterly")["corrections"] = [
                correction]
        errors = broken(mutate)
        assert any(missing in (e.problem + (e.field or "")) for e in errors), _text(errors)
