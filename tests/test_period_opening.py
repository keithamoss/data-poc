"""A period opens, and inherits what it owes nothing for, at its first filing;
a newer supply it could carry forward is warned, never re-pointed
(REQ-PIPE-271).

Against this worker's own database. The participation is stated rather than
read from contract/calendar.yaml (carry_forward_support's own docstring
says why); everything else goes through the real filing, opening,
promotion and decision-log code.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import filing_support
from carry_forward_support import (CASE_WORKERS, KEYS, conn, entries, promote,  # noqa: F401
                                   view_reads, world)
from qa_tools.common import assignment as assign_mod
from qa_tools.common import carry_forward, filing, inheritance, period_schema
from qa_tools.common import decision_log as dl

AT = datetime(2099, 10, 2, 1, 0, tzinfo=timezone.utc)


def _file(monkeypatch, world, period: str | None, dataset_id: str = "cp-notifications",
          collection_id: str = "child-protection"):
    """File one supply of `dataset_id` through the real filing.file_arrivals,
    the assignment rule's answer stated as `period` (None: held)."""
    import uuid
    supply = f"{dataset_id}@{AT.strftime('%Y%m%d')}{uuid.uuid4().int % 10**12:012d}"
    name = f"pytest-open-{supply}"
    filing_support.ensure_delivery(name, dataset_id, AT)
    arrival = SimpleNamespace(files_by_dataset={dataset_id: ["f"]}, received_at=AT,
                              delivery_name=name, run_id=f"run-{supply}")
    monkeypatch.setattr(filing, "_supply_id_for", lambda arr, ds: supply)

    def assign(**kw):
        if period is None:
            return assign_mod.Assignment(dataset_id=kw["dataset_id"],
                                         supply_id=kw["supply_id"], slot=None,
                                         branch=assign_mod.HELD, considered=(),
                                         received_at=kw["at"])
        return assign_mod.Assignment(dataset_id=kw["dataset_id"], supply_id=kw["supply_id"],
                                     slot=period, branch="pytest", considered=(period,),
                                     received_at=kw["at"])
    monkeypatch.setattr(assign_mod, "assign", assign)
    filing.file_arrivals([arrival])
    return supply, arrival


class TestOpenedAtTheFirstFiling:
    """Criteria 1 to 5."""

    def test_the_first_filing_opens_the_period_and_inherits_before_any_check(
            self, conn, world, monkeypatch):
        from qa_tools.common import period_overlay

        old = promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        assert not period_schema.opened(conn, world.q4)
        supply, arrival = _file(monkeypatch, world, world.q4)
        assert period_schema.opened(conn, world.q4)
        (made,) = entries(conn, world.q4, dl.INHERIT)
        assert made["supply"] == old
        assert inheritance.inherited(conn, CASE_WORKERS, world.q4).stands_on == world.q2
        assert view_reads(conn, world.q4), "the inherited view exists before any run"
        # BEFORE THE OVERLAY (criterion 2): the run's overlay, built next,
        # reads the inherited table from the period.
        out = period_overlay.build(
            conn, "pytest_open_overlay", period=world.q4, own_table="cp_notifications",
            arrival_key=supply.split("@")[1], tables=["cp_notifications", "cp_case_workers"],
            loaded=None)
        assert out.source.get("cp_case_workers") == period_schema.FROM_PERIOD
        assert out.resolution.supply_of.get("cp_case_workers") == old

    def test_the_openings_own_re_evaluation_is_settled_at_once(self, conn, world, monkeypatch):
        """Nothing has been checked in a period at its first filing, so the
        re-evaluation its inheritances owe has nobody to re-check: it clears
        at the filing, never waiting for the arrival's promotion (the week
        bound tests/test_knock_on.py holds a replayed history to)."""
        from qa_tools.common import recheck

        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        _file(monkeypatch, world, world.q4)
        (made,) = entries(conn, world.q4, dl.INHERIT)
        rows = conn.execute(
            f"SELECT cleared_at FROM {recheck.TABLE} WHERE kind = ? AND period = ? "
            "AND caused_by_decision = ?", [recheck.REEVALUATE, world.q4, made["id"]]).fetchall()
        assert rows, "the inheritance owed its readers a re-evaluation, as any move does"
        assert all(cleared is not None for (cleared,) in rows)

    def test_it_records_which_collections_filing_opened_it(self, conn, world, monkeypatch):
        """Criterion 4: a shared period names the collection whose filing
        opened it, and each inheritance the supply that caused it."""
        supply, _ = _file(monkeypatch, world, world.q4)
        (opened_by,) = conn.execute(
            'SELECT opened_by FROM "qa".period WHERE name = ?', [world.q4]).fetchone()
        assert "child-protection" in opened_by and supply in opened_by
        assert all(e["action"] in (dl.INHERIT, dl.INHERIT_REFUSED)
                   for e in entries(conn, world.q4))
        rows = conn.execute(
            f"SELECT caused_by_supply FROM {dl.TABLE} WHERE to_slot = ? AND action = ?",
            [world.q4, dl.INHERIT_REFUSED]).fetchall()
        assert rows, "nothing earlier was promoted, so the inheritance was refused"

    def test_a_held_supply_opens_no_period(self, conn, world, monkeypatch):
        """Criterion 3: no period, nothing opened."""
        _file(monkeypatch, world, None)
        assert not period_schema.opened(conn, world.q4)

    def test_a_second_filing_to_an_opened_period_inherits_nothing_more(
            self, conn, world, monkeypatch):
        """Criterion 5: once, at opening - a supply promoted since is not
        carried forward by a later filing."""
        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        _file(monkeypatch, world, world.q4)
        before = entries(conn, world.q4, dl.INHERIT, dl.CARRY_FORWARD)
        promote(conn, world.q3, "2099-07-02T09:00:00+08:00")
        _file(monkeypatch, world, world.q4, dataset_id="cp-clients")
        assert entries(conn, world.q4, dl.INHERIT, dl.CARRY_FORWARD) == before


class TestCarryForwardWarning:
    """Criteria 5 to 8 and 11: warned, never re-pointed or retried, and
    cleared by the one-step carry-forward."""

    def _cleared_by_carry_forward(self, conn, world):
        """REQ-PIPE-280's one step clears it (criterion 8)."""
        carry_forward.carry_forward(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                    actor="Keith", reason="the newer one is current",
                                    effective_at="2099-10-05T09:00:00+08:00")
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4) == []

    def test_a_stale_inheritance_is_warned_not_repointed(self, conn, world, monkeypatch):
        q2 = promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        period_schema.open_period(conn, world.q4, opened_by="pytest",
                                  effective_at="2099-08-01T09:00:00+08:00")
        q3 = promote(conn, world.q3, "2099-09-02T09:00:00+08:00")

        # NOT RE-POINTED (criterion 5): still Q2's.
        assert inheritance.inherited(conn, CASE_WORKERS, world.q4).supply == q2
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        assert (w.supply, w.carried, w.promoted_into) == (q3, q2, world.q3)
        (recorded,) = entries(conn, world.q4, dl.CARRY_FORWARD_WARNING)
        assert recorded["actor_kind"] == dl.RULE
        said = carry_forward.lines(w, voice="page")
        assert said[0].startswith(f"A newer {CASE_WORKERS} could be carried forward into "
                                  f"{world.q4}. {world.q4} carries forward the supply received ")
        assert said[1] == "A person can carry that one forward instead, in one step:"
        assert said[2] == (f"mothman supply decide --operation carry-forward --dataset "
                           f"{CASE_WORKERS} --period {world.q4} --reason '<why>'")
        assert said[3] == f"or from the {world.q4} door."
        terminal = carry_forward.lines(w, voice="terminal")
        assert terminal[1] == "To carry that one forward instead, in one step:"
        assert not any("un-inherit" in line for line in said + terminal)

        self._cleared_by_carry_forward(conn, world)
        assert inheritance.inherited(conn, CASE_WORKERS, world.q4).supply == q3

    def test_a_refused_inheritance_is_warned_not_retried(self, conn, world):
        """S9: nothing earlier when Q4 opened; an earlier supply promoted
        later; Q4 still carries nothing and the warning names it."""
        period_schema.open_period(conn, world.q4, opened_by="pytest",
                                  effective_at="2099-08-01T09:00:00+08:00")
        assert entries(conn, world.q4, dl.INHERIT_REFUSED)
        q3 = promote(conn, world.q3, "2099-09-02T09:00:00+08:00")

        assert inheritance.inherited(conn, CASE_WORKERS, world.q4) is None, "never retried"
        assert view_reads(conn, world.q4) is None
        (w,) = carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        assert (w.supply, w.carried) == (q3, None)
        said = carry_forward.lines(w, voice="page")
        assert said[0].startswith(f"{world.q4} carries nothing forward for {CASE_WORKERS}: "
                                  f"there was no earlier promoted supply when it opened. The "
                                  f"one received ")
        assert said[0].endswith(f"has been promoted into {world.q3} since, and a person can "
                                f"carry it forward, in one step:")
        terminal = carry_forward.lines(w, voice="terminal")
        assert terminal[1] == "To carry it forward, in one step:"

        self._cleared_by_carry_forward(conn, world)
        assert view_reads(conn, world.q4)

    def test_it_clears_when_the_newer_supply_leaves_its_period(self, conn, world):
        from qa_tools.common import rejection

        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        period_schema.open_period(conn, world.q4, opened_by="pytest",
                                  effective_at="2099-08-01T09:00:00+08:00")
        q3 = promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4)
        physical = f"cp_case_workers__{q3.split('@')[1]}"
        rejection.demote(conn, **KEYS, dataset_id=CASE_WORKERS, supply=q3,
                         from_slot=world.q3, physical_tables=[physical], actor="Keith",
                         reason="wrong file", effective_at="2099-09-03T09:00:00+08:00")
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4) == []
        # AS AT A DATE BEFORE IT CLEARED, IT STOOD (the page's as-at reading).
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4,
                                      as_at="2099-09-02T12:00:00+08:00")

    def test_an_older_promotion_is_not_warned(self, conn, world):
        """Only a supply NEWER than what the later period carries."""
        promote(conn, world.q3, "2099-07-02T09:00:00+08:00")
        period_schema.open_period(conn, world.q4, opened_by="pytest",
                                  effective_at="2099-08-01T09:00:00+08:00")
        promote(conn, world.q2, "2099-08-02T09:00:00+08:00")
        assert carry_forward.standing(conn, dataset_id=CASE_WORKERS, period=world.q4) == []
        assert not entries(conn, world.q4, dl.CARRY_FORWARD_WARNING)


class TestTheWarningIsShown:
    """Criterion 7 and 11: in the terminal's queue (not counted), in the
    period's door, in the outstanding queue and in the dashboard's data."""

    @pytest.fixture
    def warned(self, conn, world):
        promote(conn, world.q2, "2099-04-02T09:00:00+08:00")
        period_schema.open_period(conn, world.q4, opened_by="pytest",
                                  effective_at="2099-08-01T09:00:00+08:00")
        promote(conn, world.q3, "2099-09-02T09:00:00+08:00")
        return world

    def _command(self, world) -> str:
        return (f"mothman supply decide --operation carry-forward --dataset {CASE_WORKERS} "
                f"--period {world.q4} --reason '<why>'")

    def test_the_supply_queue_shows_it_uncounted_with_the_command_on_its_own_line(
            self, warned):
        from click.testing import CliRunner

        from cli import supply as supply_cli

        got = CliRunner().invoke(supply_cli.supply_group,
                                 ["queue", "--collection", "child-protection"],
                                 env={"COLUMNS": "200"})
        assert got.exit_code == 0, got.output
        lines = got.output.splitlines()
        assert self._command(warned) in lines, "the command on a line of its own"
        assert "To carry that one forward instead, in one step:" in lines
        assert f"or from the {warned.q4} door." in lines

    def test_the_period_door_shows_it_and_offers_carry_forward(
            self, warned, monkeypatch, capsys):
        from cli import common, filing_tui

        asked = []

        def select(message, choices, **kw):
            asked.append((message, list(choices)))
            if message == "Which dataset?":
                return CASE_WORKERS
            if message.startswith("Which period"):
                return next(c for c in choices if c.startswith(warned.q4))
            return None   # stop at the operation choice

        monkeypatch.setattr(common, "select", select)
        filing_tui.period_flow("child-protection")
        out = capsys.readouterr().out
        assert self._command(warned) in out.splitlines()
        offered = asked[-1][1]
        assert any(c.startswith("carry forward - inherit the newest promoted supply")
                   for c in offered), offered

    def test_the_outstanding_queue_carries_it_at_a_refused_inheritances_prominence(
            self, warned):
        from qa_tools.common import outstanding

        found = [i for i in outstanding._from_carry_forward_warnings()
                 if i.dataset_id == CASE_WORKERS and warned.q4 in i.headline]
        assert found and found[0].severity == outstanding.WARNING

    def test_the_dashboard_data_carries_it_with_the_days_it_stood(self, warned, conn):
        got = [w for w in carry_forward.for_dashboard(CASE_WORKERS, conn)
               if w["period"] == warned.q4]
        assert got and got[0]["from"] == "2099-09-02" and got[0]["until"] is None
        assert got[0]["command"] == self._command(warned)
        assert got[0]["headline"] == (f"A newer {CASE_WORKERS} could be carried forward into "
                                      f"{warned.q4}.")
        carry_forward.carry_forward(conn, dataset_id=CASE_WORKERS, period=warned.q4,
                                    actor="Keith", reason="current",
                                    effective_at="2099-10-05T09:00:00+08:00")
        (after,) = [w for w in carry_forward.for_dashboard(CASE_WORKERS, conn)
                    if w["period"] == warned.q4]
        assert after["until"] == "2099-10-05"


class TestOweNothingQuarter:
    """S6, criteria 1, 2 and 10: a quarter Case Workers does not take part in,
    and a package of the other five tables, all green. The quarter opens at
    the package's filing, Case Workers is inherited before any run, the
    readers' cross-table checks read the inherited table and pass, and all
    five promote. The real tools run, over the fixture's clean population.

    THE NO-DEADLOCK NFR is what this pins: under opening-at-first-promotion
    the readers' checks ran with no Case Workers at all, could not pass, and
    nothing could be the first promotion that would have brought it."""

    def test_readers_of_case_workers_promote_in_a_quarter_it_sits_out(
            self, cp_raw_dir, supply_dsn, monkeypatch, tmp_path):
        import random
        import uuid as _uuid
        from datetime import date as _date
        from datetime import timedelta
        from pathlib import Path

        from fixture_ids import CP_REF_RUN_ID
        from qa_tools.common import (arrival_lifecycle, arrivals, delivery, delivery_log,
                                     hierarchy, knock_on, qa_store, schedule, supply_db)
        from qa_tools.tools import orchestrate, stage

        tag = _uuid.uuid4().hex[:6]
        q2, q4 = f"2099-{tag}-Q2", f"2099-{tag}-Q4"
        order = {q2: _date(2099, 4, 1), q4: _date(2099, 10, 1)}
        real_not_expected, real_date_of = schedule.not_expected_periods, schedule.date_of
        monkeypatch.setattr(schedule, "not_expected_periods",
                            lambda ds, *a, **k: ({q4: "delivered in Feb and Aug only"}
                                                 if ds == CASE_WORKERS
                                                 else real_not_expected(ds, *a, **k)))
        monkeypatch.setattr(schedule, "date_of",
                            lambda name, ds=None: order.get(name) or real_date_of(name, ds))

        def assign(**kw):
            slot = q2 if kw["dataset_id"] == CASE_WORKERS else q4
            return assign_mod.Assignment(dataset_id=kw["dataset_id"],
                                         supply_id=kw["supply_id"], slot=slot,
                                         branch="pytest", considered=(slot,),
                                         received_at=kw["at"])
        monkeypatch.setattr(assign_mod, "assign", assign)
        # THE KNOCK-ON IS NOT THIS TEST'S SUBJECT: the readers must pass in
        # their own runs, which is what the opening makes possible.
        monkeypatch.setattr(knock_on, "follow_up_stream", lambda *a, **k: [])

        ref = Path(cp_raw_dir) / CP_REF_RUN_ID
        deliveries, receipts = tmp_path / "deliveries", tmp_path / "receipts"
        t1 = datetime(2026, 1, 3, 6, tzinfo=timezone.utc) + timedelta(
            seconds=random.randrange(86000))
        t2 = t1 + timedelta(days=40)
        delivery.write_delivery(f"pytest-s6-cw-{tag}", {
            "cp_case_workers.csv": (ref / "cp_case_workers.csv").read_text()},
            received_at=t1, deliveries_dir=deliveries, receipts_dir=receipts)
        five = [d for d in ("cp_clients", "cp_notifications", "cp_investigations",
                            "cp_placements", "cp_carers")]
        delivery.write_delivery(f"pytest-s6-five-{tag}", {
            f"{t}.csv": (ref / f"{t}.csv").read_text() for t in five},
            received_at=t2, deliveries_dir=deliveries, receipts_dir=receipts)
        stage.build_all("child-protection", deliveries_dir=deliveries, receipts_dir=receipts)
        for d in delivery.list_deliveries(deliveries, receipts):
            delivery_log.record(d, arrivals.recognise(d))
        found = sorted(arrivals.arrivals_for("child-protection", "cp_run_", deliveries,
                                             receipts),
                       key=lambda a: (a.sequence, a.run_index, a.run_id))
        assert len(found) == 6

        steps = orchestrate.steps("child-protection")
        (cw,) = [a for a in found if CASE_WORKERS in a.files_by_dataset]
        arrival_lifecycle.process_all([cw], steps=steps, run_by="pytest")
        with supply_db.connect(label="pytest-s6") as conn:
            # Q2's Case Workers in the warehouse: a person's promotion, since the
            # fixture's small population is short of one of its own row floors
            # - the readers in Q4 are this test's subject, not Q2.
            (item,) = filing.supplies_of(conn, cw)
            if dl.promoted_into(conn, CASE_WORKERS, q2) != item["supply"]:
                from qa_tools.common import promotion
                promotion.promote(conn, **KEYS, dataset_id=CASE_WORKERS, supply=item["supply"],
                                  period=q2, physical_tables=item["physical_tables"],
                                  actor="pytest", actor_kind=dl.PERSON, supply_is_red=True,
                                  reason="the Q2 supply the test stands on",
                                  effective_at=(t1 + timedelta(hours=2)).isoformat())
            cw_supply = dl.promoted_into(conn, CASE_WORKERS, q2)
            assert cw_supply == item["supply"]
            assert not period_schema.opened(conn, q4)
        rest = [a for a in found if a is not cw]
        arrival_lifecycle.process_all(rest, steps=steps, run_by="pytest")

        with supply_db.connect(label="pytest-s6") as conn:
            (opened_by,) = conn.execute('SELECT opened_by FROM "qa".period WHERE name = ?',
                                        [q4]).fetchone()
            assert opened_by.startswith("the filing of ") and "child-protection" in opened_by
            (inherit,) = [e for e in dl.decisions_for(conn, CASE_WORKERS)
                          if e["to_slot"] == q4 and e["action"] == dl.INHERIT]
            assert inherit["supply"] == cw_supply
            supplies = [x["supply"] for a in rest for x in filing.supplies_of(conn, a)]
            assert len(supplies) == 5
            # INHERITED BEFORE ANY CHECK: every reader's check of Case Workers
            # read the inherited supply, and passed.
            reads = [tuple(r) for r in conn.execute(
                f'SELECT c.check_id, c.status, k.supply_id FROM "{qa_store.SCHEMA}".check_result c '
                f'JOIN "{qa_store.SCHEMA}".check_read k ON k.check_result_id = c.id '
                f'JOIN "{qa_store.SCHEMA}".run r ON r.run_key = c.run_key '
                "WHERE k.logical_table = 'cp_case_workers' AND r.supply_id = ANY(?)",
                [supplies]).fetchall()]
            assert reads, "the readers' checks of Case Workers ran"
            assert {s for _c, _st, s in reads} == {cw_supply}
            assert {st for _c, st, _s in reads} == {"pass"}, reads
            # ALL FIVE PROMOTE.
            for a in rest:
                (ds,) = a.files_by_dataset
                assert dl.promoted_into(conn, ds, q4), f"{ds} was not promoted into {q4}"
        del hierarchy
