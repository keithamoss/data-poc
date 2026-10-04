"""A 'withheld' note must not make a filled slot read as empty.

Found by the delivery-architect's pre-build review, 2026-10-04, and
written as a failing test FIRST, on Keith's instruction, before anything
is fixed.

THE SHAPE OF IT. Every reader of "what does this slot hold" takes the
LATEST decision-log entry naming the slot and interprets its action
(decision_log.promoted_into(), and through it promotion.filled_slots()).
The off-cycle gate writes a PROMOTION_WITHHELD entry naming the slot it
stood back from - and promotion.after_run() writes it whenever the
arrival is off-cycle, even when the gate's real refusal was that the
slot was ALREADY FILLED. The withheld entry is then the latest one on a
filled slot, its action is not a promote, and the slot reads empty.

THE REAL CASE. cp-case-workers participates in Q1 and Q3 only. Its Q3
supply is promoted. A resend arrives in Q4, which it skips, and files to
Q3 as a resupply. The gate refuses it - filled slot, and off-cycle - and
records the withheld note against Q3. From then on Q3 reads unfilled, so
the next Case Workers arrival for Q3 would be promoted automatically
over the accepted one.

THE GATE IS GONE (REQ-PIPE-131 retired REQ-PIPE-077, 2026-10-04), so
nothing writes this entry today. The property is kept because it is
about every entry that annotates a slot without changing it, and
`promotion-withheld` is still the vocabulary's example of one.
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import promotion, qa_store, supply_db

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"
SLOT = "2026-Q3"
ACCEPTED = "cp_case_workers__20260801090000000000"
RESEND = "cp_case_workers__20261102090000000000"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-withheld-slot") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    """A dataset id nothing else in the suite has decided anything about -
    the log is append-only, so isolation is by id, as in
    test_decision_log.py."""
    return f"cp-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def a_filled_slot_then_withheld(conn, dataset):
    with dl.apply_decision(conn, dl.Decision(
            agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            action=dl.PROMOTE, supply=ACCEPTED, actor="mothman:promotion-gate",
            actor_kind=dl.RULE, effective_at="2026-08-01T10:00:00+08:00",
            to_slot=SLOT)):
        pass
    assert dl.promoted_into(conn, dataset, SLOT) == ACCEPTED, "precondition"
    # Written directly: the gate that wrote these was retired by
    # REQ-PIPE-131, and an annotating entry must still never change what
    # a slot holds (REQ-PIPE-132 criterion 8).
    dl.record_automatic(conn, dl.Decision(
        agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
        action=dl.PROMOTION_WITHHELD, supply=RESEND, actor="mothman:promotion-gate",
        actor_kind=dl.RULE, effective_at="2026-11-02T10:00:00+08:00", to_slot=SLOT,
        reason="this dataset is not due in 2026-Q4, the period this supply arrived in"))
    conn.commit()
    return dataset


class TestAWithheldNoteDoesNotEmptyAFilledSlot:

    def test_the_slot_still_resolves_to_the_accepted_supply(
            self, conn, a_filled_slot_then_withheld):
        assert dl.promoted_into(conn, a_filled_slot_then_withheld, SLOT) == ACCEPTED

    def test_the_slot_still_counts_as_filled_for_the_gate(
            self, conn, a_filled_slot_then_withheld):
        assert SLOT in promotion.filled_slots(conn, a_filled_slot_then_withheld)
