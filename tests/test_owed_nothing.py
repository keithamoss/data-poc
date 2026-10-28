"""Every period a dataset owes nothing in, and the delivery time in force on
each date, for the dashboard (REQ-DASH-182).

From configuration alone (criterion 5): the real committed agreement, or a
copy of it changed the way tests/test_turn_off.py changes one.
"""
from __future__ import annotations

from datetime import date

from pipeline import owed_nothing
from qa_tools.common import agreement
from tests.test_collection_defaults import _doc, _entry, _unshare, _versions
from tests.test_turn_off import _off_for_a_while


def _by_period(rows):
    return {r["period"]: r for r in rows}


class TestWhichPeriodsOweNothing:
    """Criteria 1, 2 and 6."""

    def test_a_partial_participant_owes_nothing_outside_its_months(self):
        rows = owed_nothing.for_dataset("cp-case-workers", until=date(2024, 12, 31))
        got = _by_period(rows)
        assert {"2023-Q2", "2023-Q4", "2024-Q2", "2024-Q4"} <= set(got)
        assert not {"2023-Q1", "2023-Q3", "2024-Q1", "2024-Q3"} & set(got)
        row = got["2024-Q2"]
        assert row["kind"] == owed_nothing.PARTICIPATION and row["months"] == [2, 8]
        assert row["date"] == "2024-05-01"
        assert "staffing register" in row["reason"]

    def test_nothing_after_the_date_asked_for(self):
        rows = owed_nothing.for_dataset("cp-case-workers", until=date(2024, 6, 30))
        assert max(r["date"] for r in rows) <= "2024-06-30"

    def test_a_dataset_owing_every_period_has_none(self):
        assert owed_nothing.for_dataset("cp-clients", until=date(2025, 12, 31)) == []

    def test_not_expected_carries_its_own_reason(self):
        doc = _unshare(_doc())
        _entry(doc, "cp-clients")["not_expected"] = [
            {"period": "2024-Q3", "reason": "system migration, agreed with the supplier"}]
        rows = owed_nothing.for_dataset("cp-clients", until=date(2024, 12, 31),
                                        agreement=agreement.from_doc(doc))
        (row,) = rows
        assert (row["period"], row["kind"]) == ("2024-Q3", owed_nothing.NOT_EXPECTED)
        assert row["reason"] == "system migration, agreed with the supplier"

    def test_a_turned_off_gap_is_its_own_kind(self):
        rows = owed_nothing.for_dataset("cp-clients", until=date(2025, 12, 31),
                                        agreement=agreement.from_doc(_off_for_a_while()))
        got = _by_period(rows)
        assert {"2025-Q2", "2025-Q3", "2025-Q4"} <= set(got)
        assert {r["kind"] for r in rows} == {owed_nothing.TURNED_OFF}
        assert got["2025-Q2"]["reason"] == "supplier paused"

    def test_nothing_before_the_first_participation_version(self):
        """Criterion 6: before a dataset owes anything, it is not yet owing,
        which is not an owed-nothing row."""
        doc = _unshare(_doc())
        _versions(doc, "cp-case-workers")[0]["effective_from"] = "2024-01-01"
        rows = owed_nothing.for_dataset("cp-case-workers", until=date(2024, 12, 31),
                                        agreement=agreement.from_doc(doc))
        assert rows and min(r["date"] for r in rows) >= "2024-01-01"


class TestTheDeliveryTimeInForce:
    """Criteria 3, 7, 8 and 11: one entry per participation version, each
    with the dataset's own months, resolved timing and reason."""

    def test_a_partial_participant_names_its_own_months_and_reason(self):
        got = owed_nothing.sla_timeline("cp-case-workers")
        # Two versions since REQ-GEN-207 grew the history back - to 2015 since
        # REQ-GEN-238 dropped 2013 and 2014.
        assert got["owesFrom"] == "2015-01-01"
        assert [v["from"] for v in got["versions"]] == ["2015-01-01", "2023-01-01"]
        version = got["versions"][-1]
        cadence = version["cadence"]
        assert cadence["anchor_months"] == [2, 8] and cadence["day_of_month"] == 1
        assert (cadence["expected_time"], cadence["latency_minutes"]) == ("09:00", 480)
        assert "staffing register" in version["reason"]

    def test_a_full_participant_carries_no_reason(self):
        versions = owed_nothing.sla_timeline("cp-clients")["versions"]
        assert versions and all(v["cadence"]["anchor_months"] == [2, 5, 8, 11]
                                and v["reason"] is None for v in versions)

    def test_a_daily_dataset_keeps_its_rule(self):
        versions = owed_nothing.sla_timeline("birth-registrations")["versions"]
        assert versions and all(v["cadence"]["type"] == "daily" for v in versions)

    def test_each_version_takes_its_own_values(self):
        doc = _unshare(_doc())
        first = _versions(doc, "cp-case-workers")[0]
        later = {**{k: v for k, v in first.items() if k != "changelog"},
                 "effective_from": "2025-01-01", "participates": "all", "reason": None,
                 "days_before": 1,
                 "changelog": [{"date": "2026-10-15", "author": "a test", "change": "c"}]}
        later.pop("reason")
        _versions(doc, "cp-case-workers").append(later)
        got = owed_nothing.sla_timeline("cp-case-workers", agreement.from_doc(doc))
        assert [v["from"] for v in got["versions"]] == ["2023-01-01", "2025-01-01"]
        newer = got["versions"][1]
        assert newer["cadence"]["anchor_months"] == [2, 5, 8, 11]
        assert newer["cadence"]["days_before"] == 1 and newer["reason"] is None
