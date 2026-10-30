"""The terminal names the period each slot and supply is for (REQ-PIPE-327).

Through the real commands: `mothman schedule show` against the real
contract, where Child Protection is at files_go_to_period 1 and Emergency
Department at 0, and against a copy giving Child Protection a fall from the
1 August 2026 round. The queue, held and pass words are driven through the
functions those screens call.
"""
from __future__ import annotations

import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from cli import schedule as schedule_cli
from qa_tools.common import agreement, files_go

REAL = Path(__file__).resolve().parent.parent / "contract"


@pytest.fixture(autouse=True)
def _wide(monkeypatch):
    # One table row per line, so a cell's words are not folded across lines.
    monkeypatch.setattr(schedule_cli.console, "width", 250)


def _show(*args) -> str:
    result = CliRunner().invoke(schedule_cli.schedule_group, ["show", *args])
    assert result.exit_code == 0, result.output
    return " ".join(result.output.split())


class TestScheduleShowNamesTheSlotByItsPeriodAndItsRound:
    """Criteria 1, 2, 8 and 9, at 1 and at 0."""

    def test_a_round_column_and_for_period_due_and_no_period_date_column(self):
        out = _show("--dataset", "cp-case-workers", "--all")
        assert "Round Slot" in out
        assert "Period Date" not in out
        assert "For 2026-Q2 · due 9:00am Sunday, 1 February 2026" in out

    def test_the_value_is_stated_at_1_with_its_collection_and_round(self):
        out = _show("--dataset", "cp-case-workers")
        assert ("Files go into the next period (set for Child Protection, since the "
                "2 February 2015 round)") in out

    def test_the_value_is_stated_at_0_too(self):
        out = _show("--dataset", "ed-presentations")
        assert "Files go into the period they arrive in (set for Emergency Department" in out

    def test_the_next_slot_names_its_round_by_date(self):
        out = _show("--dataset", "cp-case-workers")
        assert "Next slot: For 2027-Q2 · due 9:00am Monday, 1 February 2027, on the 1 February 2027 round" in out

    def test_the_claim_window_opens_before_the_due_instant_never_the_periods_date(self):
        out = _show("--dataset", "cp-clients")
        assert "before each slot's due instant" in out
        assert "closes when the next round's claim window opens" in out
        assert "period's date" not in out

    def test_participates_names_the_periods_its_rounds_fill_where_not_0(self):
        out = _show("--dataset", "cp-case-workers")
        assert "participates: February, August - rounds whose files go into Q2 and Q4" in out

    def test_the_calendar_entrys_renderer_states_the_value(self):
        out = _show("--dataset", "cp-clients", "--on", "2026-03-01")
        assert "files go Files go into the next period" in out


@pytest.fixture
def falling(tmp_path, monkeypatch):
    """A copy of the contract where Child Protection falls from 1 to 0 from
    the 1 August 2026 round - the round that would feed 2026-Q3 twice."""
    contract = tmp_path / "contract"
    shutil.copytree(REAL, contract)
    path = contract / "calendar.yaml"
    doc = yaml.safe_load(path.read_text())
    cp = next(c for c in doc["collections"] if c["id"] == "child-protection")
    log = [{"date": "2026-10-30", "author": "a test", "change": "a test's value"}]
    cp["files_go_to_period"] = {"versions": [
        {"effective_from": "2000-01-01", "value": 1, "changelog": log},
        {"effective_from": "2026-08-01", "value": 0, "changelog": log}]}
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    agr = agreement.load(path)
    monkeypatch.setattr(agreement, "current", lambda: agr)
    return agr


class TestAFallsRoundIsMarked:
    """Criterion 7."""

    def test_fall_rounds_names_the_round_and_the_doubly_fed_period(self, falling):
        rounds = files_go.fall_rounds("cp-clients", falling)
        assert rounds and rounds[0][0] == date(2026, 8, 1)
        assert rounds[0][1] == "2026-Q3"

    def test_schedule_show_marks_it(self, falling):
        out = _show("--dataset", "cp-clients", "--all")
        assert ("The 1 August 2026 round: its files will be held for a person - they would "
                "be a second supply for 2026-Q3") in out

    def test_no_round_is_marked_without_a_fall(self):
        assert files_go.fall_rounds("cp-clients") == []

    def test_a_cadence_rule_calendar_has_none_to_mark(self):
        assert files_go.fall_rounds("birth-registrations") == []


class _Held:
    def __init__(self, **kw):
        self.doubly_fed = kw.get("doubly_fed")
        self.reason = kw.get("reason") or {}


class TestAHeldSupplySaysWhichKindOfHeld:
    """Criteria 3 and 6."""

    def test_held_after_a_fall_is_a_second_supply_caused_by_our_change(self):
        said = files_go.held_words(_Held(doubly_fed={"period": "2026-Q3", "round": "2026-08-01"}))
        assert said == ("Held, would be a second supply for 2026-Q3 - agreement change "
                        "from the 1 August 2026 round")

    def test_held_for_one_period_it_cannot_be_filed_to(self):
        said = files_go.held_words(_Held(reason={"unavailable": [["2026-Q2", "closed"]]}))
        assert said == "Held, would be for 2026-Q2"

    def test_held_with_no_period(self):
        assert files_go.held_words(_Held()) == "Held, no period yet"


class TestTheQueueListsWhatEachSupplyIsFor:
    """Criterion 3: 'For <period> · received <instant>'."""

    def test_a_queue_row(self):
        from rich.console import Console

        from cli import filing_tui
        from qa_tools.common import slot_state

        state = type("S", (), {"period": "2026-Q2", "dataset_id": "cp-clients",
                               "supply": "cp-clients@20260201090000000800",
                               "state": slot_state.NOT_YET_DUE, "reason": None})()
        console = Console(width=250, record=True)
        console.print(filing_tui.queue_table([state]))
        text = console.export_text()
        assert "For 2026-Q2 · received " in text
        assert "Supply" in text and "Period" not in text


class TestThePassNamesEachArrivalsPeriodAndTotalsByPeriod:
    """Criterion 4."""

    def test_the_arrivals_line_and_the_totals(self, monkeypatch):
        from qa_tools.common import processing_pass, supply_db

        rows = {"filing_current": [("cp-clients", "2026-Q2"), ("cp-carers", "2026-Q2")],
                "hold": [("cp-placements", {"doubly_fed": {"period": "2026-Q2",
                                                           "round": "2026-05-01"}})]}

        class _Conn:
            def execute(self, sql, params):
                table = "hold" if ".hold" in sql else "filing_current"
                return type("R", (), {"fetchall": lambda self: rows[table]})()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(supply_db, "connect", lambda **kw: _Conn())
        arrival = type("A", (), {"run_id": "cp_run_001", "delivery_name": "Feb 2026",
                                 "received_at": datetime(2026, 2, 1, 1, tzinfo=UTC),
                                 "files_by_dataset": {"cp-clients": (), "cp-carers": (),
                                                      "cp-placements": ()}})()
        report = processing_pass.PassReport()
        line = processing_pass._filed_line(arrival, report)
        assert line.startswith("cp_run_001: For 2026-Q2 · received ")
        assert line.endswith("2 filed, 1 held")
        assert report.by_period == {"2026-Q2": {"filed": 2, "held": 1}}


class TestAReceiptIsShownOnTheAssetsClock:
    """CLI UX critic H1: arrived() printed a supply key's digits, which are
    UTC where the key ends 0000, so one supply read 01:00 in one place and
    9:00am in the next. Every received instant goes through format_instant."""

    def test_a_utc_key_reads_as_its_perth_instant(self, monkeypatch):
        from cli import filing_tui
        from qa_tools.common import display_time, filing

        monkeypatch.setattr(filing, "received_at_of", lambda *a, **k: None)
        want = display_time.format_instant(datetime(2023, 11, 1, 1, tzinfo=UTC))
        assert filing_tui.arrived("cp-case-workers@202311010100000000") == want
        assert "9:00am" in want
        assert filing_tui.for_received("2023-Q4", "cp-case-workers@202311010100000000") \
            == f"For 2023-Q4 · received {want}"

    def test_a_perth_key_reads_the_same(self, monkeypatch):
        from cli import filing_tui
        from qa_tools.common import display_time, filing

        monkeypatch.setattr(filing, "received_at_of", lambda *a, **k: None)
        from datetime import timedelta, timezone
        want = display_time.format_instant(datetime(2023, 8, 1, 9, tzinfo=timezone(timedelta(hours=8))))
        assert filing_tui.arrived("cp-clients@202308010900000800") == want
