"""REQ-PIPE-112 beyond asset_time itself: the schedule gate's
daylight-saving refusal (criterion 8), and the settings changelogs'
structured shape and its conversion (criteria 16 and 17).

The real asset is in Perth, which has no daylight saving, so the gate is
exercised by pointing the asset clock at Sydney (NFR 4) - a second asset in
such a jurisdiction is why this requirement exists, and it has no real data
to find the bugs for it.
"""
from __future__ import annotations

from datetime import date

import pytest
import yaml

from qa_tools.common import amber_setting, asset_time, slots
from qa_tools.common import validate_schedule as vs
from qa_tools.common.schemas import DataAsset

ROOT = vs.ROOT


@pytest.fixture
def sydney(tmp_path, monkeypatch):
    """The asset's clock in Sydney; everything else the real configuration."""
    doc = yaml.safe_load((ROOT / "contract" / "data-asset.yaml").read_text())
    doc["timezone"] = {"versions": [{
        "effective_from": "1970-01-01", "zone": "Australia/Sydney",
        "changelog": [{"date": "2026-10-11", "author": "pytest", "change": "test"}]}]}
    path = tmp_path / "data-asset.yaml"
    path.write_text(yaml.safe_dump(doc))
    monkeypatch.setattr(asset_time, "DATA_ASSET_YAML", path)
    asset_time.timezone_versions.cache_clear()
    yield
    asset_time.timezone_versions.cache_clear()


class TestTheGateRefusesADueTimeDaylightSavingBreaks:
    """Criterion 8 - named by dataset, period and time."""

    def test_a_time_in_the_spring_forward_gap_is_refused(self, sydney, monkeypatch):
        # Birth Registrations is daily from 2026-08-24, so 2026-10-04 -
        # Sydney's spring-forward day - is one of its periods.
        monkeypatch.setattr(slots, "_timing",
                            lambda dataset_id: ("02:30", 0, None))
        errors = vs._daylight_saving_errors(vs.Source.default())
        gap = [e for e in errors if "2026-10-04" in e.problem]
        assert gap, [e.problem for e in errors][:3]
        assert "does not exist" in gap[0].problem and "02:30" in gap[0].problem
        assert "birth" in gap[0].scope

    def test_a_time_in_the_fall_back_overlap_is_refused(self, sydney, monkeypatch):
        monkeypatch.setattr(slots, "_timing",
                            lambda dataset_id: ("02:30", 0, None))
        errors = vs._daylight_saving_errors(vs.Source.default())
        assert any("2027-04-04" in e.problem and "occurs twice" in e.problem for e in errors)

    def test_an_ordinary_time_passes_in_a_daylight_saving_zone(self, sydney, monkeypatch):
        monkeypatch.setattr(slots, "_timing",
                            lambda dataset_id: ("09:00", 0, None))
        assert vs._daylight_saving_errors(vs.Source.default()) == []

    def test_the_real_configuration_passes(self):
        assert vs._daylight_saving_errors(vs.Source.default()) == []


class TestSettingsChangelogsAreStructured:
    """Criteria 16 and 17."""

    def _doc(self):
        return yaml.safe_load((ROOT / "contract" / "data-asset.yaml").read_text())

    def test_a_plain_string_entry_is_refused(self):
        doc = self._doc()
        doc["amber_setting"]["versions"][0]["changelog"].append("2026-10-11: a plain string")
        with pytest.raises(Exception, match="changelog"):
            DataAsset.model_validate(doc)

    def test_the_committed_configuration_is_structured(self):
        DataAsset.model_validate(self._doc())

    def test_the_conversion_reads_as_no_change_to_the_past(self):
        """The guard compared raw values, so reshaping a past changelog read
        as altering a frozen version (delivery-architect S1)."""
        new = self._doc()
        old = self._doc()
        for key in ("amber_setting", "replacement_setting"):
            for version in old[key]["versions"]:
                version["changelog"] = [f"{e['date']}: {e['change']}"
                                        for e in version["changelog"]]
        assert amber_setting.past_change_problems(old, new, date(2030, 1, 1),
                                                  synthetic=False) == []

    def test_an_edit_to_a_past_entry_is_still_refused(self):
        old, new = self._doc(), self._doc()
        new["amber_setting"]["versions"][0]["changelog"][0]["change"] = "rewritten"
        problems = amber_setting.past_change_problems(old, new, date(2030, 1, 1),
                                                      synthetic=False)
        assert problems and "append-only" in problems[0][1]

    def test_an_appended_entry_is_accepted(self):
        old, new = self._doc(), self._doc()
        new["amber_setting"]["versions"][0]["changelog"].append(
            {"date": "2026-10-11", "author": "pytest", "change": "a note added later"})
        assert amber_setting.past_change_problems(old, new, date(2030, 1, 1),
                                                  synthetic=False) == []
