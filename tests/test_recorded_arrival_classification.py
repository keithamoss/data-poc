"""The recorded arrival classification replaces the one derived from
the arrival date (REQ-PIPE-080).

THREE DERIVATIONS OF ONE FACT EXISTED, which is the whole problem this
closes. `pipeline.cadence.classify_arrival()` inferred a cycle from the
arrival DATE and could only ever look backwards, so a quarterly supply
arriving a week before its anchor read twelve weeks LATE for a quarter
already filled. `arrival_classification.classify()` measures against
the slot the supply was actually filed to and gets it right. And the
dashboard separately BLANKED a resupply's verdict rather than show a
wrong one - a workaround for the first derivation, not a rule.

So the fix is not a better formula. It is recording the answer once,
against the filing, and deleting the other two paths in the same change
(criterion 7) so no window exists where the old one is gone and nothing
has replaced it.

WHAT IS RECORDED IS THE INPUT AND THE ANSWER, and the distinction
matters because REQ-PIPE-067 requires the verdict to FOLLOW a re-file.
Our receipt instant is a fact and never moves (criterion 4); the slot
is a decision and can; so the classification is stored WITH the filing
and rewritten when the filing changes. That is what makes it both
recorded and current.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import arrival_classification as classify_mod
from qa_tools.common import assignment, filing

PERTH = timezone(timedelta(hours=8))

#: A REAL dataset with real slots, deliberately, rather than a
#: fictional one with a hand-built slot map. The recording path
#: resolves a slot NAME to a real Slot through
#: `slots.slots_for_dataset()`, and that resolution is exactly what
#: could silently return nothing in production and leave the column
#: empty. A fixture that hands the classifier its slots would prove
#: the arithmetic and skip the part that breaks.
DATASET = "cp-clients"

#: 2023-Q3 opens 2023-07-18 and is due 2023-08-01 09:00 Perth. This
#: instant is inside Q3's claim window and MONTHS after Q2's due date -
#: REQ-PIPE-066's own worked example. Against the slot it is filed to
#: it is EARLY; the retired derivation looked backwards from the
#: arrival date, landed on Q2, and called it about twelve weeks late.
ARRIVED = datetime(2023, 7, 25, 9, tzinfo=PERTH)

EARLY_SLOT = "2023-Q3"
LATE_SLOT = "2023-Q2"


@pytest.fixture
def clean(supply_dsn):
    """This worker's own empty filing table."""
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="test-recorded-classification") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing')
        yield conn


def _file(slot=EARLY_SLOT, received_at=ARRIVED, supply_id="s"):
    return filing.record(assignment.Assignment(
        dataset_id=DATASET, supply_id=supply_id, slot=slot,
        branch=assignment.OLDEST_CLAIMABLE, considered=(slot,),
        received_at=received_at))


class TestTheClassificationIsRecordedWithTheFiling:
    """Criterion 1 - recorded once, against the slot it is filed to."""

    def test_recording_a_filing_records_its_classification(self, clean):
        _file()
        assert filing.filing_for(DATASET, "s")["classification"] == classify_mod.EARLY

    def test_and_our_receipt_instant_alongside_it(self, clean):
        """Criterion 4. The INPUT is recorded too, not only the answer -
        without it a re-file could not recompute the verdict."""
        _file()
        assert filing.recorded_arrival(DATASET, "s").received_at == ARRIVED

    def test_it_is_a_column_a_query_can_reach_not_only_a_json_field(self, clean):
        """Criterion 1's "every consumer reads it": a consumer asking
        "how many supplies were late" should not have to unpack a
        document per row."""
        from qa_tools.common import qa_store

        _file()
        with filing._connect("t") as conn:
            rows = conn.execute(
                f'SELECT classification FROM "{qa_store.SCHEMA}".filing '
                "WHERE dataset_id = ?", [DATASET]).fetchall()
        assert rows == [(classify_mod.EARLY,)]

    def test_a_held_supply_records_unfiled_rather_than_a_verdict(self, clean):
        """Criterion 6. There is no slot to be punctual against, and
        saying "on time" here would invent a verdict from an absence."""
        filing.record(assignment.Assignment(
            dataset_id=DATASET, supply_id="held", slot=None,
            branch=assignment.HELD, considered=(), received_at=ARRIVED))
        assert filing.filing_for(DATASET, "held")["classification"] == classify_mod.UNFILED


class TestItFollowsAReFile:
    """Criteria 5 and 8 - recorded, and still current."""

    def test_a_refile_rewrites_the_recorded_classification(self, clean):
        _file(slot=EARLY_SLOT)
        assert filing.filing_for(DATASET, "s")["classification"] == classify_mod.EARLY
        filing.refile(DATASET, "s", LATE_SLOT, refiling_id="r1")
        assert filing.filing_for(DATASET, "s")["classification"] == classify_mod.LATE

    def test_the_receipt_instant_does_NOT_move_with_it(self, clean):
        """Criterion 8, and REQ-PIPE-067 criterion 3. When we received
        something is a fact; which period it was for is a decision."""
        _file()
        filing.refile(DATASET, "s", LATE_SLOT, refiling_id="r1")
        assert filing.recorded_arrival(DATASET, "s").received_at == ARRIVED

    def test_it_is_never_recomputed_from_the_promotion_instant(self, clean):
        """Criterion 8's second half, asserted structurally: a verdict
        taken from when somebody got round to promoting would make
        punctuality a property of OUR responsiveness rather than the
        supplier's."""
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(filing._classification_for)))
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not {"promoted_at", "promoted_into", "effective_at"} & names


class TestTheIntervalFromReceiptToPromotion:
    """Criteria 9, 10 and 11 - two distinct facts, never one in place
    of the other."""

    def test_it_reports_when_the_supply_arrived_and_when_the_slot_was_filled(self, clean):
        _file()
        got = filing.recorded_arrival(DATASET, "s")
        assert got.received_at == ARRIVED
        assert got.filled_at is None, "nothing has promoted it"

    def test_an_unpromoted_supply_has_an_OPEN_interval_not_a_zero_one(self, clean):
        """Criterion 10. Absent or zero would both read as 'dealt with
        instantly', which is the opposite of what is true."""
        _file()
        got = filing.recorded_arrival(DATASET, "s")
        assert got.awaiting is True
        assert got.waited is not None and got.waited > timedelta(0)

    def test_the_two_instants_are_separate_fields(self, clean):
        """Criterion 11, structurally: neither may stand in for the
        other, so neither may be the only one present."""
        _file()
        got = filing.recorded_arrival(DATASET, "s")
        assert hasattr(got, "received_at") and hasattr(got, "filled_at")
