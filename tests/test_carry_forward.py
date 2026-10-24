"""A person carries a newer supply forward into a later period in one
decision, so no reader goes red in between (REQ-PIPE-280).

Against this worker's own database, with the quarter Case Workers sits out
stated by carry_forward_support. The reader is a real Notifications supply
promoted into that quarter, its Assigned worker check (which reads
cp_case_workers) recorded as the pipeline records it.
"""
from __future__ import annotations

import re
import uuid

import pytest
from click.testing import CliRunner

import carry_forward_support
from carry_forward_support import ASSIGNED_WORKER, CASE_WORKERS, KEYS, NAME, entries, promote, view_reads

conn = carry_forward_support.conn
world = carry_forward_support.world
from qa_tools.common import carry_forward, filing_decisions as fd, inheritance, knock_on
from qa_tools.common import decision_log as dl
from qa_tools.common import people, qa_store, recheck, supply_status
from test_results_about import _read, _result, _run

REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def actor():
    return people.person_by_email(REAL_PERSON)


def _flat(text: str) -> str:
    """Terminal output with panel borders and wrapping taken out, so a
    sentence can be looked for whole."""
    return re.sub(r"\s+", " ", re.sub(r"[│╭╮╰╯─]", " ", text))


def _stale(conn, world):
    """Q2's Case Workers promoted; a Notifications supply promoted into Q4
    (opening it, so it inherits Q2's), its Assigned worker check passing
    against Q2's; then Q3's Case Workers promoted - the stale case."""
    q2 = promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
    n = promote(conn, world.q4, "2099-08-02T10:00:00+08:00", dataset_id="cp-notifications")
    _run(conn, f"pytest-cf-{uuid.uuid4().hex[:8]}", dataset_id="cp-notifications", supply=n,
         at="2099-08-02T09:00:00+08:00",
         cross=[(_result(ASSIGNED_WORKER, "cp-notifications", "pass"),
                 (_read("cp_case_workers", q2), _read("cp_notifications", n)))])
    q3 = promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
    return q2, q3, n


def _request(actor, world, operation=fd.CARRY_FORWARD, **kw):
    kw.setdefault("reason", "the newer one is current")
    return fd.Request(operation=operation, dataset_id=CASE_WORKERS, actor=actor,
                      period=world.q4, confirmed=True, **kw)


def _apply(conn, actor, world, operation=fd.CARRY_FORWARD, **kw):
    request = _request(actor, world, operation, **kw)
    key = fd.consequences(conn, request).key
    import dataclasses
    return fd.apply(dataclasses.replace(request, acknowledged=key or None),
                    effective_at="2099-10-05T09:00:00+08:00", conn=conn)


def _owed(conn, world, decision: int | None = None):
    return [o for o in recheck.owed(conn) if o.kind == recheck.REEVALUATE
            and o.period == world.q4
            and (decision is None or o.caused_by_decision == decision)]


class TestCarryForward:

    def test_stale_inheritance_is_repointed_in_one_decision(self, conn, world, actor):
        q2, q3, _n = _stale(conn, world)
        before, owed_before = entries(conn, world.q4), len(_owed(conn, world))
        outcome = _apply(conn, actor, world)
        assert outcome.changed

        new = [e for e in entries(conn, world.q4) if e not in before]
        (entry,) = new
        assert entry["action"] == dl.CARRY_FORWARD and entry["actor"] == REAL_PERSON
        assert not entries(conn, world.q4, dl.UN_INHERIT), "never an un-inherit then inherit"
        stood = conn.execute(f"SELECT stands_on, replaces FROM {dl.TABLE} WHERE id = ?",
                             [entry["id"]]).fetchone()
        assert tuple(stood) == (world.q3, q2), "names what it stood on before and after"
        assert len(_owed(conn, world)) == owed_before + 1
        assert len(_owed(conn, world, entry["id"])) == 1, "one re-evaluation, owed by it"
        assert inheritance.inherited(conn, CASE_WORKERS, world.q4).supply == q3
        from qa_tools.common import period_schema
        assert period_schema.period_schema(world.q3) in view_reads(conn, world.q4)

    def test_no_reader_is_ever_red_for_want_of_the_table(self, conn, world, actor,
                                                         monkeypatch):
        """No committed state holds nothing for the table (criterion 4); while
        the re-check is owed the reader reads 'recheck-owed', never a
        could-not-run (criterion 10); and the one re-evaluation, once run,
        reads the new supply - with no still-failing record or ticket."""
        q2, q3, n = _stale(conn, world)
        _apply(conn, actor, world)
        (entry,) = entries(conn, world.q4, dl.CARRY_FORWARD)

        # EVERY COMMITTED INSTANT HOLDS A TABLE: inherited throughout.
        for e in entries(conn, world.q4):
            h = dl.held(conn, CASE_WORKERS, world.q4, e["effective_at"].isoformat())
            if e["id"] >= min(x["id"] for x in entries(conn, world.q4, dl.INHERIT)):
                assert h is not None and h.held_as == dl.INHERITED, e
        assert view_reads(conn, world.q4)

        (row,) = [r for r in supply_status.latest_results(conn, "cp-notifications", n)
                  if r["check_id"] == ASSIGNED_WORKER]
        assert (row["warehouse_reason"], row["owed_by_decision"]) == (
            supply_status.RECHECK_OWED, entry["id"])

        def execute(*, dataset_id, supply_id, run_key, purpose, run_by=None, on_step=None):
            """The readers-only re-run the knock-on asks for, recorded as the
            writer records one, reading what the period now carries."""
            import attempt_support

            qa_store.record_run(conn, run_key=run_key, run_timestamp="2099-10-05T09:05:00+08:00",
                                run_by="t@x", environment="test", **KEYS)
            qa_store.set_run_purpose(conn, run_key, dataset_id=dataset_id, supply_id=supply_id,
                                     scope="readers", reads_table=purpose["reads_table"],
                                     period=world.q4,
                                     caused_by_decision=purpose["caused_by_decision"])
            qa_store.record_results(
                conn, run_key, [_result(ASSIGNED_WORKER, "cp-notifications", "pass")],
                tool="dbt", **KEYS, scope=qa_store.CROSS_TABLE_SCOPE,
                reads=[(_read("cp_case_workers", q3), _read("cp_notifications", n))])
            attempt_support.opened(conn, run_key)
            qa_store.complete_run(conn, run_key)
        monkeypatch.setattr(recheck, "execute", execute)
        (item,) = _owed(conn, world, entry["id"])
        done = knock_on.complete(item)
        assert done.completed, done.message

        (row,) = [r for r in supply_status.latest_results(conn, "cp-notifications", n)
                  if r["check_id"] == ASSIGNED_WORKER]
        assert row["status"] == "pass" and knock_on.read_as(row, "cp_case_workers") == q3
        assert not [r for r in supply_status.results_about(conn, "cp-notifications", n,
                                                             view=supply_status.View()).shown
                    if r.get("unrunnable_reason")], "no could-not-run was ever recorded"
        assert not entries(conn, world.q4, dl.STILL_FAILING)
        assert not conn.execute(
            f"SELECT 1 FROM {dl.TABLE} WHERE action = ? AND to_slot = ?",
            [dl.STILL_FAILING, world.q4]).fetchall()

    def test_a_refused_inheritance_is_made_by_the_same_operation(self, conn, world, actor):
        from qa_tools.common import period_schema

        period_schema.open_period(conn, world.q4, opened_by="pytest",
                                  effective_at="2099-08-01T09:00:00+08:00")
        assert entries(conn, world.q4, dl.INHERIT_REFUSED)
        q3 = promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
        assert _apply(conn, actor, world).changed
        (entry,) = entries(conn, world.q4, dl.CARRY_FORWARD)
        stood = conn.execute(f"SELECT stands_on, replaces FROM {dl.TABLE} WHERE id = ?",
                             [entry["id"]]).fetchone()
        assert tuple(stood) == (world.q3, None), "it stood on nothing before"
        assert inheritance.inherited(conn, CASE_WORKERS, world.q4).supply == q3
        assert not inheritance.refusals(conn) or all(
            r.period != world.q4 for r in inheritance.refusals(conn))


class TestTheFlagRoute:

    @pytest.fixture
    def keyboard(self, monkeypatch):
        from cli import filing_tui
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                            lambda: people.person_by_email(REAL_PERSON))
        # The knock-on's real tools are not this test's subject.
        monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])

    def _decide(self, world, *extra, period=None):
        from cli.supply import supply_group
        return CliRunner().invoke(supply_group, [
            "decide", "--operation", "carry-forward", "--dataset", CASE_WORKERS,
            "--period", period or world.q4, "--reason", "current", "--yes", *extra])

    def test_it_refuses_over_a_promoted_supply_or_where_the_dataset_participates(
            self, conn, world, keyboard):
        got = self._decide(world, period=world.q3)
        assert got.exit_code == 1, got.output
        assert (f"{NAME} takes part in {world.q3}, so it is supplied there, not "
                f"carried forward. Nothing was recorded.") in _flat(got.output)
        own = promote(conn, world.q4, "2099-10-02T09:00:00+08:00")
        assert dl.held(conn, CASE_WORKERS, world.q4).holder == own
        before = entries(conn, world.q4)
        got = self._decide(world)
        assert got.exit_code == 1, got.output
        assert (f"{world.q4} holds a {NAME} supply of its own, so nothing is carried "
                f"forward into it. Nothing was recorded.") in _flat(got.output)
        assert entries(conn, world.q4) == before, "recorded nothing"

    def test_a_second_carry_forward_is_a_no_op_exit_0(self, conn, world, actor, keyboard):
        _stale(conn, world)
        _apply(conn, actor, world)
        before = entries(conn, world.q4)
        got = self._decide(world)
        assert got.exit_code == 0, got.output
        flat = _flat(got.output)
        assert "Already so" in flat
        assert (f"{world.q4} already carries forward the newest promoted {NAME} "
                f"(received ") in flat and "Nothing to do." in flat
        assert entries(conn, world.q4) == before


class TestTheWords:

    def test_undo_and_follow_up_lines(self, conn, world, actor, monkeypatch, capsys):
        from cli import filing_tui

        q2, _q3, _n = _stale(conn, world)
        found = fd.consequences(conn, _request(actor, world))
        undo = (f"There is no step back to the supply received "
                f"{carry_forward.received(CASE_WORKERS, q2)}; un-inherit removes what "
                f"{world.q4} carries forward, and leaves its readers with no table.")
        assert undo in found.lines
        assert any(line.startswith(f"{world.q4} stops carrying forward") for line in found.lines)
        assert any("Notification" in line and "re-checked against" in line
                   for line in found.lines), "each reader whose checks re-run is named"

        # THE RE-EVALUATION COULD NOT RUN: said, with the command on its own line.
        # The outcome is the carry-forward's own owed item's, as the real
        # follow-up reports it (S6: another period's failure is not blamed).
        def follow_up(*a, **k):
            with carry_forward_support.supply_db.connect(label="t") as c:
                return [recheck.Outcome(o.id, "", False, "made to fail")
                        for o in recheck.owed(c) if o.period == world.q4]
        monkeypatch.setattr(knock_on, "follow_up", follow_up)
        outcome = filing_tui.apply_decision(
            operation=fd.CARRY_FORWARD, dataset_id=CASE_WORKERS, period=world.q4,
            reason="current", actor=actor, yes=True, acknowledged=found.key)
        assert outcome is not None and outcome.changed
        out = capsys.readouterr().out
        assert "Re-evaluation owed" in out
        assert "mothman pipeline process" in out.splitlines()

    def test_the_follow_up_lists_every_reader_re_checked(self, conn, world, actor,
                                                         monkeypatch, capsys):
        from cli import filing_tui

        _stale(conn, world)
        found = fd.consequences(conn, _request(actor, world))
        monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [recheck.Outcome(
            1, "k", True, "1 reader(s) re-evaluated")])
        filing_tui.apply_decision(
            operation=fd.CARRY_FORWARD, dataset_id=CASE_WORKERS, period=world.q4,
            reason="current", actor=actor, yes=True, acknowledged=found.key)
        out = _flat(capsys.readouterr().out)
        assert f"Re-checked against the {NAME} carried forward into {world.q4}" in out
        assert "Notification" in out

    def test_inherit_noop_names_carry_forward_while_the_warning_stands(
            self, conn, world, actor):
        _stale(conn, world)
        outcome = fd.apply(_request(actor, world, fd.INHERIT),
                           effective_at="2099-10-05T09:00:00+08:00", conn=conn)
        assert not outcome.changed
        lines = outcome.message.split("\n")
        assert lines[0] == f"{world.q4} already inherits. Nothing to do."
        assert lines[1] == f"A newer {NAME} could be carried forward:"
        assert lines[2] == (f"mothman supply decide --operation carry-forward --dataset "
                            f"{CASE_WORKERS} --period {world.q4} --reason '<why>'")

    def test_un_inherit_names_carry_forward_as_the_way_without_a_gap(
            self, conn, world, actor):
        _stale(conn, world)
        found = fd.consequences(conn, _request(actor, world, fd.UN_INHERIT))
        assert any("carry it forward instead - one decision, no gap" in n
                   and "--operation carry-forward" in n for n in found.notes)

    def test_help_describes_it(self):
        from cli.supply import supply_group
        got = CliRunner().invoke(supply_group, ["decide", "--help"])
        assert ("inherit the newest promoted supply, replacing what this period carries "
                "forward (or giving it one)") in _flat(got.output)
        assert carry_forward.DESCRIBED in _flat(got.output)


def test_the_record_shape_is_held_by_the_database_too(conn):
    """A carry-forward is a person's, with a reason, naming both periods - the
    column constraint refuses anything else even past decision_log."""
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.raw.transaction():
            conn.execute(
                f"INSERT INTO {dl.TABLE} (agency_id, collection_id, dataset_id, action, "
                "supply, to_slot, actor, actor_kind, effective_at, recorded_at) "
                "VALUES (?, ?, ?, 'carry-forward', 's', 'p', 'rule', 'rule', now(), now())",
                [KEYS["agency_id"], KEYS["collection_id"], CASE_WORKERS])
    assert qa_store.SCHEMA_VERSION >= 47
