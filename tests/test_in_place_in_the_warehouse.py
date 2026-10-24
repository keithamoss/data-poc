"""'In place' says where - 'in place in the warehouse' - wherever the
terminal shows it to a person (REQ-DASH-277 criteria 2, 3 and 5).

The terminal's own words, driven through the functions that produce them:
the queue's and the door's state words (filing_tui.listed_words), the line a
period standing on another's supply prints, mothman scenarios' 'where' line
and the generated scenario register. The dashboard's half is
tests/test_dashboard_e2e.py::TestInPlaceInTheWarehouse.
"""
from __future__ import annotations

from types import SimpleNamespace

from cli import filing_tui
from cli import scenarios as scenarios_cli
from qa_tools.common import filing_queue, scenario_map, slot_state


def _words(state: str, reason: str | None = None) -> str:
    return filing_tui.listed_words(SimpleNamespace(state=SimpleNamespace(
        state=state, reason=reason, files=())))


class TestTheTerminalSaysWhere:

    def test_a_promoted_supply_is_in_place_in_the_warehouse(self):
        assert _words(slot_state.PROMOTED) == "in place in the warehouse (promoted)"

    def test_one_awaiting_acknowledgement_too(self):
        assert _words(slot_state.AWAITING_ACKNOWLEDGEMENT) == (
            "in place in the warehouse, awaiting acknowledgement")

    def test_one_re_checked_worse_too(self):
        assert _words(filing_queue.RECHECKED_WORSE, "Came back red: 2 checks") == (
            "in place in the warehouse - came back red")

    def test_a_period_standing_on_another_says_where_its_supply_is(self):
        line = filing_tui.stands_on_line(SimpleNamespace(
            state=slot_state.INHERITED, period="2024-Q3", stands_on="2024-Q2"))
        assert line == ("2024-Q3 stands on 2024-Q2's supply (inherited) -\n"
                        "the supply in place in the warehouse is not one of these.")
        assert all(len(part) <= 80 for part in line.splitlines())

    def test_the_line_a_person_picks_stays_within_80_columns(self, monkeypatch):
        monkeypatch.setattr(filing_tui, "arrived", lambda supply: "2024-08-13 09:00")
        line = filing_tui._supply_line(SimpleNamespace(verdict="amber", state=SimpleNamespace(
            state=slot_state.AWAITING_ACKNOWLEDGEMENT, reason=None, files=(), supply="x@1")))
        assert line == ("2024-08-13 09:00  in place in the warehouse, awaiting acknowledgement"
                        "  (amber)")
        assert len(line) <= 80

    def test_the_scenario_list_says_in_the_warehouse_on(self):
        where = scenarios_cli.where_line(SimpleNamespace(
            dataset="cp-clients", period="2024-Q3", in_place_on="2024-08-14"))
        assert where == "cp-clients · 2024-Q3 · in the warehouse on 2024-08-14"
        assert len(where) <= 80

    def test_the_scenario_register_says_in_the_warehouse_on(self):
        scenario = SimpleNamespace(id="TS-1", title="t", expect="e.", body="", breaks_as="",
                                   config="", is_injected=True)
        placement = scenario_map.Placement.of({
            "dataset": "cp-clients", "period": "2024-Q3", "in_place_on": "2024-08-14",
            "supplies": ["cp-clients@1"]})
        text = "\n".join(scenario_map._entry(scenario, placement))
        assert '| Set "in the warehouse on" to | 2024-08-14 |' in text
        assert "in-place-on" not in text and "In place on" not in text
