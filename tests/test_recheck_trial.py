"""A trial of a bulk re-check (REQ-PIPE-178): the real re-check, on a few of
the supplies it would cover, with nothing kept.

The choosing, the flags and the invisibility of a trial's run are tested on
an empty database of the test's own; the run itself - real tools over a real
supply where it lies - against the bootstrapped deployment, which is the only
place a real supply exists (`TestARealTrialLeavesNothing`).
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

import attempt_support
import test_bulk_recheck as t
from qa_tools.common import bulk_recheck as bulk
from qa_tools.common import decision_log as dl
from qa_tools.common import filing_decisions as fd
from qa_tools.common import qa_store, supply_db

conn = t.conn
CHECK, DS, STALE = t.CHECK, t.DS, t.STALE


def _plan(*covered):
    check = bulk.current_checks()[CHECK]
    return bulk.Plan(check=check, fingerprint=check.config_hash, changelog=None,
                     covered=list(covered))


def _c(supply, period, ds=DS, state="waiting", status="green"):
    return bulk.Covered(ds, supply, period, state, status, STALE)


# ---- criteria 1, 2, 9, 16: choosing ---------------------------------------------

class TestChoosing:
    P = _plan(_c("a", "2024-Q1"), _c("b", "2024-Q2"), _c("c", "2024-Q3"),
              _c("x", "2024-01-01", ds="cp-clients"))

    def test_named_supplies_from_among_what_the_real_run_covers(self):
        assert [c.supply for c in bulk.choose(self.P, supplies=("b", "a"))] == ["b", "a"]

    def test_a_supply_the_real_run_would_not_cover_is_refused(self):
        with pytest.raises(bulk.Refused, match="not among the 4 supplies"):
            bulk.choose(self.P, supplies=("a", "zz"))

    def test_a_range_of_one_dataset(self):
        got = bulk.choose(self.P, dataset_id=DS, from_period="2024-Q2", through_period="2024-Q3")
        assert [c.supply for c in got] == ["b", "c"]

    def test_a_range_without_a_dataset_is_refused_naming_the_datasets(self):
        with pytest.raises(bulk.Refused) as got:
            bulk.choose(self.P, from_period="2024-Q1", through_period="2024-Q2")
        assert "needs --dataset" in str(got.value)
        assert "cp-carers, cp-clients" in str(got.value)

    def test_nothing_to_cover_refuses_the_trial(self):
        with pytest.raises(bulk.Refused, match="nothing to try"):
            bulk.choose(_plan(), supplies=("a",))

    def test_the_count_beside_the_real_runs(self):
        from cli import bulk_recheck_tui

        line = bulk_recheck_tui.trial_count_line(self.P, list(self.P.covered[:2]))
        assert line == ("The trial runs 2 supply/supplies - cp-carers 2024-Q1 (1), cp-carers "
                        "2024-Q2 (1) - of the 4 the real bulk re-check would cover.")


# ---- criterion 7: a trial's run is no supply's -----------------------------------

class TestATrialsRunIsReadByNothing:
    def test_its_cross_table_result_about_a_real_supply_is_not_about_it(self, conn):
        from qa_tools.common import supply_status

        supply, period = t.filed(conn, fingerprint=t.current())
        key = "trial_rc_pytest"
        qa_store.record_run(conn, run_key=key, agency_id=t.AG, collection_id=t.COL,
                            run_timestamp=t.WHEN, run_by=t.REAL_PERSON, environment="sandbox")
        qa_store.set_run_purpose(conn, key, dataset_id=DS, supply_id=None, period=period,
                                 trial=True)
        qa_store.record_results(
            conn, key, [{"dataset_id": DS, "check_id": "x.cross", "status": "fail"}],
            tool="soda", agency_id=t.AG, collection_id=t.COL, scope=qa_store.CROSS_TABLE_SCOPE,
            fingerprints=attempt_support.ANY_CHECK,
            reads=[[qa_store.CheckRead("cp_carers", qa_store.READ, supply)]])
        attempt_support.opened(conn, key)
        qa_store.complete_run(conn, key)
        shown = supply_status.results_about(conn, DS, supply, view=supply_status.View()).shown
        assert "x.cross" not in {r["check_id"] for r in shown}
        assert bulk.stale_fingerprints(conn, bulk.current_checks()).get("x.cross") is None

    def test_a_trials_run_may_not_name_a_supply_or_another_scope(self, conn):
        import psycopg

        supply, _ = t.filed(conn)
        qa_store.record_run(conn, run_key="trial_rc_bad", agency_id=t.AG, collection_id=t.COL,
                            run_timestamp=t.WHEN, run_by=t.REAL_PERSON, environment="sandbox")
        with pytest.raises(psycopg.Error):
            qa_store.set_run_purpose(conn, "trial_rc_bad", dataset_id=DS, supply_id=supply,
                                     trial=True)

    def test_its_id_is_a_trial_that_owns_its_schemas_but_reads_real_supplies(self):
        from qa_tools.common import trial

        rid = bulk.trial_run_id()
        assert supply_db.is_trial_run(rid) and supply_db.is_recheck_trial(rid)
        assert not trial.is_trial(rid)
        assert trial.scope_for(rid) is None
        assert supply_db.staging_schema_for(rid) != supply_db.STAGING_SCHEMA


# ---- criterion 5: the gate's prediction ------------------------------------------

class TestThePrediction:
    def test_a_promoted_supply_stays_promoted(self, conn):
        c = _c("s", "2099-S1", state="promoted")
        status, said = bulk.predict(conn, c, [])
        assert said == "it would stay promoted - 2099-S1 keeps it"

    def test_a_waiting_supply_is_judged_by_the_gates_plan_step_and_nothing_is_written(
            self, conn):
        supply, period = t.filed(conn)
        before = conn.execute(f"SELECT count(*) FROM {dl.TABLE}").fetchone()[0]
        status, said = bulk.predict(conn, _c(supply, period),
                                    [{"dataset_id": DS, "check_id": CHECK, "status": "pass"}])
        assert conn.execute(f"SELECT count(*) FROM {dl.TABLE}").fetchone()[0] == before
        assert said.startswith(("the gate would promote it", "it would wait for a person"))
        # Q3 (PROVISIONAL): the real gate judges it with its package partners.
        assert "judges it with its package partners" in said and "may decide differently" in said
        assert "rejected" not in said and "refused" not in said


# ---- criteria 10, 12, 13, 15, 17, 18: the terminal --------------------------------

def _trial(*args):
    from cli.supply import recheck_command

    return CliRunner().invoke(recheck_command, ["--check", CHECK, "--trial", *args],
                              env={"COLUMNS": "400"})


class TestTheFlags:
    @pytest.mark.parametrize("flag", [["--reason", "x"], ["--acknowledge", "k"],
                                      ["--hand-off"]])
    def test_a_flag_that_records_is_refused_naming_it(self, conn, flag):
        got = _trial(*flag)
        assert got.exit_code == 1
        assert f"{flag[0]} cannot be used with --trial: a trial records nothing" in got.output

    def test_a_range_without_a_dataset_is_refused(self, conn):
        t.filed(conn)
        got = _trial("--from-period", "a", "--through-period", "b", "--yes")
        assert got.exit_code == 1 and "needs --dataset" in got.output

    def test_without_a_terminal_or_yes_it_is_refused_naming_yes(self, conn):
        supply, _ = t.filed(conn)
        got = _trial("--supply", supply)
        assert got.exit_code == 1 and "pass --yes" in got.output

    def test_it_runs_shows_each_beside_now_and_ends_with_the_real_command(
            self, conn, monkeypatch):
        supply, period = t.filed(conn)
        monkeypatch.setattr(bulk, "try_one", lambda c, **k: bulk.Tried(
            c, "amber", "it would wait for a person - amber"))
        got = _trial("--supply", supply, "--yes")
        assert got.exit_code == 0, got.output
        flat = " ".join(got.output.replace("│", " ").split())
        import re

        assert re.search(rf"{DS} {period} \({supply}\): amber in the trial, (green|amber|red|no "
                         rf"verdict) now - it would wait for a person", flat), flat
        assert "runs that have been discarded" in flat and "may differ" in flat
        assert "The real bulk re-check covers 1 supply/supplies:" in got.output
        assert f"\nmothman supply recheck --check {CHECK} --reason '<why>'\n" in got.output
        assert conn.execute(f"SELECT count(*) FROM {bulk.TABLE}").fetchone()[0] == 0

    def test_a_range_says_it_applies_to_the_trial_only(self, conn, monkeypatch):
        t.filed(conn, period="2099-S0001")
        monkeypatch.setattr(bulk, "try_one", lambda c, **k: bulk.Tried(c, "green", "x"))
        got = _trial("--dataset", DS, "--from-period", "2099-S0000",
                     "--through-period", "2099-S0009", "--yes")
        assert got.exit_code == 0, got.output
        assert "applies to the trial only" in " ".join(got.output.split())

    def test_ctrl_c_shows_what_finished_and_that_nothing_was_recorded(self, monkeypatch, capsys):
        from cli import bulk_recheck_tui

        p = _plan(_c("a", "2024-Q1"), _c("b", "2024-Q2"))
        calls = []

        def go(c, **k):
            calls.append(c)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return bulk.Tried(c, "red", "it would wait for a person")
        monkeypatch.setattr(bulk, "try_one", go)
        tried = bulk_recheck_tui.run_trial(p, list(p.covered))
        out = " ".join(capsys.readouterr().out.split())
        assert [x.covered.supply for x in tried] == ["a"]
        assert "Traceback" not in out and "nothing was recorded" in out

    def test_a_trial_with_nothing_chosen_is_told_what_it_takes(self):
        with pytest.raises(bulk.Refused, match="takes the supplies to try: --supply"):
            bulk.choose(_plan(_c("a", "2024-Q1")))

    def test_a_hard_killed_trials_schemas_are_listed_by_tidy(self, supply_dsn):
        from qa_tools.common import trial

        rid = bulk.trial_run_id()
        with supply_db.connect(label="test-recheck-trial") as c:
            c.execute(f'CREATE SCHEMA "{supply_db.staging_schema_for(rid)}"')
            c.execute(f'CREATE SCHEMA "{supply_db.run_schema(rid)}"')
            try:
                assert {supply_db.staging_schema_for(rid), supply_db.run_schema(rid)} <= set(
                    trial.orphan_schemas(c))
            finally:
                trial.discard(c, rid)
            assert not set(trial.orphan_schemas(c)) & {supply_db.staging_schema_for(rid)}

    def test_it_is_not_a_filing_decision_on_any_route(self):
        assert "trial" not in " ".join(fd.OPERATIONS) and "trial" not in fd.TERMINAL_ONLY


# ---- criteria 3, 6, 7 and NFR 4: the real thing ----------------------------------

@pytest.mark.needs_deployment
class TestARealTrialLeavesNothing:
    """A real supply of the bootstrapped deployment, through the real tools,
    and afterwards everything as it was: every qa table's CONTENTS, every
    schema, and every staging, period and rejected table's contents."""

    def _contents(self, c, schemas_where: str) -> dict[str, str]:
        """{schema.table: an md5 of its every row} for every base table the
        catalog lists under `schemas_where` - enumerated, never a named list,
        so a table added later is compared too (critic T1)."""
        tables = [(r[0], r[1]) for r in c.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            f"WHERE table_type = 'BASE TABLE' AND ({schemas_where}) "
            "ORDER BY 1, 2").fetchall()]
        assert tables, f"no table matched {schemas_where} - the comparison would prove nothing"
        out = {}
        for schema, table in tables:
            (digest,) = c.execute(
                f'SELECT md5(coalesce(string_agg(t::text, chr(10) ORDER BY t::text), \'\')) '
                f'FROM "{schema}"."{table}" t').fetchone()
            out[f"{schema}.{table}"] = digest
        return out

    def _qa(self, c):
        return self._contents(c, f"table_schema = '{qa_store.SCHEMA}'")

    def _supplies(self, c):
        return self._contents(c, "table_schema = 'staging' OR table_schema LIKE 'period\\_%' "
                                 "OR table_schema LIKE 'rejected%'")

    def _schemas(self, c):
        # Another session's temporary schemas come and go; they are not ours.
        return sorted(r[0] for r in c.execute(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name NOT LIKE 'pg\\_temp\\_%' "
            "AND schema_name NOT LIKE 'pg\\_toast\\_temp\\_%'").fetchall())

    def _a_supply(self, c, promoted: bool):
        from qa_tools.common import rechecking

        rows = c.execute(
            "SELECT f.dataset_id, f.supply_id FROM qa.filing_current f WHERE f.slot IS NOT NULL "
            "AND f.dataset_id = 'cp-carers' ORDER BY f.supply_id").fetchall()
        for ds, sup in rows:
            try:
                s = rechecking.standing(c, ds, sup)
            except dl.DecisionRefused:
                continue
            if (s.state == rechecking.PROMOTED) == promoted:
                return bulk.Covered(ds, sup, s.period, s.state, None, STALE)
        pytest.fail("the deployment holds no such cp-carers supply")

    @pytest.mark.parametrize("promoted", [True, False], ids=["promoted", "waiting"])
    def test_one_supplys_trial(self, deployment_history, promoted):
        from qa_tools.common import trial

        with supply_db.connect(read_only=True, label="test-recheck-trial") as c:
            covered = self._a_supply(c, promoted)
            before = (self._qa(c), self._schemas(c), self._supplies(c))
        tried = bulk.try_one(covered)
        assert tried.ran, tried.error
        assert tried.status in ("green", "amber", "red")
        assert tried.prediction
        with supply_db.connect(read_only=True, label="test-recheck-trial") as c:
            after = (self._qa(c), self._schemas(c), self._supplies(c))
            assert not trial.orphan_schemas(c)
        assert after[1] == before[1], "a schema was left behind or removed"
        changed = sorted(k for k in set(before[0]) | set(after[0])
                         if before[0].get(k) != after[0].get(k))
        assert not changed, f"qa tables changed by a trial: {changed}"
        assert after[2] == before[2], "a staging, period or rejected table changed"
        if promoted:
            assert tried.prediction.startswith("it would stay promoted")
