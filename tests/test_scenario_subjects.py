"""Each scenario's link names what it lands on - semantically, in its
placement record and the committed map (REQ-DASH-208 criterion 2)."""
from __future__ import annotations

from datetime import date

from generator import scenario_injection as si
from qa_tools.common import scenario_map


def _placement(**kw):
    return si.Placement(scenario_id="TS-75a", dataset="cp-clients", period="2025-Q1",
                        period_date=date(2025, 1, 1), config="c", **kw)


class TestThePlacementRecordNamesItsSubject:

    def test_a_linked_scenario_carries_its_links_subject(self):
        record = _placement(subjects=(("TS-75a", scenario_map.AS_AT_PANEL),)).as_record()
        assert record["subject"] == scenario_map.AS_AT_PANEL

    def test_one_with_no_named_subject_lands_on_its_supply_row(self):
        assert _placement().as_record()["subject"] == scenario_map.SUPPLY_HISTORY_ROW

    def test_the_map_reads_it_and_an_older_record_defaults(self):
        got = scenario_map.Placement.of({"scenario_id": "TS-1", "dataset": "d",
                                         "period": "p", "in_place_on": "2025-01-01",
                                         "subject": scenario_map.VERDICT_LINE})
        assert got.subject == scenario_map.VERDICT_LINE
        older = scenario_map.Placement.of({"scenario_id": "TS-1", "dataset": "d",
                                           "period": "p", "in_place_on": "2025-01-01"})
        assert older.subject == scenario_map.SUPPLY_HISTORY_ROW


class TestEveryLinkNamesASubjectFromTheVocabulary:

    def test_each_is_a_name_and_never_a_selector(self):
        links = [link for inj in si.INJECTIONS for link in inj.links]
        assert links, "no links to check"
        for link in links:
            assert link.subject in scenario_map.SUBJECTS, link
            assert not any(ch in link.subject for ch in "[].#=\"'"), link

    def test_the_as_at_scenarios_land_on_what_their_expect_quotes(self):
        """TS-75 to TS-78's Expects quote the as-at panel, the substitution
        detail or the verdict line (REQ-GEN-199 criterion 36)."""
        subject = {link.scenario_id: link.subject for inj in si.INJECTIONS for link in inj.links}
        assert subject["TS-75a"] == subject["TS-75b"] == scenario_map.AS_AT_PANEL
        assert subject["TS-76"] == subject["TS-77a"] == scenario_map.SUBSTITUTION_DRILL_DOWN
        assert subject["TS-78b"] == scenario_map.VERDICT_LINE


class TestALetteredSiblingCarriesItsOwnSubject:
    """TS-77b shares TS-77a's placement and lands on something else - its
    record must say so (found driving the page: it landed on TS-77a's)."""

    def test_written_with_its_own_subject(self, tmp_path, monkeypatch):
        import json

        monkeypatch.setitem(si._ALSO, "TS-77a", ("TS-77b",))
        placement = si.Placement(
            scenario_id="TS-77a", dataset="cp-placements", period="2023-Q2",
            period_date=date(2023, 5, 1), config="c",
            subjects=(("TS-77a", scenario_map.SUBSTITUTION_DRILL_DOWN),
                      ("TS-77b", scenario_map.AS_AT_PANEL)))
        out = si.write_placements([placement], path=tmp_path / "p.json")
        records = {r["scenario_id"]: r for r in json.loads(out.read_text())["placements"]}
        assert records["TS-77a"]["subject"] == scenario_map.SUBSTITUTION_DRILL_DOWN
        assert records["TS-77b"]["subject"] == scenario_map.AS_AT_PANEL


class TestAnUnknownSubjectIsRefused:
    """post-build-review #202 F10: a subject name outside the vocabulary
    fails the build, rather than reading on the page as 'nothing to show'."""

    def test_reading_a_record_with_an_unknown_subject_raises(self):
        import pytest

        with pytest.raises(ValueError, match="no-such-thing"):
            scenario_map.Placement.of({"scenario_id": "TS-1", "dataset": "d", "period": "p",
                                       "in_place_on": "2025-01-01", "subject": "no-such-thing"})
