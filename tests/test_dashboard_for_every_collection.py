"""REQ-DASH-244: the dashboard is built for every collection by one builder.

What is tested here is what the two per-collection builders could never
show: a THIRD collection, registered only in the hierarchy with a contract
and a presentation entry, is built, embedded and linked with no code of its
own (criteria 1, 6, 9 and 17); one with no recorded runs is built with an
empty history (criterion 6); one with no file refuses the embed, writing no
page (criterion 7); and one with no presentation entry fails the gate before
any build (criterion 8). Today's two collections keep their tests in
test_build_dashboard_data.py and test_build_dashboard_child_protection.py,
and their output is proved unchanged by the equivalence capture.
"""
from __future__ import annotations

import json

import pytest
import yaml

from pipeline import build_dashboard_data as bdd
from qa_tools import collections
from qa_tools.common import hierarchy, presentation
from third_collection import FAKE_DATASET, FAKE_ID, FAKE_TABLE

FAKE_AGENCY = "fake-agency"


@pytest.fixture
def described(third_collection, tmp_path, monkeypatch, supply_dsn):
    """The third collection with what a real one carries: its table in its
    contract, a presentation entry, and no recorded runs."""
    contract = hierarchy.DATA_ASSET_YAML.parent / collections.by_id(FAKE_ID).contract
    doc = yaml.safe_load(contract.read_text())
    doc["schema"] = [{
        "name": FAKE_TABLE, "physicalType": "table", "description": "One row per fake thing.",
        "customProperties": [{"property": "tableLevelChecksNote", "value": "No rule yet."}],
        "properties": [
            {"name": "fake_id", "logicalType": "string", "physicalType": "varchar(20)",
             "description": "Primary key."},
            {"name": "made_on", "logicalType": "date", "physicalType": "date",
             "description": "Required."},
        ]}]
    contract.write_text(yaml.safe_dump(doc, sort_keys=False))
    shown = yaml.safe_load(open(bdd.ROOT + "/contract/presentation.yaml"))
    shown["collections"][FAKE_ID] = {"provider": "The Fake Agency", "delivery_format": "CSV",
                                     "provenance": "Built from fakes. ({table_description})"}
    shown["agencies"][FAKE_AGENCY] = {"blurb": "Makes fake things."}
    (hierarchy.DATA_ASSET_YAML.parent / "presentation.yaml").write_text(yaml.safe_dump(shown))
    # ITS PLACE IN THE DELIVERY CALENDAR, as any real collection has: on the
    # quarterly calendar, owing what a Child Protection dataset owes.
    from qa_tools.common import agreement

    cal = yaml.safe_load(agreement.CALENDAR_YAML.read_text())
    cp = next(c for c in cal["collections"] if c["id"] == "child-protection")
    # REPLACED, not appended: the third_collection fixture already puts it on
    # the quarterly calendar (REQ-PIPE-262's streams need one).
    cal["collections"] = [c for c in cal["collections"] if c["id"] != FAKE_ID]
    cal["collections"].append({**cp, "id": FAKE_ID})
    clients = next(d for d in cal["datasets"] if d["id"] == "cp-clients")
    cal["datasets"].append({**clients, "id": FAKE_DATASET})
    calendar = tmp_path / "calendar.yaml"
    calendar.write_text(yaml.safe_dump(cal, sort_keys=False))
    monkeypatch.setattr(agreement, "CALENDAR_YAML", calendar)
    # AN EMPTY RESULTS FILE, as the real rebuild writes for a collection with
    # no recorded runs - a MISSING file is refused (Keith, 2026-10-18; see
    # TestAMissingResultsFileIsRefused below), not read as no runs.
    results = tmp_path / f"results-{FAKE_ID}.json"
    results.write_text(json.dumps({"runs": [], "results": [], "dataset_stats": {}}))
    monkeypatch.setattr(bdd, "results_path", lambda cid: str(results))
    # The recorded history the build reads, empty for the fake collection.
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="test-dashboard-third-collection") as conn:
        qa_store.ensure_schema(conn)
    return third_collection


class TestAThirdCollectionIsBuilt:
    """Criteria 1 and 6: from its contract and presentation entry alone."""

    def test_its_columns_come_from_its_contract(self, described):
        (ds,) = bdd.build_datasets(FAKE_ID)
        by_name = {c["name"]: c for c in ds["columns"]}
        assert by_name["fake_id"]["logicalType"] == "string · varchar(20)"
        assert by_name["fake_id"]["description"] == "Primary key."
        assert by_name["made_on"]["logicalType"] == "date"
        assert by_name[bdd.TABLE_LEVEL_PSEUDO_COLUMN]["description"] == "No rule yet."

    def test_with_no_recorded_runs_it_has_an_empty_history(self, described):
        (ds,) = bdd.build_datasets(FAKE_ID)
        assert ds["id"] == FAKE_DATASET and ds["provider"] == "The Fake Agency"
        assert ds["runs"] == [] and ds["arrivalHistory"] == [] and ds["lastArrival"] is None
        assert ds["_provenance"] == "Built from fakes. (One row per fake thing.)"
        # Every column shown says no rule is defined - never a crash.
        assert {c["checks"][0]["key"] for c in ds["columns"]} == {"no_rule_defined"}

    def test_a_one_table_collection_shows_table_level_but_no_cross_table_section(
            self, described):
        """REQ-QAC-247 (Keith, 2026-10-18): a missing rule is visible, so an
        empty Table-level section shows its grey card - but a collection with
        one table has no cross-table gap to report, so that section is left
        out rather than shown empty."""
        (ds,) = bdd.build_datasets(FAKE_ID)
        names = [c["name"] for c in ds["columns"]]
        assert bdd.TABLE_LEVEL_PSEUDO_COLUMN in names
        assert bdd.CROSS_TABLE_PSEUDO_COLUMN not in names

    def test_it_is_written_in_the_shape_every_collection_now_has(self, described, tmp_path,
                                                               monkeypatch):
        monkeypatch.setattr(bdd, "out_path", lambda cid: str(tmp_path / f"{cid}.json"))
        doc = json.loads(open(bdd.write(FAKE_ID)).read())
        assert [d["id"] for d in doc["datasets"]] == [FAKE_DATASET]


class TestAMissingResultsFileIsRefused:
    """Keith, 2026-10-18 (post-build-review #233, from the REQ-DASH-244
    critic's G1): a collection whose results file is missing is refused,
    naming it and the command that writes the file. It used to be read as
    'no recorded runs', so `build-data` run before `rebuild-results` published
    a collection with real history as never supplied, without a word."""

    def test_the_build_names_the_collection_and_the_command(self, described, tmp_path,
                                                            monkeypatch):
        monkeypatch.setattr(bdd, "results_path", lambda cid: str(tmp_path / "absent.json"))
        with pytest.raises(bdd.MissingResultsFile) as raised:
            bdd.build_datasets(FAKE_ID)
        said = str(raised.value)
        assert FAKE_ID in said and "mothman dashboard rebuild-results" in said


class TestTheEmbed:
    """Criteria 4, 7 and 9 on the embed step."""

    def test_every_collection_is_embedded_in_hierarchy_order(self, described, tmp_path,
                                                           monkeypatch):
        from dashboard import embed_dashboard_data as edd

        monkeypatch.setattr(bdd, "out_path", lambda cid: str(tmp_path / f"{cid}.json"))
        for coll in collections.all_collections():
            (tmp_path / f"{coll.id}.json").write_text(
                json.dumps({"datasets": [{"id": coll.id}]}))
        data = edd.collection_data()
        assert list(data) == [c.id for c in collections.all_collections()]
        assert list(data)[-1] == FAKE_ID

    def test_a_collection_with_no_file_refuses_and_writes_no_page(self, described, tmp_path,
                                                                monkeypatch):
        from dashboard import embed_dashboard_data as edd

        page = tmp_path / "page.html"
        monkeypatch.setattr(edd, "DASHBOARD_HTML", str(page))
        monkeypatch.setattr(bdd, "out_path", lambda cid: str(tmp_path / f"{cid}.json"))
        with pytest.raises(edd.MissingCollectionData) as refused:
            edd.embed()
        said = str(refused.value)
        assert "civil-registration" in said and "mothman dashboard build-data" in said
        assert "civil-registration.json" in said and "No page was written" in said
        assert not page.exists()


class TestTheGateRefusesACollectionTheBuilderCannotDescribe:
    """Criterion 8, before any build."""

    def test_no_presentation_entry_is_named(self, third_collection):
        found = presentation.problems()
        assert any(FAKE_ID in p and "presentation.yaml" in p for p in found), found

    def test_one_with_its_entry_passes(self, described):
        assert presentation.problems() == []


class TestAThirdCollectionIsLinked:
    """Criteria 12, 13 and 17 for qa_tools/common/github_links.py."""

    def test_its_dataset_and_agency_get_links_from_the_registry(self, described):
        from qa_tools.common import github_links

        links = github_links.build_folder_links(sha="abc123", root=hierarchy.DATA_ASSET_YAML.parent.parent)
        assert links["agencies"][FAKE_AGENCY].endswith(f"/tree/abc123/contract/{FAKE_AGENCY}")
        assert links["datasets"][FAKE_DATASET].startswith(
            f"https://github.com/keithamoss/data-poc/blob/abc123/contract/{FAKE_AGENCY}/")
        assert "#L" in links["datasets"][FAKE_DATASET]

    def test_its_agency_blurb_comes_from_presentation(self, described):
        assert presentation.agency_blurbs()[FAKE_AGENCY] == "Makes fake things."
