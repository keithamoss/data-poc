"""A check may read another collection's table, from the warehouse only,
through one shared resolver (REQ-PIPE-331 criteria 3, 5, 6 and 9).

Driven through the real callers - orchestrate.file_and_overlay,
recheck.execute and gate._warehouse - with the period overlay and the
decision log stood in for, so each caller is seen asking the one resolver
rather than its own collection's list.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qa_tools.common import run_reads


class TestTheOneResolver:
    def test_a_product_reads_each_linked_table_as_foreign(self):
        reads = run_reads.reads_for("linkage-products")
        assert reads.own == ("linkage_keys",)
        assert reads.foreign == ("cp_clients", "ed_presentations")

    def test_a_collection_reading_only_its_own_tables_has_no_foreign(self):
        for coll in ("child-protection", "emergency-department", "civil-registration"):
            reads = run_reads.reads_for(coll)
            assert reads.own, coll
            assert reads.foreign == (), coll

    def test_foreign_readers_of_a_linked_table(self):
        assert run_reads.foreign_readers("cp_clients") == ["linkage-products"]
        assert run_reads.foreign_readers("ed_presentations") == ["linkage-products"]
        assert run_reads.foreign_readers("linkage_keys") == []
        assert run_reads.foreign_readers("no_such_table") == []


class TestTheOverlayIsGivenTheForeignTablesFromTheWarehouse:
    """Criterion 3: file_and_overlay asks the resolver."""

    def test_file_and_overlay(self, monkeypatch):
        from qa_tools.common import filing, period_overlay
        from qa_tools.tools import orchestrate

        seen = {}
        monkeypatch.setattr(filing, "file_arrivals", lambda arrivals: None)
        monkeypatch.setattr(period_overlay, "rebuild_for_arrival",
                            lambda arrival, **kw: seen.update(kw))
        arrival = SimpleNamespace(run_id="linkage_keys__x", received_at=None, sequence=0,
                                  run_index=0, files_by_dataset={"linkage-keys": ()})
        orchestrate.file_and_overlay("linkage-products", arrival, among=[arrival])
        assert seen["tables"] == ["linkage_keys", "cp_clients", "ed_presentations"]
        assert seen["foreign"] == ("cp_clients", "ed_presentations")

    def test_an_own_only_collection_is_unchanged(self, monkeypatch):
        from qa_tools import collections
        from qa_tools.common import filing, period_overlay
        from qa_tools.tools import orchestrate

        seen = {}
        monkeypatch.setattr(filing, "file_arrivals", lambda arrivals: None)
        monkeypatch.setattr(period_overlay, "rebuild_for_arrival",
                            lambda arrival, **kw: seen.update(kw))
        arrival = SimpleNamespace(run_id="cp_clients__x", received_at=None, sequence=0,
                                  run_index=0, files_by_dataset={"cp-clients": ()})
        orchestrate.file_and_overlay("child-protection", arrival, among=[arrival])
        assert seen["tables"] == [d.table for d in collections.by_id("child-protection").datasets]
        assert seen["foreign"] == ()


class TestTheGatesWarehouseViewNamesForeignTables:
    """Criterion 9: gate._warehouse includes every table a reader reads."""

    def test_warehouse_includes_the_linked_tables(self, monkeypatch):
        from qa_tools.common import decision_log, gate

        held = SimpleNamespace(holder="cp-clients@1", held_as=decision_log.PROMOTED)
        monkeypatch.setattr(decision_log, "held",
                            lambda conn, ds, period: held if ds == "cp-clients" else None)
        member = SimpleNamespace(dataset_id="linkage-keys")
        tables = gate._warehouse(None, "2026-Q2", {("linkage-keys", "s"): member})
        assert tables["cp_clients"] == "cp-clients@1"
        assert "ed_presentations" in tables and tables["ed_presentations"] is None
        assert "linkage_keys" in tables


class TestJoinPassesOverAnotherCollectionsSupply:
    """Criterion 6: a recorded read naming another collection's supply never
    joins it to the application."""

    def test_join(self, monkeypatch):
        from qa_tools.common import gate, supply_status

        monkeypatch.setattr(supply_status, "_shown", lambda conn, ds, s: [{"reads": {
            "cp_clients": {"state": "read", "supply_id": "cp-clients@1"}}}])
        monkeypatch.setattr(supply_status, "dataset_of", lambda t: "cp-clients")
        called = []
        monkeypatch.setattr(gate, "joinable", lambda *a: called.append(a) or {})
        from qa_tools.common import qa_store
        monkeypatch.setattr(qa_store, "READ", "read")
        member = SimpleNamespace(dataset_id="linkage-keys", supply="linkage-keys@1",
                                 key=("linkage-keys", "linkage-keys@1"))
        members = {member.key: member}
        gate._join(None, members, "2026-Q2")
        assert called == []
        assert list(members) == [member.key]


@pytest.mark.parametrize("coll", ["linkage-products"])
def test_recheck_execute_asks_the_resolver(coll, monkeypatch):
    """Criterion 3: recheck.execute's tables and warehouse_for come from the
    resolver too."""
    from qa_tools.common import filing, period_overlay, recheck, supply_db

    class _C:
        def execute(self, *a):
            return SimpleNamespace(fetchall=lambda: [("2026-Q2", "d")])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(supply_db, "connect", lambda **kw: _C())
    from datetime import UTC, datetime
    monkeypatch.setattr(filing, "received_at_of", lambda *a: datetime(2026, 5, 1, tzinfo=UTC))
    seen = {}

    class _Stop(Exception):
        pass

    def _rebuild(arrival, **kw):
        seen.update(kw)
        raise _Stop

    monkeypatch.setattr(period_overlay, "rebuild_for_arrival", _rebuild)
    from qa_tools.tools import orchestrate
    monkeypatch.setattr(orchestrate, "discard_run_schemas", lambda k: None)
    with pytest.raises(_Stop):
        recheck.execute(dataset_id="linkage-keys", supply_id="linkage-keys@1",
                        run_key="linkage_keys__r", purpose={})
    assert seen["tables"] == ["linkage_keys", "cp_clients", "ed_presentations"]
    assert seen["foreign"] == ("cp_clients", "ed_presentations")


LP = "data-asset-1.department-of-health.linkage-products.linkage-keys.cp-clients.referential_soda"


class TestADeclaredReadAcrossCollectionsIsGated:
    """Criterion 2, from configuration."""

    def test_the_real_declarations_pass(self):
        assert run_reads.declaration_problems() == []

    def test_a_table_no_dataset_owns(self):
        [p] = run_reads.declaration_problems({LP: ["no_such_table"]})
        assert LP in p and "no_such_table" in p and "no dataset" in p

    def test_a_dataset_on_another_calendar(self):
        [p] = run_reads.declaration_problems({LP: ["birth_registrations"]})
        assert LP in p and "birth_registrations" in p and "daily" in p and "quarterly" in p

    def test_a_dataset_with_no_calendar(self, monkeypatch):
        from qa_tools.common import schedule

        real = schedule.calendar_for_dataset

        def _none(dataset_id, agreement=None):
            if dataset_id == "cp-clients":
                raise schedule.NoCalendarAgreed(dataset_id, "a test")
            return real(dataset_id, agreement)

        monkeypatch.setattr(schedule, "calendar_for_dataset", _none)
        [p] = run_reads.declaration_problems({LP: ["cp_clients"]})
        assert "names no calendar" in p and "cp-clients" in p

    def test_a_read_within_the_collection_is_not_this_gates(self):
        own = "data-asset-1.department-of-health.linkage-products.linkage-keys.x.y_soda"
        assert run_reads.declaration_problems({own: ["linkage_keys"]}) == []


class TestAContendedCollectionDoesNotStopTheOthers:
    """Criterion 10: knock_on.complete re-gates every other collection's
    readers and keeps the item owed for the contended one."""

    def test_complete(self, monkeypatch):
        from qa_tools.common import (agreement_drift, decision_log, gate, knock_on,
                                     recheck, supply_db, supply_files)

        class _C:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(supply_db, "connect", lambda **kw: _C())
        readers = [knock_on.Reader("cp-clients", "cp-clients@1", True),
                   knock_on.Reader("linkage-keys", "linkage-keys@1", True)]
        monkeypatch.setattr(knock_on, "readers", lambda *a: readers)
        monkeypatch.setattr(agreement_drift, "refusals", lambda conn, ids: {})
        monkeypatch.setattr(knock_on, "_failing_checks", lambda *a: frozenset())
        monkeypatch.setattr(decision_log, "follows", lambda conn, d: None)
        monkeypatch.setattr(supply_files, "tables_in", lambda *a: ())
        monkeypatch.setattr(supply_files, "open_contest", lambda *a: None)
        applied = []

        def _apply(collection_id, period, **kw):
            applied.append(collection_id)
            return SimpleNamespace(contended=collection_id == "child-protection", failed={},
                                   refused={}, promoted=[], held_back=[], frozen=[],
                                   not_judged={})

        monkeypatch.setattr(gate, "apply", _apply)
        monkeypatch.setattr(gate, "report", lambda a: None)
        cleared = []
        monkeypatch.setattr(recheck, "clear", lambda *a: cleared.append(a))
        item = SimpleNamespace(id=1, period="2026-Q2", tables=["cp_clients"],
                               caused_by_decision="d")
        out = knock_on.complete(item)
        assert applied == ["child-protection", "linkage-products"]
        assert out.contended and not out.completed
        assert "child-protection" in out.message
        assert cleared == []


class TestARunnerTreatsAnAbsentForeignTableAsAbsent:
    """Criterion 8, found by the first bootstrap with Linkage Products: Soda
    and datacontract-cli worked out what a run could not read from its OWN
    collection's tables only, so a check reading another collection's absent
    table was handed to the tool and raised 'relation does not exist'."""

    def test_unreadable_names_the_foreign_tables_without_a_view(self, monkeypatch):
        from qa_tools.common import supply_db

        monkeypatch.setattr(supply_db, "readable_in", lambda conn, run_id: {"linkage_keys"})
        got = run_reads.unreadable_in(None, "linkage-products", "linkage_keys__x")
        assert got == frozenset({"cp_clients", "ed_presentations"})

    def test_soda_and_datacontract_ask_it(self):
        import inspect

        from qa_tools.tools import run_datacontract, run_soda

        # An architecture rule, by source: both runners take their unreadable
        # set from the one resolver rather than a list of their own.
        assert "run_reads.unreadable_in" in inspect.getsource(run_soda.evaluate)
        assert "run_reads.unreadable_in" in inspect.getsource(run_datacontract._unreadable_in)
