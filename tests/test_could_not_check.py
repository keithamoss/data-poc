"""A supply nobody could check (REQ-PIPE-417 criterion 11, REQ-TEST-418
criterion 6).

Each supply is received and filed as a real one is (a delivery record, its
file's receipt, its filing), and each try at its run opened and ended by the
writer the orchestrator's run step calls - so the blocker, the 'needs a
person' item, the filing-queue state, the processing pass's own state and the
terminal's commands are all read from a record made the real way.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import filing_support
from qa_tools.common import (
    dataset_blockers, decision_log, filing_queue, outstanding, processing_pass, qa_store,
    qa_results_writer, supply_db,
)

DS = "cp-clients"
TABLE = "cp_clients"
AGENCY = "child-protection-family-support"
CP = "child-protection"
PERIOD = "2030-Q1"
WHEN = "2030-01-05T10:00:00+08:00"
BY = "tests@example.gov.au"
SECRET = "SECRET-ROW-VALUE-9182"

pytestmark = pytest.mark.asset("quarterly")


@pytest.fixture
def conn(clean_qa_history):
    supply_db.ensure_schemas(clean_qa_history)
    with supply_db.connect(label="test-could-not-check") as c:
        for table in ("hold", "load_outcome", "filing", "delivery_file", "delivery"):
            c.execute(f'TRUNCATE "{qa_store.SCHEMA}"."{table}" CASCADE')
    yield clean_qa_history


class Supply:
    """One received, filed supply of cp-clients, and its runs."""

    def __init__(self, conn):
        # ITS OWN RECEIPT INSTANT: qa.decision is never truncated, so no
        # earlier test's decision about this arrival can answer this one.
        self.received = datetime(2030, 1, 2, tzinfo=timezone.utc) + timedelta(
            seconds=uuid.uuid4().int % 10_000_000)
        self.key = supply_db.arrival_segment(self.received.isoformat())
        self.id = f"{DS}@{self.key}"
        self.run_id = f"{TABLE}__{self.key}"
        self.delivery = f"pytest-cnc-{self.key}"
        filing_support.ensure_delivery(self.delivery, DS, self.received)
        filing_support.place(conn, DS, self.id, PERIOD, self.delivery)
        self.conn = conn

    def tries(self, *outcomes: str, run_id: str | None = None, **purpose) -> str:
        """'C' completes, 'X' fails in dbt-core, 'Y' crashes outside a tool."""
        from qa_tools.tools import orchestrate

        run_id = run_id or self.run_id
        stated = {"dataset_id": DS, "supply_id": self.id, "scope": "arrival", **purpose}
        for outcome in outcomes:
            qa_results_writer.open_run(AGENCY, CP, run_id, WHEN, BY, purpose=stated)
            if outcome == "C":
                qa_results_writer.finish_run(run_id)
            elif outcome == "X":
                qa_results_writer.close_attempt(run_id, orchestrate.QaRunFailure(
                    "dbt-core failed", tool="dbt-core", cause=ValueError(SECRET)))
            else:
                qa_results_writer.close_attempt(run_id, RuntimeError(SECRET))
        return run_id

    def decide(self, action: str, at: datetime, **extra) -> int:
        """A decision about this supply recorded in the log, as of `at`."""
        return decision_log._insert(self.conn, decision_log.Decision(
            agency_id=AGENCY, collection_id=CP, dataset_id=DS, action=action,
            supply=self.id, actor="person@example.com",
            actor_kind=decision_log.PERSON, effective_at=at.isoformat(),
            reason="test", from_slot=PERIOD, **extra))

    def blockers(self) -> list:
        return [b for b in dataset_blockers.all_blockers(self.conn)
                if b.kind == dataset_blockers.COULD_NOT_CHECK and b.supply == self.id]


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value)


class TestAnArrivalWhoseOnlyTryCrashed:
    """Criteria 1, 2, 4, 5 and 6."""

    def test_red_from_receipt_with_its_item_and_its_queue_state(self, conn):
        s = Supply(conn)
        s.tries("X")
        (b,) = s.blockers()
        assert b.is_open and _at(b.opened_at) == s.received
        assert not b.open_at(s.received - timedelta(seconds=1)) and b.open_at(s.received)
        assert "failed in dbt-core" in b.reason and SECRET not in b.reason
        assert b.tries["errorType"] == "ValueError" and b.tries["failed"] == 1

        (item,) = [i for i in outstanding.survey(conn).items
                   if i.kind == outstanding.COULD_NOT_CHECK]
        assert item.blocking and item.headline == f"{TABLE} could not be checked"
        for words in ("failed in dbt-core", "Nothing is yet known", "next processing pass",
                      "reject the supply", "mothman supply failures"):
            assert words in item.detail
        assert SECRET not in item.detail

        (state,) = [q for q in filing_queue.awaiting(conn, CP)
                    if q.state == filing_queue.COULD_NOT_CHECK]
        assert state.supply == s.id and state.period == PERIOD
        assert filing_queue.operations_for(state) == ((filing_decisions_reject(),), ())

    def test_no_fail_is_recorded_on_the_supply(self, conn):
        s = Supply(conn)
        s.tries("X")
        assert not conn.execute(
            f'SELECT 1 FROM "{qa_store.SCHEMA}".check_result WHERE run_key = ? '
            "AND status IN ('fail', 'error')", [s.run_id]).fetchall()

    def test_three_failed_tries_say_three(self, conn):
        s = Supply(conn)
        s.tries("X", "Y", "X")
        (b,) = s.blockers()
        assert b.tries["failed"] == 3 and "3 tries" in b.reason


def filing_decisions_reject():
    from qa_tools.common import filing_decisions

    return filing_decisions.REJECT


class TestADecisionRecheckThatCrashed:
    """Criterion 2: the earlier verdict until the decision's effective time."""

    def test_opens_at_its_decision(self, conn):
        s = Supply(conn)
        s.tries("C")
        decided = s.received + timedelta(days=3)
        decision = s.decide(decision_log.RECHECK, decided)
        s.tries("Y", run_id=f"{TABLE}__recheck_{s.key}", scope="full",
                caused_by_decision=decision)
        (b,) = s.blockers()
        assert _at(b.opened_at) == decided
        assert not b.open_at(decided - timedelta(seconds=1)) and b.open_at(decided)


class TestRunsThatNeverCount:
    """Criterion 7."""

    def test_a_gate_application_recheck_and_a_readers_only_run(self, conn):
        s = Supply(conn)
        s.tries("C")
        s.tries("Y", run_id=f"{TABLE}__gate_{s.key}", scope="full", caused_by_decision=1,
                gate_application=990077)
        s.tries("Y", run_id=f"{TABLE}__readers_{s.key}", scope="readers",
                caused_by_decision=1, reads_table=TABLE, period=PERIOD)
        assert s.blockers() == []


class TestReopenedThenCrashed:
    def test_red(self, conn):
        """B2: the earlier verdict stands only until the reopened try."""
        s = Supply(conn)
        s.tries("C", "X")
        (b,) = s.blockers()
        assert b.is_open


class TestWhatClosesIt:
    """Criterion 3."""

    def test_a_completing_try(self, conn):
        s = Supply(conn)
        s.tries("X", "C")
        (b,) = s.blockers()
        (_, done) = qa_store.attempts_of(conn, s.run_id)
        assert b.resolved_at is not None and _at(b.resolved_at) == done["ended_at"]
        assert not [i for i in outstanding.survey(conn).items
                    if i.kind == outstanding.COULD_NOT_CHECK]

    def test_a_rejection_with_no_try_completing(self, conn):
        s = Supply(conn)
        s.tries("X")
        rejected = s.received + timedelta(days=1)
        s.decide(decision_log.REJECT, rejected)
        (b,) = s.blockers()
        assert _at(b.resolved_at) == rejected and b.rejected
        assert not [q for q in filing_queue.awaiting(conn, CP)
                    if q.state == filing_queue.COULD_NOT_CHECK]

    def test_a_supersession(self, conn):
        s = Supply(conn)
        s.tries("X")
        moved = s.received + timedelta(days=2)
        s.decide(decision_log.SUPERSEDE, moved)
        (b,) = s.blockers()
        assert _at(b.resolved_at) == moved


class TestARejectedArrivalNobodyCouldCheck:
    """Criterion 10 (TV2): processed - not retried, holding nothing back."""

    def test_it_is_processed(self, conn):
        s = Supply(conn)
        s.tries("X")
        arrival = SimpleNamespace(run_id=s.run_id, collection_id=CP, received_at=s.received,
                                  files_by_dataset={DS: (f"{TABLE}.csv",)})
        assert processing_pass.state_of(arrival, processing_pass.recorded(conn)) == \
            processing_pass.UNCHECKED
        # TAKEN EFFECT: on the one clock, which reads today, before this
        # synthetic receipt - so a rejection effective today.
        from asset_model import asset_time

        s.decide(decision_log.REJECT, asset_time.now() - timedelta(minutes=1))
        assert processing_pass.state_of(arrival, processing_pass.recorded(conn)) == \
            processing_pass.PROCESSED
        assert arrival not in processing_pass.unprocessed([arrival], conn=conn)


class TestAReloadsRecheckThatCrashed:
    """TV1: red continuous from the reload, where 'Could not be loaded' ends."""

    def test_continuous(self, conn):
        from qa_tools.common import load_log

        s = Supply(conn)
        failed_at = s.received + timedelta(minutes=5)
        reloaded_at = s.received + timedelta(days=1)
        load_log.record(s.delivery, DS, s.run_id, load_log.FAILED, failed_at.isoformat(),
                        reason="bad bytes", conn=conn)
        again = load_log.record(s.delivery, DS, s.run_id, load_log.LOADED,
                                reloaded_at.isoformat(), conn=conn)
        s.tries("Y", run_id=f"{TABLE}__reload_{s.key}", scope="full", caused_by_load=again.id)
        (refused,) = [b for b in dataset_blockers.all_blockers(conn)
                      if b.kind == dataset_blockers.REFUSED and b.dataset_id == DS]
        (b,) = s.blockers()
        assert _at(refused.resolved_at) == reloaded_at == _at(b.opened_at)


class TestAPackageMatesLine:
    """Criterion 8 (TR2): a mate's line keeps its 'run stopped' and drops
    'Nothing needs deciding yet.' while the mate could not be checked."""

    def test_the_mates_line(self):
        from pipeline import package_gating as pg

        received = datetime(2030, 1, 2, tzinfo=timezone.utc)
        pkg = SimpleNamespace(members=[("cp-clients", "a"), ("cp-carers", "b")],
                              received=received)
        when = received + timedelta(days=1)
        stopped = {"b": [received + timedelta(hours=1)]}
        common = dict(gate_owed=[], app_windows=[], checked_at={"a": received},
                      stopped_at=stopped, settles=[], when=when)
        plain = pg._state("cp-clients", "a", pkg, **common)
        lead, rest = pg.words(plain, received)
        assert "Nothing needs deciding yet." in "".join(r.get("text", "") for r in rest)
        state = pg._state("cp-clients", "a", pkg, **common,
                          unchecked={"b": [(received + timedelta(hours=1), None)]})
        lead, rest = pg.words(state, received)
        text = "".join(r.get("text", "") for r in rest)
        assert "Nothing needs deciding yet." not in text
        assert "'s run stopped; the next processing pass re-runs it." in text
        # ITS OWN 'COULD NOT BE CHECKED' REPLACES THE FORMS.
        assert pg._state("cp-carers", "b", pkg, **common,
                         unchecked={"b": [(received, None)]}) is None


# ---------------------------------------------------------------------------
# REQ-TEST-418: the terminal
# ---------------------------------------------------------------------------

def _supply_cmd(args):
    from cli.supply import supply_group

    return CliRunner().invoke(supply_group, args)


class TestTheTerminal:

    def test_supply_failures_lists_every_try_and_its_full_message_beside_a_failed_load(
            self, conn):
        from qa_tools.common import load_log

        s = Supply(conn)
        s.tries("X", "Y")
        load_log.record("monday", DS, f"{TABLE}__2031", load_log.FAILED,
                        WHEN, reason="UnicodeDecodeError: byte 0x9c", conn=conn)
        out = _supply_cmd(["failures"])
        assert out.exit_code == 0, out.output
        assert "could not be loaded" in out.output and "UnicodeDecodeError" in out.output
        assert "could not be checked" in out.output and s.id in out.output
        assert "try 1:" in out.output and "try 2:" in out.output
        assert "crashed in dbt-core after" in out.output and "(ValueError)" in out.output
        assert out.output.count(SECRET) == 2, "every try's full message, once each"
        assert "retry it" in out.output and "Reject the supply" in out.output

    def test_supply_history_shows_run_times(self, conn, monkeypatch):
        from qa_tools.common import arrival_history

        s = Supply(conn)
        ticks = iter([0.0, 192.0])
        monkeypatch.setattr(qa_results_writer, "_counter", lambda: next(ticks))
        s.tries("C")
        monkeypatch.setattr(arrival_history, "arrivals_of", lambda ds: [SimpleNamespace(
            supply_id=s.id, received_at=s.received.isoformat(), delivery=s.delivery)])
        monkeypatch.setattr(arrival_history, "delivery_companions", lambda d: [DS])
        out = _supply_cmd(["history", "--dataset", DS])
        assert out.exit_code == 0, out.output
        assert "Run time" in out.output and "3m 12s" in out.output

    def test_the_queue_the_tui_and_the_door_offer_reject_alone_with_the_retry_hint(
            self, conn, capsys, monkeypatch):
        from cli import filing_tui

        s = Supply(conn)
        s.tries("X")
        out = _supply_cmd(["queue", "--collection", "cp"])
        assert out.exit_code == 0, out.output
        said = " ".join(out.output.split())
        assert "could not be checked -" in said and "failed in dbt-core" in said
        assert "ValueError" in said and SECRET not in said
        (state,) = [q for q in filing_queue.awaiting(conn, CP)
                    if q.state == filing_queue.COULD_NOT_CHECK]
        # THE PERIOD DOOR lists it as could not be checked, offering reject
        # alone (criterion 3).
        (entry,) = filing_queue.supplies_in(conn, state)
        assert entry.state.state == filing_queue.COULD_NOT_CHECK
        assert filing_tui.listed_words(entry).startswith("could not be checked - ")
        assert filing_queue.operations_for(entry.state) == ((filing_decisions_reject(),), ())
        # THE DECISION says the reason and the retry hint before it offers.
        asked = []
        monkeypatch.setattr(filing_tui.common, "select",
                            lambda message, choices, **k: asked.append(choices))
        filing_tui._decide_on(entry.state, offer=filing_tui._offers(
            entry.state, filing_queue.operations_for(entry.state)[0]))
        said = " ".join(capsys.readouterr().out.split())
        assert f"{s.id} could not be checked: its newest try failed in dbt-core" in said
        assert filing_queue.RETRY in said and "mothman supply failures" in said
        assert asked, "a decision was offered"

    def test_the_owed_list_says_last_try(self, capsys):
        from cli import supply as supply_cli

        supply_cli._say_owed([SimpleNamespace(
            id=1, kind="recheck", dataset_id=DS, supply_id=f"{DS}@x", period=PERIOD,
            caused_by_decision=None, last_failure="dbt fell over")])
        out = capsys.readouterr().out
        assert "last try: dbt fell over" in out and "last attempt" not in out

    def test_a_supply_owed_a_recheck_that_could_not_be_checked_is_listed_once(self, conn):
        from cli import supply as supply_cli

        s = Supply(conn)
        s.tries("X")
        waiting = [q for q in filing_queue.awaiting(conn, CP)
                   if q.state == filing_queue.COULD_NOT_CHECK]
        owed = [SimpleNamespace(dataset_id=DS, supply_id=s.id, last_failure="dbt fell over",
                                kind="recheck", caused_by_decision=None)]
        listed, still_owed = supply_cli._fold_owed_into_unchecked(waiting, owed)
        assert still_owed == []
        assert "owed re-check's last try: dbt fell over" in listed[0].reason
