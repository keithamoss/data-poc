"""'In place' says where - 'in place in the warehouse' - wherever the
terminal shows it to a person (REQ-DASH-277 criteria 2, 3 and 5).

The terminal's own words, driven through the functions that produce them:
the queue's and the door's state words (filing_tui.listed_words), the line a
period standing on another's supply prints, mothman scenarios' 'where' line
and the generated scenario register. The dashboard's half is
tests/test_dashboard_e2e.py::TestInPlaceInTheWarehouse.
"""
from __future__ import annotations

import io
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
        # WITH questionary's pointer before it (post-build-review #266 S2):
        # the full words were 78 columns, 81 once the pointer is drawn.
        assert line == ("2024-08-13 09:00  in place in the warehouse, awaiting acknowledgeme\u2026"
                        "  (amber)")
        assert len(line) + 3 <= 80

    def test_the_scenario_list_says_in_the_warehouse_on(self):
        where = scenarios_cli.where_line(SimpleNamespace(
            dataset="cp-clients", period="2024-Q3", in_place_on="2024-08-14"))
        assert where == "cp-clients · 2024-Q3 · in the warehouse on 2024-08-14"
        assert len(where) <= 80

    def test_the_scenario_list_as_printed_stays_within_80_columns(self, monkeypatch):
        """Post-build-review #266: the 'where' line above is checked as a
        string; this is the table `mothman scenarios list` prints, at 80
        columns - its Where cell wraps (as 'in place on' did before), never
        past the edge."""
        from rich.cells import cell_len
        from rich.console import Console

        printer = Console(width=80, record=True, file=io.StringIO())
        monkeypatch.setattr(scenarios_cli, "console", printer)
        scenarios_cli.list_command.callback(injected_only=False)
        lines = printer.export_text().splitlines()
        assert any("warehouse on" in line for line in lines)
        assert max(cell_len(line) for line in lines) <= 80

    def test_the_scenario_register_says_in_the_warehouse_on(self):
        scenario = SimpleNamespace(id="TS-1", title="t", expect="e.", body="", breaks_as="",
                                   config="", is_injected=True)
        placement = scenario_map.Placement.of({
            "dataset": "cp-clients", "period": "2024-Q3", "in_place_on": "2024-08-14",
            "supplies": ["cp-clients@1"]})
        text = "\n".join(scenario_map._entry(scenario, placement))
        assert '| Set "in the warehouse on" to | 2024-08-14 |' in text
        assert "in-place-on" not in text and "In place on" not in text


# The verdicts a listed supply can carry: filing_queue._verdict's two words
# for none, and every status promotion.status_of can return.
_VERDICTS = ("green", "amber", "red", filing_queue.NO_VERDICT, filing_queue.VERDICT_UNREADABLE,
             "exhausted", "inactive", "nodata", "notcounted", "turnedoff")

#: questionary's pointer and the space after it, drawn before every choice.
_POINTER = 3


def _real_states(monkeypatch):
    """Every state a listed supply can be in, each with the reason
    filing_queue really gives it - the re-checked-worse reason built by
    filing_queue._rechecked_worse itself, the decided ones with a real
    instant in the longest month and weekday names."""
    from qa_tools.common import display_time, rechecking

    when = "2024-09-18T04:15:00+00:00"   # a Wednesday in September
    states = []
    for now in ("amber", "red"):
        monkeypatch.setattr(rechecking, "worse_for", lambda *a, now=now: rechecking.Worse(
            dataset_id="cp-investigations", supply="cp-investigations@20240801010000000000",
            period="2024-Q3", promoted_on="green", now=now, recheck_id=1234,
            recheck_at="2024-09-18T12:15:00"))
        (worse,) = filing_queue._rechecked_worse(None, "", [slot_state.SlotState(
            dataset_id="cp-investigations", period="2024-Q3",
            supply="cp-investigations@20240801010000000000",
            state=slot_state.AWAITING_ACKNOWLEDGEMENT)])
        states.append(SimpleNamespace(state=worse.state, reason=worse.reason, files=()))
    reasons = {
        slot_state.REJECTED: f"by keith.moss@example.wa.gov.au, "
                             f"{display_time.format_instant(when)}",
        filing_queue.SUPERSEDED: f"by the supply that arrived "
                                 f"{display_time.format_instant(when)}",
        filing_queue.COULD_NOT_LOAD: "the file's header names a column the contract does "
                                     "not declare: notification_reference_number",
    }
    for state in filing_tui._LISTED_AS:
        files = (("cp_investigations_2024-08-01.csv", "cp_investigations_2024-08-01_v2.csv")
                 if state == slot_state.TWO_FILES else ())
        states.append(SimpleNamespace(state=state, reason=reasons.get(state), files=files))
    return states


class TestTheLineAPersonPicks:

    def test_every_real_state_and_verdict_fits_80_columns(self, monkeypatch):
        """Post-build-review #266 S2: the picker's line, with questionary's
        pointer before it, within 80 columns for every state x verdict -
        the re-checked-worse amber line reached 86."""
        monkeypatch.setattr(filing_tui, "arrived", lambda supply: "2024-08-13 09:00")
        states = _real_states(monkeypatch)
        assert len(states) == len(filing_tui._LISTED_AS) + 2
        over = []
        for state in states:
            for verdict in _VERDICTS:
                line = filing_tui._supply_line(SimpleNamespace(
                    verdict=verdict, state=SimpleNamespace(supply="x@1", **vars(state))))
                if _POINTER + len(line) > 80:
                    over.append((_POINTER + len(line), line))
        assert not over, over

    def test_a_shortened_line_still_says_when_where_and_its_verdict(self, monkeypatch):
        """Shortened with filing_tui's own shortening (criterion 5), never
        wrapped: the arrival, the start of the words and the verdict all
        stay, so the line is still meaningful piped."""
        monkeypatch.setattr(filing_tui, "arrived", lambda supply: "2024-08-13 09:00")
        line = filing_tui._supply_line(SimpleNamespace(
            verdict=filing_queue.VERDICT_UNREADABLE, state=SimpleNamespace(
                state=slot_state.AWAITING_ACKNOWLEDGEMENT, reason=None, files=(),
                supply="x@1")))
        assert line.startswith("2024-08-13 09:00  in place in the warehouse")
        assert line.endswith(f"…  ({filing_queue.VERDICT_UNREADABLE})")
        assert "\n" not in line and "[" not in line
