"""The schedule gate's rules for files_go_to_period (REQ-PIPE-320 criteria 3
to 7, 9 and 13; REQ-PIPE-324 criteria 1 and 4).

Each test copies the real contract directory, breaks contract/calendar.yaml
in one way and requires the gate to name it. The real file is untouched.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from qa_tools.common.validate_schedule import Source, validate

REAL = Path(__file__).resolve().parent.parent / "contract"


def _v(effective_from, value):
    return {"effective_from": effective_from, "value": value,
            "changelog": [{"date": "2026-10-30", "author": "a test", "change": "a test's value"}]}


@pytest.fixture
def gate(tmp_path):
    contract = tmp_path / "contract"
    shutil.copytree(REAL, contract)
    src = Source(contract / "data-asset.yaml", contract)
    cal_path = contract / "calendar.yaml"

    def run(mutate):
        doc = yaml.safe_load(cal_path.read_text())
        for c in doc["collections"]:
            c["files_go_to_period"] = {"versions": [_v("2000-01-01",
                                                       1 if c["id"] == "child-protection" else 0)]}
        mutate(doc)
        cal_path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return validate(src)
    return run


def _collection(doc, cid):
    return next(c for c in doc["collections"] if c["id"] == cid)


def _dataset(doc, did):
    return next(d for d in doc["datasets"] if d["id"] == did)


def _text(errors):
    return "\n".join(f"{e.scope or ''} | {e.problem} | {e.fix}" for e in errors)


def _offset_errors(errors):
    return [e for e in errors if "files_go_to_period" in f"{e.problem} {e.fix}"]


class TestTheValuesTheBatchStates:
    """REQ-PIPE-320 criterion 10: 0 for Civil Registration and Emergency
    Department, 1 for Child Protection, passes."""

    def test_the_intended_values_pass(self, gate):
        assert _offset_errors(gate(lambda doc: None)) == []


class TestItBelongsToTheCollection:
    """Criterion 3."""

    def test_a_dataset_entry_stating_it_is_refused_naming_the_collection(self, gate):
        def mutate(doc):
            _dataset(doc, "cp-carers")["files_go_to_period"] = {"versions": [_v("2000-01-01", 1)]}
        text = _text(_offset_errors(gate(mutate)))
        assert "cp-carers" in text and "belongs to the collection" in text
        assert "child-protection" in text

    def test_a_participation_version_stating_it_is_refused(self, gate):
        def mutate(doc):
            _dataset(doc, "cp-carers")["participation"]["versions"][0]["files_go_to_period"] = 1
        text = _text(_offset_errors(gate(mutate)))
        assert "cp-carers" in text and "belongs to the collection" in text


    def test_any_level_of_the_hierarchy_stating_it_is_refused(self, tmp_path):
        """Criterion 3's hierarchy case (critic test gap): a collection in
        contract/data-asset.yaml stating it is refused the same way."""
        contract = tmp_path / "contract"
        shutil.copytree(REAL, contract)
        path = contract / "data-asset.yaml"
        doc = yaml.safe_load(path.read_text())
        for agency in doc["hierarchy"]["agencies"]:
            for collection in agency.get("collections") or []:
                if collection["id"] == "child-protection":
                    collection["files_go_to_period"] = 1
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        text = _text(validate(Source(path, contract)))
        assert "files_go_to_period" in text and "hierarchy" in text
        assert "child-protection" in text


class TestACollectionWithNoCalendar:
    """Criterion 5 (critic test gap)."""

    def test_stating_it_is_refused_saying_there_are_no_periods(self, gate):
        def mutate(doc):
            ed = [d for d in doc["datasets"] if d["id"].startswith("ed-")]
            assert ed, "precondition: Emergency Department's datasets"
            for d in ed:
                d.pop("participation", None)
                d.pop("calendar", None)
                d["no_calendar"] = "a test's collection with no calendar"
        text = _text(_offset_errors(gate(mutate)))
        assert "emergency-department" in text
        assert "a collection with no calendar has no periods to send files to" in text


class TestEveryCollectionOnACalendarStatesIt:
    """Criterion 4 - no default."""

    def test_a_collection_with_none_is_refused_naming_its_first_round(self, gate):
        text = _text(_offset_errors(gate(
            lambda doc: _collection(doc, "emergency-department").pop("files_go_to_period"))))
        assert "emergency-department" in text
        assert "first round" in text

    def test_a_first_version_starting_after_the_first_round_is_refused(self, gate):
        def mutate(doc):
            _collection(doc, "emergency-department")["files_go_to_period"] = {
                "versions": [_v("2024-06-01", 0)]}
        text = _text(_offset_errors(gate(mutate)))
        assert "emergency-department" in text and "first round" in text


class TestACadenceRuleCalendarKeepsDaysBefore:
    """Criterion 7, with REQ-PIPE-324 criterion 4's pointer."""

    def test_a_non_zero_value_on_the_daily_calendar_is_refused(self, gate):
        def mutate(doc):
            _collection(doc, "civil-registration")["files_go_to_period"] = {
                "versions": [_v("2000-01-01", 1)]}
        text = _text(_offset_errors(gate(mutate)))
        assert "civil-registration" in text and "days before" in text and "at most 1" in text


class TestADatasetWithItsOwnDatesIsOnlySupportedAtZero:
    """Criterion 13."""

    def test_own_dates_under_a_non_zero_collection_is_refused(self, gate):
        def mutate(doc):
            d = _dataset(doc, "cp-carers")
            versions = d["participation"]["versions"]
            for v in versions:
                v.pop("participates", None)
            d["dates"] = {"versions": [{
                "effective_from": "2015-01-01",
                "changelog": [{"date": "2026-10-30", "author": "a test", "change": "own dates"}],
                "dates": [{"period": "2025-Q1", "date": "2025-02-01"}]}]}
        text = _text(_offset_errors(gate(mutate)))
        assert "cp-carers" in text and "own dates" in text and "only at 0" in text


class TestANegativeValueIsRefused:
    """Criterion 6."""

    def test_minus_one_is_refused(self, gate):
        def mutate(doc):
            _collection(doc, "child-protection")["files_go_to_period"] = {
                "versions": [_v("2000-01-01", -1)]}
        errors = gate(mutate)
        assert any("files_go_to_period" in f"{e.problem} {e.fix} {e.scope}" or
                   "value" in f"{e.problem}" for e in errors)
        assert errors


    def test_a_fraction_is_refused_naming_the_collection_and_the_version(self, gate):
        """Criterion 6 as worded (critic finding 10): the refusal names the
        collection and the version by its effective_from - not a schema
        path of indices."""
        def mutate(doc):
            _collection(doc, "child-protection")["files_go_to_period"] = {
                "versions": [_v("2000-01-01", 1.5)]}
        text = _text(gate(mutate))
        assert "collection 'child-protection', the version effective 2000-01-01" in text
        assert "a whole number of periods" in text


class TestTwoVersionsOnOneDateAreRefused:
    """Critic finding 10: two versions with one effective_from left which
    is in force to the order they were written in."""

    def test_refused_naming_the_date(self, gate):
        def mutate(doc):
            _collection(doc, "child-protection")["files_go_to_period"] = {
                "versions": [_v("2000-01-01", 1), _v("2000-01-01", 0)]}
        text = _text(gate(mutate))
        assert "child-protection" in text and "two files_go_to_period versions" in text
        assert "2000-01-01" in text


class TestAdoptingTheKeyOnFrozenHistory:
    """REQ-PIPE-320 criteria 8, 11 and 12: the freeze gate as built would refuse
    adopting the key on today's frozen history, so a first version at 0 from a
    collection's first round is allowed anywhere, and a synthetic asset may add
    or change a value without a correction."""

    import copy as _copy
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    AT = _dt(2026, 10, 30, 9, 0, tzinfo=_tz(_td(hours=8)))

    def _states(self):
        cal = yaml.safe_load((REAL / "calendar.yaml").read_text())
        for c in cal["collections"]:
            c.pop("files_go_to_period", None)
        asset = yaml.safe_load((REAL / "data-asset.yaml").read_text())
        people = yaml.safe_load((REAL / "people.yaml").read_text())
        return cal, asset, people

    def _check(self, old_cal, new_cal, asset, people, synthetic=True):
        from qa_tools.common import agreement_freeze as freeze

        old_asset, new_asset = self._copy.deepcopy(asset), self._copy.deepcopy(asset)
        old_asset["synthetic"] = new_asset["synthetic"] = synthetic
        return freeze.check(old_cal, new_cal, old_asset, new_asset, people,
                            instant_of=lambda key: self.AT, today=self.AT.date(),
                            base_codeowners=(REAL.parent / ".github" / "CODEOWNERS").read_text())

    def _with(self, cal, values, eff="2000-01-01"):
        new = self._copy.deepcopy(cal)
        for c in new["collections"]:
            if c["id"] in values:
                c["files_go_to_period"] = {"versions": [_v(eff, values[c["id"]])]}
        return new

    def test_a_first_version_at_zero_lands_without_a_correction_on_a_real_asset(self):
        cal, asset, people = self._states()
        new = self._with(cal, {"emergency-department": 0, "civil-registration": 0})
        assert self._check(cal, new, asset, people, synthetic=False) == []

    def test_a_first_version_at_one_over_frozen_rounds_needs_a_correction_on_a_real_asset(self):
        cal, asset, people = self._states()
        new = self._with(cal, {"child-protection": 1})
        found = self._check(cal, new, asset, people, synthetic=False)
        assert any("files_go_to_period" in f.scope for f in found)

    def test_a_synthetic_asset_adds_one_without_a_correction(self):
        cal, asset, people = self._states()
        new = self._with(cal, {"child-protection": 1, "emergency-department": 0,
                               "civil-registration": 0})
        assert self._check(cal, new, asset, people, synthetic=True) == []

    def test_a_synthetic_asset_changes_a_frozen_value_without_a_correction(self):
        cal, asset, people = self._states()
        old = self._with(cal, {"child-protection": 0})
        new = self._with(cal, {"child-protection": 1})
        assert self._check(old, new, asset, people, synthetic=True) == []

    def test_a_real_asset_changing_a_frozen_value_needs_a_correction(self):
        cal, asset, people = self._states()
        old = self._with(cal, {"child-protection": 0})
        new = self._with(cal, {"child-protection": 1})
        found = self._check(old, new, asset, people, synthetic=False)
        assert any("files_go_to_period" in f.scope for f in found)
