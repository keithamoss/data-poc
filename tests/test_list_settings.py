"""A list-valued effective-dated setting, read by the amber setting's own
mechanism (REQ-QAC-300 criteria 2, 5, 7, 8, 10, 11 and 12). Configuration
only; the documents here are built by hand except where the committed
configuration is the thing under test."""
from __future__ import annotations

import copy
from datetime import date

import pytest

from qa_tools.common import amber_setting, replacement_setting

PATH = ("list_settings", "census_years")


def _v(start, value, change="x"):
    return {"effective_from": start, "value": value,
            "changelog": [{"date": start, "author": "t", "change": change}]}


def _doc(*, coll_list=None, ds_list=None, asset_list=None):
    ds = {"id": "d1", "name": "D1", "table": "d1"}
    coll = {"id": "c1", "name": "Coll One", "datasets": [ds]}
    doc = {"amber_setting": {"versions": [_v("2013-01-01", "hold")]},
           "replacement_setting": {"versions": [_v("2013-01-01", "never"),
                                                _v("2020-03-01", "green")]},
           "hierarchy": {"agencies": [{"id": "a", "name": "A", "collections": [coll]}]}}
    if coll_list is not None:
        coll["list_settings"] = {"census_years": {"versions": coll_list}}
    if ds_list is not None:
        ds["list_settings"] = {"census_years": {"versions": ds_list}}
    if asset_list is not None:
        doc["list_settings"] = {"census_years": {"versions": asset_list}}
    return doc


FOUR = [_v("2013-01-01", [2011]), _v("2017-08-01", [2011, 2016]),
        _v("2022-08-01", [2011, 2016, 2021]), _v("2027-08-01", [2011, 2016, 2021, 2026])]


class TestCriterionTwelveSeenFailingFirst:
    def test_timeline_given_replacement_settings_key_returns_its_own_changes(self):
        doc = _doc()
        line = amber_setting.timeline("d1", doc=doc, key=replacement_setting.KEY)
        assert [(e["from"], e["value"]) for e in line] == [("2013-01-01", "never"),
                                                           ("2020-03-01", "green")]
        assert line[1]["text"] == "green (set for the whole data asset, since 1 Mar 2020)"

    def test_a_list_setting_on_the_collection_alone_resolves_with_no_asset_value(self):
        doc = _doc(coll_list=FOUR)
        r = amber_setting.resolve_on_date("d1", date(2018, 1, 1), doc=doc, key=PATH)
        assert (r.value, r.level, r.version) == ((2011, 2016), amber_setting.COLLECTION,
                                                 "2017-08-01")


class TestThePathAndTheTypedValue:
    def test_scalar_settings_resolve_as_text_as_before(self):
        r = amber_setting.resolve("d1", "2021-01-01T00:00:00+08:00", doc=_doc())
        assert r.value == "hold" and isinstance(r.value, str)

    def test_a_list_value_is_a_tuple_in_declared_order(self):
        doc = _doc(coll_list=[_v("2013-01-01", [2016, 2011])])
        assert amber_setting.resolve_on_date("d1", date(2014, 1, 1), doc=doc,
                                             key=PATH).value == (2016, 2011)

    def test_nearest_level_wins_for_a_list_setting(self):
        doc = _doc(coll_list=FOUR, ds_list=[_v("2013-01-01", [1999])])
        r = amber_setting.resolve_on_date("d1", date(2023, 1, 1), doc=doc, key=PATH)
        assert (r.value, r.level) == ((1999,), amber_setting.DATASET)

    def test_a_date_before_every_version_resolves_to_none(self):
        doc = _doc(coll_list=FOUR)
        assert amber_setting.resolve_on_date("d1", date(2012, 1, 1), doc=doc, key=PATH) is None

    def test_describe_words_a_list_generically(self):
        doc = _doc(coll_list=FOUR)
        assert amber_setting.describe("d1", date(2023, 1, 1), doc=doc, key=PATH) == (
            "2011, 2016 and 2021 (set for Coll One, since 1 Aug 2022)")
        assert amber_setting.describe("d1", date(2014, 1, 1), doc=doc, key=PATH) == (
            "2011 (set for Coll One, since 1 Jan 2013)")

    def test_timeline_of_a_list_setting(self):
        line = amber_setting.timeline("d1", doc=_doc(coll_list=FOUR), key=PATH)
        assert [e["value"] for e in line] == [(2011,), (2011, 2016), (2011, 2016, 2021),
                                              (2011, 2016, 2021, 2026)]

    def test_the_amber_timeline_is_unchanged(self):
        doc = _doc(coll_list=FOUR)
        assert amber_setting.timeline("d1", doc=doc) == [
            {"from": "2013-01-01", "value": "hold", "level": amber_setting.ASSET,
             "version": "2013-01-01",
             "text": "hold (set for the whole data asset, since 1 Jan 2013)"}]


class TestCriterionElevenTheAssetLevelDemandIsTheSettingsOwn:
    def test_amber_and_replacement_still_demand_an_asset_value(self):
        doc = _doc()
        doc["amber_setting"] = {"versions": [_v("2099-01-01", "hold")]}
        assert any("no version is in effect today" in p
                   for _, p in amber_setting.standing_problems(doc, date(2026, 11, 1)))

    def test_a_list_setting_never_does(self):
        doc = _doc(coll_list=FOUR)
        assert amber_setting.standing_problems(doc, date(2026, 11, 1), key=PATH) == []

    def test_its_settings_are_found_at_every_level(self):
        doc = _doc(coll_list=FOUR, ds_list=FOUR, asset_list=FOUR)
        assert set(amber_setting._settings(doc, PATH)) == {
            amber_setting.ASSET, "collection c1", "dataset d1"}
        assert amber_setting.list_setting_keys(doc) == [PATH]


class TestCriterionEightTheFreezeIsAmberSettings:
    def test_altering_a_past_version_is_refused(self):
        old = _doc(coll_list=FOUR)
        new = copy.deepcopy(old)
        new["hierarchy"]["agencies"][0]["collections"][0]["list_settings"]["census_years"][
            "versions"][1]["value"] = [2011, 2016, 2021]
        problems = amber_setting.past_change_problems(old, new, date(2026, 11, 1),
                                                      synthetic=True, key=PATH)
        assert problems == [("collection c1", "the version effective 2017-08-01 has been "
                                              "altered, and its date has passed")]

    def test_a_future_version_may_still_change(self):
        old = _doc(coll_list=FOUR)
        new = copy.deepcopy(old)
        new["hierarchy"]["agencies"][0]["collections"][0]["list_settings"]["census_years"][
            "versions"][3]["value"] = [2011, 2016, 2021, 2026, 2031]
        assert amber_setting.past_change_problems(old, new, date(2026, 11, 1),
                                                  synthetic=False, key=PATH) == []

    def test_a_new_back_dated_version_is_refused_except_on_a_synthetic_asset(self):
        old = _doc(coll_list=FOUR[:1])
        new = _doc(coll_list=FOUR)
        assert amber_setting.past_change_problems(old, new, date(2026, 11, 1),
                                                  synthetic=True, key=PATH) == []
        refused = amber_setting.past_change_problems(old, new, date(2026, 11, 1),
                                                     synthetic=False, key=PATH)
        assert [w for w, _p in refused] == ["collection c1", "collection c1"]


class TestTheSchemaAcceptsAnyListSetting:
    def test_one_generic_model(self):
        from qa_tools.common.schemas import CollectionConfig

        c = CollectionConfig.model_validate({
            "id": "c", "name": "C", "short": "c", "run_prefix": "c_", "contract": "x.yaml",
            "datasets": [{"id": "d", "name": "D", "table": "d"}],
            "list_settings": {"anything": {"versions": [_v("2013-01-01", ["a", 1])]}}})
        assert c.list_settings["anything"].versions[0].value == ["a", 1]

    def test_a_non_list_value_is_refused(self):
        from pydantic import ValidationError

        from qa_tools.common.schemas import ListSetting

        with pytest.raises(ValidationError):
            ListSetting.model_validate({"versions": [_v("2013-01-01", "2011")]})


class TestTheScheduleGateFreezesEveryListSetting:
    """Criterion 8 through the gate itself: the schedule gate runs the amber
    setting's own guard for each entry list_settings declares."""

    def _errors(self, monkeypatch, old, new):
        from qa_tools.common import validate_schedule as vs
        import yaml

        monkeypatch.setattr(vs, "_content_at", lambda rel, ref: yaml.safe_dump(old))
        src = vs.Source(asset_path=vs.DATA_ASSET_YAML, contract_dir=vs.DATA_ASSET_YAML.parent)
        return vs._list_setting_errors(new, src, date(2026, 11, 1), ref="HEAD")

    def test_an_altered_past_census_version_is_refused(self, monkeypatch):
        old = _doc(coll_list=FOUR)
        old["synthetic"] = True
        new = copy.deepcopy(old)
        new["hierarchy"]["agencies"][0]["collections"][0]["list_settings"]["census_years"][
            "versions"][2]["value"] = [2011, 2021]
        errors = self._errors(monkeypatch, old, new)
        assert len(errors) == 1 and "2022-08-01" in errors[0].problem \
            and errors[0].scope == "list_settings/census_years (collection c1)", errors

    def test_the_unchanged_configuration_passes(self, monkeypatch):
        old = _doc(coll_list=FOUR)
        assert self._errors(monkeypatch, old, copy.deepcopy(old)) == []

    def test_the_committed_census_years(self):
        from qa_tools.common.amber_setting import _doc as committed

        doc = committed()
        assert amber_setting.list_setting_keys(doc) == [PATH]
        r = amber_setting.timeline("geo-cp-clients", doc=doc, key=PATH)
        assert [(e["from"], e["value"]) for e in r] == [
            ("2013-01-01", (2011,)), ("2017-08-01", (2011, 2016)),
            ("2022-08-01", (2011, 2016, 2021)), ("2027-08-01", (2011, 2016, 2021, 2026))]
        assert r[2]["text"] == "2011, 2016 and 2021 (set for Linkage Products, since 1 Aug 2022)"


class TestCriterionTenEachVersionLandsInItsQuarter:
    """Read through contract/calendar.yaml and the one resolution, so a
    corrected round date moving a quarter across a version's start fails
    here rather than silently re-judging the quarter."""

    @pytest.mark.parametrize("period,round_date,years", [
        ("2017-Q2", date(2017, 5, 1), (2011,)),
        ("2017-Q3", date(2017, 8, 1), (2011, 2016)),
        ("2022-Q2", date(2022, 5, 1), (2011, 2016)),
        ("2022-Q3", date(2022, 8, 1), (2011, 2016, 2021)),
        ("2027-Q2", date(2027, 5, 1), (2011, 2016, 2021)),
        ("2027-Q3", date(2027, 8, 1), (2011, 2016, 2021, 2026)),
    ])
    @pytest.mark.parametrize("dataset", ["geo-cp-clients", "geo-ed-presentations"])
    def test_landing(self, dataset, period, round_date, years):
        from qa_tools.common import schedule

        dp = next(p for p in schedule.periods_for_dataset(dataset) if p.name == period)
        assert dp.round_date == round_date
        assert amber_setting.resolve_on_date(dataset, dp.round_date, key=PATH).value == years
