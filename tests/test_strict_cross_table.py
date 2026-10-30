"""A cross-table check that cannot read a table is red for the table that
asks, whatever the reason - not yet due included (REQ-PIPE-270).

Driven through the real Child Protection lifecycle with each tool's
evaluation stood in for (tests/gate_support.py): the could-not-run record
is the orchestrator's own, written where it writes it, and read back from
qa.check_result.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gate_support import (CP, DATASET, Scenario, checks_reading, install_fake_tools,
                          pin_replacement_setting)
from qa_tools.common import period_schema, unrunnable

Q3 = "2024-Q4"
CLIENT_REFS = checks_reading("cp_clients", "cp-notifications")


@pytest.fixture
def scenario(private_supply_dsn, cp_raw_dir, tmp_path, monkeypatch):
    sc = Scenario(root=tmp_path, raw_dir=Path(cp_raw_dir))
    install_fake_tools(monkeypatch, sc)
    pin_replacement_setting(monkeypatch)
    return sc


def _client_ref_records(sc: Scenario, supply: str) -> list[dict]:
    out = []
    for run in sc.runs(supply):
        out += [r for r in sc.results(run["run_key"]) if r["check_id"] in CLIENT_REFS]
    return out


def _put_partners_in_the_warehouse(sc: Scenario, period: str, at: str, tables) -> dict:
    """Deliver and promote by hand the tables a scenario needs in place."""
    got = sc.deliver(at, {t: t[3:5].upper() + "1" for t in tables})
    sc.process()
    for supply in got.values():
        sc.promote_by_hand(supply, period, at=at)
    return got


class TestNotYetDuePartner:

    def test_early_file_is_red_until_its_partner_is_in_the_warehouse(self, scenario):
        """S3, the false green closed: Notifications v2 arrives alone at 08:40
        on Child Protection's due day, Clients due at 09:00. Its Client
        reference records not evaluated and RED, with the not-yet-due code and
        Clients' due instant, and it is held back rather than promoted (as
        decision 103 promoted cp-investigations@202408010100000000 on 'no
        data')."""
        sc = scenario
        _put_partners_in_the_warehouse(sc, Q3, "2024-07-25T10:00:00+08:00",
                                       ["cp_case_workers", "cp_investigations"])
        n2 = sc.deliver("2024-08-01T08:40:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()

        records = _client_ref_records(sc, n2)
        assert records, "precondition: Notifications v2's Client reference was recorded"
        for r in records:
            assert r["status"] == "fail", (r["check_id"], r["status"])
            extra = r.get("extra") or {}
            assert extra.get("unrunnable_code") == "not-yet-due", extra
            assert extra.get("unrunnable_due_at", "").startswith("2024-08-01T09:00:00"), extra
            assert extra.get("unrunnable_reason")
        assert sc.holder("cp-notifications", Q3) != n2, "held back, never promoted on it"
        assert "promote" not in sc.actions(n2)


class TestEveryReasonIsRed:

    @pytest.mark.parametrize("state, code", [
        # Literal codes, so the test is collected - and seen to fail - on a
        # tree that does not know the new ones yet.
        ("not-yet-due", "not-yet-due"),
        ("past-due", "past-due"),
        ("staged-awaiting-decision", "staged-awaiting-decision"),
        ("rejected", "rejected"),
        ("could-not-be-loaded", "could-not-be-loaded"),
        ("contested", "contested"),
        ("held-back", "held-back-with-its-package"),
    ])
    def test_each_reason_records_red_and_is_described(self, scenario, monkeypatch, state, code):
        """Every reason criterion 4 names, driven through the real run step
        with an unreadable Clients: red at qa.check_result with that reason's
        code, and a describe() text other than the catch-all."""
        sc = scenario
        _put_partners_in_the_warehouse(sc, Q3, "2024-07-25T10:00:00+08:00",
                                       ["cp_case_workers", "cp_investigations"])
        if state == "held-back":
            # The run is a gate application's re-check, reading Clients from
            # the warehouse because its supply is not promoting with it.
            from qa_tools.tools import orchestrate

            real = orchestrate.entry_for

            def entry_for(collection_id, arrival):
                entry = real(collection_id, arrival)
                entry["purpose"] = None
                return {**entry, "purpose": {"held_back_tables": ["cp_clients"]}}
            monkeypatch.setattr(orchestrate, "entry_for", entry_for)
            # (purpose only carries the held-back tables here; the period is
            # the arrival's own filing.)
            monkeypatch.setattr(unrunnable, "supply_state", lambda *a: None)
        elif state in ("could-not-be-loaded", "contested"):
            monkeypatch.setattr(unrunnable, "supply_state", lambda *a: None)
            if state == "could-not-be-loaded":
                monkeypatch.setattr(unrunnable, "_refused_with",
                                    lambda conn, run_id: frozenset({"cp_clients"}))
            else:
                from qa_tools.common import supply_db

                real_res = supply_db.resolution_for

                def contested(conn, run_id):
                    res = real_res(conn, run_id)
                    if "cp_clients" in res.absent:
                        res.absent.remove("cp_clients")
                        res.ambiguous["cp_clients"] = ["a", "b"]
                    return res
                monkeypatch.setattr(supply_db, "resolution_for", contested)
        else:
            def supply_state(conn, dataset_id, period, as_at):
                return state if dataset_id == "cp-clients" else None
            monkeypatch.setattr(unrunnable, "supply_state", supply_state)
        n2 = sc.deliver("2024-08-03T10:00:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()

        records = _client_ref_records(sc, n2)
        assert records, "precondition: the Client reference was recorded"
        for r in records:
            extra = r.get("extra") or {}
            assert r["status"] == "fail", (state, r["status"])
            assert extra.get("unrunnable_code") == code, (state, extra)
        described = unrunnable.describe([{**(r.get("extra") or {}), **r} for r in records])
        assert unrunnable.words_for(code) in described
        verdict = period_schema.Unrunnable(status=period_schema.RED, reason=code,
                                           names=("cp_clients",))
        assert "no prior period" not in verdict.describe()

    def test_held_is_red_and_coded_too(self):
        """A HELD table's record (held_blast_radius) is red and carries its
        code beside held_reason, which carried.not_evaluated_reason keys on."""
        from qa_tools.common import carried, held_blast_radius

        (r,) = held_blast_radius.results_for(
            held={"cp_clients": "cp_clients__x"},
            reads={CLIENT_REFS[0]: ["cp_clients"]}, run_id="r", run_timestamp="t")
        assert r["status"] == "fail" and r.get("unrunnable_code") == "held"
        assert carried.not_evaluated_reason(r)
        assert unrunnable.words_for("held")

    def test_no_code_reaches_the_catch_all(self):
        for code in ("not-yet-due", "past-due", "staged-awaiting-decision", "contested",
                     "could-not-be-loaded", "held", "held-back-with-its-package", "rejected"):
            text = period_schema.Unrunnable(status=period_schema.RED, reason=code,
                                            names=("cp_clients",)).describe()
            assert "no prior period" not in text, code
            assert unrunnable.words_for(code)
        assert "rejected - a person rejected this period's file and none has replaced it" == \
            unrunnable.words_for("rejected")


class TestNotInTheAgreement:

    def test_a_check_whose_table_joins_later_is_out_of_scope(self, scenario, monkeypatch):
        """A dataset joining Child Protection's agreement from 2025-Q2 - here
        Clients, by its slot being refused for any period before it - and a
        reader's check of it run in 2025-Q1: left out of the run's scope, in
        left_out with its reason, no result and no red, and the reader's
        status decided without it. The same check in 2025-Q2, Clients not yet
        supplied, is red."""
        from qa_tools.common import slots

        real = slots.slots_for_dataset

        def joins_later(dataset_id, **kw):
            got = real(dataset_id, **kw)
            if dataset_id == "cp-clients":
                return [s for s in got if s.name >= "2025-Q2"]
            return got
        monkeypatch.setattr(slots, "slots_for_dataset", joins_later)
        sc = scenario
        q4 = "2025-Q1"
        _put_partners_in_the_warehouse(sc, q4, "2024-10-25T10:00:00+08:00",
                                       ["cp_case_workers", "cp_investigations"])
        n2 = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()

        assert _client_ref_records(sc, n2) == []
        (run,) = [r for r in sc.runs(n2) if r["scope"] == "arrival"]
        left = [r for r in sc.results(run["run_key"]) if r["tool"] == "left_out"]
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(read_only=True, label="pytest") as conn:
            raw = conn.execute(
                f'SELECT raw_output FROM "{qa_store.SCHEMA}".tool_output WHERE run_key = ? '
                "AND tool = 'left_out'", [run["run_key"]]).fetchall()
        assert raw, (left, "a left_out record names the checks out of scope")
        outside = raw[0][0].get("not_in_agreement") or {}
        assert set(CLIENT_REFS) <= set(outside), outside
        assert all(v == f"not part of the agreement for {q4}" for v in outside.values())
        # DECIDED WITHOUT IT: nothing else is red, so it promotes.
        assert sc.holder("cp-notifications", q4) == n2

        # 2025-Q2: Clients is part of the agreement and not yet supplied.
        _put_partners_in_the_warehouse(sc, "2025-Q2", "2025-01-25T10:00:00+08:00",
                                       ["cp_case_workers", "cp_investigations"])
        n3 = sc.deliver("2025-02-03T10:00:00+08:00", {"cp_notifications": "N3"})["N3"]
        sc.process()
        records = _client_ref_records(sc, n3)
        assert records and all(r["status"] == "fail" for r in records)


    def test_the_build_carries_why_it_did_not_run(self, scenario, monkeypatch, tmp_path):
        """The page half of criterion 9 waits for the page merge; the BUILD
        DATA it needs is here: the dataset's page carries each check left out
        of a run as not part of the agreement, with its reason."""
        from pipeline import build_dashboard_data as bdd
        from qa_tools.common import slots
        from qa_tools.tools import results_history

        real = slots.slots_for_dataset

        def joins_later(dataset_id, **kw):
            got = real(dataset_id, **kw)
            return [s for s in got if s.name >= "2025-Q2"] if dataset_id == "cp-clients" \
                else got
        monkeypatch.setattr(slots, "slots_for_dataset", joins_later)
        sc = scenario
        _put_partners_in_the_warehouse(sc, "2025-Q1", "2024-10-25T10:00:00+08:00",
                                       ["cp_case_workers", "cp_investigations"])
        n2 = sc.deliver("2024-11-03T10:00:00+08:00", {"cp_notifications": "N2"})["N2"]
        sc.process()
        out = tmp_path / "results.json"
        monkeypatch.setattr(results_history, "results_path", lambda _cid: str(out))
        monkeypatch.setattr(bdd, "results_path", lambda _cid: str(out))
        results_history.build_results_from_history(CP)
        page = next(d for d in bdd.build_datasets(CP) if d["id"] == "cp-notifications")
        mine = [e for e in page["notInAgreement"] if e["supplyId"] == n2]
        assert {e["checkId"] for e in mine} >= set(CLIENT_REFS)
        assert all(e["reason"] == "not part of the agreement for 2025-Q1" for e in mine)


def test_dataset_names_are_the_fixtures():
    assert DATASET["cp_case_workers"] == "cp-case-workers"
    assert CP == "child-protection"
