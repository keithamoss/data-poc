"""The divergent-arrivals cut keeps the shape the real build produces
(post-build-review #269).

`TestPerDatasetArrivals` in tests/test_dashboard_e2e.py renders a Child
Protection file cut short by tests/divergent_arrivals.py. The cut kept a
check's history entry only when the entry's own RUN was one the dataset kept,
so it dropped every result recorded under ANOTHER table's run (#253) - since
REQ-PIPE-265 the only record of a same-instant sibling's cross-table check -
while leaving the build's `counted` answer pointing at it. The page then met a
counted rank its history did not hold, which post-build-review #266 makes a
console error, and the render gate failed on a shape the real build never
produces: in the real file every counted rank resolves to an entry about the
same supply.

These tests drive the cut itself on a small card of that real shape, so they
need no deployment.
"""
from __future__ import annotations

from tests.divergent_arrivals import cut_datasets_short


def _entry(rank, run_id, supply_id, recorded_by=None, **extra):
    return {"rank": rank, "run_id": run_id, "run_date": "2018-05-01", "supply_id": supply_id,
            "recorded_by": recorded_by, "recorded_at": "2018-05-01T09:00:00+08:00",
            "value": 0.0, "status": "green", **extra}


def _collection():
    """cp-investigations with two supplies. A cross-table check about the first
    is recorded only under cp-clients' same-instant run (REQ-PIPE-265), the
    second's under its own run, and one superseded result of the second."""
    a, b = "cp-investigations@A", "cp-investigations@B"
    card = {
        "check_id": "x.cp_client_id.relationships_dbt",
        "history": [
            _entry(1, "cp_investigations__A", a),
            _entry(2, "cp_clients__A", a, recorded_by="cp-clients", read_run="cp_investigations__A"),
            _entry(3, "cp_investigations__B", b),
        ],
        "superseded": [_entry(4, "cp_investigations__B0", b, replaced_by="cp_investigations__B",
                              supply_run="cp_investigations__B")],
        "counted": {a: [{"rank": 2, "reason": None, "on": "2018-05-01"}],
                    b: [{"rank": 3, "reason": None, "on": "2018-08-01"}]},
    }
    return {"datasets": [{
        "id": "cp-investigations",
        "runs": [{"run_id": "cp_investigations__A", "run_date": "2018-05-01", "supply_id": a},
                 {"run_id": "cp_investigations__B", "run_date": "2018-08-01", "supply_id": b}],
        "arrivalHistory": [], "arrivalByRun": {}, "lastArrival": {},
        "columns": [{"checks": [card], "stats": {}}],
    }]}


def _card(data):
    return data["datasets"][0]["columns"][0]["checks"][0]


class TestTheCutKeepsWhatTheBuildCounts:
    def test_every_counted_rank_left_after_the_cut_is_in_the_cards_entries(self):
        card = _card(cut_datasets_short(_collection(), {"cp-investigations": 1}))
        entries = {h["rank"] for h in card["history"] + card.get("superseded", [])}
        counted = [p["rank"] for points in card["counted"].values() for p in points
                   if p["rank"] is not None]
        assert counted, "precondition: the cut left nothing counted to check"
        missing = [r for r in counted if r not in entries]
        assert not missing, (f"the cut leaves counted ranks {missing} that the card's entries "
                             f"do not hold - a shape the real build never produces")

    def test_a_result_recorded_under_another_tables_run_about_a_kept_supply_stays(self):
        card = _card(cut_datasets_short(_collection(), {"cp-investigations": 1}))
        assert [h["rank"] for h in card["history"]] == [1, 2]

    def test_nothing_about_a_cut_supply_is_left(self):
        card = _card(cut_datasets_short(_collection(), {"cp-investigations": 1}))
        assert set(card["counted"]) == {"cp-investigations@A"}
        assert card.get("superseded", []) == []
        assert all(h["supply_id"] == "cp-investigations@A" for h in card["history"])
