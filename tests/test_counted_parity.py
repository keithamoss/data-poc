"""Which datasets COUNT, held to one table by every Python status implementation
(REQ-PIPE-438's CORRECTNESS NFR; REQ-DASH-436 criterion 4).

status-cases.json's `counted_cases` is read here and by
tests-js/counted-parity.test.js, which holds the page's inNoRollup, rollup,
unagreedMarker and column status to the same rows. Neither suite owns the
table - the item-74 lesson: a correct data layer and a page whose own
transform disagreed rendered a check with 14 real violations green.

Driven through the real implementations: what a result is RECORDED as
(sample_data.supply_state / state_for_participants, the writer's own calls),
where a cross-table result is SHOWN (build_dashboard_data.
share_cross_table_results), and what a dataset's status and its group's
rollup are (dataset_status.py), against a fixture asset declaring each kind -
the real daily asset with its datasets replaced, as tests/test_no_calendar.py
does. The calendar loader reads `never` and `derived` on it; only the schedule
gate refuses them there (criterion 8).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import agreement_split
from qa_tools.common import dataset_status, qa_store, sample_data

CASES = json.loads((Path(__file__).resolve().parent.parent / "status-cases.json").read_text())
COUNTED = CASES["counted_cases"]
BY_ID = {d["id"]: d for d in COUNTED["datasets"]}


def _table(dataset_id: str) -> str:
    return dataset_id.replace("-", "_")


@pytest.fixture
def asset(tmp_path, monkeypatch):
    doc = agreement_split.merged_view(agreement_split.REAL_CONTRACT_DIR)
    agency = doc["hierarchy"]["agencies"][0]
    agency["collections"] = [{
        "id": "civil-registration", "name": "Civil Registration", "short": "bdm",
        "run_prefix": "run_",
        "contract": "registry-services/bdm-birth-registrations-contract.yaml",
        "delivery_boundary": "directory",
        "datasets": [{"id": d["id"], "name": d["id"], "table": _table(d["id"]),
                      "arrival_pattern": rf"{_table(d['id'])}\.csv", **d["declares"]}
                     for d in COUNTED["datasets"]]}]
    doc["hierarchy"]["agencies"] = [agency]
    agreement_split.repoint(monkeypatch, tmp_path, doc)


def _page(dataset_id: str, status: str) -> dict:
    """The dataset as the build hands it to the page."""
    page = {"id": dataset_id, **BY_ID[dataset_id]["page"]}
    if status == "notyetchecked":
        return {**page, "notYetChecked": True, "columns": []}
    return {**page, "columns": [{"name": "a", "status": status}]}


def test_the_table_is_not_empty():
    assert COUNTED["datasets"] and COUNTED["cross_table"] and COUNTED["rollups"]


@pytest.mark.parametrize("case", COUNTED["datasets"], ids=lambda c: c["id"])
class TestEachDeclaration:
    def test_its_results_are_recorded_as_the_table_says(self, case, asset):
        expect = qa_store.AGREED if case["counted"] else qa_store.IN_DEVELOPMENT
        assert sample_data.supply_state(case["id"]) == expect

    def test_its_routing_is_the_no_period_schema_for_either_no_calendar_value(self, case, asset):
        """The ROUTING question stays is_sample (REQ-PIPE-438's MAINTAINABILITY
        NFR): both no_calendar values, derived or not."""
        assert sample_data.is_sample(case["id"]) is ("no_calendar" in case["declares"])

    def test_the_rollup_leaves_it_out_as_the_table_says(self, case, asset):
        assert dataset_status.in_no_rollup(_page(case["id"], "red")) is (not case["counted"])


@pytest.mark.parametrize("case", COUNTED["cross_table"], ids=lambda c: c["id"])
class TestEachCrossTableCheck:
    def test_it_is_recorded_as_the_table_says(self, case, asset):
        assert sample_data.state_for_participants(case["participants"]) == case["state"]

    def test_it_is_shown_where_the_table_says(self, case, asset):
        from pipeline import build_dashboard_data as build

        tables = {_table(d) for d in case["participants"]}
        record = {"check_id": "spans", "dataset_id": case["participants"][0],
                  "reads": {t: {"state": "READ", "supply_id": f"{t}@1", "contested": False}
                            for t in tables}}
        if case["state"] == qa_store.IN_DEVELOPMENT:
            record["supply_state"] = qa_store.IN_DEVELOPMENT
        by_table = {t: [] for t in tables}
        build.share_cross_table_results([record], by_table)
        shown = {t for t, got in by_table.items() if got}
        assert shown == {_table(d) for d in case["shown_on"]}

    def test_it_counts_only_where_the_table_says(self, case, asset):
        """On a page where it is not counted the build marks the card
        notCountedHere, and the dataset's status leaves it out."""
        for dataset_id in case["shown_on"]:
            marked = dataset_id in case["not_counted_on"]
            page = {"columns": [{"name": "(cross-table)", "checks": [
                {"current": 0, "warn": 0, "fail": 0, "current_status": "green"},
                {"current": 9, "warn": 0, "fail": 0, "current_status": "red",
                 **({"notCountedHere": True} if marked else {})}]}]}
            assert dataset_status.dataset_status(page) == ("green" if marked else "red")


@pytest.mark.parametrize("case", COUNTED["rollups"], ids=lambda c: c["id"])
def test_each_rollup(case):
    assert dataset_status.rollup_datasets(
        [_page(d, s) for d, s in case["datasets"]]) == case["expect"]


def test_not_yet_checked_is_a_dataset_s_own_status():
    """REQ-DASH-436 criterion 4: distinct from the check-level notchecked."""
    assert dataset_status.dataset_status({"notYetChecked": True, "columns": []}) == "notyetchecked"
    assert "notyetchecked" in dataset_status.DATASET_STATUSES
    assert "notyetchecked" not in dataset_status.CHECK_STATUSES


#: The daily asset's configuration is the fixture's base.
pytestmark = pytest.mark.asset("daily")


@pytest.mark.parametrize("case", COUNTED["package_checks"], ids=lambda c: c["id"])
def test_a_one_offs_package_checks_count(case):
    """REQ-DASH-436 criterion 2 (REQ-DASH-097 criterion 2 AMENDED 2026-11-22,
    Keith): a one-off's two package checks, marked countsInStatus by the
    build, count in its dataset's status; no other file check does."""
    def file_check(status, counts):
        return {"current_status": status, **({"countsInStatus": True} if counts else {})}
    page = {"columns": [{"name": "a", "checks": [
                {"current": 9 if s == "red" else 0, "warn": 0, "fail": 0, "current_status": s}]}
                        for s in case["columns"]],
            "fileChecks": {"checks": [file_check(s, True) for s in case["package"]]
                           + [file_check(s, False) for s in case.get("unmarked", [])]}}
    assert dataset_status.dataset_status(page) == case["expect"]
