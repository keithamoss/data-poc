"""A person places a held supply into a period (REQ-PIPE-163): filed there as a
re-file from no period by that person, its hold resolved, its checks owed -
through ONE shared placer the rule's own placements use too. Against a real
database; each test mints its own periods. Written first."""
from __future__ import annotations

import re
import uuid

import pytest

import test_supersession as _base
from qa_tools.common import decision_log as dl
from qa_tools.common import filing, supply_holds
from test_supersession import DS, REAL_PERSON, WHEN, _filed

conn = _base.conn
period = _base.period


@pytest.fixture
def target():
    return f"2099-P{uuid.uuid4().hex[:6]}"


def _held(conn, period, dataset=DS):
    """A supply the assignment rule held: filed to no period, with an open
    assignment-rule hold."""
    import filing_support

    if dataset == DS:
        supply, table = _filed(conn, period, "2026-05-01T01:00:00+00:00")
    else:
        key = uuid.uuid4().hex[:12]
        supply, table, delivery = f"{dataset}@{key}", f"x__{key}", f"pytest-place-{key}"
        conn.execute("INSERT INTO qa.delivery (name, received_at, received_instant) "
                     "VALUES (?, ?, ?)", [delivery, WHEN, WHEN])
        conn.execute("INSERT INTO qa.filing (dataset_id, supply_id, slot, branch, delivery) "
                     "VALUES (?, ?, ?, 'pytest', ?)", [dataset, supply, period, delivery])
    (delivery,) = conn.execute(f"SELECT delivery FROM {filing.CURRENT} WHERE supply_id = ?",
                               [supply]).fetchall()[0]
    filing_support.place(conn, dataset, supply, None, delivery)
    supply_holds.raise_hold(conn, dataset_id=dataset, supply_id=supply,
                            kind=supply_holds.ASSIGNMENT_RULE,
                            reason={"unavailable": [], "considered": []}, raised_by="pytest")
    return supply, table


def _request(supply, to_period, dataset=DS, **kw):
    from qa_tools.common import filing_decisions as fd, people

    return fd.Request(operation=fd.PLACE, dataset_id=dataset,
                      actor=people.person_by_email(REAL_PERSON), reason="supplier's Q3 file",
                      supply=supply, to_period=to_period, **kw)


def _place(conn, supply, to_period, dataset=DS):
    from qa_tools.common import filing_decisions as fd

    key = fd.consequences(conn, _request(supply, to_period, dataset)).key
    return fd.apply(_request(supply, to_period, dataset, acknowledged=key or None),
                    effective_at=WHEN, conn=conn)


def _current_slot(conn, supply):
    return conn.execute(f"SELECT slot FROM {filing.CURRENT} WHERE dataset_id = ? AND "
                        "supply_id = ?", [DS, supply]).fetchall()[0][0]


class TestAPlacementIsARefileFromNoPeriodByAPerson:
    """Criteria 1, 2, 9 and 41."""

    def test_it_is_filed_there_its_hold_resolved_and_its_checks_owed(self, conn, period, target):
        from qa_tools.common import recheck

        supply, _ = _held(conn, period)
        got = _place(conn, supply, target)
        assert got.changed and got.owed
        assert _current_slot(conn, supply) == target
        assert supply_holds.hold_on(conn, DS, supply) is None
        (entry,) = [d for d in dl.decisions_for(conn, DS)
                    if d["action"] == dl.REFILE and d["supply"] == supply]
        assert entry["from_slot"] is None and entry["to_slot"] == target
        assert entry["actor_kind"] == dl.PERSON
        (owed,) = [o for o in recheck.owed(conn, DS) if o.id in got.owed]
        assert owed.supply_id == supply and owed.caused_by_decision == entry["id"]

    def test_the_hold_names_the_decision_that_resolved_it(self, conn, period, target):
        supply, _ = _held(conn, period)
        _place(conn, supply, target)
        (resolved_by,) = conn.execute(
            f"SELECT resolved_by FROM {supply_holds.TABLE} WHERE dataset_id = ? AND "
            "supply_id = ?", [DS, supply]).fetchall()[0]
        (entry,) = [d for d in dl.decisions_for(conn, DS)
                    if d["action"] == dl.REFILE and d["supply"] == supply]
        assert resolved_by == entry["id"]

    def test_it_is_said_as_placed_into_the_period_never_as_a_refile(self, conn, period, target):
        supply, _ = _held(conn, period)
        said = _place(conn, supply, target).message
        assert f"placed into {target}" in said
        assert "re-file" not in said and "None" not in said and "->" not in said


class TestTheDecisionLogAcceptsAPersonsRefileFromNoPeriodOnlyToPlace:
    """Criterion 39."""

    def _decision(self, supply, to_period):
        return dl.Decision(
            agency_id="child-protection-family-support", collection_id="child-protection",
            dataset_id=DS, action=dl.REFILE, supply=supply, actor=REAL_PERSON,
            actor_kind=dl.PERSON, effective_at=WHEN, from_slot=None, to_slot=to_period,
            reason="r")

    def test_refused_for_a_supply_with_no_open_hold_naming_place(self, conn, period, target):
        supply, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused, match="place"):
            with dl.apply_decision(conn, self._decision(supply, target)):
                pass

    def test_accepted_for_a_held_supply(self, conn, period, target):
        supply, _ = _held(conn, period)
        with dl.apply_decision(conn, self._decision(supply, target)) as entry_id:
            assert entry_id


class TestRefusedBeforeAnythingIsRecorded:
    """Criteria 7, 8, 33, 34 and 35 - each refusal appends nothing."""

    def _nothing_recorded(self, conn, supply):
        assert not [d for d in dl.decisions_for(conn, DS) if d["supply"] == supply]
        assert supply_holds.hold_on(conn, DS, supply) is not None

    def test_a_supply_that_is_not_held(self, conn, period, target):
        supply, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused, match="not held"):
            _place(conn, supply, target)

    def test_a_period_the_calendar_does_not_generate(self, conn, period):
        supply, _ = _held(conn, period)
        with pytest.raises(dl.DecisionRefused) as refused:
            _place(conn, supply, "2026-Q9")
        assert "2026-Q9" in str(refused.value)
        assert f"\n  mothman schedule show --dataset {DS}" in str(refused.value)
        self._nothing_recorded(conn, supply)

    def test_a_period_the_dataset_owes_nothing_in_quotes_why(self, conn, period):
        """cp-case-workers participates in February and August only, so the
        calendar's 2023-Q2 is a period it owes nothing in - for the reason its
        participation version gives."""
        supply = _held(conn, period, dataset="cp-case-workers")[0]
        with pytest.raises(dl.DecisionRefused) as refused:
            _place(conn, supply, "2023-Q2", dataset="cp-case-workers")
        said = str(refused.value)
        assert "owes nothing" in said and "staffing register" in said
        assert "un-inherit" not in said
        assert "\n  mothman schedule show --dataset cp-case-workers" in said
        assert not [d for d in dl.decisions_for(conn, "cp-case-workers")
                    if d["supply"] == supply]

    def test_an_inherited_period_names_un_inherit(self, conn, period, target, monkeypatch):
        supply, _ = _held(conn, period)
        real = dl.held

        class Inherited:
            held_as, holder, stands_on, filled = dl.INHERITED, "x", target, False

        monkeypatch.setattr(dl, "held", lambda c, d, p, **k: Inherited() if p == target
                            else real(c, d, p, **k))
        with pytest.raises(dl.DecisionRefused, match="un-inherit"):
            _place(conn, supply, target)
        self._nothing_recorded(conn, supply)

    def test_a_version_waiting_there_is_decided_first(self, conn, period, target):
        supply, _ = _held(conn, period)
        waiting, _ = _filed(conn, target, "2026-06-01T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused) as refused:
            _place(conn, supply, target)
        said = str(refused.value)
        assert waiting in said and "decided first" in said
        assert (f"\n  mothman supply decide --operation <promote|reject> --dataset {DS} "
                f"--period {target} --supply {waiting} --reason '<why>'") in said
        self._nothing_recorded(conn, supply)

    def test_an_open_pair_there_is_settled_first(self, conn, period, target, monkeypatch):
        from qa_tools.common import settlement

        supply, _ = _held(conn, period)
        monkeypatch.setattr(settlement, "open_pair_in",
                            lambda c, d, p, besides: f"{p} has two files of its own waiting "
                            "to be settled" if p == target else None)
        with pytest.raises(dl.DecisionRefused, match="settled"):
            _place(conn, supply, target)
        self._nothing_recorded(conn, supply)

    def test_a_dataset_the_backstop_refuses(self, conn, period, target, monkeypatch):
        from qa_tools.common import agreement_drift

        supply, _ = _held(conn, period)
        monkeypatch.setattr(agreement_drift, "refusal_for",
                            lambda c, d, **k: agreement_drift.Refusal(dataset_id=d))
        with pytest.raises(dl.DecisionRefused) as refused:
            _place(conn, supply, target)
        said = str(refused.value)
        assert "without a declared correction" in said
        assert "once the correction is declared" in said
        self._nothing_recorded(conn, supply)


class TestOnePlacer:
    """Criterion 40: a person's placement, a confirmed correction's and the
    rule's re-file of holds configuration now covers all file a held supply
    through placing.place - and refiling.plan still refuses a held supply."""

    def test_the_rules_drain_places_through_the_shared_placer(self, conn, period, target,
                                                             monkeypatch):
        from qa_tools.common import placing, schedule_ended

        supply, _ = _held(conn, period)
        calls = []
        real = placing.place

        def spy(*a, **k):
            calls.append(k.get("supply"))
            return real(*a, **k)

        monkeypatch.setattr(placing, "place", spy)
        monkeypatch.setattr(schedule_ended, "_covering_slot",
                            lambda ds, at, agreement=None: type("S", (), {"name": target})())
        done = schedule_ended.refile_holds(
            lambda c: [h for h in supply_holds.outstanding(c, dataset_id=DS)
                       if h.supply_id == supply],
            lambda h, slot: "dates now cover it", lambda h, slot: "", say=lambda *_: None)
        assert done == [(DS, supply, target)] and calls == [supply]
        assert _current_slot(conn, supply) == target

    def test_a_held_supply_is_still_refused_as_a_refile(self, conn, period, target):
        from qa_tools.common import refiling

        supply, _ = _held(conn, period)
        with pytest.raises(dl.DecisionRefused, match="Place it instead"):
            refiling.plan(conn, dataset_id=DS, supply=supply, to_period=target)


class TestPersonsPromoteOfAHeldSupplyGivesTheHoldsResponses:
    """Criterion 38: still refused, now naming place, its menu path and its
    flag form, each command on a line of its own."""

    def test_refusal_offers_place_and_reject(self, conn, period, target):
        from qa_tools.common import filing_decisions as fd, people

        supply, _ = _held(conn, period)
        with pytest.raises(dl.DecisionRefused) as refused:
            fd.apply(fd.Request(operation=fd.PROMOTE, dataset_id=DS,
                                actor=people.person_by_email(REAL_PERSON), reason="r",
                                period=target, supply=supply), effective_at=WHEN, conn=conn)
        said = str(refused.value)
        assert (f"\n  mothman supply decide --operation place --dataset {DS} "
                f"--supply {supply} --to-period <period> --reason '<why>'") in said
        assert "Filing decisions" in said
        assert f"\n  mothman supply decide --operation reject --dataset {DS}" in said


class TestTheGitHubRouteRefusesIt:
    """Criteria 14 and 36: offered on the terminal route only."""

    def test_a_comment_naming_place_appends_nothing_and_says_where(self, conn, period, target):
        from qa_tools.common import filing_from_github as gh
        from qa_tools.common import placing

        supply, _ = _held(conn, period)
        comment = gh.Comment(author="someone",
                             body=f"/place supply: {supply} to-period: {target}\nwhy",
                             slot_key=f"{DS}/{target}")
        with pytest.raises(dl.DecisionRefused) as got:
            gh.read(comment)
        said = str(got.value)
        assert "made in the terminal" in said and placing.where_to_decide(DS) in said
        assert "Settling two files" not in said
        assert not [d for d in dl.decisions_for(conn, DS) if d["supply"] == supply]


@pytest.fixture
def cli(monkeypatch):
    from click.testing import CliRunner

    from cli import filing_tui, supply
    from qa_tools.common import filing_decisions as fd, knock_on, people

    monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                        lambda: people.person_by_email(REAL_PERSON))
    monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
    monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])
    return lambda argv: CliRunner().invoke(supply.supply_group, argv)


def _no_run(monkeypatch):
    from qa_tools.common import recheck

    def refuse(*a, **k):
        raise AssertionError("decide without --wait must not run the checks")

    monkeypatch.setattr(recheck, "run", refuse)


def _runs_as(monkeypatch, **outcome):
    from qa_tools.common import recheck

    seen = []

    def fake(owed_id, **k):
        seen.append(owed_id)
        if "raise_" in outcome:
            raise outcome["raise_"]
        return recheck.Outcome(owed_id, "rk", **outcome)

    monkeypatch.setattr(recheck, "run", fake)
    return seen


def _plain(output: str) -> str:
    """The output with any colour codes taken out, its lines kept."""
    return re.sub(r"\x1b\[[0-9;]*m", "", output)


def _said(output: str) -> str:
    """The output as one line of words, the panels' borders and any colour
    codes taken out - CI forces colour on (1e6fffb's run went red on it)."""
    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    return " ".join(re.sub(r"[\u2500-\u257f]", " ", plain).split())


def _argv(supply, target, *extra):
    return ["decide", "--operation", "place", "--dataset", DS, "--supply", supply,
            "--to-period", target, "--reason", "supplier's Q3 file", "--yes", *extra]


class TestDecidePlacesThroughFlags:
    """Criteria 4, 15, 27, 32."""

    def test_it_leaves_the_checks_owed_and_names_the_pass(self, conn, period, target, cli,
                                                          monkeypatch):
        from qa_tools.common import recheck

        supply, _ = _held(conn, period)
        _no_run(monkeypatch)
        got = cli(_argv(supply, target))
        assert got.exit_code == 0, got.output
        assert f"placed into {target}" in _plain(got.output)
        assert "\nmothman pipeline process\n" in _plain(got.output)
        assert "every owed QA run" in _said(got.output)
        assert [o for o in recheck.owed(conn, DS) if o.supply_id == supply]

    def test_a_placement_needs_the_supply(self, cli):
        got = cli(["decide", "--operation", "place", "--dataset", DS, "--to-period",
                   "2099-Q1", "--reason", "r", "--yes"])
        assert got.exit_code != 0 and "--supply" in _plain(got.output)

    def test_a_placement_takes_no_period(self, conn, period, target, cli):
        supply, _ = _held(conn, period)
        got = cli(_argv(supply, target, "--period", target))
        assert got.exit_code != 0 and "--period" in _plain(got.output) and "--to-period" in _plain(got.output)

    def test_the_dataset_must_be_the_supplys_own(self, conn, period, target, cli):
        supply, _ = _held(conn, period)
        argv = _argv(supply, target)
        argv[argv.index(DS)] = "cp-clients"
        got = cli(argv)
        assert got.exit_code != 0 and DS in _plain(got.output) and "cp-clients" in _plain(got.output)

    def test_help_names_place_and_says_checks_are_left_owed(self, cli):
        said = _said(cli(["decide", "--help"]).output)
        assert "place" in said
        assert "leaves a decision's checks owed unless --wait is given" in said

    def test_wait_is_refused_for_a_decision_that_owes_no_run(self, cli):
        got = cli(["decide", "--operation", "promote", "--dataset", DS, "--period",
                   "2099-Q1", "--supply", "x", "--reason", "r", "--yes", "--wait"])
        assert got.exit_code != 0 and "--wait" in _plain(got.output) and "promote" in _plain(got.output)


class TestDecideWaitRunsTheChecks:
    """Criteria 19, 20, 25, 26, 28, 29, 30."""

    def test_it_ends_with_where_the_supply_stands(self, conn, period, target, cli, monkeypatch):
        seen = _runs_as(monkeypatch, completed=True, message="m", status="green",
                        period=target, promoted=False, waits_because="it waits for a person")
        supply, _ = _held(conn, period)
        got = cli(_argv(supply, target, "--wait"))
        assert got.exit_code == 0, got.output
        assert seen
        said = _said(got.output)
        assert f"had not been checked in {target} before" in said
        assert "filed, and nothing is lost" in said
        for word in ("again", "rejected", "refused", "earlier verdict stands"):
            assert not re.search(rf"\b{word}\b", said.lower()), word

    def test_checks_that_do_not_finish_exit_with_their_own_code(self, conn, period, target, cli,
                                                                monkeypatch):
        from cli import filing_tui

        _runs_as(monkeypatch, completed=False, message="boom")
        supply, _ = _held(conn, period)
        got = cli(_argv(supply, target, "--wait"))
        assert got.exit_code == filing_tui.CHECKS_STILL_OWED_EXIT not in (0, 1)
        said = _said(got.output)
        assert "placement stands" in said and "still owed" in said

    def test_a_run_claimed_elsewhere_shows_no_verdict(self, conn, period, target, cli,
                                                      monkeypatch):
        from cli import filing_tui
        from qa_tools.common import recheck

        _runs_as(monkeypatch, completed=False, message=recheck.CLAIMED_ELSEWHERE)
        supply, _ = _held(conn, period)
        got = cli(_argv(supply, target, "--wait"))
        assert got.exit_code == filing_tui.CHECKS_STILL_OWED_EXIT
        said = _said(got.output)
        assert "being run elsewhere" in said and "will finish there" in said
        assert "green" not in said and "red" not in said.split()

    def test_ctrl_c_ends_without_a_traceback(self, conn, period, target, cli, monkeypatch):
        from cli import filing_tui

        _runs_as(monkeypatch, raise_=KeyboardInterrupt())
        supply, _ = _held(conn, period)
        got = cli(_argv(supply, target, "--wait"))
        assert got.exit_code == filing_tui.CHECKS_STILL_OWED_EXIT
        assert "Traceback" not in _plain(got.output)
        said = _said(got.output)
        assert "placement stands" in said and "still owed" in said
        assert "\nmothman pipeline process\n" in _plain(got.output)

    def test_a_refile_through_decide_accepts_wait_likewise(self, conn, period, target, cli,
                                                           monkeypatch):
        seen = _runs_as(monkeypatch, completed=True, message="m", status="amber",
                        period=target, promoted=True)
        supply, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        from qa_tools.common import filing_decisions as fd, people

        key = fd.consequences(conn, fd.Request(
            operation=fd.REFILE, dataset_id=DS, actor=people.person_by_email(REAL_PERSON),
            reason="r", period=period, supply=supply, to_period=target)).key
        got = cli(["decide", "--operation", "refile", "--dataset", DS, "--period", period,
                   "--supply", supply, "--to-period", target, "--reason", "r", "--yes",
                   "--wait", *(["--acknowledge", key] if key else [])])
        assert got.exit_code == 0, got.output
        assert seen and "promoted it into" in _said(got.output)


class TestThePeriodChooser:
    """Criterion 16: periods offered as a choice, nearest the receipt on both
    sides, every owed-nothing period in its place and not selectable."""

    def _received(self, iso):
        from datetime import datetime

        return datetime.fromisoformat(iso)

    def test_it_opens_on_the_nearest_owed_periods_either_side(self):
        from qa_tools.common import placing

        got = placing.period_choices("cp-case-workers",
                                     self._received("2024-05-15T09:00:00+08:00"), {})
        chosen = [r.period for r in got.rows if r.selectable]
        assert "2024-Q1" in chosen and "2024-Q3" in chosen
        q1 = next(r for r in got.rows if r.period == "2024-Q1")
        q3 = next(r for r in got.rows if r.period == "2024-Q3")
        assert "closed when it arrived" in q1.label
        assert "not yet open when it arrived" in q3.label

    def test_a_period_owed_nothing_is_shown_in_its_place_and_not_selectable(self):
        from qa_tools.common import placing

        got = placing.period_choices("cp-case-workers",
                                     self._received("2024-05-15T09:00:00+08:00"), {})
        names = [r.label.split(" ")[0] for r in got.rows]
        assert names.index("2024-Q1") < names.index("2024-Q2") < names.index("2024-Q3")
        q2 = got.rows[names.index("2024-Q2")]
        assert not q2.selectable and q2.period is None
        assert "owes nothing" in q2.label and "staffing register" in q2.label

    def test_it_shows_each_periods_state_now_and_what_comes_first(self):
        from qa_tools.common import placing

        got = placing.period_choices(
            "cp-carers", self._received("2024-05-15T09:00:00+08:00"),
            {"2024-Q1": "promoted", "2024-Q2": "inherited", "2024-Q3": "awaiting-decision"})
        by = {r.period: r.label for r in got.rows}
        # The period list's own word for it (#188, cli-ux M5).
        assert by["2024-Q1"].endswith("promoted")
        assert "un-inherit it first" in by["2024-Q2"]
        assert "decide the version waiting there first" in by["2024-Q3"]

    def test_it_pages_earlier_and_later(self):
        from qa_tools.common import placing

        at = self._received("2024-05-15T09:00:00+08:00")
        first = placing.period_choices("cp-carers", at, {})
        earlier = placing.period_choices("cp-carers", at, {}, page=-1)
        later = placing.period_choices("cp-carers", at, {}, page=1)
        assert first.has_earlier and first.has_later

        # A RUN OF QUARTERS OWED NOTHING is one row with no period to choose
        # (cp-carers' 2022-Q1 and Q2 turn-off, TS-63), so it is not compared.
        def periods(choices):
            return [r.period for r in choices.rows if r.period is not None]
        assert min(periods(earlier)) < min(periods(first))
        assert max(periods(later)) > max(periods(first))


class TestAHeldSupplyCanBeRejected:
    """Criterion 11: from the terminal and through decide, with a reason,
    ending its hold - though it has no period."""

    def test_through_the_shared_implementation(self, conn, period):
        from qa_tools.common import filing_decisions as fd, people, supersession

        supply, table = _held(conn, period)
        got = fd.apply(fd.Request(operation=fd.REJECT, dataset_id=DS,
                                  actor=people.person_by_email(REAL_PERSON),
                                  reason="not this supplier's file", supply=supply),
                       effective_at=WHEN, conn=conn)
        assert got.changed
        assert supply_holds.hold_on(conn, DS, supply) is None
        assert supersession._rejected(conn, DS, supply)
        assert _base._schema_of(conn, table) == ["rejected"]

    def test_through_decide_without_a_period(self, conn, period, cli):
        supply, _ = _held(conn, period)
        got = cli(["decide", "--operation", "reject", "--dataset", DS, "--supply", supply,
                   "--reason", "not ours", "--yes"])
        assert got.exit_code == 0, got.output
        assert supply_holds.hold_on(conn, DS, supply) is None

    def test_a_reject_with_no_period_of_a_supply_that_is_not_held_is_refused(self, conn, period):
        from qa_tools.common import filing_decisions as fd, people

        supply, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")
        with pytest.raises(dl.DecisionRefused, match="period"):
            fd.apply(fd.Request(operation=fd.REJECT, dataset_id=DS,
                                actor=people.person_by_email(REAL_PERSON), reason="r",
                                supply=supply), effective_at=WHEN, conn=conn)


class TestTheFilingDecisionsDoorListsHeldSupplies:
    """Criteria 10, 17, 18 and 22, driven through the door's own flows."""

    def _row(self, **kw):
        from qa_tools.common import filing_queue as fq

        base = dict(dataset_id=DS, dataset_name="Carer Register", supply="cp-carers@h1",
                    received_at=None, received_text="15 May 2024, 09:00",
                    why="cp-carers@h1 could not be placed - 2024-Q1: closed.",
                    schedule_ended=False)
        base.update(kw)
        return fq.HeldRow(**base)

    def _door(self, monkeypatch, held, waiting):
        import contextlib

        from cli import filing_tui
        from qa_tools.common import filing_queue as fq

        monkeypatch.setattr(filing_tui, "open_log", lambda: contextlib.nullcontext(None))
        monkeypatch.setattr(fq, "awaiting", lambda *a, **k: waiting)
        monkeypatch.setattr(fq, "closed_gaps", lambda *a, **k: [])
        monkeypatch.setattr(fq, "held_in", lambda *a, **k: held)
        offered = []
        monkeypatch.setattr(filing_tui.common, "select",
                            lambda msg, choices, **k: offered.append(list(choices)) or None)
        return filing_tui, offered

    def test_held_supplies_are_their_own_group_above_the_slot_rows(self, monkeypatch, capsys):
        from qa_tools.common import slot_state

        slot = slot_state.SlotState(state=slot_state.AWAITING_DECISION, dataset_id=DS,
                                    period="2024-Q2", supply="cp-carers@w1")
        door, offered = self._door(monkeypatch, [self._row()], [slot])
        door.queue_flow("child-protection")
        out = _said(capsys.readouterr().out)
        assert "Held - no period yet (1)" in out
        assert out.index("Held - no period yet") < out.index("waiting on a decision")
        assert "15 May 2024, 09:00" in out and "could not be placed" in out
        (choices,) = offered
        assert any(c.startswith(f"Held, no period yet: {DS}") for c in choices)

    def test_a_held_supply_offers_place_and_reject(self, monkeypatch):
        door, offered = self._door(monkeypatch, [], [])
        door.held_flow(self._row())
        (choices,) = offered
        assert [c.split(" -")[0] for c in choices] == ["place", "reject"]

    def test_a_schedule_ended_hold_offers_only_adding_dates(self, monkeypatch, capsys):
        door, offered = self._door(monkeypatch, [], [])
        door.held_flow(self._row(schedule_ended=True, why="arrived after the schedule ended"))
        out = capsys.readouterr().out
        assert offered == []
        assert "contract/calendar.yaml" in out
        assert "\nmothman schedule draft-correction\n" in out
        assert "nothing to decide" not in out.lower()

    def test_how_it_would_read_is_shown_before_the_reason_is_asked(self, conn, period, target,
                                                                    monkeypatch):
        from cli import filing_tui

        supply, _ = _held(conn, period)
        order = []
        monkeypatch.setattr(filing_tui, "choose_period", lambda *a, **k: target)
        monkeypatch.setattr(filing_tui, "_show",
                            lambda text, title, style: order.append(("shown", title, text)))
        monkeypatch.setattr(filing_tui, "apply_decision",
                            lambda **k: order.append(("decide", k["operation"])) or None)
        filing_tui.place_flow(self._row(supply=supply))
        assert [o[0] for o in order] == ["shown", "decide"]
        assert order[0][1] == f"Placing it into {target}"
        assert "reads" in order[0][2] and "holds" in order[0][2]
        assert order[1] == ("decide", "place")


class TestEveryListingSaysPlaced:
    """Criterion 41: `mothman supply decisions` and `filings` call it a
    placement - never a re-file, 'None -> period' or a machine name."""

    def test_decisions_and_filings(self, conn, period, target, cli, monkeypatch):
        from cli import supply as supply_cli

        monkeypatch.setattr(supply_cli.console, "_width", 400)
        supply, _ = _held(conn, period)
        _place(conn, supply, target)
        decisions = _said(cli(["decisions", "--dataset", DS, "--limit", "100000"]).output)
        filings = _said(cli(["filings", "--dataset", DS, "--limit", "100000"]).output)
        for said in (decisions, filings):
            assert f"placed into {target}" in said
            assert f"None -> {target}" not in said


class TestAPairHeldWholeIsPlacedTogether:
    """Criterion 37: both files into the period in one transaction, still
    contested; the second file's move named and confirmed; --wait refused."""

    @pytest.fixture
    def held_pair(self, conn):
        from datetime import date, timedelta

        import filing_support
        from pair_support import DS as BR, Pair, _at, free_day

        day = free_day(conn, date(2026, 11, 1))
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
        filing_support.place(conn, BR, p.pair, None, p.delivery)
        supply_holds.raise_hold(conn, dataset_id=BR, supply_id=p.pair,
                                kind=supply_holds.ASSIGNMENT_RULE,
                                reason={"unavailable": [], "considered": []},
                                raised_by="pytest")
        p.target = (day + timedelta(days=1)).isoformat()
        return BR, p

    def test_both_files_move_named_and_neither_is_checked(self, conn, held_pair):
        from qa_tools.common import filing_decisions as fd, recheck, supply_files

        ds, p = held_pair
        found = fd.consequences(conn, _request(p.pair, p.target, ds))
        said = " ".join(found.lines)
        assert p.files[0][0] in said and p.files[1][0] in said and "still contested" in said
        got = _place(conn, p.pair, p.target, ds)
        assert got.changed and got.owed == ()
        assert supply_files.resolve(conn, ds, p.pair).period == p.target
        assert supply_files.open_contest(conn, ds, p.pair) is not None
        assert not [o for o in recheck.owed(conn, ds) if o.supply_id == p.pair]

    def test_wait_is_refused_naming_both_files_and_where(self, conn, held_pair, cli):
        from qa_tools.common import placing

        ds, p = held_pair
        got = cli(["decide", "--operation", "place", "--dataset", ds, "--supply", p.pair,
                   "--to-period", p.target, "--reason", "r", "--yes", "--wait"])
        said = _said(got.output)
        assert got.exit_code != 0
        assert p.files[0][0] in said and p.files[1][0] in said
        assert placing.where_to_decide(ds) in said


class TestTheRestOfThePlacementRules:

    def test_a_closed_period_can_be_named(self):
        """Criterion 6: a person is not the assignment rule."""
        from qa_tools.common import placing

        assert placing.period_problem(DS, "2023-Q1") is None

    def test_a_placement_is_not_a_persons_decision_about_its_data(self, conn, period, target):
        """Criterion 24: a placed supply checked green may promote itself."""
        from qa_tools.common import rejection

        supply, _ = _held(conn, period)
        _place(conn, supply, target)
        assert not rejection.decided_by_a_person(conn, DS, supply)

    def test_the_reason_prompt_says_it_is_published(self, conn, period, target, monkeypatch):
        """Criterion 21."""
        from cli import filing_tui
        from qa_tools.common import people

        supply, _ = _held(conn, period)
        asked = []
        monkeypatch.setattr(filing_tui.common, "text_prompt",
                            lambda message, **k: asked.append(message) or None)
        filing_tui.apply_decision(operation="place", dataset_id=DS, period=target,
                                  supply=supply, to_period=target,
                                  actor=people.person_by_email(REAL_PERSON))
        assert asked and "published" in asked[0] and "dashboard" in asked[0]

    def test_the_door_runs_the_checks_while_the_person_waits(self, conn, period, target,
                                                             monkeypatch):
        """Criterion 3."""
        from cli import filing_tui
        from qa_tools.common import filing_decisions as fd, knock_on, people

        seen = _runs_as(monkeypatch, completed=True, message="m", status="green",
                        period=target, promoted=True)
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
        monkeypatch.setattr(knock_on, "follow_up", lambda *a, **k: [])
        supply, _ = _held(conn, period)
        got = filing_tui.apply_decision(operation="place", dataset_id=DS, period=target,
                                        supply=supply, to_period=target, reason="r", yes=True,
                                        actor=people.person_by_email(REAL_PERSON))
        assert got.changed and seen == list(got.owed) and got.checks_finished

    def test_holds_names_the_command_on_a_line_of_its_own(self, conn, period, cli):
        """Criterion 12."""
        supply, _ = _held(conn, period)
        out = cli(["holds"]).output
        assert (f"\nmothman supply decide --operation place --dataset {DS} --supply {supply} "
                f"--to-period <period> --reason '<why>'\n") in out
        assert "Filing decisions" in out


    def test_d8_a_reason_with_brackets_is_printed_as_written(self, conn, period, cli,
                                                               monkeypatch):
        """post-build-review #190 D8: describe() carries configuration text
        (a turned_off_reason), printed literally, never as Rich markup."""
        from qa_tools.common import supply_holds

        _held(conn, period)
        monkeypatch.setattr(supply_holds.Held, "describe",
                            lambda self: "held: turned off [/supplier paused]")
        got = cli(["holds"])
        assert got.exit_code == 0, got.output
        assert "turned off [/supplier paused]" in got.output


class TestASettlementsRefileTargetIsChosen:
    """Criterion 42, amending REQ-PIPE-193 criterion 19: the chooser, with
    the next period as its first choice - never a typed period."""

    def test_it_opens_on_the_next_period(self, monkeypatch):
        from cli import common, filing_tui, settle_tui
        from pair_support import DS as BR, _at
        from datetime import date
        import contextlib

        monkeypatch.setattr(filing_tui, "open_log", lambda: contextlib.nullcontext(None))
        from qa_tools.common import filing_queue as fq

        monkeypatch.setattr(fq, "slots_of", lambda *a, **k: [])
        seen = {}

        def pick(message, choices, **k):
            seen.update(k, choices=choices)
            return None

        monkeypatch.setattr(common, "select", pick)
        day = date(2026, 11, 2)
        assert settle_tui._target(BR, day.isoformat(), "f.csv", None,
                                  received_at=_at(day, "13:30")) is None
        assert seen["default"].startswith("2026-11-03 ")
        assert seen["default"] in seen["choices"]


class TestARepeatedRejectIsAlreadySo:
    """Found by REQ-GHUB-165's parity test (post-build-review): rejecting a
    supply already rejected appended a second rejection rather than saying
    nothing changed (REQ-GHUB-082 criterion 26)."""

    def test_the_second_reject_changes_nothing(self, conn, period):
        from qa_tools.common import filing_decisions as fd, people

        supply, _ = _filed(conn, period, "2026-05-01T01:00:00+00:00")

        def reject():
            return fd.apply(fd.Request(operation=fd.REJECT, dataset_id=DS,
                                       actor=people.person_by_email(REAL_PERSON), reason="r",
                                       period=period, supply=supply, confirmed=True),
                            effective_at=WHEN, conn=conn)

        assert reject().changed
        again = reject()
        assert not again.changed and "already rejected" in again.message
        assert len([d for d in dl.decisions_for(conn, DS)
                    if d["supply"] == supply and d["action"] == dl.REJECT]) == 1


# post-build-review #188 (delivery-critic on REQ-PIPE-163) - each written first.

class TestCriticFindingsOnPlacement:

    def test_d1_wait_is_accepted_for_un_supersede_which_owes_a_run(self, cli):
        """Criterion 27 refuses --wait only for a decision that owes no QA run;
        un-supersede owes one (REQ-PIPE-120)."""
        got = cli(["decide", "--operation", "un-supersede", "--dataset", DS, "--period",
                   "2099-Qnone", "--supply", "x", "--reason", "r", "--yes", "--wait"])
        assert "owes none" not in _said(got.output)

    def test_d4_holds_keeps_every_response_of_a_correction_hold(self, conn, period, cli):
        supply, _ = _held(conn, period)
        conn.execute(f"UPDATE {supply_holds.TABLE} SET reason = reason || "
                     "'{\"correction\": \"CAB-9\"}'::jsonb WHERE supply_id = ?", [supply])
        out = _said(cli(["holds"]).output)
        assert "declare a correction adding a date" in out
        assert f"--supply {supply} --to-period <period>" in out

    def test_d5_filings_names_the_rule_for_the_rules_placement(self, conn, period, target,
                                                               cli, monkeypatch):
        from cli import supply as supply_cli
        from qa_tools.common import placing

        monkeypatch.setattr(supply_cli.console, "_width", 400)
        supply, _ = _held(conn, period)
        with dl.decision_transaction(conn):
            placing.place(conn, agency_id="child-protection-family-support",
                          collection_id="child-protection", dataset_id=DS, supply=supply,
                          to_period=target, actor="calendar rule", actor_kind=dl.RULE,
                          reason="dates now cover it", effective_at=WHEN)
        said = _said(cli(["filings", "--dataset", DS, "--limit", "100000"]).output)
        line = next(x for x in said.split(supply)[1:2])
        assert "by the rule" in line and "by a person" not in line

    def test_d7_a_pair_placed_through_flags_says_where_it_is_settled(self, conn, cli):
        """Criterion 37: the outcome offers settling the pair now."""
        held = TestAPairHeldWholeIsPlacedTogether.held_pair.__wrapped__(None, conn)
        ds, p = held
        from qa_tools.common import filing_decisions as fd, placing

        key = fd.consequences(conn, _request(p.pair, p.target, ds)).key
        got = cli(["decide", "--operation", "place", "--dataset", ds, "--supply", p.pair,
                   "--to-period", p.target, "--reason", "r", "--yes", "--acknowledge", key])
        assert got.exit_code == 0, got.output
        said = _said(got.output)
        assert placing.where_to_decide(ds) in said and "settle" in said.lower()

    def test_d8_the_preview_says_on_time_in_words(self):
        from cli import filing_tui
        from qa_tools.common import placing

        p = placing.Plan(dataset_id=DS, supply="s", to_period="2024-Q1", received="",
                         classification="on_time")
        assert "on time" in filing_tui.preview(p) and "on_time" not in filing_tui.preview(p)

    def test_d9_an_agreement_refused_hold_offers_nothing_to_choose(self):
        from qa_tools.common import filing_queue as fq

        row = fq.HeldRow(dataset_id=DS, dataset_name="Carer Register", supply="s",
                         received_at=None, received_text="x", why="w", schedule_ended=False,
                         agreement_refused=True)
        assert fq.held_operations(row) == ()

    def test_d10_the_owes_nothing_refusal_has_one_full_stop(self, conn, period):
        supply = _held(conn, period, dataset="cp-case-workers")[0]
        with pytest.raises(dl.DecisionRefused) as refused:
            _place(conn, supply, "2023-Q2", dataset="cp-case-workers")
        assert ".." not in str(refused.value)

    def test_d6_a_refile_of_a_held_supply_names_the_place_command(self, conn, period, target):
        from qa_tools.common import refiling

        supply, _ = _held(conn, period)
        with pytest.raises(dl.DecisionRefused) as refused:
            refiling.plan(conn, dataset_id=DS, supply=supply, to_period=target)
        assert (f"\n  mothman supply decide --operation place --dataset {DS} --supply {supply} "
                f"--to-period <period>") in str(refused.value)


# post-build-review #188 (delivery-cli-ux-critic on REQ-PIPE-163) - written first.

class TestTheChooserOnARealScreen:

    def _drive(self, monkeypatch, dataset, received, first=None, current=None):
        import contextlib

        from cli import common, filing_tui
        from qa_tools.common import filing_queue as fq

        monkeypatch.setattr(filing_tui, "open_log", lambda: contextlib.nullcontext(None))
        monkeypatch.setattr(fq, "slots_of", lambda *a, **k: [])
        seen = {}

        def pick(message, choices, flag_hint, default=None):
            # As questionary does: a default that is not a selectable choice raises.
            labels = [c for c in choices if isinstance(c, str)]
            if default is not None and default not in labels:
                raise ValueError(f"Invalid `default` value passed: {default}")
            seen.update(choices=choices, default=default)
            return None

        monkeypatch.setattr(common, "select", pick)
        filing_tui.choose_period(dataset, received, "Which period?", first=first,
                                 current=current)
        return seen

    def test_blocker_a_page_with_an_owes_nothing_row_does_not_crash(self, monkeypatch):
        from datetime import datetime

        seen = self._drive(monkeypatch, "cp-case-workers",
                           datetime.fromisoformat("2024-05-15T09:00:00+08:00"))
        assert seen["choices"]

    def test_the_cursor_starts_on_the_nearest_owed_period(self, monkeypatch):
        from datetime import datetime

        seen = self._drive(monkeypatch, "cp-case-workers",
                           datetime.fromisoformat("2024-05-15T09:00:00+08:00"))
        assert seen["default"].startswith("2024-Q3 ")

    def test_the_supplys_own_period_cannot_be_chosen(self, monkeypatch):
        from datetime import datetime

        seen = self._drive(monkeypatch, "cp-carers",
                           datetime.fromisoformat("2024-05-15T09:00:00+08:00"),
                           current="2024-Q2")
        labels = [c for c in seen["choices"] if isinstance(c, str)]
        assert not any(c.startswith("2024-Q2 ") for c in labels)
        shown = [getattr(c, "title", "") or "" for c in seen["choices"]
                 if not isinstance(c, str)]
        assert any("2024-Q2" in t and "filed here now" in t for t in shown)


class TestTheHeldScreenSaysWhy:

    def test_the_reason_is_shown_above_place_and_reject(self, monkeypatch, capsys):
        from cli import filing_tui
        from qa_tools.common import filing_queue as fq

        monkeypatch.setattr(filing_tui.common, "select", lambda *a, **k: None)
        filing_tui.held_flow(fq.HeldRow(
            dataset_id=DS, dataset_name="Carer Register", supply="cp-carers@h1",
            received_at=None, received_text="x",
            why="cp-carers@h1 could not be placed - 2024-Q1: closed.",
            schedule_ended=False))
        assert "2024-Q1: closed" in capsys.readouterr().out

    def test_an_unlisted_person_is_told_on_entering_filing_decisions(self, monkeypatch, capsys):
        from cli import filing_tui
        from qa_tools.common import people

        def nobody():
            raise people.UnknownActor("'x@y' is not in contract/people.yaml")

        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard", nobody)
        asked = []
        monkeypatch.setattr(filing_tui.common, "select",
                            lambda *a, **k: asked.append(a) or None)
        filing_tui.filing_menu()
        assert "people.yaml" in capsys.readouterr().out and not asked
