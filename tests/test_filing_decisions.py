"""One implementation of every filing decision (REQ-GHUB-082 criterion
13), driven against a real PostgreSQL.

WHY THIS MODULE EXISTS AT ALL is criterion 3: the two operator routes
SHALL write an identical entry and SHALL NOT give either an operation
the other lacks. That is not something two implementations can be held
to by testing both; it is something ONE implementation makes true. So
these tests drive the shared call directly - the routes, when they
exist, are adapters that decide only who is asking and what they asked
for.
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import (filing_decisions as fd, hierarchy, inheritance,
                              people, period_schema, promotion, qa_store,
                              schedule, substitution, supply_db)

WHEN = "2026-09-29T09:00:00+08:00"
REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-filing-decisions") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def actor():
    return people.person_by_email(REAL_PERSON)


@pytest.fixture
def dataset():
    """A REAL dataset, so its table name and agency are real."""
    return hierarchy.dataset("cp-carers")


@pytest.fixture
def periods(monkeypatch):
    tag = uuid.uuid4().hex[:6]
    names = (f"2099-P{tag}", f"2099-Q{tag}")
    from datetime import date
    order = {names[0]: date(2099, 1, 1), names[1]: date(2099, 4, 1)}
    for mod in (schedule, inheritance.schedule):
        monkeypatch.setattr(mod, "date_of", lambda name, ds: order.get(name))
    return names


def _stage(conn, dataset, arrival=None):
    """A real staged supply, whose ID and TABLE are different strings -
    as they are in the real system, and as a test that conflated them
    hid a defect for an hour on 2026-09-29."""
    arrival = arrival or uuid.uuid4().hex[:10]
    physical = f"{dataset.table}__{arrival}"
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    conn.execute(f'CREATE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" (id integer)')
    conn.execute(f'INSERT INTO "{supply_db.STAGING_SCHEMA}"."{physical}" VALUES (7)')
    return f"{dataset.dataset_id}@{arrival}", physical


def _entry_for(conn, dataset_id, period, action=None):
    """This period's own decision-log entry, newest first match.

    NEVER `decisions_for(...)[-1]`, and this helper exists because that
    spelling broke CI three times in one day. These tests act on a REAL
    dataset id - `cp-carers`, because the fixture needs a real table and
    agency - while minting a period of their own. Every other module
    touching cp-carers on the same xdist worker writes into the same
    log, so the NEWEST entry for the dataset is routinely somebody
    else's: a promotion the rule made, or a reason another test typed.

    It is also not deterministic, which is what made it expensive: which
    module shares a worker depends on how pytest-xdist distributes
    files, so the same code went green once and red twice.
    """
    matches = [e for e in dl.decisions_for(conn, dataset_id)
                if period in (e.get("to_slot"), e.get("from_slot"))
                and (action is None or e["action"] == action)]
    assert matches, f"no {action or 'decision'} recorded for {dataset_id} {period}"
    return matches[-1]


def _request(dataset, actor, operation, **kw):
    kw.setdefault("reason", "because I looked at it")
    return fd.Request(operation=operation, dataset_id=dataset.dataset_id,
                       actor=actor, **kw)


class TestTheEightAreOneList:
    """Criterion 3's second half - neither route may have an operation
    the other lacks, which is a property of there being one list."""

    def test_every_operation_is_a_real_decision_log_action(self):
        for operation in fd.OPERATIONS:
            assert operation in dl.ACTIONS, operation

    def test_there_are_twelve_of_them(self):
        """Eight, and REQ-PIPE-132's mark as not supplied (2026-10-05)."""
        assert len(set(fd.OPERATIONS)) == 12
        assert fd.MARK_NOT_SUPPLIED in fd.PERIOD_SCOPED

    def test_supply_scoped_and_period_scoped_partition_them(self):
        """Criterion 31: none of the four period-scoped ones answers
        "what do I do with this arriving supply", which is why they are
        reached somewhere else entirely."""
        assert set(fd.SUPPLY_SCOPED) | set(fd.PERIOD_SCOPED) == set(fd.OPERATIONS)
        assert not set(fd.SUPPLY_SCOPED) & set(fd.PERIOD_SCOPED)

    def test_something_that_is_not_one_is_refused_by_name(self):
        with pytest.raises(fd.NotOffered) as exc:
            fd.offered("delete")
        assert "promote" in str(exc.value), "the refusal should say what IS offered"


class TestWhoMayRaiseOne:
    """Criteria 6, 14 and 27."""

    def test_a_decision_with_no_actor_at_all_is_refused(self, dataset):
        with pytest.raises(people.UnknownActor):
            fd.apply(fd.Request(operation=fd.PROMOTE, dataset_id=dataset.dataset_id,
                                 actor={}, reason="r", period="2099-X"),
                      effective_at=WHEN)

    def test_the_actor_written_to_the_log_is_the_person(
            self, conn, dataset, actor, periods):
        first, _ = periods
        supply, physical = _stage(conn, dataset)
        fd.apply(_request(dataset, actor, fd.PROMOTE, period=first, supply=supply),
                  effective_at=WHEN, conn=conn)
        entry = _entry_for(conn, dataset.dataset_id, first, dl.PROMOTE)
        assert entry["actor"] == REAL_PERSON
        assert entry["actor_kind"] == dl.PERSON, (
            "a person's decision is never recorded as the rule's")
        assert physical  # the staged table really existed


class TestAReasonIsRequired:
    """Criterion 10, and it is stricter than the decision log's own
    rule - that one asks for a reason where somebody will ask why a year
    later and lets a routine automatic promotion go without. This is
    about a PERSON: they are here, deciding on purpose."""

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_it_is_refused_without_one(self, conn, dataset, actor, periods, blank):
        first, _ = periods
        supply, _ = _stage(conn, dataset)
        request = fd.Request(operation=fd.PROMOTE, dataset_id=dataset.dataset_id,
                              actor=actor, reason=blank, period=first, supply=supply)
        with pytest.raises(dl.DecisionRefused) as exc:
            fd.apply(request, effective_at=WHEN, conn=conn)
        assert "needs a reason" in str(exc.value)
        assert dl.promoted_into(conn, dataset.dataset_id, first) is None, \
            "a refused decision must leave the warehouse alone"


class TestTheDestructiveOnesAreConfirmed:
    """Criteria 9 and 28, refused here as well as by the operation - so
    a route that forgot to ask gets the same answer wherever it
    forgot."""

    @pytest.mark.parametrize("operation", fd.NEEDS_CONFIRMATION)
    def test_an_unconfirmed_one_is_refused(self, conn, dataset, actor, periods,
                                            operation):
        first, _ = periods
        with pytest.raises(dl.DecisionRefused) as exc:
            fd.apply(_request(dataset, actor, operation, period=first),
                      effective_at=WHEN, conn=conn)
        assert "confirmation" in str(exc.value)

    def test_the_other_five_need_none(self):
        assert not set(fd.NEEDS_CONFIRMATION) - set(fd.OPERATIONS)
        assert fd.PROMOTE not in fd.NEEDS_CONFIRMATION


class TestSevenOfTheEightReallyWork:
    """The decisions, end to end, against a real database.

    DRIVEN AS A SEQUENCE where the operations depend on each other,
    because that is how an operator meets them: a supply is promoted
    before it can be demoted, and a period inherits before it can be
    un-inherited.
    """

    def test_promote_moves_the_tables_and_records_it(
            self, conn, dataset, actor, periods):
        first, _ = periods
        supply, physical = _stage(conn, dataset)

        got = fd.apply(_request(dataset, actor, fd.PROMOTE, period=first,
                                 supply=supply), effective_at=WHEN, conn=conn)

        assert got.changed is True
        assert dl.promoted_into(conn, dataset.dataset_id, first) == supply
        held = period_schema.promoted_in(conn, first, [dataset.table])
        assert physical in (held.get(dataset.table) or [])

    def test_demote_puts_it_back_and_leaves_the_slot_unfilled(
            self, conn, dataset, actor, periods):
        first, _ = periods
        supply, _ = _stage(conn, dataset)
        fd.apply(_request(dataset, actor, fd.PROMOTE, period=first, supply=supply),
                  effective_at=WHEN, conn=conn)

        got = fd.apply(_request(dataset, actor, fd.DEMOTE, period=first,
                                 supply=supply), effective_at=WHEN, conn=conn)

        assert got.changed is True
        assert dl.promoted_into(conn, dataset.dataset_id, first) is None

    def test_reject_moves_a_staged_supply_out_of_the_way(
            self, conn, dataset, actor, periods):
        first, _ = periods
        supply, physical = _stage(conn, dataset)

        got = fd.apply(_request(dataset, actor, fd.REJECT, period=first,
                                 supply=supply), effective_at=WHEN, conn=conn)

        assert got.changed is True
        entry = _entry_for(conn, dataset.dataset_id, first, dl.REJECT)
        assert entry["action"] == dl.REJECT
        staged = supply_db.candidates_in(
            conn, supply_db.STAGING_SCHEMA, [dataset.table],
            arrival=supply.rsplit("@", 1)[1]).get(dataset.table) or []
        assert physical not in staged, "a rejected supply stays in staging"

    def test_substitute_then_de_substitute(self, conn, dataset, actor, periods):
        first, second = periods
        supply, _ = _stage(conn, dataset)
        fd.apply(_request(dataset, actor, fd.PROMOTE, period=first, supply=supply),
                  effective_at=WHEN, conn=conn)
        period_schema.ensure_period_schema(conn, second)

        fd.apply(_request(dataset, actor, fd.SUBSTITUTE, period=second,
                           stands_on=first, supply=supply),
                  effective_at=WHEN, conn=conn)
        assert substitution.substituted(conn, dataset.dataset_id, second) is not None

        fd.apply(_request(dataset, actor, fd.DE_SUBSTITUTE, period=second,
                           confirmed=True), effective_at=WHEN, conn=conn)
        assert substitution.substituted(conn, dataset.dataset_id, second) is None

    def test_inherit_then_un_inherit(self, conn, dataset, actor, periods,
                                      monkeypatch):
        first, second = periods
        monkeypatch.setattr(
            inheritance.schedule, "not_expected_periods",
            lambda ds: {second: "carers are annual"} if ds == dataset.dataset_id else {})
        supply, _ = _stage(conn, dataset)
        fd.apply(_request(dataset, actor, fd.PROMOTE, period=first, supply=supply),
                  effective_at=WHEN, conn=conn)
        period_schema.ensure_period_schema(conn, second)

        fd.apply(_request(dataset, actor, fd.INHERIT, period=second),
                  effective_at=WHEN, conn=conn)
        assert inheritance.inherited(conn, dataset.dataset_id, second) is not None

        fd.apply(_request(dataset, actor, fd.UN_INHERIT, period=second,
                           confirmed=True), effective_at=WHEN, conn=conn)
        assert inheritance.inherited(conn, dataset.dataset_id, second) is None

    def test_refile_says_it_is_unbuilt_rather_than_doing_something_wrong(
            self, conn, dataset, actor, periods):
        """The one of the eight with no effect written. filing.refile()
        moves the FILING RECORD and writes no decision-log entry, and
        what happens to a PROMOTED supply's tables on a re-file is
        REQ-PIPE-079's wiring. Inventing it in the dispatcher would put
        the answer in the one place nobody would look for it - so it
        refuses, loudly, naming why."""
        first, _ = periods
        supply, _ = _stage(conn, dataset)
        with pytest.raises(fd.NotOffered) as exc:
            fd.apply(_request(dataset, actor, fd.REFILE, period=first,
                               supply=supply, confirmed=True),
                      effective_at=WHEN, conn=conn)
        assert "REQ-PIPE-079" in str(exc.value)
        assert "other seven operations work" in str(exc.value)


class TestADecisionThatChangesNothingSaysSo:
    """Criterion 26, and the reason it matters: an operator arriving at
    a state that already holds happens constantly when two people look
    at the same ticket. Reporting it as a failure teaches them to ignore
    failures."""

    def test_promoting_what_is_already_promoted(self, conn, dataset, actor, periods):
        first, _ = periods
        supply, _ = _stage(conn, dataset)
        fd.apply(_request(dataset, actor, fd.PROMOTE, period=first, supply=supply),
                  effective_at=WHEN, conn=conn)
        before = len(dl.decisions_for(conn, dataset.dataset_id))

        got = fd.apply(_request(dataset, actor, fd.PROMOTE, period=first,
                                 supply=supply), effective_at=WHEN, conn=conn)

        assert got.changed is False
        assert "already promoted" in got.message
        assert len(dl.decisions_for(conn, dataset.dataset_id)) == before, \
            "a no-op must not append a duplicate entry"

    def test_de_substituting_a_period_that_holds_no_substitution(
            self, conn, dataset, actor, periods):
        _first, second = periods
        got = fd.apply(_request(dataset, actor, fd.DE_SUBSTITUTE, period=second,
                                 confirmed=True), effective_at=WHEN, conn=conn)
        assert got.changed is False
        assert "no substitution" in got.message

    def test_un_inheriting_a_period_that_never_inherited(
            self, conn, dataset, actor, periods):
        _first, second = periods
        got = fd.apply(_request(dataset, actor, fd.UN_INHERIT, period=second,
                                 confirmed=True), effective_at=WHEN, conn=conn)
        assert got.changed is False
        assert "no inheritance" in got.message

    def test_but_un_inheriting_a_SUBSTITUTION_is_a_real_refusal(
            self, conn, dataset, actor, periods):
        """The two are identical in SQL and opposite in meaning. The
        operator has asked to undo the wrong one, which is a thing to
        tell them rather than a state that already holds."""
        first, second = periods
        supply, _ = _stage(conn, dataset)
        fd.apply(_request(dataset, actor, fd.PROMOTE, period=first, supply=supply),
                  effective_at=WHEN, conn=conn)
        period_schema.ensure_period_schema(conn, second)
        fd.apply(_request(dataset, actor, fd.SUBSTITUTE, period=second,
                           stands_on=first, supply=supply),
                  effective_at=WHEN, conn=conn)

        with pytest.raises(inheritance.InheritanceRefused) as exc:
            fd.apply(_request(dataset, actor, fd.UN_INHERIT, period=second,
                               confirmed=True), effective_at=WHEN, conn=conn)
        assert "SUBSTITUTION" in str(exc.value)


class TestTheFilingRulesAreJudgedWhenTheEntryIsAppended:
    """Criteria 20, 21 and 24. The judgement is NOT in this module, and
    that is the design: whether a later period stands on a supply is a
    fact about other rows, and an operator who was shown the state a
    moment ago may be wrong by now."""

    def test_a_demotion_is_refused_and_names_the_remedy(
            self, conn, dataset, actor, periods, monkeypatch):
        first, second = periods
        monkeypatch.setattr(
            inheritance.schedule, "not_expected_periods",
            lambda ds: {second: "carers are annual"} if ds == dataset.dataset_id else {})
        supply, _ = _stage(conn, dataset)
        fd.apply(_request(dataset, actor, fd.PROMOTE, period=first, supply=supply),
                  effective_at=WHEN, conn=conn)
        period_schema.ensure_period_schema(conn, second)
        fd.apply(_request(dataset, actor, fd.INHERIT, period=second),
                  effective_at=WHEN, conn=conn)

        with pytest.raises(dl.DecisionRefused) as exc:
            fd.apply(_request(dataset, actor, fd.DEMOTE, period=first,
                               supply=supply), effective_at=WHEN, conn=conn)

        # Criterion 25: the remedy, not just the obstacle.
        assert second in str(exc.value)
        assert dl.UN_INHERIT in str(exc.value)
        assert dl.promoted_into(conn, dataset.dataset_id, first) == supply, \
            "a refused decision leaves the warehouse exactly as it was"

    def test_the_refusal_is_the_LOGS_rather_than_this_modules(
            self, conn, dataset, actor, periods, monkeypatch):
        """Criterion 24 holds by construction rather than by agreement:
        there is one implementation, so there is one place for the two
        routes to agree - and the judgement is not even in it. Driven by
        asking the operation DIRECTLY and through `apply`, and requiring
        the same exception with the same words from both."""
        first, second = periods
        monkeypatch.setattr(
            inheritance.schedule, "not_expected_periods",
            lambda ds: {second: "carers are annual"} if ds == dataset.dataset_id else {})
        supply, physical = _stage(conn, dataset)
        fd.apply(_request(dataset, actor, fd.PROMOTE, period=first, supply=supply),
                  effective_at=WHEN, conn=conn)
        period_schema.ensure_period_schema(conn, second)
        fd.apply(_request(dataset, actor, fd.INHERIT, period=second),
                  effective_at=WHEN, conn=conn)

        from qa_tools.common import rejection

        with pytest.raises(dl.DecisionRefused) as direct:
            rejection.demote(
                conn, agency_id=dataset.agency_id,
                collection_id=dataset.collection_id, dataset_id=dataset.dataset_id,
                supply=supply, physical_tables=[physical], actor="someone",
                effective_at=WHEN, reason="r", from_slot=first)
        with pytest.raises(dl.DecisionRefused) as through:
            fd.apply(_request(dataset, actor, fd.DEMOTE, period=first,
                               supply=supply), effective_at=WHEN, conn=conn)

        assert str(direct.value) == str(through.value)

    def test_a_supersession_is_permitted_WITH_a_reason_and_recorded_as_one(
            self, conn, dataset, actor, periods):
        """The log's own rule, not this module's: promoting over a
        supply already in the slot needs a reason, and a person raising
        a decision has always given one. So it goes through - and the
        entry carries the why, which is the whole point of demanding
        it."""
        first, _ = periods
        theirs, theirs_physical = _stage(conn, dataset)
        promotion.promote(
            conn, agency_id=dataset.agency_id, collection_id=dataset.collection_id,
            dataset_id=dataset.dataset_id, supply=theirs, period=first,
            physical_tables=[theirs_physical], actor="someone",
            actor_kind=dl.PERSON, effective_at=WHEN)
        mine, _ = _stage(conn, dataset)

        got = fd.apply(
            fd.Request(operation=fd.PROMOTE, dataset_id=dataset.dataset_id,
                        actor=actor, period=first, supply=mine,
                        reason="theirs was the wrong extract"),
            effective_at=WHEN, conn=conn)

        assert got.changed is True
        assert dl.promoted_into(conn, dataset.dataset_id, first) == mine
        assert _entry_for(conn, dataset.dataset_id, first,
                           dl.PROMOTE)["reason"] == \
            "theirs was the wrong extract"


class TestTheTicketIsReconciledByTheOnePass:
    """Criterion 8. A decision taken in the terminal appears on its
    ticket the same way one raised on the ticket does - said once and in
    the same words - which is a property of there being one writer."""

    def test_a_no_op_reconciles_nothing(self, monkeypatch):
        called = []
        import qa_tools.common.ticket_reconciler as tr
        monkeypatch.setattr(tr, "after_runs", lambda *a, **k: called.append(1))
        fd.reconcile_after(
            fd.Outcome(operation=fd.PROMOTE, dataset_id="d", period="p",
                        changed=False, message="already"),
            "child-protection")
        assert called == [], (
            "a no-op leaves the log as the last pass found it, so the pass "
            "would correctly say nothing - running it is work to produce silence")

    def test_an_unreachable_ticket_service_never_loses_the_decision(self, monkeypatch):
        """The entry is committed by the time this runs. A ticket a pass
        behind is fixed by the next pass; a lost decision is not."""
        import qa_tools.common.ticket_reconciler as tr

        def _boom(*a, **k):
            raise RuntimeError("gh: not found")

        monkeypatch.setattr(tr, "after_runs", _boom)
        fd.reconcile_after(
            fd.Outcome(operation=fd.PROMOTE, dataset_id="d", period="p",
                        changed=True, message="done"),
            "child-protection")


class TestRejectingASupplyThatNeverLoaded:
    """post-build-review #80's reproduction, REQ-PIPE-153 criterion 14: the
    failed-load item offers "reject the supply", and a failed load has no
    table to move. The rejection was ACCEPTED and the item stayed open, so
    the person was told it was recorded and then asked again."""

    def _failed(self, conn, dataset):
        from qa_tools.common import load_log

        arrival = uuid.uuid4().hex[:10]
        physical = f"{dataset.table}__{arrival}"
        load_log.record(f"probe-{arrival}", dataset.dataset_id, physical,
                        load_log.FAILED, "2026-09-29T08:00:00+08:00",
                        reason="malformed row: line 3 has 4 fields where 2 were expected",
                        conn=conn)
        return arrival, physical

    def test_it_is_accepted_and_the_failed_load_leaves_the_queue(
            self, conn, dataset, actor, periods):
        from qa_tools.common import load_log, outstanding

        first, _ = periods
        arrival, physical = self._failed(conn, dataset)
        assert physical in {r.physical for r in load_log.failures(conn=conn)}
        before = [r for r in load_log.records(conn=conn) if r.physical == physical]

        got = fd.apply(_request(dataset, actor, fd.REJECT, period=first,
                                 supply=f"{dataset.dataset_id}@{arrival}"),
                        effective_at=WHEN, conn=conn)

        assert got.changed is True
        assert physical not in {r.physical for r in load_log.failures(conn=conn)}, \
            "a rejected failed load is still offered for a decision"
        assert not [i for i in outstanding.survey(conn).items
                    if i.kind == outstanding.FAILED_LOAD and physical in i.headline]
        after = [r for r in load_log.records(conn=conn) if r.physical == physical]
        assert after == before, "a rejection writes nothing to the load record (criterion 3)"

    def test_the_item_still_reads_open_before_the_rejection_took_effect(
            self, conn, dataset, actor, periods):
        """Criterion 2: open from receipt, closed from the rejection."""
        from datetime import datetime, timedelta

        from qa_tools.common import dataset_blockers

        first, _ = periods
        arrival, physical = self._failed(conn, dataset)
        fd.apply(_request(dataset, actor, fd.REJECT, period=first,
                           supply=f"{dataset.dataset_id}@{arrival}"),
                  effective_at=WHEN, conn=conn)
        (b,) = [b for b in dataset_blockers.all_blockers(conn)
                if b.kind == dataset_blockers.REFUSED and b.supply.endswith(arrival)]
        rejected_at = datetime.fromisoformat(WHEN)
        assert b.rejected and b.rejected["actor"]
        assert b.open_at(rejected_at - timedelta(minutes=1))
        assert not b.open_at(rejected_at)


class TestAReloadAfterARejectionIsNotPromotedAutomatically:
    """REQ-PIPE-153 criterion 11: the rejection stands, and the automatic
    gate defers to it for the supply's whole life (REQ-PIPE-076
    criterion 7)."""

    def test_the_gate_sees_the_persons_rejection(self, conn, dataset, actor, periods):
        from qa_tools.common import load_log, rejection

        first, _ = periods
        arrival = uuid.uuid4().hex[:10]
        physical = f"{dataset.table}__{arrival}"
        load_log.record(f"probe-{arrival}", dataset.dataset_id, physical,
                        load_log.FAILED, WHEN, reason="the file is empty", conn=conn)
        supply = f"{dataset.dataset_id}@{arrival}"
        fd.apply(_request(dataset, actor, fd.REJECT, period=first, supply=supply),
                  effective_at=WHEN, conn=conn)
        load_log.record(f"probe-{arrival}", dataset.dataset_id, physical,
                        load_log.LOADED, "2026-09-30T09:00:00+08:00", row_count=3, conn=conn)
        assert rejection.decided_by_a_person(conn, dataset.dataset_id, supply)


class TestPromotingASupplyThatNeverLoaded:
    """REQ-PIPE-153 criterion 6: promoting a supply whose current load
    record is failed is refused on every route - promotion would move the
    tables it is given, which is none, and record a period filled by a
    supply nothing can read."""

    def test_it_is_refused_naming_the_failed_load_and_records_nothing(
            self, conn, dataset, actor, periods):
        from qa_tools.common import load_log

        first, _ = periods
        arrival = uuid.uuid4().hex[:10]
        load_log.record(f"probe-{arrival}", dataset.dataset_id,
                        f"{dataset.table}__{arrival}", load_log.FAILED, WHEN,
                        reason="the file is empty", conn=conn)
        with pytest.raises(dl.DecisionRefused, match="could not be loaded.*the file is empty"):
            fd.apply(_request(dataset, actor, fd.PROMOTE, period=first,
                               supply=f"{dataset.dataset_id}@{arrival}"),
                      effective_at=WHEN, conn=conn)
        assert not [e for e in dl.decisions_for(conn, dataset.dataset_id)
                    if e.get("to_slot") == first]


class TestTheQueueListsWhatCouldNotBeLoaded:
    """REQ-PIPE-153 criteria 5 and 12."""

    def _failed(self, conn, dataset, *, filed_to=None):
        import filing_support
        from qa_tools.common import assignment, load_log

        arrival = f"t{uuid.uuid4().hex[:10]}"
        load_log.record(f"probe-{arrival}", dataset.dataset_id, f"{dataset.table}__{arrival}",
                        load_log.FAILED, WHEN, reason="the file is empty", conn=conn)
        if filed_to:
            filing_support.file(assignment.Assignment(
                dataset_id=dataset.dataset_id, supply_id=f"{dataset.dataset_id}@{arrival}",
                slot=filed_to, branch=assignment.OPEN_UNFILLED, considered=(filed_to,)))
        return f"{dataset.dataset_id}@{arrival}"

    def test_a_filed_failed_load_is_listed_offering_reject_only(self, conn, dataset, periods):
        from qa_tools.common import filing_queue

        first, _ = periods
        supply = self._failed(conn, dataset, filed_to=first)
        (got,) = [s for s in filing_queue.awaiting(conn, dataset.collection_id)
                  if s.supply == supply]
        assert got.state == filing_queue.COULD_NOT_LOAD and got.period == first
        assert got.reason == "the file is empty"
        assert filing_queue.operations_for(got) == ((fd.REJECT,), ())

    def test_one_filed_to_no_period_is_left_to_the_held_route(self, conn, dataset):
        from qa_tools.common import filing_queue

        supply = self._failed(conn, dataset)
        assert not [s for s in filing_queue.awaiting(conn, dataset.collection_id)
                    if s.supply == supply]


class TestRejectingAFailedResupplyOfAFilledPeriod:
    """REQ-PIPE-153 criterion 7: the period keeps resolving to the supply
    that fills it - a rejection naming another supply never empties it
    (post-build-review #84's fix, pinned for the failed-load case)."""

    def test_the_period_still_resolves_to_its_promoted_supply(self, conn, dataset, actor,
                                                              periods):
        from qa_tools.common import load_log

        first, _ = periods
        filled, _ = _stage(conn, dataset)
        fd.apply(_request(dataset, actor, fd.PROMOTE, period=first, supply=filled),
                  effective_at=WHEN, conn=conn)
        arrival = uuid.uuid4().hex[:10]
        load_log.record(f"probe-{arrival}", dataset.dataset_id, f"{dataset.table}__{arrival}",
                        load_log.FAILED, WHEN, reason="the file is empty", conn=conn)
        fd.apply(_request(dataset, actor, fd.REJECT, period=first,
                           supply=f"{dataset.dataset_id}@{arrival}"),
                  effective_at="2026-09-30T09:00:00+08:00", conn=conn)
        assert dl.promoted_into(conn, dataset.dataset_id, first) == filled
