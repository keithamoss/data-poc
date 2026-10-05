"""A slot that closed unfilled reads as closed, and a person can accept it
as not supplied (REQ-PIPE-132).

Against a real database and the real quarterly schedule. qa.decision is
append-only, so each test takes its own (dataset, period) pair - nothing
one test records can answer another's question.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import (decision_log as dl, filing_decisions as fd, filing_queue,
                             not_supplied, people, qa_store, slot_state, supply_db)

PERTH = timezone(timedelta(hours=8))
LATER = datetime(2027, 12, 1, 9, tzinfo=PERTH)      # every 2024-2026 period has closed
REAL_PERSON = "fpycnkgvmt@privaterelay.appleid.com"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-not-supplied") as c:
        qa_store.ensure_schema(c)
        yield c


def _slot(dataset_id, period):
    from qa_tools.common import slots

    return next(s for s in slots.slots_for_dataset(dataset_id, until=LATER.date())
                if s.name == period)


def _state(conn, dataset_id, period, at=LATER, filings=None):
    return slot_state.state_of(conn, dataset_id=dataset_id, slot=_slot(dataset_id, period),
                               now=at, filings=filings or {}, ever_delivered=True)


def _mark(conn, dataset_id, period, reason="supplier confirmed they had nothing"):
    return not_supplied.mark(
        conn, agency_id="child-protection-family-support", collection_id="child-protection",
        dataset_id=dataset_id, period=period, actor=REAL_PERSON, reason=reason,
        effective_at=LATER.isoformat())


class TestClosedIsDerived:
    """Criteria 1 and 2."""

    def test_a_closed_unfilled_slot_is_overdue_and_closed(self, conn):
        got = _state(conn, "cp-clients", "2024-Q2")
        assert got.state == slot_state.OVERDUE and got.closed
        assert got.responses == slot_state.CLOSED_RESPONSES

    def test_an_overdue_slot_still_open_is_not_closed(self, conn):
        at = datetime(2026, 3, 1, 9, tzinfo=PERTH)      # Q1 due 1 Feb, closes mid-April
        got = _state(conn, "cp-clients", "2026-Q1", at=at)
        assert got.state == slot_state.OVERDUE and not got.closed

    def test_a_closed_slot_with_a_supply_waiting_reads_awaiting(self, conn):
        """Criterion 3."""
        got = _state(conn, "cp-clients", "2024-Q3",
                     filings={"2024-Q3": {"supply_id": "cp-clients@x"}})
        assert got.state == slot_state.AWAITING_DECISION


class TestMarkingIt:
    """Criteria 4, 6, 7, 8 and 9."""

    def test_a_closed_unfilled_slot_can_be_marked_and_reads_accepted(self, conn):
        _mark(conn, "cp-carers", "2024-Q2")
        got = _state(conn, "cp-carers", "2024-Q2")
        assert got.state == slot_state.NOT_SUPPLIED_ACCEPTED
        assert not got.needs_action, "an accepted gap leaves the to-do list"
        assert got.decided_by == REAL_PERSON and "nothing" in got.reason

    def test_it_changes_nothing_a_slot_holds(self, conn):
        _mark(conn, "cp-carers", "2024-Q3")
        assert dl.held(conn, "cp-carers", "2024-Q3") is None
        assert dl.promoted_into(conn, "cp-carers", "2024-Q3") is None

    def test_an_open_slot_is_refused_with_the_fix(self, conn):
        with pytest.raises(dl.DecisionRefused, match="still open.*mothman supply decide"):
            not_supplied.mark(
                conn, agency_id="a", collection_id="c", dataset_id="cp-carers",
                period="2027-Q4", actor=REAL_PERSON, reason="r",
                effective_at=LATER.isoformat())

    def test_a_filled_slot_is_refused(self, conn):
        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id="cp-placements",
                action=dl.PROMOTE, supply="cp-placements@k1", actor=REAL_PERSON,
                actor_kind=dl.PERSON, effective_at=LATER.isoformat(), to_slot="2024-Q2")):
            pass
        with pytest.raises(dl.DecisionRefused, match="so it is answered.*demote"):
            _mark(conn, "cp-placements", "2024-Q2")

    def test_only_a_person_with_a_reason_may_mark(self, conn):
        for kind, reason in ((dl.RULE, "r"), (dl.PERSON, "")):
            with pytest.raises(dl.DecisionRefused):
                with dl.apply_decision(conn, dl.Decision(
                        agency_id="a", collection_id="c", dataset_id="cp-carers",
                        action=dl.MARK_NOT_SUPPLIED, supply="", actor="x",
                        actor_kind=kind, effective_at=LATER.isoformat(),
                        to_slot="2024-Q4", reason=reason)):
                    pass

    def test_a_later_substitution_supersedes_the_mark(self, conn):
        _mark(conn, "cp-investigations", "2024-Q2")
        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id="cp-investigations",
                action=dl.SUBSTITUTE, supply="cp-investigations@k0", actor=REAL_PERSON,
                actor_kind=dl.PERSON, effective_at=(LATER + timedelta(days=1)).isoformat(),
                to_slot="2024-Q2", stands_on="2024-Q1", reason="stand on Q1")):
            pass
        assert not_supplied.marked(conn, "cp-investigations", "2024-Q2") is None


class TestBothRoutes:
    """Criteria 4 and 5: one of the filing decisions, period-scoped."""

    def test_the_route_records_it_and_a_second_time_changes_nothing(self, conn):
        actor = people.person_by_email(REAL_PERSON)
        request = fd.Request(operation=fd.MARK_NOT_SUPPLIED, dataset_id="cp-notifications",
                             actor=actor, reason="supplier had a system outage",
                             period="2024-Q2")
        first = fd.apply(request, effective_at=LATER.isoformat(), conn=conn)
        second = fd.apply(request, effective_at=LATER.isoformat(), conn=conn)
        assert first.changed and not second.changed

    def test_it_is_offered_on_a_closed_period_and_not_from_the_supply_queue(self, conn):
        got = _state(conn, "cp-clients", "2024-Q4")
        supply_scoped, period_scoped = filing_queue.operations_for(got)
        assert fd.MARK_NOT_SUPPLIED in period_scoped
        assert fd.MARK_NOT_SUPPLIED not in supply_scoped
        assert fd.MARK_NOT_SUPPLIED not in fd.SUPPLY_SCOPED


class TestGrouping:
    """Criterion 11: consecutive closed gaps of one dataset are one item."""

    def _s(self, ds, period, state=slot_state.OVERDUE, closed=True):
        return slot_state.SlotState(dataset_id=ds, period=period, state=state, closed=closed)

    def test_consecutive_gaps_group_and_anything_between_breaks_them(self):
        states = [self._s("d", "1"), self._s("d", "2"), self._s("d", "3"),
                  self._s("d", "4", state=slot_state.PROMOTED, closed=False),
                  self._s("d", "5"), self._s("e", "6")]
        got = filing_queue.group_gaps(states)
        assert [(g.dataset_id, g.periods) for g in got] == [
            ("d", ("1", "2", "3")), ("d", ("5",)), ("e", ("6",))]
        assert got[0].describe() == "3 periods with no supply, 1 to 3"

    def test_a_daily_run_says_days_in_the_pages_own_date_form(self):
        """The display standard (REQ-DASH-071): a day reads as the page
        writes one, never ISO - found by the real-browser raw-timestamp
        test the first time a daily feed's gap reached the queue."""
        got = filing_queue.group_gaps([self._s("d", "2026-09-22"), self._s("d", "2026-09-23")])
        assert got[0].describe() == ("2 days with no supply, Tuesday, 22 September 2026 "
                                     "to Wednesday, 23 September 2026")
        one = filing_queue.group_gaps([self._s("d", "2026-09-23")])
        assert one[0].describe() == "1 day with no supply, Wednesday, 23 September 2026"

    def test_an_accepted_gap_is_not_listed(self):
        got = filing_queue.group_gaps([self._s("d", "1", state=slot_state.NOT_SUPPLIED_ACCEPTED)])
        assert got == []


class TestWhatTheBuildEmbeds:
    """REQ-DASH-133 criteria 9 and 10: the build embeds every slot that was
    a gap when it closed, with the instants that decide what it reads as -
    the page only compares them with the date on show."""

    def test_a_marked_period_carries_its_mark_and_instant(self, conn):
        from pipeline import closed_slots

        _mark(conn, "cp-notifications", "2025-Q1", reason="nothing that quarter")
        got = {s["period"]: s for s in closed_slots.for_dataset("cp-notifications", conn, now=LATER)}
        assert got["2025-Q1"]["marks"][-1]["reason"] == "nothing that quarter"
        assert got["2025-Q1"]["marks"][-1]["at"] and got["2025-Q1"]["closesAt"]
        assert [s["index"] for s in got.values()] == sorted(s["index"] for s in got.values())

    def test_a_slot_filled_after_it_closed_was_still_a_gap_and_says_when(self, conn):
        from pipeline import closed_slots

        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id="cp-placements",
                action=dl.PROMOTE, supply="cp-placements@k3", actor=REAL_PERSON,
                actor_kind=dl.PERSON, effective_at=LATER.isoformat(), to_slot="2025-Q2")):
            pass
        got = {s["period"]: s for s in closed_slots.for_dataset("cp-placements", conn, now=LATER)}
        assert got["2025-Q2"]["changes"][-1]["held"], "a late fill ends the gap from that instant on"

    def test_a_slot_not_yet_closed_is_not_listed(self, conn):
        from pipeline import closed_slots

        early = datetime(2025, 3, 1, 9, tzinfo=PERTH)
        got = {s["period"] for s in closed_slots.for_dataset("cp-carers", conn, now=early)}
        assert "2025-Q1" not in got and "2024-Q2" in got


class TestAMarkCarriesNoSupply:
    """A mark is about a PERIOD, not an arrival, so it records no supply -
    and every reader that walks the whole decision log has to cope.
    Found 2026-10-05: dataset_blockers._decided_keys took the arrival key
    of every decision's supply and raised a TypeError on a mark's NULL,
    which took the whole outstanding queue down with it."""

    def test_the_blockers_and_the_queue_still_read(self, conn):
        from qa_tools.common import dataset_blockers, outstanding

        _mark(conn, "cp-case-workers", "2024-Q3", reason="nothing that half-year")
        dataset_blockers.all_blockers(conn)
        outstanding.survey(conn)


class TestARejectedSupplyLeavesItsPeriodEmpty:
    """REQ-DASH-133 criterion 1's exception and REQ-PIPE-153 criterion 9: a
    supply filed to a period and then rejected leaves that period with
    nothing in it, and the embed says so - with who, when and why -
    rather than counting the filing. Found 2026-10-05 re-testing 153's
    deferral: the first cut of closed_slots counted any filing, so a
    period whose only supply was rejected never read as unfilled."""

    def test_the_period_carries_the_rejection(self, conn):
        from pipeline import closed_slots
        from qa_tools.common import filing

        supply = "cp-investigations@202502050100000000"
        delivery = "pytest-rejected-2025q1"
        conn.execute(
            "INSERT INTO qa.delivery (name, received_at, received_instant) "
            "VALUES (?, '2025-02-05T01:00:00+00:00', '2025-02-05T01:00:00+00:00') "
            "ON CONFLICT DO NOTHING", [delivery])
        conn.execute(
            "INSERT INTO qa.delivery_file (delivery, filename, dataset_id, received_at, "
            "received_instant, received_from, receipt_sequence) VALUES (?, "
            "'cp_investigations.csv', 'cp-investigations', '2025-02-05T01:00:00+00:00', "
            "'2025-02-05T01:00:00+00:00', 'our-clock', 1) ON CONFLICT DO NOTHING", [delivery])
        conn.execute(
            f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, delivery) "
            "VALUES ('cp-investigations', ?, '2025-Q1', 'pytest', ?) "
            "ON CONFLICT (dataset_id, supply_id) DO UPDATE SET slot = EXCLUDED.slot",
            [supply, delivery])
        before = {s["period"] for s in closed_slots.for_dataset("cp-investigations", conn, now=LATER)}
        assert "2025-Q1" not in before, "a live filing before the close was never a gap"
        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id="cp-investigations",
                action=dl.REJECT, supply=supply, actor=REAL_PERSON, actor_kind=dl.PERSON,
                effective_at=LATER.isoformat(), reason="supplier is resending",
                from_slot="2025-Q1")):
            pass
        got = {s["period"]: s for s in closed_slots.for_dataset("cp-investigations", conn, now=LATER)}
        assert got["2025-Q1"]["rejected"]["reason"] == "supplier is resending"
        assert got["2025-Q1"]["rejected"]["actor"] == REAL_PERSON
        assert got["2025-Q1"]["filedAt"] is None


class TestAnEmptiedPeriodIsAGapAgain:
    """delivery-critic, 2026-10-05 (#105), HIGH: closed_slots recorded only
    the FIRST fill, so a closed period filled and then emptied again -
    substituted then de-substituted, or promoted then demoted - read as
    filled on the page for ever while the queue said it needed a person."""

    def test_a_de_substitution_after_the_close_reopens_the_gap(self, conn):
        from pipeline import closed_slots

        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id="cp-clients",
                action=dl.SUBSTITUTE, supply="cp-clients@kx", actor=REAL_PERSON,
                actor_kind=dl.PERSON, effective_at=LATER.isoformat(), to_slot="2025-Q2",
                stands_on="2025-Q1", reason="stand on Q1")):
            pass
        undone = (LATER + timedelta(days=2)).isoformat()
        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id="cp-clients",
                action=dl.DE_SUBSTITUTE, supply="cp-clients@kx", actor=REAL_PERSON,
                actor_kind=dl.PERSON, effective_at=undone, from_slot="2025-Q2",
                reason="undo")):
            pass
        got = {s["period"]: s for s in closed_slots.for_dataset(
            "cp-clients", conn, now=LATER + timedelta(days=5))}
        changes = got["2025-Q2"]["changes"]
        assert [c["held"] for c in changes][-2:] == [True, False]


class TestASupplyWaitingInAClosedPeriodIsNotAGap:
    """delivery-critic, 2026-10-05 (#105), MEDIUM-HIGH: after a rejection, a
    resupply filed to the same period still read REJECTED and closed, so it
    was listed as 'no supply' and could be marked not supplied
    (REQ-PIPE-132 criteria 3 and 6)."""

    def test_the_resupply_reads_awaiting_and_the_mark_is_refused(self, conn):
        from qa_tools.common import filing

        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id="cp-investigations",
                action=dl.REJECT, supply="cp-investigations@s1", actor=REAL_PERSON,
                actor_kind=dl.PERSON, effective_at=LATER.isoformat(),
                from_slot="2024-Q3", reason="bad file")):
            pass
        conn.execute("INSERT INTO qa.delivery (name, received_at, received_instant) VALUES "
                     "('pytest-resupply-s2', '2024-09-05T01:00:00+00:00', "
                     "'2024-09-05T01:00:00+00:00') ON CONFLICT DO NOTHING")
        conn.execute(
            f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, delivery) "
            "VALUES ('cp-investigations', 'cp-investigations@s2', '2024-Q3', 'pytest', "
            "'pytest-resupply-s2') "
            "ON CONFLICT (dataset_id, supply_id) DO UPDATE SET slot = EXCLUDED.slot")
        filings = {"2024-Q3": {"supply_id": "cp-investigations@s2"}}
        got = _state(conn, "cp-investigations", "2024-Q3", filings=filings)
        assert got.state == slot_state.AWAITING_DECISION and not got.closed
        with pytest.raises(dl.DecisionRefused, match="waiting for a decision"):
            _mark(conn, "cp-investigations", "2024-Q3")


class TestTheRefusalNamesTheRightUndo:
    """delivery-critic #105: marking a substituted period named `demote` of
    the supply it stands on, which is itself refused - the undo is
    de-substitute."""

    def test_a_substituted_period_names_de_substitute(self, conn):
        with dl.apply_decision(conn, dl.Decision(
                agency_id="a", collection_id="c", dataset_id="cp-notifications",
                action=dl.SUBSTITUTE, supply="cp-notifications@k0", actor=REAL_PERSON,
                actor_kind=dl.PERSON, effective_at=LATER.isoformat(), to_slot="2025-Q2",
                stands_on="2025-Q1", reason="stand on Q1")):
            pass
        with pytest.raises(dl.DecisionRefused, match="--operation de-substitute"):
            _mark(conn, "cp-notifications", "2025-Q2")


class TestALateDayStillOpenIsNamed:
    """REQ-DASH-133, Keith 2026-10-05 (#104): a daily feed's row names
    today's late-but-open file beside an old gap. The build embeds every
    slot that was ever late while open - when it went late, when a file
    came, when it closed - and the page only compares those with the date
    on show."""

    def test_a_slot_with_nothing_filed_was_late_from_its_late_instant(self, conn):
        from pipeline import closed_slots

        got = {s["period"]: s for s in closed_slots.late_slots("cp-carers", conn, now=LATER)}
        assert got["2025-Q1"]["filedAt"] is None
        assert got["2025-Q1"]["lateAt"] and got["2025-Q1"]["closesAt"]

    def test_a_slot_filed_on_time_was_never_late(self, conn):
        from pipeline import closed_slots
        from qa_tools.common import filing, slots

        slot = next(s for s in slots.slots_for_dataset("cp-carers", until=LATER.date())
                    if s.name == "2025-Q1")
        on_time = (slot.claim_opens_at + (slot.late_after - slot.claim_opens_at) / 2).isoformat()
        delivery = "pytest-on-time-2025q1"
        conn.execute("INSERT INTO qa.delivery (name, received_at, received_instant) "
                     "VALUES (?, ?, ?) ON CONFLICT DO NOTHING", [delivery, on_time, on_time])
        conn.execute(
            "INSERT INTO qa.delivery_file (delivery, filename, dataset_id, received_at, "
            "received_instant, received_from, receipt_sequence) VALUES (?, 'cp_carers.csv', "
            "'cp-carers', ?, ?, 'our-clock', 1) ON CONFLICT DO NOTHING",
            [delivery, on_time, on_time])
        conn.execute(
            f"INSERT INTO {filing.TABLE} (dataset_id, supply_id, slot, branch, delivery) "
            "VALUES ('cp-carers', 'cp-carers@ontime', '2025-Q1', 'pytest', ?) "
            "ON CONFLICT (dataset_id, supply_id) DO UPDATE SET slot = EXCLUDED.slot", [delivery])
        got = {s["period"] for s in closed_slots.late_slots("cp-carers", conn, now=LATER)}
        assert "2025-Q1" not in got
