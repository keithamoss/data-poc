"""An asset's synthetic-era setting versions live in synthetic/eras.yaml and
merge with data-asset.yaml into one timeline (REQ-GEN-371).

The golden timelines (tests/fixtures/settings_timelines_<asset>.json) were
captured from both assets' data-asset.yaml BEFORE the move, at the fixed test
anchor: every dataset's resolved amber and replacement settings on every date
a version starts. The move must leave them exactly as they were (criterion 4).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import asset_folders
from asset_model import amber_setting, config_yaml, eras

FIXTURES = Path(__file__).parent / "fixtures"
ASSETS = [pytest.param(a, marks=pytest.mark.asset(a), id=a) for a in ("daily", "quarterly")]


def _raw():
    return config_yaml.load(asset_folders.real_folder() / "data-asset.yaml") or {}


def _eras():
    path = asset_folders.real_folder() / "synthetic" / "eras.yaml"
    assert path.exists(), "the asset keeps its synthetic eras in synthetic/eras.yaml"
    return config_yaml.load(path) or {}


def _every_version(doc):
    for key in eras.KEYS:
        for v in ((doc.get(key) or {}).get("versions") or []):
            yield "data asset", key, v
    for kind, ident, node in eras._levels(doc):
        for key in eras.KEYS:
            for v in ((node.get(key) or {}).get("versions") or []):
                yield f"{kind[:-1]} {ident}", key, v


@pytest.mark.parametrize("asset", ASSETS)
class TestTheMove:
    """Criteria 1 and 3."""

    def test_no_synthetic_version_is_left_in_data_asset_yaml(self, asset):
        left = [(lvl, key, v["effective_from"]) for lvl, key, v in _every_version(_raw())
                if eras.is_synthetic(v)]
        assert left == [], left

    def test_every_version_in_eras_yaml_is_synthetic(self, asset):
        found = list(_every_version(eras.merged({"hierarchy": _raw().get("hierarchy")}, _eras())))
        assert found, "test precondition - eras.yaml holds versions"
        assert [v["effective_from"] for _l, _k, v in found if not eras.is_synthetic(v)] == []

    def test_the_back_dated_version_moved(self, asset):
        starts = {str(v["effective_from"]) for v in _eras()["amber_setting"]["versions"]}
        assert "2013-01-01" in starts

    def test_a_named_era_moved_with_the_version_that_ends_it(self, asset):
        changes = [str(e.get("change")) for v in _eras()["amber_setting"]["versions"]
                   for e in v["changelog"]]
        assert any("synthetic era -" in c for c in changes), changes
        assert any("synthetic era ends" in c for c in changes), changes

    def test_the_real_versions_stay(self, asset):
        assert [str(v["effective_from"]) for v in _raw()["amber_setting"]["versions"]] == \
            ["2023-01-01"]


def test_an_emptied_level_is_removed():
    """Child Protection's collection-level replacement setting held only its
    synthetic era, so the level comes out of data-asset.yaml (criterion 3)."""
    raw = _raw()
    cp = next(node for kind, ident, node in eras._levels(raw) if ident == "child-protection")
    assert "replacement_setting" not in cp
    assert _eras()["collections"]["child-protection"]["replacement_setting"]["versions"]


@pytest.mark.parametrize("asset", ASSETS)
def test_the_merged_timeline_is_unchanged(asset):
    """Criterion 4: every dataset's resolved setting on every date, as before."""
    golden = json.loads((FIXTURES / f"settings_timelines_{asset}.json").read_text())
    assert golden, "test precondition - the golden timelines are not empty"
    doc = amber_setting.load_doc()
    got = {f"{ds}|{key}": amber_setting.timeline(ds, doc=doc, key=key)
           for ds, key in (k.split("|") for k in golden)}
    assert json.loads(json.dumps(got, default=str)) == golden


def test_without_eras_yaml_a_level_falls_back(tmp_path):
    """A real deployment has no synthetic/ folder: data-asset.yaml alone."""
    asset = tmp_path / "data-asset.yaml"
    asset.write_text(yaml.safe_dump({"amber_setting": {"versions": [
        {"effective_from": "2023-01-01", "value": "promote", "changelog": []}]}}))
    assert amber_setting.load_doc(asset)["amber_setting"]["versions"][0]["value"] == "promote"


def test_an_era_naming_an_unknown_level_is_refused():
    with pytest.raises(eras.ErasError, match="no-such-collection"):
        eras.merged({"hierarchy": {"agencies": []}},
                    {"collections": {"no-such-collection": {"replacement_setting": {
                        "versions": [{"effective_from": "2017-01-01", "value": "green"}]}}}})


class TestTheFreeze:
    """Criterion 5: merged against merged at the base - a version moved
    between the two files is not a change, an edit to a past-dated one in
    eras.yaml is."""

    def _errors(self, monkeypatch, *, old_asset, old_eras, new_eras):
        from qa_tools.common import validate_schedule as vs

        folder = asset_folders.real_folder()
        src = vs.Source(folder / "data-asset.yaml", folder)
        asset_rel = vs._repo_path(src.asset_path)
        eras_rel = vs._repo_path(eras.path_for(src.asset_path))
        monkeypatch.setattr(vs, "_content_at", lambda rel, ref: {
            asset_rel: old_asset, eras_rel: old_eras}.get(rel))
        monkeypatch.setattr(vs, "_eras_text_now", lambda src: new_eras)
        raw = config_yaml.load(src.asset_path) or {}
        return vs._amber_setting_errors(raw, src, ref="HEAD")

    def test_a_version_moved_between_the_files_is_not_a_change(self, monkeypatch):
        folder = asset_folders.real_folder()
        now_eras = (folder / "synthetic" / "eras.yaml").read_text()
        doc = yaml.safe_load((folder / "data-asset.yaml").read_text())
        moved = yaml.safe_load(now_eras)
        # The base: every synthetic version still in data-asset.yaml.
        doc["amber_setting"]["versions"] = sorted(
            doc["amber_setting"]["versions"] + moved["amber_setting"]["versions"],
            key=lambda v: str(v["effective_from"]))
        errors = self._errors(monkeypatch, old_asset=yaml.safe_dump(doc), old_eras=None,
                              new_eras=now_eras)
        assert errors == [], [str(e) for e in errors]

    def test_an_edit_to_a_past_dated_version_in_eras_yaml_is_refused(self, monkeypatch):
        folder = asset_folders.real_folder()
        now_eras = (folder / "synthetic" / "eras.yaml").read_text()
        edited = yaml.safe_load(now_eras)
        edited["amber_setting"]["versions"][0]["value"] = "hold"
        errors = self._errors(monkeypatch, old_asset=(folder / "data-asset.yaml").read_text(),
                              old_eras=now_eras, new_eras=yaml.safe_dump(edited))
        assert any("2013-01-01" in str(e) for e in errors), [str(e) for e in errors]


pytestmark = pytest.mark.asset("quarterly")
