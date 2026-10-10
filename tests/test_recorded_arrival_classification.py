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

import filing_support
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
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing CASCADE')
        yield conn


def _file(slot=EARLY_SLOT, received_at=ARRIVED, supply_id="s"):
    return filing_support.file(assignment.Assignment(
        dataset_id=DATASET, supply_id=supply_id, slot=slot,
        branch=assignment.OPEN_UNFILLED, considered=(slot,),
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
        filing_support.file(assignment.Assignment(
            dataset_id=DATASET, supply_id="held", slot=None,
            branch=assignment.HELD, considered=(), received_at=ARRIVED))
        assert filing.filing_for(DATASET, "held")["classification"] == classify_mod.UNFILED


def _refile(dataset_id, supply_id, to_slot):
    from qa_tools.common import supply_db

    with supply_db.connect(label="test-refile") as conn:
        return filing.refile(conn, dataset_id, supply_id, to_slot, decision_id=1)


class TestItFollowsAReFile:
    """Criteria 5 and 8 - recorded, and still current."""

    def test_a_refile_rewrites_the_recorded_classification(self, clean):
        _file(slot=EARLY_SLOT)
        assert filing.filing_for(DATASET, "s")["classification"] == classify_mod.EARLY
        _refile(DATASET, "s", LATE_SLOT)
        assert filing.filing_for(DATASET, "s")["classification"] == classify_mod.LATE

    def test_the_receipt_instant_does_NOT_move_with_it(self, clean):
        """Criterion 8, and REQ-PIPE-067 criterion 3. When we received
        something is a fact; which period it was for is a decision."""
        _file()
        _refile(DATASET, "s", LATE_SLOT)
        assert filing.recorded_arrival(DATASET, "s").received_at == ARRIVED

    def test_it_is_never_recomputed_from_the_promotion_instant(self, clean):
        """Criterion 8's second half, asserted structurally: a verdict
        taken from when somebody got round to promoting would make
        punctuality a property of OUR responsiveness rather than the
        supplier's."""
        import ast
        import inspect
        import textwrap

        from qa_tools.common import verdict

        for fn in (filing._judged_for, verdict.judge):
            tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
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


class TestTheRealFilingPathRecordsIt:
    """The gap the first cut of this requirement left, and the reason
    it was invisible: every test above builds an `Assignment` by hand
    with `received_at=`, so they passed while `assign()` - the only
    thing that constructs one in production - set it on none of its six
    branches. The columns would have been null for every real supply.

    Same shape as CLAUDE.md's own standing lesson: a green data layer
    says nothing about the path that actually feeds it.
    """

    def test_every_branch_of_the_rule_carries_the_arrival_instant(self):
        """Asserted over the real function rather than one branch,
        because the bug was five branches being right and one wrong
        being just as broken as all six."""
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(assignment.assign)))
        built = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "Assignment"]
        assert built, "assign() builds no Assignment - has it been renamed?"
        missing = [n.lineno for n in built
                   if "received_at" not in {k.arg for k in n.keywords}]
        assert not missing, (
            f"{len(missing)} of {len(built)} Assignment(...) in assign() omit "
            f"received_at, at lines {missing} - those supplies record no "
            f"arrival instant and so no classification")

    def test_and_the_rule_really_returns_one(self, clean):
        """The structural test above would pass on a literal `None`, so
        this drives the real function and looks at the value."""
        from qa_tools.common import slots as slots_mod

        got = assignment.assign(
            DATASET, f"{DATASET}@202307250100000000", ARRIVED,
            slots_mod.slots_for_dataset(
                DATASET, until=slots_mod.claimable_until(DATASET, ARRIVED.date())),
            frozenset())
        assert got.received_at == ARRIVED
class TestTheRetiredDerivations:
    """Criteria 2 and 3 - gone, not merely unused."""

    def test_the_arrival_date_derivation_is_gone(self):
        """Criterion 2. It could only look BACKWARDS from the arrival
        date, so it could never see a slot that had not started - which
        is why 'early' was unreachable through it."""
        # pipeline/cadence.py itself is gone since REQ-PIPE-110, which
        # moved what was left of it to qa_tools/common/agreement.py.
        import importlib.util

        from qa_tools.common import agreement

        assert importlib.util.find_spec("pipeline.cadence") is None
        assert not hasattr(agreement, "classify_arrival")

    def test_the_builders_no_longer_derive_it(self):
        """Criterion 3. Blanking was a workaround for the derivation
        being wrong on exactly those supplies; with the derivation gone
        the workaround hides a real answer."""
        import pathlib

        # ON THE IMPORT, not on the text: both modules still MENTION
        # the retired function in a comment explaining why it is gone,
        # and a substring check cannot tell that from a call. An
        # import is unambiguous - and since the function no longer
        # exists, one would fail at module load anyway.
        import ast

        for name in ("build_dashboard_data.py", "build_cp_dashboard_data.py"):
            tree = ast.parse(pathlib.Path("pipeline", name).read_text())
            imported = {a.name for n in ast.walk(tree)
                        if isinstance(n, ast.ImportFrom) for a in n.names}
            assert "classify_arrival" not in imported, f"{name} still imports it"

    def test_the_template_no_longer_blanks_a_resupplys_verdict(self):
        """Criterion 3. Blanking was a workaround for the derivation
        being wrong on exactly those supplies; with the derivation gone
        the workaround hides a real answer."""
        import pathlib as _p

        src = _p.Path("dashboard/qa-reporting-dashboard.template.html").read_text()
        assert "arrivalStatus: idx===0" not in src
        assert "arrivedAt: idx===0" not in src
