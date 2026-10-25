"""The build's half of REQ-DASH-272 (pipeline/cross_table_grid.py): which cell
a cross-table result sits in on the page of the supply it is about, its note
and sentence, the awaiting line's warehouse clause and a joint promotion's
history row - each from structured fields as at an instant.

In memory: slot timelines and a decision log in the shapes the build reads.
The page is tests/test_dashboard_e2e.py's TestWarehouseAndStagingViews.
"""
from __future__ import annotations

from pipeline import cross_table_grid as g
from pipeline import cross_table_notices as ctn
from qa_tools.common import asset_time

P = "2024-Q3"
N1, N2 = "cp-notifications@202407251000000800", "cp-notifications@202408051000000800"
C1, C2 = "cp-clients@202407251000000800", "cp-clients@202408051000000800"
RECEIPTS = g.Receipts({N1: "2024-07-25T10:00:00+08:00", N2: "2024-08-05T10:00:00+08:00",
                       C1: "2024-07-25T10:00:00+08:00", C2: "2024-08-05T10:00:00+08:00"})


def _at(text):
    return asset_time.parse_instant(text, "test")


def _slots(**extra):
    timelines = {
        "cp-notifications": [{"at": "2024-07-25T10:30:00+08:00", "slot": P, "held_as": "promoted",
                              "holder": N1, "stands_on": None}],
        "cp-clients": [{"at": "2024-07-25T10:30:00+08:00", "slot": P, "held_as": "promoted",
                        "holder": C1, "stands_on": None}],
    }
    for ds, entries in extra.items():
        timelines[ds] = timelines.get(ds, []) + entries
    return g.Slots(timelines)


def _entry(read_clients, **kw):
    return {"supply_id": N2, "rank": 8, "status": "green", "recorded_at": "2024-08-05T10:00:00+08:00",
            "cause": "arrival:x", "reads": {
                "cp_notifications": {"state": "READ", "supply_id": N2},
                "cp_clients": ({"state": "READ", "supply_id": read_clients} if read_clients
                               else {"state": "ABSENT", "supply_id": None})}, **kw}


def _place(entry, slots, log=None, when="2024-08-05T12:00:00+08:00", held_back=None):
    return g.place(entry, dataset_id="cp-notifications", own_table="cp_notifications", period=P,
                   when=_at(when), slots=slots, log=log or ctn.Log(), receipts=RECEIPTS,
                   held_back=held_back)


class TestTheCell:

    def test_a_partner_in_the_warehouse_is_the_warehouse_cell(self):
        got = _place(_entry(C1), _slots())
        assert got["bucket"] == g.WAREHOUSE
        assert g.words_of(got["note"]) == "Client Register received Thursday, 25 July 2024"
        assert g.words_of(got["sentence"]) == (
            "Read against the Client Register in place in the warehouse, received 10:00am "
            "Thursday, 25 July 2024")

    def test_a_waiting_partner_is_the_staged_cell_on_a_waiting_page(self):
        got = _place(_entry(C2), _slots())
        assert got["bucket"] == g.STAGED
        assert g.words_of(got["sentence"]).endswith("not in place in the warehouse yet")

    def test_a_partner_since_replaced_is_in_neither_cell(self):
        """Criterion 7's third bucket (dashboard UX v4 B1)."""
        slots = _slots(**{"cp-clients": [{"at": "2024-08-05T11:00:00+08:00", "slot": P,
                                          "held_as": "promoted", "holder": C2, "stands_on": None}]})
        got = _place(_entry(C1), slots)
        assert got["bucket"] is None
        assert g.words_of(got["sentence"]) == (
            "Read against the Client Register received 10:00am Thursday, 25 July 2024, since "
            "replaced in the warehouse by the one received 10:00am Monday, 5 August 2024")

    def test_a_turned_down_partner_is_in_neither_cell(self):
        log = ctn.Log()
        log.state_instants = {C2: [(_at("2024-08-05T11:00:00+08:00"), "reject", None)]}
        got = _place(_entry(C2), _slots(), log=log)
        assert got["bucket"] is None and g.words_of(got["sentence"]).endswith("since turned down")

    def test_no_partner_reads_no_dataset_in_the_warehouse(self):
        got = _place(_entry(None), _slots())
        assert got["bucket"] == g.WAREHOUSE
        assert g.words_of(got["note"]) == "no Client Register in the warehouse for 2024-Q3"

    def test_an_inherited_partner_is_carried_forward(self):
        slots = _slots(**{"cp-clients": [{"at": "2024-08-01T09:00:00+08:00", "slot": P,
                                          "held_as": "inherited", "holder": C1,
                                          "stands_on": "2024-Q2"}]})
        got = _place(_entry(C1), slots)
        assert got["bucket"] == g.WAREHOUSE
        assert g.words_of(got["note"]).endswith(", carried forward from 2024-Q2")
        assert "in place in the warehouse for 2024-Q3, carried forward from 2024-Q2 (received" \
            in g.words_of(got["sentence"])

    def test_a_gate_re_check_says_why(self):
        """Criterion 13: a gate application's re-evaluation."""
        entry = _entry(C1, cause="gate:4", recorded_at="2024-08-05T10:30:00+08:00")
        entry["supply_id"] = C2
        entry["reads"] = {"cp_clients": {"state": "READ", "supply_id": C2},
                          "cp_notifications": {"state": "READ", "supply_id": N1}}
        got = g.place(entry, dataset_id="cp-clients", own_table="cp_clients", period=P,
                      when=_at("2024-08-05T12:00:00+08:00"), slots=_slots(), log=ctn.Log(),
                      receipts=RECEIPTS, held_back={"by": N2, "came": "package-mate"})
        assert g.words_of(got["sentence"]) == (
            "Re-checked 10:30am Monday, 5 August 2024 against the Notifications in place in the "
            "warehouse (received 10:00am Thursday, 25 July 2024): the Notifications received "
            "with this supply was held back.")


class TestTheClause:
    """The supply in place is the panel's (the most recently promoted) or the
    one the period stands on; its status red_promoted's counted timeline."""

    def _clause(self, health, holder=C1, stands_on=None, when="2024-08-05T12:00:00+08:00"):
        return g._clause("cp-clients", C2, holder, stands_on, _at(when), health,
                         {C1: "run-c1"}, RECEIPTS)

    def test_green(self):
        got = self._clause({"run-c1": {"promotedOn": "green", "timeline": []}})
        assert g.words_of(got["clause"]) + "Green" + g.words_of(got["tail"]) == (
            "The supply in place in the warehouse is the one received 10:00am Thursday, 25 July "
            "2024, and is Green.")

    def test_red_since_a_persons_promotion_names_them(self):
        health = {"run-c1": {"promotedOn": "green", "promotedAt": "2024-07-25T10:30:00+08:00",
                             "timeline": [{"at": "2024-08-01T10:00:00+08:00", "status": "red",
                                           "cause": "the promote of Notifications",
                                           "by": "Robin Hale"}]}}
        got = self._clause(health)
        assert got["status"] == "red"
        assert g.words_of(got["tail"]) == (": it turned red 10:00am Thursday, 1 August 2024, "
                                          "after the promote of Notifications by Robin Hale.")

    def test_promoted_while_red(self):
        health = {"run-c1": {"promotedOn": "red", "promotedAt": "2024-07-25T10:30:00+08:00",
                             "timeline": [{"at": "2024-07-25T10:00:00+08:00", "status": "red",
                                           "cause": "the arrival of Client Register"}]}}
        assert g.words_of(self._clause(health)["tail"]) == ": it was promoted while red."

    def test_nothing_in_place(self):
        got = self._clause({}, holder=None)
        assert g.words_of(got["clause"]) == "Nothing is in place in the warehouse for this period yet."

    def test_an_inherited_supply_is_carried_forward(self):
        got = self._clause({"run-c1": {"promotedOn": "green", "timeline": []}},
                           stands_on="2024-Q2")
        assert g.words_of(got["clause"]) == (
            "The supply in place in the warehouse is the one carried forward from 2024-Q2 "
            "(received 10:00am Thursday, 25 July 2024), and is ")

    def test_the_clause_names_the_panels_supply_from_the_timeline(self):
        """The supply in place is the panel's, judged per day; a period that
        stands on an earlier one names that."""
        timeline = {"points": [{"on": "2024-07-25", "promoted": {"supply": C1}}],
                    "standing": [{"on": "2024-08-06", "period": P, "standingIn": {
                        "supply": C1, "standsOn": "2024-Q2"}}]}
        log = ctn.Log()
        pts = g.clause_points("cp-clients", {C2: P}, timeline=timeline,
                              health={"run-c1": {"promotedOn": "green", "timeline": []}},
                              run_of={C1: "run-c1"}, log=log, receipts=RECEIPTS)[C2]
        assert [p["on"] for p in pts] == ["2024-08-05", "2024-08-06"]
        assert "carried forward from 2024-Q2" in g.words_of(pts[1]["clause"])


class TestTheNames:

    def test_two_supplies_of_a_table_on_one_day_take_their_time(self):
        receipts = g.Receipts({C1: "2024-08-05T09:00:00+08:00", C2: "2024-08-05T09:05:00+08:00"})
        assert g.words_of(g.named("cp-clients", C2, receipts, style="note")) == \
            "Client Register received 9:05am Monday, 5 August 2024"

    def test_past_three_the_first_two_and_n_more(self):
        names = [[g.text(x)] for x in "abcde"]
        assert g.words_of(g._names(names)) == "a, b and 3 more"
        assert g.words_of(g._names(names[:3])) == "a, b and c"
