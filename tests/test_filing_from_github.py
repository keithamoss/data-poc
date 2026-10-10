"""Raising a filing decision from a comment (REQ-GHUB-082 criteria 1, 4,
5, 7, 23 and 30).

AN ADAPTER'S TESTS, therefore, and they are about the two things that
are genuinely this route's: reading an operation out of prose somebody
typed, and saying no on the thread they typed it in. What a decision
MEANS is tested once, in tests/test_filing_decisions.py, because there
is one implementation of it.
"""
from __future__ import annotations

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import filing_decisions as fd
from qa_tools.common import filing_from_github as gh
from qa_tools.common import people

SLOT = "cp-carers/2026-Q3"
KEITH = "keithamoss"


def _comment(body, author=KEITH, slot_key=SLOT):
    return gh.Comment(body=body, author=author, slot_key=slot_key)


class TestPeopleTalkOnTickets:
    """Criterion 5's first half: a comment carrying no known command is
    ignored OUTRIGHT - no refusal, no reply, no entry. A route that
    answered every sentence would make the thread unusable for the thing
    threads are for."""

    @pytest.mark.parametrize("body", [
        "Any idea why this one is late?",
        "I'll chase the supplier tomorrow.",
        "",
        "/nonsense some arguments",
        "promote it please",          # no slash: addressed to people
        "See /promote in the runbook for how this works",  # not line-initial
    ])
    def test_it_raises_nothing(self, body):
        with pytest.raises(gh.NoDecisionHere):
            gh.read(_comment(body))

    def test_handle_returns_None_and_says_nothing(self):
        said = []
        got = gh.handle(_comment("just talking"), collection_id="child-protection",
                         effective_at="2026-09-29T09:00:00+08:00",
                         service=_Service(said), ticket=object())
        assert got is None
        assert said == [], "a conversation must not be answered with a refusal"


class TestTheProseAROUNDACommandIsIgnored:
    """Criterion 5's second half. A person raises a decision in their own
    words, and those words are the REASON rather than noise to be
    stripped - criterion 10 refuses the decision without one, and asking
    them to repeat it inside a `reason:` argument is how a reason becomes
    "see above"."""

    def test_the_words_above_and_below_become_the_reason(self):
        request = gh.read(_comment(
            "The supplier confirmed this extract is not coming.\n"
            "/substitute supply: cp-carers@2026 stands-on: 2026-Q2\n"
            "Standing it on last quarter until they resend."))
        assert request.operation == fd.SUBSTITUTE
        assert "not coming" in request.reason
        assert "Standing it on last quarter" in request.reason
        assert "/substitute" not in request.reason

    def test_a_key_word_in_a_SENTENCE_is_not_an_argument(self):
        """The arguments come off the command LINE only. Somebody
        writing "the supply: it was truncated" is writing a sentence."""
        request = gh.read(_comment(
            "/demote\nAbout the supply: it was truncated on arrival."))
        assert request.supply is None
        assert "truncated" in request.reason


class TestWhereTheDecisionActs:
    """Criterion 1: the period comes from the TICKET's own identity,
    never from anything stated in the body. A comment that could name
    its own period could act on a period its author is not looking
    at."""

    def test_the_dataset_and_period_come_from_the_slot_key(self):
        request = gh.read(_comment("/promote supply: cp-carers@2026\nlooks fine"))
        assert request.dataset_id == "cp-carers"
        assert request.period == "2026-Q3"

    def test_a_period_named_in_the_body_changes_nothing(self):
        request = gh.read(_comment(
            "/promote supply: cp-carers@2026 period: 2024-Q1\nlooks fine"))
        assert request.period == "2026-Q3"

    def test_a_ticket_that_is_not_a_slot_raises_nothing(self):
        with pytest.raises(gh.NoDecisionHere):
            gh.read(_comment("/promote\nr", slot_key="not-a-slot"))


class TestWhoIsAsking:
    """Criterion 4. Anybody who can comment on a public repository can
    type somebody else's name; only GitHub can say whose account
    posted."""

    def test_the_actor_is_the_authenticated_author(self):
        request = gh.read(_comment("/promote supply: s\nbecause"))
        assert request.actor_name == "fpycnkgvmt@privaterelay.appleid.com"

    def test_there_is_nowhere_to_claim_one(self):
        """The rule made structural rather than checked: `Comment` has
        no field for an actor, so a body cannot supply one."""
        assert not hasattr(gh.Comment(body="", author="a", slot_key=SLOT), "actor")

    def test_a_name_typed_in_the_body_is_not_read_as_one(self):
        request = gh.read(_comment(
            "/promote supply: s\nactor: somebody-else\nRaising on their behalf."))
        assert request.actor_name == "fpycnkgvmt@privaterelay.appleid.com"

    def test_a_stranger_is_refused_rather_than_ignored(self):
        """Criterion 14 reaching this route. Ignoring them would leave
        somebody believing their decision had been taken."""
        with pytest.raises(people.UnknownActor):
            gh.read(_comment("/promote supply: s\nbecause", author="a-stranger"))


class TestOneCommandPerComment:
    """Two would be two decisions with one reason between them, and the
    second would inherit the first's justification - exactly what
    criterion 10 exists to prevent."""

    def test_two_are_refused_rather_than_half_obeyed(self):
        with pytest.raises(dl.DecisionRefused) as exc:
            gh.read(_comment("/promote supply: s\n/reject supply: s\nboth please"))
        assert "separate comments" in str(exc.value)


class TestConfirmation:
    """Criteria 9 and 28 on this route. The destructive operations take
    an explicit confirmation, and on a ticket that has to be something
    the person typed."""

    @pytest.mark.parametrize("word", ["yes", "true", "confirmed", "YES"])
    def test_an_affirmative_confirms(self, word):
        assert gh.read(_comment(f"/un-inherit confirm: {word}\nfreeing it")).confirmed

    def test_anything_else_does_not(self):
        assert not gh.read(_comment("/un-inherit confirm: maybe\nfreeing it")).confirmed

    def test_omitting_it_does_not(self):
        assert not gh.read(_comment("/un-inherit\nfreeing it")).confirmed


class _Service:
    """A ticket service that records what it was asked to post."""

    def __init__(self, said, fail=False):
        self.said = said
        self.fail = fail

    def comment(self, ticket, body):
        if self.fail:
            raise RuntimeError("gh: not found")
        self.said.append(body)


class TestARefusalIsSaidOnTheThreadThatRaisedIt:
    """Criteria 22 and 23. A refusal appends nothing to the decision
    log, so REQ-PIPE-083's pass would correctly find nothing changed and
    say nothing - and the person who raised it would be told, in
    silence, that it had been accepted."""

    def _handled(self, body, author=KEITH, service=None):
        said = []
        service = service or _Service(said)
        got = gh.handle(_comment(body, author=author),
                         collection_id="child-protection",
                         effective_at="2026-09-29T09:00:00+08:00",
                         service=service, ticket=object())
        return got, said

    def test_a_stranger_is_told_why_on_the_ticket(self):
        got, said = self._handled("/promote supply: s\nbecause", author="a-stranger")
        assert got is None
        assert len(said) == 1
        assert "a-stranger" in said[0]
        assert "not recorded" in said[0]

    def test_a_missing_reason_is_told_why(self):
        got, said = self._handled("/promote supply: s")
        assert got is None
        assert "needs a reason" in said[0]

    def test_an_unconfirmed_destructive_one_is_told_why(self):
        got, said = self._handled("/un-inherit\nfreeing the demotion")
        assert got is None
        assert "confirmation" in said[0]

    def test_it_is_POSTED_rather_than_left_to_the_reconciler(self, monkeypatch):
        """The pass runs on a CHANGE. A refusal is not one, so the pass
        would say nothing - which reads, to whoever raised it, exactly
        like acceptance."""
        import qa_tools.common.ticket_reconciler as tr
        passes = []
        monkeypatch.setattr(tr, "after_runs", lambda *a, **k: passes.append(1))
        _got, said = self._handled("/promote supply: s")
        assert said, "the refusal was not posted"
        assert passes == [], "a refusal must not go through the reconciler's pass"

    def test_an_unpostable_refusal_does_not_crash_the_next_comment(self):
        """Whatever invokes this is processing comments, possibly
        several. One stranger's attempt must not stop the next person's
        real decision."""
        said = []
        got, _ = self._handled("/promote supply: s", service=_Service(said, fail=True))
        assert got is None

    def test_nothing_reaches_the_decision_log(self, supply_dsn):
        from qa_tools.common import qa_store, supply_db

        with supply_db.connect(label="test-github-refusal") as conn:
            qa_store.ensure_schema(conn)
            before = len(dl.decisions_for(conn, "cp-carers"))
        self._handled("/promote supply: s\nbecause", author="a-stranger")
        with supply_db.connect(label="test-github-refusal") as conn:
            assert len(dl.decisions_for(conn, "cp-carers")) == before


class TestTheTerminalRouteNeverCallsGitHub:
    """Criterion 30, asserted at the only place it can be: this module
    is the GitHub route, and `filing_decisions` - which the terminal
    route will use - must not import it.

    The requirement's own reason: the terminal route needs no GitHub
    reachability, and the ticket is updated by whatever already has it.
    """

    def test_the_shared_implementation_does_not_import_this_one(self):
        import inspect

        source = inspect.getsource(fd)
        assert "filing_from_github" not in source
        assert "ticket_github" not in source, (
            "the shared implementation reaches GitHub only through "
            "REQ-PIPE-083's own reconciling pass, which is a different thing")


class TestGitHubIsTheInputChannelAndTheLogIsTheRecord:
    """Criterion 7: SHALL NOT read current filing state back out of an
    issue.

    A ticket is what a reconciling pass WROTE about a slot, so reading
    state from it would be reading our own last summary and calling it
    the truth - and a summary a person edited would then decide what
    happens next.
    """

    def test_nothing_here_reads_the_ticket(self):
        """Driven by a service that has ONLY `comment`. Anything that
        tried to find, list or read a ticket would raise
        AttributeError rather than quietly succeeding."""
        class _WriteOnly:
            def __init__(self):
                self.said = []

            def comment(self, ticket, body):
                self.said.append(body)

        service = _WriteOnly()
        gh.handle(_comment("/promote supply: s"), collection_id="child-protection",
                   effective_at="2026-09-29T09:00:00+08:00",
                   service=service, ticket=object())
        assert service.said, "the refusal should still have been posted"

    def test_the_module_never_mentions_reading_one(self):
        import inspect

        source = inspect.getsource(gh)
        for reader in (".comments(", ".find("):
            assert reader not in source, (
                f"{reader} would read filing state out of an issue, which "
                f"criterion 7 forbids - the decision log is the record")
