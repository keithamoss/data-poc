"""What a declared correction claims (REQ-GEN-205 criteria 10 and 18,
REQ-GEN-237 criterion 3): every period whose slot one of its changes
alters, with the period before and after, refused where another scenario
claims one, where another collection on the calendar holds a supply in an
altered period, or where it falls outside the generated history. Written
first and seen to fail.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from generator import correction_claims as cc
from generator import scenario_injection as si
from test_correction_apply import _docs, _move_q3
from test_correction_replay import _declare


@pytest.fixture
def docs():
    return _declare(_docs(), _move_q3, "CAB-1", "2026-01-10")


@dataclass(frozen=True)
class _P:
    name: str
    date: date

    @property
    def round_date(self):
        return self.date


def _quarters(first="2023-Q2", n=8):
    year, q = int(first[:4]), int(first[-1])
    out = []
    for _ in range(n):
        out.append(_P(f"{year}-Q{q}", date(year, 3 * q - 1, 1)))
        year, q = (year + 1, 1) if q == 4 else (year, q + 1)
    return out


class TestWhatACorrectionAlters:
    def test_a_moved_quarter_date_alters_that_quarter_and_the_one_before(self, docs):
        got = cc.altered("CAB-1", ["cp-clients"], docs=docs)
        assert got == {"cp-clients": {"2023-Q3", "2023-Q4"}}

    def test_its_claim_adds_the_period_before_and_after(self, docs):
        got = cc.claimed("CAB-1", {"cp-clients": _quarters()}, docs=docs)
        assert got == {"cp-clients": ["2023-Q2", "2023-Q3", "2023-Q4", "2024-Q1"]}


def _inj(sid, ds, anchor, rides=None):
    return si.Injection(sid, ds, anchor, "test", correction=rides)


class TestTheClaimIsChecked:
    def test_a_scenario_riding_it_may_sit_in_its_claim(self, docs):
        cc.check([_inj("TS-58", "cp-clients", 2, rides="CAB-1")],
                 {"cp-clients": _quarters()}, docs=docs, history_end=date(2026, 8, 1))

    def test_another_scenario_in_its_claim_is_refused_naming_both(self, docs):
        with pytest.raises(si.CannotPlace, match=r"TS-9.*CAB-1|CAB-1.*TS-9"):
            cc.check([_inj("TS-58", "cp-clients", 2, rides="CAB-1"),
                      _inj("TS-9", "cp-clients", 3)],
                     {"cp-clients": _quarters()}, docs=docs, history_end=date(2026, 8, 1))

    def test_another_collection_holding_a_supply_in_an_altered_quarter_is_refused(self, docs):
        with pytest.raises(si.CannotPlace) as e:
            cc.check([_inj("TS-58", "ed-presentations", 2, rides="CAB-1")],
                     {"ed-presentations": _quarters(), "cp-clients": _quarters()},
                     docs=docs, history_end=date(2026, 8, 1))
        msg = str(e.value)
        assert "CAB-1" in msg and "child-protection" in msg and "2023-Q4" in msg

    def test_a_quarter_another_collection_suppresses_is_not_a_supply(self, docs):
        cc.check([_inj("TS-58", "ed-presentations", 2, rides="CAB-1")],
                 {"ed-presentations": _quarters(), "cp-clients": _quarters()},
                 docs=docs, history_end=date(2026, 8, 1),
                 suppressed={"cp-clients": {"2023-Q3", "2023-Q4"}})

    def test_a_correction_dated_after_the_history_is_refused(self, docs):
        with pytest.raises(si.CannotPlace, match=r"TS-58.*CAB-1"):
            cc.check([_inj("TS-58", "cp-clients", 2, rides="CAB-1")],
                     {"cp-clients": _quarters()}, docs=docs, history_end=date(2025, 12, 1))

    def test_an_altered_period_outside_the_history_is_refused(self, docs):
        with pytest.raises(si.CannotPlace, match=r"TS-58.*CAB-1.*2023-Q3"):
            cc.check([_inj("TS-58", "cp-clients", 0, rides="CAB-1")],
                     {"cp-clients": _quarters("2023-Q4", 4)}, docs=docs,
                     history_end=date(2026, 8, 1))

    def test_riding_an_undeclared_correction_is_refused(self, docs):
        with pytest.raises(si.CannotPlace, match="CAB-9"):
            cc.check([_inj("TS-58", "cp-clients", 2, rides="CAB-9")],
                     {"cp-clients": _quarters()}, docs=docs, history_end=date(2026, 8, 1))


def test_the_driver_refuses_before_it_writes(monkeypatch, tmp_path):
    from generator import driver

    def refuse(*_a, **_k):
        raise si.CannotPlace("claimed twice")
    monkeypatch.setattr(cc, "check_all", refuse)
    monkeypatch.setattr(driver.delivery, "remove_deliveries",
                        lambda *a, **k: pytest.fail("cleared before the claim check"))
    with pytest.raises(si.CannotPlace, match="claimed twice"):
        driver.generate("emergency-department")


def test_a_scenario_on_another_dataset_of_the_collection_is_refused_too(docs):
    """Child Protection is one delivery a quarter: a claim on cp-clients'
    quarter is a claim on that quarter's delivery, whatever dataset the other
    scenario names."""
    with pytest.raises(si.CannotPlace, match=r"TS-9.*CAB-1"):
        cc.check([_inj("TS-58", "cp-clients", 2, rides="CAB-1"),
                  _inj("TS-9", "cp-placements", 3)],
                 {"cp-clients": _quarters(), "cp-placements": _quarters()}, docs=docs,
                 history_end=date(2026, 8, 1))


class TestAnotherCollectionsCorrectionEmptiesItsQuarters:
    """REQ-GEN-237 criterion 3's 'or by suppressing its routine supply there':
    Child Protection writes no routine supply in a quarter that a correction
    ridden by another collection's scenarios alters, and the claim check
    counts those quarters as suppressed."""

    def test_the_quarters_are_the_correction_s_altered_ones(self):
        # Only the quarters Child Protection still owes since REQ-GEN-238
        # dropped 2013 and 2014: of the correction's, 2015-Q2 and 2015-Q4.
        got = cc.foreign_altered("child-protection")
        assert {"2015-Q2", "2015-Q4"} <= got
        assert not any(q.startswith(("2013", "2014", "2016", "2021")) for q in got), got

    def test_a_collection_riding_the_correction_suppresses_nothing_for_it(self):
        assert cc.foreign_altered("emergency-department") == set()

    def test_child_protection_writes_nothing_there(self):
        from generator.collections import child_protection as cp

        plan = cp.PROVIDER.plan()
        empty = {job.period.name for job in plan.jobs if cp.PROVIDER.slot(plan, job) is None}
        assert cc.foreign_altered("child-protection") <= empty


def _widen_daily(cal, asset):
    daily = next(c for c in cal["calendars"] if c["name"] == "daily")
    last = daily["versions"][-1]
    daily["versions"].append({**last, "effective_from": "2026-09-19", "claim_window": "6h",
                              "changelog": [{"date": "2026-10-18", "author": "a test",
                                             "change": "wider"}]})


class TestAVersionLevelChangeClaimsOnlyTheFilingsItChanges:
    """REQ-GEN-205 criterion 10's narrowing for a version-level change
    (TS-62's): only the days whose filing it would change, by the impact
    trial's own rule (assignment.open_slot), with the day before and after."""

    @pytest.fixture
    def widened(self):
        return _declare(_docs(), _widen_daily, "CAB-W", "2026-09-19")

    def test_an_arrival_the_wider_window_takes_changes_its_filing(self, widened):
        from qa_tools.common import asset_time

        at = asset_time.wall_clock(date(2026, 9, 20), "09:00")
        assert cc.filing_changes("CAB-W", "birth-registrations", [at], docs=widened) \
            == {"2026-09-19", "2026-09-20"}

    def test_an_ordinary_arrival_changes_nothing(self, widened):
        from qa_tools.common import asset_time

        at = asset_time.wall_clock(date(2026, 9, 20), "12:00")
        assert cc.filing_changes("CAB-W", "birth-registrations", [at], docs=widened) == set()

    def test_it_is_a_version_level_change(self, widened, docs):
        assert cc.is_version_level("CAB-W", docs=widened)
        assert not cc.is_version_level("CAB-1", docs=docs)


def _widen_daily_from(day):
    def widen(cal, asset):
        daily = next(c for c in cal["calendars"] if c["name"] == "daily")
        last = daily["versions"][-1]
        daily["versions"].append({**last, "effective_from": day, "claim_window": "6h",
                                  "changelog": [{"date": "2026-10-19", "author": "a test",
                                                 "change": "wider"}]})
    return widen


class TestTS62sVersionStandsAfterTheHistoryREQGEN199Quotes:
    """REQ-GEN-205 criterion 25: TS-62's version takes effect after
    2026-09-08, TS-47's following day, and after the last day any REQ-GEN-199
    link names; on or before either, generation refuses naming TS-62 and
    never shifts it."""

    def _check(self, effective, last_link_day=None):
        docs = _declare(_docs(), _widen_daily_from(effective), "CAB-62", "2026-09-07")
        cc.check_version_after([_inj("TS-62", "birth-registrations", -1, rides="CAB-62")],
                               docs=docs, last_link_day=last_link_day)

    def test_a_version_after_ts47s_following_day_stands(self):
        self._check("2026-09-09", last_link_day=date(2026, 9, 1))

    def test_a_version_on_ts47s_following_day_is_refused_naming_ts62(self):
        with pytest.raises(si.CannotPlace, match=r"TS-62.*2026-09-08"):
            self._check("2026-09-08")

    def test_a_version_on_the_last_link_day_is_refused(self):
        with pytest.raises(si.CannotPlace, match=r"TS-62.*2026-09-12"):
            self._check("2026-09-12", last_link_day=date(2026, 9, 12))

    def test_it_is_refused_not_shifted(self):
        docs = _declare(_docs(), _widen_daily_from("2026-09-05"), "CAB-62", "2026-09-04")
        with pytest.raises(si.CannotPlace):
            cc.check_version_after([_inj("TS-62", "birth-registrations", -1, rides="CAB-62")],
                                   docs=docs, last_link_day=None)
        assert cc.added_versions("CAB-62", docs=docs) == [date(2026, 9, 5)]

    def test_the_committed_ts62_stands(self):
        cc.check_version_after(si.INJECTIONS, last_link_day=cc.last_req_gen_199_link_day())

    def test_the_last_req_gen_199_link_day_is_found(self):
        day = cc.last_req_gen_199_link_day()
        assert day is not None and day >= date(2026, 9, 1)


class TestAWrittenArrivalIsAskedOnlyWhatAConfirmationCouldMove:
    """correction_claims.check_written asks a version-level correction about
    an ordinary arrival only where its confirmation could re-file it: an
    arrival received BEFORE the correction's date, of a dataset it carries.
    One received after was filed under the corrected agreement as it arrived.

    A real defect, found by the first Emergency Department bootstrap
    (post-build-review #244): Child Protection's ordinary 2022-Q2 delivery,
    received after REQ-GEN-218's 15 December 2021 date and carrying cp_carers
    as REQ-GEN-218's decision says the gap's deliveries do, was refused as an
    arrival the correction would re-file."""

    def _cp(self, tables, at="2022-02-01T08:30:00+08:00"):
        return {"run_id": "cp_run_x", "period": "2022-Q2", "received_at": at,
                "row_counts": {t: 10 for t in tables}}

    def test_a_gap_delivery_received_after_the_correction_is_not_asked(self):
        cc.check_written(["cp-carers"], [self._cp(["cp_carers", "cp_clients"])])

    def test_an_arrival_without_the_dataset_is_not_asked(self):
        cc.check_written(["cp-carers"], [self._cp(["cp_clients"])])

    @pytest.fixture
    def backdated(self, monkeypatch):
        """CAB-W's wider window from 2026-09-19, declared on 2026-09-25 and
        ridden by one scenario, as a version-level correction would be."""
        import dataclasses

        rider = dataclasses.replace(si.INJECTIONS[0], correction="CAB-W")
        monkeypatch.setattr(si, "INJECTIONS", [rider])
        return _declare(_docs(), _widen_daily, "CAB-W", "2026-09-25")

    def _br(self, at):
        return {"run_id": "run_x", "period": "2026-09-20", "received_at": at,
                "row_counts": {"birth_registrations": 10}}

    def test_an_arrival_before_the_correction_it_would_refile_is_refused(self, backdated):
        with pytest.raises(si.CannotPlace, match="run_x"):
            cc.check_written(["birth-registrations"], [self._br("2026-09-20T09:00:00+08:00")],
                             docs=backdated)

    def test_the_same_arrival_after_the_correction_is_not(self, backdated, monkeypatch):
        later = _declare(_docs(), _widen_daily, "CAB-W", "2026-09-19")
        cc.check_written(["birth-registrations"], [self._br("2026-09-20T09:00:00+08:00")],
                         docs=later)


class TestADateLevelCorrectionIsAskedToo:
    """REQ-GEN-237 criterion 4 (Keith, 2026-10-19: build it): generation
    refuses where a correction - a period's DATE moved, not only a version's
    window - would move OR RE-JUDGE an ordinary supply no scenario names,
    naming the change and the run. Moves by assignment.open_slot and verdicts
    by arrival_classification.classify, the rules the impact preview uses.
    Before this, check_written skipped every date-level correction."""

    @pytest.fixture
    def rider(self, monkeypatch):
        import dataclasses

        monkeypatch.setattr(si, "INJECTIONS",
                            [dataclasses.replace(si.INJECTIONS[0], correction="CAB-1")])

    def _docs(self, to):
        return _declare(_docs(), lambda cal, asset: _move_q3(cal, asset, to), "CAB-1",
                        "2026-01-10")

    def _cp(self, at):
        return {"run_id": "cp_run_x", "period": "2023-Q4", "received_at": at,
                "row_counts": {"cp_clients": 10}}

    def test_an_ordinary_supply_it_would_move_is_refused(self, rider):
        with pytest.raises(si.CannotPlace, match=r"CAB-1.*cp_run_x"):
            cc.check_written(["cp-clients"], [self._cp("2023-08-01T08:30:00+08:00")],
                             docs=self._docs("2023-10-20"))

    def test_an_ordinary_supply_it_would_only_re_judge_is_refused(self, rider):
        with pytest.raises(si.CannotPlace, match=r"CAB-1 would re-judge cp_run_x"):
            cc.check_written(["cp-clients"], [self._cp("2023-08-01T10:00:00+08:00")],
                             docs=self._docs("2023-08-03"))

    def test_a_supply_it_leaves_alone_is_not(self, rider):
        cc.check_written(["cp-clients"], [self._cp("2024-02-01T08:30:00+08:00")],
                         docs=self._docs("2023-10-20"))

    def test_a_scenario_s_own_supply_is_not_asked(self, rider):
        cc.check_written(["cp-clients"], [self._cp("2023-08-01T08:30:00+08:00")],
                         frozenset({"2023-Q4"}), docs=self._docs("2023-10-20"))
