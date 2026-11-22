"""The dashboard builds and reads correctly for a dataset with no calendar
(REQ-DASH-436 criteria 1 and 2).

THE DEFECT (plans/running-thoughts.md #141): the build's agreement.cadence()
raised NoCalendarAgreed, so no page could be built for an asset holding such
a dataset. Driven through the real one builder, build_dashboard_data.
build_datasets, over a third collection whose one dataset declares
`no_calendar` (tests/third_collection.py), with an empty recorded history.
"""
from __future__ import annotations

import json

import pytest
import yaml

from pipeline import build_dashboard_data as bdd
from asset_model import collections, hierarchy
from third_collection import FAKE_DATASET, FAKE_ID, FAKE_TABLE


@pytest.fixture(params=["not-yet-agreed", "never"])
def no_calendar(request, third_collection, tmp_path, monkeypatch, supply_dsn):
    import asset_folders
    from asset_model import agreement
    from qa_tools.common import qa_store, supply_db

    contract = hierarchy.data_asset_yaml().parent / collections.by_id(FAKE_ID).contract
    doc = yaml.safe_load(contract.read_text())
    doc["schema"] = [{"name": FAKE_TABLE, "physicalType": "table", "description": "Fakes.",
                      "properties": [{"name": "fake_id", "logicalType": "string",
                                      "description": "Primary key."}]}]
    contract.write_text(yaml.safe_dump(doc, sort_keys=False))
    shown = yaml.safe_load((asset_folders.real_folder() / "presentation.yaml").read_text())
    shown["collections"][FAKE_ID] = {"provider": "The Fake Agency", "delivery_format": "CSV",
                                     "provenance": "Built from fakes."}
    shown["agencies"]["fake-agency"] = {"blurb": "Makes fake things."}
    (hierarchy.data_asset_yaml().parent / "presentation.yaml").write_text(yaml.safe_dump(shown))
    cal = yaml.safe_load(agreement.calendar_yaml().read_text())
    cal["datasets"] = [d for d in cal["datasets"] if d["id"] != FAKE_DATASET]
    cal["datasets"].append({"id": FAKE_DATASET, "no_calendar": request.param})
    asset_folders.replace("calendar.yaml", yaml.safe_dump(cal, sort_keys=False))
    results = tmp_path / f"results-{FAKE_ID}.json"
    results.write_text(json.dumps({"runs": [], "run_facts": {}, "results": [],
                                   "dataset_stats": {}}))
    monkeypatch.setattr(bdd, "results_path", lambda cid: str(results))
    with supply_db.connect(label="test-no-calendar-dashboard") as conn:
        qa_store.ensure_schema(conn)
    return request.param


class TestTheBuildBuildsIt:
    """Criterion 1: no NoCalendarAgreed out of agreement.cadence() or any other
    cadence read."""

    def test_its_page_is_built(self, no_calendar):
        (ds,) = bdd.build_datasets(FAKE_ID)
        assert ds["id"] == FAKE_DATASET
        assert ds["scheduleNotAgreed"] == no_calendar


class TestNoScheduleIsShownForIt:
    """Criterion 2: no period, slot, due date or lateness."""

    def test_it_carries_no_schedule(self, no_calendar):
        (ds,) = bdd.build_datasets(FAKE_ID)
        assert ds["periodSlots"] is None
        assert ds["sla"].get("cadence") is None
        assert not ds["owedNothing"]
        assert not ds["slotTimeline"]


class TestThePageIsEmbedded:
    """Criterion 1 at the embed: the page's schedule reads (the as-of
    calendar, the period list) skip the dataset rather than raise."""

    def test_the_embed_writes_a_page(self, no_calendar, tmp_path, monkeypatch):
        from dashboard import embed_dashboard_data as edd

        page = tmp_path / "page.html"
        monkeypatch.setattr(edd, "DASHBOARD_HTML", str(page))
        monkeypatch.setattr(bdd, "out_path", lambda cid: str(tmp_path / f"{cid}.json"))
        for coll in collections.all_collections():
            if coll.id != FAKE_ID:
                (tmp_path / f"{coll.id}.json").write_text(json.dumps({"datasets": []}))
        bdd.write(FAKE_ID)
        edd.embed()
        assert FAKE_DATASET in page.read_text()


#: The third collection is the quarterly asset's.
pytestmark = pytest.mark.asset("quarterly")
