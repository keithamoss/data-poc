"""The processing pass reads new slot-ticket comments and hands each to the
GitHub filing route once (REQ-GHUB-433).

GITHUB IS STOOD IN FOR, ALWAYS (Keith, 2026-11-22): the real API is never
called from a test and no real GitHub write happens. Two stand-ins:
`_Repo`, a ticket service with the three reads the stage makes and the one
write a refusal makes, for the stage itself; and `ticket_github._gh` replaced
by a recorder, for what GitHubTickets asks of `gh` - which is where criterion
2's 'two repository-level listings, never a request per ticket' lives.

The filing route itself (filing_from_github.handle_counted) is the real one:
a stranger is refused and a comment with no command ignored by the real
reader. Where a decision is RAISED, filing_decisions.apply - tested on its own
in tests/test_filing_decisions.py - is replaced by a recorder, so what the
stage hands it (the author, the period, the instant) is what is asserted.
"""
from __future__ import annotations

import json

import pytest

from qa_tools.common import filing_decisions, supply_db, ticket_comments
from qa_tools.common import ticket_github

KEITH = "keithamoss"
BOT = "mothman-bot"
SLOT = "cp-carers/2026-Q3"


def _c(cid, body, *, author=KEITH, created="2026-11-01T01:00:00Z", issue=7):
    return {"id": cid, "body": body, "author": author, "created_at": created, "issue": issue}


class _Repo:
    """A slot-ticket repository: its comments, its slot tickets, and what the
    stage posted. Any per-ticket read fails the test (criterion 2)."""

    def __init__(self, comments=(), tickets=None, fail=None):
        self.all = list(comments)
        self.tickets = {7: SLOT} if tickets is None else tickets
        self.fail = fail
        self.since, self.posted = [], []

    def issue_comments_since(self, since):
        if self.fail == "comments":
            raise RuntimeError("HTTP 502 from api.github.com")
        self.since.append(since)
        return list(self.all)

    def slot_tickets(self):
        return dict(self.tickets)

    def own_login(self):
        return BOT

    def comment(self, ticket, body):
        self.posted.append((ticket.number, body))

    def find(self, key):
        raise AssertionError("the stage made a request per ticket")

    comments = find


@pytest.fixture
def db(private_supply_dsn):
    from qa_tools.common import qa_store

    with supply_db.connect(label="test-ticket-comments") as conn:
        qa_store.ensure_schema(conn)
    return private_supply_dsn


@pytest.fixture
def applied(monkeypatch):
    """filing_decisions.apply recorded rather than run - see the docstring."""
    got = []

    def apply(request, *, effective_at, **kw):
        got.append((request, effective_at))
        return object()
    monkeypatch.setattr(filing_decisions, "apply", apply)
    monkeypatch.setattr(filing_decisions, "reconcile_after", lambda outcome, c: None)
    return got


PROMOTE = "/promote supply: cp-carers@1\nchecked it by hand"


class TestEachCommentIsHandedOn:
    """Criteria 1, 7 and 9: oldest first, the GitHub author as the actor and
    its creation instant as effective_at."""

    def test_oldest_first_with_its_own_instant_and_author(self, db, applied):
        repo = _Repo([_c(2, PROMOTE, created="2026-11-02T00:00:00Z"),
                      _c(1, PROMOTE, created="2026-11-01T00:00:00Z")])
        got = ticket_comments.read_and_handle(repo)
        assert [at for _r, at in applied] == ["2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z"]
        assert applied[0][0].actor["github"] == KEITH
        assert (applied[0][0].dataset_id, applied[0][0].period) == ("cp-carers", "2026-Q3")
        assert (got.read, got.raised, got.refused, got.failure) == (2, 2, 0, None)

    def test_an_author_named_in_the_body_is_not_the_actor(self, db, applied):
        repo = _Repo([_c(1, "/promote supply: x\nauthor: keithamoss", author="a-stranger")])
        got = ticket_comments.read_and_handle(repo)
        assert applied == [] and got.refused == 1
        assert "a-stranger" in repo.posted[0][1]


class TestTwoListingsAndNothingPerTicket:
    """Criterion 2, at what GitHubTickets asks of `gh`."""

    def test_the_reads_are_two_paged_repository_listings(self, monkeypatch):
        asked = []

        def gh(args):
            asked.append(args)
            if "user" in args:
                return "mothman-bot\n"
            if "issues/comments" in args[-1]:
                return json.dumps([{"id": 1, "body": "hi", "user": {"login": KEITH},
                                    "created_at": "2026-11-01T00:00:00Z",
                                    "issue_url": "https://api.github.com/repos/o/r/issues/7"}]) \
                    + json.dumps([{"id": 2, "body": "two", "user": {"login": KEITH},
                                   "created_at": "2026-11-02T00:00:00Z",
                                   "issue_url": "https://api.github.com/repos/o/r/issues/8"}])
            return json.dumps([{"number": 7, "labels": [{"name": "slot-ticket"},
                                                        {"name": f"slot:{SLOT}"}]}])
        monkeypatch.setattr(ticket_github, "_gh", gh)
        repo = ticket_github.GitHubTickets("o", "r")
        found = repo.issue_comments_since("2026-11-01T00:00:00Z")
        assert [(c["id"], c["issue"]) for c in found] == [(1, 7), (2, 8)], "both pages read"
        assert repo.slot_tickets() == {7: SLOT}
        listings = [a for a in asked if a[:2] == ["api", "--paginate"]]
        assert len(listings) == 2
        assert listings[0][-1] == "repos/o/r/issues/comments?per_page=100&since=2026-11-01T00:00:00Z"
        assert "labels=slot-ticket&state=all" in listings[1][-1]

    def test_the_stage_reads_no_ticket_on_its_own(self, db, applied):
        ticket_comments.read_and_handle(_Repo([_c(1, PROMOTE)]))   # _Repo.find raises


class TestOnceEach:
    """Criteria 4 and 5: handled ids in the asset's database, each handed on
    at most once whatever GitHub lists again; the listing anchored on the
    newest handled comment's creation instant."""

    def test_a_second_pass_hands_on_nothing_again(self, db, applied):
        repo = _Repo([_c(1, PROMOTE, created="2026-11-01T01:00:00Z")])
        ticket_comments.read_and_handle(repo)
        again = ticket_comments.read_and_handle(repo)     # GitHub lists it again
        assert len(applied) == 1 and again.read == 0
        assert repo.since == [None, "2026-11-01T01:00:00Z"]

    def test_an_edited_old_comment_is_not_raised_twice(self, db, applied):
        repo = _Repo([_c(1, PROMOTE)])
        ticket_comments.read_and_handle(repo)
        repo.all = [_c(1, PROMOTE + "\n(edited)")]
        ticket_comments.read_and_handle(repo)
        assert len(applied) == 1

    def test_the_record_is_in_the_database(self, db, applied):
        ticket_comments.read_and_handle(_Repo([_c(41, PROMOTE)]))
        with supply_db.connect(read_only=True, label="test-ticket-comments") as conn:
            assert ticket_comments.handled_ids(conn) == {41}


class TestWhatIsNeverACommand:
    def test_its_own_replies_are_left_out(self, db, applied):
        """Criterion 6."""
        got = ticket_comments.read_and_handle(_Repo([_c(1, PROMOTE, author=BOT)]))
        assert applied == [] and got.read == 0

    def test_another_asset_s_slot_is_neither_handled_nor_answered(self, db, applied):
        """Criterion 10: both assets name the same repository today."""
        repo = _Repo([_c(1, PROMOTE, issue=9)], tickets={7: SLOT, 9: "birth-registrations/2026-11-01"})
        got = ticket_comments.read_and_handle(repo)
        assert applied == [] and repo.posted == [] and got.read == 0 and got.not_ours == 1

    def test_a_comment_on_a_ticket_of_no_slot_is_left_alone(self, db, applied):
        got = ticket_comments.read_and_handle(_Repo([_c(1, PROMOTE, issue=99)]))
        assert applied == [] and got.read == 0


class TestAFailureMidPass:
    """Criterion 8: every id handled so far is kept, the stage fails naming the
    cause, and the rest is read on the next pass."""

    def test_a_failing_listing_is_named(self, db, applied):
        got = ticket_comments.read_and_handle(_Repo([_c(1, PROMOTE)], fail="comments"))
        assert got.failure and "issue comments" in got.failure[0] and "502" in got.failure[1]

    def test_a_route_failure_stops_the_stage_naming_the_comment(self, db, applied, monkeypatch):
        from qa_tools.common import filing_from_github as route

        real = route.handle_counted

        def handle(comment, **kw):
            if "second" in comment.body:
                raise RuntimeError("the decision log refused the connection")
            return real(comment, **kw)
        monkeypatch.setattr(route, "handle_counted", handle)
        repo = _Repo([_c(1, PROMOTE, created="2026-11-01T00:00:00Z"),
                      _c(2, PROMOTE + "\nsecond", created="2026-11-02T00:00:00Z"),
                      _c(3, PROMOTE, created="2026-11-03T00:00:00Z")])
        got = ticket_comments.read_and_handle(repo)
        assert "ticket comment 2" in got.failure[0] and "refused the connection" in got.failure[1]
        assert got.handled == [1]
        monkeypatch.setattr(route, "handle_counted", real)
        nxt = ticket_comments.read_and_handle(repo)
        assert nxt.handled == [2, 3], "the next pass reads the rest"


class TestThePassReport:
    """Criteria 11 and 14, at the pass and its terminal report."""

    @pytest.fixture
    def world(self, supply_dsn, monkeypatch):
        import test_processing_pass as tpp

        return tpp.TestThePassItself.world.__wrapped__(self, supply_dsn, monkeypatch)

    def test_ticketing_off_reads_nothing_and_says_so_once(self, world):
        from qa_tools.common import processing_pass as pp

        report = pp.run_pass(run_by="me", say=lambda m: None)
        assert report.comments is None
        assert sum("no ticket comment was read" in t for t in report.tickets) == 1

    def test_comments_read_that_raised_nothing_are_not_nothing_to_process(
            self, world, monkeypatch, capsys, private_supply_dsn):
        from cli import pipeline
        from qa_tools.common import processing_pass as pp
        from qa_tools.common import ticket_reconciler

        world.arrivals = []
        world.tickets = _Repo([_c(1, "thanks, looking at it now")])
        monkeypatch.setattr(ticket_reconciler, "after_runs", lambda c: ticket_reconciler.Outcome())
        monkeypatch.setattr(ticket_reconciler, "report", lambda outcome: None)
        report = pp.run_pass(run_by="me", say=lambda m: None)
        assert (report.comments.read, report.comments.raised, report.comments.refused) == (1, 0, 0)
        assert not report.nothing_to_do
        pipeline._say_pass(report)
        out = capsys.readouterr().out
        assert "Nothing to process" not in out
        assert "Read 1 new ticket comment(s): 0 decision(s) raised, 0 refused." in out

    def test_a_failed_stage_fails_the_pass_naming_the_call(self, world, private_supply_dsn):
        from qa_tools.common import processing_pass as pp

        world.arrivals = []
        world.tickets = _Repo(fail="comments")
        report = pp.run_pass(run_by="me", say=lambda m: None)
        assert report.exit_status == pp.EXIT_FAILED
        assert any("issue comments" in what for what, _ in report.failures)


class TestTheTicketSaysWhenCommandsAreRead:
    """Criterion 12: at the next pass, and how often as configuration declares
    it - nothing about how often where none is declared."""

    def _state(self):
        from qa_tools.common import slot_state

        return slot_state.SlotState(dataset_id="cp-carers", period="2026-Q3",
                                    state=slot_state.AWAITING_DECISION)

    def test_undeclared_says_only_the_next_pass(self, monkeypatch):
        from qa_tools.common import environments, ticket_reconciler as tr

        monkeypatch.setattr(environments, "current_or_none",
                            lambda *a: environments.Environment(id="production", label="P"))
        body = tr.body_for(self._state())
        assert "acted on at the next processing pass." in body
        assert "every" not in body.split("next processing pass")[-1]

    def test_a_declared_interval_is_said(self, monkeypatch):
        from qa_tools.common import environments, ticket_reconciler as tr

        monkeypatch.setattr(environments, "current_or_none", lambda *a: environments.Environment(
            id="production", label="P", processing_interval_minutes=15))
        assert "passes run every 15 minutes." in tr.body_for(self._state())

    def test_the_interval_is_read_from_the_environments_file(self, tmp_path):
        from qa_tools.common import environments

        path = tmp_path / "environments.yaml"
        path.write_text("environments:\n  - id: prod\n    processing_interval_minutes: 120\n")
        (env,) = environments.all_environments(path)
        assert env.processing_interval_minutes == 120
        assert environments.interval_words(120) == "every 2 hours"
        path.write_text("environments:\n  - id: prod\n    processing_interval_minutes: soon\n")
        with pytest.raises(environments.EnvironmentError_):
            environments.all_environments(path)


#: Child Protection's slots are the quarterly asset's.
pytestmark = pytest.mark.asset("quarterly")
