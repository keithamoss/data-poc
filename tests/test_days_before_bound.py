"""days before stays inside one round (REQ-PIPE-324).

On an authored calendar a due date may not reach back past the round
before it - a later period is said with the collection's files_go_to_period
instead; on a cadence-rule calendar 1 is the most, and nothing else is
pointed to. Each test copies the real contract and sets one dataset's
days before; the real file is untouched.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from qa_tools.common.validate_schedule import Source, validate

REAL = Path(__file__).resolve().parent.parent / "contract"


@pytest.fixture
def gate(tmp_path):
    contract = tmp_path / "contract"
    shutil.copytree(REAL, contract)
    cal_path = contract / "calendar.yaml"

    def run(dataset_id, days):
        doc = yaml.safe_load(cal_path.read_text())
        entry = next(d for d in doc["datasets"] if d["id"] == dataset_id)
        for v in entry["participation"]["versions"]:
            v["days_before"] = days
        cal_path.write_text(yaml.safe_dump(doc, sort_keys=False))
        found = [e for e in validate(Source(contract / "data-asset.yaml", contract))
                 if "days before" in f"{e.problem} {e.fix}" or "days_before" in e.problem]
        return "\n".join(f"{e.scope} | {e.problem} | {e.fix}" for e in found)
    return run


class TestAnAuthoredCalendar:
    """Criterion 1: on Child Protection's calendar the 1 May 2015 round is
    88 days after the corrected 2 February 2015 one, and the 1 November 2015
    round 82 after the corrected 11 August - the shortest."""

    def test_a_due_date_inside_every_round_is_accepted(self, gate):
        assert gate("cp-clients", 80) == ""

    def test_one_reaching_back_past_the_previous_round_is_refused(self, gate):
        text = gate("cp-clients", 90)
        assert "cp-clients" in text and "1 May" in text
        assert "at most 88" in text
        assert "files_go_to_period" in text and "every dataset of the collection" in text


    def test_a_round_the_dataset_does_not_take_part_in_is_not_checked(self, gate):
        """Critic finding 4: cp-case-workers supplies in the February and
        August rounds only, so the 1 November 2015 round (82 days after the
        August one) is not its round, and 85 is accepted. Each of its own
        rounds is still checked against the calendar round just before it -
        here 93 and 102 days (PROVISIONAL reading of 'the round before')."""
        assert gate("cp-case-workers", 85) == ""
        assert "at most 93" in gate("cp-case-workers", 95)


class TestACadenceRuleCalendar:
    """Criteria 2 and 4."""

    def test_the_evening_before_is_accepted(self, gate):
        assert gate("birth-registrations", 1) == ""

    def test_two_is_refused_saying_one_is_the_most_and_pointing_nowhere_else(self, gate):
        text = gate("birth-registrations", 2)
        assert "birth-registrations" in text and "1 is the most" in text
        assert "files_go_to_period" not in text
