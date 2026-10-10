"""A contested table: staging offers nothing, the period still answers.

REQ-PIPE-105 criterion 8 and REQ-PIPE-079 criteria 11, 12 and 13, which
together draw a line an earlier, blunter rule did not.

THE EARLIER RULE SAID AMBIGUITY IS ABSENCE, FULL STOP, and its reason
was real: falling back to the promoted table would QA the delivery
against data it did not contain, which reads green and means nothing.
That reason is exactly true of the contested table's OWN checks and
false of every check that merely READS it - a referential-integrity
check filed against placements that reads carers is in the same
position as any check reading a table the delivery did not bring at
all, and reading the period's promoted carers is the ordinary answer
rather than a fallback.

So the split is: the view resolves to the period's promoted version
(criterion 12), the contest is still recorded so that the table's own
checks do not run and it is not promoted (criterion 13), and nothing
ever chooses between the staged candidates for any purpose
(criterion 11).

Own DuckDB file per test, for the reason tests/test_period_schema.py
gives at its top.
"""
from __future__ import annotations

import duckdb
import pytest

from qa_tools.common import period_schema as ps
from qa_tools.common import promotion
from qa_tools.common import supply_db


@pytest.fixture
def conn(tmp_path):
    connection = duckdb.connect(str(tmp_path / "contested.duckdb"))
    connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
    try:
        yield connection
    finally:
        connection.close()


def _stage(conn, physical, rows):
    values = ", ".join(f"({v})" for v in rows)
    conn.execute(
        f'CREATE OR REPLACE TABLE "{supply_db.STAGING_SCHEMA}"."{physical}" AS '
        f"SELECT * FROM (VALUES {values}) AS t(n)")


def _promote(conn, period, physical, rows):
    ps.ensure_period_schema(conn, period)
    values = ", ".join(f"({v})" for v in rows)
    conn.execute(
        f'CREATE OR REPLACE TABLE "{ps.period_schema(period)}"."{physical}" AS '
        f"SELECT * FROM (VALUES {values}) AS t(n)")


def _contested(conn, *, promoted_rows=(1, 2, 3)):
    """Two staged files claiming `clients`, over a promoted version."""
    if promoted_rows:
        _promote(conn, "2026-Q3", "clients__20260801010000", list(promoted_rows))
    _stage(conn, "clients__20260901010000__1", [8])
    _stage(conn, "clients__20260901010000__2", [9])
    return ps.create_overlay_views(
        conn, "run_1", "2026-Q3",
        staged={"clients": ["clients__20260901010000__1",
                             "clients__20260901010000__2"]},
        promoted=ps.promoted_in(conn, "2026-Q3", ["clients"]))


class TestTheContestIsRecordedAndThePeriodIsStillReadable:
    """Criterion 8, and REQ-PIPE-079 criteria 11 and 12."""

    def test_the_staged_candidates_are_recorded_as_contested(self, conn):
        res = _contested(conn)
        assert res.resolution.ambiguous["clients"] == [
            "clients__20260901010000__1", "clients__20260901010000__2"]

    def test_the_view_resolves_to_the_periods_promoted_version(self, conn):
        res = _contested(conn)
        assert res.resolution.resolved["clients"] == "clients__20260801010000"
        assert res.source["clients"] == ps.FROM_PERIOD

    def test_nothing_chooses_between_the_staged_candidates(self, conn):
        """Criterion 11. The rows a check reads are the period's, never
        either candidate's - which is what "offering nothing" means when
        said in SQL rather than in prose."""
        res = _contested(conn)
        rows = conn.execute(
            f'SELECT n FROM "{res.resolution.schema}"."clients" ORDER BY n').fetchall()
        assert [r[0] for r in rows] == [1, 2, 3]

    def test_a_check_that_merely_reads_it_runs(self, conn):
        """Criterion 12: on the same terms as any table the delivery did
        not bring."""
        res = _contested(conn)
        assert ps.check_readiness(["clients"], res) is None

    def test_a_contest_with_nothing_promoted_is_still_unreadable(self, conn):
        """Criterion 12 is conditional on the period HAVING a promoted
        supply. With none, there is nothing to fall through to and the
        table is as absent as it ever was."""
        res = _contested(conn, promoted_rows=())
        assert "clients" in res.resolution.ambiguous
        assert "clients" not in res.resolution.resolved
        assert "clients" not in res.source
        with pytest.raises(duckdb.Error):
            conn.execute(f'SELECT * FROM "{res.resolution.schema}"."clients"')
        assert ps.check_readiness(["clients"], res).status == ps.RED


class TestTheContestedTablesOwnChecksDoNotRun:
    """REQ-PIPE-079 criterion 13, and the safeguard that makes the
    fall-through above safe rather than a false green."""

    OWN = ("data-asset-1.child-protection-directorate.child-protection"
            ".cp-clients.client_id.unique_dbt")
    OTHER = ("data-asset-1.child-protection-directorate.child-protection"
              ".cp-placements.client_id.relationship_dbt")

    def test_the_tables_own_checks_are_suppressed(self):
        assert ps.contested_own_checks(
            ["cp_clients"], [self.OWN, self.OTHER]) == frozenset({self.OWN})

    def test_a_check_of_another_dataset_reading_it_is_not_suppressed(self):
        """The whole point of the split: this check is the one criterion
        12 exists for, and suppressing it would put us back where we
        started."""
        assert self.OTHER not in ps.contested_own_checks(
            ["cp_clients"], [self.OWN, self.OTHER])

    def test_nothing_contested_suppresses_nothing(self):
        assert ps.contested_own_checks([], [self.OWN, self.OTHER]) == frozenset()

    def test_a_logical_name_no_dataset_claims_is_an_error_not_a_pass(self):
        """The dangerous direction is failing to suppress, so an
        unrecognised table is loud rather than skipped."""
        from qa_tools.common import hierarchy
        with pytest.raises(hierarchy.UnknownDatasetError):
            ps.contested_own_checks(["not_a_table"], [self.OWN])


class TestAContestedTableIsNeverPromoted:
    """REQ-PIPE-079 criterion 13's second half: "whatever the period
    holds"."""

    def test_a_contested_supply_is_refused(self):
        ok, why = promotion.should_promote(
            status="green", slot_filled=False, held_without_slot=False,
            has_active_checks=True, contested=True)
        assert ok is False
        assert "which one is the supply" in why

    def test_the_refusal_outranks_every_other_question(self):
        """"Whatever the period holds" - so a contested supply is refused
        for BEING contested, not for the slot being filled, because the
        reason is what an operator acts on."""
        _, why = promotion.should_promote(
            status="green", slot_filled=True, held_without_slot=False,
            has_active_checks=True, contested=True)
        assert "slot is already filled" not in why

    def test_an_uncontested_supply_is_unaffected(self):
        ok, why = promotion.should_promote(
            status="green", slot_filled=False, held_without_slot=False,
            has_active_checks=True)
        assert (ok, why) == (True, None)
