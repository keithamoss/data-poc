"""What each tool leaves out must be what the run records as not
evaluated (REQ-PIPE-115 criteria 17, 19 and 20).

The reconciliation is unit-tested first, then driven for real: the
Child Protection orchestrator over a period whose sibling table is
unreadable in each of the three ways a slot can explain it, asserting at
qa.check_result - the layer that records - that each records its own
reason code rather than the catch-all, and that every in-scope check has
exactly one of a tool verdict or a not-evaluated record.
"""
from __future__ import annotations


import pytest

import filing_support
from qa_tools.common import assignment, left_out, supply_db

P = "data-asset-1.child-protection-family-support.child-protection"
REL = f"{P}.cp-placements.carer_id.relationships_dbt"
SODA = f"{P}.cp-placements.carer_id.reference_soda"


class TestTheComparison:
    def test_agreement_returns_what_was_compared(self):
        got = left_out.reconcile("r", {"dbt": {REL}}, [{"check_id": REL}],
                                 lambda c: True)
        assert got == {"dbt": [REL]}

    def test_a_check_left_out_and_recorded_by_nobody_refuses_the_run(self):
        with pytest.raises(left_out.LeftOutMismatch, match="left out but nothing recorded"):
            left_out.reconcile("r", {"dbt": {REL}}, [], lambda c: True)

    def test_a_record_for_a_check_nobody_left_out_refuses_the_run(self):
        with pytest.raises(left_out.LeftOutMismatch, match="not left out"):
            left_out.reconcile("r", {}, [{"check_id": REL}], lambda c: True)

    def test_only_the_runs_scope_is_compared(self):
        """A tool leaves checks out across the whole collection; those
        belonging to other runs are theirs to account for."""
        assert left_out.reconcile("r", {"dbt": {REL}}, [], lambda c: False) == {}

    def test_the_registry_is_per_run_and_forgets_on_take(self):
        left_out.note("run-a", "soda", [SODA])
        left_out.note("run-b", "dbt", [REL])
        assert left_out.take("run-a") == {"soda": {SODA}}
        assert left_out.take("run-a") == {}
        assert left_out.take("run-b") == {"dbt": {REL}}


def _recorded(run_id: str) -> list[tuple]:
    with supply_db.connect(read_only=True, label="test-left-out") as conn:
        return conn.execute(
            "SELECT tool, check_id, status, extra->>'unrunnable_code' "
            'FROM "qa".check_result WHERE run_key LIKE ?', [f"%{run_id}"]).fetchall()


def _placements_run(received: str, *, carers_filed: bool):
    """A cp-placements run filed to 2026-Q3, reading every sibling from
    the fixture's own run except cp_carers, which it cannot read."""
    from conftest import clone_run_views
    from fixture_ids import CP_REF_RUN_ID

    key = supply_db.arrival_segment(received)
    run_id = f"cp_placements__{key}"
    filing_support.file(assignment.Assignment(
        dataset_id="cp-placements", supply_id=f"cp-placements@{key}", slot="2026-Q3",
        branch=assignment.OPEN_UNFILLED, considered=("2026-Q3",), received_at=None))
    if carers_filed:
        filing_support.file(assignment.Assignment(
            dataset_id="cp-carers", supply_id=f"cp-carers@{key}", slot="2026-Q3",
            branch=assignment.OPEN_UNFILLED, considered=("2026-Q3",), received_at=None))
    with supply_db.connect(label="test-left-out") as conn:
        clone_run_views(conn, CP_REF_RUN_ID, run_id, absent={"cp_carers"})
    return run_id, {"run_id": run_id, "run_index": 1, "received_at": received,
                    "delivery": "d", "files": {}}


@pytest.fixture
def clean_q3(supply_dsn):
    def _clear():
        with supply_db.connect(label="test-left-out") as conn:
            conn.execute("DELETE FROM qa.filing WHERE slot = '2026-Q3' AND dataset_id IN "
                         "('cp-carers', 'cp-placements')")
    _clear()
    yield
    _clear()


class TestEachSlotStateRecordsItsOwnReason:
    """Criterion 20, end to end through the real orchestrator and all
    four real tools."""

    @pytest.mark.parametrize("received,carers_filed,code,status", [
        # Before cp-carers is due for 2026-Q3 (due 2026-08-01).
        ("2026-07-25T03:00:00+00:00", False, "not-yet-due", "nodata"),
        # Well after it was due, with nothing filed.
        ("2026-09-01T03:00:00+00:00", False, "past-due", "fail"),
        # After it was due, with a supply filed and not yet decided.
        ("2026-09-02T03:00:00+00:00", True, "staged-awaiting-decision", "fail"),
    ])
    def test_the_sibling_check_records_its_reason(self, received, carers_filed, code,
                                                  status, cp_duckdb_dir, clean_q3):
        import qa_tools.cp.orchestrate_cp as orchestrate_cp

        run_id, entry = _placements_run(received, carers_filed=carers_filed)
        orchestrate_cp._run_one(entry, received, "t@example.com", reference_run_id=None)
        rows = _recorded(run_id)
        unrunnable = {(c, s, why) for tool, c, s, why in rows if tool == "unrunnable"}
        assert unrunnable, "the check reading the unreadable sibling must be recorded"
        assert {why for _, _, why in unrunnable} == {code}
        assert {s for _, s, _ in unrunnable} == {status}

        # EXACTLY ONE OF A VERDICT OR A NOT-EVALUATED RECORD per check.
        seen: dict[str, int] = {}
        for _tool, check, _s, _why in rows:
            seen[check] = seen.get(check, 0) + 1
        assert {c: n for c, n in seen.items() if n != 1} == {}

        # AND WHAT WAS COMPARED IS ON RECORD, per tool (the auditable NFR).
        with supply_db.connect(read_only=True, label="test-left-out") as conn:
            (compared,) = conn.execute(
                "SELECT raw_output->'left_out' FROM qa.tool_output "
                "WHERE run_key LIKE ? AND tool = 'left_out'", [f"%{run_id}"]).fetchone()
        assert compared and set(compared) <= {"dbt", "soda", "datacontract", "evidently"}
        assert {c for ids in compared.values() for c in ids} == {c for c, _, _ in unrunnable}
