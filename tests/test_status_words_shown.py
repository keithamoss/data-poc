"""REQ-TEST-361 criterion 5: no colour word comes back into what the
terminal or a GitHub Issue prints for a status.

The Python status_words and every wording REQ-TEST-360 criteria 2 to 10 build
from a status value - the outcome lines, the root-cause and queue-state lines,
the re-checked-worse heading and reason, the bulk re-check's summary, the
gate's refusal, the ticket's title, bodies and result lines, the scenario
map's 'Built to' and a replacement setting's value - are run over every
status in status-cases.json, with NO_COLOR set, and any 'green', 'amber' or
'red' in what a person reads fails the test. Behaviour, not source text
(CLAUDE.md test rule 1): each function is called and its output read.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

CASES = json.loads((Path(__file__).resolve().parents[1] / "status-cases.json").read_text())
LABELS = {k: v for k, v in CASES["vocabulary"]["labels"].items() if not k.startswith("_")}
STATUSES = sorted(LABELS)
VERDICTS = ("green", "amber", "red")
COLOUR = re.compile(r"\b(green|amber|red)\b", re.I)


@pytest.fixture(autouse=True)
def _no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")


def _clean(text: str, where: str) -> None:
    # Rich markup is a colour STYLE, not a word a person reads (REQ-TEST-360
    # criterion 11): '[red]...[/red]' prints no 'red' with NO_COLOR set.
    shown = re.sub(r"\[/?[a-z ]+\]", "", text)
    found = COLOUR.search(shown)
    assert found is None, f"{where}: {found.group(0)!r} in {shown!r}"


def test_the_table_names_every_status_it_is_run_over():
    """CLAUDE.md test rule 3: an empty table cannot pass."""
    assert set(VERDICTS) <= set(STATUSES) and len(STATUSES) >= 8


@pytest.mark.parametrize("value", STATUSES)
@pytest.mark.parametrize("form", ["label", "verb", "count"])
def test_status_words(value, form):
    from qa_tools.common.dataset_status import status_words

    _clean(status_words(value, form), f"status_words({value!r}, {form!r})")


@pytest.mark.parametrize("value", STATUSES)
def test_the_outcome_lines(value):
    from cli import lifecycle_report
    from qa_tools.common.dataset_status import status_words

    lines = lifecycle_report.outcome_lines(
        [lifecycle_report.ReGated("cp-clients", value, status_words(value, "verb"),
                                  "still held back")] * 9, more="see the queue")
    assert lines
    for line in lines:
        _clean(line, "outcome_lines")


def test_the_root_cause_lines():
    from qa_tools.common import period_schema, root_cause

    for root in (root_cause.Root(kind="slot", dataset_id="cp-clients", period="2024-Q4",
                                 reason=period_schema.PAST_DUE),
                 root_cause.Root(kind="supply", dataset_id="cp-clients", period="2024-Q4",
                                 supply="cp-clients@1")):
        _clean(root_cause._overdue_words(root), "root_cause._overdue_words")
        _clean(root_cause._overdue_reason(root), "root_cause._overdue_reason")


def test_the_queue_state_words():
    from cli import filing_tui

    said = list(filing_tui._HOW_IT_READS.values()) + list(filing_tui._LISTED_AS.values())
    assert said
    for words in said:
        _clean(words, "filing_tui state words")
    for value in STATUSES:
        _clean(filing_tui.verdict_words(value), "verdict_words")


@pytest.mark.parametrize("was,now", [("green", "amber"), ("green", "red"), ("amber", "red")])
def test_the_rechecked_worse_heading_and_reason(was, now):
    from cli import filing_tui
    from qa_tools.common import filing_queue, rechecking, slot_state

    w = rechecking.Worse("cp-carers", "cp-carers@1", "2024-Q3", was, now, 7,
                         "2024-09-18T12:15:00", "2024-08-01T02:00:00+00:00")
    reason = filing_queue.rechecked_worse_reason(w)
    assert "was promoted " in reason and " on Thursday, 1 August 2024," in reason
    _clean(reason, "rechecked_worse_reason")
    state = slot_state.SlotState(dataset_id="cp-carers", period="2024-Q3",
                                 state=filing_queue.RECHECKED_WORSE, supply="cp-carers@1",
                                 verdict=now, reason=reason)
    _clean(filing_tui._label(state), "filing_tui._label")
    _clean(filing_tui.listed_words(SimpleNamespace(state=state)), "listed_words")


def test_the_bulk_recheck_summary():
    from qa_tools.common import bulk_recheck as bulk, rechecking

    covered = bulk.Covered("cp-carers", "cp-carers@1", "2024-Q3", rechecking.PROMOTED, "green", "f")
    ran = bulk.Ran(covered, SimpleNamespace(completed=True, status="red", message="m"), ("a.b",))
    lines = bulk.summary_lines(bulk.Summary(ran=[ran]))
    assert any("Promoted, then failing on re-check" in line for line in lines), lines
    for line in lines:
        _clean(line, "bulk_recheck.summary_lines")


@pytest.mark.parametrize("value", [v for v in STATUSES if v != "green"])
def test_the_gates_refusal(value):
    from qa_tools.common import promotion

    ok, why = promotion.should_promote(status=value, slot_filled=False, held_without_slot=False,
                                       has_active_checks=True, amber_setting=promotion.AMBER_HOLD)
    assert not ok
    _clean(why, f"should_promote({value!r})")


def test_the_gate_refuses_a_status_it_has_no_word_for():
    """REQ-QAC-047: refused, never passed through raw (the earlier critic's
    finding on promotion._status_label)."""
    from qa_tools.common import promotion
    from qa_tools.common.dataset_status import UnknownStatusError

    with pytest.raises(UnknownStatusError):
        promotion.should_promote(status="purple", slot_filled=False, held_without_slot=False,
                                 has_active_checks=True)


@pytest.mark.asset("daily")
@pytest.mark.parametrize("value", VERDICTS)
def test_the_ticket_wording(value, monkeypatch):
    from qa_tools.common import ticket_sync
    from qa_tools.common.ticket_sync import DatasetScope

    calls = []

    def gh(args):
        calls.append(args)
        return "https://github.com/o/r/issues/42\n" if args[:2] == ["issue", "create"] else ""

    monkeypatch.setattr(ticket_sync, "_run_gh", gh)
    scope = DatasetScope("birth-registrations", "Birth Registrations", "registry-services",
                         "civil-registration")
    ticket_sync.open_ticket("o", "r", scope, value, None, None)
    (create,) = [a for a in calls if a[:2] == ["issue", "create"]]
    _clean(create[create.index("--title") + 1], "ticket title")
    _clean(create[create.index("--body") + 1], "ticket body")
    _clean(ticket_sync._label(value), "ticket label")
    _clean(ticket_sync._verb(value), "ticket verb")


def test_the_scenario_maps_built_to():
    from qa_tools.common import scenario_map

    for value in VERDICTS:
        text = scenario_map._target_text({"built_to": value, "rules": ["x.completeness"],
                                          "date": "2026-07-18", "at": "14:00"})
        _clean(text, "scenario_map._target_text")


def test_a_replacement_settings_value_is_said_in_words():
    """REQ-DASH-359 criterion 12: 'never', 'when passing', 'when passing or
    warning' - never the raw green or green-or-amber."""
    from qa_tools.common import amber_setting, replacement_setting

    assert replacement_setting.WORDS == {"never": "never", "green": "when passing",
                                         "green-or-amber": "when passing or warning"}
    for value in replacement_setting.WORDS:
        _clean(replacement_setting.words(value), "replacement_setting.words")
    with pytest.raises(amber_setting.AmberSettingError):
        replacement_setting.words("amber")


def test_the_warn_setting_commands_help_says_warn_setting():
    """The earlier critic's minor finding: `mothman supply amber-setting`'s
    help said 'the amber setting'. The command's name is something people
    type and stays (REQ-TEST-360 NFR COMPATIBILITY); its words change."""
    from click.testing import CliRunner

    from cli import supply

    got = CliRunner().invoke(supply.supply_group, ["amber-setting", "--help"])
    assert got.exit_code == 0, got.output
    flat = " ".join(got.output.split())
    assert "The warn setting in force for each dataset" in flat, flat
    assert "amber setting" not in flat.lower()


def test_the_scenarios_bands_help_says_warn():
    """The Pass / Warn / Fail critic's finding 3: `mothman scenarios bands
    --help` said 'whether it can read amber' and 'its amber band is'."""
    from click.testing import CliRunner

    from cli import scenarios

    got = CliRunner().invoke(scenarios.scenarios_group, ["bands", "--help"])
    assert got.exit_code == 0, got.output
    flat = " ".join(got.output.split())
    assert "whether it can read Warn" in flat and "its warn band is" in flat, flat
    _clean(flat, "mothman scenarios bands --help")


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
