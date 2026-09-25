"""The scenario register, read as data, and the map built from it
(REQ-GEN-045).

What the map is FOR, in Keith's own framing: showing this to somebody,
a deliberately broken supply should read as a demonstration rather than
as a defect nobody got round to.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from qa_tools.common import scenario_map as sm
from qa_tools.common import scenarios as sc


class TestTheRegisterReadsAsData:
    """The register stays prose in plans/supply-model.md - it was
    reviewed by Keith as prose, and that review is what makes it
    authoritative. This is a view of it, not a replacement."""

    def test_every_scenario_in_the_register_is_parsed(self):
        """A register of fifty scenarios that quietly returns
        forty-nine is worse than one that cannot be read at all, so
        this counts the raw mentions rather than trusting the parse."""
        import re

        text = Path(sc.REGISTER_PATH).read_text()
        start = text.index(sc.REGISTER_HEADING)
        end = text.find("\n## ", start + 10)
        region = text[start:end if end > 0 else len(text)]
        mentioned = re.findall(r"TS-[0-9]+[a-z]?\s+`\[(?:INJECT|unit|both)\]`", region)

        assert len(sc.parse_register()) == len(mentioned)

    def test_the_injected_set_is_the_one_the_register_marks(self):
        injected = {s.id for s in sc.injected()}
        assert injected, "the register marks nothing for injection"
        assert all(s.mode == sc.INJECT for s in sc.injected())
        assert "TS-1" in injected          # a scenario Keith proposed
        assert "TS-5" not in injected      # a pure unit scenario

    def test_each_scenario_carries_its_section(self):
        for scenario in sc.parse_register():
            assert scenario.section, scenario.id

    def test_a_scenario_carries_what_it_expects_where_the_register_states_one(self):
        by_id = {s.id: s for s in sc.parse_register()}
        assert "resupply of Monday" in (by_id["TS-1"].expect or "")
        assert "off by one" in (by_id["TS-1"].breaks_as or "")
        assert by_id["TS-1"].config == "Config: daily, due 12:00."

    def test_a_missing_heading_is_a_loud_failure_not_an_empty_list(self, tmp_path):
        path = tmp_path / "no-register.md"
        path.write_text("# Some other document\n")
        with pytest.raises(sc.RegisterError):
            sc.parse_register(path)

    def test_an_entry_the_parser_cannot_read_is_a_loud_failure(self, tmp_path):
        path = tmp_path / "broken.md"
        path.write_text(f"{sc.REGISTER_HEADING}\n\n"
                         "**TS-1 `[INJECT]` A title that never closes\n\nbody\n")
        with pytest.raises(sc.RegisterError):
            sc.parse_register(path)

    def test_a_duplicated_id_is_a_loud_failure(self, tmp_path):
        path = tmp_path / "dupes.md"
        path.write_text(f"{sc.REGISTER_HEADING}\n\n"
                         "**TS-1 `[unit]` One.**\n\nbody\n\n"
                         "**TS-1 `[unit]` Two.**\n\nbody\n")
        with pytest.raises(sc.RegisterError, match="more than once"):
            sc.parse_register(path)

    def test_scenarios_sort_by_number_then_suffix(self):
        ids = [s.id for s in sorted(sc.parse_register(), key=lambda s: s.sort_key)]
        assert ids.index("TS-3") < ids.index("TS-3a") < ids.index("TS-3b")
        assert ids.index("TS-9") < ids.index("TS-10")


class TestWhereEachScenarioLanded:
    """Criterion 2: from the generator's OWN record, never from
    anything a person maintains."""

    def test_an_absent_record_is_the_ordinary_state_not_an_error(self, tmp_path):
        assert sm.read_placements(tmp_path / "nothing.json") == {}

    def test_a_malformed_record_does_not_stop_the_map_being_built(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("{not json")
        assert sm.read_placements(path) == {}

    def test_a_recorded_placement_is_read_back_whole(self, tmp_path):
        path = tmp_path / "placements.json"
        path.write_text(json.dumps({"placements": [{
            "scenario_id": "TS-1", "dataset": "birth-registrations",
            "supplies": ["run_047", "run_048"], "period": "2026-07-14",
            "as_of": "2026-07-15"}]}))

        placement = sm.read_placements(path)["TS-1"]

        assert placement.dataset == "birth-registrations"
        assert placement.supplies == ("run_047", "run_048")
        assert placement.is_complete

    def test_a_HALF_recorded_placement_is_not_a_coordinate(self, tmp_path):
        """Criterion 6. A record naming a dataset but no period leads
        exactly nowhere, which is the dead link it forbids."""
        path = tmp_path / "placements.json"
        path.write_text(json.dumps([{"scenario_id": "TS-1",
                                      "dataset": "birth-registrations"}]))
        assert not sm.read_placements(path)["TS-1"].is_complete


class TestTheMapItself:
    def _map(self, placements=None):
        return sm.build_map(sc.parse_register(), placements or {})

    def test_it_names_the_dataset_supplies_period_and_as_of_date(self):
        """Criterion 1."""
        text = sm.build_map(sc.parse_register(), {"TS-1": sm.Placement(
            scenario_id="TS-1", dataset="Birth Registrations",
            supplies=("run_047", "run_048"), period="2026-07-14",
            as_of="2026-07-15")})

        assert "Birth Registrations" in text
        assert "`run_047`" in text and "`run_048`" in text
        assert "2026-07-14" in text
        assert "2026-07-15" in text

    def test_it_emits_COORDINATES_and_never_a_link(self):
        """Criterion 5. The generator does not know the dashboard's
        routing scheme, and a URL written here would break silently
        the next time a route changed."""
        text = self._map({"TS-1": sm.Placement(
            scenario_id="TS-1", dataset="d", supplies=("s",),
            period="p", as_of="2026-01-01")})

        assert "http://" not in text and "https://" not in text
        assert "#/" not in text
        assert "](" not in text, "the map emitted a markdown link"

    def test_a_scenario_with_no_data_behind_it_says_so(self):
        """Criterion 6."""
        text = self._map()
        assert "not injected - nothing to look at yet" in text

    def test_a_unit_scenario_says_it_has_nothing_to_navigate_to(self):
        """A `[unit]` scenario is not an injection that has not
        happened yet - it is one that never will, and saying the same
        thing about both would make the real backlog invisible."""
        text = self._map()
        assert "unit test - no generated data, nothing to navigate to" in text

    def test_it_states_what_each_scenario_DEMONSTRATES_not_only_where_it_is(self):
        """Criterion 9. A coordinate with no meaning beside it sends a
        reader to a page and tells them nothing about why."""
        text = self._map()
        assert "**What it demonstrates.**" in text
        assert "resupply of Monday" in text

    def test_it_reads_as_a_complete_document_on_its_own(self):
        """Criterion 8 - no dashboard to render it, so it carries its
        own explanation and its own groupings."""
        text = self._map()
        assert text.startswith("<!--")
        assert "# Scenario map" in text
        assert "which red was on purpose" in text
        for section in sorted({s.section for s in sc.parse_register()}):
            assert f"## {section}" in text

    def test_it_counts_how_many_are_actually_injected(self):
        text = self._map()
        injected = len(sc.injected())
        assert f"0 of {injected} scenarios marked for injection" in text

    def test_every_scenario_appears(self):
        text = self._map()
        for scenario in sc.parse_register():
            assert f"### {scenario.id} - " in text, scenario.id


class TestTheCommittedMap:
    """Criterion 4: committed markdown, so anything reading it reads a
    committed file and never touches data/."""

    def test_the_committed_map_is_not_stale(self):
        """The same shape plans/INDEX.md's own gate has. A generated
        file that can drift from its source is one that will."""
        assert sm.MAP_PATH.read_text() == sm.build_map(
            sc.parse_register(), sm.read_placements()), (
            "SCENARIOS.md is stale - run `mothman scenarios map`")

    def test_the_map_lives_outside_data(self):
        assert "data" not in sm.MAP_PATH.relative_to(sm.ROOT).parts

    def test_building_the_map_reads_nothing_under_data_except_the_record(self):
        """The record is generator bookkeeping and lives under data/ by
        design; the MAP does not, which is what lets the dashboard
        build read it under the standing no-data rule."""
        source = Path(sm.__file__).read_text()
        assert 'ROOT / "data" / "scenario_placements.json"' in source
        assert "duckdb" not in source
        assert "supply_db" not in source


class TestItIsRebuiltWithTheHistory:
    """Criterion 3: in the same act, so the two cannot disagree."""

    @pytest.mark.parametrize("path", ["cli/bdm.py", "cli/cp.py"])
    def test_generating_synthetic_data_also_rebuilds_the_map(self, path):
        tree = ast.parse(Path(path).read_text())
        function = next(n for n in ast.walk(tree)
                         if isinstance(n, ast.FunctionDef)
                         and n.name == "generate_synthetic_data")
        calls = {getattr(n.func, "attr", None) for n in ast.walk(function)
                  if isinstance(n, ast.Call)}
        assert "write_map" in calls, (
            f"{path}'s generate_synthetic_data no longer rebuilds the scenario map - "
            f"the map and the history can now disagree silently")
