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


def _quarters(first="2023-Q1", n=8):
    year, q = int(first[:4]), int(first[-1])
    out = []
    for _ in range(n):
        out.append(_P(f"{year}-Q{q}", date(year, 3 * q - 1, 1)))
        year, q = (year + 1, 1) if q == 4 else (year, q + 1)
    return out


class TestWhatACorrectionAlters:
    def test_a_moved_quarter_date_alters_that_quarter_and_the_one_before(self, docs):
        got = cc.altered("CAB-1", ["cp-clients"], docs=docs)
        assert got == {"cp-clients": {"2023-Q2", "2023-Q3"}}

    def test_its_claim_adds_the_period_before_and_after(self, docs):
        got = cc.claimed("CAB-1", {"cp-clients": _quarters()}, docs=docs)
        assert got == {"cp-clients": ["2023-Q1", "2023-Q2", "2023-Q3", "2023-Q4"]}


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
        assert "CAB-1" in msg and "child-protection" in msg and "2023-Q3" in msg

    def test_a_quarter_another_collection_suppresses_is_not_a_supply(self, docs):
        cc.check([_inj("TS-58", "ed-presentations", 2, rides="CAB-1")],
                 {"ed-presentations": _quarters(), "cp-clients": _quarters()},
                 docs=docs, history_end=date(2026, 8, 1),
                 suppressed={"cp-clients": {"2023-Q2", "2023-Q3"}})

    def test_a_correction_dated_after_the_history_is_refused(self, docs):
        with pytest.raises(si.CannotPlace, match=r"TS-58.*CAB-1"):
            cc.check([_inj("TS-58", "cp-clients", 2, rides="CAB-1")],
                     {"cp-clients": _quarters()}, docs=docs, history_end=date(2025, 12, 1))

    def test_an_altered_period_outside_the_history_is_refused(self, docs):
        with pytest.raises(si.CannotPlace, match=r"TS-58.*CAB-1.*2023-Q2"):
            cc.check([_inj("TS-58", "cp-clients", 0, rides="CAB-1")],
                     {"cp-clients": _quarters("2023-Q3", 4)}, docs=docs,
                     history_end=date(2026, 8, 1))

    def test_riding_an_undeclared_correction_is_refused(self, docs):
        with pytest.raises(si.CannotPlace, match="CAB-9"):
            cc.check([_inj("TS-58", "cp-clients", 2, rides="CAB-9")],
                     {"cp-clients": _quarters()}, docs=docs, history_end=date(2026, 8, 1))


def test_the_driver_refuses_before_it_writes(monkeypatch, tmp_path):
    from generator import driver

    def refuse():
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
        got = cc.foreign_altered("child-protection")
        assert {"2013-Q1", "2013-Q4", "2014-Q3", "2015-Q1", "2015-Q3"} <= got
        assert "2016-Q1" not in got and not any(q.startswith("2021") for q in got)

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
