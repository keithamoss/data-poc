"""REQ-DASH-299 on the page-build path: what the dashboard build carries for
the geocoding pages, from recorded results and configuration only (NFR 5).

- a set-member result's recorded version of its list setting rides on its
  history entry with the setting's display name (criterion 9);
- a dataset linking one source with no code carries that source and its word
  for the relation (criterion 10);
- a left-out check carries the tables it is between, from its declared reads,
  so its row sits in its collection's group (A1);
- every list setting and every such dataset has its tile's word, or
  `mothman check`'s collections gate says which does not (NFR 2).

Configuration only, so it sits in CI's fast half."""
from __future__ import annotations

import shutil

import yaml

from pipeline import build_dashboard_data as bdd
from qa_tools.common import hierarchy, presentation


def _geo():
    return hierarchy.dataset("geo-cp-clients")


class TestTheRecordedSetRidesOnTheResult:
    def test_a_year_checks_recorded_version_is_carried_with_its_display_name(self):
        got = bdd._member_set({"member_setting": "census_years", "member_set_version": "2017-08-01",
                               "member_set": [2011, 2016], "member_set_added": [2016]})
        assert got == {"setting": "census_years", "label": "Census years", "version": "2017-08-01",
                       "members": [2011, 2016], "added": [2016]}

    def test_the_first_version_adds_nothing(self):
        got = bdd._member_set({"member_setting": "census_years", "member_set_version": "2013-01-01",
                               "member_set": [2011], "member_set_added": []})
        assert got["added"] == [] and got["members"] == [2011]

    def test_a_result_recording_no_set_carries_none(self):
        assert bdd._member_set({"check_id": "x", "status": "pass"}) is None
        assert bdd._member_set({"member_setting": "census_years"}) is None


class TestTheLinkedSource:
    def test_a_geocoding_dataset_names_its_source_and_its_word(self):
        assert presentation.linked_source(_geo()) == {"datasetId": "cp-clients", "relation": "Geocodes"}

    def test_a_dataset_linking_several_sources_by_code_has_none(self):
        keys = hierarchy.dataset("linkage-keys")
        assert len(keys.linked) >= 2, "precondition: Linkage Keys links several sources by code"
        assert presentation.linked_source(keys) is None

    def test_a_dataset_linking_nothing_has_none(self):
        ds = hierarchy.dataset("cp-clients")
        assert not ds.linked
        assert presentation.linked_source(ds) is None


class TestALeftOutCheckKnowsItsTables:
    def test_its_declared_reads_name_the_other_collections_dataset(self):
        from qa_tools.common import validate_check_lifecycle

        by_id = {c.check_id: c for c in validate_check_lifecycle.collect_checks(None)}
        reading = [c for c in by_id.values() if "cp_clients" in (c.reads_tables or ())
                   and c.check_id.split(".")[2] == "linkage-products"]
        assert reading, "precondition: a Linkage Products check declares it reads cp_clients"
        got = bdd._left_out_between(reading[0].check_id, by_id)
        assert "cp-clients" in got["between"]["reads"]

    def test_a_check_with_no_declared_reads_carries_nothing(self):
        assert bdd._left_out_between("no.such.check.at.all.x", {}) == {}


class TestEveryTileHasItsWord:
    def _copy(self, tmp_path, edit):
        path = tmp_path / "presentation.yaml"
        shutil.copy(hierarchy.data_asset_yaml().parent / "presentation.yaml", path)
        doc = yaml.safe_load(path.read_text())
        edit(doc)
        path.write_text(yaml.safe_dump(doc))
        return path

    def test_the_real_configuration_names_every_tile(self):
        assert presentation.problems() == []

    def test_a_list_setting_with_no_label_is_named(self, tmp_path):
        path = self._copy(tmp_path, lambda d: d.pop("list_settings"))
        found = presentation.problems(path)
        assert any("census_years" in p and "label" in p for p in found), found

    def test_a_codeless_linked_dataset_with_no_word_is_named(self, tmp_path):
        path = self._copy(tmp_path, lambda d: d["datasets"].pop("geo-ed-presentations"))
        found = presentation.problems(path)
        assert any("geo-ed-presentations" in p and "relation" in p for p in found), found
        assert not any("geo-cp-clients" in p for p in found), found


class TestTheYearChecksKeepTheirDeclaredOrder:
    """REQ-DASH-299 criterion 1: missing, duplicated, unexpected - however
    the results arrive. dbt with one thread breaks ties by unique_id, which
    is alphabetical (duplicated, missing, unexpected), and the build keeps
    arrival order; equals are sorted by the kinds' declared order, data in
    pipeline/dashboard_check_labels.py, never by a dataset's name."""

    def _card(self, kind, status="green"):
        return {"check_id": f"a.b.c.geo-cp-clients.census_year.{kind}_dbt",
                "tool_ref": f"dbt:{kind}", "current": 0, "warn": None, "fail": 0,
                "current_status": status}

    def test_alphabetical_arrival_is_shown_missing_duplicated_unexpected(self):
        from pipeline.dashboard_check_labels import rank_for_headline

        cards = [self._card(k) for k in ("duplicated_set_members", "missing_set_members",
                                          "unexpected_set_members")]
        rank_for_headline(cards)
        assert [c["tool_ref"] for c in cards] == [
            "dbt:missing_set_members", "dbt:duplicated_set_members", "dbt:unexpected_set_members"]

    def test_a_worse_status_still_comes_first(self):
        from pipeline.dashboard_check_labels import rank_for_headline

        cards = [self._card("duplicated_set_members"), self._card("missing_set_members"),
                 self._card("unexpected_set_members", "red")]
        rank_for_headline(cards)
        assert [c["tool_ref"] for c in cards] == [
            "dbt:unexpected_set_members", "dbt:missing_set_members", "dbt:duplicated_set_members"]

    def test_checks_of_no_declared_family_keep_their_arrival_order(self):
        from pipeline.dashboard_check_labels import rank_for_headline

        cards = [{"check_id": f"a.b.c.d.col.{k}", "tool_ref": f"dbt:{k}", "current": 0,
                  "warn": None, "fail": 0, "current_status": "green"}
                 for k in ("unique", "not_null", "accepted_values")]
        rank_for_headline(cards)
        assert [c["tool_ref"] for c in cards] == ["dbt:unique", "dbt:not_null", "dbt:accepted_values"]
