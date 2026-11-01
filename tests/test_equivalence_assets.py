"""REQ-TEST-357 criterion 2: a commit with asset folders is captured as one
baseline per asset, and compare reads the union of a post-split commit's
baselines against a pre-split commit's single one, collection by collection,
normalising only REQ-QAC-344's data_asset_id segment and the database identity
row. Driven on hand-built baselines and trees - a real capture is two full
bootstraps (the end-of-run bootstrap's job)."""
from __future__ import annotations

import pytest

from qa_tools.common import equivalence as eq


def _base(assets, surfaces):
    return {"harness": eq.HARNESS_VERSION, "normaliser": eq.NORMALISER_VERSION,
            "pinned_now": eq.PINNED_NOW, "label": "x", "assets": assets, "surfaces": surfaces}


def _s1(*rows, identity=None):
    out = {"qa.result": {"columns": ["check_id", "status"], "rows": [[list(r), 1] for r in rows]}}
    if identity:
        out[eq.IDENTITY_TABLE] = {"columns": ["asset"], "rows": [[[identity], 1]]}
    return out


BEFORE = _base(["data-asset-1"], {
    "S1": _s1(("data-asset-1.registry-services.civil-registration.br.c.unique_dbt", "pass"),
              ("data-asset-1.department-of-health.emergency-department.ed.c.unique_dbt", "fail"),
              identity="data-asset-1"),
    "S4": {"data/deliveries/a/f.csv": "h1", "data/deliveries/b/g.csv": "h2"},
    "S5": {"results_rs_civil-registration.json": {"n": 1},
           "results_doh_emergency-department.json": {"n": 2}}})


def _after(ed_status="fail"):
    per_asset = {
        "daily": {"S1": _s1(("daily.registry-services.civil-registration.br.c.unique_dbt", "pass"),
                            identity="daily"),
                  "S4": {"data/deliveries/a/f.csv": "h1"},
                  "S5": {"results_rs_civil-registration.json": {"n": 1}}},
        "quarterly": {"S1": _s1(("quarterly.department-of-health.emergency-department.ed.c.unique_dbt",
                                 ed_status), identity="quarterly"),
                      "S4": {"data/deliveries/b/g.csv": "h2"},
                      "S5": {"results_doh_emergency-department.json": {"n": 2}}},
    }
    b = _base(["daily", "quarterly"], eq.union(per_asset))
    b["per_asset"] = per_asset
    return b


class TestTheTreesAssets:
    def test_a_split_tree_is_one_asset_per_folder(self, tmp_path):
        for a in ("quarterly", "daily"):
            (tmp_path / "assets" / a).mkdir(parents=True)
            (tmp_path / "assets" / a / "data-asset.yaml").write_text(f"data_asset_id: {a}\n")
        (tmp_path / "assets" / "environments.yaml").write_text("environments: []\n")
        assert eq.tree_assets(tmp_path) == ["daily", "quarterly"]
        assert eq._tree_state(tmp_path, "daily", "data") == tmp_path / "data" / "daily"

    def test_a_tree_from_before_the_split_is_its_one_asset(self, tmp_path):
        (tmp_path / "contract").mkdir()
        (tmp_path / "contract" / "data-asset.yaml").write_text("data_asset_id: data-asset-1\n")
        assert eq.tree_assets(tmp_path) == ["data-asset-1"]
        assert eq._tree_state(tmp_path, "data-asset-1", "data") == tmp_path / "data"

    @pytest.mark.asset("daily")
    def test_files_are_named_under_data_whatever_the_layout(self, tmp_path):
        (tmp_path / "assets" / "daily").mkdir(parents=True)
        (tmp_path / "assets" / "daily" / "data-asset.yaml").write_text("data_asset_id: daily\n")
        (tmp_path / "data" / "daily" / "deliveries" / "a").mkdir(parents=True)
        (tmp_path / "data" / "daily" / "deliveries" / "a" / "f.csv").write_text("x\n")
        assert list(eq.generated_files(tmp_path, "daily")) == ["data/deliveries/a/f.csv"]


class TestTheUnion:
    def test_rows_add_and_distinct_keys_are_kept(self):
        u = _after()["surfaces"]
        assert len(u["S1"]["qa.result"]["rows"]) == 2
        assert set(u["S4"]) == {"data/deliveries/a/f.csv", "data/deliveries/b/g.csv"}

    def test_a_key_both_assets_hold_is_kept_once_per_asset(self):
        u = eq.union({"daily": {"S4": {"data/generator_bookkeeping.json": "d"}},
                      "quarterly": {"S4": {"data/generator_bookkeeping.json": "q"}}})
        assert u["S4"] == {"daily | data/generator_bookkeeping.json": "d",
                           "quarterly | data/generator_bookkeeping.json": "q"}


class TestComparingAcrossTheSplit:
    def test_a_pure_rename_and_the_identity_row_report_no_difference(self):
        assert eq.compare(BEFORE, _after(), ["S1", "S4", "S5"]) == {"S1": [], "S4": [], "S5": []}

    def test_any_other_change_is_still_a_difference(self):
        found = eq.compare(BEFORE, _after(ed_status="pass"), ["S1"])
        assert found["S1"] and "qa.result" in found["S1"][0]

    def test_a_shared_file_split_between_assets_is_shown_not_hidden(self):
        a = _base(["data-asset-1"], {"S4": {"data/generator_bookkeeping.json": "one"}})
        b = _base(["daily", "quarterly"], eq.union({
            "daily": {"S4": {"data/generator_bookkeeping.json": "d"}},
            "quarterly": {"S4": {"data/generator_bookkeeping.json": "q"}}}))
        assert eq.compare(a, b, ["S4"])["S4"]

    def test_within_one_layout_nothing_is_normalised(self):
        assert eq.compare(BEFORE, BEFORE, ["S1"]) == {"S1": []}
        renamed = _base(["data-asset-1"], {"S1": _s1(("quarterly.x.y.z.c.unique_dbt", "pass"))})
        plain = _base(["data-asset-1"], {"S1": _s1(("data-asset-1.x.y.z.c.unique_dbt", "pass"))})
        assert eq.compare(plain, renamed, ["S1"])["S1"]


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
