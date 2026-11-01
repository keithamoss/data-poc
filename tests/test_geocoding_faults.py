"""REQ-GEN-298: the geocoding history carries each fault on purpose.

Two halves. The FAULTS by construction (criteria 1, 4, 5 and 6): each named
row fault applied to rows built by hand, asserted on the shape it gives and on
the band its share or coverage lands in. And THE PLAN (criteria 2, 3, 7, 8
and 13): the Linkage Products provider's own plan - what the driver writes -
asserted on where the ordinary severities and the named scenarios land, which
files are tried at generation, and what the warehouse holds when each tried
file arrives.

Planned once for the module: the plan runs every source collection's
provider in memory, about two minutes."""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from collection_modules import provider_module
from qa_tools.common import asset_time

lp = provider_module("linkage-products")

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

CP, ED = "geo-cp-clients", "geo-ed-presentations"


@pytest.fixture(scope="module")
def plan():
    return lp.PROVIDER.plan()


@pytest.fixture(scope="module")
def catalogue():
    from qa_tools.common import check_bands

    return check_bands.catalogue()


def _source(n=400):
    return pd.DataFrame({"cp_client_id": [f"C{i}" for i in range(n)],
                         "suburb": ["Ascot"] * n, "postcode": ["6104"] * n})


def _rows(source, years=(2011, 2016)):
    return lp.geocode_rows(CP, source, ("cp_client_id",), years, 0.0)


def _apply(rows, fault, source, catalogue, years=(2011, 2016), seed=7):
    return lp.apply_geo_faults(CP, rows, (f"{fault}@{CP}",), source_rows=source,
                               id_columns=("cp_client_id",), years=years,
                               rng=np.random.default_rng(seed), where="a test",
                               catalogue=catalogue, seed=seed)


class TestTheFaultsByConstruction:
    """Criteria 1, 4, 5 and 6, on rows built by hand."""

    def test_a_missing_year_drops_one_years_row_and_keeps_the_record(self, catalogue):
        source = _source()
        rows, verdict = _apply(_rows(source), "missing_year", source, catalogue)
        per = rows.groupby("id_1")["census_year"].nunique()
        short = per[per < 2]
        assert 1 <= len(short) <= 3 and verdict == "red"
        assert set(rows["id_1"]) == set(source["cp_client_id"]), "no record left out"

    def test_a_missing_year_needs_two_years_in_force(self, catalogue):
        source = _source()
        with pytest.raises(lp.CannotGenerate, match="two or more years in force"):
            _apply(_rows(source, (2011,)), "missing_year", source, catalogue, years=(2011,))

    def test_a_duplicated_year_is_identical_in_every_column(self, catalogue):
        source = _source()
        rows, verdict = _apply(_rows(source), "duplicate_year", source, catalogue)
        dupes = rows[rows.duplicated(keep=False)]
        assert 2 <= len(dupes) <= 6 and verdict == "red"
        assert dupes.duplicated(subset=["id_1", "census_year"], keep=False).all()

    def test_an_unexpected_year_is_2026_and_nothing_else_changes(self, catalogue):
        source = _source()
        before = _rows(source)
        rows, verdict = _apply(before, "unexpected_year", source, catalogue)
        extra = rows[rows["census_year"] == 2026]
        assert 1 <= len(extra) <= 3 and verdict == "red"
        assert len(rows) == len(before) + len(extra)
        assert lp.UNEXPECTED_YEAR == 2026

    @pytest.mark.parametrize("band", ["amber", "red"])
    def test_a_share_fault_turns_whole_records_in_every_year(self, catalogue, band):
        source = _source(1000)
        rows, verdict = _apply(_rows(source), f"not_geocoded_{band}", source, catalogue)
        assert verdict == band
        assert (rows.groupby("id_1")["match_level"].nunique() == 1).all(), "whole records"
        unplaced = rows[rows["match_level"] == "not geocoded"]
        assert (unplaced["sa2_code"] == "").all() and (unplaced["lga_code"] == "").all()
        share = 100.0 * len(unplaced) / len(rows)
        lo, hi = (6.0, 9.0) if band == "amber" else (12.0, 18.0)
        assert lo <= share <= hi + 0.2, share

    @pytest.mark.parametrize("band,lo,hi", [("amber", 0.5, 1.5), ("red", 3.0, 6.0)])
    def test_coverage_leaves_whole_records_out_in_every_year(self, catalogue, band, lo, hi):
        source = _source(1000)
        rows, verdict = _apply(_rows(source), f"left_out_{band}", source, catalogue)
        left = 100.0 * (1 - rows["id_1"].nunique() / len(source))
        assert lo <= left <= hi and verdict == band
        assert (rows.groupby("id_1")["census_year"].nunique() == 2).all(), \
            "no record has a year missing, so the missing-year check does not catch it"

    def test_an_orphan_is_added_and_every_source_record_keeps_its_rows(self, catalogue):
        source = _source()
        rows, verdict = _apply(_rows(source), "orphan_record", source, catalogue)
        orphans = set(rows["id_1"]) - set(source["cp_client_id"])
        assert len(orphans) == 1 and verdict == "red"
        assert set(source["cp_client_id"]) <= set(rows["id_1"]), "coverage unchanged"
        assert (rows[rows["id_1"].isin(orphans)]["census_year"].nunique()) == 2

    def test_an_empty_file_needs_a_source_holding_rows(self, catalogue):
        source = _source()
        rows, verdict = _apply(_rows(source), "empty_file", source, catalogue)
        assert len(rows) == 0 and verdict == "red"
        assert list(rows.columns) == lp.geo_columns(CP)
        with pytest.raises(lp.CannotGenerate, match="source supply holding rows"):
            _apply(_rows(source), "empty_file", source.iloc[0:0], catalogue)

    def test_an_unknown_fault_and_a_fault_on_another_dataset_are_refused(self, catalogue):
        source = _source()
        with pytest.raises(lp.CannotGenerate, match="unknown geocoding row fault"):
            _apply(_rows(source), "no_such", source, catalogue)
        with pytest.raises(lp.CannotGenerate, match="must name the dataset"):
            lp.apply_geo_faults(CP, _rows(source), (f"missing_year@{ED}",),
                                source_rows=source, id_columns=("cp_client_id",),
                                years=(2011, 2016), rng=np.random.default_rng(1),
                                where="a test", catalogue=catalogue, seed=1)

    def test_the_same_draw_gives_the_same_rows(self, catalogue):
        source = _source()
        a, _ = _apply(_rows(source), "not_geocoded_red", source, catalogue)
        b, _ = _apply(_rows(source), "not_geocoded_red", source, catalogue)
        assert a.equals(b)

    def test_no_lever_set_is_added_to_targeting(self):
        """Criterion 1 (architect S2): the share is computed in the stream."""
        from generator import targeting

        assert lp.PROVIDER.target_levers is None
        assert "geocod" not in open(targeting.__file__).read().lower()


def _table(dataset_id):
    from qa_tools.common import hierarchy

    return hierarchy.dataset(dataset_id).table


def _geo(plan):
    return [j for j in plan.jobs if j.stream == lp.GEO_STREAM]


def _faults(plan):
    return plan.state["geo_faults"]


class TestTheOrdinarySeverities:
    """Criterion 2 and REQ-GEN-295 criterion 13: the collections' mix per
    geocoding dataset, from the stream's own seed."""

    def _drawn(self, plan, d):
        named = {i.scenario_id for i, _p in plan.resolved}
        scenario_periods = {p.period for i, p in plan.resolved if i.dataset_id == d}
        out = {}
        for job in _geo(plan):
            faults = _faults(plan).get((job.slot_id, d))
            if faults and job.period.name not in scenario_periods:
                out[job.period.name] = faults
        assert named
        return out

    @pytest.mark.parametrize("d", [CP, ED])
    def test_about_a_quarter_amber_and_two_reds(self, plan, d):
        drawn = self._drawn(plan, d)
        n = len([j for j in _geo(plan) if plan.state["geocoding"][j.slot_id]
                 and _table(d) in plan.state["geocoding"][j.slot_id][1]])
        ambers = [p for p, f in drawn.items() if f == (f"{lp.GEO_AMBER_PRESET}@{d}",)]
        reds = [p for p, f in drawn.items() if f != (f"{lp.GEO_AMBER_PRESET}@{d}",)]
        assert len(ambers) == max(1, round(n * 0.25)) and len(reds) == 2, drawn

    @pytest.mark.parametrize("d", [CP, ED])
    def test_each_red_has_a_green_resupply_five_to_twenty_days_later(self, plan, d):
        drawn = self._drawn(plan, d)
        for job in _geo(plan):
            faults = drawn.get(job.period.name)
            if not faults or faults == (f"{lp.GEO_AMBER_PRESET}@{d}",):
                continue
            (at, files), (again, files2) = lp.PROVIDER._geo_arrivals(plan, job)
            assert 5 <= (asset_time.local_date(again) - asset_time.local_date(at)).days <= 20
            assert files[_table(d)][2] == "red"
            assert files2[_table(d)][2] == "green"

    def test_the_oldest_supply_is_clean(self, plan):
        first = _geo(plan)[0]
        assert not any(k[0] == first.slot_id for k in _faults(plan))

    def test_a_missing_year_only_where_two_years_are_in_force(self, plan):
        for job in _geo(plan):
            for (slot, d), faults in _faults(plan).items():
                if slot == job.slot_id and any(f.startswith("missing_year") for f in faults):
                    assert len(lp.members_in_force(d, job.period)) >= 2, job.period.name

    def test_no_ordinary_fault_on_a_corrected_round_or_a_held_source(self, plan):
        ridden = lp._ridden_quarters()
        held = {p for (_d, p) in plan.state["geo_named"]}
        scenario = {p.period for i, p in plan.resolved if i.dataset_id in (CP, ED)}
        for job in _geo(plan):
            if job.period.name in scenario:
                continue
            for (slot, _d) in _faults(plan):
                if slot == job.slot_id:
                    assert job.period.name not in ridden | held, job.period.name


#: Each named scenario's dataset, quarter and fault (criteria 3 and 4).
SCENARIOS = {
    "TS-102": (CP, "2023-Q2", "missing_year"), "TS-103": (ED, "2022-Q1", "duplicate_year"),
    "TS-104": (CP, "2016-Q2", "unexpected_year"), "TS-105": (ED, "2023-Q1", "not_geocoded_amber"),
    "TS-106": (CP, "2024-Q1", "not_geocoded_red"), "TS-107": (ED, "2014-Q1", "left_out_amber"),
    "TS-108": (CP, "2025-Q1", "left_out_red"), "TS-109": (ED, "2017-Q4", "orphan_record"),
    "TS-110": (CP, "2025-Q4", "empty_file"), "TS-111": (CP, "2026-Q1", "left_out_amber"),
}


class TestTheNamedScenarios:
    def test_ten_scenarios_one_fault_each_where_declared(self, plan):
        placed = {i.scenario_id: (i.dataset_id, p.period) for i, p in plan.resolved
                  if i.dataset_id in (CP, ED)}
        assert placed == {sid: (d, q) for sid, (d, q, _f) in SCENARIOS.items()}
        by_period = {j.period.name: j for j in _geo(plan)}
        for sid, (d, q, fault) in SCENARIOS.items():
            job = by_period[q]
            assert _faults(plan)[(job.slot_id, d)] == (f"{fault}@{d}",), sid
            others = [k for k in _faults(plan) if k[0] == job.slot_id and k[1] != d]
            assert not others, f"{sid}'s quarter carries a second fault"
            assert lp.PROVIDER._geo_arrivals(plan, job)[0][0].strftime("%H:%M") == "18:30"

    def test_the_missing_year_scenario_has_two_years_in_force(self, plan):
        job = next(j for j in _geo(plan) if j.period.name == SCENARIOS["TS-102"][1])
        assert len(lp.members_in_force(CP, job.period)) >= 2

    def test_the_g1_route_is_in_a_quarter_whose_amber_setting_promotes(self, plan):
        from qa_tools.common import amber_setting

        job = next(j for j in _geo(plan) if j.period.name == SCENARIOS["TS-111"][1])
        at = lp.PROVIDER._geo_arrivals(plan, job)[0][0]
        assert amber_setting.resolve(CP, at).value != amber_setting.HOLD
        assert plan.state["geocoding"][job.slot_id][1]["geo_cp_clients"][2] == "amber"

    def test_criterion_eights_files_are_named_not_planted(self, plan):
        assert plan.state["geo_named"] == {(CP, "2019-Q1"): "TS-93c", (CP, "2019-Q3"): "TS-100c",
                                           (ED, "2021-Q4"): "TS-101b"}
        for (d, q) in plan.state["geo_named"]:
            job = next(j for j in _geo(plan) if j.period.name == q)
            assert (job.slot_id, d) not in _faults(plan)
            meta = plan.state["geo_meta"][(job.slot_id, 1)]
            assert d in meta["tried"] and meta["sources"][d]["received_at"] is None

    def test_a_scenario_on_a_corrected_round_is_refused_not_moved(self, monkeypatch):
        from generator import scenario_injection as si

        bad = [i for i in si.INJECTIONS if i.scenario_id == "TS-107"][0]
        moved = dataclasses.replace(bad, anchor=-51)  # 2013-Q3, a corrected round
        monkeypatch.setattr(si, "INJECTIONS", tuple(moved if i is bad else i
                                                    for i in si.INJECTIONS))
        with pytest.raises(lp.CannotGenerate, match="TS-107.*correction alters"):
            lp.PROVIDER.plan()

    def test_a_scenario_in_a_quarter_of_its_sources_scenario_is_refused(self, monkeypatch):
        from generator import scenario_injection as si

        bad = [i for i in si.INJECTIONS if i.scenario_id == "TS-104"][0]
        moved = dataclasses.replace(bad, anchor=-43)  # 2016-Q1, which TS-84 claims
        monkeypatch.setattr(si, "INJECTIONS", tuple(moved if i is bad else i
                                                    for i in si.INJECTIONS))
        with pytest.raises(lp.CannotGenerate, match="TS-104: 2016-Q1 already holds TS-84"):
            lp.PROVIDER.plan()


class TestWhatIsTriedAndAgainstWhat:
    """Criteria 11 and 13."""

    def test_every_amber_red_and_scenario_file_is_tried_and_no_ordinary_green(self, plan):
        scenario = {(i.dataset_id, p.period) for i, p in plan.resolved}
        for job in _geo(plan):
            for n, (_at, files) in enumerate(lp.PROVIDER._geo_arrivals(plan, job), start=1):
                tried = set((plan.state["geo_meta"].get((job.slot_id, n)) or {}).get("tried", ()))
                for _t, (d, _rows, verdict) in files.items():
                    want = (verdict != "green" or (d, job.period.name) in scenario
                            or (d, job.period.name) in plan.state["geo_named"])
                    assert (d in tried) == want, (job.period.name, n, d, verdict)

    def test_about_forty_eight_are_tried(self, plan):
        n = sum(len(m.get("tried", ())) for m in plan.state["geo_meta"].values())
        assert 40 <= n <= 60, n

    def test_the_source_staged_is_the_one_the_plan_promotes_before_the_receipt(self, plan):
        for (slot, n), meta in plan.state["geo_meta"].items():
            for d, source in (meta.get("sources") or {}).items():
                if source["received_at"] is None:
                    continue
                at = lp.PROVIDER._geo_arrivals(plan, next(
                    j for j in _geo(plan) if j.slot_id == slot))[n - 1][0]
                assert asset_time.parse_instant(source["received_at"], d) < at

    def test_a_held_or_rejected_source_is_not_in_the_warehouse(self, plan):
        sources = plan.state["sources"]
        q = "2019-Q3"
        job = next(j for j in _geo(plan) if j.period.name == q)
        at = plan.state["geocoding"][job.slot_id][0]
        assert lp.in_warehouse("cp-clients", q, at, sources["cp-clients"]) is None
        # TS-100a's person promotes it at 10:00 the day after the release:
        later = at + timedelta(days=2)
        assert lp.in_warehouse("cp-clients", q, later, sources["cp-clients"]) is not None


def test_two_plans_place_the_same_faults(plan):
    """NFR 1: the same seed and configuration place the same injections."""
    again = lp.PROVIDER.plan()
    assert again.state["geo_faults"] == plan.state["geo_faults"]
    assert again.state["geo_meta"] == plan.state["geo_meta"]
    for job in _geo(plan):
        a = lp.PROVIDER._geo_arrivals(plan, job)
        b = lp.PROVIDER._geo_arrivals(again, job)
        assert [x[0] for x in a] == [x[0] for x in b]
        for (_at, fa), (_at2, fb) in zip(a, b):
            for t in fa:
                assert fa[t][1].equals(fb[t][1]) and fa[t][2] == fb[t][2]
