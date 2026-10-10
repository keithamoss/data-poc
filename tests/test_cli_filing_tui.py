"""The terminal's route onto a filing decision (REQ-GHUB-082 criteria 2,
12, 16-19, 22, 26, 28, 30 and 31).

AN ADAPTER IS TESTED FOR WHAT ONLY IT CAN GET WRONG. What a decision
MEANS is `filing_decisions`' and is covered there; what is here is the
two things that are genuinely a terminal's - who is at the keyboard and
what they asked for - plus the three properties the criteria put on this
surface specifically: it confirms before it writes, it never shows a
cached answer, and it calls no GitHub.
"""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from cli import filing_tui
from cli.supply import supply_group
from qa_tools.common import (decision_log as dl, filing_decisions as fd,
                              filing_queue, people, slot_state, supply_db)

REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def actor():
    return people.person_by_email(REAL_PERSON)


def _state(state=slot_state.AWAITING_DECISION, **kw):
    kw.setdefault("dataset_id", "cp-carers")
    kw.setdefault("period", "2026-Q1")
    return slot_state.SlotState(state=state, **kw)


class TestEveryOneOfTheEightIsOfferedHere:
    """Criterion 2, and criterion 3's second half read from this end: the
    TUI may not be missing an operation the GitHub route has."""

    def test_the_menu_has_a_sentence_for_all_eight(self):
        assert set(filing_tui._WHAT_IT_DOES) == set(fd.OPERATIONS)

    def test_the_flag_form_accepts_all_eight(self):
        choice = next(p for p in supply_group.commands["decide"].params
                       if p.name == "operation")
        assert set(choice.type.choices) == set(fd.OPERATIONS)

    def test_every_slot_state_has_a_human_reading(self):
        """A state with no sentence renders as its own identifier, which
        is how `never-supplied` reaches somebody as `never-supplied`."""
        for name in dir(slot_state):
            value = getattr(slot_state, name)
            if name.isupper() and isinstance(value, str) and "-" in value:
                assert value in filing_tui._HOW_IT_READS, value


class TestItConfirmsBeforeItWrites:
    """Criterion 28: an explicit confirmation before applying anything,
    not only for the destructive three."""

    def test_declining_the_confirmation_appends_nothing(self, monkeypatch, actor):
        applied = []
        monkeypatch.setattr(fd, "apply", lambda *a, **k: applied.append(1))
        monkeypatch.setattr(filing_tui.common, "confirm", lambda *a, **k: False)
        out = filing_tui.apply_decision(
            operation=fd.PROMOTE, dataset_id="cp-carers", period="2026-Q1",
            reason="looked fine", actor=actor)
        assert out is None
        assert applied == []

    def test_it_asks_even_for_a_promote(self, monkeypatch, actor):
        asked = []
        monkeypatch.setattr(filing_tui.common, "confirm",
                             lambda msg, **k: asked.append(msg) or False)
        filing_tui.apply_decision(operation=fd.PROMOTE, dataset_id="cp-carers",
                                   period="2026-Q1", reason="x", actor=actor)
        assert asked and "promote" in asked[0]

    def test_the_confirmation_names_who_it_will_be_recorded_as(self, monkeypatch,
                                                                actor):
        asked = []
        monkeypatch.setattr(filing_tui.common, "confirm",
                             lambda msg, **k: asked.append(msg) or False)
        filing_tui.apply_decision(operation=fd.REJECT, dataset_id="cp-carers",
                                   period="2026-Q1", reason="x", actor=actor)
        assert REAL_PERSON in asked[0]

    def test_confirming_marks_the_request_confirmed(self, monkeypatch, actor):
        """`--yes` and `confirmed` are different things and both are set
        by the same act: the operation itself refuses a re-file that
        arrives unconfirmed, whichever route forgot to ask."""
        seen = {}

        def capture(request, **kw):
            seen["request"] = request
            return fd.Outcome(operation=request.operation,
                               dataset_id=request.dataset_id,
                               period=request.period, changed=True, message="done")

        monkeypatch.setattr(filing_tui.common, "confirm", lambda *a, **k: True)
        monkeypatch.setattr(fd, "apply", capture)
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
        filing_tui.apply_decision(operation=fd.REFILE, dataset_id="cp-carers",
                                   period="2026-Q1", to_period="2026-Q2",
                                   reason="x", actor=actor)
        assert seen["request"].confirmed is True


class TestARefusalIsToldToThePersonWhoRaisedIt:
    """Criterion 22 on this route, and criterion 25's remedy carried
    through rather than restated."""

    def test_a_missing_reason_stops_it_before_anything_is_applied(self, monkeypatch,
                                                                   actor):
        applied = []
        monkeypatch.setattr(fd, "apply", lambda *a, **k: applied.append(1))
        monkeypatch.setattr(filing_tui.common, "text_prompt", lambda *a, **k: None)
        out = filing_tui.apply_decision(operation=fd.PROMOTE,
                                         dataset_id="cp-carers", period="2026-Q1",
                                         actor=actor)
        assert out is None and applied == []

    def test_an_unknown_actor_is_refused_and_says_so(self, monkeypatch, capsys):
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                             lambda: (_ for _ in ()).throw(
                                 people.UnknownActor("nobody@example.com is not in "
                                                      "contract/people.yaml")))
        out = filing_tui.apply_decision(operation=fd.PROMOTE,
                                         dataset_id="cp-carers", period="2026-Q1",
                                         reason="x")
        assert out is None
        assert "people.yaml" in capsys.readouterr().out

    def test_the_logs_own_refusal_reaches_the_screen_unchanged(self, monkeypatch,
                                                                actor, capsys):
        """Criterion 25 says the refusal names the remedy. It is composed
        once, by the log, and repeating it here is how two copies drift."""
        monkeypatch.setattr(filing_tui.common, "confirm", lambda *a, **k: True)
        monkeypatch.setattr(fd, "apply", lambda *a, **k: (_ for _ in ()).throw(
            dl.DecisionRefused("2026-Q2 stands on it - de-substitute 2026-Q2 first")))
        out = filing_tui.apply_decision(operation=fd.DEMOTE,
                                         dataset_id="cp-carers", period="2026-Q1",
                                         reason="x", actor=actor)
        assert out is None
        assert "de-substitute 2026-Q2 first" in capsys.readouterr().out.replace("\n", "")

    def test_an_operation_nobody_offers_is_refused_rather_than_crashing(
            self, monkeypatch, actor, capsys):
        monkeypatch.setattr(filing_tui.common, "confirm", lambda *a, **k: True)
        monkeypatch.setattr(fd, "apply", lambda *a, **k: (_ for _ in ()).throw(
            fd.NotOffered("re-file's effect is not built yet")))
        assert filing_tui.apply_decision(
            operation=fd.REFILE, dataset_id="cp-carers", period="2026-Q1",
            reason="x", actor=actor) is None
        assert "not built yet" in capsys.readouterr().out


class TestANoOpIsNotARefusal:
    """Criterion 26 - two people working the same slot arrive here
    constantly, and reporting it as a failure teaches them to ignore
    failures."""

    @pytest.fixture
    def already(self, monkeypatch):
        monkeypatch.setattr(filing_tui.common, "confirm", lambda *a, **k: True)
        monkeypatch.setattr(fd, "apply", lambda request, **k: fd.Outcome(
            operation=request.operation, dataset_id=request.dataset_id,
            period=request.period, changed=False,
            message="already promoted. Nothing to do."))

    def test_it_comes_back_as_an_outcome_not_as_None(self, already, actor):
        out = filing_tui.apply_decision(operation=fd.PROMOTE,
                                         dataset_id="cp-carers", period="2026-Q1",
                                         reason="x", actor=actor)
        assert out is not None and out.changed is False

    def test_it_does_not_reconcile_a_ticket_that_has_nothing_new_to_say(
            self, already, actor, monkeypatch):
        passes = []
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: passes.append(1))
        filing_tui.apply_decision(operation=fd.PROMOTE, dataset_id="cp-carers",
                                   period="2026-Q1", reason="x", actor=actor)
        assert passes == []

    def test_the_command_exits_zero_on_it(self, already, monkeypatch, supply_dsn):
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                             lambda: people.person_by_email(REAL_PERSON))
        result = CliRunner().invoke(supply_group, [
            "decide", "--operation", "promote", "--dataset", "cp-carers",
            "--period", "2026-Q1", "--supply", "cp-carers@1",
            "--reason", "x", "--yes"])
        assert result.exit_code == 0, result.output

    def test_the_command_exits_nonzero_on_a_real_refusal(self, monkeypatch,
                                                          supply_dsn):
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                             lambda: people.person_by_email(REAL_PERSON))
        monkeypatch.setattr(fd, "apply", lambda *a, **k: (_ for _ in ()).throw(
            dl.DecisionRefused("not permitted")))
        result = CliRunner().invoke(supply_group, [
            "decide", "--operation", "promote", "--dataset", "cp-carers",
            "--period", "2026-Q1", "--supply", "cp-carers@1",
            "--reason", "x", "--yes"])
        assert result.exit_code == 1, result.output


class TestItNeverShowsACachedAnswer:
    """Criterion 19: where the log is unreachable it says so, and shows
    no filing state at all."""

    def test_an_unreachable_database_raises_rather_than_falling_back(self,
                                                                      monkeypatch):
        monkeypatch.setattr(supply_db, "connect", lambda *a, **k: (
            _ for _ in ()).throw(supply_db.SupplyDbError("cannot reach it")))
        with pytest.raises(filing_queue.LogUnreachable):
            filing_tui.open_log()

    def test_the_standing_view_says_so_and_prints_no_periods(self, monkeypatch,
                                                              capsys):
        monkeypatch.setattr(filing_tui, "open_log", lambda: (_ for _ in ()).throw(
            filing_queue.LogUnreachable("cannot reach the supply database")))
        filing_tui.standing_view("child-protection")
        out = capsys.readouterr().out
        assert "cannot be read" in out.replace("\n", " ")
        assert "promoted" not in out

    def test_the_queue_says_so_and_offers_nothing(self, monkeypatch, capsys):
        monkeypatch.setattr(filing_tui, "open_log", lambda: (_ for _ in ()).throw(
            filing_queue.LogUnreachable("cannot reach the supply database")))
        monkeypatch.setattr(filing_tui.common, "select", lambda *a, **k: (
            _ for _ in ()).throw(AssertionError("nothing may be offered")))
        filing_tui.queue_flow("child-protection")
        assert "Decision log not available" in capsys.readouterr().out

    def test_the_command_fails_rather_than_printing_an_empty_queue(self,
                                                                    monkeypatch):
        monkeypatch.setattr(filing_tui, "open_log", lambda: (_ for _ in ()).throw(
            filing_queue.LogUnreachable("cannot reach the supply database")))
        result = CliRunner().invoke(supply_group,
                                     ["queue", "--collection", "child-protection"])
        assert result.exit_code == 1


class TestItCallsNoGitHub:
    """Criterion 30: the terminal route writes the decision log alone, so
    it needs no GitHub reachability - which on a government network may
    be the difference between a usable tool and none."""

    def test_nothing_in_this_module_imports_a_github_client(self):
        """READ OFF THE IMPORTS rather than the whole file: this module's
        prose talks about GitHub at length, and a substring check over
        the source would fail on its own explanation of why it does not
        call it."""
        import ast

        tree = ast.parse(open(filing_tui.__file__).read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported |= {f"{node.module}.{a.name}" for a in node.names}
        for name in sorted(imported):
            assert "github" not in name.lower(), name
            assert "ticket" not in name.lower(), name
            assert "subprocess" not in name.lower(), name

    def test_the_ticket_is_brought_up_to_date_by_the_shared_pass(self, monkeypatch,
                                                                  actor):
        """Criterion 8: through REQ-PIPE-083's own pass, never an update
        this route composes."""
        passes = []
        monkeypatch.setattr(filing_tui.common, "confirm", lambda *a, **k: True)
        monkeypatch.setattr(fd, "apply", lambda request, **k: fd.Outcome(
            operation=request.operation, dataset_id=request.dataset_id,
            period=request.period, changed=True, message="done"))
        monkeypatch.setattr(fd, "reconcile_after",
                             lambda outcome, collection: passes.append(collection))
        filing_tui.apply_decision(operation=fd.PROMOTE, dataset_id="cp-carers",
                                   period="2026-Q1", reason="x", actor=actor)
        assert passes == ["child-protection"]


class TestTheOfferAfterARunIsQuietWhenItShouldBe:
    """Criterion 17, and the part of it that is a judgement rather than a
    clause: a person reading their QA results must not be interrupted by
    an error about a queue they did not ask for."""

    def test_it_says_nothing_where_the_log_cannot_be_read(self, monkeypatch, capsys):
        monkeypatch.setattr(filing_tui.sys.stdin, "isatty", lambda: True,
                             raising=False)
        monkeypatch.setattr(filing_tui, "open_log", lambda: (_ for _ in ()).throw(
            filing_queue.LogUnreachable("down")))
        filing_tui.offer_after_run("child-protection", "cp_run_001")
        assert capsys.readouterr().out == ""

    def test_it_says_nothing_with_no_terminal(self, monkeypatch, capsys):
        monkeypatch.setattr(filing_tui, "open_log", lambda: (_ for _ in ()).throw(
            AssertionError("the log must not even be opened")))
        filing_tui.offer_after_run("child-protection", "cp_run_001")
        assert capsys.readouterr().out == ""


class TestHowASlotReads:

    def test_the_arrival_is_shown_as_a_date_rather_than_a_key(self):
        assert filing_tui.arrived("cp-carers@202605010100000000") == "2026-05-01 01:00"

    def test_a_supply_with_no_usable_key_still_renders(self):
        assert filing_tui.arrived("") == "-"
        assert filing_tui.arrived("cp-carers@abc") == "abc"

    def test_a_long_reason_is_cut_rather_than_wrapped(self):
        cut = filing_tui._short("x" * 200)
        assert len(cut) == 48 and cut.endswith("…")

    def test_nobody_decided_reads_as_nobody_rather_than_as_a_rule(self):
        assert "-" in filing_tui._who_decided(_state(slot_state.AWAITING_DECISION))
        assert "rule" not in filing_tui._who_decided(_state(slot_state.AWAITING_DECISION))

    def test_an_automatic_decision_reads_as_a_rule(self):
        assert "rule" in filing_tui._who_decided(_state(slot_state.PROMOTED))

    def test_a_person_is_named(self):
        assert filing_tui._who_decided(
            _state(slot_state.PROMOTED, decided_by="a@b.com")) == "a@b.com"


class TestTheCommandReallyWritesTheLog:
    """The one thing neither the shared implementation's tests nor the
    adapter's own can show on their own: `mothman supply decide` reaching
    a real PostgreSQL and leaving an entry behind.

    AGAINST THE WORKER'S OWN DATABASE, never the real `supply` one - a
    filing decision is append-only by a database trigger, so a test that
    wrote to the live log could not take it back.
    """

    @pytest.fixture
    def conn(self, supply_dsn):
        from qa_tools.common import qa_store

        with supply_db.connect(label="test-cli-filing") as c:
            qa_store.ensure_schema(c)
            yield c

    @pytest.fixture
    def period(self, monkeypatch):
        """A period of this test's own, so it cannot collide with another
        test's decisions in an append-only log."""
        import uuid
        from datetime import date

        from qa_tools.common import inheritance, schedule

        name = f"2099-C{uuid.uuid4().hex[:6]}"
        for mod in (schedule, inheritance.schedule):
            monkeypatch.setattr(mod, "date_of",
                                 lambda n, ds, _n=name: date(2099, 1, 1) if n == _n
                                 else None)
        return name

    def _stage(self, conn, dataset):
        import uuid

        arrival = uuid.uuid4().hex[:10]
        physical = f"{dataset.table}__{arrival}"
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
        conn.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
        return f"{dataset.dataset_id}@{arrival}"

    def test_a_promote_from_the_terminal_lands_in_the_decision_log(
            self, conn, period, monkeypatch):
        from qa_tools.common import hierarchy

        dataset = hierarchy.dataset("cp-carers")
        supply = self._stage(conn, dataset)
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                             lambda: people.person_by_email(REAL_PERSON))
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)

        result = CliRunner().invoke(supply_group, [
            "decide", "--operation", "promote", "--dataset", "cp-carers",
            "--period", period, "--supply", supply,
            "--reason", "the checks passed and I read them", "--yes"])

        assert result.exit_code == 0, result.output
        # THE ENTRY FOR THIS SUPPLY, NEVER THE LAST ONE. A promotion
        # also tries to carry the supply into the periods after it, and
        # records an `inherit-refused` for each one it cannot - so the
        # newest entry for this dataset is routinely not the decision
        # that was just taken. In isolation there were no later periods
        # to try and `[-1]` happened to be right, which is exactly the
        # shape of assertion that passes alone and fails in a full run.
        entries = [e for e in dl.decisions_for(conn, "cp-carers")
                   if e["supply"] == supply and e["action"] == dl.PROMOTE]
        assert len(entries) == 1, "exactly one promote for this supply"
        entry = entries[0]
        assert entry["to_slot"] == period
        assert entry["supply"] == supply
        assert entry["actor"] == REAL_PERSON
        assert entry["actor_kind"] == dl.PERSON, (
            "criterion 27: the person, never the terminal that carried it")
        assert entry["reason"] == "the checks passed and I read them"

    def test_running_it_twice_is_a_no_op_rather_than_a_second_entry(
            self, conn, period, monkeypatch):
        """Criterion 26, end to end. Two people working the same slot is
        the ordinary case, not an error state."""
        from qa_tools.common import hierarchy

        dataset = hierarchy.dataset("cp-carers")
        supply = self._stage(conn, dataset)
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                             lambda: people.person_by_email(REAL_PERSON))
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
        argv = ["decide", "--operation", "promote", "--dataset", "cp-carers",
                "--period", period, "--supply", supply, "--reason", "once",
                "--yes"]

        assert CliRunner().invoke(supply_group, argv).exit_code == 0
        before = len(dl.decisions_for(conn, "cp-carers"))
        again = CliRunner().invoke(supply_group, argv)

        assert again.exit_code == 0, again.output
        assert "Nothing to do" in again.output.replace("\n", " ")
        assert len(dl.decisions_for(conn, "cp-carers")) == before

    def test_the_standing_view_then_shows_the_person_who_decided(
            self, conn, period, monkeypatch, capsys):
        """Criterion 18 and criterion 34 together: the filing state the
        decision resolves to, with a person's name on it rather than a
        rule's."""
        from qa_tools.common import hierarchy

        dataset = hierarchy.dataset("cp-carers")
        supply = self._stage(conn, dataset)
        monkeypatch.setattr(filing_tui, "actor_at_the_keyboard",
                             lambda: people.person_by_email(REAL_PERSON))
        monkeypatch.setattr(fd, "reconcile_after", lambda *a, **k: None)
        CliRunner().invoke(supply_group, [
            "decide", "--operation", "promote", "--dataset", "cp-carers",
            "--period", period, "--supply", supply, "--reason", "read them",
            "--yes"])
        capsys.readouterr()

        monkeypatch.setattr(slot_state, "states_for", lambda c, cid, now=None: [
            _state(slot_state.PROMOTED, period=period, supply=supply,
                    decided_by=REAL_PERSON)])
        filing_tui.standing_view("child-protection", "cp-carers")

        out = capsys.readouterr().out
        assert period in out
        assert "promoted" in out
        # REQ-PIPE-122 NFR 1 (built 2026-10-05): the setting that decides
        # what an amber supply does, and where it was set.
        assert "Amber setting:" in out and "set for the whole data asset" in out


class TestEveryOperationIsReachableFromSomeDoor:
    """Criterion 2 read as a question about NAVIGATION rather than about
    a list of strings: an operation the menus never route to is not
    offered, whatever the choices in the flag form say.

    FOUND BY RE-READING THE CRITERIA rather than by a failure. Criterion
    16 puts promote, reject, demote and re-file in the standing queue -
    but the queue holds only slots AWAITING a decision, and a slot has
    to be PROMOTED before demoting it means anything. So demote was
    reachable from no wizard door at all, and only the flag form could
    reach it.
    """

    def _offered_by(self, flow, state, monkeypatch, excuse_offers=()):
        """What this door would put in front of somebody, for this slot.
        `excuse_offers` stands in for the recorded punctuality the excuse
        offer reads (REQ-PIPE-161 criterion 10), which needs a database."""
        seen = {}
        monkeypatch.setattr(filing_tui, "open_log",
                             lambda: __import__("contextlib").nullcontext(None))
        monkeypatch.setattr(filing_queue, "excuse_offers", lambda conn, s: excuse_offers)
        monkeypatch.setattr(filing_queue, "awaiting", lambda *a, **k: [state])
        monkeypatch.setattr(filing_queue, "slots_of", lambda *a, **k: [state])
        monkeypatch.setattr(filing_queue, "closed_gaps", lambda *a, **k: [])
        monkeypatch.setattr(filing_tui, "_pick_slot", lambda states, msg: state)
        monkeypatch.setattr(filing_tui, "_decide_on",
                             lambda s, offer: seen.setdefault("offer", offer))
        monkeypatch.setattr(filing_tui.common, "select",
                             lambda msg, choices, **k: choices[0])
        flow("child-protection")
        return set(seen.get("offer", ()))

    def test_demote_is_reachable_from_the_period_door(self, monkeypatch):
        offered = self._offered_by(filing_tui.period_flow,
                                    _state(slot_state.PROMOTED, supply="cp-carers@1"),
                                    monkeypatch)
        assert fd.DEMOTE in offered

    def test_the_period_door_still_offers_the_period_scoped_ones(self, monkeypatch):
        offered = self._offered_by(filing_tui.period_flow,
                                    _state(slot_state.OVERDUE), monkeypatch)
        assert {fd.SUBSTITUTE, fd.INHERIT} <= offered

    def test_the_queue_still_offers_no_period_scoped_one(self, monkeypatch):
        """Criterion 31 unchanged by the fix above: somebody working an
        arriving supply is never offered inherit."""
        offered = self._offered_by(filing_tui.queue_flow,
                                    _state(slot_state.AWAITING_DECISION,
                                            supply="cp-carers@1"), monkeypatch)
        assert not offered & set(fd.PERIOD_SCOPED)
        assert fd.PROMOTE in offered

    def test_between_the_two_doors_all_of_them_are_reachable(self, monkeypatch):
        """Eight, mark as not supplied on a CLOSED period (REQ-PIPE-132),
        acknowledge on a promotion owing one (REQ-PIPE-122), and excuse
        lateness and its withdrawal on a late supply (REQ-PIPE-161)."""
        reachable = set()
        for flow, states in (
                (filing_tui.queue_flow, [(slot_state.AWAITING_DECISION, False),
                                          (slot_state.AWAITING_ACKNOWLEDGEMENT, False),
                                          (slot_state.REJECTED, False)]),
                (filing_tui.period_flow, [(slot_state.PROMOTED, False),
                                           (slot_state.OVERDUE, False),
                                           (slot_state.OVERDUE, True),
                                           (slot_state.SUBSTITUTED, False),
                                           (slot_state.INHERITED, False)])):
            for name, closed in states:
                reachable |= self._offered_by(
                    flow, _state(name, supply="cp-carers@1", closed=closed), monkeypatch)
        for offers in ((fd.EXCUSE_LATENESS,), (fd.WITHDRAW_EXCUSE,)):
            reachable |= self._offered_by(
                filing_tui.queue_flow,
                _state(slot_state.AWAITING_DECISION, supply="cp-carers@1"), monkeypatch,
                excuse_offers=offers)
        assert reachable == set(fd.OPERATIONS)


class TestProductionTypesItsIdIntoTheRealFlows:
    """post-build-review #119 D3: REQ-PIPE-093 criteria 4, 6 and 7 tested on
    the FLOWS, not only on confirm_change - a mutation that swapped the
    flow's confirmation back to a plain yes/no passed every test before."""

    def test_a_decision_in_production_needs_the_typed_id_even_with_yes(
            self, monkeypatch, actor):
        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "production")
        monkeypatch.setattr(filing_tui.common, "require_tty", lambda hint: None)
        typed = []
        monkeypatch.setattr(filing_tui.common, "_ask_text",
                            lambda m: typed.append(m) or "Production")
        applied = []
        monkeypatch.setattr(fd, "apply", lambda *a, **k: applied.append(1))
        out = filing_tui.apply_decision(operation=fd.PROMOTE, dataset_id="cp-carers",
                                        period="2026-Q1", reason="x", actor=actor, yes=True)
        assert typed, "the typed id was never asked for"
        assert out is None and applied == [], "a mistyped id must record nothing"

    def test_hand_filing_in_production_needs_the_typed_id(self, monkeypatch):
        import click

        from cli import common

        monkeypatch.setenv("MOTHMAN_ENVIRONMENT", "production")
        monkeypatch.setattr(common, "decide_keep", lambda paths, keep: common.Keep(True))
        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        typed = []
        monkeypatch.setattr(common, "_ask_text", lambda m: typed.append(m) or "nope")
        with pytest.raises(click.ClickException, match="not filed"):
            common._file_or_trial(["x.csv"], "child-protection", "cp_run_", keep=True,
                                  route="terminal", originally=None, storage_times=None)
        assert typed
