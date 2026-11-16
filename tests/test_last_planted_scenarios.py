"""The last planted scenarios of REQ-GEN-136 and REQ-GEN-137 (REQ-GEN-206):
TS-52's held Case Workers file written after generation, TS-53's
un-supersede case, TS-55's three-kind period, TS-112's pair with both files
rejected, TS-47's green following day, TS-99's move, and the riders TS-48
and TS-50.

Each test drives the generator's own planning functions against the real
calendar and configuration; what the pages say is quoted in the register as
observed on the bootstrapped build, and the hold guard is a needs_deployment
test in tests/test_as_at_scenarios.py.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta

import pytest

import collection_modules
from asset_model import asset_time
from generator import scenario_injection as si
from qa_tools.common import scenario_map, scripted_decisions

pytestmark = [pytest.mark.filterwarnings("ignore::UserWarning"), pytest.mark.asset("quarterly")]


def _injection(sid):
    found = [i for i in si.INJECTIONS if i.scenario_id == sid]
    assert len(found) == 1, sid
    return found[0]


def _periods(dataset_id):
    return si.generated_periods(dataset_id)


@dataclasses.dataclass
class _Arrival:
    """The fields of a recognised arrival TS-52's chooser reads."""

    run_id: str
    delivery_name: str
    received_at: datetime
    files_by_dataset: dict


def _at(day: str, hhmm: str = "09:00") -> datetime:
    from datetime import date

    return asset_time.wall_clock(date.fromisoformat(day), hhmm)


def _cw(day, name, hhmm="09:00"):
    return _Arrival(f"cp_case_workers__{day.replace('-', '')}", name, _at(day, hhmm),
                    {"cp-case-workers": ("cp_case_workers.csv",),
                     "cp-clients": ("cp_clients.csv",)})


@pytest.mark.asset("quarterly")
class TestTS52IsChosenFromTheDeliveries:
    """Criteria 1 and 2: the newest cp-case-workers supply received while no
    period it delivers in was open, outside every injection's delivery - and a
    refusal naming TS-52 where there is none, never a supply held otherwise."""

    def test_the_newest_held_one_is_chosen(self):
        # 27 May: the February round's slot closed in April and August's
        # window has not opened - held. 2 February and 2 August: open slots.
        recognised = [_cw("2026-02-02", "feb"), _cw("2025-05-27", "may25"),
                      _cw("2026-05-27", "may26"), _cw("2026-08-02", "aug")]
        placement = si.held_case_workers_placement(recognised, set())
        assert placement.scenario_id == "TS-52"
        assert placement.dataset == "cp-case-workers"
        assert placement.arrivals[0]["delivery"] == "may26"
        assert placement.arrivals[0]["run_id"] == "cp_case_workers__20260527"
        assert dict(placement.in_place_on) == {"TS-52": "2026-05-28"}
        assert placement.subject_for("TS-52") == scenario_map.VERDICT_LINE
        assert placement.as_record()["supplies"] == ["cp_case_workers__20260527"]

    def test_never_one_an_injection_places(self):
        recognised = [_cw("2025-05-27", "may25"), _cw("2026-05-27", "may26")]
        placement = si.held_case_workers_placement(recognised, {"may26"})
        assert placement.arrivals[0]["delivery"] == "may25"

    def test_refused_naming_it_where_none_is_held(self):
        # Every one arrives while a period it delivers in is open, or is a
        # scenario's: nothing to link, and no other held supply stands in.
        recognised = [_cw("2026-02-02", "feb"), _cw("2026-08-02", "aug"),
                      _cw("2026-05-27", "may26"),
                      _Arrival("cp_clients__20260527", "may26c", _at("2026-05-28"),
                               {"cp-clients": ("cp_clients.csv",)})]
        with pytest.raises(si.CannotPlace, match="TS-52"):
            si.held_case_workers_placement(recognised, {"may26"})

    def test_the_generated_history_holds_one(self, tmp_path):
        """Against the deliveries the real generator writes: the provider's
        extra placements carry TS-52 beside TS-79's."""
        import json

        from generator import driver, output

        undo = output.redirect(tmp_path)
        try:
            driver.generate("child-protection")
        finally:
            undo()
        written = tmp_path / "scenario_placements.json"
        assert written.is_file()
        placements = {p["scenario_id"]: p for p in json.loads(written.read_text())["placements"]}
        assert {"TS-52", "TS-79a", "TS-79b"} <= set(placements), sorted(placements)
        ts52 = placements["TS-52"]
        assert ts52["dataset"] == "cp-case-workers" and len(ts52["supplies"]) == 1
        assert ts52["subject"] == scenario_map.VERDICT_LINE


@pytest.mark.asset("daily")
class TestTS47AndTS53:
    """Criteria 5 and 11: TS-47's following day is generated green and claimed
    by TS-47; TS-53 sits on days nobody else claims, under replacement never,
    its person's decisions in the order REQ-PIPE-120 needs."""

    def test_ts47s_following_day_is_its_own_and_green(self):
        ts47 = _injection("TS-47")
        placement = si.resolve(ts47, _periods("birth-registrations"))
        assert placement.follow == ("2026-09-08",)
        assert "2026-09-08" in si.claimed_periods(ts47, _periods("birth-registrations"))

    def test_another_scenario_on_ts47s_following_day_is_refused_naming_both(self):
        ts47 = _injection("TS-47")
        periods = _periods("birth-registrations")
        names = [p.name for p in periods]
        other = si.Injection("TS-999", "birth-registrations",
                             names.index("2026-09-08") - len(names), "a test",
                             arrivals=(si.ExtraArrival(0, "14:00", None),))
        with pytest.raises(si.CannotPlace, match="TS-999 and TS-47|TS-47 and TS-999"):
            si.no_two_scenarios_share_a_period([ts47, other], {"birth-registrations": periods})

    def test_ts53_is_planted_under_replacement_never(self):
        from qa_tools.common import replacement_setting

        ts53 = _injection("TS-53")
        periods = _periods("birth-registrations")
        placement = si.resolve(ts53, periods)
        assert placement.period == "2026-08-04"
        for name in si.claimed_periods(ts53, periods):
            from datetime import date

            at = asset_time.start_of_day(date.fromisoformat(name))
            assert replacement_setting.resolve("birth-registrations", at).value == "never"
        targets = [a["target"]["built_to"] for a in placement.arrivals]
        assert targets == ["green", "green", "red"]

    def test_ts53s_decisions_reject_then_restore_then_promote(self):
        mine = [s for s in scripted_decisions.load() if s.scenario == "TS-53"]
        assert [(s.operation, s.supply_index) for s in mine] == [
            ("reject", 2), ("un-supersede", 1), ("promote", 1)]
        placement = si.resolve(_injection("TS-53"), _periods("birth-registrations"))
        received = [asset_time.wall_clock(__import__("datetime").date.fromisoformat(a["date"]),
                                          a["at"]) for a in placement.arrivals]
        when = [received[s.supply_index] + timedelta(hours=s.after_hours) for s in mine]
        assert when == sorted(when) and len(set(when)) == 3
        assert when[0] > received[2]

    def test_ts53s_link_stands(self):
        assert si.link_problems([_injection("TS-53")]) == []


@pytest.mark.asset("quarterly")
class TestTheQuarterlyPlacements:
    """Criteria 4, 18 and 24: TS-55 on 2023-Q1 standing on 2022-Q4, TS-112 in
    2017-Q2, TS-99 moved to 2024-Q3 - each where its requirement put it, and
    the riders TS-48 and TS-50 on their placements."""

    def test_ts55(self):
        ts55 = _injection("TS-55")
        periods = _periods("cp-clients")
        placement = si.resolve(ts55, periods)
        assert placement.period == "2023-Q1"
        assert si.stood_on(ts55, periods) == "2022-Q4"
        assert placement.arrivals[0]["file_shape"] == "one_table_missing"
        assert placement.subject_for("TS-55") == scenario_map.PERIOD_COMPOSITION
        assert si.link_problems([ts55]) == []

    def test_ts55_stands_where_case_workers_inherits(self):
        from asset_model import schedule

        delivered = {p.name for p in schedule.periods_for_dataset(
            "cp-case-workers", until=_periods("cp-clients")[-1].round_date)}
        assert "2023-Q1" not in delivered and "2022-Q4" in delivered

    def test_ts112(self):
        ts112 = _injection("TS-112a")
        placement = si.resolve(ts112, _periods("cp-clients"))
        assert placement.period == "2017-Q2"
        files = placement.arrivals[0]["files"]
        assert [(f["filename"], f["at"]) for f in files] == [
            ("cp_clients.csv", "08:30"), ("cp_clients_v2.csv", "08:40")]
        assert not ts112.keeps_drawn_severity and not ts112.is_targeted
        assert si.link_problems([ts112]) == []
        dates = dict(si.resolve(ts112, _periods("cp-clients")).in_place_on)
        assert dates == {"TS-112a": "2017-02-01", "TS-112b": "2017-02-08"}

    def test_ts112s_person_settles_neither_then_promotes_and_marks(self):
        mine = [s for s in scripted_decisions.load() if s.scenario == "TS-112a"]
        ops = [(s.operation, s.dataset_id) for s in mine]
        assert ops == [("choose-file", "cp-clients"), ("promote", "cp-notifications"),
                       ("promote", "cp-investigations"), ("promote", "cp-placements"),
                       ("mark-not-supplied", "cp-clients")]
        assert mine[0].files == ("reject", "reject") and mine[0].day_offset == 1
        assert all(s.day_offset == 8 for s in mine[1:4])

    def test_ts99_moved_to_2024_q3(self):
        placement = si.resolve(_injection("TS-99"), _periods("linkage-keys"))
        assert placement.period == "2024-Q3"

    def test_the_riders(self):
        assert "TS-48" in _injection("TS-75a").also_demonstrates
        assert "TS-50" in _injection("TS-81").also_demonstrates
        assert si.link_problems([_injection("TS-75a"), _injection("TS-81")]) == []


@pytest.mark.asset("quarterly")
class TestNoLinkagePlanAgainstARejectedPair:
    """Criterion 22: the Linkage Products plan reads a contested pair as
    promoted by no rule, and a settlement rejecting both files as promoting
    nothing - and refuses, naming the scenario, where it would plan TS-112's
    quarter against a Client Register promoted there."""

    @pytest.fixture(scope="class")
    def lp(self):
        return collection_modules.provider_module("linkage-products")

    @pytest.fixture(scope="class")
    def plan(self, lp):
        return lp.PROVIDER.plan()

    def test_ts112s_quarter_is_named(self, lp):
        assert ("TS-112a", "cp-clients", "2017-Q2") in lp.rejected_pairs()

    def test_no_client_register_is_planned_in_the_warehouse_there(self, lp, plan):
        src = plan.state["sources"]["cp-clients"]
        pair = [s for s in src if s.period == "2017-Q2"]
        assert pair and pair[0].contested
        for job in plan.jobs:
            if job.period.name != "2017-Q2":
                continue
            found = (plan.state["geocoding"].get(job.slot_id),) if job.stream == lp.GEO_STREAM \
                else tuple((at, None) for at, _f, _s in plan.state["arrivals"][job.slot_id])
            for got in found:
                if got:
                    assert lp.in_warehouse("cp-clients", "2017-Q2", got[0], src) is None

    def test_a_settlement_naming_a_supply_promotes_the_pair(self, lp, plan):
        """TS-80's settlement makes its real file the supply, so its quarter's
        Client Register is in the warehouse once it is played."""
        src = plan.state["sources"]["cp-clients"]
        pair = next(s for s in src if s.period == "2021-Q1" and s.contested)
        received = asset_time.parse_instant(pair.received_at, "cp-clients")
        assert lp.in_warehouse("cp-clients", "2021-Q1", received + timedelta(hours=1),
                               src) is None
        assert lp.in_warehouse("cp-clients", "2021-Q1", received + timedelta(days=3),
                               src) is pair

    def test_refused_naming_ts112_where_it_would_be(self, lp, plan, monkeypatch):
        promoted = dataclasses.replace(
            next(s for s in plan.state["sources"]["cp-clients"] if s.period == "2017-Q2"),
            contested=False)
        monkeypatch.setattr(lp, "in_warehouse", lambda *_a, **_k: promoted)
        with pytest.raises(lp.CannotGenerate, match="TS-112a"):
            lp._refuse_planned_against_a_rejected_pair(plan)


def test_a_one_table_pair_contests_its_table_and_a_six_table_one_only_its_own():
    """The generic provider rule (REQ-GEN-206 criterion 22)."""
    from generator.collections.base import Job, Plan, Provider

    class P(Provider):
        collection_id = "x"

    one = si.Injection("TS-1", "birth-registrations", 0, "",
                       arrivals=(si.ExtraArrival(0, "08:00", files=(
                           si.PairFile("08:00", "a.csv"), si.PairFile("08:10", "b.csv"))),))
    six = _injection("TS-112a")
    period = type("Period", (), {"name": "Q"})()
    for inj, table, want in ((one, "birth_registrations", True),
                             (six, "cp_clients", True), (six, "cp_notifications", False)):
        plan = Plan(jobs=[], resolved=[], injected_by_period={"Q": (inj, None)})
        assert P().contests_table(plan, Job("s", 0, None, period), 1, None, table) is want
