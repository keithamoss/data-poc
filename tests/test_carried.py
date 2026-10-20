"""A cross-table check is evaluated once for tables that arrive together,
and every sibling's gate reads that one verdict (REQ-PIPE-265; Keith
2026-10-20, option b).

The fixture's dirty delivery lands its six Child Protection files at one
instant - a zip - and its notifications name clients the register does not
hold, so "Notifications -> Client Register" is red. The Client Register's
run is checked first and evaluates it; the Notifications run must carry it:
not ask a tool for it, record nothing for it, and still hand the red verdict
to its promotion gate. Written before the code; the real tools run.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fixture_ids import CP_DIRTY_RUN_IDS
from qa_tools.common import arrivals, carried, promotion, qa_store, supply_db
from qa_tools.tools import orchestrate

CP = "child-protection"
CLIENTS = next(r for r in CP_DIRTY_RUN_IDS if r.startswith("cp_clients__"))
NOTIFICATIONS = next(r for r in CP_DIRTY_RUN_IDS if r.startswith("cp_notifications__"))


def _found(cp_raw_dir):
    return arrivals.arrivals_for(CP, "cp_run_", Path(cp_raw_dir) / "deliveries",
                                 Path(cp_raw_dir) / "receipts")


def _arrival(cp_raw_dir, run_id):
    return next(a for a in _found(cp_raw_dir) if a.run_id == run_id)


def _reading_clients_from_notifications() -> set[str]:
    """The checks filed under Notifications that declare they read the
    Client Register, for the tools that can carry."""
    from qa_tools.common import check_id

    out = set()
    for check, tables in promotion._declared_reads().items():
        parsed = check_id.try_parse(check)
        if (parsed and parsed.dataset == "cp-notifications" and "cp_clients" in tables
                and parsed.tool in carried.CARRIED_TOOLS):
            out.add(check)
    return out


@pytest.fixture(scope="module")
def two_runs(cp_duckdb_dir, cp_raw_dir):
    """The Client Register's run, then the Notifications run, of one zip -
    each filed with its siblings and overlaid, then through the real run
    step, as the lifecycle does (REQ-PIPE-105 criterion 5: a zip is filed
    whole, so its first file sees the rest). The shared fixture overlays
    file by file, which is a staggered delivery's shape, not a zip's."""
    stamp = "2026-04-01T06:30:00+08:00"
    found = _found(cp_raw_dir)
    got = {}
    for run_id in (CLIENTS, NOTIFICATIONS):
        arrival = next(a for a in found if a.run_id == run_id)
        orchestrate.file_and_overlay(CP, arrival, among=found)
        got[run_id] = orchestrate.run_one(CP, orchestrate.entry_for(CP, arrival), stamp,
                                          "pytest")
    return got


class TestTheLaterSiblingCarriesTheCheck:

    def test_there_are_checks_to_carry(self):
        assert _reading_clients_from_notifications(), \
            "precondition: Notifications declares checks reading the Client Register"

    def test_the_client_register_run_evaluated_them_red(self, two_runs):
        mine = {r["check_id"]: r for r in two_runs[CLIENTS]}
        wanted = _reading_clients_from_notifications()
        assert wanted <= set(mine), sorted(wanted - set(mine))
        # A VERDICT, NOT A COULD-NOT-RUN RECORD - both say "fail".
        assert all(carried.not_evaluated_reason(mine[c]) is None for c in wanted), \
            [carried.not_evaluated_reason(mine[c]) for c in wanted]
        assert any(mine[c]["status"] == "fail" for c in wanted), \
            "precondition: the dirty notifications name clients the register lacks"

    def test_the_notifications_run_records_that_it_carried_them(self, two_runs):
        with supply_db.connect(read_only=True, label="pytest:carried") as conn:
            on_record = carried.carried_of(conn, NOTIFICATIONS)
        wanted = _reading_clients_from_notifications()
        assert wanted <= set(on_record), sorted(wanted - set(on_record))
        assert {on_record[c] for c in wanted} == {CLIENTS}

    def test_no_tool_was_asked_for_them_and_nothing_was_recorded_for_them(self, two_runs):
        wanted = _reading_clients_from_notifications()
        with supply_db.connect(read_only=True, label="pytest:carried") as conn:
            asked = qa_store.asked_for_run(conn, NOTIFICATIONS)
            recorded = {r[0] for r in conn.execute(
                f'SELECT check_id FROM "{qa_store.SCHEMA}".check_result WHERE run_key = ?',
                [NOTIFICATIONS]).fetchall()}
        assert wanted.isdisjoint(c for checks in asked.values() for c in checks)
        assert wanted.isdisjoint(recorded)
        assert not any(r["check_id"] in wanted for r in two_runs[NOTIFICATIONS])

    def test_the_notifications_gate_reads_the_red_carried_verdict(self, two_runs, cp_raw_dir,
                                                                  monkeypatch):
        """NFR 1, no false green: the gate of the table that did not evaluate
        the check is handed its red verdict."""
        seen = []
        real = promotion.after_run

        def spy(conn, **kwargs):
            seen.extend(kwargs["results"])
            return real(conn, **kwargs)

        monkeypatch.setattr(promotion, "after_run", spy)
        monkeypatch.setattr(promotion, "promote", lambda *a, **k: None)
        arrival = _arrival(cp_raw_dir, NOTIFICATIONS)
        promotion.after_runs([arrival], two_runs[NOTIFICATIONS], agency_id="x",
                             collection_id=CP, actor="pytest", actor_kind="rule",
                             effective_at="2026-04-01T06:31:00+08:00")
        handed = {r["check_id"]: r for r in seen}
        wanted = _reading_clients_from_notifications()
        assert wanted <= set(handed), sorted(wanted - set(handed))
        assert any(handed[c]["status"] == "fail" for c in wanted)
        assert {handed[c]["carried_from"] for c in wanted} == {CLIENTS}


class TestWhatIsNeverCarried:
    """Criteria 1, 5, 6 and 8, on the rule itself."""

    def test_a_staggered_file_has_no_siblings(self):
        assert carried.siblings("cp_notifications__202604010600000000") != \
            carried.siblings("cp_notifications__202604010605000000")
        assert "cp_clients__202604010600000000" not in \
            carried.siblings("cp_notifications__202604010605000000")

    def test_a_re_check_has_no_siblings(self):
        assert carried.siblings(f"{NOTIFICATIONS}{supply_db.RERUN_MARK}1") == []

    def test_a_run_naming_no_table_has_no_siblings(self):
        assert carried.siblings("trial_20261002t010203") == []

    def test_a_check_over_a_different_supply_is_evaluated_afresh(self, monkeypatch):
        check = sorted(_reading_clients_from_notifications())[0]
        here = supply_db.Resolution(run_id=NOTIFICATIONS, schema="s",
                                    resolved={"cp_clients": "cp_clients__202604010600000000__2",
                                              "cp_notifications": NOTIFICATIONS})
        there = supply_db.Resolution(run_id=CLIENTS, schema="s",
                                     resolved={"cp_clients": CLIENTS,
                                               "cp_notifications": NOTIFICATIONS})
        monkeypatch.setattr(supply_db, "resolution_for",
                            lambda conn, run_id: here if run_id == NOTIFICATIONS else there)
        monkeypatch.setattr(carried, "_evaluated_in",
                            lambda conn, run, checks: set(checks) if run == CLIENTS else set())
        got = carried.decide(None, NOTIFICATIONS, lambda c: True, promotion._declared_reads())
        assert check not in got

    def test_a_table_promoted_between_the_two_runs_is_the_same_supply(self, monkeypatch):
        check = sorted(_reading_clients_from_notifications())[0]
        supply = "cp-clients@202604010600000000"
        here = supply_db.Resolution(run_id=NOTIFICATIONS, schema="s",
                                    resolved={"cp_clients": "cp_clients",
                                              "cp_notifications": NOTIFICATIONS},
                                    supply_of={"cp_clients": supply})
        there = supply_db.Resolution(run_id=CLIENTS, schema="s",
                                     resolved={"cp_clients": CLIENTS,
                                               "cp_notifications": NOTIFICATIONS})
        from qa_tools.common import supply_status

        monkeypatch.setattr(supply_db, "resolution_for",
                            lambda conn, run_id: here if run_id == NOTIFICATIONS else there)
        monkeypatch.setattr(supply_status, "_own_tables", lambda conn, ds, s: [CLIENTS])
        monkeypatch.setattr(carried, "_evaluated_in",
                            lambda conn, run, checks: set(checks) if run == CLIENTS else set())
        got = carried.decide(None, NOTIFICATIONS, lambda c: True, promotion._declared_reads())
        assert got.get(check) == CLIENTS

    def test_a_held_table_is_never_carried_over(self, monkeypatch):
        check = sorted(_reading_clients_from_notifications())[0]
        here = supply_db.Resolution(run_id=NOTIFICATIONS, schema="s",
                                    resolved={"cp_notifications": NOTIFICATIONS},
                                    held={"cp_clients": CLIENTS})
        there = supply_db.Resolution(run_id=CLIENTS, schema="s",
                                     resolved={"cp_clients": CLIENTS,
                                               "cp_notifications": NOTIFICATIONS})
        monkeypatch.setattr(supply_db, "resolution_for",
                            lambda conn, run_id: here if run_id == NOTIFICATIONS else there)
        monkeypatch.setattr(carried, "_evaluated_in",
                            lambda conn, run, checks: set(checks) if run == CLIENTS else set())
        assert check not in carried.decide(None, NOTIFICATIONS, lambda c: True,
                                           promotion._declared_reads())

    def test_a_not_evaluated_record_is_no_verdict(self):
        assert carried.not_evaluated_reason({"unrunnable_reason": "not yet due"})
        assert carried.not_evaluated_reason({"held_reason": "held"})
        assert carried.not_evaluated_reason({"status": "fail"}) is None
