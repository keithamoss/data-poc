"""A declared correction can be reverted from the configuration it is in
(REQ-PIPE-170): the agreement as it stood before the correction is the
current one with each declared change put back to its `old` value. No git
history is needed - a shallow clone and the synthetic generator both lack it.

Each case changes a copy of the real configuration, computes the changes
the gate sees, reverts them, and checks the flattened items match the
original exactly.
"""
from __future__ import annotations

import copy

import pytest
import yaml

from qa_tools.common import agreement, agreement_freeze, asset_time


def _docs():
    cal = copy.deepcopy(yaml.safe_load(agreement.CALENDAR_YAML.read_text()))
    asset = copy.deepcopy(yaml.safe_load(asset_time.DATA_ASSET_YAML.read_text()))
    return cal, asset


def _entry(cal, ds):
    entry = next(d for d in cal["datasets"] if d["id"] == ds)
    entry["participation"]["versions"] = copy.deepcopy(entry["participation"]["versions"])
    return entry


def _quarterly(cal):
    return next(c for c in cal["calendars"] if c["name"] == "quarterly")


def _move_date(cal, asset):
    for d in _quarterly(cal)["versions"][-1]["dates"]:
        if d["period"] == "2023-Q3":
            d["date"] = "2023-08-20"


def _remove_date(cal, asset):
    dates = _quarterly(cal)["versions"][-1]["dates"]
    dates[:] = [d for d in dates if d["period"] != "2023-Q3"]


def _add_date(cal, asset):
    _quarterly(cal)["versions"][-1]["dates"].append({"period": "2099-Q1", "date": "2099-02-01"})


def _grace(cal, asset):
    _entry(cal, "cp-clients")["participation"]["versions"][0]["grace"] = "1h"


def _months(cal, asset):
    _entry(cal, "cp-case-workers")["participation"]["versions"][0]["participates"] = [
        "February", "May", "August"]


def _not_expected_added(cal, asset):
    _entry(cal, "cp-clients")["not_expected"] = [{"period": "2023-Q3", "reason": "agreed"}]


def _calendar_version_setting(cal, asset):
    _quarterly(cal)["versions"][-1]["claim_window"] = "1d"


def _timezone(cal, asset):
    asset["timezone"]["versions"][0]["zone"] = "Australia/Sydney"


def _membership(cal, asset):
    _entry(cal, "cp-clients")["calendar"] = "daily"


def _several(cal, asset):
    _move_date(cal, asset)
    _grace(cal, asset)
    _timezone(cal, asset)


@pytest.mark.parametrize("change", [
    _move_date, _remove_date, _add_date, _grace, _months, _not_expected_added,
    _calendar_version_setting, _timezone, _membership, _several])
def test_reverting_the_changes_gives_back_the_original(change):
    base_cal, base_asset = _docs()
    work_cal, work_asset = copy.deepcopy(base_cal), copy.deepcopy(base_asset)
    change(work_cal, work_asset)
    changes = [(key, old, new) for key, (_i, old, new, _f) in agreement_freeze.changed(
        base_cal, work_cal, base_asset, work_asset).items()]
    assert changes, "the change is one the gate sees"
    got_cal, got_asset = agreement_freeze.revert(work_cal, work_asset, changes)
    assert {k: i.norm for k, i in agreement_freeze.flatten(got_cal, got_asset).items()} == \
        {k: i.norm for k, i in agreement_freeze.flatten(base_cal, base_asset).items()}


def test_it_leaves_the_documents_it_was_given_alone():
    base_cal, base_asset = _docs()
    work_cal, work_asset = copy.deepcopy(base_cal), copy.deepcopy(base_asset)
    _move_date(work_cal, work_asset)
    before = copy.deepcopy(work_cal)
    changes = [(k, o, n) for k, (_i, o, n, _f) in agreement_freeze.changed(
        base_cal, work_cal, base_asset, work_asset).items()]
    agreement_freeze.revert(work_cal, work_asset, changes)
    assert work_cal == before


def test_an_item_it_does_not_know_is_refused():
    cal, asset = _docs()
    with pytest.raises(ValueError, match="cannot be reverted"):
        agreement_freeze.revert(cal, asset, [("calendar quarterly sideways 1", 1, 2)])
