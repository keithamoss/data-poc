"""What is waiting on a person, and what they may do about it
(REQ-GHUB-082 criteria 16, 17, 18, 19 and 31).

THE POINT OF MOST OF THESE is that there is ONE definition of "awaiting
a person" and this module filters it rather than restating it. A second
list would be a second answer, and the visible symptom would be a ticket
open for something the terminal says is done - which nobody would trace
back to a tuple in a module.
"""
from __future__ import annotations

import pytest

from qa_tools.common import (filing_decisions as fd, filing_queue, qa_store,
                              slot_state, supply_db)


def _state(state, *, dataset_id="cp-carers", period="2026-Q1", supply=None,
           decided_by=None):
    return slot_state.SlotState(dataset_id=dataset_id, period=period, state=state,
                                 supply=supply, decided_by=decided_by)


class TestTheQueueUsesTheTicketPolicysOwnDefinition:
    """Criterion 16: derived from the same definition `needs-action`
    uses, "never a second one"."""

    def test_the_two_halves_partition_needs_action_exactly(self):
        assert (set(filing_queue.WITH_A_SUPPLY) | set(filing_queue.WITHOUT_A_SUPPLY)
                == set(slot_state.NEEDS_ACTION))

    def test_no_state_is_in_both_halves(self):
        assert not (set(filing_queue.WITH_A_SUPPLY)
                    & set(filing_queue.WITHOUT_A_SUPPLY))

    def test_a_state_outside_needs_action_is_in_neither(self):
        """PROMOTED is finished and NOT_YET_DUE has not started. Putting
        either in the queue is how a queue stops being read."""
        for quiet in (slot_state.PROMOTED, slot_state.NOT_YET_DUE):
            assert quiet not in filing_queue.WITH_A_SUPPLY
            assert quiet not in filing_queue.WITHOUT_A_SUPPLY


class TestTheQueueHoldsOnlySuppliesSomebodyMustDecideAbout:

    @pytest.fixture
    def states(self, monkeypatch):
        every = [
            _state(slot_state.AWAITING_DECISION, period="2026-Q1", supply="cp-carers@1"),
            _state(slot_state.OVERDUE, period="2026-Q2"),
            _state(slot_state.PROMOTED, period="2025-Q4", supply="cp-carers@0"),
            _state(slot_state.REJECTED, period="2025-Q3", supply="cp-carers@9"),
            _state(slot_state.NOT_YET_DUE, period="2026-Q3"),
            _state(slot_state.NEVER_SUPPLIED, period="2024-Q1",
                    dataset_id="cp-clients"),
        ]
        monkeypatch.setattr(slot_state, "states_for",
                             lambda conn, collection_id, now=None: every)
        return every

    def test_it_holds_the_supplies_and_not_the_empty_periods(self, states):
        got = filing_queue.awaiting(None, "child-protection")
        assert [s.period for s in got] == ["2025-Q3", "2026-Q1"]

    def test_the_empty_periods_are_the_other_doors_business(self, states):
        """Criterion 31: none of substitute/inherit answers "what do I do
        with this arriving supply", so they are reached per period."""
        got = filing_queue.periods_needing_a_person(None, "child-protection")
        assert [(s.dataset_id, s.period) for s in got] == [
            ("cp-clients", "2024-Q1"), ("cp-carers", "2026-Q2")]
        assert {s.state for s in got} == {slot_state.OVERDUE,
                                           slot_state.NEVER_SUPPLIED}

    def test_between_them_they_are_the_whole_needs_action_set(self, states):
        both = (filing_queue.awaiting(None, "child-protection")
                 + filing_queue.periods_needing_a_person(None, "child-protection"))
        assert {s.state for s in both} == {
            s.state for s in states if s.state in slot_state.NEEDS_ACTION}

    def test_nothing_quiet_reaches_either(self, states):
        both = (filing_queue.awaiting(None, "child-protection")
                 + filing_queue.periods_needing_a_person(None, "child-protection"))
        assert slot_state.PROMOTED not in {s.state for s in both}
        assert slot_state.NOT_YET_DUE not in {s.state for s in both}


class TestWhatASlotOffers:
    """Criterion 2 read against criterion 31 - all eight are reachable,
    and the four period-scoped ones are never reached from the queue."""

    def test_every_one_of_the_eight_is_offered_by_some_slot(self):
        offered = set()
        for state in (slot_state.AWAITING_DECISION, slot_state.PROMOTED,
                       slot_state.REJECTED, slot_state.SUBSTITUTED,
                       slot_state.INHERITED, slot_state.OVERDUE):
            supply_scoped, period_scoped = filing_queue.operations_for(
                _state(state, supply="cp-carers@1"))
            offered |= set(supply_scoped) | set(period_scoped)
        assert offered == set(fd.OPERATIONS)

    def test_the_queue_half_is_only_ever_supply_scoped(self):
        """Criterion 31 made mechanical: whatever a slot is in, the first
        half of the answer can never contain a period-scoped operation."""
        for state in (slot_state.AWAITING_DECISION, slot_state.PROMOTED,
                       slot_state.REJECTED, slot_state.HELD,
                       slot_state.RETURNED, slot_state.SUBSTITUTED,
                       slot_state.INHERITED, slot_state.OVERDUE):
            supply_scoped, _ = filing_queue.operations_for(
                _state(state, supply="cp-carers@1"))
            assert not set(supply_scoped) & set(fd.PERIOD_SCOPED), state

    def test_a_period_with_nothing_in_it_offers_no_supply_operation(self):
        supply_scoped, period_scoped = filing_queue.operations_for(
            _state(slot_state.OVERDUE))
        assert supply_scoped == ()
        assert set(period_scoped) == {fd.SUBSTITUTE, fd.INHERIT}

    def test_a_promoted_slot_does_not_offer_promoting_it_again(self):
        supply_scoped, _ = filing_queue.operations_for(
            _state(slot_state.PROMOTED, supply="cp-carers@1"))
        assert fd.PROMOTE not in supply_scoped
        assert fd.DEMOTE in supply_scoped

    def test_a_substituted_period_offers_undoing_it_and_not_redoing_it(self):
        _, period_scoped = filing_queue.operations_for(_state(slot_state.SUBSTITUTED))
        assert period_scoped == (fd.DE_SUBSTITUTE,)

    def test_an_inherited_period_offers_un_inherit_not_de_substitute(self):
        """The two are identical in SQL and opposite in meaning, which is
        exactly why offering the wrong one would be a trap."""
        _, period_scoped = filing_queue.operations_for(_state(slot_state.INHERITED))
        assert period_scoped == (fd.UN_INHERIT,)


class TestWhichArrivalASupplyBelongsTo:
    """post-build-review #64's lesson: a supply id is not a table name,
    and the only safe join between them is the key they both carry."""

    def test_it_reads_the_key_out_of_a_supply_id(self):
        assert filing_queue.arrival_key_of(
            "cp-carers@202605010100000000") == "202605010100000000"

    def test_a_second_file_in_one_arrival_shares_the_key(self):
        assert filing_queue.arrival_key_of(
            "cp-carers@202605010100000000#1") == "202605010100000000"

    def test_the_physical_table_carries_the_same_key(self):
        supply = "cp-carers@202605010100000000"
        physical = "cp_carers__202605010100000000"
        assert filing_queue.arrival_key_of(supply) == physical.rsplit("__", 1)[-1]


class TestTheOfferAfterARun:
    """Criterion 17, and the join it rests on: a run's arrival comes from
    the tables it read, which the database already holds."""

    @pytest.fixture
    def conn(self, supply_dsn):
        with supply_db.connect(label="test-filing-queue") as c:
            qa_store.ensure_schema(c)
            yield c

    def _run(self, conn, run_key, physical):
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".run '
            "(run_key, agency_id, collection_id, run_timestamp, run_instant, "
            " run_by, environment) VALUES (?, ?, ?, ?, now(), ?, ?) "
            "ON CONFLICT (run_key) DO NOTHING",
            [run_key, "dcp", "child-protection", "2026-09-29T09:00:00+08:00",
             "somebody@example.com", "test"])
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".tables_read '
            "(run_key, logical_table, physical_table) VALUES (?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [run_key, "cp_carers", physical])

    def test_it_finds_this_runs_own_supply_and_not_another_one(self, conn, monkeypatch):
        self._run(conn, "cp_run_test_a", "cp_carers__202605010100000000")
        monkeypatch.setattr(slot_state, "states_for", lambda c, cid, now=None: [
            _state(slot_state.AWAITING_DECISION, period="2026-Q2",
                    supply="cp-carers@202605010100000000"),
            _state(slot_state.AWAITING_DECISION, period="2025-Q2",
                    supply="cp-carers@202505010100000000"),
        ])
        got = filing_queue.from_run(conn, "child-protection", "cp_run_test_a")
        assert [s.period for s in got] == ["2026-Q2"]

    def test_a_run_that_read_nothing_offers_nothing(self, conn, monkeypatch):
        monkeypatch.setattr(slot_state, "states_for", lambda c, cid, now=None: [
            _state(slot_state.AWAITING_DECISION, supply="cp-carers@1")])
        assert filing_queue.from_run(conn, "child-protection", "no-such-run") == []

    def test_a_run_whose_supply_was_already_decided_offers_nothing(self, conn,
                                                                    monkeypatch):
        """The ordinary case: the rule promoted it, so there is nothing
        left for the person who ran the checks to decide."""
        self._run(conn, "cp_run_test_b", "cp_carers__202602010100000000")
        monkeypatch.setattr(slot_state, "states_for", lambda c, cid, now=None: [
            _state(slot_state.PROMOTED, period="2026-Q1",
                    supply="cp-carers@202602010100000000")])
        assert filing_queue.from_run(conn, "child-protection", "cp_run_test_b") == []


class TestWhereEveryPeriodStands:
    """Criterion 18 - the filing state the decisions resolve to,
    whichever route recorded each of them."""

    def test_it_shows_every_slot_not_only_the_ones_needing_a_person(self, monkeypatch):
        monkeypatch.setattr(slot_state, "states_for", lambda c, cid, now=None: [
            _state(slot_state.PROMOTED, period="2025-Q4", supply="a@1"),
            _state(slot_state.NOT_YET_DUE, period="2026-Q3"),
            _state(slot_state.AWAITING_DECISION, period="2026-Q1", supply="a@2"),
        ])
        got = filing_queue.slots_of(None, "child-protection")
        assert [s.period for s in got] == ["2026-Q3", "2026-Q1", "2025-Q4"]

    def test_it_narrows_to_one_dataset(self, monkeypatch):
        monkeypatch.setattr(slot_state, "states_for", lambda c, cid, now=None: [
            _state(slot_state.PROMOTED, dataset_id="cp-carers", supply="a@1"),
            _state(slot_state.PROMOTED, dataset_id="cp-clients", supply="b@1"),
        ])
        got = filing_queue.slots_of(None, "child-protection", dataset_id="cp-clients")
        assert [s.dataset_id for s in got] == ["cp-clients"]

    def test_a_decision_raised_anywhere_shows_up_the_same(self, monkeypatch):
        """The log does not record which surface raised an entry, which
        is what makes "whichever route recorded each of them" free rather
        than something this had to be built to do."""
        monkeypatch.setattr(slot_state, "states_for", lambda c, cid, now=None: [
            _state(slot_state.PROMOTED, period="2026-Q1", supply="a@1",
                    decided_by="someone@example.com")])
        got = filing_queue.slots_of(None, "child-protection")
        assert got[0].decided_by == "someone@example.com"


class TestOnlyTheStatesADecisionProducedSayARuleDecidedThem:
    """Criterion 34, applied to the display: an automatic decision and a
    slot nobody has touched both read as `decided_by=None`, and calling
    both "a rule" puts a decision where none was made."""

    def test_the_decided_states_are_the_ones_a_decision_produces(self):
        for state in filing_queue.FROM_A_DECISION:
            assert state in (slot_state.PROMOTED, slot_state.REJECTED,
                              slot_state.SUBSTITUTED, slot_state.INHERITED,
                              slot_state.RETURNED)

    def test_a_supply_merely_filed_is_not_one_of_them(self):
        assert slot_state.AWAITING_DECISION not in filing_queue.FROM_A_DECISION
        assert slot_state.OVERDUE not in filing_queue.FROM_A_DECISION
        assert slot_state.HELD not in filing_queue.FROM_A_DECISION
