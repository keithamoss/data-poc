"""A decision runs a supply's QA again, as a run of its own (REQ-PIPE-140).

Against the real tools: the dirty Child Protection fixture delivery is
staged and filed to 2026-Q2 by conftest's cp_duckdb_dir, and its
cp-placements supply is re-checked through the one executor.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from fixture_ids import CP_DIRTY_RUN_ID
from qa_tools.common import decision_log as dl, qa_store, recheck, supply_db

ROOT = Path(__file__).resolve().parent.parent
DATASET = "cp-placements"
SUPPLY = f"{DATASET}@{CP_DIRTY_RUN_ID.split('__')[1]}"


def _a_decision(conn) -> int:
    """A real decision to be the cause - criterion 4 names one."""
    return dl.record_automatic(conn, dl.Decision(
        agency_id="child-protection-family-support", collection_id="child-protection",
        dataset_id=DATASET, action=dl.PROMOTION_WITHHELD, supply=SUPPLY,
        actor="pytest", actor_kind=dl.RULE, effective_at="2026-04-02T00:00:00+00:00",
        to_slot="2026-Q2", reason="cause for a re-check"))


@pytest.fixture
def owed_one(cp_duckdb_dir, monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "pytest@example.org")
    with supply_db.connect(label="test-recheck") as conn:
        qa_store.ensure_schema(conn)
        with conn.raw.transaction():
            decision_id = _a_decision(conn)
            owed_id = recheck.owe(conn, dataset_id=DATASET, supply_id=SUPPLY,
                                  decision_id=decision_id)
    return owed_id, decision_id


class TestAReRunIsARunOfItsOwn:
    """Criteria 1, 3, 4 and 5, against the real tools."""

    def test_it_runs_records_its_cause_and_becomes_the_current_run(self, owed_one,
                                                                   monkeypatch):
        from qa_tools.common import promotion

        monkeypatch.setattr(promotion, "report", lambda outcome: None)
        owed_id, decision_id = owed_one
        with supply_db.connect(label="test-recheck") as conn:
            before = conn.execute(
                "SELECT count(*) FROM qa.check_result WHERE run_key = ?",
                [CP_DIRTY_RUN_ID]).fetchall()[0][0]
        got = recheck.run(owed_id, run_by="pytest@example.org")
        assert got.completed, got.message
        # A RUN ID OF ITS OWN (criterion 3) - the next `__r<N>`, whatever N:
        # another module on the same worker's fixture may have taken __r1.
        first, n = supply_db.split_run(got.run_key)
        assert first == CP_DIRTY_RUN_ID and n >= 1
        with supply_db.connect(label="test-recheck") as conn:
            row = conn.execute(
                "SELECT scope, dataset_id, supply_id, period, caused_by_decision, "
                "completed_at IS NOT NULL FROM qa.run WHERE run_key = ?",
                [got.run_key]).fetchall()[0]
            assert row == ("full", DATASET, SUPPLY, "2026-Q2", decision_id, True)
            assert conn.execute(
                "SELECT count(*) FROM qa.check_result WHERE run_key = ?",
                [got.run_key]).fetchall()[0][0] > 0
            # THE FIRST RUN'S RESULTS ARE UNTOUCHED (criterion 3).
            assert conn.execute(
                "SELECT count(*) FROM qa.check_result WHERE run_key = ?",
                [CP_DIRTY_RUN_ID]).fetchall()[0][0] == before
            assert qa_store.current_run(conn, DATASET, SUPPLY) == got.run_key
            # EVERY RESULT NAMES THE DECISION, never an arrival (criterion 4;
            # post-build-review #114 D6 - the readers' results named the
            # re-run's own key as the arrival that caused them).
            causes = conn.execute(
                "SELECT DISTINCT extra->>'reevaluated_after_arrival_of', "
                "extra->>'reevaluated_after_decision' FROM qa.check_result "
                "WHERE run_key = ?", [got.run_key]).fetchall()
            assert causes == [(None, str(decision_id))], causes
            assert recheck.owed(conn, DATASET) == [] or all(
                o.id != owed_id for o in recheck.owed(conn, DATASET))
            assert not supply_db.split_run(got.run_key)[1] == 0


class TestWhatIsOwed:
    """Criterion 7."""

    def test_owing_twice_for_one_cause_is_one_record(self, cp_duckdb_dir):
        with supply_db.connect(label="test-recheck") as conn:
            qa_store.ensure_schema(conn)
            decision_id = _a_decision(conn)
            a = recheck.owe(conn, dataset_id=DATASET, supply_id=SUPPLY,
                            decision_id=decision_id)
            b = recheck.owe(conn, dataset_id=DATASET, supply_id=SUPPLY,
                            decision_id=decision_id)
        assert a == b

    def test_one_cause_exactly(self, cp_duckdb_dir):
        with supply_db.connect(label="test-recheck") as conn:
            with pytest.raises(recheck.RecheckRefused, match="exactly one cause"):
                recheck.owe(conn, dataset_id=DATASET, supply_id=SUPPLY)

    def test_a_run_that_breaks_stays_owed_and_says_so(self, owed_one, monkeypatch):
        """Criterion 8: the decision stays, the earlier verdict stands."""
        from qa_tools.cp import orchestrate_cp

        def boom(*a, **k):
            raise RuntimeError("the tool fell over")
        monkeypatch.setattr(orchestrate_cp, "_run_one", boom)
        owed_id, _ = owed_one
        got = recheck.run(owed_id, run_by="pytest@example.org")
        assert not got.completed and "still owed" in got.message
        with supply_db.connect(label="test-recheck") as conn:
            (still,) = [o for o in recheck.owed(conn, DATASET) if o.id == owed_id]
            assert still.last_failure and "fell over" in still.last_failure


class TestOnlyFromTheOrchestratorPath:
    """Criterion 6: nothing on a read-committed-history path imports it."""

    def test_no_build_path_imports_the_executor(self):
        offenders = []
        for top in ("pipeline", "dashboard"):
            for path in sorted((ROOT / top).rglob("*.py")):
                for node in ast.walk(ast.parse(path.read_text())):
                    names = []
                    if isinstance(node, ast.ImportFrom):
                        names = [f"{node.module}.{a.name}" for a in node.names]
                    elif isinstance(node, ast.Import):
                        names = [a.name for a in node.names]
                    if any("recheck" in n for n in names):
                        offenders.append(str(path.relative_to(ROOT)))
        for path in (ROOT / "qa_tools").rglob("build_results_from_history.py"):
            if "recheck" in path.read_text():
                offenders.append(str(path.relative_to(ROOT)))
        assert offenders == []


class TestTwoOwedRunsNeverShareAnId:
    """post-build-review #114 D2: an id minted by an attempt that broke was
    not seen by the next mint, so two owed re-checks of one supply both
    took `__r1` - and the second's results would replace the first's."""

    def test_a_broken_attempts_id_is_not_minted_again(self, cp_duckdb_dir, monkeypatch):
        from qa_tools.common import period_overlay

        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "pytest@example.org")
        with supply_db.connect(label="test-recheck") as conn:
            qa_store.ensure_schema(conn)
            with conn.raw.transaction():
                first = recheck.owe(conn, dataset_id=DATASET, supply_id=SUPPLY,
                                    decision_id=_a_decision(conn))
                second = recheck.owe(conn, dataset_id=DATASET, supply_id=SUPPLY,
                                     decision_id=_a_decision(conn))

        def boom(*a, **k):
            raise RuntimeError("no overlay today")
        monkeypatch.setattr(period_overlay, "rebuild_for_arrival", boom)
        a = recheck.run(first, run_by="pytest@example.org")
        b = recheck.run(second, run_by="pytest@example.org")
        assert not a.completed and not b.completed
        assert a.run_key != b.run_key


class TestAPromotedSupplyRefiledIsCheckedInItsNewPeriod:
    """post-build-review #115 D4: re-filing a PROMOTED supply left a re-check
    that could not read its own table ('UnreadableOwnTable ... set up
    wrong'), so the supply had left its period and was never checked in the
    new one."""

    def test_the_owed_recheck_runs(self, cp_duckdb_dir, monkeypatch):
        from qa_tools.common import filing_decisions as fd, people, promotion

        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "pytest@example.org")
        monkeypatch.setattr(promotion, "report", lambda outcome: None)
        person = "fpycnkgvmt@privaterelay.appleid.com"
        with supply_db.connect(label="test-recheck") as conn:
            qa_store.ensure_schema(conn)
            promotion.promote(conn, agency_id="child-protection-family-support",
                              collection_id="child-protection", dataset_id=DATASET,
                              supply=SUPPLY, period="2026-Q2",
                              physical_tables=[recheck.first_run_id(DATASET, SUPPLY)],
                              actor=person, actor_kind=dl.PERSON,
                              effective_at="2026-04-02T00:00:00+00:00", reason="in")

            def ask(acknowledged=None):
                return fd.Request(operation=fd.REFILE, dataset_id=DATASET,
                                  actor=people.person_by_email(person), reason="belongs in Q1",
                                  period="2026-Q2", supply=SUPPLY, to_period="2026-Q1",
                                  confirmed=True, acknowledged=acknowledged)
            key = fd.consequences(conn, ask()).key
            got = fd.apply(ask(key), effective_at="2026-04-03T00:00:00+00:00", conn=conn)
        done = recheck.run(got.owed, run_by="pytest@example.org")
        assert done.completed, done.message


class TestTheGateTakesEffectWhenItsCauseDid:
    """post-build-review #116: a re-check's promotion was stamped with the
    wall clock, so a replayed un-supersede in 2024 promoted in 2026."""

    def test_it(self, owed_one, monkeypatch):
        from qa_tools.common import promotion

        seen = {}
        monkeypatch.setattr(recheck, "execute", lambda **k: (object(), []))
        monkeypatch.setattr(promotion, "after_runs",
                            lambda arrivals, results, **k: seen.update(k) or
                            promotion.AfterRun(promoted=(), refused={}, failed={}))
        monkeypatch.setattr(promotion, "report", lambda o: None)
        owed_id, _ = owed_one
        recheck.run(owed_id, run_by="pytest@example.org")
        assert seen["effective_at"].startswith("2026-04-02")


class TestOnAFreshDatabase:
    """Found by the sprint 12 gate (2026-10-05): every orchestrator's
    promote_after ends by running what is owed, which read qa.owed_run over
    a connection of its own without making sure the schema exists - so on a
    database no earlier call had prepared it crashed with UndefinedTable,
    and test_promotion_actor passed or failed by what ran before it on the
    same worker."""

    def test_nothing_owed_is_nothing_run(self, monkeypatch):
        import dbsupport

        dbsupport.use_empty_supply_db(monkeypatch)
        assert recheck.run_all_owed() == []


class TestALiveRecheckTakesEffectWhenItRan:
    """post-build-review #117 D7 (Keith, 2026-10-06): live, a re-check's
    promotion is recorded as in place when it ran, never at the earlier
    instant of the decision that owed it."""

    def test_three_hours_later_is_three_hours_later(self, supply_dsn, monkeypatch):
        import uuid
        from datetime import datetime, timedelta, timezone
        from types import SimpleNamespace

        from qa_tools.common import asset_time, qa_store, recheck, supply_db
        from qa_tools.common import decision_log as dl

        ds = f"cp-{uuid.uuid4().hex[:10]}"
        with supply_db.connect(label="test-recheck") as conn:
            qa_store.ensure_schema(conn)
            with dl.apply_decision(conn, dl.Decision(
                    agency_id="a", collection_id="c", dataset_id=ds, action=dl.PROMOTE,
                    supply=f"{ds}@1", actor="k@x", actor_kind=dl.PERSON, to_slot="2099-Q1",
                    effective_at=datetime.now(timezone.utc).isoformat())):
                pass
            did, recorded = conn.execute(f"SELECT id, recorded_at FROM {dl.TABLE} "
                                         "WHERE dataset_id = ?", [ds]).fetchone()
        ran = recorded + timedelta(hours=3)
        monkeypatch.setattr(asset_time, "now", lambda: ran)
        took = asset_time.parse_instant(
            recheck._cause_instant(SimpleNamespace(caused_by_decision=did)), "t")
        assert abs(took - ran) < timedelta(seconds=5)


class TestOneDefinitionOfASupplysCurrentRun:
    """post-build-review #117 D6 (Keith, 2026-10-06): the current run is the
    newest on the ASSET'S timeline - a re-run by when the decision that caused
    it took effect - as supply_status.runs_about already orders them, never
    by the wall clock a replay stamps years later in processing order."""

    def test_the_later_cause_is_current_whatever_ran_last(self, supply_dsn):
        import uuid

        from qa_tools.common.qa_results_writer import finish_run

        ds = f"cp-{uuid.uuid4().hex[:10]}"
        supply = f"{ds}@2024070100000000"
        with supply_db.connect(label="test-current-run") as conn:
            qa_store.ensure_schema(conn)
            ids = {}
            for name, effective in (("august", "2024-08-01T09:00:00+08:00"),
                                    ("july", "2024-07-15T09:00:00+08:00")):
                with dl.apply_decision(conn, dl.Decision(
                        agency_id="a", collection_id="c", dataset_id=ds, action=dl.PROMOTE,
                        supply=f"{supply}-{name}", actor="k@x", actor_kind=dl.PERSON,
                        to_slot=f"2099-{name}", effective_at=effective)):
                    pass
                ids[name] = conn.execute(f"SELECT max(id) FROM {dl.TABLE} WHERE dataset_id = ?",
                                         [ds]).fetchone()[0]
            # Processed in the other order: july's re-run has the later wall clock.
            for name, ran in (("august", "2026-10-06T10:00:00+08:00"),
                              ("july", "2026-10-06T10:05:00+08:00")):
                key = f"recheck_{name}_{uuid.uuid4().hex[:6]}"
                qa_store.record_run(conn, run_key=key, agency_id="a", collection_id="c",
                                    run_timestamp=ran, run_by="t@x", environment="test")
                qa_store.set_run_purpose(conn, key, dataset_id=ds, supply_id=supply,
                                         scope="full", caused_by_decision=ids[name])
                finish_run(key)
                ids[f"run_{name}"] = key
            assert qa_store.current_run(conn, ds, supply) == ids["run_august"]

    def test_a_tie_on_the_timeline_goes_to_the_later_run_not_the_later_key(self, supply_dsn):
        """Keith, 2026-10-06 (post-build-review #122 D6): two runs about the
        same supply with the same cause sorted by run key as TEXT, so
        `__r10` lost to `__r9`. The run instant breaks the tie first."""
        import uuid

        from qa_tools.common.qa_results_writer import finish_run

        ds = f"cp-{uuid.uuid4().hex[:10]}"
        supply = f"{ds}@2024070100000000"
        tag = uuid.uuid4().hex[:6]
        with supply_db.connect(label="test-current-run") as conn:
            qa_store.ensure_schema(conn)
            with dl.apply_decision(conn, dl.Decision(
                    agency_id="a", collection_id="c", dataset_id=ds, action=dl.PROMOTE,
                    supply=supply, actor="k@x", actor_kind=dl.PERSON, to_slot="2099-x",
                    effective_at="2024-08-01T09:00:00+08:00")):
                pass
            cause = conn.execute(f"SELECT max(id) FROM {dl.TABLE} WHERE dataset_id = ?",
                                 [ds]).fetchone()[0]
            for key, ran in ((f"z_first_{tag}", "2026-10-06T10:00:00+08:00"),
                             (f"a_second_{tag}", "2026-10-06T10:05:00+08:00")):
                qa_store.record_run(conn, run_key=key, agency_id="a", collection_id="c",
                                    run_timestamp=ran, run_by="t@x", environment="test")
                qa_store.set_run_purpose(conn, key, dataset_id=ds, supply_id=supply,
                                         scope="full", caused_by_decision=cause)
                finish_run(key)
            assert qa_store.current_run(conn, ds, supply) == f"a_second_{tag}"


class TestAReloadIsACauseLikeADecision:
    """REQ-DASH-148 criterion 12, end to end: a supply whose load failed and
    then loaded owes a re-check (load_log.record_load), and running it is a
    run of its own whose recorded cause is the reload."""

    def test_the_reload_is_the_runs_cause(self, cp_duckdb_dir, monkeypatch):
        from qa_tools.common import load_log, promotion

        monkeypatch.setenv("GIT_AUTHOR_EMAIL", "pytest@example.org")
        monkeypatch.setattr(promotion, "report", lambda outcome: None)
        physical = CP_DIRTY_RUN_ID   # the supply's staged table's own name
        load_log.record_load("pytest-reload", DATASET, physical, load_log.FAILED,
                             "2026-04-02T00:00:00+00:00", reason="ragged row")
        loaded = load_log.record_load("pytest-reload", DATASET, physical, load_log.LOADED,
                                      "2026-04-02T00:05:00+00:00", row_count=1)
        with supply_db.connect(read_only=True, label="test-recheck") as conn:
            [owed] = [o for o in recheck.owed(conn, DATASET)
                      if o.caused_by_load == loaded.id]
        got = recheck.run(owed.id, run_by="pytest@example.org")
        assert got.completed, got.message
        with supply_db.connect(read_only=True, label="test-recheck") as conn:
            row = conn.execute("SELECT caused_by_load, caused_by_decision, supply_id "
                               "FROM qa.run WHERE run_key = ?", [got.run_key]).fetchall()[0]
        assert row == (loaded.id, None, SUPPLY)
