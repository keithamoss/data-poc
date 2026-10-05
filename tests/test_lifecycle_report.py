"""A kept terminal run says what the lifecycle decided about each arrival,
and on what grounds (REQ-TEST-150)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from cli import common, lifecycle_report as lr
from qa_tools.common import arrival_lifecycle, supply_holds

WHEN = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)


def _arrival(dataset="cp-clients", table="cp_clients", files=("cp_clients.csv",)):
    return SimpleNamespace(run_id=f"{table}__1", received_at=WHEN,
                           files_by_dataset={dataset: tuple(files)})


class _Conn:
    """Answers each query from what the test says was recorded."""

    def __init__(self, *, filing=None, gate=None, inherits=()):
        self.filing, self.gate, self.inherits = filing, gate, list(inherits)
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        if "filing_current" in sql:
            rows = [self.filing] if self.filing else []
        elif "action IN" in sql:
            rows = [self.gate] if self.gate else []
        else:
            rows = self.inherits
        return SimpleNamespace(fetchall=lambda: rows)


class TestEachOutcomeIsSaid:
    """Criteria 1, 2, 3, 4, 5 and 6."""

    def test_filed_with_its_classification(self):
        o = lr.outcome_of(_Conn(filing=("2026-Q1", "late", ["2026-Q1"]),
                                gate=("promote", "green", "auto-promotion")), _arrival())
        assert o.filed == "recognised as cp-clients; filed to 2026-Q1, late"

    def test_the_gate_names_the_rule_and_its_recorded_reason(self):
        o = lr.outcome_of(_Conn(filing=("2026-Q1", "on_time", []),
                                gate=("promotion-refused", "status is red", "auto-promotion")),
                          _arrival())
        assert o.gate == "left for a person by the rule (auto-promotion), not by you - status is red"

    def test_no_gate_outcome_says_it_is_owed(self):
        o = lr.outcome_of(_Conn(filing=("2026-Q1", "on_time", [])), _arrival())
        assert "owed to the next processing pass" in o.gate

    def test_a_held_arrival_names_each_slot_and_says_nothing_ran(self, monkeypatch):
        monkeypatch.setattr(supply_holds, "hold_on", lambda conn, ds, s: SimpleNamespace(
            reason={"unavailable": [["2026-Q1", "closed"], ["2026-Q2", "not yet open"]]}))
        o = lr.outcome_of(_Conn(), _arrival())
        assert o.filed.endswith("filed to no period")
        assert o.extra[0] == ("held - 2026-Q1: closed; 2026-Q2: not yet open. "
                              "No check ran over it.")

    def test_a_contested_arrival_names_the_other_file(self):
        o = lr.outcome_of(_Conn(filing=("2026-Q1", "on_time", [])),
                          _arrival(files=("cp_clients.csv", "cp_clients_v2.csv")))
        assert any("cp_clients_v2.csv" in line and "contested" in line for line in o.extra)

    def test_an_inheritance_is_the_rules(self):
        o = lr.outcome_of(_Conn(filing=("2026-Q2", "on_time", []),
                                inherits=[("2026-Q2", "cp-clients@2026Q1")]),
                          _arrival(), since=WHEN)
        assert any("the rule inherited cp-clients@2026Q1's supply into 2026-Q2" in line
                   for line in o.extra)

    def test_it_reads_only_recorded_rows(self):
        """Criterion 9: three reads of the record - the filing, the gate's
        entry, the inheritances - and nothing worked out again."""
        conn = _Conn(filing=("2026-Q1", "on_time", []), gate=("promote", "ok", "r"))
        lr.outcome_of(conn, _arrival(), since=WHEN)
        assert len(conn.sql) == 3


class TestOneOutcomeSharedIsSaidOnce:
    """Criterion 8."""

    def test_six_arrivals_one_line(self):
        outs = [lr.Outcome(f"t{i}__1", f"cp-{i}", f"recognised as cp-{i}; filed to 2026-Q1, on time",
                           "promoted by the rule (r), not by you - ok") for i in range(6)]
        lines = list(lr._grouped(outs))
        assert ("recognised as its dataset; filed to 2026-Q1, on time", "6 arrivals") in lines
        assert len(lines) == 2

    def test_one_that_differs_gets_its_own_line(self):
        outs = [lr.Outcome(f"t{i}__1", f"cp-{i}", "filed", "promoted") for i in range(3)]
        outs.append(lr.Outcome("t9__1", "cp-9", "filed", "left for a person"))
        lines = list(lr._grouped(outs))
        assert ("left for a person", "t9__1") in lines and ("promoted", "3 arrivals") in lines


class TestAFailedStageIsNamed:
    """Criterion 7."""

    def test_the_arrival_the_stage_and_what_completed(self):
        def boom(*a, **k):
            raise ValueError("dbt fell over")
        steps = arrival_lifecycle.Steps(
            file_and_overlay=lambda arrival, among: None,
            entry_for=lambda arrival: {}, run_one=boom,
            promote_after=lambda *a: None)
        with pytest.raises(arrival_lifecycle.StageFailed) as caught:
            arrival_lifecycle.process(_arrival(), steps=steps, among=[], run_timestamp="t",
                                      run_by="me")
        exc = caught.value
        assert (exc.run_id, exc.stage, exc.completed) == (
            "cp_clients__1", arrival_lifecycle.CHECKING, (arrival_lifecycle.FILING,))

    def test_the_terminal_never_says_kept(self, capsys):
        lr.stage_failure(arrival_lifecycle.StageFailed(
            "cp_clients__1", arrival_lifecycle.GATING, ("filing and overlay", "checks"),
            RuntimeError("x")))
        out = capsys.readouterr().out
        assert "STOPPED" in out and "promotion gate" in out and "Kept." not in out


class TestATrialSaysWhatRecognitionWouldDo:
    """Criterion 10."""

    def test_each_file_and_the_trial_goes_on(self, capsys):
        filed = common._as_trial(["/x/cp_clients.csv", "/x/notes.pdf"])
        out = capsys.readouterr().out
        assert "cp_clients.csv: would be cp-clients" in out
        assert "notes.pdf: would be claimed by no dataset" in out
        assert filed.run_id and not filed.delivery_name


class TestSeveralArrivalsAreReportedCompactly:
    """Criterion 11."""

    def _results(self):
        return [{"dataset_id": "cp-clients", "status": "pass", "check_id": "a"},
                {"dataset_id": "cp-clients", "status": "pass", "check_id": "b"},
                {"dataset_id": "cp-carers", "status": "fail", "check_id": "c"}]

    def test_failing_in_full_passing_counted(self, monkeypatch, capsys):
        shown = []
        monkeypatch.setattr(common.hand_filing, "arrivals_of",
                            lambda filed, c, p: [_arrival(), _arrival("cp-carers", "cp_carers")])
        monkeypatch.setattr(lr, "report", lambda found, since=None: shown.append("summary"))
        filed = SimpleNamespace(run_id="cp_clients__1", delivery_name="d", received_at=WHEN)
        common.finish_kept(self._results(), filed, collection_id="child-protection",
                           run_id_prefix="cp_run_",
                           table=lambda rows, run_id: shown.append([r["check_id"] for r in rows])
                           or "")
        out = capsys.readouterr().out
        assert shown[0] == ["c"] and "cp-clients: 2 checks passed" in out
        assert shown[-1] == "summary", "it ends on the lifecycle summary"

    def test_all_checks_lists_every_one(self, monkeypatch):
        shown = []
        monkeypatch.setattr(common.hand_filing, "arrivals_of",
                            lambda filed, c, p: [_arrival(), _arrival("cp-carers", "cp_carers")])
        monkeypatch.setattr(lr, "report", lambda found, since=None: None)
        filed = SimpleNamespace(run_id="cp_clients__1", delivery_name="d", received_at=WHEN)
        common.finish_kept(self._results(), filed, collection_id="child-protection",
                           run_id_prefix="cp_run_", all_checks=True,
                           table=lambda rows, run_id: shown.append(len(rows)) or "")
        assert shown == [3]
