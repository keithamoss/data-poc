"""The reconciler's ticket service, over real GitHub Issues
(REQ-PIPE-083 criteria 2, 3, 17 and 19).

`gh` IS NOT INSTALLED IN THIS CONTAINER, and that is not a gap these
tests work around - it is what makes criterion 17 observable rather
than merely asserted. "Where the ticketing service cannot be reached,
THE SYSTEM SHALL NOT fail the operation that prompted the
reconciliation" is a claim about a real absence, and there is a real
absence here to make it against.

Everything else is driven by replacing the ONE subprocess call, which
is deliberate: a fake that replaced the whole class would prove the fake
works. Replacing `_gh` leaves every argument list this module builds
under test, and the argument list is where criterion 19 lives.
"""
from __future__ import annotations

import json

import pytest

from qa_tools.common import ticket_github as tg


@pytest.fixture
def calls(monkeypatch):
    """Every `gh` invocation this module makes, and what it gets back."""
    seen: list[list[str]] = []
    replies: dict = {}

    def fake_gh(args):
        seen.append(list(args))
        for prefix, reply in replies.items():
            if args[:len(prefix)] == list(prefix):
                return reply
        return ""

    monkeypatch.setattr(tg, "_gh", fake_gh)
    return seen, replies


@pytest.fixture
def svc():
    return tg.GitHubTickets("keithamoss", "data-poc")


class TestAnAbsentServiceRefusesCleanly:
    """Criterion 17, against a real absence rather than a mocked one."""

    def test_gh_missing_raises_the_services_own_type(self, svc):
        with pytest.raises(tg.TicketServiceUnavailable):
            svc.find("cp-carers/2026-Q3")

    def test_it_says_the_change_still_stands(self, svc):
        """The message is what somebody reads in a pipeline run's
        output, and it has to say the thing that is true: nothing was
        lost."""
        with pytest.raises(tg.TicketServiceUnavailable) as exc:
            svc.find("cp-carers/2026-Q3")
        assert "durable record" in str(exc.value)

    def test_the_reconciler_records_it_and_carries_on(self, svc):
        """Criterion 20 meeting criterion 17: every slot fails, and the
        pass still returns rather than raising at the caller."""
        from qa_tools.common import slot_state, ticket_reconciler as tr

        states = [slot_state.SlotState(dataset_id=d, period="2026-Q3",
                                        state=slot_state.OVERDUE)
                   for d in ("cp-carers", "cp-clients")]
        out = tr.reconcile(svc, states, policy=tr.ALL)
        assert sorted(out.failed) == ["cp-carers/2026-Q3", "cp-clients/2026-Q3"]
        assert out.opened == ()


class TestEveryWayTheServiceCanBeAbsentSaysTheSameThing:
    """Criterion 17's MESSAGE, on the path this container cannot reach.

    `gh` is missing here, so every test above takes the FileNotFoundError
    branch. A GitHub Actions runner HAS gh and has no token for it, so it
    takes the CalledProcessError branch instead - and that one used to
    say only "`gh issue list` failed: <stderr>", with none of the "the
    change still stands" that the whole message exists to carry. Found by
    CI going red on the test above, 2026-09-29, in an environment this
    one cannot reproduce by accident.

    Both branches are driven here explicitly rather than relying on
    whichever one the host happens to take, because a test that passes
    for a reason about the machine is a test that stops covering the
    other reason.
    """

    def test_a_missing_gh_says_the_change_still_stands(self, monkeypatch):
        def missing(*a, **k):
            raise FileNotFoundError("gh")

        monkeypatch.setattr(tg.subprocess, "run", missing)
        with pytest.raises(tg.TicketServiceUnavailable) as exc:
            tg._gh(["issue", "list"])
        assert "durable record" in str(exc.value)

    def test_an_unauthenticated_gh_says_it_too(self, monkeypatch):
        """The real CI message: gh is installed, GH_TOKEN is unset, and
        it exits non-zero telling you so."""
        def refused(*a, **k):
            raise tg.subprocess.CalledProcessError(
                4, ["gh"], output="",
                stderr="gh: To use GitHub CLI in a GitHub Actions workflow, "
                        "set the GH_TOKEN environment variable.")

        monkeypatch.setattr(tg.subprocess, "run", refused)
        with pytest.raises(tg.TicketServiceUnavailable) as exc:
            tg._gh(["issue", "list"])
        assert "durable record" in str(exc.value)

    def test_and_still_says_what_actually_went_wrong(self, monkeypatch):
        """The reassurance must not replace the diagnosis. Somebody
        reading a pipeline run needs to know it was the token."""
        def refused(*a, **k):
            raise tg.subprocess.CalledProcessError(
                4, ["gh"], output="", stderr="set the GH_TOKEN environment variable")

        monkeypatch.setattr(tg.subprocess, "run", refused)
        with pytest.raises(tg.TicketServiceUnavailable) as exc:
            tg._gh(["issue", "list"])
        assert "GH_TOKEN" in str(exc.value)
        assert "issue list" in str(exc.value)


class TestEveryReadIsFencedByThisSchemesOwnLabel:
    """Criterion 19, in its enforceable form. A query that can only ever
    SEE this scheme's tickets cannot adopt, re-key, close or delete
    another one, however the code around it changes."""

    def test_the_find_query_carries_the_scheme_label(self, svc, calls):
        seen, _ = calls
        svc.find("cp-carers/2026-Q3")
        assert tg.SCHEME_LABEL in seen[0]

    def test_and_the_slot_label(self, svc, calls):
        seen, _ = calls
        svc.find("cp-carers/2026-Q3")
        assert "slot:cp-carers/2026-Q3" in seen[0]

    def test_a_new_ticket_carries_both_labels(self, svc, calls):
        seen, replies = calls
        replies[("issue", "create")] = "https://github.com/keithamoss/data-poc/issues/7\n"
        svc.open("cp-carers/2026-Q3", "title", "body")
        created = [c for c in seen if c[:2] == ["issue", "create"]][0]
        assert tg.SCHEME_LABEL in created
        assert "slot:cp-carers/2026-Q3" in created

    def test_nothing_here_can_close_or_delete(self):
        """The strongest form of criterion 19: the verbs are absent."""
        import inspect
        source = inspect.getsource(tg)
        assert '"close"' not in source and '"delete"' not in source


class TestItFindsATicketAPersonClosed:
    """Criterion 12 needs it, and a query filtered to OPEN tickets would
    quietly open a second one for that slot instead - which is criterion
    2's whole risk."""

    def test_the_query_asks_for_all_states(self, svc, calls):
        seen, _ = calls
        svc.find("cp-carers/2026-Q3")
        assert "--state" in seen[0] and "all" in seen[0]

    def test_a_closed_ticket_comes_back_marked_closed(self, svc, calls):
        _, replies = calls
        replies[("issue", "list")] = json.dumps([{"number": 12, "state": "CLOSED"}])
        got = svc.find("cp-carers/2026-Q3")
        assert got.number == 12 and got.closed is True

    def test_an_open_one_comes_back_open(self, svc, calls):
        _, replies = calls
        replies[("issue", "list")] = json.dumps([{"number": 12, "state": "OPEN"}])
        assert svc.find("cp-carers/2026-Q3").closed is False

    def test_no_ticket_is_None_rather_than_an_error(self, svc, calls):
        assert svc.find("cp-carers/2026-Q3") is None


class TestTwoReconcilersRacingAgreeAfterwards:
    """Criterion 2's hardest half - "however many reconcilers are
    running at the same moment". Neither can be stopped from creating,
    so the rule is that they agree on WHICH is the ticket."""

    def test_the_lowest_number_wins(self, svc, calls):
        _, replies = calls
        replies[("issue", "list")] = json.dumps(
            [{"number": 31, "state": "OPEN"}, {"number": 12, "state": "OPEN"}])
        assert svc.find("cp-carers/2026-Q3").number == 12

    def test_and_it_is_the_older_one(self, svc, calls):
        """The older ticket is the one anybody may already have
        commented on, which is why it is the survivor rather than an
        arbitrary choice."""
        _, replies = calls
        replies[("issue", "list")] = json.dumps(
            [{"number": 12, "state": "OPEN"}, {"number": 31, "state": "OPEN"}])
        assert svc.find("cp-carers/2026-Q3").number == 12


class TestTheSlotKeyIsInALabelRatherThanTheTitle:
    """A title is something a person edits, and a ticket that stops
    being findable because somebody tidied its wording is a second
    ticket for the same slot on the next pass."""

    def test_the_label_carries_the_key(self):
        assert tg.slot_label("cp-carers/2026-Q3") == "slot:cp-carers/2026-Q3"

    def test_the_query_does_not_search_the_title(self, svc, calls):
        seen, _ = calls
        svc.find("cp-carers/2026-Q3")
        assert "--search" not in seen[0]


class TestTheLabelsAreCreatedBeforeTheyAreUsed:
    """`gh issue create --label` needs a real repo label, unlike
    `gh issue list --label` which silently matches nothing - a real bug
    this project already hit once."""

    def test_both_labels_are_ensured_before_the_issue(self, svc, calls):
        seen, replies = calls
        replies[("issue", "create")] = "https://github.com/x/y/issues/1\n"
        svc.open("cp-carers/2026-Q3", "t", "b")
        kinds = [c[0] for c in seen]
        assert kinds.index("label") < kinds.index("issue")

    def test_it_ensures_each_label_once_per_service(self, svc, calls):
        seen, replies = calls
        replies[("issue", "create")] = "https://github.com/x/y/issues/1\n"
        svc.open("cp-carers/2026-Q3", "t", "b")
        svc.open("cp-carers/2026-Q3", "t", "b")
        assert len([c for c in seen if c[0] == "label"]) == 2


class TestReadingBackWhatGhSaid:
    def test_the_issue_number_comes_from_the_url(self, svc, calls):
        _, replies = calls
        replies[("issue", "create")] = "https://github.com/keithamoss/data-poc/issues/88\n"
        assert svc.open("k", "t", "b").number == 88

    def test_output_it_cannot_read_is_the_SERVICE_failing(self, svc, calls):
        """Not one slot's problem: it means `gh` printed something this
        does not understand, which is the same class as it not being
        there at all."""
        _, replies = calls
        replies[("issue", "create")] = "something else entirely"
        with pytest.raises(tg.TicketServiceUnavailable):
            svc.open("k", "t", "b")

    def test_comments_come_back_as_plain_bodies(self, svc, calls):
        _, replies = calls
        replies[("issue", "view")] = json.dumps(
            {"comments": [{"body": "first"}, {"body": "second"}]})
        got = svc.comments(tg.Ticket(key="k", number=1))
        assert got == ["first", "second"]

    def test_a_ticket_with_no_comments_is_an_empty_list(self, svc, calls):
        assert svc.comments(tg.Ticket(key="k", number=1)) == []
