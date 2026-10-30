"""A collection's files_go_to_period changing from a round (REQ-PIPE-322).

A RISE is refused until every period it skips is declared not owed; a FALL
is accepted, with the files that would feed one period twice held for a
person. Each test copies the real contract, gives Child Protection a second
files_go_to_period version from the 1 August 2026 round, and asks the
schedule gate - or the slots - what follows. The real file is untouched.
"""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from qa_tools.common import agreement, schedule, slots
from qa_tools.common.validate_schedule import (NOT_EXPECTED_PLACEHOLDER, Source,
                                                fall_lines, validate)

REAL = Path(__file__).resolve().parent.parent / "contract"
CP = ("cp-carers", "cp-case-workers", "cp-clients", "cp-investigations",
      "cp-notifications", "cp-placements")


def _v(effective_from, value):
    return {"effective_from": effective_from, "value": value,
            "changelog": [{"date": "2026-10-30", "author": "a test", "change": "a test's value"}]}


def _cp(doc):
    return next(c for c in doc["collections"] if c["id"] == "child-protection")


def _dataset(doc, did):
    return next(d for d in doc["datasets"] if d["id"] == did)


@pytest.fixture
def contract(tmp_path):
    contract = tmp_path / "contract"
    shutil.copytree(REAL, contract)
    cal_path = contract / "calendar.yaml"

    def write(old, new, declare=(), reason="the change of period this round skips"):
        doc = yaml.safe_load(cal_path.read_text())
        _cp(doc)["files_go_to_period"] = {"versions": [_v("2000-01-01", old),
                                                       _v("2026-08-01", new)]}
        for did in declare:
            entry = _dataset(doc, did)
            entry["not_expected"] = list(entry.get("not_expected") or []) + [
                {"period": "2026-Q3", "reason": reason}]
        cal_path.write_text(yaml.safe_dump(doc, sort_keys=False))
        return Source(contract / "data-asset.yaml", contract), cal_path
    return write


def _offset(errors):
    return [e for e in errors if "files_go_to_period" in f"{e.scope} {e.problem} {e.fix}"
            or "not_expected" in f"{e.problem} {e.fix}"]


class TestARiseIsRefusedUntilTheSkippedPeriodIsDeclared:
    """Criteria 1, 2, 5 and 8."""

    def test_refused_while_2026_q3_is_owed_naming_it_and_who_must_declare(self, contract):
        src, _ = contract(0, 1)
        found = _offset(validate(src))
        assert len(found) == 1, [f"{e.scope}: {e.problem}" for e in found]
        [e] = found
        text = f"{e.scope} {e.problem} {e.fix}"
        assert "child-protection" in text and "2026-08-01" in text and "2026-Q3" in text
        for did in CP:
            assert did in text
        assert "need not" in text.lower()
        assert "not_expected:" in e.fix and NOT_EXPECTED_PLACEHOLDER in e.fix

    def test_refused_while_a_pasted_entry_keeps_its_placeholder(self, contract):
        src, _ = contract(0, 1, declare=CP, reason=NOT_EXPECTED_PLACEHOLDER)
        text = "\n".join(f"{e.scope} {e.problem} {e.fix}" for e in validate(src))
        assert "2026-Q3" in text and "state the reason" in text.lower()

    def test_accepted_once_every_dataset_declares_it_and_then_files_by_the_new_value(
            self, contract, tmp_path):
        src, cal_path = contract(0, 1, declare=CP)
        assert _offset(validate(src)) == []
        agr = agreement.load(cal_path)
        names = {s.round_date: s.name for s in slots.slots_for_dataset(
            "cp-clients", until=date(2027, 1, 1), agreement=agr)}
        assert names[date(2026, 5, 1)] == "2026-Q2"
        assert names[date(2026, 8, 1)] == "2026-Q4"
        assert "2026-Q3" not in names.values()

    def test_a_first_version_is_no_change(self, contract):
        """Criterion 5: the real history is at 1 from its first round."""
        src = Source(REAL / "data-asset.yaml", REAL)
        assert _offset(validate(src)) == []


class TestAFallIsAcceptedAndItsDoublyFedRoundOpensNoSlot:
    """Criteria 3, 8 and 10."""

    def test_accepted_with_its_information_line(self, contract):
        src, cal_path = contract(1, 0)
        assert _offset(validate(src)) == []
        lines = fall_lines(agreement.load(cal_path))
        assert lines == ["Child Protection: from the 1 August 2026 round, files for 2026-Q3 "
                         "will be held for a person - the 1 May 2026 round already fills it."]

    def test_the_may_round_fills_q3_and_the_august_round_opens_no_slot(self, contract):
        _, cal_path = contract(1, 0)
        agr = agreement.load(cal_path)
        names = {s.round_date: s.name for s in slots.slots_for_dataset(
            "cp-clients", until=date(2027, 3, 1), agreement=agr)}
        assert names[date(2026, 5, 1)] == "2026-Q3"
        assert date(2026, 8, 1) not in names
        assert names[date(2026, 11, 1)] == "2026-Q4"
        assert schedule.round_of("2026-Q3", "cp-clients", agr) == date(2026, 5, 1)


def test_the_gate_prints_the_fall_as_information_and_passes(contract, capsys):
    """Criterion 10, through the gate's own entry point."""
    from qa_tools.common.validate_schedule import main

    src, _ = contract(1, 0)
    assert main(src) == 0
    out = capsys.readouterr().out
    assert "schedule validation OK" in out
    assert "files for 2026-Q3 will be held for a person" in out


class TestASupplyInTheDoublyFedRoundIsHeldForAPerson:
    """Criteria 3, 8 and 9: after a fall from 1 to 0 from the 1 August 2026
    round, a supply received in that round is held with the agreement
    change as its reason, and may only go into 2026-Q3 as a resupply or be
    rejected."""

    @staticmethod
    def _held(contract, monkeypatch):
        from datetime import datetime, timedelta, timezone

        from qa_tools.common import agreement as agreement_mod, assignment

        _, cal_path = contract(1, 0)
        agr = agreement.load(cal_path)
        monkeypatch.setattr(agreement_mod, "current", lambda: agr)
        at = datetime(2026, 8, 1, 10, tzinfo=timezone(timedelta(hours=8)))
        got = assignment.assign("cp-clients", "cp-clients@aug", at,
                                slots.slots_for_dataset("cp-clients", until=date(2027, 3, 1),
                                                        agreement=agr),
                                frozenset({"2026-Q3"}))
        return got

    def test_it_is_held_naming_the_change_and_the_period(self, contract, monkeypatch):
        got = self._held(contract, monkeypatch)
        assert got.is_held
        assert got.doubly_fed == {
            "collection_id": "child-protection", "collection": "Child Protection",
            "version": "2026-08-01", "round": "2026-08-01", "period": "2026-Q3",
            "filled_by": "2026-05-01"}

    def test_the_hold_offers_only_a_resupply_of_q3_or_rejecting_it(self, contract,
                                                                     monkeypatch):
        from datetime import datetime, timezone

        from qa_tools.common import supply_holds

        got = self._held(contract, monkeypatch)
        held = supply_holds.Held(
            dataset_id="cp-clients", supply_id="cp-clients@aug",
            kind=supply_holds.ASSIGNMENT_RULE, reason=supply_holds.reason_for(got),
            raised_by="the filing rule", delivery=None,
            raised_at=datetime(2026, 8, 1, tzinfo=timezone.utc))
        responses = " | ".join(held.responses)
        assert "--to-period 2026-Q3" in responses and "reject" in responses
        assert "2026-Q4" not in responses
        assert "files_go_to_period" in responses and "correction" in responses
        words = held.describe()
        assert "2026-Q3" in words and "1 May 2026" in words and "Child Protection" in words


def test_placing_it_into_the_period_after_is_refused(contract, monkeypatch, clean_qa_history):
    """Criterion 9, through the one placer's plan: 2026-Q4 is refused,
    naming 2026-Q3 and its command."""
    from qa_tools.common import decision_log, placing, supply_holds

    got = TestASupplyInTheDoublyFedRoundIsHeldForAPerson._held(contract, monkeypatch)
    conn = clean_qa_history
    conn.execute("DELETE FROM qa.hold WHERE supply_id = 'cp-clients@aug'")
    supply_holds.raise_hold(conn, dataset_id="cp-clients", supply_id="cp-clients@aug",
                            kind=supply_holds.ASSIGNMENT_RULE,
                            reason=supply_holds.reason_for(got), raised_by="the filing rule")
    with pytest.raises(decision_log.DecisionRefused, match="placed only into 2026-Q3"):
        placing.plan(conn, dataset_id="cp-clients", supply="cp-clients@aug",
                     to_period="2026-Q4")


def test_draft_correction_prints_a_rises_not_expected_entries(contract, monkeypatch):
    """Criterion 11: `mothman schedule draft-correction` drafts a rise
    complete, with the not_expected entries to paste."""
    from click.testing import CliRunner

    from cli import schedule as schedule_cli
    from qa_tools.common import correction_trial

    _, cal_path = contract(0, 1)
    cal = yaml.safe_load(cal_path.read_text())
    asset = yaml.safe_load((cal_path.parent / "data-asset.yaml").read_text())
    monkeypatch.setattr(correction_trial, "working", lambda: (cal, asset))
    monkeypatch.setattr(correction_trial, "draft", lambda *a, **k: [])
    assert correction_trial.rise_entries(), "the working copy's rise was not found"
    got = CliRunner().invoke(schedule_cli.schedule_group, ["draft-correction"])
    assert got.exit_code == 0, got.output
    assert "not_expected:" in got.output and '"2026-Q3"' in got.output
    assert NOT_EXPECTED_PLACEHOLDER in got.output


def test_a_slot_across_a_fall_closes_when_the_next_rounds_window_opens(contract):
    """Criterion 4: 2026-Q3's slot (the 1 May round) closes at the 1 August
    round's claim-opening instant, though that round opens no slot."""
    _, cal_path = contract(1, 0)
    agr = agreement.load(cal_path)
    q3 = next(s for s in slots.slots_for_dataset("cp-clients", until=date(2027, 3, 1),
                                                  agreement=agr) if s.name == "2026-Q3")
    assert q3.closes_at == slots.slot_instants("cp-clients", date(2026, 8, 1),
                                               agr).claim_opens_at
