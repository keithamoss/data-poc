"""REQ-DASH-126's data and REQ-DASH-127's: what the build embeds so the page
can label a red promoted supply, and give every supply its outcome."""
from __future__ import annotations

import test_supersession as _base
from pipeline import red_promoted, slot_timeline
from qa_tools.common import decision_log as dl, promotion, supersession, supply_status
from test_supersession import DS, REAL_PERSON, WHEN, _filed

conn = _base.conn
period = _base.period

AG, COL = "child-protection-family-support", "child-protection"


def _promote(conn, supply, table, period, *, status="green", kind=dl.RULE):
    promotion.promote(conn, agency_id=AG, collection_id=COL, dataset_id=DS, supply=supply,
                      period=period, physical_tables=[table],
                      actor="promotion rule" if kind == dl.RULE else REAL_PERSON,
                      actor_kind=kind, effective_at=WHEN, reason="because", status=status)


class TestEverySupplysOutcome:
    """REQ-DASH-127 criteria 1, 3 and 4."""

    def test_a_superseded_supply_names_what_superseded_it_and_who(self, conn, period):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period)
        b, b_table = _filed(conn, period, "2026-06-01T01:00:00+00:00")
        _promote(conn, b, b_table, period, kind=dl.PERSON)
        assert supersession.is_superseded(conn, DS, a)
        entries = slot_timeline.supply_states(DS, conn=conn)[a]
        assert [e["action"] for e in entries] == ["promote", "supersede"]
        assert entries[-1]["supersededBy"] == b and entries[-1]["by"] == dl.PERSON


class TestRedPromoted:
    """REQ-DASH-126: the status a promoted supply went in on, and after each
    run that read it, with what caused that run."""

    def test_the_timeline(self, conn, period, monkeypatch):
        a, a_table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        _promote(conn, a, a_table, period, status="green")
        # ONLY THIS TEST'S SUPPLY has a run: other modules on the same worker
        # promote cp-carers supplies too, and mapping them all to one run let
        # whichever came last overwrite this one's entry.
        monkeypatch.setattr(slot_timeline, "_run_for", lambda c, d, s: "run-a" if s == a else None)
        monkeypatch.setattr(supply_status, "runs_about", lambda c, d, s: ["arrival", "later"])
        results = {"arrival": [{"dataset_id": DS, "check_id": "x", "status": "pass"}],
                   "later": [{"dataset_id": DS, "check_id": "x", "status": "fail"}]}
        monkeypatch.setattr(red_promoted, "_results_of", lambda c, k: results[k])
        causes = {"arrival": ("2026-05-01T01:00:00+00:00", "the arrival of Carers"),
                  "later": ("2026-06-01T01:00:00+00:00", "the promote of Client Register")}
        monkeypatch.setattr(red_promoted, "_cause", lambda c, k: causes[k])
        got = red_promoted.for_dataset(DS, conn=conn)["run-a"]
        assert got["promotedOn"] == "green"
        assert [(t["status"], t["cause"]) for t in got["timeline"]] == [
            ("green", "the arrival of Carers"), ("red", "the promote of Client Register")]
