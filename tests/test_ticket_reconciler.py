"""One ticket per slot, reconciled to its current state (REQ-PIPE-083).

A team shares one queue, and the queue only works if everything in it
wants somebody and nothing in it says the same thing twice. Both halves
are easy to get wrong in opposite directions, so both are pinned here:
a stream of events fills the queue with things already dealt with, and a
queue nobody updates fills it with things already done.

THE FAKE SERVICE IS THE POINT of this file rather than a shortcut. The
reconciler's contract is five methods, and driving it against a real
GitHub would test the network far more than the logic - while making
every one of these tests a litter of real issues in a public
repository.
"""
from __future__ import annotations

import pytest

from qa_tools.common import slot_state, ticket_reconciler as tr


class FakeTickets:
    """A ticketing service that remembers, and can be made to fail."""

    def __init__(self, *, raises_on=None):
        self.tickets: dict[str, tr.Ticket] = {}
        self.threads: dict[str, list[str]] = {}
        self.raises_on = raises_on or set()
        self.opened: list[str] = []

    def _check(self, key):
        if key in self.raises_on:
            raise RuntimeError("the ticketing service is unreachable")

    def find(self, key):
        self._check(key)
        return self.tickets.get(key)

    def open(self, key, title, body):
        self._check(key)
        ticket = tr.Ticket(key=key, number=len(self.tickets) + 1)
        self.tickets[key] = ticket
        self.threads[key] = [body]
        self.opened.append(title)
        return ticket

    def comment(self, ticket, body):
        self._check(ticket.key)
        self.threads[ticket.key].append(body)

    def reopen(self, ticket):
        self._check(ticket.key)
        ticket.closed = False

    def comments(self, ticket):
        self._check(ticket.key)
        return list(self.threads.get(ticket.key, ()))


def a_slot(state=slot_state.OVERDUE, dataset="cp-carers", period="2026-Q3",
            **over):
    return slot_state.SlotState(dataset_id=dataset, period=period, state=state,
                                 **over)


class TestOneTicketPerSlot:
    """Criteria 1, 2 and 3."""

    def test_a_first_pass_opens_one(self):
        svc = FakeTickets()
        out = tr.reconcile(svc, [a_slot()], policy=tr.ALL)
        assert out.opened == ("cp-carers/2026-Q3",)
        assert len(svc.tickets) == 1

    def test_a_second_pass_opens_none(self):
        svc = FakeTickets()
        slot = a_slot()
        tr.reconcile(svc, [slot], policy=tr.ALL)
        out = tr.reconcile(svc, [slot], policy=tr.ALL)
        assert out.opened == ()
        assert len(svc.tickets) == 1

    def test_the_key_is_the_dataset_and_the_period(self):
        svc = FakeTickets()
        tr.reconcile(svc, [a_slot()], policy=tr.ALL)
        assert "cp-carers/2026-Q3" in svc.tickets


class TestRunningItTwiceOverAnUnchangedWorldChangesNothing:
    """Criteria 4 and 5, which are one claim seen from two sides."""

    def test_the_second_pass_posts_nothing(self):
        svc = FakeTickets()
        slot = a_slot()
        tr.reconcile(svc, [slot], policy=tr.ALL)
        before = len(svc.threads["cp-carers/2026-Q3"])
        out = tr.reconcile(svc, [slot], policy=tr.ALL)
        assert out.unchanged == ("cp-carers/2026-Q3",)
        assert len(svc.threads["cp-carers/2026-Q3"]) == before

    def test_a_pass_that_changed_nothing_says_so(self):
        svc = FakeTickets()
        slot = a_slot()
        tr.reconcile(svc, [slot], policy=tr.ALL)
        assert tr.reconcile(svc, [slot], policy=tr.ALL).quiet is True

    def test_a_changed_state_DOES_post(self):
        svc = FakeTickets()
        tr.reconcile(svc, [a_slot(slot_state.OVERDUE)], policy=tr.ALL)
        out = tr.reconcile(svc, [a_slot(slot_state.AWAITING_DECISION,
                                         supply="cp-carers@1")], policy=tr.ALL)
        assert out.updated == ("cp-carers/2026-Q3",)
        assert len(svc.threads["cp-carers/2026-Q3"]) == 2

    def test_two_states_that_read_identically_are_the_same_state(self):
        """Posting for a difference nobody can see is the repetition
        criterion 5 forbids."""
        one = a_slot(slot_state.OVERDUE)
        two = a_slot(slot_state.OVERDUE)
        assert tr.fingerprint(one) == tr.fingerprint(two)


class TestItSpeaksOnlyToItsOwnComments:
    """Criterion 11, and the failure it stops: a reconciler that answers
    people."""

    def test_a_persons_comment_is_not_a_reason_to_post(self):
        svc = FakeTickets()
        slot = a_slot()
        tr.reconcile(svc, [slot], policy=tr.ALL)
        svc.threads["cp-carers/2026-Q3"].append("I'm on it - Keith")
        out = tr.reconcile(svc, [slot], policy=tr.ALL)
        assert out.updated == ()
        assert out.unchanged == ("cp-carers/2026-Q3",)

    def test_what_it_last_said_is_read_past_a_persons_comment(self):
        svc = FakeTickets()
        tr.reconcile(svc, [a_slot(slot_state.OVERDUE)], policy=tr.ALL)
        svc.threads["cp-carers/2026-Q3"].append("chasing them now")
        out = tr.reconcile(svc, [a_slot(slot_state.AWAITING_DECISION)],
                            policy=tr.ALL)
        assert out.updated == ("cp-carers/2026-Q3",)

    def test_its_own_comments_carry_an_invisible_marker(self):
        """A prefix a person could type by accident is not a marker."""
        svc = FakeTickets()
        tr.reconcile(svc, [a_slot()], policy=tr.ALL)
        assert svc.threads["cp-carers/2026-Q3"][0].startswith("<!--")


class TestAClosedTicketIsReopenedRatherThanReplaced:
    """Criterion 12, and it is criterion 2 seen from the other side: a
    second ticket for one slot is exactly what must never happen."""

    def test_it_reopens_the_same_ticket(self):
        svc = FakeTickets()
        tr.reconcile(svc, [a_slot(slot_state.OVERDUE)], policy=tr.ALL)
        svc.tickets["cp-carers/2026-Q3"].closed = True
        out = tr.reconcile(svc, [a_slot(slot_state.REJECTED)], policy=tr.ALL)
        assert out.reopened == ("cp-carers/2026-Q3",)
        assert len(svc.tickets) == 1
        assert svc.tickets["cp-carers/2026-Q3"].closed is False

    def test_a_closed_ticket_whose_slot_has_not_moved_is_left_closed(self):
        svc = FakeTickets()
        slot = a_slot()
        tr.reconcile(svc, [slot], policy=tr.ALL)
        svc.tickets["cp-carers/2026-Q3"].closed = True
        out = tr.reconcile(svc, [slot], policy=tr.ALL)
        assert out.reopened == ()
        assert svc.tickets["cp-carers/2026-Q3"].closed is True


class TestItNeverCloses:
    """Criterion 10. Closing is a person saying "I am done with this",
    and a rule saying it for them is how somebody's work disappears."""

    def test_the_service_is_never_asked_to_close(self):
        import inspect
        assert "def close" not in inspect.getsource(tr), \
            "the reconciler has no way to close a ticket, and that is the design"

    def test_a_finished_slot_gets_its_outcome_recorded(self):
        body = tr.body_for(a_slot(slot_state.PROMOTED, supply="cp-carers@1"))
        assert "Nothing is waiting on a person" in body
        assert "Left open" in body


class TestThePolicyDecidesWhichSlotsGetATicket:
    """Criterion 21, and the default is not timidity - at ~30 datasets
    `all` is a ticket per dataset per period whether or not anything
    needed a person, which is how a queue becomes noise."""

    def test_needs_action_is_the_default(self):
        assert tr.DEFAULT_POLICY == tr.NEEDS_ACTION
        assert tr.policy_from_config({}) == tr.NEEDS_ACTION

    def test_needs_action_skips_a_slot_nobody_has_to_look_at(self):
        svc = FakeTickets()
        out = tr.reconcile(svc, [a_slot(slot_state.PROMOTED)],
                            policy=tr.NEEDS_ACTION)
        assert out.opened == ()
        assert svc.tickets == {}

    def test_needs_action_opens_one_for_a_slot_that_does(self):
        svc = FakeTickets()
        out = tr.reconcile(svc, [a_slot(slot_state.HELD)], policy=tr.NEEDS_ACTION)
        assert out.opened == ("cp-carers/2026-Q3",)

    def test_all_opens_one_for_everything(self):
        svc = FakeTickets()
        out = tr.reconcile(svc, [a_slot(slot_state.PROMOTED)], policy=tr.ALL)
        assert out.opened == ("cp-carers/2026-Q3",)

    def test_an_unknown_policy_falls_back_and_says_so(self, capsys):
        assert tr.policy_from_config({"ticket_policy": "whatever"}) == tr.NEEDS_ACTION
        assert "whatever" in capsys.readouterr().out

    def test_the_real_asset_config_declares_one(self):
        assert tr.policy_from_config() in tr.POLICIES


class TestOneSlotsFailureIsScopedToIt:
    """Criterion 20. At ~30 datasets a pass that abandons twenty-nine
    tickets because the thirtieth raised is a pass somebody turns off."""

    def test_the_others_are_still_reconciled(self):
        svc = FakeTickets(raises_on={"cp-clients/2026-Q3"})
        out = tr.reconcile(svc, [
            a_slot(dataset="cp-carers"), a_slot(dataset="cp-clients"),
            a_slot(dataset="cp-placements")], policy=tr.ALL)
        assert sorted(out.opened) == ["cp-carers/2026-Q3", "cp-placements/2026-Q3"]
        assert list(out.failed) == ["cp-clients/2026-Q3"]

    def test_an_unreachable_service_raises_nothing_at_the_caller(self):
        """Criterion 17: the change stands on its durable record, and
        the next pass brings the ticket up to date."""
        svc = FakeTickets(raises_on={"cp-carers/2026-Q3"})
        out = tr.reconcile(svc, [a_slot()], policy=tr.ALL)
        assert out.failed and out.opened == ()


class TestANarrowedPassIsTheSamePass:
    """Criterion 18: fewer slots, never a second code path."""

    def test_reconciling_one_slot_leaves_the_others_alone(self):
        svc = FakeTickets()
        both = [a_slot(dataset="cp-carers"), a_slot(dataset="cp-clients")]
        tr.reconcile(svc, both, policy=tr.ALL)
        out = tr.reconcile(svc, [both[0]], policy=tr.ALL)
        assert out.unchanged == ("cp-carers/2026-Q3",)
        assert len(svc.tickets) == 2

    def test_there_is_no_second_entry_point(self):
        import inspect
        public = [n for n, v in vars(tr).items()
                   if inspect.isfunction(v) and not n.startswith("_")]
        assert "reconcile" in public
        assert not [n for n in public if n.startswith("reconcile_")], public


class TestWhatTheTicketSays:
    """Criteria 6 and 9."""

    @pytest.mark.parametrize("state", [
        slot_state.OVERDUE, slot_state.NEVER_SUPPLIED,
        slot_state.AWAITING_DECISION, slot_state.RETURNED, slot_state.HELD,
        slot_state.REJECTED, slot_state.PROMOTED, slot_state.SUBSTITUTED,
        slot_state.INHERITED, slot_state.NOT_YET_DUE])
    def test_every_state_renders(self, state):
        body = tr.body_for(a_slot(state))
        assert state in body

    def test_it_names_the_responses_rather_than_offering_them(self):
        body = tr.body_for(a_slot(slot_state.HELD))
        assert "What somebody can do:" in body
        assert "which file is the supply" in body

    def test_a_daily_period_is_written_in_words(self):
        body = tr.body_for(a_slot(period="2026-08-27"))
        assert "2026-08-27" not in body
        assert "August" in body

    def test_it_shows_a_reason_as_written(self):
        body = tr.body_for(a_slot(slot_state.SUBSTITUTED,
                                   reason="the supplier confirmed none is coming"))
        assert "the supplier confirmed none is coming" in body


class TestTheReconcilerIsInvokedAfterEveryRun:
    """Criteria 13 and 16, asserted on the AST rather than the source
    text - a comment mentioning the reconciler is not a call to it, and
    this project has been caught by exactly that before
    (tests/test_filing_before_checks.py's own header)."""

    @staticmethod
    def _calls(module_name, func_name):
        import ast
        import inspect

        module = __import__(module_name, fromlist=[func_name])
        source = inspect.getsource(getattr(module, func_name))
        tree = ast.parse(source.lstrip() if source.startswith(" ") else source)
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            parts, target = [], node.func
            while isinstance(target, ast.Attribute):
                parts.append(target.attr)
                target = target.value
            if isinstance(target, ast.Name):
                parts.append(target.id)
            out.append((".".join(reversed(parts)), node.lineno))
        return out

    @pytest.mark.parametrize("module,func", [
        ("qa_tools.cp.orchestrate_cp", "run_pipeline_cp"),
        ("qa_tools.bdm.orchestrate_bdm", "run_pipeline"),
    ])
    def test_it_is_called(self, module, func):
        names = [n for n, _ in self._calls(module, func)]
        assert "ticket_reconciler.after_runs" in names, names

    @pytest.mark.parametrize("module,func", [
        ("qa_tools.cp.orchestrate_cp", "run_pipeline_cp"),
        ("qa_tools.bdm.orchestrate_bdm", "run_pipeline"),
    ])
    def test_it_is_called_AFTER_the_runs(self, module, func):
        """Criterion 16: only after the change is durably recorded, so a
        ticket can never say something the decision log does not."""
        calls = dict(self._calls(module, func))
        assert calls["ticket_reconciler.after_runs"] > \
            calls["parallel_orchestrate.run_manifest"]


class TestNoTicketingConfiguredIsNotABrokenRun:
    """A pipeline run on somebody's laptop has no GITHUB_REPOSITORY and
    no `gh`. That is a run with no ticketing, which is the ordinary
    state of this repository for most of its life."""

    def test_it_returns_a_quiet_outcome_rather_than_raising(self, monkeypatch):
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        out = tr.after_runs("child-protection")
        assert out.quiet is True and out.failed == {}

    def test_no_service_means_no_connection_is_opened(self, monkeypatch):
        """Cheap, and it matters: a laptop run should not need a
        database reachable to decide it has no ticketing."""
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
        monkeypatch.setattr(tr, "service_from_env", lambda: None)
        assert tr.after_runs("child-protection").quiet is True


class TestTheReportDoesNotFloodTheTerminal:
    """Thirty-five copies of "the service is unreachable" buries the one
    line that matters and trains somebody to scroll past the end of a
    pipeline run."""

    def test_identical_failures_collapse_to_one_line(self, capsys):
        same = "TicketServiceUnavailable: gh is not installed here"
        tr.report(tr.Outcome(failed={f"cp-{i}/2026-Q3": same for i in range(35)}))
        out = capsys.readouterr().out
        assert out.count("gh is not installed here") == 1
        assert "35 slot(s)" in out

    def test_a_failure_of_its_own_still_names_its_slot(self, capsys):
        tr.report(tr.Outcome(failed={"cp-carers/2026-Q3": "something odd"}))
        assert "cp-carers/2026-Q3" in capsys.readouterr().out

    def test_a_quiet_pass_says_nothing_at_all(self, capsys):
        tr.report(tr.Outcome(unchanged=("cp-carers/2026-Q3",)))
        assert capsys.readouterr().out == ""
