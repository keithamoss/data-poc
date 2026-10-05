"""One processing pass handles what has arrived and finishes what is owed,
never generates data, and is what a scheduler calls (REQ-PIPE-151)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import processing_pass as pp
from qa_tools.common import promotion, qa_store, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
WHEN = "2026-09-28T10:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-processing-pass") as c:
        qa_store.ensure_schema(c)
        yield c


def _dataset() -> str:
    return f"cp-{uuid.uuid4().hex[:12]}"


def _staged(conn, logical: str) -> str:
    physical = f"{logical}__a{uuid.uuid4().hex[:8]}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    return physical


def _gate(conn, dataset_id, *, status="fail", period="2099-Q1", staged=True,
          actor_kind=dl.RULE, held=False):
    supply = f"{dataset_id}@2099010100000000"
    item = {"dataset_id": dataset_id, "supply": supply, "period": period, "held": held,
            "physical_tables": [_staged(conn, dataset_id.replace("-", "_"))] if staged else []}
    out = promotion.after_run(
        conn, agency_id=AGENCY, collection_id=COLLECTION, supplies=[item],
        results=[{"dataset_id": dataset_id, "status": status,
                  "check_id": f"{dataset_id}.rowcount_dbt"}],
        reads={}, actor="pipeline", actor_kind=actor_kind, effective_at=WHEN)
    return out, supply


def _refusals(conn, dataset_id):
    return conn.execute(
        f"SELECT supply, to_slot, reason, actor_kind FROM {dl.TABLE} "
        "WHERE dataset_id = ? AND action = ?", [dataset_id, dl.PROMOTION_REFUSED]).fetchall()


class TestTheGateRecordsEveryRefusal:
    """Criteria 3, 4, 5 and 19."""

    def test_a_red_supply_is_recorded_once_with_its_reason(self, conn):
        ds = _dataset()
        out, supply = _gate(conn, ds)
        assert ds in out.refused
        (row,) = _refusals(conn, ds)
        assert row[0] == supply and row[1] == "2099-Q1" and row[3] == dl.RULE
        assert "red" in row[2]
        _gate(conn, ds)
        assert len(_refusals(conn, ds)) == 1, "a second gate over the same supply adds nothing"

    def test_a_refusal_changes_no_slot(self, conn):
        ds = _dataset()
        _gate(conn, ds)
        assert dl.held(conn, ds, "2099-Q1") is None

    def test_a_supply_filed_to_no_period_is_recorded_with_no_slot(self, conn):
        ds = _dataset()
        out, _ = _gate(conn, ds, period=None, held=True)
        (row,) = _refusals(conn, ds)
        assert row[1] is None and ds in out.refused

    def test_a_refusal_never_ends_the_hold_it_reports(self, conn):
        from qa_tools.common import supply_holds

        ds = _dataset()
        supply = f"{ds}@2099010100000000"
        supply_holds.raise_hold(conn, dataset_id=ds, supply_id=supply,
                                kind=supply_holds.ASSIGNMENT_RULE, reason={},
                                raised_by="t", delivery="d")
        _gate(conn, ds, period=None, held=True)
        assert supply_holds.hold_on(conn, ds, supply) is not None
        assert conn.execute("SELECT resolved_by FROM qa.hold WHERE dataset_id = ?",
                            [ds]).fetchone()[0] is None

    def test_nothing_staged_reads_could_not_be_loaded(self, conn):
        ds = _dataset()
        out, _ = _gate(conn, ds, status="pass", staged=False)
        assert "could not be loaded" in out.refused[ds]
        assert "could not be loaded" in _refusals(conn, ds)[0][2]

    def test_only_the_rule_records_one(self, conn):
        ds = _dataset()
        _gate(conn, ds, actor_kind=dl.PERSON)
        assert _refusals(conn, ds) == []

    def test_it_is_an_automatic_action_and_a_refusal(self):
        assert dl.PROMOTION_REFUSED in dl.AUTOMATIC_ACTIONS
        assert dl.PROMOTION_REFUSED in dl.RECORDS_A_REFUSAL


def _arrival(table="cp_clients", dataset="cp-clients", when=None, run_id=None):
    when = when or datetime(2099, 1, 1, tzinfo=timezone.utc)
    from qa_tools.common import asset_time

    key = asset_time.arrival_key(when)
    return SimpleNamespace(run_id=run_id or f"{table}__{key}", received_at=when,
                           files_by_dataset={dataset: (f"{table}.csv",)},
                           collection_id=COLLECTION, sequence=1)


class TestProcessedIsDerived:
    """Criteria 2, 4 and 8."""

    def test_the_three_states(self):
        a = _arrival()
        ds, base = pp.supply_of(a)
        rec = pp.Recorded()
        assert pp.state_of(a, rec) == pp.UNCHECKED
        rec.completed_runs.add(a.run_id)
        assert pp.state_of(a, rec) == pp.UNGATED
        rec.gated.add((ds, base))
        assert pp.state_of(a, rec) == pp.PROCESSED

    def test_an_open_hold_counts_as_gated(self):
        a = _arrival()
        rec = pp.Recorded(completed_runs={a.run_id}, held={pp.supply_of(a)})
        assert pp.state_of(a, rec) == pp.PROCESSED

    def test_a_contested_supplys_suffix_is_its_arrival(self, conn):
        """`cp-clients@<key>#1` is the same arrival as `cp-clients@<key>`."""
        assert pp._base("cp-clients@2099010100000000#1") == "cp-clients@2099010100000000"

    def test_it_is_one_read(self, conn, monkeypatch):
        calls = {"n": 0}
        real = supply_db.SupplyConnection.execute

        def counting(self, *a, **k):
            calls["n"] += 1
            return real(self, *a, **k)
        monkeypatch.setattr(supply_db.SupplyConnection, "execute", counting)
        pp.recorded(conn)
        assert calls["n"] == 1

    def test_a_real_gate_outcome_reads_as_processed(self, conn):
        ds = _dataset()
        _gate(conn, ds)
        rec = pp.recorded(conn)
        assert (ds, f"{ds}@2099010100000000") in rec.gated


class TestTheGateOnlyPathFeedsTheGateItsResults:
    """Criterion 2's 'checked but not gated' - the defect the first real pass
    found: recorded rows say run_key, the gate matches on run_id, and every
    result was dropped."""

    def test_the_recorded_results_reach_the_gate(self, clean_qa_history, finish_runs,
                                                 monkeypatch):
        from qa_tools.common.qa_results_writer import write_qa_result

        a = _arrival(run_id=f"cp_clients__{uuid.uuid4().int % 10**16:016d}")
        write_qa_result(AGENCY, COLLECTION, a.run_id, WHEN, "soda", {"hasErrors": False},
                        [{"check_id": f"x.y.{COLLECTION}.cp-clients.col.missing_soda",
                          "dataset_id": "cp-clients", "run_id": a.run_id, "status": "fail"}],
                        run_by="a@b.c")
        finish_runs(a.run_id, agency=AGENCY, collection=COLLECTION, when=WHEN, run_by="a@b.c")
        seen = {}
        states = iter([pp.UNGATED, pp.PROCESSED])
        monkeypatch.setattr(pp, "state_of", lambda arrival, rec: next(states))
        fake = SimpleNamespace(STEPS=SimpleNamespace(
            promote_after=lambda arrival, got, run_by: seen.setdefault("got", got)))
        monkeypatch.setattr(pp, "_modules", lambda collection: (fake, None))
        report = pp.PassReport()
        pp._one(a, [a], WHEN, "a@b.c", report, say=lambda m: None)
        assert seen["got"] and all(r["run_id"] == a.run_id for r in seen["got"])
        assert report.gated_only == [a.run_id] and report.red


class TestTheLocks:
    """Criteria 6 and 16."""

    def test_a_second_pass_is_refused_naming_the_first(self, supply_dsn):
        with pp.pass_lock("process"):
            with pytest.raises(pp.PassLockHeld, match="mothman pipeline process"):
                with pp.pass_lock("bootstrap"):
                    pass
        with pp.pass_lock("run"):
            pass

    def test_one_arrival_is_processed_by_one_process(self, supply_dsn):
        with supply_db.connect(label="t1") as one, supply_db.connect(label="t2") as two:
            with pp.arrival_lock(one, "cp_clients__1") as mine:
                assert mine
                with pp.arrival_lock(two, "cp_clients__1") as theirs:
                    assert not theirs
                with pp.arrival_lock(two, "cp_clients__2") as other:
                    assert other
            with pp.arrival_lock(two, "cp_clients__1") as now:
                assert now


class TestExitStatus:
    """Criterion 20: 2 outranks 1."""

    def test_codes(self):
        assert pp.PassReport().exit_status == pp.EXIT_OK
        assert pp.PassReport(red=True).exit_status == pp.EXIT_RED
        assert pp.PassReport(red=True, failures=[("x", "y")]).exit_status == pp.EXIT_FAILED
        assert pp.EXIT_LOCKED == 75

    def test_the_help_states_them(self):
        from click.testing import CliRunner

        from cli.app import cli

        out = CliRunner().invoke(cli, ["pipeline", "process", "--help"]).output
        for code in ("0", "1", "2", "75"):
            assert f"  {code} " in out


class TestTheCommandGeneratesNothing:
    """Criteria 10 and 17: the pass reads; run and bootstrap regenerate."""

    def test_no_generator_is_imported(self):
        import inspect

        source = inspect.getsource(pp)
        assert "generate_synthetic_data" not in source
        assert "from generator" not in source and "import generator" not in source


class TestATypedIdWhereTheEnvironmentAsksForIt:
    """REQ-PIPE-093 criterion 15: a person at a terminal types the id in
    production; a scheduler, with no terminal, is never asked."""

    def _run(self, monkeypatch, *, env, tty, answer=True):
        import sys

        from cli import pipeline

        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", env)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: tty)
        asked, ran = [], []

        @__import__("contextlib").contextmanager
        def no_lock(command):
            yield
        monkeypatch.setattr(pp, "pass_lock", no_lock)
        monkeypatch.setattr(pp, "run_pass", lambda **k: ran.append(1) or pp.PassReport())
        pipeline.run_process(confirm=lambda message, yes: asked.append(message) or answer)
        return asked, ran

    def test_production_at_a_terminal_asks(self, monkeypatch):
        asked, ran = self._run(monkeypatch, env="production", tty=True)
        assert len(asked) == 1 and ran

    def test_a_refusal_processes_nothing(self, monkeypatch):
        asked, ran = self._run(monkeypatch, env="production", tty=True, answer=False)
        assert asked and not ran

    def test_a_scheduler_is_never_asked(self, monkeypatch):
        asked, ran = self._run(monkeypatch, env="production", tty=False)
        assert asked == [] and ran

    def test_an_environment_that_does_not_ask_never_asks(self, monkeypatch):
        asked, ran = self._run(monkeypatch, env="sandbox", tty=True)
        assert asked == [] and ran


class TestATerminalKeepTakesTheArrivalLock:
    """Criterion 6 and REQ-PIPE-086 criterion 8, post-build-review #120 D1: a
    person keeping a supply at the terminal and a processing pass never
    process the same arrival at once - the race the critic reproduced, where
    each dropped the other's run schemas and both failed."""

    def _fake_steps(self, called):
        from qa_tools.common import arrival_lifecycle

        return arrival_lifecycle.Steps(
            file_and_overlay=lambda arrival, among: called.append("filed"),
            entry_for=lambda arrival: {}, run_one=lambda *a, **k: called.append("ran") or [],
            promote_after=lambda *a: called.append("gated"))

    @pytest.mark.parametrize("module", ["qa_tools.bdm.orchestrate_bdm",
                                        "qa_tools.cp.orchestrate_cp"])
    def test_an_arrival_another_process_holds_is_refused_untouched(self, supply_dsn,
                                                                   monkeypatch, module):
        import importlib

        from qa_tools.common import arrival_lifecycle

        orchestrator = importlib.import_module(module)
        called = []
        monkeypatch.setattr(orchestrator, "STEPS", self._fake_steps(called))
        a = _arrival(run_id=f"cp_clients__{uuid.uuid4().int % 10**16:016d}")
        a.run_index = 0
        with supply_db.connect(label="the-pass") as other:
            with pp.arrival_lock(other, a.run_id) as held:
                assert held
                with pytest.raises(arrival_lifecycle.StageFailed) as caught:
                    orchestrator.run_arrivals([a], run_by="me")
        assert called == [], "nothing was filed, checked or gated"
        assert caught.value.completed == ()
        assert "another process" in str(caught.value.cause)

    def test_an_arrival_it_holds_runs_and_the_lock_is_given_back(self, supply_dsn,
                                                                 monkeypatch):
        from qa_tools.bdm import orchestrate_bdm

        called = []
        monkeypatch.setattr(orchestrate_bdm, "STEPS", self._fake_steps(called))
        a = _arrival(run_id=f"cp_clients__{uuid.uuid4().int % 10**16:016d}")
        a.run_index = 0
        orchestrate_bdm.run_arrivals([a], run_by="me")
        assert called == ["filed", "ran", "gated"]
        with supply_db.connect(label="after") as conn, pp.arrival_lock(conn, a.run_id) as got:
            assert got

    def test_one_another_process_finished_meanwhile_is_not_processed_twice(
            self, supply_dsn, monkeypatch, clean_qa_history, finish_runs):
        from qa_tools.bdm import orchestrate_bdm
        from qa_tools.common import arrival_lifecycle

        called = []
        monkeypatch.setattr(orchestrate_bdm, "STEPS", self._fake_steps(called))
        a = _arrival(run_id=f"cp_clients__{uuid.uuid4().int % 10**16:016d}")
        a.run_index = 0
        finish_runs(a.run_id, agency=AGENCY, collection=COLLECTION, when=WHEN, run_by="x")
        with pytest.raises(arrival_lifecycle.StageFailed) as caught:
            orchestrate_bdm.run_arrivals([a], run_by="me")
        assert called == [] and "already" in str(caught.value.cause)


class _FakeBuilder:
    def __init__(self, fail_on=()):
        self.fail_on, self.staged = set(fail_on), []

    def stage_arrival(self, arrival):
        if arrival.run_id in self.fail_on:
            raise OSError("disk full")
        self.staged.append(arrival.run_id)


class TestThePassItself:
    """run_pass end to end over fakes for each stage it composes - criteria
    1, 9, 11, 12, 14 and 20, which the critic found had no automated test
    (post-build-review #120 D2 and its coverage note)."""

    @pytest.fixture
    def world(self, supply_dsn, monkeypatch):
        from qa_tools.common import delivery_log, recheck, ticket_reconciler

        bdm = _arrival("birth_registrations", "birth-registrations",
                       datetime(2099, 1, 1, 2, tzinfo=timezone.utc))
        bdm.collection_id = "civil-registration"
        cp_one = _arrival(when=datetime(2099, 1, 1, 1, tzinfo=timezone.utc))
        cp_two = _arrival("cp_carers", "cp-carers", datetime(2099, 1, 1, 3, tzinfo=timezone.utc))
        world = SimpleNamespace(arrivals=[cp_one, bdm, cp_two], builder=_FakeBuilder(),
                                processed=[], owed=[], tickets=None, one_fails=set())
        monkeypatch.setattr(delivery_log, "record_all", lambda: None)
        monkeypatch.setattr(pp, "all_arrivals", lambda: list(world.arrivals))
        monkeypatch.setattr(pp, "unprocessed", lambda found, conn=None: list(found))
        monkeypatch.setattr(pp, "state_of", lambda arrival, rec: pp.UNCHECKED)
        monkeypatch.setattr(pp, "_modules", lambda c: (None, world.builder))

        def one(arrival, among, ts, run_by, report, say):
            if arrival.run_id in world.one_fails:
                raise RuntimeError("dbt fell over")
            world.processed.append(arrival.run_id)
            report.processed.append(arrival.run_id)
        monkeypatch.setattr(pp, "_one", one)
        monkeypatch.setattr(recheck, "run_all_owed", lambda **k: list(world.owed))
        monkeypatch.setattr(ticket_reconciler, "service_from_env", lambda: world.tickets)
        return world

    def test_every_arrival_in_the_order_given(self, world):
        report = pp.run_pass(run_by="me", say=lambda m: None)
        assert world.processed == [a.run_id for a in world.arrivals]
        assert report.exit_status == pp.EXIT_OK
        assert "No ticketing is configured" in report.tickets[0]

    def test_a_staging_failure_holds_back_only_its_collection(self, world):
        cp_one, bdm, cp_two = world.arrivals
        world.builder.fail_on = {cp_one.run_id}
        report = pp.run_pass(run_by="me", say=lambda m: None)
        assert world.processed == [bdm.run_id], "the other collection carried on"
        assert report.left_behind_failure == [cp_two.run_id]
        assert report.failures[0][0] == cp_one.run_id and "disk full" in report.failures[0][1]
        assert report.exit_status == pp.EXIT_FAILED

    def test_an_arrival_failure_holds_back_only_its_collection(self, world):
        cp_one, bdm, cp_two = world.arrivals
        world.one_fails = {cp_one.run_id}
        report = pp.run_pass(run_by="me", say=lambda m: None)
        assert world.processed == [bdm.run_id]
        assert report.left_behind_failure == [cp_two.run_id]

    def test_a_locked_arrival_is_left_for_the_next_pass(self, world):
        cp_one = world.arrivals[0]
        with supply_db.connect(label="other") as other, pp.arrival_lock(other, cp_one.run_id):
            report = pp.run_pass(run_by="me", say=lambda m: None)
        assert report.left_locked == [cp_one.run_id] and cp_one.run_id not in world.processed

    @pytest.mark.parametrize("stage", ["record_all", "run_all_owed", "tickets", "all_arrivals"])
    def test_a_failure_at_any_pass_level_stage_exits_2(self, world, monkeypatch, stage):
        from qa_tools.common import delivery_log, recheck, ticket_reconciler

        def boom(*a, **k):
            raise RuntimeError("it broke")
        target = {"record_all": (delivery_log, "record_all"),
                  "run_all_owed": (recheck, "run_all_owed"),
                  "tickets": (ticket_reconciler, "service_from_env"),
                  "all_arrivals": (pp, "all_arrivals")}[stage]
        monkeypatch.setattr(*target, boom)
        report = pp.run_pass(run_by="me", say=lambda m: None)
        assert report.exit_status == pp.EXIT_FAILED
        assert any("it broke" in why for _, why in report.failures)

    def test_owed_work_is_run_and_a_failure_stays_owed(self, world):
        world.owed = [SimpleNamespace(owed_id=7, completed=False, message="no", status=None),
                      SimpleNamespace(owed_id=8, completed=True, message="", status="red")]
        report = pp.run_pass(run_by="me", say=lambda m: None)
        assert report.failures == [("owed #7", "no")] and report.red


class TestARefusalAfterTheSupplyMovedIsStillRecorded:
    """Criterion 3, post-build-review #120 D7: the once-only check skipped a
    refusal whenever the supply had EVER been promoted or withheld, so a
    supply promoted, then demoted by a person and refused on its re-check
    left no entry - and the kept-run report went on saying "promoted"."""

    def _refuse(self, conn, ds, supply, when, reason="status is red"):
        promotion._record_refused(conn, agency_id=AGENCY, collection_id=COLLECTION,
                                  dataset_id=ds, supply=supply, period="2099-Q1",
                                  reason=reason, effective_at=when)

    def _apply(self, conn, ds, supply, action, when, **over):
        fields = dict(agency_id=AGENCY, collection_id=COLLECTION, dataset_id=ds,
                      action=action, supply=supply, actor="keith@example.gov.au",
                      actor_kind=dl.PERSON, effective_at=when, to_slot="2099-Q1")
        fields.update(over)
        with dl.apply_decision(conn, dl.Decision(**fields)):
            pass

    def test_promoted_then_demoted_then_refused(self, conn):
        ds = _dataset()
        supply = f"{ds}@2099010100000000"
        self._apply(conn, ds, supply, dl.PROMOTE, "2099-01-02T00:00:00+08:00")
        self._refuse(conn, ds, supply, "2099-01-03T00:00:00+08:00")
        assert _refusals(conn, ds) == [], "a re-gate over its own promotion is no refusal"
        self._apply(conn, ds, supply, dl.DEMOTE, "2099-01-04T00:00:00+08:00", to_slot=None,
                    from_slot="2099-Q1", reason="withdrawn by the supplier")
        self._refuse(conn, ds, supply, "2099-01-05T00:00:00+08:00")
        assert len(_refusals(conn, ds)) == 1

    def test_the_same_refusal_again_is_still_once(self, conn):
        ds = _dataset()
        supply = f"{ds}@2099010100000000"
        self._refuse(conn, ds, supply, "2099-01-03T00:00:00+08:00")
        self._refuse(conn, ds, supply, "2099-01-04T00:00:00+08:00")
        assert len(_refusals(conn, ds)) == 1
        self._refuse(conn, ds, supply, "2099-01-05T00:00:00+08:00", reason="slot filled")
        assert len(_refusals(conn, ds)) == 2
