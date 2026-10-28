"""What the dashboard build records about a supply re-checked after we fixed a
check (REQ-DASH-221), from Child Protection histories driven through the real
lifecycle (tests/gate_support.py) on a pinned clock, in this test's own
database - and the outstanding queue's item for a promoted supply re-checked
worse (criterion 12)."""
from __future__ import annotations

from pathlib import Path

import pytest

from gate_support import Scenario, install_fake_tools, own_red, pin_replacement_setting
from test_package_gate import Q3, established

CP = "child-protection"


@pytest.fixture
def sc(private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    from qa_tools.common import environments

    monkeypatch.setenv(environments.ENVIRONMENT_ENV, "test")
    scenario = Scenario(root=tmp_path, raw_dir=Path(cp_raw_dir))
    install_fake_tools(monkeypatch, scenario)
    pin_replacement_setting(monkeypatch)
    scenario.at = lambda instant: monkeypatch.setenv(_pinned(), instant)
    return scenario


def _pinned() -> str:
    from qa_tools.common import asset_time

    return asset_time.PINNED_NOW_VARIABLE


def _rechecks():
    from pipeline import re_checks
    from qa_tools.common import supply_db

    with supply_db.connect(read_only=True, label="pytest-rechecks") as conn:
        return re_checks.for_collection(conn, CP)


def _own_check(dataset_id: str) -> str:
    """The one own check own_red() fails for a dataset (gate_support._first_own)."""
    from gate_support import declared_reads

    from qa_tools.common import asked_for

    return [c for c in asked_for.collection_checks(CP, "dbt")
            if c.split(".")[3] == dataset_id and c not in declared_reads()
            and "not_null" in c][0]


def _waiting_red(sc) -> dict:
    """2024-Q3 holding v1 of every table; then Clients v2 red on its own data,
    refused promotion and waiting for a person."""
    sc.at("2024-07-25T10:30:00+08:00")
    v1 = established(sc)
    sc.rules.append(own_red("C2"))
    sc.at("2024-08-05T10:30:00+08:00")
    v2 = sc.deliver("2024-08-05T10:00:00+08:00", {"cp_clients": "C2"})
    sc.process()
    assert sc.actions(v2["C2"]) == ["promotion-refused"], "precondition: waiting, red"
    return {**v1, **v2}


class TestASingleRecheck:
    """Criteria 1, 3 and 13: who, when, why, and the verdict either side."""

    def test_a_waiting_supply_rechecked_green_records_both_verdicts(self, sc):
        got = _waiting_red(sc)
        sc.rules.clear()  # "we fixed our check"
        sc.at("2024-08-07T10:30:00+08:00")
        sc.recheck(got["C2"], Q3, at="2024-08-07T10:30:00+08:00", reason="our check was wrong")
        (event,) = _rechecks().by_supply[got["C2"]]
        assert (event["before"], event["after"]) == ("red", "green")
        assert event["person"] == "Keith Moss"
        assert event["reason"] == "our check was wrong"
        assert event["at"].startswith("2024-08-07T02:30:00")
        assert "bulk" not in event

    def test_a_recheck_that_changed_nothing_is_still_recorded(self, sc):
        got = _waiting_red(sc)
        sc.at("2024-08-07T10:30:00+08:00")
        sc.recheck(got["C2"], Q3, at="2024-08-07T10:30:00+08:00", reason="just to be sure")
        (event,) = _rechecks().by_supply[got["C2"]]
        assert (event["before"], event["after"]) == ("red", "red")
        assert event["reason"] == "just to be sure"

    def test_a_recheck_not_yet_run_is_not_shown(self, sc):
        got = _waiting_red(sc)
        sc.at("2024-08-07T10:30:00+08:00")
        sc.recheck(got["C2"], Q3, at="2024-08-07T10:30:00+08:00", run=False)
        assert got["C2"] not in _rechecks().by_supply

    def test_a_trial_records_nothing_here(self, sc):
        """Criterion 11."""
        from qa_tools.common import bulk_recheck, supply_db

        got = _waiting_red(sc)
        check = _own_check("cp-clients")
        sc.judged_under_an_old_definition(check, [got["C2"]])
        with supply_db.connect(read_only=True, label="pytest") as conn:
            (covered,) = [c for c in bulk_recheck.plan(conn, check).covered
                          if c.supply == got["C2"]]
        sc.at("2024-08-07T10:30:00+08:00")
        bulk_recheck.try_one(covered)
        found = _rechecks()
        assert found.by_supply == {} and found.lines == {}


class TestAPromotedSupplyRecheckedWorse:
    """Criteria 8 and 12."""

    def test_it_is_recorded_and_listed_under_its_own_heading(self, sc):
        from qa_tools.common import outstanding

        sc.at("2024-07-25T10:30:00+08:00")
        v1 = established(sc)
        sc.rules.append(own_red("N1"))
        sc.at("2024-08-09T10:30:00+08:00")
        sc.recheck(v1["N1"], Q3, at="2024-08-09T10:30:00+08:00", reason="the fix found more")
        (event,) = _rechecks().by_supply[v1["N1"]]
        assert (event["before"], event["after"]) == ("green", "red")
        items = [i for i in outstanding.survey().items
                 if i.kind == outstanding.RECHECKED_WORSE]
        assert len(items) == 1, items
        (item,) = items
        assert item.dataset_id == "cp-notifications" and item.verdict == "red"
        assert item.observed_at.startswith("2024-08-09T02:30:00"), item.observed_at
        assert "acknowledges its new verdict" in item.detail
        # NOT ALSO COUNTED AS AN ORDINARY SUPPLY AWAITING A DECISION.
        assert not [i for i in outstanding.survey().items
                    if i.kind == outstanding.AWAITING_DECISION
                    and i.dataset_id == "cp-notifications"]
        # UNTIL IT IS ACKNOWLEDGED - and the acknowledgement is carried, naming who.
        sc.at("2024-08-10T10:30:00+08:00")
        sc.acknowledge(v1["N1"], Q3, at="2024-08-10T10:30:00+08:00")
        assert not [i for i in outstanding.survey().items
                    if i.kind == outstanding.RECHECKED_WORSE]
        (ack,) = _rechecks().acks[v1["N1"]]
        assert ack["actor"] == "Keith Moss" and ack["withdrawn"] is None


class TestABulkRecheck:
    """Criteria 2 and 4: the check and its changelog entry on each changed
    supply, and one line for the check's drawer."""

    def test_a_bulk_recheck_records_its_line_and_each_changed_supply(self, sc):
        got = _waiting_red(sc)
        check = _own_check("cp-clients")
        sc.judged_under_an_old_definition(check, [got["C2"], got["C1"]])
        sc.rules.clear()
        sc.at("2024-08-08T10:30:00+08:00")
        sc.bulk_recheck(check, at="2024-08-08T10:30:00+08:00", reason="the null rule was wrong")
        found = _rechecks()
        (event,) = found.by_supply[got["C2"]]
        assert (event["before"], event["after"]) == ("red", "green")
        assert event["bulk"]["checkId"] == check
        assert event["bulk"]["others"] is False, "only the corrected check's result moved"
        (line,) = found.lines[check]
        assert line["person"] == "Keith Moss" and line["reason"] == "the null rule was wrong"
        assert line["supplies"] == len([s for s in found.by_supply.values()
                                        for e in s if e.get("bulk")])
        assert line["datasets"] == 1
        assert line["changes"] == [event["at"]], "only the supply whose verdict moved"
        assert line["at"].startswith("2024-08-08T02:30:00")
        # PER DATASET, AND ONLY WHAT IS ON IT.
        mine = found.for_dataset("cp-clients", [check])
        assert set(mine["supplies"]) <= {got["C1"], got["C2"]} and check in mine["lines"]
        assert found.for_dataset("cp-carers", []) == {}

    def test_red_for_want_of_a_partner_with_a_partner_waiting_it_is_still_listed(self, sc):
        """post-build-review #283 (L2 wave-2 critic, 9): the outstanding
        survey drops a supply root_cause.group_queue lists beneath a cause.
        The likeliest way for a re-checked-worse supply to have one: its
        partner is demoted out of the period and a new partner waits there
        for a decision. It is red for want of the partner, not beneath it -
        that red is the warehouse's own reason, which trace() stops on - so
        it is still listed under its own heading, beside the partner's."""
        import dataclasses

        from qa_tools.common import filing_decisions as fd
        from qa_tools.common import outstanding, people, supply_db
        from test_carry_forward import REAL_PERSON

        sc.at("2024-07-25T10:30:00+08:00")
        v1 = established(sc)
        demote = fd.Request(operation=fd.DEMOTE, dataset_id="cp-clients",
                            actor=people.person_by_email(REAL_PERSON), reason="t", period=Q3,
                            supply=v1["C1"], confirmed=True)
        with supply_db.connect(read_only=True, label="pytest") as conn:
            key = fd.consequences(conn, demote).key
        sc.at("2024-08-20T10:30:00+08:00")
        fd.apply(dataclasses.replace(demote, acknowledged=key or None),
                 effective_at="2024-08-20T10:00:00+08:00")
        sc.run_owed()
        assert sc.holder("cp-clients", Q3) is None, "precondition: no Clients in 2024-Q3"
        sc.rules.append(own_red("C2"))
        sc.at("2024-08-25T10:30:00+08:00")
        c2 = sc.deliver("2024-08-25T10:00:00+08:00", {"cp_clients": "C2"})
        sc.process()
        assert sc.actions(c2["C2"]) == ["promotion-refused"], "precondition: a partner waits"
        sc.at("2024-08-28T10:30:00+08:00")
        sc.recheck(v1["N1"], Q3, at="2024-08-28T10:30:00+08:00", reason="the fix found more")
        kinds = {(i.kind, i.dataset_id) for i in outstanding.survey().items}
        assert (outstanding.RECHECKED_WORSE, "cp-notifications") in kinds, kinds
        assert (outstanding.AWAITING_DECISION, "cp-clients") in kinds, kinds
