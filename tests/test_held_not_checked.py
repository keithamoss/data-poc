"""A held supply is not checked, and what reads it goes red
(REQ-PIPE-078 criteria 9 and 10).

ONE MECHANISM, TWO CRITERIA, which is why they are tested together.
Withholding the view is what stops the held supply being checked, and
it is also what makes every cross-table check reading it unanswerable -
so a test that covered only the first would leave the second looking
like separate work.
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import held_blast_radius, qa_store, supply_db, supply_holds

CP = "child-protection"
AGENCY = "child-protection-family-support"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-held-not-checked") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def staged(conn):
    """Two real staged tables in this worker's own staging schema."""
    run_id = f"heldrun_{uuid.uuid4().hex[:8]}"
    staging = supply_db.staging_schema_for(run_id)
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{staging}"')
    for physical in ("cp_clients__20260930010000000000",
                      "cp_placements__20260930010000000000"):
        conn.execute(f'DROP TABLE IF EXISTS "{staging}"."{physical}"')
        conn.execute(f'CREATE TABLE "{staging}"."{physical}" (id int)')
        conn.execute(f'INSERT INTO "{staging}"."{physical}" VALUES (1)')
    yield run_id, staging
    conn.execute(f'DROP SCHEMA IF EXISTS "{supply_db.run_schema(run_id)}" CASCADE')


CANDIDATES = {"cp_clients": ["cp_clients__20260930010000000000"],
              "cp_placements": ["cp_placements__20260930010000000000"]}


class TestAHeldSupplyGetsNoView:
    """Criterion 9. The mechanism, not a rule anybody has to remember:
    nothing can read what has no view."""

    def test_without_a_hold_both_tables_resolve(self, conn, staged):
        run_id, staging = staged
        res = supply_db.create_run_views(conn, run_id, CANDIDATES,
                                          source_schema=staging)
        assert set(res.resolved) == {"cp_clients", "cp_placements"}
        assert res.held == {}

    def test_a_held_table_is_withheld_and_the_others_are_not(self, conn, staged):
        run_id, staging = staged
        res = supply_db.create_run_views(conn, run_id, CANDIDATES,
                                          source_schema=staging,
                                          held=["cp_clients"])
        assert set(res.resolved) == {"cp_placements"}, \
            "one held dataset must not cost the others their QA"
        assert res.held == {"cp_clients": "cp_clients__20260930010000000000"}

    def test_nothing_can_select_from_the_held_table(self, conn, staged):
        run_id, staging = staged
        supply_db.create_run_views(conn, run_id, CANDIDATES,
                                    source_schema=staging, held=["cp_clients"])
        schema = supply_db.run_schema(run_id)
        views = {r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = ?", [schema]).fetchall()}
        assert views == {"cp_placements"}

    def test_it_records_which_physical_table_is_being_withheld(self, conn, staged):
        """Resolving the hold means somebody looking at that supply, so
        'something is held' is not enough."""
        run_id, staging = staged
        res = supply_db.create_run_views(conn, run_id, CANDIDATES,
                                          source_schema=staging, held=["cp_clients"])
        assert res.held["cp_clients"].startswith("cp_clients__")


class TestHeldIsNotTheSameAsAbsent:
    """The Resolution keeps three reasons apart because they mean
    different things to whoever has to fix them."""

    def test_held_does_not_land_in_absent(self, conn, staged):
        run_id, staging = staged
        res = supply_db.create_run_views(conn, run_id, CANDIDATES,
                                          source_schema=staging, held=["cp_clients"])
        assert "cp_clients" not in res.absent
        assert "cp_clients" not in res.ambiguous

    def test_a_table_that_never_arrived_is_still_absent(self, conn, staged):
        run_id, staging = staged
        res = supply_db.create_run_views(
            conn, run_id, dict(CANDIDATES, cp_carers=[]),
            source_schema=staging, held=["cp_clients"])
        assert res.absent == ["cp_carers"] and "cp_clients" in res.held

    def test_unreadable_covers_all_three(self, conn, staged):
        run_id, staging = staged
        res = supply_db.create_run_views(
            conn, run_id, dict(CANDIDATES, cp_carers=[]),
            source_schema=staging, held=["cp_clients"])
        assert res.unreadable == ["cp_carers", "cp_clients"]

    def test_it_survives_the_round_trip_to_the_record(self, conn, staged):
        run_id, staging = staged
        res = supply_db.create_run_views(conn, run_id, CANDIDATES,
                                          source_schema=staging, held=["cp_clients"])
        supply_db.record_resolution(conn, res)
        back = supply_db.resolution_for(conn, run_id)
        assert back.held == res.held
        assert "cp_clients" not in back.absent

    def test_the_committed_form_carries_it(self, conn, staged):
        run_id, staging = staged
        res = supply_db.create_run_views(conn, run_id, CANDIDATES,
                                          source_schema=staging, held=["cp_clients"])
        assert res.as_record()["held"] == {
            "cp_clients": "cp_clients__20260930010000000000"}


class TestTheHoldStoreDecidesWhichTables:
    """The two warehouse builders ask one question rather than three
    copies of a lookup.

    A DATABASE OF ITS OWN, and it was not optional - this class raises
    a hold against a REAL dataset id, which is the point of it. On the
    worker's shared database that hold outlived the test, so every
    later CP run withheld `cp_clients`' view and three integration
    tests in two other modules went red on a table that was fine. The
    test was right and its blast radius was the whole worker.
    """

    @pytest.fixture(autouse=True)
    def _alone(self, private_supply_dsn):
        return private_supply_dsn

    def test_a_held_dataset_becomes_its_table_name(self, conn):
        dataset = "cp-clients"
        key = f"k{uuid.uuid4().hex[:8]}"
        supply_holds.raise_hold(conn, dataset_id=dataset, supply_id=f"{dataset}@{key}",
                                 kind=supply_holds.ASSIGNMENT_RULE,
                                 reason={"unavailable": []}, raised_by="r1")
        assert "cp_clients" in supply_holds.held_tables(conn, arrival_key=key)
        # Scoped to the hold's own arrival since 2026-10-05.
        assert "cp_clients" not in supply_holds.held_tables(conn, arrival_key="another")

    def test_a_dataset_the_tree_does_not_know_is_skipped(self, conn):
        """A hold outlives the schedule it was raised under, and a run
        that cannot start because a retired dataset is still held is a
        worse failure than a view nothing reads."""
        gone = f"cp-retired-{uuid.uuid4().hex[:8]}"
        supply_holds.raise_hold(conn, dataset_id=gone, supply_id="s1",
                                 kind=supply_holds.ASSIGNMENT_RULE,
                                 reason={"unavailable": []}, raised_by="r1")
        assert supply_holds.held_tables(conn, arrival_key="s1") is not None


HELD = {"cp_clients": "cp_clients__20260930010000000000"}
READS = {
    f"data-asset-1.{AGENCY}.{CP}.cp-placements.client_id.referential_integrity_soda":
        ["cp_clients"],
    f"data-asset-1.{AGENCY}.{CP}.cp-notifications.client_id.referential_integrity_soda":
        ["cp_clients"],
    f"data-asset-1.{AGENCY}.{CP}.cp-carers.carer_id.some_other_check_soda":
        ["cp_carers"],
}


class TestACrossTableCheckReadingItGoesRed:
    """Criterion 10."""

    def test_each_check_reading_the_held_table_is_red(self):
        out = held_blast_radius.results_for(
            held=HELD, reads=READS, run_id="r1", run_timestamp="2026-09-30T06:00:00+08:00")
        assert len(out) == 2
        assert {r["status"] for r in out} == {"fail"}

    def test_it_names_the_held_table_as_the_reason(self):
        out = held_blast_radius.results_for(
            held=HELD, reads=READS, run_id="r1", run_timestamp="t")
        for result in out:
            assert result["held_table"] == "cp_clients"
            assert "cp_clients" in result["held_reason"]
            assert "cp_clients__20260930010000000000" in result["held_reason"]

    def test_it_says_the_check_did_not_fail(self):
        """A check that could not be evaluated is not a verdict on
        anybody's data, and the text has to say so - red is the honest
        report of 'unanswerable', not of 'bad'."""
        [one, _] = held_blast_radius.results_for(
            held=HELD, reads=READS, run_id="r1", run_timestamp="t")
        assert "did not fail" in one["held_reason"]
        assert "could not be evaluated" in one["held_reason"]

    def test_a_check_reading_nothing_held_is_untouched(self):
        out = held_blast_radius.results_for(
            held=HELD, reads=READS, run_id="r1", run_timestamp="t")
        assert not any(r["dataset_id"] == "cp-carers" for r in out)

    def test_the_held_datasets_own_checks_produce_nothing(self):
        """Criterion 9's other half - no check result is recorded
        against a supply that has no period."""
        own = {f"data-asset-1.{AGENCY}.{CP}.cp-clients.id.not_null_soda": ["cp_clients"]}
        assert held_blast_radius.results_for(
            held=HELD, reads=own, run_id="r1", run_timestamp="t") == []

    def test_a_check_reading_two_held_tables_reports_both(self):
        both = {f"data-asset-1.{AGENCY}.{CP}.cp-placements.x.joint_check_soda":
                ["cp_clients", "cp_carers"]}
        out = held_blast_radius.results_for(
            held={"cp_clients": "a", "cp_carers": "b"}, reads=both,
            run_id="r1", run_timestamp="t")
        assert sorted(r["held_table"] for r in out) == ["cp_carers", "cp_clients"]

    def test_no_holds_means_no_results(self):
        assert held_blast_radius.results_for(
            held={}, reads=READS, run_id="r1", run_timestamp="t") == []

    def test_an_unparseable_check_id_is_skipped_rather_than_fatal(self):
        assert held_blast_radius.results_for(
            held=HELD, reads={"not a check id": ["cp_clients"]},
            run_id="r1", run_timestamp="t") == []

    def test_the_result_is_scoped_to_the_reading_dataset(self):
        out = held_blast_radius.results_for(
            held=HELD, reads=READS, run_id="r1", run_timestamp="t")
        assert {r["dataset_id"] for r in out} == {"cp-placements", "cp-notifications"}
        assert {r["collection_id"] for r in out} == {CP}


class TestItIsReportedAsOneThing:
    """Same reason the holds themselves aggregate."""

    def test_one_line_for_the_whole_class(self):
        out = held_blast_radius.results_for(
            held=HELD, reads=READS, run_id="r1", run_timestamp="t")
        line = held_blast_radius.describe(out)
        assert line.count("\n") == 0 and "2 check(s)" in line

    def test_nothing_to_say_when_nothing_is_held(self):
        assert held_blast_radius.describe([]) == ""
