"""The drift and volume reference says what it skipped (REQ-QAC-108
criteria 2, 5 and 8 to 17, amended 2026-10-04).

Against a real database and cp-carers' real quarterly schedule, in 2027
so no other test's promotions are in the way. Periods: 2027-Q1 due
1 February, 2027-Q2 due 1 May, 2027-Q3 due 1 August - each with eight
hours' grace.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import decision_log, drift_reference, supply_db

DS = "cp-carers"
PERTH = timezone(timedelta(hours=8))
AFTER_Q2_DUE = datetime(2027, 6, 1, 9, tzinfo=PERTH)
BEFORE_Q2_DUE = datetime(2027, 4, 25, 9, tzinfo=PERTH)


def _decide(conn, action, slot, ds=DS, **kw):
    supply = f"{ds}@t{uuid.uuid4().hex[:12]}"
    with decision_log.apply_decision(conn, decision_log.Decision(
            agency_id="child-protection-family-support", collection_id="child-protection",
            dataset_id=ds, action=action, supply=supply, actor="t@example.com",
            actor_kind=decision_log.PERSON, effective_at="2027-01-01T00:00:00+08:00",
            to_slot=slot, **kw)):
        pass


#: ONE DATASET PER TEST - qa.decision is append-only, so a test cannot
#: clear what an earlier one promoted. All five are quarterly.
OWN = {"measured": "cp-carers", "gap": "cp-clients", "not_due": "cp-placements",
       "dealt": "cp-investigations", "no_ref": "cp-notifications"}


def _conn_for(ds):
    from qa_tools.common import qa_store

    c = supply_db.connect(label="test-drift-gap")
    qa_store.ensure_schema(c)
    if c.execute("SELECT 1 FROM qa.decision WHERE dataset_id = ? AND to_slot LIKE ?",
                 [ds, "2027-%"]).fetchall():
        c.close()
        pytest.skip(f"this worker's database already holds 2027 decisions for {ds}")
    return c


class TestTheGap:
    def test_a_promoted_previous_period_is_measured_unflagged(self, supply_dsn):
        ds = OWN["measured"]
        conn = _conn_for(ds)
        _decide(conn, decision_log.PROMOTE, "2027-Q2", ds)
        got = drift_reference.assess(conn, ds, "2027-Q3", AFTER_Q2_DUE)
        assert got.kind == drift_reference.MEASURED and got.reference.period == "2027-Q2"

    def test_an_owed_overdue_period_with_nothing_accepted_is_a_gap(self, supply_dsn):
        """Criterion 8, with its own example wording."""
        ds = OWN["gap"]
        conn = _conn_for(ds)
        _decide(conn, decision_log.PROMOTE, "2027-Q1", ds)
        got = drift_reference.assess(conn, ds, "2027-Q3", AFTER_Q2_DUE)
        assert got.kind == drift_reference.GAP
        assert got.reference.period == "2027-Q1" and got.gap == ("2027-Q2",)
        assert got.reason == "compared with 2027-Q1, not 2027-Q2: 2027-Q2 has no accepted supply"

    def test_a_period_not_yet_overdue_is_not_a_gap(self, supply_dsn):
        """Criterion 11."""
        ds = OWN["not_due"]
        conn = _conn_for(ds)
        _decide(conn, decision_log.PROMOTE, "2027-Q1", ds)
        got = drift_reference.assess(conn, ds, "2027-Q3", BEFORE_Q2_DUE)
        assert got.kind == drift_reference.MEASURED and got.reference.period == "2027-Q1"

    def test_a_period_a_person_dealt_with_is_said_but_not_red(self, supply_dsn):
        """Criterion 17: substituted."""
        ds = OWN["dealt"]
        conn = _conn_for(ds)
        _decide(conn, decision_log.PROMOTE, "2027-Q1", ds)
        _decide(conn, decision_log.SUBSTITUTE, "2027-Q2", ds, stands_on="2027-Q1")
        got = drift_reference.assess(conn, ds, "2027-Q3", AFTER_Q2_DUE)
        assert got.kind == drift_reference.MEASURED and got.dealt_with == ("2027-Q2",)
        assert "compared with 2027-Q1, not 2027-Q2" in got.reason

    def test_no_reference_with_owed_periods_is_red_not_no_data(self, supply_dsn):
        """Criterion 9 - the owed periods are named. (Only where this
        worker's database has nothing promoted for the dataset before 2027.)"""
        ds = OWN["no_ref"]
        conn = _conn_for(ds)
        got = drift_reference.assess(conn, ds, "2027-Q3", AFTER_Q2_DUE)
        assert got.kind in (drift_reference.NO_REFERENCE_OWED, drift_reference.GAP)
        assert "2027-Q2" in got.gap and "2027-Q2" in got.reason


class TestJudging:
    RESULTS = [{"dataset_id": DS, "check_id": "x", "status": "pass", "metric_value": 0.01}]

    def _results(self):
        return [dict(r) for r in self.RESULTS]

    def test_a_gap_is_one_red_result_keeping_the_measurement(self):
        """Criteria 13 and 14."""
        a = drift_reference.Assessment(
            kind=drift_reference.GAP, dataset_id=DS,
            reference=drift_reference.Reference(DS, "2027-Q1", "s"), gap=("2027-Q2",))
        (r,) = drift_reference.judge(self._results(), a)
        assert r["status"] == "fail" and r["measured_status"] == "pass"
        assert r["metric_value"] == 0.01 and r["reference_period"] == "2027-Q1"
        assert "has no accepted supply" in r["reference_reason"]

    def test_no_reference_owed_is_red_not_evaluated_with_no_metric(self):
        """Criterion 9: under its own tool, no metric, never no-data."""
        a = drift_reference.Assessment(kind=drift_reference.NO_REFERENCE_OWED,
                                       dataset_id=DS, gap=("2027-Q1",))
        (r,) = drift_reference.judge(self._results(), a)
        assert r["status"] == "fail" and r["metric_value"] is None
        assert r["reference_not_evaluated"] is True

    def test_a_new_dataset_keeps_its_no_data(self):
        """Criterion 10."""
        a = drift_reference.Assessment(kind=drift_reference.NO_REFERENCE_NEW, dataset_id=DS)
        results = [{"dataset_id": DS, "check_id": "x", "status": "nodata", "metric_value": None}]
        (r,) = drift_reference.judge(results, a)
        assert r["status"] == "nodata" and "nothing to compare" in r["reference_reason"]

    def test_another_datasets_result_is_left_alone(self):
        a = drift_reference.Assessment(kind=drift_reference.NO_REFERENCE_OWED,
                                       dataset_id="cp-clients", gap=("2027-Q1",))
        (r,) = drift_reference.judge(self._results(), a)
        assert r["status"] == "pass"


class TestTheTerminalSaysItApart:
    """Criterion 14, terminal half."""

    def test_a_gap_red_shows_the_measured_verdict(self):
        from cli import common

        got = common.reference_suffix({"status": "fail", "measured_status": "pass",
                                       "reference_reason": "compared with 2027-Q1, not 2027-Q2: "
                                                           "2027-Q2 has no accepted supply"})
        assert "measured pass" in got and "no accepted supply" in got

    def test_a_measured_red_is_not_excused(self):
        from cli import common

        assert common.reference_suffix({"status": "fail", "measured_status": "fail",
                                        "reference_reason": "x"}) == ""

    def test_an_ordinary_result_gets_nothing(self):
        from cli import common

        assert common.reference_suffix({"status": "pass"}) == ""


def test_a_long_gap_names_the_five_most_recent_and_counts_the_rest():
    a = drift_reference.Assessment(kind=drift_reference.NO_REFERENCE_OWED, dataset_id=DS,
                                   gap=tuple(f"2026-08-{d:02d}" for d in range(1, 21)))
    assert a.reason.endswith("2026-08-16, 2026-08-17, 2026-08-18, 2026-08-19, 2026-08-20 "
                             "and 15 earlier owed one")
