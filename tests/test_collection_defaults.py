"""A collection's participation defaults, and inherit (REQ-PIPE-181).

Two halves, as tests/test_agreement.py is: the resolution - one function,
value by value, on each period's date - and the schedule gate's refusals,
each broken in ONE way against a copy of the real configuration.

Child Protection's five quarterly datasets share one anchored version in the
real file; most cases here move cp-clients' due time and grace up to the
collection, which is the change REQ-PIPE-181 exists to make one edit.
"""
from __future__ import annotations

import copy
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from qa_tools.common import agreement, schedule, slots
from qa_tools.common.validate_schedule import Source, validate

REAL_CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"
LOG = [{"date": "2023-01-01", "author": "a test", "change": "a test"}]


def _per_dataset(doc: dict) -> dict:
    """The premise these cases are written against: each Child Protection
    dataset stating its own due time and grace, and the collection stating
    nothing - the real file as it stood before its own migration."""
    for coll in doc["collections"]:
        coll.pop("participation_defaults", None)
        coll.pop("corrections", None)
    for entry in doc["datasets"]:
        entry.pop("corrections", None)
        if entry["id"].startswith("cp-"):
            entry["participation"]["versions"] = [
                {**v, "expected_time": v.get("expected_time", "09:00"),
                 "grace": v.get("grace", "8h")}
                for v in entry["participation"]["versions"]]
    return doc


def _doc() -> dict:
    return _per_dataset(copy.deepcopy(
        yaml.safe_load((REAL_CONTRACT_DIR / "calendar.yaml").read_text())))


def _entry(doc, dataset_id):
    return next(d for d in doc["datasets"] if d["id"] == dataset_id)


def _collection(doc, cid="child-protection"):
    return next(c for c in doc["collections"] if c["id"] == cid)


def _versions(doc, dataset_id):
    return _entry(doc, dataset_id)["participation"]["versions"]


def _unshare(doc):
    """Give every dataset its own copy of its versions - the real file
    anchors one version across five, so an edit to one would be an edit to
    all."""
    for entry in doc["datasets"]:
        if entry.get("participation"):
            entry["participation"]["versions"] = [dict(v) for v in
                                                  entry["participation"]["versions"]]
    return doc


def _defaults(doc, *versions, cid="child-protection"):
    _collection(doc, cid)["participation_defaults"] = {"versions": list(versions)}


def _lift(doc, *datasets, keys=("expected_time", "grace")):
    """Take `keys` off each dataset's versions, so they come from above."""
    for ds in datasets:
        for v in _versions(doc, ds):
            for k in keys:
                v.pop(k, None)


CP = ("cp-clients", "cp-notifications", "cp-investigations", "cp-placements", "cp-carers",
      "cp-case-workers")


# ---- resolution -------------------------------------------------------

class TestEachValueResolvesSeparately:
    """Criteria 1 and 2."""

    def test_a_dataset_saying_nothing_takes_its_collections_due_time(self):
        doc = _unshare(_doc())
        _lift(doc, "cp-clients")
        _defaults(doc, {"effective_from": "2023-01-01", "expected_time": "10:30",
                        "grace": "2h", "changelog": LOG})
        got = agreement.from_doc(doc).participation_on("cp-clients", date(2024, 2, 1))
        assert (got.expected_time, got.grace) == ("10:30", timedelta(hours=2))
        assert got.sources["expected_time"] == (agreement.COLLECTION, date(2023, 1, 1))

    def test_a_value_the_dataset_states_wins(self):
        doc = _unshare(_doc())
        _lift(doc, "cp-clients", keys=("grace",))
        _defaults(doc, {"effective_from": "2023-01-01", "expected_time": "10:30",
                        "grace": "2h", "changelog": LOG})
        got = agreement.from_doc(doc).participation_on("cp-clients", date(2024, 2, 1))
        assert got.expected_time == "09:00"            # its own
        assert got.grace == timedelta(hours=2)         # its collection's
        assert got.sources["expected_time"][0] == agreement.DATASET

    def test_each_level_uses_its_own_version_in_force_on_the_periods_date(self):
        doc = _unshare(_doc())
        _lift(doc, "cp-clients")
        _defaults(doc,
                  {"effective_from": "2023-01-01", "expected_time": "09:00", "grace": "8h",
                   "changelog": LOG},
                  {"effective_from": "2025-01-01", "expected_time": "09:00", "grace": "1h",
                   "changelog": LOG})
        agr = agreement.from_doc(doc)
        assert agr.participation_on("cp-clients", date(2024, 11, 1)).grace == timedelta(hours=8)
        assert agr.participation_on("cp-clients", date(2025, 2, 1)).grace == timedelta(hours=1)
        before = slots.slot_instants("cp-clients", date(2024, 11, 1), agreement=agr)
        after = slots.slot_instants("cp-clients", date(2025, 2, 1), agreement=agr)
        assert (before.grace, after.grace) == (timedelta(hours=8), timedelta(hours=1))

    def test_nothing_states_it_takes_the_fallback(self):
        """REQ-PIPE-110 criterion 6: no days before, the calendar's window."""
        doc = _unshare(_doc())
        _defaults(doc, {"effective_from": "2023-01-01", "grace": "2h", "changelog": LOG})
        got = agreement.from_doc(doc).participation_on("cp-clients", date(2024, 2, 1))
        assert got.days_before == 0 and got.claim_window is None
        assert got.sources["claim_window"] == (agreement.FALLBACK, None)

    def test_the_months_carry_their_reason_from_the_level_that_gave_them(self):
        """Criterion 18."""
        doc = _unshare(_doc())
        _defaults(doc, {"effective_from": "2023-01-01", "participates": ["February", "August"],
                        "reason": "half-yearly by agreement", "changelog": LOG})
        agr = agreement.from_doc(doc)
        got = agr.participation_on("cp-clients", date(2024, 2, 1))
        assert got.participates == (2, 8) and got.reason == "half-yearly by agreement"
        assert {p.date.month for p in schedule.periods_for_dataset("cp-clients", agreement=agr)} \
            == {2, 8}


class TestNotYetOwingTakesNothing:
    """Criterion 3."""

    def test_before_the_datasets_first_version_it_resolves_to_nothing(self):
        doc = _unshare(_doc())
        _versions(doc, "cp-clients")[0]["effective_from"] = "2025-01-01"
        _defaults(doc, {"effective_from": "2023-01-01", "expected_time": "10:30",
                        "grace": "2h", "changelog": LOG})
        agr = agreement.from_doc(doc)
        assert agr.participation_on("cp-clients", date(2024, 6, 1)) is None
        assert min(p.date for p in schedule.periods_for_dataset("cp-clients", agreement=agr)) \
            == date(2025, 2, 1)


class TestInherit:
    """Criterion 5."""

    def test_inherit_goes_back_to_the_collections_value(self):
        doc = _unshare(_doc())
        first = _versions(doc, "cp-clients")[0]
        _versions(doc, "cp-clients").append(
            {**first, "effective_from": "2025-01-01", "grace": "inherit", "changelog": LOG})
        _defaults(doc, {"effective_from": "2023-01-01", "grace": "3h", "changelog": LOG})
        agr = agreement.from_doc(doc)
        assert agr.participation_on("cp-clients", date(2024, 11, 1)).grace == timedelta(hours=8)
        assert agr.participation_on("cp-clients", date(2025, 2, 1)).grace == timedelta(hours=3)


# ---- the gate ----------------------------------------------------------

@pytest.fixture
def broken(tmp_path):
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


def _text(errors):
    return "\n".join(f"{e.file} | {e.scope} | {e.problem} | {e.fix}" for e in errors)


class TestTheGateAcceptsTheShape:
    def test_due_time_and_grace_stated_once_for_the_collection(self, broken):
        def mutate(doc):
            _lift(doc, *CP)
            _defaults(doc, {"effective_from": "2023-01-01", "expected_time": "09:00",
                            "grace": "8h", "changelog": LOG})
        errors = broken(mutate)
        assert not [e for e in errors if "expected_time" in e.problem or "grace" in e.problem
                    or "inherit" in e.problem], _text(errors)


class TestTheRestateRuleAtEveryLevel:
    """Criteria 4 and 7."""

    def test_a_collection_version_dropping_a_value_is_refused(self, broken):
        def mutate(doc):
            _defaults(doc,
                      {"effective_from": "2023-01-01", "grace": "8h", "changelog": LOG},
                      {"effective_from": "2025-01-01", "claim_window": "7d", "changelog": LOG})
        errors = broken(mutate)
        hit = [e for e in errors if "collection 'child-protection'" == e.scope
               and "leaves out" in e.problem]
        assert hit and "2025-01-01" in hit[0].problem and "grace" in hit[0].problem \
            and "'8h'" in hit[0].problem, _text(errors)

    def test_inherit_counts_as_stated_for_the_next_version(self, broken):
        """The REQ-PIPE-110 criterion 33 amendment."""
        def mutate(doc):
            _defaults(doc, {"effective_from": "2023-01-01", "grace": "3h", "changelog": LOG})
            first = _versions(doc, "cp-clients")[0]
            third = {k: v for k, v in first.items() if k != "grace"}
            _versions(doc, "cp-clients").extend([
                {**first, "effective_from": "2024-01-01", "grace": "inherit", "changelog": LOG},
                {**third, "effective_from": "2025-01-01", "changelog": LOG}])
        errors = broken(mutate)
        hit = [e for e in errors if e.scope == "dataset 'cp-clients'" and "leaves out" in e.problem]
        assert hit and "'inherit'" in hit[0].problem and "2025-01-01" in hit[0].problem, \
            _text(errors)

    def test_the_refusal_offers_inherit_and_what_it_would_take(self, broken):
        def mutate(doc):
            _defaults(doc, {"effective_from": "2023-01-01", "grace": "3h", "changelog": LOG})
            first = _versions(doc, "cp-clients")[0]
            _versions(doc, "cp-clients").append(
                {**{k: v for k, v in first.items() if k != "grace"},
                 "effective_from": "2025-01-01", "changelog": LOG})
        errors = broken(mutate)
        hit = [e for e in errors if e.scope == "dataset 'cp-clients'" and "leaves out" in e.problem]
        assert hit, _text(errors)
        assert "grace: inherit" in hit[0].fix and "'3h'" in hit[0].fix \
            and "set for Child Protection, since 1 Jan 2023" in hit[0].fix, hit[0].fix

    def test_with_nothing_above_it_offers_restating_only(self, broken):
        def mutate(doc):
            first = _versions(doc, "cp-clients")[0]
            _versions(doc, "cp-clients").append(
                {**{k: v for k, v in first.items() if k != "grace"},
                 "effective_from": "2025-01-01", "changelog": LOG})
        errors = broken(mutate)
        hit = [e for e in errors if e.scope == "dataset 'cp-clients'" and "leaves out" in e.problem]
        assert hit and "inherit" not in hit[0].fix, _text(errors)


class TestInheritOnlyWhereSomethingWasStated:
    """Criterion 6, at both levels, and criterion 10."""

    def test_on_a_datasets_first_version(self, broken):
        def mutate(doc):
            _versions(doc, "cp-clients")[0]["claim_window"] = "inherit"
        errors = broken(mutate)
        assert any(e.scope == "dataset 'cp-clients'" and "claim_window: inherit" in e.problem
                   and "Leave" in e.fix for e in errors), _text(errors)

    def test_on_a_collections_first_version(self, broken):
        def mutate(doc):
            _defaults(doc, {"effective_from": "2023-01-01", "days_before": "inherit",
                            "changelog": LOG})
        errors = broken(mutate)
        assert any(e.scope == "collection 'child-protection'" and "days_before: inherit"
                   in e.problem for e in errors), _text(errors)

    @pytest.mark.parametrize("key", ["expected_time", "grace"])
    def test_a_collection_never_inherits_a_due_time_or_grace(self, broken, key):
        def mutate(doc):
            _defaults(doc,
                      {"effective_from": "2023-01-01", key: "09:00" if key == "expected_time"
                       else "8h", "changelog": LOG},
                      {"effective_from": "2025-01-01", key: "inherit", "changelog": LOG})
        errors = broken(mutate)
        assert any(e.scope == "collection 'child-protection'" and f"{key}: inherit" in e.problem
                   and "resolves to nothing" in e.problem for e in errors), _text(errors)


class TestWideningIsNeverAKeyword:
    """Criterion 8."""

    def test_a_dataset_inheriting_all_from_a_list_is_refused_with_the_fix(self, broken):
        def mutate(doc):
            first = _versions(doc, "cp-case-workers")[0]
            _versions(doc, "cp-case-workers").append(
                {**first, "effective_from": "2025-01-01", "participates": "inherit",
                 "reason": first["reason"], "changelog": LOG})
        errors = broken(mutate)
        hit = [e for e in errors if e.scope == "dataset 'cp-case-workers'"
               and "newly owe" in e.problem]
        assert hit and "May" in hit[0].problem and "November" in hit[0].problem, _text(errors)
        assert "participates: [February, August]" in hit[0].fix and "reason:" in hit[0].fix

    def test_an_inherit_that_keeps_the_months_is_accepted(self, broken):
        def mutate(doc):
            _defaults(doc, {"effective_from": "2023-01-01", "participates": ["February", "August"],
                            "reason": "half-yearly", "changelog": LOG})
            first = _versions(doc, "cp-case-workers")[0]
            _versions(doc, "cp-case-workers").append(
                {**first, "effective_from": "2025-01-01", "participates": "inherit",
                 "changelog": LOG})
        errors = broken(mutate)
        assert not [e for e in errors if "newly owe" in e.problem], _text(errors)

    def test_a_collection_inheriting_all_names_each_dataset_affected(self, broken):
        def mutate(doc):
            _defaults(doc,
                      {"effective_from": "2023-01-01", "participates": ["February", "August"],
                       "reason": "half-yearly", "changelog": LOG},
                      {"effective_from": "2025-01-01", "participates": "inherit",
                       "changelog": LOG})
        errors = broken(mutate)
        hit = [e for e in errors if e.scope == "collection 'child-protection'"
               and "newly owe" in e.problem]
        assert hit and "cp-clients" in hit[0].problem \
            and "cp-case-workers" not in hit[0].problem, _text(errors)


class TestAnotherCalendarStatesItsOwn:
    """Criterion 9."""

    def test_a_dataset_on_its_own_calendar_taking_a_collection_value_is_refused(self, broken):
        def mutate(doc):
            _lift(doc, "cp-carers", keys=("grace",))
            _entry(doc, "cp-carers")["calendar"] = "daily"
            _defaults(doc, {"effective_from": "2023-01-01", "grace": "8h", "changelog": LOG})
        errors = broken(mutate)
        assert any(e.scope == "dataset 'cp-carers'" and "'daily'" in e.problem
                   and "'quarterly'" in e.problem and "grace" in e.problem
                   for e in errors), _text(errors)


class TestOrderAndOneRootCauseOnce:
    """Criteria 11 and 12."""

    def test_two_collection_versions_on_one_date_are_refused(self, broken):
        def mutate(doc):
            _defaults(doc, {"effective_from": "2023-01-01", "grace": "8h", "changelog": LOG},
                      {"effective_from": "2023-01-01", "grace": "8h", "changelog": LOG})
        errors = broken(mutate)
        assert any(e.scope == "collection 'child-protection'" and "not after it" in e.problem
                   for e in errors), _text(errors)

    def test_a_value_missing_for_several_datasets_is_reported_once(self, broken):
        def mutate(doc):
            _lift(doc, *CP, keys=("grace",))
            _defaults(doc, {"effective_from": "2023-01-01", "expected_time": "09:00",
                            "changelog": LOG})
        errors = broken(mutate)
        grace = [e for e in errors if "no grace" in e.problem]
        assert len(grace) == 1 and grace[0].scope == "collection 'child-protection'", \
            _text(errors)
        assert all(ds in grace[0].problem for ds in CP)


class TestMonthsAgainstACadenceRule:
    """Criterion 17: REQ-PIPE-110 criterion 7 applies to months a collection
    gives."""

    def test_a_collection_on_a_daily_calendar_naming_months_is_refused(self, broken):
        def mutate(doc):
            _defaults(doc, {"effective_from": "2023-01-01", "participates": ["February"],
                            "reason": "a test", "changelog": LOG}, cid="civil-registration")
        errors = broken(mutate)
        assert any(e.scope == "collection 'civil-registration'" and "cadence RULE" in e.problem
                   for e in errors), _text(errors)


# ---- frozen like a dataset's own versions (REQ-PIPE-111 c4, amended) ----

class TestACollectionsDefaultsFreeze:
    NOW = None

    def _check(self, change):
        from datetime import datetime, timezone

        from qa_tools.common import agreement_freeze as freeze

        at = datetime(2026, 10, 11, 3, 0, tzinfo=timezone(timedelta(hours=8)))
        old_cal = _unshare(_doc())
        _defaults(old_cal, {"effective_from": "2023-01-01", "claim_window": "21d",
                            "changelog": LOG})
        asset = yaml.safe_load((REAL_CONTRACT_DIR / "data-asset.yaml").read_text())
        people = yaml.safe_load((REAL_CONTRACT_DIR / "people.yaml").read_text())
        new_cal = copy.deepcopy(old_cal)
        change(new_cal)
        codeowners = (REAL_CONTRACT_DIR.parent / ".github" / "CODEOWNERS").read_text()
        return freeze.check(old_cal, new_cal, asset, copy.deepcopy(asset), people,
                            instant_of=lambda key: at, today=at.date(),
                            base_codeowners=codeowners)

    def test_changing_a_past_default_is_refused_on_the_collection(self):
        def mutate(doc):
            _collection(doc)["participation_defaults"]["versions"][0]["claim_window"] = "7d"
        found = self._check(mutate)
        hit = [f for f in found
               if "collection child-protection participation_defaults" in (f.scope or "")]
        assert hit and "collection 'child-protection'" in hit[0].fix, \
            "\n".join(f"{f.scope} | {f.problem} | {f.fix}" for f in found)

    def test_a_correction_on_the_collection_allows_it(self):
        key = "collection child-protection participation_defaults 2023-01-01"

        def mutate(doc):
            coll = _collection(doc)
            coll["participation_defaults"]["versions"][0]["claim_window"] = "7d"
            coll["corrections"] = [{
                "change_reference": "CAB-9", "date": "2026-10-11", "author": "a test",
                "approver": "fpycnkgvmt@privaterelay.appleid.com",
                "reason": "the agreed window was mistyped",
                "changes": [{"item": key, "old": {"claim_window": "21d"},
                             "new": {"claim_window": "7d"}}]}]
        found = self._check(mutate)
        assert found == [], "\n".join(f"{f.scope} | {f.problem} | {f.fix}" for f in found)

    def test_a_collection_correction_reverts(self):
        from qa_tools.common import agreement_freeze as freeze

        doc = _unshare(_doc())
        _defaults(doc, {"effective_from": "2023-01-01", "claim_window": "7d", "changelog": LOG})
        before, _asset = freeze.revert(doc, {}, [(
            "collection child-protection participation_defaults 2023-01-01",
            {"claim_window": "21d"}, {"claim_window": "7d"})])
        assert _collection(before)["participation_defaults"]["versions"][0]["claim_window"] \
            == "21d"


# ---- shown with where each value came from (criteria 13-15) -------------

class TestWhereEachValueCameFrom:
    def _agr(self):
        doc = _unshare(_doc())
        _lift(doc, "cp-clients", keys=("grace",))
        _defaults(doc,
                  {"effective_from": "2023-01-01", "grace": "8h", "changelog": LOG},
                  {"effective_from": "2025-01-01", "grace": "1h", "changelog": LOG})
        return agreement.from_doc(doc)

    def test_each_value_names_its_level_and_when_that_version_took_effect(self):
        from qa_tools.common import participation_view

        v = participation_view.view("cp-clients", date(2024, 6, 1), self._agr())
        values = {x.label: x for x in v.values}
        assert values["Grace"].text == "8h"
        assert values["Grace"].source == "set for Child Protection, since 1 Jan 2023"
        assert values["Due time"].source == "set for this dataset, since 1 Jan 2023"
        assert values["Claim window"].source.startswith("from the quarterly calendar, since ")
        assert "inherited" not in " ".join(x.source for x in v.values)

    def test_a_change_due_above_says_when_and_to_what(self):
        from qa_tools.common import participation_view

        v = participation_view.view("cp-clients", date(2024, 6, 1), self._agr())
        assert {x.label: x for x in v.values}["Grace"].changes == "1 Jan 2025: 1h"

    def test_no_level_stating_a_value_says_so_and_gives_the_fallback(self):
        from qa_tools.common import participation_view

        v = participation_view.view("cp-clients", date(2024, 6, 1), self._agr())
        assert {x.label: x for x in v.values}["Days before"].source \
            == "no level states this - so none"

    def test_before_the_first_version_it_is_not_yet_owing(self):
        from qa_tools.common import participation_view

        v = participation_view.view("cp-clients", date(2020, 6, 1), self._agr())
        assert v.not_yet == date(2023, 1, 1) and v.values == ()

    def test_schedule_show_takes_on(self):
        from click.testing import CliRunner

        from cli import schedule as schedule_cli

        got = CliRunner().invoke(schedule_cli.schedule_group,
                                 ["show", "--dataset", "cp-clients", "--on", "2020-06-01"])
        assert got.exit_code == 0, got.output
        assert "not yet owing - first version takes effect 1 Jan 2023" in got.output

    def test_the_calendar_entry_uses_the_same_renderer(self, supply_dsn, monkeypatch):
        from cli import common
        from cli import schedule as schedule_cli
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(label="test-collection-defaults") as c:
            qa_store.ensure_schema(c)

        shown = []
        monkeypatch.setattr(schedule_cli, "_show_values", shown.append)
        answers = iter(["cp-clients", None])
        monkeypatch.setattr(common, "select", lambda *a, **k: next(answers))
        monkeypatch.setattr(common, "text_prompt", lambda *a, **k: "2024-06-01")
        schedule_cli.calendar_menu()
        assert shown and shown[0].dataset_id == "cp-clients" and shown[0].on == date(2024, 6, 1)


# ---- delivery-critic on REQ-PIPE-181 (post-build-review #150) ----------

class TestCriticFindingsOn181:
    """Each failed before its fix."""

    def test_f1_a_dataset_naming_its_collections_own_calendar_is_still_widened(self, broken):
        def mutate(doc):
            _entry(doc, "cp-clients")["calendar"] = "quarterly"
            _defaults(doc,
                      {"effective_from": "2023-01-01", "participates": ["February", "August"],
                       "reason": "half-yearly", "changelog": LOG},
                      {"effective_from": "2025-01-01", "participates": "inherit",
                       "changelog": LOG})
        errors = broken(mutate)
        hit = [e for e in errors if e.scope == "collection 'child-protection'"
               and "newly owe" in e.problem]
        assert hit and "cp-clients" in hit[0].problem, _text(errors)

    def test_f2_inherited_months_need_no_reason_restated(self, broken):
        """Keith, 2026-10-11: the reason belongs to the months, so it comes
        with them from above."""
        def mutate(doc):
            _defaults(doc, {"effective_from": "2023-01-01", "participates": ["February", "August"],
                            "reason": "half-yearly", "changelog": LOG})
            first = _versions(doc, "cp-case-workers")[0]
            _versions(doc, "cp-case-workers").append(
                {**{k: v for k, v in first.items() if k != "reason"},
                 "effective_from": "2025-01-01", "participates": "inherit", "changelog": LOG})
        errors = broken(mutate)
        assert not [e for e in errors if "cp-case-workers" in (e.scope or "")], _text(errors)

    def test_f2_a_reason_beside_inherited_months_is_refused(self, broken):
        def mutate(doc):
            _defaults(doc, {"effective_from": "2023-01-01", "participates": ["February", "August"],
                            "reason": "half-yearly", "changelog": LOG})
            first = _versions(doc, "cp-case-workers")[0]
            _versions(doc, "cp-case-workers").append(
                {**first, "effective_from": "2025-01-01", "participates": "inherit",
                 "changelog": LOG})
        errors = broken(mutate)
        assert any(e.scope == "dataset 'cp-case-workers'" and "reason" in e.problem
                   and "inherit" in e.problem for e in errors), _text(errors)

    def test_f3_inherit_is_not_offered_where_it_would_widen(self, broken):
        def mutate(doc):
            _defaults(doc, {"effective_from": "2023-01-01",
                            "participates": ["February", "May", "August", "November"],
                            "reason": "quarterly", "changelog": LOG})
            first = _versions(doc, "cp-case-workers")[0]
            _versions(doc, "cp-case-workers").append(
                {**{k: v for k, v in first.items() if k not in ("participates", "reason")},
                 "effective_from": "2025-01-01", "changelog": LOG})
        errors = broken(mutate)
        hit = [e for e in errors if e.scope == "dataset 'cp-case-workers'"
               and "leaves out" in e.problem]
        assert hit and "participates: inherit" not in hit[0].fix, _text(errors)

    def test_f4_the_claim_window_offer_names_what_it_would_really_take(self, broken):
        def mutate(doc):
            _versions(doc, "cp-clients")[0]["claim_window"] = "10d"
            first = _versions(doc, "cp-clients")[0]
            _versions(doc, "cp-clients").append(
                {**{k: v for k, v in first.items() if k != "claim_window"},
                 "effective_from": "2024-01-01", "changelog": LOG})
            _defaults(doc, {"effective_from": "2023-01-01", "claim_window": "7d", "changelog": LOG},
                      {"effective_from": "2025-01-01", "claim_window": "inherit",
                       "changelog": LOG})
        errors = broken(mutate)
        hit = [e for e in errors if e.scope == "dataset 'cp-clients'" and "leaves out" in e.problem]
        assert hit and "'7d'" in hit[0].fix and "quarterly calendar" in hit[0].fix, _text(errors)

    def test_f5_the_collection_error_names_a_dataset_that_inherits_after_stating(self, broken):
        def mutate(doc):
            first = _versions(doc, "cp-clients")[0]
            _versions(doc, "cp-clients")[0] = {**first, "participates": ["February", "August"],
                                               "reason": "half-yearly"}
            _versions(doc, "cp-clients").append(
                {**first, "effective_from": "2024-01-01", "participates": "inherit",
                 "changelog": LOG})
            _defaults(doc,
                      {"effective_from": "2023-01-01", "participates": ["February", "August"],
                       "reason": "half-yearly", "changelog": LOG},
                      {"effective_from": "2025-01-01", "participates": "inherit",
                       "changelog": LOG})
        errors = broken(mutate)
        hit = [e for e in errors if e.scope == "collection 'child-protection'"
               and "newly owe" in e.problem]
        assert hit and "cp-clients" in hit[0].problem, _text(errors)

    def test_f6_with_no_defaults_each_dataset_keeps_its_own_message(self, broken):
        """Keith, 2026-10-11: once only where the collection has defaults."""
        def mutate(doc):
            _lift(doc, "cp-clients", "cp-carers", keys=("grace",))
        errors = broken(mutate)
        grace = [e for e in errors if "no grace" in e.problem]
        assert {e.scope for e in grace} == {"dataset 'cp-clients'", "dataset 'cp-carers'"}, \
            _text(errors)

    def test_f6_datasets_on_another_calendar_are_not_grouped(self, broken):
        def mutate(doc):
            _lift(doc, "cp-clients", "cp-carers", keys=("grace",))
            for ds in ("cp-clients", "cp-carers"):
                _entry(doc, ds)["calendar"] = "daily"
            _defaults(doc, {"effective_from": "2023-01-01", "grace": "8h", "changelog": LOG})
        errors = broken(mutate)
        assert not [e for e in errors if e.scope == "collection 'child-protection'"
                    and "no grace" in e.problem], _text(errors)

    def test_f7_a_later_calendar_window_is_shown_as_a_change(self):
        from qa_tools.common import participation_view

        doc = _unshare(_doc())
        quarterly = next(c for c in doc["calendars"] if c["name"] == "quarterly")
        last = quarterly["versions"][-1]
        quarterly["versions"].append({**last, "effective_from": "2026-01-01",
                                      "claim_window": "21d", "dates": [
                                          d for d in last.get("dates") or []
                                          if str(d["date"]) >= "2026-01-01"],
                                      "changelog": LOG})
        v = participation_view.view("cp-clients", date(2024, 3, 1), agreement.from_doc(doc))
        window = {x.label: x for x in v.values}["Claim window"]
        assert window.source.startswith("from the quarterly calendar, since"), window.source
        assert window.changes == "1 Jan 2026: 21d", window.changes

    def test_f8_a_dataset_with_no_versions_renders_without_crashing(self, capsys):
        from cli import schedule as schedule_cli
        from qa_tools.common import participation_view

        schedule_cli._show_values(participation_view.View("x", date(2024, 1, 1), None, ()))
        assert "no participation" in capsys.readouterr().out

    @pytest.mark.parametrize("value", ["Inherit", "INHERIT"])
    def test_f9_a_miscased_inherit_is_named_as_such(self, broken, value):
        def mutate(doc):
            first = _versions(doc, "cp-clients")[0]
            _versions(doc, "cp-clients").append(
                {**first, "effective_from": "2025-01-01", "grace": value, "changelog": LOG})
        errors = broken(mutate)
        assert any("lower case" in e.problem + e.fix for e in errors), _text(errors)

    def test_drift_attributes_a_collection_value_to_the_collection(self):
        from qa_tools.common import agreement_drift

        doc = _unshare(_doc())
        _lift(doc, "cp-clients", keys=("grace",))
        _defaults(doc, {"effective_from": "2023-01-01", "grace": "8h", "changelog": LOG})
        keys = agreement_drift._sources("cp-clients", "2024-Q1", date(2024, 2, 1),
                                        agreement.from_doc(doc), None)
        assert "collection child-protection participation_defaults 2023-01-01" in keys
        assert agreement_drift._kind(
            "collection child-protection participation_defaults 2023-01-01") == "defaults"

    def test_a_collection_correction_affects_its_datasets_not_one_on_its_own_calendar(self):
        from qa_tools.common import correction_apply

        doc = _unshare(_doc())
        _entry(doc, "cp-carers")["calendar"] = "daily"
        p = correction_apply.Pending(
            reference="CAB-2", owner=("collection", "child-protection"), label="l",
            date="2026-10-11", reason="r", approver="a",
            changes=(("collection child-protection participation_defaults 2023-01-01", None,
                      {"grace": "8h"}),))
        got = correction_apply.affected_datasets(p, doc)
        assert "cp-clients" in got and "cp-carers" not in got

    def test_a_long_value_in_a_drafted_correction_pastes_as_valid_yaml(self):
        """Found migrating Child Protection (2026-10-11): cp-case-workers'
        reason wrapped the drafted `old:` across lines at the wrong indent, so
        the entry the gate and the draft offer could not be pasted as given."""
        from qa_tools.common import agreement_freeze

        value = {"participates": ["February", "August"],
                 "reason": "A staffing register rather than casework, so it is resupplied "
                           "twice a year rather than quarterly.",
                 "expected_time": "09:00", "grace": "8h"}
        text = agreement_freeze._value_text(value)
        assert "\n" not in text
        pasted = yaml.safe_load(f"corrections:\n  - changes:\n      - old: {text}\n")
        assert pasted["corrections"][0]["changes"][0]["old"] == value


class TestTheRealContractStatesChildProtectionOnce:
    """Keith, 2026-10-11 (morning report (v)): Child Protection's due time and
    grace moved up to the collection, by a declared correction, unchanged."""

    def test_every_child_protection_dataset_takes_them_from_the_collection(self):
        agr = agreement.current()
        for ds in CP:
            got = agr.participation_on(ds, date(2024, 2, 1))
            assert (got.expected_time, got.grace) == ("09:00", timedelta(hours=8)), ds
            assert got.sources["grace"] == (agreement.COLLECTION, date(2023, 1, 1)), ds

    def test_no_slot_moved(self):
        """The migration changes where a value is written, never a due instant."""
        agr = agreement.current()
        due = slots.slot_instants("cp-clients", date(2024, 2, 1), agreement=agr)
        assert due.due_at.isoformat() == "2024-02-01T09:00:00+08:00"
        assert due.grace == timedelta(hours=8)
