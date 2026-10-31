"""REQ-GEN-335: the linkage history's scenarios, driven through the Linkage
Products provider's own plan and slot hooks - what the driver writes - and
asserted on the rows each scenario's quarter is built with.

Planned once for the module: the plan runs every linked collection's provider
in memory (about forty seconds)."""
from __future__ import annotations

import dataclasses

import pytest

from generator import scenario_injection as si
from generator.collections import linkage_products as lp
from qa_tools.common import asset_time

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

CODES = {"cp-clients": "DOC_CLIENTS", "ed-presentations": "EDDC_PRESENTATION"}
COLUMN = {"cp-clients": "cp_client_id", "ed-presentations": "presentation_id"}


@pytest.fixture(scope="module")
def plan():
    return lp.PROVIDER.plan()


def _job(plan, period):
    return next(j for j in plan.jobs if j.period.name == period)


def _period_of(sid):
    injection = next(i for i in si.INJECTIONS if i.scenario_id == sid)
    return si.resolve(dataclasses.replace(injection, links=()),
                      lp.PROVIDER.generated_periods()).period


def _release(plan, sid, n=0):
    job = _job(plan, _period_of(sid))
    deliveries = lp.PROVIDER.slot(plan, job)
    assert deliveries, f"{sid} has no release"
    return job, deliveries[n].payload


def _source(plan, job, did, n=0):
    """The ids of the linked dataset's supply the release describes."""
    at = plan.state["arrivals"][job.slot_id][n][0]
    before = [s for s in plan.state["sources"][did] if s.period == job.period.name
              and asset_time.parse_instant(s.received_at, did) < at]
    assert before, f"no {did} supply before {job.period.name}'s release"
    return lp._ids(before[-1].rows, COLUMN[did])


def _coverage(plan, job, df, did, n=0):
    source = _source(plan, job, did, n)
    linked = set(df.loc[df["dataset"] == CODES[did], "id_1"])
    return lp._coverage(source, linked)


def _clean(plan, job, df, n=0):
    """Every own-row and cross-table property an ordinary release has."""
    assert len(df) > 0
    assert (df["linkage_key"] != "").all()
    assert set(df["dataset"]) <= set(CODES.values())
    assert (df["id_2"] == "").all()
    assert (df["id_1"] != "").all()
    assert not df.duplicated(["dataset", "id_1"]).any()
    assert lp.large_group_share(df) <= 2.0
    for did, code in CODES.items():
        if (df["dataset"] == code).any():
            assert set(df.loc[df["dataset"] == code, "id_1"]) <= set(_source(plan, job, did, n))
            assert 90.0 <= _coverage(plan, job, df, did, n) <= 96.5


def test_an_empty_key(plan):
    job, df = _release(plan, "TS-86")
    assert (df["linkage_key"] == "").sum() == 1
    _clean(plan, job, df[df["linkage_key"] != ""])


def test_an_undeclared_code_stands_for_a_missing_dataset(plan):
    job, df = _release(plan, "TS-87")
    assert not (df["dataset"] == "EDDC_PRESENTATION").any()
    assert (df["dataset"] == "EDDC_PRESENTATION_V2").sum() > 1000
    assert (df["dataset"] == "DOC_CLIENTS").any()


def test_a_surplus_identifier(plan):
    job, df = _release(plan, "TS-88")
    surplus = df[df["id_2"] != ""]
    assert len(surplus) == 1 and surplus.iloc[0]["dataset"] == "DOC_CLIENTS"
    _clean(plan, job, df.assign(id_2=""))


def test_one_record_linked_twice(plan):
    job, df = _release(plan, "TS-89")
    twice = df[df.duplicated(["dataset", "id_1"], keep=False)]
    assert len(twice) == 2 and set(twice["dataset"]) == {"EDDC_PRESENTATION"}
    assert twice["linkage_key"].nunique() == 2


@pytest.mark.parametrize("sid,did", [("TS-90", "ed-presentations"),
                                     ("TS-94", "cp-clients")])
def test_a_link_to_a_record_the_quarter_does_not_hold(plan, sid, did):
    job, df = _release(plan, sid)
    rows = df[df["dataset"] == CODES[did]]
    dangling = set(rows["id_1"]) - set(_source(plan, job, did))
    assert len(dangling) == 1


@pytest.mark.parametrize("sid,did,low,high", [("TS-91", "cp-clients", 85.0, 90.0),
                                              ("TS-92", "ed-presentations", 0.0, 85.0)])
def test_coverage_in_its_band(plan, sid, did, low, high):
    job, df = _release(plan, sid)
    assert low <= _coverage(plan, job, df, did) < high
    other = next(d for d in CODES if d != did)
    assert _coverage(plan, job, df, other) >= 90.0


@pytest.mark.parametrize("sid,low,high", [("TS-97", 2.0, 4.0), ("TS-98", 4.0, 100.0)])
def test_large_key_groups_in_their_band(plan, sid, low, high):
    job, df = _release(plan, sid)
    share = lp.large_group_share(df)
    assert low < share <= high
    assert not df.duplicated(["dataset", "id_1"]).any()
    sizes = df.groupby("linkage_key").size()
    assert sizes[sizes > lp.LARGE_GROUP].nunique() > 1, "every large group one size"


def test_a_blank_expected_identifier(plan):
    job, df = _release(plan, "TS-99")
    blank = df[df["id_1"] == ""]
    assert len(blank) == 1 and blank.iloc[0]["dataset"] == "DOC_CLIENTS"


def test_a_quarter_with_no_release(plan):
    job = _job(plan, _period_of("TS-96"))
    assert lp.PROVIDER.slot(plan, job) is None


@pytest.mark.parametrize("sid", ["TS-93b", "TS-100b"])
def test_the_release_reading_a_held_client_register_is_itself_ordinary(plan, sid):
    job, df = _release(plan, sid)
    _clean(plan, job, df)


def test_the_same_round_red_quarter_is_resupplied_after_the_release(plan):
    job, df = _release(plan, "TS-101")
    _clean(plan, job, df)
    at = plan.state["arrivals"][job.slot_id][0][0]
    times = [asset_time.parse_instant(s.received_at, "ed")
             for s in plan.state["sources"]["ed-presentations"] if s.period == job.period.name]
    assert any(t < at for t in times) and any(t > at for t in times)


def test_every_scenario_in_a_quarter_of_its_own(plan):
    mine = [i for i in si.INJECTIONS if i.dataset_id == lp.DATASET_ID]
    periods = [_period_of(i.scenario_id) for i in mine]
    assert len(mine) == 15 and len(set(periods)) == len(periods)
    for period in periods:
        assert plan.injected_by_period[period][0].dataset_id == lp.DATASET_ID


def test_the_ordinary_severity_mix(plan):
    owned = set(plan.injected_by_period) | plan.state["suppressed"]
    ordinary = [j for j in plan.jobs if j.period.name not in owned]
    severities = [j.severity for j in plan.jobs]
    assert severities[0] is None
    assert severities.count("red") == 2
    assert severities.count("amber") == round(len(plan.jobs) * 0.25)
    assert all(j.severity is None for j in plan.jobs if j.period.name in owned)
    for job in ordinary:
        deliveries = lp.PROVIDER.slot(plan, job)
        if job.severity is None:
            assert len(deliveries) == 1
            _clean(plan, job, deliveries[0].payload)
            continue
        fault = plan.state["arrivals"][job.slot_id][0][1][0]
        did = fault.split("@")[1]
        cover = _coverage(plan, job, deliveries[0].payload, did)
        if job.severity == "amber":
            assert len(deliveries) == 1 and 85.0 <= cover < 90.0
        else:
            assert cover < 85.0 and len(deliveries) == 2
            gap = (deliveries[1].received_date - deliveries[0].received_date).days
            assert 5 <= gap <= 20
            _clean(plan, job, deliveries[1].payload, n=1)


def test_no_ordinary_severity_on_a_quarter_a_correction_it_rides_alters(plan):
    """Found by the lp_boot bootstrap from empty, 2026-10-30: an ordinary amber
    drawn on 2013-Q4, a quarter REQ-GEN-205 alters, read green on arrival -
    the correction moves Emergency Department's supply there, so the coverage
    check that carries the amber could not run until the knock-on after
    confirmation. A severity carried only by a cross-collection check needs
    its sources in place when it arrives, so a rider quarter is clean, like a
    scenario's (PROVISIONAL)."""
    from generator import correction_claims, scenario_injection

    ridden = set()
    for reference, datasets in scenario_injection.CORRECTION_RIDERS.items():
        if lp.DATASET_ID in datasets:
            ridden |= correction_claims.altered(reference, [lp.DATASET_ID]).get(lp.DATASET_ID, set())
    assert ridden, "the precondition - REQ-GEN-205 alters some linkage quarter"
    on_them = [(j.period.name, j.severity) for j in plan.jobs
               if j.period.name in ridden and j.severity]
    assert on_them == []


def test_the_named_scenario_rides_a_marked_quarter(plan):
    marked = lp.marked_quarters([j.period for j in plan.jobs])
    assert marked and marked[0] == ("cp-clients", "2015-Q2")
    assert "2015-Q2" not in plan.injected_by_period


def test_an_unknown_fault_is_refused_naming_the_scenario():
    with pytest.raises(lp.CannotGenerate, match="TS-X.*unknown row fault 'typo'"):
        lp.parse_fault("typo", "TS-X")
    with pytest.raises(lp.CannotGenerate, match="names no linked dataset"):
        lp.parse_fault("dangling_id", "TS-X")


def test_a_fault_that_cannot_be_placed_is_refused_not_relaxed():
    import numpy as np
    import pandas as pd

    rows = {"cp-clients": pd.DataFrame({"cp_client_id": [f"C{i}" for i in range(40)]})}
    with pytest.raises(lp.CannotGenerate, match="TS-X: too few rows"):
        lp.build_rows(rows, ("large_groups_red",), np.random.default_rng(1), "TS-X")


def test_a_quarter_holding_another_collections_scenario_is_refused(plan):
    taken = next(i for i in si.INJECTIONS if i.scenario_id == "TS-12")
    period = si.resolve(dataclasses.replace(taken, links=()),
                        si.generated_periods(taken.dataset_id)).period
    fake = si.Injection(scenario_id="TS-999", dataset_id=lp.DATASET_ID, anchor=0, config="")
    placement = dataclasses.replace(si.resolve(fake, lp.PROVIDER.generated_periods()),
                                    period=period)
    with pytest.raises(lp.CannotGenerate, match=f"TS-999: {period} already holds TS-12"):
        lp._refuse_scenario_quarters([(fake, placement)])


def test_two_plans_build_the_same_rows(plan):
    again = lp.PROVIDER.plan()
    for job in plan.jobs:
        for a, b in zip(plan.state["rows"][job.slot_id], again.state["rows"][job.slot_id]):
            assert a.equals(b), job.period.name


def test_the_child_protection_sides_move_no_ordinary_severity(monkeypatch):
    """Criterion 6 and the byte-identical-neighbours NFR: TS-93a and TS-100a
    sit on quarters drawn clean, so every other quarter's severity is as it
    was without them, and each is one delivery with cp_clients alone red."""
    from generator import collections

    cp = collections.provider("child-protection")
    with_them = cp.plan()
    sides = {"TS-93a", "TS-100a"}
    monkeypatch.setattr(si, "INJECTIONS",
                        tuple(i for i in si.INJECTIONS if i.scenario_id not in sides))
    without = cp.plan()
    ours = {p.period for _i, p in with_them.resolved if p.scenario_id in sides}
    assert len(ours) == 2
    for a, b in zip(with_them.jobs, without.jobs):
        assert a.period.name == b.period.name
        if a.period.name in ours:
            assert b.severity is None, f"{a.period.name} was not drawn clean"
            deliveries = cp.slot(with_them, a)
            assert len(deliveries) == 1 and deliveries[0].severity == "red"
        else:
            assert a.severity == b.severity, a.period.name


class TestEachOrdinaryReleaseIsScheduledAfterThePromotionItReads:
    """REQ-GEN-334 criterion 12, refused before anything is written: an
    ordinary release received after the effective instant of each same-round
    source promotion - the gate's own effective_at_for, seeded as the gate
    seeds it - AND within its own due time and grace; else refused naming the
    quarter, the delivery and the promotion's effective instant."""

    @staticmethod
    def _quarter(name="2024-Q3"):
        from generator.collections.base import Job
        from qa_tools.common import schedule

        period = next(p for p in schedule.periods_for_dataset(lp.DATASET_ID)
                      if p.name == name)
        return Job("lp_slot_01", lp.BASE_SEED + 1, None, period), period

    @staticmethod
    def _source(period, hhmm):
        from generator.collections.base import GeneratedSupply

        received = asset_time.wall_clock(period.round_date, hhmm)
        return {"ed-presentations": [GeneratedSupply(period.name,
                                                     asset_time.isoformat(received), None)]}

    def test_an_ordinary_release_on_time_after_its_source_passes(self):
        job, period = self._quarter()
        at = asset_time.wall_clock(period.round_date, "17:30")
        lp._refuse_unschedulable([job], self._source(period, "16:00"),
                                 {job.slot_id: [(at, (), None)]}, {})

    def test_a_release_past_its_due_time_and_grace_is_refused(self):
        """Due 18:00 with eight hours' grace: a release at 03:00 the next day
        would be late by accident (Keith, OQ1 = a) - refused, not written."""
        from datetime import timedelta

        job, period = self._quarter()
        at = asset_time.wall_clock(period.round_date + timedelta(days=1), "03:00")
        with pytest.raises(lp.CannotGenerate, match=f"{period.name}.*linkage.*takes effect.*due time and grace"):
            lp._refuse_unschedulable([job], self._source(period, "16:00"),
                                     {job.slot_id: [(at, (), None)]}, {})

    def test_a_release_before_its_source_arrives_is_refused(self):
        job, period = self._quarter()
        at = asset_time.wall_clock(period.round_date, "17:30")
        with pytest.raises(lp.CannotGenerate, match=f"{period.name}.*ed-presentations"):
            lp._refuse_unschedulable([job], self._source(period, "17:45"),
                                     {job.slot_id: [(at, (), None)]}, {})

    def test_the_effective_instant_named_is_the_gates_own(self):
        """Seeded by the arrival's run id and capped at the release, as
        orchestrate.effective_at_of computes it."""
        from datetime import timedelta

        from qa_tools.common import promotion, schedule

        job, period = self._quarter()
        src = self._source(period, "16:00")
        first = asset_time.parse_instant(src["ed-presentations"][0].received_at, "t")
        at = asset_time.wall_clock(period.round_date + timedelta(days=1), "03:00")
        took = promotion.effective_at_for(
            first, seed=f"ed_presentations__{asset_time.arrival_key(first)}", before=at,
            within=schedule.claim_window("ed-presentations",
                                         on=asset_time.local_date(first)))
        with pytest.raises(lp.CannotGenerate) as exc:
            lp._refuse_unschedulable([job], src, {job.slot_id: [(at, (), None)]}, {})
        assert took.isoformat() in str(exc.value)


def test_a_dataset_identified_by_several_columns_carries_each(monkeypatch):
    """REQ-QAC-330 criterion 5: id_1 onward hold a linked dataset's declared
    source columns in order - every one of them, not only the first - and the
    columns after them are blank."""
    import numpy as np
    import pandas as pd

    monkeypatch.setattr(lp, "linked", lambda: (
        ("cp-clients", "DOC_CLIENTS", ("cp_client_id", "episode")),))
    monkeypatch.setattr(lp, "columns", lambda: ["linkage_key", "dataset", "id_1", "id_2",
                                                "id_3"])
    n = 200
    source = pd.DataFrame({"cp_client_id": [f"C{i:04d}" for i in range(n)],
                           "episode": [str(i % 3 + 1) for i in range(n)]})
    df = lp.build_rows({"cp-clients": source}, (), np.random.default_rng(1), "t")
    assert list(df.columns) == ["linkage_key", "dataset", "id_1", "id_2", "id_3"]
    pairs = set(zip(source["cp_client_id"], source["episode"]))
    got = list(zip(df["id_1"], df["id_2"]))
    assert got and set(got) <= pairs, got[:3]
    assert (df["id_3"] == "").all()
    assert 90.0 <= lp._coverage(list(pairs), set(got)) <= 96.5
