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
    supply = f"{dataset_id}@{AT.strftime('%Y%m%d%H%M%S')}{id(world) % 1000000:06d}"
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
        carry_forward.carry_forward(conn, dataset_id=CASE_WORKERS, period=warned.q4,
                                    actor="Keith", reason="current",
                                    effective_at="2099-10-05T09:00:00+08:00")
        (after,) = [w for w in carry_forward.for_dashboard(CASE_WORKERS, conn)
                    if w["period"] == warned.q4]
        assert after["until"] == "2099-10-05"
