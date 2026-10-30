"""A collection's files go into the period N after the round they arrive in
(REQ-PIPE-320, REQ-PIPE-321).

Each test loads a copy of the real contract/calendar.yaml with Child
Protection's files_go_to_period set as the test needs, and passes it to the
functions under test as their agreement value - the real file and every cache
are untouched. The quarterly calendar's rounds are dated 1 February, 1 May,
1 August and 1 November, and its periods are named for the round's quarter
(2026-Q1 is dated 2026-02-01), so a Child Protection file arriving on the
1 February 2026 round at files_go_to_period 1 fills 2026-Q2 (criterion 9's
worked example).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from qa_tools.common import agreement, asset_time, assignment, schedule, slots

REAL = Path(__file__).resolve().parent.parent / "contract" / "calendar.yaml"


def _offset_version(effective_from, value, author="a test"):
    return {"effective_from": effective_from, "value": value,
            "changelog": [{"date": "2026-10-30", "author": author, "change": "a test's value"}]}


def _doc(cp=1, ed=0, br=0, cp_versions=None):
    doc = yaml.safe_load(REAL.read_text())
    for c in doc["collections"]:
        value = {"child-protection": cp, "emergency-department": ed,
                 "civil-registration": br}.get(c["id"])
        c.pop("files_go_to_period", None)
        if c["id"] == "child-protection" and cp_versions is not None:
            c["files_go_to_period"] = {"versions": cp_versions}
        elif value is not None:
            c["files_go_to_period"] = {"versions": [_offset_version("2000-01-01", value)]}
    return doc


def _load(tmp_path, doc):
    path = tmp_path / "calendar.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return agreement.load(path)


def _perth(*args):
    return datetime(*args, tzinfo=asset_time.zone_on(date(*args[:3])))


def _slots(dataset_id, agr, until=date(2027, 1, 1)):
    return slots.slots_for_dataset(dataset_id, until=until, agreement=agr)


def _slot(dataset_id, name, agr):
    return next(s for s in _slots(dataset_id, agr) if s.name == name)


@pytest.fixture
def at_one(tmp_path):
    return _load(tmp_path, _doc(cp=1))


class TestTheValueIsReadFromTheCollection:
    """REQ-PIPE-320 criteria 1 and 2."""

    def test_child_protection_resolves_one_on_a_round(self, at_one):
        assert at_one.files_go_to_period("child-protection", date(2026, 2, 1)) == 1

    def test_emergency_department_resolves_zero(self, at_one):
        assert at_one.files_go_to_period("emergency-department", date(2026, 2, 1)) == 0

    def test_a_dataset_resolves_its_collections_value(self, at_one):
        assert at_one.files_go_to_period_for("cp-clients", date(2026, 2, 1)) == 1
        assert at_one.files_go_to_period_for("ed-presentations", date(2026, 2, 1)) == 0

    def test_the_value_is_resolved_on_the_round_date(self, tmp_path):
        agr = _load(tmp_path, _doc(cp_versions=[_offset_version("2000-01-01", 0),
                                                _offset_version("2026-05-01", 1)]))
        assert agr.files_go_to_period("child-protection", date(2026, 2, 1)) == 0
        assert agr.files_go_to_period("child-protection", date(2026, 5, 1)) == 1


class TestARoundsSlotFillsThePeriodAfterIt:
    """REQ-PIPE-321 criteria 1 and 9."""

    def test_the_february_round_opens_2026_q2s_slot_due_on_1_february(self, at_one):
        slot = _slot("cp-clients", "2026-Q2", at_one)
        assert slot.round_date == date(2026, 2, 1)
        assert slot.due_at == _perth(2026, 2, 1, 9, 0)

    def test_a_supply_at_its_due_time_on_1_february_fills_2026_q2_on_time(self, at_one):
        at = _perth(2026, 2, 1, 9, 0)
        chosen = assignment.open_slot(_slots("cp-clients", at_one), at)
        assert chosen.name == "2026-Q2"
        assert at <= chosen.late_after

    def test_one_received_2_may_fills_2026_q3_late(self, at_one):
        at = _perth(2026, 5, 2, 9, 0)
        chosen = assignment.open_slot(_slots("cp-clients", at_one), at)
        assert chosen.name == "2026-Q3"
        assert at > chosen.late_after

    def test_2026_q2_closes_when_the_1_may_rounds_claim_window_opens(self, at_one):
        q2, q3 = _slot("cp-clients", "2026-Q2", at_one), _slot("cp-clients", "2026-Q3", at_one)
        assert q2.closes_at == q3.claim_opens_at
        assert q3.claim_opens_at == _perth(2026, 5, 1, 9, 0) - timedelta(days=14)

    def test_before_the_february_window_opens_a_supply_files_to_2026_q1(self, at_one):
        at = _perth(2026, 1, 10, 9, 0)
        chosen = assignment.open_slot(_slots("cp-clients", at_one), at)
        assert chosen.name == "2026-Q1"
        assert chosen.round_date == date(2025, 11, 1)

    def test_an_expected_time_change_from_1_may_moves_q3_and_not_q2(self, tmp_path):
        doc = _doc(cp=1)
        cp = next(c for c in doc["collections"] if c["id"] == "child-protection")
        versions = cp["participation_defaults"]["versions"]
        versions.append({**versions[-1], "effective_from": "2026-05-01", "expected_time": "14:00",
                         "changelog": [{"date": "2026-10-30", "author": "a test",
                                        "change": "later due time"}]})
        agr = _load(tmp_path, doc)
        assert _slot("cp-clients", "2026-Q2", agr).due_at == _perth(2026, 2, 1, 9, 0)
        assert _slot("cp-clients", "2026-Q3", agr).due_at == _perth(2026, 5, 1, 14, 0)

    def test_february_and_august_rounds_owe_q2_and_q4(self, at_one):
        names = {s.name for s in _slots("cp-case-workers", at_one) if s.name.startswith("2026")}
        assert names == {"2026-Q2", "2026-Q4"}

    def test_the_period_before_the_first_round_fills_is_not_yet_owing(self, at_one):
        first = _slots("cp-clients", at_one)[0]
        # The 2015-Q1 round is dated 2 February 2015 (a corrected date).
        assert first.round_date == schedule.date_of("2015-Q1", "cp-clients")
        assert first.name == "2015-Q2"
        owed = [p.name for p in schedule.periods_for_dataset("cp-clients", agreement=at_one)]
        assert "2015-Q1" not in owed


class TestTwoCollectionsReceivingOnOneDay:
    """REQ-PIPE-321 criterion 10."""

    def test_they_file_into_consecutive_periods(self, at_one):
        at = _perth(2026, 2, 1, 9, 0)
        cp = assignment.open_slot(_slots("cp-clients", at_one), at)
        ed = assignment.open_slot(_slots("ed-presentations", at_one), at)
        assert (ed.name, cp.name) == ("2026-Q1", "2026-Q2")

    def test_each_period_still_names_one_date_and_one_schema(self, at_one):
        cp = _slot("cp-clients", "2026-Q2", at_one).period
        ed = _slot("ed-presentations", "2026-Q2", at_one).period
        assert cp == ed
        assert schedule.schema_name(cp) == schedule.schema_name(ed) == "period_2026_q2"


class TestAtZeroNothingMoves:
    """REQ-PIPE-321 NFR 'identical at 0': every slot of a collection at 0
    is the slot it was before the key existed."""

    def test_every_slot_at_zero_matches_the_real_agreement(self, tmp_path):
        agr = _load(tmp_path, _doc(cp=0))
        for dataset_id in ("cp-clients", "cp-case-workers", "ed-presentations"):
            new = _slots(dataset_id, agr)
            assert new
            assert all(s.round_date == s.period.date for s in new)


class TestATurnedOffGapIsJudgedOnTheRound:
    """REQ-PIPE-321 criterion 2: a period is in a turned-off gap when the
    ROUND that fills it falls in the gap - never on the period's own date.
    Found 2026-10-30: a parked move into 2024-Q1 (filled by the 1 November
    2023 round, inside an off-from-30-September, on-from-1-January gap) was
    read as owed because 2024-Q1's own date, 1 February 2024, is after the
    gap ends."""

    def test_the_period_a_gap_round_fills_is_in_the_gap(self, tmp_path):
        from qa_tools.common import turned_off

        doc = _doc(cp=1)
        clients = next(d for d in doc["datasets"] if d["id"] == "cp-clients")
        versions = clients["participation"]["versions"]
        first = versions[-1]
        versions.append({**{k: v for k, v in first.items() if k != "changelog"},
                         "effective_from": "2024-01-01",
                         "changelog": [{"date": "2026-10-30", "author": "a test",
                                        "change": "back on"}]})
        first.update(effective_to="2023-09-30", turned_off_reason="supplier paused")
        agr = _load(tmp_path, doc)
        assert turned_off.gap_for_period("cp-clients", "2024-Q1", agr) is not None
        assert turned_off.gap_for_period("cp-clients", "2024-Q2", agr) is None
        assert turned_off.gap_for_period("cp-clients", "2023-Q4", agr) is None
