"""The build's half of REQ-DASH-204: which table a not-evaluated result could
not read, from structured fields alone, and the lines a supply's page shows
for it as at each date (pipeline/cross_table_notices.py).

In memory: cards in the shape build_one_table makes them, and a decision log
in the shape read_log reads it - so each rule is asserted on its own. The
page's wording and the real chain are tests/test_dashboard_e2e.py's
TestAnotherTableCouldNotBeRead.
"""
from __future__ import annotations

from pipeline import cross_table_notices as ctn
from qa_tools.common import root_cause

CHECK = "data-asset-1.child-protection-family-support.child-protection.cp-notifications"
REF_DBT = f"{CHECK}.cp_client_id.relationships_dbt"
REF_SODA = f"{CHECK}.cp_client_id.relationships_soda"
N2 = "cp-notifications@202411031000000800"
C2 = "cp-clients@202411031000000800"
C3 = "cp-clients@202411071000000800"


class TestBlockingTables:

    def test_each_table_carries_its_own_code(self):
        record = {"unrunnable_table": "cp_clients", "unrunnable_tables": ["cp_clients", "cp_carers"],
                  "unrunnable_code": "contested",
                  "unrunnable_codes": {"cp_clients": "contested", "cp_carers": "not-yet-due"}}
        assert root_cause.blocking_tables(record) == {"cp_clients": "contested",
                                                      "cp_carers": "not-yet-due"}

    def test_a_record_written_before_per_table_codes_reads_its_single_code(self):
        """Criterion 10: 'records written before this change SHALL be read by
        their single unrunnable_code'."""
        record = {"unrunnable_table": "cp_clients", "unrunnable_code": "past-due"}
        assert root_cause.blocking_tables(record) == {"cp_clients": "past-due"}

    def test_a_held_supply_record_names_its_held_tables(self):
        record = {"held_tables": ["cp_clients"], "held_reason": "held"}
        assert root_cause.blocking_tables(record) == {"cp_clients": "held"}

    def test_a_verdict_names_nothing(self):
        """Never from prose: a reason's text alone names no table."""
        assert root_cause.blocking_tables({"status": "fail",
                                           "unrunnable_reason": "cp_clients was held"}) == {}


def _card(check_id, entries, counted):
    return {"check_id": check_id, "history": entries, "counted": {N2: counted}}


def _not_evaluated(rank, code="held-back-with-its-package", **extra):
    return {"rank": rank, "supply_id": N2, "status": "red", "not_evaluated": "could not run",
            "unreadable": {"cp_clients": code}, "recorded_at": "2024-11-03T10:30:00+08:00",
            **extra}


def _log(**kw) -> ctn.Log:
    log = ctn.Log()
    log.gate = {N2: [("2024-11-03", "promotion-withheld", C2,
                      {"by": C2, "came": "package-mate",
                       "by_received": "2024-11-03T02:00:00+00:00"}, None)]}
    log.receipts = {C2: "2024-11-03T02:00:00+00:00", C3: "2024-11-07T02:00:00+00:00"}
    for key, value in kw.items():
        setattr(log, key, value)
    return log


def _points(cards, log, own=()):
    return ctn.no_promoted("cp-notifications", "cp_notifications", cards, list(own),
                           {N2: "2024-Q4"}, log)[N2]


class TestTheLines:

    def test_one_line_per_table_however_many_checks_read_it(self):
        cards = [_card(c, [_not_evaluated(8)], [{"on": "2024-11-03", "rank": 8, "reason": None}])
                 for c in (REF_DBT, REF_SODA)]
        (point,) = _points(cards, _log())
        (line,) = point["lines"]
        assert line["datasetId"] == "cp-clients" and line["n"] == 2
        assert line["form"] == ctn.PACKAGE and line["partner"] == C2
        assert point["ownRed"] is False

    def test_the_partner_turned_down_and_replaced_as_at_each_date(self):
        cards = [_card(REF_DBT, [_not_evaluated(8)], [{"on": "2024-11-03", "rank": 8,
                                                        "reason": None}])]
        down = _points(cards, _log(states={C2: [("2024-11-05", "reject", None)]}))
        assert [(p["on"], p["lines"][0]["form"]) for p in down] == [
            ("2024-11-03", ctn.PACKAGE), ("2024-11-05", ctn.TURNED_DOWN)]
        replaced = _points(cards, _log(states={C2: [("2024-11-07", "supersede", C3)]}))
        assert replaced[-1]["lines"][0]["form"] == ctn.REPLACED
        assert replaced[-1]["lines"][0]["replacedReceived"] == "2024-11-07T02:00:00+00:00"

    def test_a_red_check_of_its_own_is_said(self):
        """Criterion 3: the page leaves 'not a fault' out of a supply with a
        red check of its own."""
        cards = [_card(REF_DBT, [_not_evaluated(8)], [{"on": "2024-11-03", "rank": 8,
                                                        "reason": None}])]
        own = [{"check_id": f"{CHECK}.notification_id.not_null_dbt",
                "history": [{"rank": 7, "supply_id": N2, "status": "red",
                             "recorded_at": "2024-11-03T10:00:00+08:00"}]}]
        (point,) = _points(cards, _log(), own)
        assert point["ownRed"] is True

    def test_a_partner_not_due_is_overdue_from_its_due_day(self):
        """Criterion 16: a not-yet-due partner's slot has no item of its own
        once it falls due - from the due day, a change point of its own."""
        entry = _not_evaluated(8, code="not-yet-due", due_at="2024-11-01T09:00:00+08:00")
        cards = [_card(REF_DBT, [entry], [{"on": "2024-10-30", "rank": 8, "reason": None}])]
        log = _log(gate={})
        points = _points(cards, log)
        assert [(p["on"], p["lines"][0]["noItem"]) for p in points] == [
            ("2024-10-30", False), ("2024-11-01", True)]
        assert points[0]["lines"][0]["dueAt"] == "2024-11-01T09:00:00+08:00"

    def test_an_owed_re_check_names_the_promotion(self):
        cards = [_card(REF_DBT, [], [{"on": "2024-08-06", "rank": None, "reason": "recheck-owed",
                                       "owedBy": 11}])]
        log = _log(gate={}, decisions={11: ("cp-clients", C2, "2024-08-06T02:00:00+00:00")})
        (point,) = _points(cards, log)
        assert point["lines"] == [{
            "datasetId": "cp-clients", "name": "Client Register",
            "agencyId": "child-protection-family-support", "collectionId": "child-protection",
            "period": "2024-Q4", "n": 1, "form": ctn.OWED,
            "promotedAt": "2024-08-06T02:00:00+00:00", "noItem": False}]

    def test_no_line_once_re_evaluated(self):
        """Criterion 8: once the counted result is a real verdict, no line."""
        cards = [_card(REF_DBT, [_not_evaluated(8), {"rank": 9, "supply_id": N2, "status": "green"}],
                       [{"on": "2024-11-03", "rank": 8, "reason": None},
                        {"on": "2024-11-07", "rank": 9, "reason": None}])]
        points = _points(cards, _log())
        assert [(p["on"], len(p["lines"])) for p in points] == [("2024-11-03", 1),
                                                                ("2024-11-07", 0)]
