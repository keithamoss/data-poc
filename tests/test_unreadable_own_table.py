"""A run that cannot read its OWN table runs no tool and records no
per-check result (REQ-PIPE-115 criteria 5, 6 and 9).

THE DEFECT (post-build-review #77, gap 2): a held Child Protection
supply's run kept the views staging gave it, because the period overlay
returns early for a supply filed to no period - so its own table stayed
readable, all four tools ran, and every one of the nine held Case
Workers supplies in a real bootstrap had ordinary tool verdicts recorded
against a supply nobody had placed. Asserted at qa.check_result, the
layer that records, because the helpers were right and the recording
was wrong.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import qa_tools.bdm.orchestrate_bdm as orchestrate_bdm
import qa_tools.cp.orchestrate_cp as orchestrate_cp
from qa_tools.common import own_table, supply_db

OWN = "cp_case_workers"


def _recorded(run_id: str) -> dict[str, int]:
    with supply_db.connect(read_only=True, label="test-own-table") as conn:
        return dict(conn.execute(
            'SELECT tool, COUNT(*) FROM "qa".check_result '
            "WHERE run_key LIKE ? GROUP BY tool", [f"%{run_id}"]).fetchall())


def _cp_run(**views) -> tuple[str, dict]:
    from conftest import clone_run_views
    from fixture_ids import CP_REF_RUN_ID

    mine = f"{OWN}__t{uuid.uuid4().hex[:12]}"
    with supply_db.connect(label="test-own-table") as conn:
        clone_run_views(conn, CP_REF_RUN_ID, mine, **views)
    entry = {"run_id": mine, "run_index": 1, "received_at": "2026-01-01T06:00:00+00:00",
             "delivery": "d", "files": {}}
    return mine, entry


class TestAChildProtectionRunWhoseOwnTableIsUnreadable:
    """Criteria 5 and 6, for both ways an arrival can bring it."""

    @pytest.mark.parametrize("how", ["held", "contested"])
    def test_no_tool_runs_and_no_per_check_result_is_recorded(self, how, cp_duckdb_dir):
        mine, entry = _cp_run(**{how: {OWN}})
        results = orchestrate_cp._run_one(entry, "2026-01-01T09:00:00Z", "t@example.com",
                                          reference_run_id=None)
        assert results == []
        recorded = _recorded(mine)
        assert recorded == {}, (
            f"a run whose own table is {how} recorded {recorded} - verdicts against a "
            f"supply nobody could place")

    def test_a_readable_own_table_is_still_checked(self, cp_duckdb_dir):
        """The guard must not switch checking off for an ordinary run."""
        mine, entry = _cp_run()
        orchestrate_cp._run_one(entry, "2026-01-01T09:00:00Z", "t@example.com",
                                reference_run_id=None)
        assert set(_recorded(mine)) >= {"dbt", "soda"}


class TestAnyOtherReasonIsAFailedRun:
    """Criterion 9: missing, and not held, contested or refused at load."""

    def test_a_birth_registrations_run_with_its_table_simply_absent_raises(
            self, bdm_duckdb_dir):
        from conftest import clone_run_views
        from fixture_ids import BDM_REF_RUN_ID

        mine = f"bdm_absent_{uuid.uuid4().hex[:8]}"
        with supply_db.connect(label="test-own-table") as conn:
            clone_run_views(conn, BDM_REF_RUN_ID, mine, absent={"birth_registrations"})
        entry = {"run_id": mine, "run_index": 1, "csv_path": "unused.csv",
                 "received_at": "2026-01-01T06:00:00+00:00", "delivery": "d"}
        with pytest.raises(own_table.UnreadableOwnTable, match="birth_registrations"):
            orchestrate_bdm._run_one(entry, "2026-01-01T09:00:00Z", "t@example.com",
                                     reference_run_id=None)

    def test_a_refused_load_is_not_a_failed_run(self, monkeypatch):
        res = supply_db.Resolution(run_id="r", schema="s", absent=[OWN])
        monkeypatch.setattr(supply_db, "readable_in", lambda conn, run_id: frozenset())
        from qa_tools.common import load_log
        monkeypatch.setattr(load_log, "latest_by_table", lambda *a, **k: {"x": SimpleNamespace(
            dataset_id="cp-case-workers", physical=f"{OWN}__202601010600000000", loaded=False)})
        assert own_table.why_unreadable(
            None, "r", OWN, res, own_dataset="cp-case-workers",
            arrival_key="202601010600000000") == own_table.REFUSED

    def test_held_and_contested_are_named(self, monkeypatch):
        monkeypatch.setattr(supply_db, "readable_in", lambda conn, run_id: frozenset({OWN}))
        held = supply_db.Resolution(run_id="r", schema="s", held={OWN: "x"})
        contested = supply_db.Resolution(run_id="r", schema="s", ambiguous={OWN: ["a", "b"]})
        assert own_table.why_unreadable(None, "r", OWN, held) == own_table.HELD
        assert own_table.why_unreadable(None, "r", OWN, contested) == own_table.CONTESTED, (
            "a contested table whose view fell through to the period's promoted version is "
            "still not this arrival's supply")


class TestTheOverlayWithholdsAHeldSupplysOwnTable:
    """Criterion 5's cause: a held supply has no period, so the overlay
    used to return early and leave staging's view of the held table in
    place, readable."""

    def test_the_own_table_is_withheld_and_recorded_as_held(self, cp_duckdb_dir):
        from qa_tools.common import period_overlay, supply_holds

        mine, _ = _cp_run()
        key = f"t{uuid.uuid4().hex[:12]}"
        # An instant nothing in the fixture filed, so the supply has no period.
        n = uuid.uuid4().int
        received = f"2031-01-01T{n % 24:02d}:{n // 24 % 60:02d}:{n // 1440 % 60:02d}+00:00"
        arrival = SimpleNamespace(files_by_dataset={"cp-case-workers": ("f.csv",)},
                                  received_at=received, run_id=mine)
        with supply_db.connect(label="test-own-table") as conn:
            assert OWN in supply_db.readable_in(conn, mine)
            supply_holds.raise_hold(
                conn, dataset_id="cp-case-workers",
                supply_id=f"cp-case-workers@{supply_db.arrival_segment(received)}",
                kind=supply_holds.ASSIGNMENT_RULE, reason={"why": key}, raised_by="test")
        try:
            period_overlay.rebuild_for_arrival(arrival, tables=["cp_case_workers"])
            with supply_db.connect(read_only=True, label="test-own-table") as conn:
                assert OWN not in supply_db.readable_in(conn, mine)
                assert OWN in supply_db.resolution_for(conn, mine).held
        finally:
            with supply_db.connect(label="test-own-table") as conn:
                conn.execute("DELETE FROM qa.hold WHERE dataset_id = 'cp-case-workers' "
                             "AND supply_id = ?",
                             [f"cp-case-workers@{supply_db.arrival_segment(received)}"])


class TestASiblingHeldInTheSameArrivalIsNamedHeld:
    """Criterion 14: a run of an arrival received WITH a held supply says
    held for its table, not absent - and only such a run (option B)."""

    @pytest.fixture
    def hold(self, supply_dsn):
        from qa_tools.common import qa_store, supply_holds

        received = "2031-02-03T04:05:06+00:00"
        supply = f"cp-carers@{supply_db.arrival_segment(received)}"
        with supply_db.connect(label="test-own-table") as conn:
            qa_store.ensure_schema(conn)
            conn.execute("DELETE FROM qa.hold WHERE dataset_id = 'cp-carers'")
            supply_holds.raise_hold(conn, dataset_id="cp-carers", supply_id=supply,
                                    kind=supply_holds.ASSIGNMENT_RULE, reason={},
                                    raised_by="t", delivery="the-zip")
            yield conn, received, supply
            conn.execute("DELETE FROM qa.hold WHERE dataset_id = 'cp-carers'")

    def _res(self):
        return supply_db.Resolution(run_id="r", schema="s", resolved={OWN: "x"},
                                    absent=["cp_carers"])

    def test_same_receipt_instant(self, hold):
        from qa_tools.common import period_overlay

        conn, received, supply = hold
        res = self._res()
        arrival = SimpleNamespace(received_at=received, delivery_name="another")
        assert period_overlay.name_held_siblings(conn, res, arrival) == ["cp_carers"]
        assert res.held == {"cp_carers": supply} and res.absent == []

    def test_same_delivery(self, hold):
        from qa_tools.common import period_overlay

        conn, _, _ = hold
        res = self._res()
        arrival = SimpleNamespace(received_at="2031-02-03T09:00:00+00:00",
                                  delivery_name="the-zip")
        assert period_overlay.name_held_siblings(conn, res, arrival) == ["cp_carers"]

    def test_an_arrival_received_apart_from_it_still_reads_absent(self, hold):
        from qa_tools.common import period_overlay

        conn, _, _ = hold
        res = self._res()
        arrival = SimpleNamespace(received_at="2031-05-03T09:00:00+00:00",
                                  delivery_name="later")
        assert period_overlay.name_held_siblings(conn, res, arrival) == []
        assert res.absent == ["cp_carers"]

    def test_a_readable_sibling_is_left_readable(self, hold):
        from qa_tools.common import period_overlay

        conn, received, _ = hold
        res = supply_db.Resolution(run_id="r", schema="s",
                                   resolved={OWN: "x", "cp_carers": "promoted"})
        period_overlay.name_held_siblings(
            conn, res, SimpleNamespace(received_at=received, delivery_name="the-zip"))
        assert "cp_carers" in res.resolved and not res.held


class TestARunWhoseOwnTableCouldNotBeLoaded:
    """REQ-DASH-148 criterion 5: no tool, no per-check result for its own
    checks, and the run completes rather than failing."""

    def test_it_completes_having_checked_nothing(self, cp_duckdb_dir):
        from conftest import clone_run_views
        from fixture_ids import CP_REF_RUN_ID
        from qa_tools.common import load_log

        received = "2031-03-03T03:03:03+00:00"
        key = supply_db.arrival_segment(received)
        mine = f"{OWN}__{key}"
        with supply_db.connect(label="test-own-table") as conn:
            clone_run_views(conn, CP_REF_RUN_ID, mine, absent={OWN})
            load_log.record("refused-drop", "cp-case-workers", f"{OWN}__{key}",
                            load_log.FAILED, received, reason="the file is empty", conn=conn)
        entry = {"run_id": mine, "run_index": 1, "received_at": received,
                 "delivery": "refused-drop", "files": {}}
        results = orchestrate_cp._run_one(entry, received, "t@example.com",
                                          reference_run_id=None)
        assert results == [] and _recorded(mine) == {}


    def test_a_refused_table_that_fell_through_is_still_refused(self, cp_duckdb_dir):
        """REAL DEFECT (post-build-review #124 D2): once the overlay rebuilt the
        run over its period, a refused table FELL THROUGH to the period's
        promoted version, so it read as readable - all four tools ran against
        last period's table and recorded 78 passes under the refused file's
        run. Keith: a refused file records its file-check verdicts only."""
        from conftest import clone_run_views
        from fixture_ids import CP_REF_RUN_ID
        from qa_tools.common import load_log

        received = "2031-04-04T04:04:04+00:00"
        key = supply_db.arrival_segment(received)
        mine = f"{OWN}__{key}"
        with supply_db.connect(label="test-own-table") as conn:
            clone_run_views(conn, CP_REF_RUN_ID, mine)   # readable: it fell through
            load_log.record("refused-through", "cp-case-workers", f"{OWN}__{key}",
                            load_log.FAILED, received, reason="ragged row", conn=conn)
        entry = {"run_id": mine, "run_index": 1, "received_at": received,
                 "delivery": "refused-through", "files": {}}
        results = orchestrate_cp._run_one(entry, received, "t@example.com",
                                          reference_run_id=None)
        assert results == [] and _recorded(mine) == {}


class TestAContestedTableThatFellThroughIsReadable:
    """REAL DEFECT, found by REQ-PIPE-115 criterion 17's reconciliation on
    its first full bootstrap: a sibling with two versions staged for the
    period FALLS THROUGH to the period's promoted version (REQ-PIPE-079
    criterion 12), so it is both `resolved` and `ambiguous`. Soda asks the
    catalogue and checked it; dbt asked `Resolution.unreadable`, which
    counted every ambiguous name, and excluded its tests - which nobody
    then recorded, because the unrunnable rule correctly saw it readable.
    Two checks silently missing from cp_placements__202605270100000000."""

    def test_a_resolved_name_is_never_unreadable(self):
        res = supply_db.Resolution(run_id="r", schema="s",
                                   resolved={"cp_carers": "cp_carers__202605010100000000"},
                                   ambiguous={"cp_carers": ["a", "b"]}, absent=["cp_clients"])
        assert res.unreadable == ["cp_clients"]


class TestAnUnrelatedHoldDoesNotStopAFiledSupplyBeingChecked:
    """REAL DEFECT, found by the sprint-6 delivery-critic on supply6: an
    open hold on ONE of a dataset's supplies withheld the table from EVERY
    later run of that dataset (supply_holds.held_tables was dataset-wide),
    and REQ-PIPE-115's guard then ran no tool for them - eight on-time,
    filed Case Workers supplies with no QA at all, shown green in supply
    history. A hold is about one supply: its own arrival."""

    def test_held_tables_is_scoped_to_the_arrival(self, supply_dsn):
        from qa_tools.common import supply_holds

        with supply_db.connect(label="test-own-table") as conn:
            conn.execute("DELETE FROM qa.hold WHERE dataset_id = 'cp-case-workers'")
            supply_holds.raise_hold(conn, dataset_id="cp-case-workers",
                                    supply_id="cp-case-workers@202305010100000000",
                                    kind=supply_holds.ASSIGNMENT_RULE, reason={},
                                    raised_by="t")
            try:
                assert OWN in supply_holds.held_tables(
                    conn, arrival_key="202305010100000000")
                assert OWN not in supply_holds.held_tables(
                    conn, arrival_key="202308010100000000")
            finally:
                conn.execute("DELETE FROM qa.hold WHERE dataset_id = 'cp-case-workers'")

    def test_the_overlay_does_not_withhold_a_filed_supplys_table(self, monkeypatch,
                                                                  supply_dsn):
        from qa_tools.common import filing, period_overlay, supply_holds

        seen = {}
        monkeypatch.setattr(filing, "period_of", lambda ds, at: "2023-Q3")
        with supply_db.connect(label="test-own-table") as conn:
            conn.execute("DELETE FROM qa.hold WHERE dataset_id = 'cp-case-workers'")
            supply_holds.raise_hold(conn, dataset_id="cp-case-workers",
                                    supply_id="cp-case-workers@202305010100000000",
                                    kind=supply_holds.ASSIGNMENT_RULE, reason={},
                                    raised_by="t")

        def fake_build(conn, run_id, **kw):
            seen["held"] = set(kw["held"])
            raise RuntimeError("stop here")
        monkeypatch.setattr(period_overlay, "build", fake_build)
        arrival = SimpleNamespace(files_by_dataset={"cp-case-workers": ("f.csv",)},
                                  received_at="2023-08-01T01:00:00+00:00",
                                  run_id=f"{OWN}__202308010100000000", delivery_name="d")
        try:
            with pytest.raises(RuntimeError, match="stop here"):
                period_overlay.rebuild_for_arrival(arrival, tables=[OWN])
        finally:
            with supply_db.connect(label="test-own-table") as conn:
                conn.execute("DELETE FROM qa.hold WHERE dataset_id = 'cp-case-workers'")
        assert OWN not in seen["held"]


class TestAHeldSiblingDoesNotTakeAnyToolDown:
    """REQ-PIPE-078 criteria 9 and 10, end to end through all four tools.

    WHAT WAS LEFT: criterion 10's producer (held_blast_radius) was built and
    unit-tested on 2026-09-30, but a run with a held sibling died at dbt and,
    once dbt was fixed, at Soda - so nothing had ever reached it. Since then
    every tool leaves a check over an unreadable table out and says so
    (REQ-PIPE-079, REQ-PIPE-115). This runs the real tools over a Child
    Protection run whose OWN table is readable while cp_clients is held."""

    def test_the_run_completes_and_names_the_held_table(self, cp_duckdb_dir):
        """A PLACEMENTS run, because a run records only its own dataset's
        checks: Placements' client-reference checks read cp_clients, so its
        run is the one the held table costs (Case Workers' reads nothing
        there, which is how the first draft of this test passed vacuously)."""
        from conftest import clone_run_views
        from fixture_ids import CP_REF_RUN_ID

        mine = f"cp_placements__t{uuid.uuid4().hex[:12]}"
        with supply_db.connect(label="test-own-table") as conn:
            clone_run_views(conn, CP_REF_RUN_ID, mine, held={"cp_clients"})
        entry = {"run_id": mine, "run_index": 1, "received_at": "2026-01-01T06:00:00+00:00",
                 "delivery": "d", "files": {}}
        results = orchestrate_cp._run_one(entry, "2026-01-01T09:00:00Z", "t@example.com",
                                          reference_run_id=None)
        recorded = _recorded(mine)
        assert {"dbt", "soda"} <= set(recorded), (
            f"the tools did not all run over the readable tables: {recorded}")
        # CRITERION 10, AT THE LAYER THAT RECORDS: one red per check that
        # reads the held table, under the held pseudo-tool, naming it.
        assert recorded.get("held"), f"no check reading the held table was recorded: {recorded}"
        with supply_db.connect(read_only=True, label="test-own-table") as conn:
            named = conn.execute(
                'SELECT DISTINCT status, column_name FROM "qa".check_result '
                "WHERE run_key = ? AND tool = 'held'", [mine]).fetchall()
            # NO TOOL VERDICT about the held table itself (criterion 9).
            about_held = conn.execute(
                'SELECT tool, count(*) FROM "qa".check_result WHERE run_key = ? '
                "AND dataset_id = 'cp-clients' AND tool <> 'held' GROUP BY tool",
                [mine]).fetchall()
        assert named == [("fail", "cp_clients")]
        assert about_held == []
        assert results, "the run returned its results"
