"""The scenarios that show what the as-at panel and qualifier say on a past
date (REQ-GEN-199): TS-75 to TS-79, and the generator capabilities they
needed - a delivery that leaves one table out or carries it alone, one
placement covering several days, a hold era the scenario refuses to leave,
the quarter an early arrival files into claimed, and TS-79's placements
written after generation.

Each test drives the generator's own planning functions against the real
calendar and configuration; the page-level criteria are needs_deployment
tests in tests/test_dashboard_e2e.py.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date

import pytest

from generator import scenario_injection as si
from generator.targeting import Target

FILES = {f"{t}.csv": f"{t} rows" for t in
         ("cp_clients", "cp_notifications", "cp_investigations", "cp_placements",
          "cp_carers", "cp_case_workers")}


def _cp_periods():
    from generator import generate_cp_runs

    return generate_cp_runs.generated_periods()


def _bdm_periods():
    from generator import generate_runs

    return generate_runs.generated_periods()


def _injection(sid):
    return next(i for i in si.INJECTIONS if i.scenario_id == sid)


class TestTheTwoNewFileShapes:
    """Criterion 6: cp_placements left out, then arriving alone; the
    existing one-table shape untouched."""

    def test_one_table_missing_leaves_out_placements_and_nothing_else(self):
        out = si.apply_file_shape("one_table_missing", FILES)
        assert set(out) == set(FILES) - {"cp_placements.csv"}
        assert all(out[k] == FILES[k] for k in out)

    def test_missing_table_late_is_placements_alone(self):
        assert si.apply_file_shape("missing_table_late", FILES) == {
            "cp_placements.csv": "cp_placements rows"}

    def test_one_table_only_is_still_clients_alone(self):
        assert si.apply_file_shape("one_table_only", FILES) == {
            "cp_clients.csv": "cp_clients rows"}

    def test_a_delivery_that_leaves_a_table_out_takes_no_supply_index_for_it(self):
        """A link's `arrival N` and a script's `supply N` must name the same
        file, so the delivery TS-77 leaves cp_placements out of is not one of
        cp-placements' supplies - its late file is supply 0."""
        placement = si.resolve(_injection("TS-77a"), _cp_periods())
        shapes = [a["file_shape"] for a in si.supply_arrivals(placement)]
        assert shapes == ["missing_table_late"]


class TestASupplyIndexNamesOneFileEverywhere:
    """The critic's G1: the replay read `supply N` from the placement's
    recorded supplies, which counted any arrival given a run id - including a
    delivery that carried none of the dataset's file, given its only run by
    resolve_run_ids' fallback - while links counted only arrivals carrying
    the file. The recorded supplies now come from the same list."""

    def test_a_delivery_without_the_datasets_file_takes_no_supply_index(self):
        placement = si.resolve(_injection("TS-77a"), _cp_periods())
        placement.arrivals[0]["run_id"] = "cp_clients__the_five_table_delivery"
        placement.arrivals[1]["run_id"] = "cp_placements__the_late_file"
        assert placement.as_record()["supplies"] == ["cp_placements__the_late_file"]


class TestAKeptSeverityIsOnlyEverAnAmber:
    """The critic's G2: a scenario that keeps its quarter's drawn severity
    keeps an amber; a drawn red would be planned and not written."""

    def test_a_drawn_red_on_such_a_quarter_is_refused(self, monkeypatch):
        from generator import generate_cp_runs

        periods = _cp_periods()
        index = [p.name for p in periods].index(si.resolve(_injection("TS-76"), periods).period)
        plan = list(generate_cp_runs.RUN_PLAN)
        plan[index] = (plan[index][0], "red")
        monkeypatch.setattr(generate_cp_runs, "RUN_PLAN", plan)
        with pytest.raises(si.CannotPlace, match="TS-76.*keeps only an amber"):
            generate_cp_runs._plan_injections(periods)


class TestOnePlacementCoversSeveralDays:
    """TS-78: D, D+1 and D+2 are one placement, because D+1 is both D's
    following day and D+2's lead-in."""

    def test_the_covered_days_are_claimed_and_the_green_day_follows_them(self):
        placement = si.resolve(_injection("TS-78a"), _bdm_periods())
        assert placement.period == "2026-08-30"
        assert placement.covered == ("2026-08-31", "2026-09-01")
        assert placement.lead_in == ("2026-08-28", "2026-08-29")
        assert placement.follow == ("2026-09-02",)

    def test_another_scenario_on_a_covered_day_is_refused(self):
        periods = _bdm_periods()
        other = si.Injection("TS-x", "birth-registrations", -23, "cfg")  # 31 August
        with pytest.raises(si.CannotPlace, match="TS-x and TS-78a|TS-78a and TS-x"):
            si.no_two_scenarios_share_a_period([_injection("TS-78a"), other],
                                               {"birth-registrations": periods})

    def test_the_generator_writes_no_ordinary_supply_on_a_covered_day(self):
        from generator import generate_runs

        _r, by_period, _s, quiet = generate_runs._plan_injections(_bdm_periods())
        covered = generate_runs._covered(by_period)
        assert covered == {"2026-08-31", "2026-09-01"}
        assert covered <= quiet, "no other day's resend may land on a covered day"


class TestTheHoldEraIsNotLeft:
    """Criterion 15: outside the era, refused naming the scenario - never
    shifted."""

    def test_today_the_era_covers_d_to_d_plus_2(self):
        si.resolve(_injection("TS-78a"), _bdm_periods())  # no refusal

    def test_an_anchor_outside_the_era_is_refused_naming_it(self):
        moved = dataclasses.replace(_injection("TS-78a"), anchor=-30)
        with pytest.raises(si.CannotPlace, match="TS-78a.*outside a hold"):
            si.resolve(moved, _bdm_periods())


class TestAnEarlyArrivalClaimsTheQuarterItFilesInto:
    """Criterion 28: TS-67 arrives before its quarter's window, files into
    the quarter before (-13), and claims it."""

    def test_ts_67_claims_the_quarter_before_its_anchor(self):
        periods = _cp_periods()
        placement = si.resolve(_injection("TS-67"), periods)
        assert si.filed_early_into(_injection("TS-67"), placement, periods) == ("2023-Q3",)

    def test_an_arrival_inside_its_window_claims_nothing_more(self):
        periods = _cp_periods()
        placement = si.resolve(_injection("TS-65"), periods)
        assert si.filed_early_into(_injection("TS-65"), placement, periods) == ()

    def test_a_scenario_placed_where_ts_67_files_is_refused(self):
        periods = _cp_periods()
        other = si.Injection("TS-x", "cp-clients", -13, "cfg")
        with pytest.raises(si.CannotPlace, match="2023-Q3"):
            si.no_two_scenarios_share_a_period([_injection("TS-67"), other],
                                               {"cp-clients": periods})


class TestWhereTheNewChildProtectionScenariosSit:
    """Criteria 1, 7, 10 and 29."""

    def test_the_anchors_and_their_quarters(self):
        periods = _cp_periods()
        got = {sid: si.resolve(_injection(sid), periods).period
               for sid in ("TS-75a", "TS-76", "TS-77a")}
        assert got == {"TS-75a": "2024-Q1", "TS-76": "2025-Q1", "TS-77a": "2023-Q2"}

    def test_none_at_minus_1_minus_2_or_minus_15(self):
        for sid in ("TS-75a", "TS-76", "TS-77a"):
            assert _injection(sid).anchor not in (-1, -2, -15), sid

    def test_every_one_is_planned_through_the_per_delivery_check(self):
        from generator import generate_cp_runs

        resolved, _ = generate_cp_runs._plan_injections(_cp_periods())
        assert {"TS-75a", "TS-76", "TS-77a"} <= {i.scenario_id for i, _p in resolved}

    def test_ts_75_dirties_clients_alone(self):
        """Criterion 1: red by cp_clients' own preset alone (H2)."""
        from generator import generate_cp_runs

        seen = []

        class Provider:
            def generate(self, *a, **k):
                return {t.removesuffix(".csv"): t for t in FILES}

            def churn(self, payload, **k):
                return payload

            def dirty(self, payload, severity, seed, previous_row_count):
                seen.append((sorted(payload), severity))
                return {t: f"dirty {t}" for t in payload}

        period = _cp_periods()[-11]
        got = generate_cp_runs._injected_chain(Provider(), _injection("TS-75a"), period,
                                                seed=1)
        assert seen == [(["cp_clients"], "red")]
        assert got[0].payload["cp_clients"] == "dirty cp_clients"
        assert got[0].payload["cp_carers"] == "cp_carers.csv"


class TestTs79IsWrittenAfterGeneration:
    """Criteria 19-21: from the calendar's participation, never from
    configuration, in the same write as Child Protection's placements."""

    def test_the_newest_and_oldest_inherited_quarters(self):
        got = {p.scenario_id: p for p in si.inheritance_placements(_cp_periods())}
        assert (got["TS-79a"].period, got["TS-79b"].period) == ("2026-Q2", "2023-Q2")
        assert {p.dataset for p in got.values()} == {"cp-case-workers"}

    def test_each_link_date_is_inside_its_quarter(self):
        periods = _cp_periods()
        names = [p.name for p in periods]
        for p in si.inheritance_placements(periods):
            on = date.fromisoformat(p.in_place_on_for(p.scenario_id))
            nxt = periods[names.index(p.period) + 1].date
            assert p.period_date < on < nxt, p.scenario_id

    def test_they_claim_no_period_and_name_no_supply(self):
        for p in si.inheritance_placements(_cp_periods()):
            record = p.as_record()
            assert record["supplies"] == [] and not record["lead_in"]
            assert p.scenario_id not in {i.scenario_id for i in si.INJECTIONS}

    def test_a_regeneration_replaces_them_rather_than_merging_past_them(self, tmp_path):
        path = tmp_path / "placements.json"
        stale = {"scenario_id": "TS-79a", "dataset": "cp-case-workers",
                 "period": "2020-Q2", "in_place_on": "2020-06-16", "supplies": []}
        path.write_text(json.dumps({"placements": [stale]}))
        si.write_placements(si.inheritance_placements(_cp_periods()), path, merge=True)
        records = json.loads(path.read_text())["placements"]
        assert [r["period"] for r in records if r["scenario_id"] == "TS-79a"] == ["2026-Q2"]


class TestTheLinksResolveBetweenTheirEvents:
    """Criterion 23: each link's date between its two events."""

    def test_every_link_of_the_new_scenarios_stands(self):
        new = [i for i in si.INJECTIONS
               if i.scenario_id in ("TS-75a", "TS-76", "TS-77a", "TS-78a")]
        assert len(new) == 4
        assert si.link_problems(new) == []

    def test_the_dates(self):
        got = {}
        for sid, periods in (("TS-75a", _cp_periods()), ("TS-76", _cp_periods()),
                             ("TS-77a", _cp_periods()), ("TS-78a", _bdm_periods())):
            got.update(dict(si.resolve(_injection(sid), periods).in_place_on))
        assert got == {"TS-75a": "2024-02-08", "TS-75b": "2024-02-25",
                       "TS-76": "2025-02-17", "TS-77a": "2023-05-17",
                       # TS-54 rides TS-76's placement and date (REQ-GEN-044).
                       "TS-54": "2025-02-17",
                       "TS-77b": "2023-06-08", "TS-78a": "2026-08-31",
                       "TS-78b": "2026-09-01"}


def test_a_targeted_amber_is_never_named_with_a_severity():
    with pytest.raises(si.CannotPlace):
        si.ExtraArrival(0, "14:00", "amber", target=Target("amber"))
    with pytest.raises(si.CannotPlace, match="no severity"):
        si.ExtraArrival(0, "09:00", None, severity_tables=("cp_clients",))


class TestOnlyThePlantedAmbersWaitUnderHold:
    """Criterion 16, on the bootstrapped history: every supply the rule held
    under the hold amber setting is TS-43's or TS-78's - the guard that the
    back-dated 30 August version held nothing else. KEYED BY SUPPLY, and split
    in two (the critic's T2): that the planted supplies ARE held passes today;
    that NOTHING ELSE is held is the strict expected failure #175 records."""

    @staticmethod
    def _held_and_planted():
        from qa_tools.common import decision_log as dl
        from qa_tools.common import scenario_map, scripted_decisions, supply_db

        placements = scenario_map.read_placements()
        planted = set()
        for sid, index in (("TS-43", 0), ("TS-78a", 0), ("TS-78a", 2)):
            run = placements[sid].supplies[index]
            planted.add(scripted_decisions._supply_of("birth-registrations", run))
        with supply_db.connect(label="test-hold-guard") as conn:
            held = {s for (s,) in conn.execute(
                f"SELECT supply FROM {dl.TABLE} WHERE action = ? AND amber_setting = 'hold'",
                [dl.PROMOTION_WITHHELD]).fetchall()}
        return held, planted

    def test_the_planted_ambers_are_held(self, deployment_history):
        held, planted = self._held_and_planted()
        assert len(planted) == 3, planted
        assert planted <= held, f"not held under hold: {sorted(planted - held)}"

    @pytest.mark.xfail(strict=True, reason=(
        "post-build-review #175: on the first bootstrap two more supplies waited under "
        "hold on 2026-09-08 - TS-47's late file and that day's own supply. Keith to "
        "decide; the criterion is not loosened"))
    def test_nothing_else_is_held(self, deployment_history):
        held, planted = self._held_and_planted()
        assert held - planted == set(), sorted(held - planted)
