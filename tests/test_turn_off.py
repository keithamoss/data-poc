"""Turning a dataset, or a whole collection, off (REQ-PIPE-179).

Written before the code, as the requirement's TEST FIRST NFR asks: a
turn-off that hides an owed period looks exactly like one that works, so
each case here was seen to fail first.

Two halves, as tests/test_collection_defaults.py is: what the one helper
answers for a dataset on a date, and the schedule gate's refusals, each
broken in ONE way against a copy of the real configuration.

Child Protection is quarterly - periods dated 1 February, May, August and
November - and takes its due time and grace from the collection, so a turn
off at 31 March 2025 leaves 2025-Q1 (1 February) owed and 2025-Q2 (1 May)
owing nothing.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import shutil

import yaml

from qa_tools.common import agreement, schedule
from qa_tools.common.validate_schedule import Source, validate
from tests.test_collection_defaults import (
    CP, LOG, REAL_CONTRACT_DIR, _collection, _defaults, _doc, _lift, _per_dataset, _text,
    _unshare, _versions)


@pytest.fixture
def broken(tmp_path):
    """The real configuration, copied, changed by `mutate` and gated - as
    tests/test_collection_defaults.py's own fixture does."""
    contract_dir = tmp_path / "contract"
    shutil.copytree(REAL_CONTRACT_DIR, contract_dir)
    src = Source(contract_dir / "data-asset.yaml", contract_dir)

    def apply(mutate):
        path = contract_dir / "calendar.yaml"
        doc = _per_dataset(_unshare(yaml.safe_load(path.read_text())))
        mutate(doc)
        path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return validate(src)

    return apply

OFF_LOG = [{"date": "2026-10-14", "author": "a test", "change": "turned off",
            "turns_off": True}]


def _turn_off(version: dict, to: str = "2025-03-31", reason: str = "supplier paused",
              log=None) -> dict:
    version.update(effective_to=to, turned_off_reason=reason)
    version["changelog"] = list(version.get("changelog") or []) + (log or OFF_LOG)
    return version


def _back_on(doc, dataset_id: str, on: str, **values) -> dict:
    """A later version of a dataset's own, restating what the first did."""
    first = {k: v for k, v in _versions(doc, dataset_id)[0].items()
             if k not in ("effective_to", "turned_off_reason", "changelog")}
    version = {**first, "effective_from": on, **values, "changelog": LOG}
    _versions(doc, dataset_id).append(version)
    return version


def _defaults_version(doc) -> dict:
    """Child Protection's one defaults version - put back as the real file
    has it (the shared helpers start from each dataset stating its own)."""
    block = _collection(doc).get("participation_defaults")
    if not block:
        _lift(doc, *CP)
        _defaults(doc, {"effective_from": "2023-01-01", "expected_time": "09:00",
                        "grace": "8h", "changelog": LOG})
        block = _collection(doc)["participation_defaults"]
    return block["versions"][0]


# ---- the one helper (criteria 1, 3, 5, 6, 7, 27) ----------------------

class TestADatasetTurnedOff:
    def test_it_owes_until_its_effective_to_and_nothing_after(self):
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        agr = agreement.from_doc(doc)
        on = agr.standing_on("cp-clients", date(2025, 2, 1))
        off = agr.standing_on("cp-clients", date(2025, 5, 1))
        assert on.state == agreement.OWING and on.turned_off is None
        assert off.state == agreement.TURNED_OFF
        assert (off.turned_off.effective_to, off.turned_off.reason, off.turned_off.level) \
            == (date(2025, 3, 31), "supplier paused", agreement.DATASET)

    def test_effective_to_is_inclusive(self):
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        agr = agreement.from_doc(doc)
        assert agr.standing_on("cp-clients", date(2025, 3, 31)).state == agreement.OWING
        assert agr.standing_on("cp-clients", date(2025, 4, 1)).state == agreement.TURNED_OFF

    def test_with_no_later_version_it_is_off_for_good(self):
        """Criterion 5."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        agr = agreement.from_doc(doc)
        off = agr.standing_on("cp-clients", date(2040, 1, 1))
        assert off.state == agreement.TURNED_OFF and off.turned_off.until is None

    def test_a_later_version_turns_it_back_on(self):
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        _back_on(doc, "cp-clients", "2026-01-01")
        agr = agreement.from_doc(doc)
        off = agr.standing_on("cp-clients", date(2025, 11, 1))
        assert off.turned_off.until == date(2026, 1, 1)
        assert agr.standing_on("cp-clients", date(2026, 2, 1)).state == agreement.OWING

    def test_the_turn_off_carries_the_last_versions_timing(self):
        """Criterion 27: 'the last applying version's resolved timing' -
        here the collection's due time, which the dataset took while on."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        off = agreement.from_doc(doc).standing_on("cp-clients", date(2025, 5, 1))
        assert (off.values.expected_time, off.values.grace) == ("09:00", timedelta(hours=8))

    def test_not_yet_owing_is_said_before_turned_off(self):
        doc = _unshare(_doc())
        _versions(doc, "cp-clients")[0]["effective_from"] = "2024-01-01"
        _turn_off(_versions(doc, "cp-clients")[0], to="2024-03-31")
        agr = agreement.from_doc(doc)
        assert agr.standing_on("cp-clients", date(2023, 6, 1)).state == agreement.NOT_YET_OWING

    def test_its_off_periods_are_not_periods_it_owes(self):
        """Criteria 4 and 13: no period, so no slot."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        _back_on(doc, "cp-clients", "2026-01-01")
        names = [p.period.name for p in
                 schedule.periods_for_dataset("cp-clients", agreement=agreement.from_doc(doc))]
        assert "2025-Q1" in names and "2026-Q1" in names
        assert not {"2025-Q2", "2025-Q3", "2025-Q4"} & set(names)


class TestACollectionTurnedOff:
    def test_every_dataset_taking_its_defaults_is_off(self):
        """Criterion 3, second half - one edit however many datasets."""
        doc = _unshare(_doc())
        _turn_off(_defaults_version(doc))
        agr = agreement.from_doc(doc)
        for ds in ("cp-clients", "cp-carers", "cp-placements"):
            off = agr.standing_on(ds, date(2025, 5, 1))
            assert off.state == agreement.TURNED_OFF, ds
            assert off.turned_off.level == agreement.COLLECTION

    def test_a_datasets_own_version_inside_the_gap_brings_it_alone_back(self):
        """Criterion 6."""
        doc = _unshare(_doc())
        _turn_off(_defaults_version(doc))
        _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00", grace="2h")
        agr = agreement.from_doc(doc)
        assert agr.standing_on("cp-carers", date(2025, 5, 1)).state == agreement.TURNED_OFF
        back = agr.standing_on("cp-carers", date(2025, 8, 1))
        assert back.state == agreement.OWING and back.brought_back is True
        assert agr.standing_on("cp-clients", date(2025, 8, 1)).state == agreement.TURNED_OFF

    def test_a_later_collection_version_does_not_end_a_datasets_own_turn_off(self):
        """Criterion 6, last clause."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0])
        _defaults_version(doc)
        _collection(doc)["participation_defaults"]["versions"].append(
            {**{k: v for k, v in _defaults_version(doc).items() if k != "changelog"},
             "effective_from": "2025-07-01", "changelog": LOG})
        agr = agreement.from_doc(doc)
        assert agr.standing_on("cp-clients", date(2025, 8, 1)).state == agreement.TURNED_OFF
        assert agr.standing_on("cp-carers", date(2025, 8, 1)).state == agreement.OWING

    def test_a_dataset_back_on_takes_none_of_its_collections_values(self):
        """Criterion 7: while the collection is off, nothing comes from it."""
        doc = _unshare(_doc())
        _defaults_version(doc)["claim_window"] = "10d"
        _turn_off(_defaults_version(doc))
        _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00", grace="2h")
        back = agreement.from_doc(doc).participation_on("cp-carers", date(2025, 8, 1))
        assert (back.expected_time, back.grace) == ("11:00", timedelta(hours=2))
        assert back.claim_window is None
        assert back.sources["claim_window"] == (agreement.FALLBACK, None)


class TestWhenItWasTurnedOff:
    def test_the_newest_turns_off_changelog_entry_dates_it(self):
        """Criterion 41, without a correction: the newest entry carrying
        turns_off: true."""
        doc = _unshare(_doc())
        _turn_off(_versions(doc, "cp-clients")[0], log=[
            {"date": "2026-09-01", "author": "a", "change": "off", "turns_off": True},
            {"date": "2026-10-02", "author": "a", "change": "moved", "turns_off": True},
            {"date": "2026-10-09", "author": "a", "change": "typo"}])
        off = agreement.from_doc(doc).standing_on("cp-clients", date(2025, 5, 1))
        assert off.turned_off.authored_on == date(2026, 10, 2)


# ---- the gate ------------------------------------------------------------

def _clean(errors, *words):
    """The errors naming every one of `words` - the gate reports the whole
    file, so a case looks only at what its one break produced."""
    return [e for e in errors if all(w in str(e) for w in words)]


class TestTheGateAcceptsATurnOff:
    def test_a_permanent_turn_off(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0])
        assert broken(mutate) == []

    def test_a_temporary_one_with_no_restating_of_its_own_keys(self, broken):
        """Criterion 10: effective_to and turned_off_reason belong to the one
        version that states them, so the next version need not restate them."""
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0])
            _back_on(doc, "cp-clients", "2026-01-01")
        assert broken(mutate) == []

    def test_a_permanent_one_after_the_calendars_last_period(self, broken):
        """Criterion 9, last clause."""
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="2030-12-31")
        assert broken(mutate) == []


class TestTheKeysComeTogether:
    """Criterion 2."""

    def test_effective_to_without_a_reason(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0]).pop("turned_off_reason")
        got = _text(broken(mutate))
        assert "effective_to" in got and "turned_off_reason" in got and "cp-clients" in got

    def test_a_reason_without_effective_to(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0]).pop("effective_to")
        got = _text(broken(mutate))
        assert "turned_off_reason" in got and "effective_to" in got

    def test_reason_in_place_of_turned_off_reason_is_named(self, broken):
        def mutate(doc):
            v = _turn_off(_versions(doc, "cp-clients")[0])
            v["reason"] = v.pop("turned_off_reason")
        got = _text(broken(mutate))
        assert "turned_off_reason is the key" in got
        assert "only some periods" in got


class TestTheChangelogSaysItTurnsOff:
    """Criterion 40."""

    def test_no_turns_off_entry_prints_one_to_paste(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0],
                      log=[{"date": "2026-10-14", "author": "a", "change": "off"}])
        errors = broken(mutate)
        got = _text(errors)
        assert "cp-clients" in got and "2023-01-01" in got
        assert "\n      turns_off: true" in got
        assert "\n    - date: " in got

    @pytest.mark.parametrize("value", [False, "yes", 1])
    def test_turns_off_accepts_only_true(self, broken, value):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], log=[
                {"date": "2026-10-14", "author": "a", "change": "off", "turns_off": value}])
        assert "turns_off" in _text(broken(mutate))

    def test_on_a_collection_version_too(self, broken):
        def mutate(doc):
            _turn_off(_defaults_version(doc),
                      log=[{"date": "2026-10-14", "author": "a", "change": "off"}])
        got = _text(broken(mutate))
        assert "child-protection" in got and "turns_off: true" in got


class TestEffectiveToFits:
    """Criterion 9."""

    def test_before_its_own_effective_from(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="2022-12-31")
        got = _text(broken(mutate))
        assert "before" in got and "2022-12-31" in got and "cp-clients" in got

    def test_on_or_after_the_next_versions_effective_from(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="2026-01-01")
            _back_on(doc, "cp-clients", "2026-01-01")
        got = _text(broken(mutate))
        assert "2026-01-01" in got and "next version" in got

    def test_a_gap_holding_no_period(self, broken):
        """31 March to 1 April 2025 - no Child Protection period between."""
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="2025-03-31")
            _back_on(doc, "cp-clients", "2025-04-15")
        got = _text(broken(mutate))
        assert "no period" in got and "2025-03-31" in got


class TestNotInheritable:
    """Criterion 10."""

    def test_turned_off_reason_inherit_is_refused(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], reason="inherit")
        assert "turned_off_reason" in _text(broken(mutate))

    def test_effective_to_inherit_is_refused(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0], to="inherit")
        assert "effective_to" in _text(broken(mutate))


class TestBackOnInsideTheCollectionsGap:
    """Criterion 7, the gate half."""

    def test_a_value_the_collection_supplied_must_be_stated(self, broken):
        def mutate(doc):
            _turn_off(_defaults_version(doc))
            _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00")
        got = _text(broken(mutate))
        assert "cp-carers" in got and "grace" in got and "8h" in got

    def test_stating_them_all_is_accepted(self, broken):
        def mutate(doc):
            _turn_off(_defaults_version(doc))
            _back_on(doc, "cp-carers", "2025-07-01", expected_time="11:00", grace="2h")
        assert broken(mutate) == []


class TestNotExpectedInsideAGap:
    """Criterion 21."""

    def test_its_own_gap(self, broken):
        def mutate(doc):
            _turn_off(_versions(doc, "cp-clients")[0])
            next(d for d in doc["datasets"] if d["id"] == "cp-clients")["not_expected"] = [
                {"period": "2025-Q3", "reason": "no file"}]
        got = _text(broken(mutate))
        assert "2025-Q3" in got and "not_expected" in got and "supplier paused" in got
        assert "for good" in got

    def test_its_collections_gap(self, broken):
        def mutate(doc):
            _turn_off(_defaults_version(doc), reason="whole collection paused")
            next(d for d in doc["datasets"] if d["id"] == "cp-clients")["not_expected"] = [
                {"period": "2025-Q3", "reason": "no file"}]
        got = _text(broken(mutate))
        assert "2025-Q3" in got and "whole collection paused" in got
