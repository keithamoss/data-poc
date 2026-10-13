"""Settling a contested pair - choose-file (REQ-PIPE-193), driven against a
real PostgreSQL through the one implementation every route shares.

The pairs are Birth Registrations' (its arrival pattern admits two files
for one day, REQ-GEN-196's decision), on a random day of the coming year
so nothing else on the worker shares it.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from pair_support import DS, TABLE, Pair, _at, free_day
from qa_tools.common import dataset_blockers, decision_log, filing
from qa_tools.common import filing_decisions as fd
from qa_tools.common import (people, qa_store, recheck, rejection, settlement,
                             supersession, supply_db, supply_files)

REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-choose-file") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def actor():
    return people.person_by_email(REAL_PERSON)


@pytest.fixture
def day(conn):
    # WITHIN THE NEXT YEAR: the calendar names periods that far ahead, and a
    # daily calendar walked decades out is slow. FREE OF OTHER TESTS' PAIRS.
    return free_day(conn, date(2026, 11, 1))


def _schema_of(conn, physical):
    rows = conn.execute("SELECT table_schema FROM information_schema.tables "
                        "WHERE table_name = ?", [physical]).fetchall()
    return rows[0][0] if rows else None


def _entries(conn, supply):
    return [d for d in decision_log.decisions_for(conn, DS) if d["supply"] == supply]


def _open(conn, pair):
    return supply_files.open_contest(conn, DS, pair.pair) is not None


class TestADuplicateSend:
    """TS-68's shape: byte-identical, file one the supply, file two a spare."""

    def test_one_entry_per_file_records_and_moves(self, conn, actor, day):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:40")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:50"))])
        one, two = (n for n, _ in p.files)
        out = p.settle(conn, actor, (one, "supply"), (two, "supersede"))
        assert out.changed and len(out.owed) == 1

        (choose,) = [d for d in _entries(conn, p.pair) if d["action"] == "choose-file"]
        assert choose["actor"] and choose["reason"]
        (spare,) = [d for d in _entries(conn, p.second) if d["action"] == "supersede"]
        rows = dict(conn.execute(
            f'SELECT filename, outcome FROM "{qa_store.SCHEMA}".decision_file '
            "WHERE decision_id = ?", [choose["id"]]).fetchall())
        assert rows == {one: "supply", two: "superseded"}
        cause = conn.execute(f"SELECT caused_by_decision FROM {decision_log.TABLE} "
                             "WHERE id = ?", [spare["id"]]).fetchall()[0][0]
        assert cause == choose["id"]

        # Criteria 9 and 12: the spare is #2, kept in the period's superseded
        # schema with its own filing; the supply's file stays in staging.
        assert _schema_of(conn, p.table[two]) == supersession.superseded_schema(p.period)
        assert _schema_of(conn, p.table[one]) == supply_db.STAGING_SCHEMA
        assert filing.filing_for(DS, p.second)["slot"] == p.period
        assert supersession.is_superseded(conn, DS, p.second)
        assert not _open(conn, p)

    def test_its_receipt_unchanged_writes_no_new_filing(self, conn, actor, day):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:40")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:50"))])
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "supersede"))
        rows = conn.execute(f"SELECT count(*) FROM {filing.TABLE} WHERE dataset_id = ? "
                            "AND supply_id = ?", [DS, p.pair]).fetchall()[0][0]
        assert rows == 1


class TestALaterFileChosen:
    """TS-70's shape: the corrected re-export, received late, chosen - and
    staged FIRST by name, so `#1` is the `__1`... of the OTHER order."""

    def test_its_own_receipt_is_the_supplys_and_rejudges_it(self, conn, actor, day):
        early = f"birth_registrations_{day}.csv"
        late = f"birth_registrations_{day}-resend.csv"
        p = Pair(conn, day, [(early, _at(day, "13:40")), (late, _at(day, "16:30"))])
        before = filing.filing_for(DS, p.pair)["classification"]
        p.settle(conn, actor, (early, "reject"), (late, "supply"))

        # Criterion 10: the later file's receipt is the supply's, and its
        # verdict changes - a new filing, the old kept.
        assert filing.received_at_of(DS, p.pair) == p.files[1][1]
        after = filing.filing_for(DS, p.pair)
        assert after["slot"] == p.period and after["classification"] != before
        # Criterion 13: `#1` is the file staged `__1` here (sorted first),
        # and the rejected early file is `#2`, staged `__2`.
        assert supply_files.resolve(conn, DS, p.pair).tables == (p.table[late],)
        assert supply_files.resolve(conn, DS, p.second).tables == (p.table[early],)
        assert _schema_of(conn, p.table[early]) == supply_db.REJECTED_SCHEMA
        assert _schema_of(conn, p.table[late]) == supply_db.STAGING_SCHEMA


class TestANextDaysFileSentEarly:
    """TS-69's shape: file two re-filed to the next day - two supplies, two
    QA runs, two gates (criterion 21)."""

    def test_two_supplies_in_two_periods(self, conn, actor, day):
        nxt = day + timedelta(days=1)
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{nxt}.csv", _at(day, "13:45"))])
        one, two = (n for n, _ in p.files)
        out = p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()))
        assert len(out.owed) == 2
        assert filing.filing_for(DS, p.second)["slot"] == nxt.isoformat()
        (moved,) = [d for d in _entries(conn, p.second) if d["action"] == "refile"]
        assert (moved["from_slot"], moved["to_slot"]) == (p.period, nxt.isoformat())
        owed = {o.supply_id for o in recheck.owed(conn, DS) if o.id in out.owed}
        assert owed == {p.pair, p.second}

    def test_promoting_or_rejecting_either_moves_only_its_own_table(self, conn, actor, day):
        """Criterion 25's test, written first: once a settlement leaves two
        files staged under two supplies, a decision about either one moves
        only that supply's own table."""
        nxt = day + timedelta(days=1)
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{nxt}.csv", _at(day, "13:45"))])
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()))
        assert fd._staged(conn, DS, p.pair) == [p.table[one]]
        assert fd._staged(conn, DS, p.second) == [p.table[two]]
        fd.apply(fd.Request(operation=fd.REJECT, dataset_id=DS, actor=actor, reason="r",
                            period=nxt.isoformat(), supply=p.second),
                 effective_at=_at(nxt, "12:00").isoformat(), conn=conn)
        assert _schema_of(conn, p.table[two]) == supply_db.REJECTED_SCHEMA
        assert _schema_of(conn, p.table[one]) == supply_db.STAGING_SCHEMA


class TestNeither:
    """Criterion 26: 'reject both' is a settlement, each file's rejection
    its own entry, each undoable alone."""

    def test_both_rejected_each_its_own_entry(self, conn, actor, day):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:20")),
                              (f"birth_registrations_{day}_TEST.csv", _at(day, "13:40"))])
        one, two = (n for n, _ in p.files)
        out = p.settle(conn, actor, (one, "reject"), (two, "reject"))
        assert out.owed == ()
        assert [d["action"] for d in _entries(conn, p.pair)] == ["choose-file", "reject"]
        assert [d["action"] for d in _entries(conn, p.second)] == ["reject"]
        assert _schema_of(conn, p.table[one]) == supply_db.REJECTED_SCHEMA
        assert _schema_of(conn, p.table[two]) == supply_db.REJECTED_SCHEMA
        assert not _open(conn, p)


class TestARefusedFile:
    """Criterion 7: a file the load refused is offered only 'rejected'."""

    def _pair(self, conn, day):
        from qa_tools.common import load_log

        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}-test.csv", _at(day, "13:35"))])
        test_file = p.files[1][0]
        load_log.record(p.delivery, DS, p.table[test_file], load_log.FAILED,
                        _at(day, "13:35").isoformat(), reason="ragged")
        return p

    def test_only_rejected_is_offered(self, conn, day):
        p = self._pair(conn, day)
        _, _, files = settlement.pair_files(conn, DS, p.pair)
        assert [settlement.offered(f) for f in files] == [settlement.OUTCOMES,
                                                          (settlement.REJECT,)]

    def test_any_other_outcome_for_it_is_refused(self, conn, actor, day):
        p = self._pair(conn, day)
        one, two = (n for n, _ in p.files)
        with pytest.raises(decision_log.DecisionRefused, match="never loaded"):
            p.settle(conn, actor, (one, "reject"), (two, "supply"))

    def test_the_other_file_is_checked_on_its_own(self, conn, actor, day):
        p = self._pair(conn, day)
        one, two = (n for n, _ in p.files)
        out = p.settle(conn, actor, (one, "supply"), (two, "reject"))
        assert len(out.owed) == 1
        assert supply_files.resolve(conn, DS, p.pair).tables == (p.table[one],)


class TestTheRules:
    """Criteria 4, 5, 6 and 15: each refusal names its rule, before anything
    is written."""

    @pytest.mark.parametrize("answers, says", [
        ((("A", "supply"), ("B", "supply")), "only one file can be the supply"),
        ((("A", "reject"), ("B", "supersede")), "spare copy only where"),
        ((("A", "supply"), ("B", "refile", "SELF")), "the pair's own period"),
        ((("A", "supply"),), "none was given for"),
        ((("A", "supply"), ("nope.csv", "reject")), "not one of the pair's files"),
        ((("A", "maybe"), ("B", "reject")), "is not an outcome"),
    ])
    def test_refused(self, conn, actor, day, answers, says):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
        names = {"A": p.files[0][0], "B": p.files[1][0]}
        real = [tuple(names.get(x, p.period if x == "SELF" else x) for x in a)
                for a in answers]
        with pytest.raises(decision_log.DecisionRefused, match=says):
            p.settle(conn, actor, *real, acknowledged=None)
        assert not _entries(conn, p.pair) and _open(conn, p)

    def test_a_supply_that_is_no_open_pair_is_refused_before_asking(self, conn, actor, day):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "supersede"))
        with pytest.raises(decision_log.DecisionRefused, match="already settled, by"):
            p.settle(conn, actor, (one, "supply"), (two, "supersede"), acknowledged=None)


class TestTheWarning:
    """Criterion 17: every consequence in one panel, computed from the plan
    that applies it - and the QA runs that follow."""

    def test_it_names_the_runs_and_a_changed_verdict(self, conn, actor, day):
        early = f"birth_registrations_{day}.csv"
        late = f"birth_registrations_{day}-resend.csv"
        p = Pair(conn, day, [(early, _at(day, "13:40")), (late, _at(day, "16:30"))])
        found = fd.consequences(conn, fd.Request(
            operation=fd.CHOOSE_FILE, dataset_id=DS, actor=actor, reason="",
            period=p.period, supply=p.pair,
            file_outcomes=p.answers((early, "reject"), (late, "supply"))))
        text = "\n".join((*found.lines, *found.notes))
        assert "own receipt is the supply's" in "\n".join(found.lines)
        assert f"{late} against {p.period}" in text
        assert "promoted by the promotion gate with no further decision" in text

    def test_it_is_refused_unconfirmed(self, conn, actor, day):
        early = f"birth_registrations_{day}.csv"
        late = f"birth_registrations_{day}-resend.csv"
        p = Pair(conn, day, [(early, _at(day, "13:40")), (late, _at(day, "16:30"))])
        with pytest.raises(fd.ConsequencesNotAcknowledged):
            p.settle(conn, actor, (early, "reject"), (late, "supply"), acknowledged=None)
        assert _open(conn, p)


class TestAtomic:
    """NFR 1: a failure part-way leaves nothing recorded and nothing moved."""

    def test_a_failed_move_rolls_the_settlement_back(self, conn, actor, day, monkeypatch):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:20")),
                              (f"birth_registrations_{day}_TEST.csv", _at(day, "13:40"))])
        one, two = (n for n, _ in p.files)
        real_move = supply_db.move_table
        calls = []

        def second_fails(*a, **k):
            calls.append(a)
            if len(calls) == 2:
                raise RuntimeError("disk on fire")
            return real_move(*a, **k)

        monkeypatch.setattr(supply_db, "move_table", second_fails)
        with pytest.raises(RuntimeError):
            p.settle(conn, actor, (one, "reject"), (two, "reject"))
        assert not _entries(conn, p.pair) and not _entries(conn, p.second)
        assert _schema_of(conn, p.table[one]) == supply_db.STAGING_SCHEMA
        assert _open(conn, p)


class TestTheGitHubRouteRefusesIt:
    """Criterion 16: it appends nothing and says where in the terminal."""

    def test_a_comment_naming_it_is_refused_with_the_place(self, conn, day):
        from qa_tools.common import filing_from_github as gh

        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
        comment = gh.Comment(author="someone", body="/choose-file\nwhy",
                             slot_key=f"{DS}/{p.period}")
        with pytest.raises(decision_log.DecisionRefused) as got:
            gh.read(comment)
        text = str(got.value)
        assert supply_files.where_to_settle(DS) in text
        assert f"`{p.files[0][0]}`" in text and f"`{p.files[1][0]}`" in text
        assert not _entries(conn, p.pair)


class TestASettlementDoesNotBarAutomaticPromotion:
    """Criterion 22."""

    def test_it_is_not_a_decision_about_its_data(self, conn, actor, day):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:40")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:50"))])
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "supersede"))
        assert not rejection.decided_by_a_person(conn, DS, p.pair)


def test_the_contest_closes_at_the_settlements_instant(conn, actor, day):
    """REQ-PIPE-194 criterion 9, through the real decision."""
    p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:40")),
                          (f"birth_registrations_{day}-1.csv", _at(day, "13:50"))])
    one, two = (n for n, _ in p.files)
    when = _at(day + timedelta(days=1), "11:00")
    p.settle(conn, actor, (one, "supply"), (two, "supersede"), at=when)
    (blocker,) = [b for b in dataset_blockers.contests(conn) if b.supply == p.pair]
    assert blocker.open_at(when - timedelta(seconds=1)) and not blocker.open_at(when)



class TestASettledSupplysRuns:
    """Criterion 14: each supply's runs are its own, distinct from the other
    file's, and carry the run_index the pair's arrival recorded - never 0."""

    def test_distinct_run_ids_and_the_arrivals_run_index(self, conn, actor, day):
        nxt = day + timedelta(days=1)
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{nxt}.csv", _at(day, "13:45"))])
        one, two = (n for n, _ in p.files)
        out = p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()))
        first = recheck.mint_run_id(conn, DS, p.pair, owed_id=out.owed[0])
        second = recheck.mint_run_id(conn, DS, p.second, owed_id=out.owed[1])
        assert first != second
        assert first.startswith(f"birth_registrations__{p.key}__1__r")
        arrival = supply_files.arrival_run_id_of(DS, p.second)
        assert arrival == f"birth_registrations__{p.key}"
        conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".run (run_key, agency_id, collection_id, '
                     "run_timestamp, run_instant) VALUES (?, 'a', 'c', ?, now()) "
                     "ON CONFLICT DO NOTHING", [arrival, _at(day, "13:30").isoformat()])
        conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".dataset_stats (run_key, dataset_id, '
                     "stats) VALUES (?, ?, ?::jsonb)",
                     [arrival, DS, '{"arrival_record": {"run_index": 41}}'])
        assert recheck._run_index_of(arrival) == 41


class TestTheRunsAfterASettlement:
    """Criterion 20: a run that fails says the settlement is recorded and the
    run owed - finished by 'Process what has arrived' - never to settle
    again; and one panel ends it."""

    def test_a_failed_run_is_said_owed(self, monkeypatch, capsys):
        from cli import settle_tui

        def boom(owed_id, on_step=None):
            raise RuntimeError("dbt fell over")

        monkeypatch.setattr(recheck, "run", boom)
        outcome = fd.Outcome(operation=fd.CHOOSE_FILE, dataset_id=DS, period="P",
                             changed=True, message="m", owed=(7,))
        got = settle_tui._run_what_it_owed(outcome, [("a.csv", "P")], "P")
        import re

        text = re.sub(r"[\s│╭╮╰╯─]+", " ", capsys.readouterr().out)
        assert got == {"a.csv": "not checked yet - owed"}
        assert "run 1 of 1 - a.csv for P" in text
        assert "The settlement is recorded" in text and "Process what has arrived" in text
        assert "settle again" not in text and "settle it" not in text


class TestCriticFindingsOn193:
    """post-build-review #170 - each failed before its fix."""

    def _pair(self, conn, day, second="-resend", at=("13:40", "13:50")):
        return Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, at[0])),
                                (f"birth_registrations_{day}{second}.csv", _at(day, at[1]))])

    def test_the_runs_are_listed_but_need_no_key(self, conn, actor, day):
        """Keith: every settlement owes runs, so listing them is not a side
        effect to acknowledge - a plain supply + reject goes through with
        --yes alone."""
        p = self._pair(conn, day)
        one, two = (n for n, _ in p.files)
        found = fd.consequences(conn, fd.Request(
            operation=fd.CHOOSE_FILE, dataset_id=DS, actor=actor, reason="r",
            period=p.period, supply=p.pair,
            file_outcomes=p.answers((one, "supply"), (two, "reject"))))
        assert found.key == ""
        assert any(f"{one} against {p.period}" in n for n in found.notes)
        assert p.settle(conn, actor, (one, "supply"), (two, "reject"),
                        acknowledged=None).changed

    def test_a_refile_into_a_period_holding_an_open_pair_is_refused(self, conn, actor, day):
        """Keith: as the plain supersede of an open pair is (criterion 25)."""
        nxt = day + timedelta(days=1)
        other = self._pair(conn, nxt)
        p = self._pair(conn, day)
        one, two = (n for n, _ in p.files)
        with pytest.raises(decision_log.DecisionRefused, match="two files") as got:
            p.settle(conn, actor, (one, "supply"), (two, "refile", other.period),
                     acknowledged=None)
        for name, _ in other.files:
            assert name in str(got.value)
        assert _open(conn, other) and _open(conn, p)

    def test_a_rejected_file_is_promoted_back(self, conn, actor, day):
        """Criteria 3 and 26, and REQ-PIPE-075 criterion 9: a rejection is
        reversed by promoting the supply back, from the rejected schema."""
        p = self._pair(conn, day)
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "reject"), (two, "reject"))
        request = fd.Request(operation=fd.PROMOTE, dataset_id=DS, actor=actor,
                             reason="it was the right file after all", period=p.period,
                             supply=p.second, confirmed=True)
        request = fd.Request(**{**request.__dict__,
                                "acknowledged": fd.consequences(conn, request).key or None})
        fd.apply(request, effective_at=_at(day + timedelta(days=2), "10:00").isoformat(),
                 conn=conn)
        assert decision_log.held(conn, DS, p.period).holder == p.second
        assert _schema_of(conn, p.table[two]) != supply_db.REJECTED_SCHEMA
        assert _schema_of(conn, p.table[one]) == supply_db.REJECTED_SCHEMA

    def test_a_later_file_chosen_is_found_by_its_own_receipt(self, conn, actor, day):
        """Criterion 13: the dashboard finds a run's arrival by the receipt
        the run records, which for a settled supply is its own file's."""
        early = f"birth_registrations_{day}.csv"
        late = f"birth_registrations_{day}-resend.csv"
        p = Pair(conn, day, [(early, _at(day, "13:40")), (late, _at(day, "16:30"))])
        p.settle(conn, actor, (early, "reject"), (late, "supply"))
        received = p.files[1][1]
        assert filing.period_of(DS, received) == p.period
        assert filing.recorded_arrival_at(DS, received).supply_id == p.pair

    def test_a_refiled_second_file_is_found_by_its_own_receipt(self, conn, actor, day):
        nxt = day + timedelta(days=1)
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{nxt}.csv", _at(day, "13:45"))])
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()))
        assert filing.period_of(DS, p.files[1][1]) == nxt.isoformat()
        assert filing.period_of(DS, p.files[0][1]) == p.period

    def test_a_version_a_settlement_displaces_names_it_as_the_cause(self, conn, actor, day):
        """Criterion 8: every entry a settlement makes names it."""
        nxt = day + timedelta(days=1)
        waiting = self._pair(conn, nxt)
        w1, w2 = (n for n, _ in waiting.files)
        waiting.settle(conn, actor, (w1, "supply"), (w2, "reject"))
        p = self._pair(conn, day)
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()))
        (choose,) = [d for d in _entries(conn, p.pair) if d["action"] == "choose-file"]
        (displaced,) = [d for d in _entries(conn, waiting.pair) if d["action"] == "supersede"]
        cause = conn.execute(f"SELECT caused_by_decision FROM {decision_log.TABLE} "
                             "WHERE id = ?", [displaced["id"]]).fetchall()[0][0]
        assert cause == choose["id"]

    def _hold(self, conn, supply):
        from qa_tools.common import supply_holds

        supply_holds.raise_hold(conn, dataset_id=DS, supply_id=supply,
                                kind=supply_holds.ASSIGNMENT_RULE,
                                reason={"unavailable": []}, raised_by="pytest")

    def test_a_decision_about_one_file_leaves_the_other_files_hold(self, conn, day):
        """Criterion 13: a hold is one supply's, never its arrival's."""
        from qa_tools.common import supply_holds

        p = self._pair(conn, day)
        self._hold(conn, p.pair)
        assert supply_holds.resolve_for_supply(conn, dataset_id=DS, supply=p.second,
                                               decision_id=1) == ()
        assert p.pair in {h.supply_id for h in supply_holds.outstanding(conn, dataset_id=DS)}

    def test_one_files_hold_does_not_withhold_the_other_files_run(self, conn, day):
        from qa_tools.common import supply_holds

        p = self._pair(conn, day)
        self._hold(conn, p.pair)
        assert TABLE not in supply_holds.held_tables(conn, arrival_key=p.key,
                                                     supply=p.second)
        assert TABLE in supply_holds.held_tables(conn, arrival_key=p.key, supply=p.pair)
        assert TABLE in supply_holds.held_tables(conn, arrival_key=p.key)


class TestTheSlotNamesItsTwoFiles:
    """REQ-PIPE-194 criterion 2: the slot state the ticket reads carries
    the pair's files, from the same open-contest judgement."""

    def test_states_for_carries_the_files(self, conn, day):
        from qa_tools.common import slot_state

        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:40")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:50"))])
        (state,) = [s for s in slot_state.states_for(conn, "civil-registration")
                    if s.dataset_id == DS and s.period == p.period]
        assert state.state == slot_state.TWO_FILES
        assert set(state.files) == {n for n, _ in p.files}


class TestTheBlockerRecordsItsSettlement:
    """REQ-PIPE-194 criteria 10 and 13: what the page draws the settled row
    and each settled supply's note from - recorded metadata only."""

    def test_who_when_why_and_each_file_in_receipt_order(self, conn, actor, day):
        nxt = day + timedelta(days=1)
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{nxt}.csv", _at(day, "13:45"))])
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()))
        (blocker,) = [b for b in dataset_blockers.contests(conn) if b.supply == p.pair]
        got = blocker.as_record()["settlement"]
        assert got["actor"] == people.display_name(REAL_PERSON) != REAL_PERSON
        assert got["reason"] == "the supplier sent it twice"
        assert got["at"] == blocker.resolved_at
        assert [(f["filename"], f["outcome"], f["toPeriod"]) for f in got["files"]] == [
            (one, "supply", None), (two, "refiled", nxt.isoformat())]
        assert [f["supplyId"] for f in got["files"]] == [p.pair, p.second]
        assert got["files"][1]["runId"] == supply_files.run_id_of(DS, p.second)
        assert got["arrivalRunId"] == supply_files.arrival_run_id_of(DS, p.pair)
        assert all(f["receivedAt"] for f in got["files"])

    def test_an_open_pair_has_none(self, conn, day):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "13:45"))])
        (blocker,) = [b for b in dataset_blockers.contests(conn) if b.supply == p.pair]
        assert blocker.as_record()["settlement"] is None


class TestCriticFindingsOn194:
    """post-build-review #171 - each failed before its fix."""

    def _promoted_then_a_pair(self, conn, actor, day):
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "09:30")),
                              (f"birth_registrations_{day}-1.csv", _at(day, "09:45"))])
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "reject"))
        promote = fd.Request(operation=fd.PROMOTE, dataset_id=DS, actor=actor, reason="r",
                             period=p.period, supply=p.pair, confirmed=True)
        promote = fd.Request(**{**promote.__dict__,
                                "acknowledged": fd.consequences(conn, promote).key or None})
        fd.apply(promote, effective_at=_at(day, "12:00").isoformat(), conn=conn)
        q = Pair(conn, day, [(f"birth_registrations_{day}-again.csv", _at(day, "15:30")),
                              (f"birth_registrations_{day}-again-1.csv", _at(day, "15:45"))])
        assert supply_files.open_contest(conn, DS, q.pair) is not None
        return p, q

    def test_a_pair_over_a_promoted_period_reads_two_files(self, conn, actor, day):
        """Criteria 2 and 4: the slot is TWO_FILES - settled, not offered
        promote, reject or supersede, each of which is refused."""
        from qa_tools.common import filing_queue, slot_state

        p, q = self._promoted_then_a_pair(conn, actor, day)
        (state,) = [s for s in slot_state.states_for(conn, "civil-registration")
                    if s.dataset_id == DS and s.period == p.period]
        assert state.state == slot_state.TWO_FILES
        assert set(state.files) == {n for n, _ in q.files}
        waiting = [s for s in filing_queue.awaiting(conn, "civil-registration")
                   if s.dataset_id == DS and s.period == p.period]
        assert [filing_queue.operations_for(s)[0] for s in waiting] == [(fd.CHOOSE_FILE,)]

    def test_a_refiled_file_sharing_its_pairs_receipt_is_found_as_itself(
            self, conn, actor, day):
        """#171 B: every multi-file delivery in the bootstrap shares one
        receipt instant, so a re-filed file's runs were found as the other
        file's arrival - its row in the wrong period. The run names its
        supply (recheck's purpose); the build reads it."""
        from pipeline import recorded_arrival

        nxt = day + timedelta(days=1)
        p = Pair(conn, day, [(f"birth_registrations_{day}.csv", _at(day, "13:30")),
                              (f"birth_registrations_{nxt}.csv", _at(day, "13:30"))])
        one, two = (n for n, _ in p.files)
        p.settle(conn, actor, (one, "supply"), (two, "refile", nxt.isoformat()))
        received = filing.received_at_of(DS, p.second)
        assert recorded_arrival.for_run(DS, received, supply=p.second)["slot"] == nxt.isoformat()
        assert recorded_arrival.for_run(DS, received, supply=p.pair)["slot"] == p.period
