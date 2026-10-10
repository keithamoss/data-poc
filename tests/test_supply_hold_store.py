"""A hold outlives the run that raised it (REQ-PIPE-078).

WHY EVERY TEST USES ITS OWN DATASET ID. A hold is resolved by a
decision, and `qa.decision` is append-only by a database trigger, so
there is no cleaning up between tests. A unique dataset id per test
gives isolation without asking for an exemption from the guarantee -
the same shape `tests/test_decision_log.py` uses and for the same
reason.
"""
from __future__ import annotations

import uuid

import psycopg
import pytest

from qa_tools.common import decision_log as dl
from qa_tools.common import qa_store, supply_db, supply_holds

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-supply-holds") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    return f"cp-{uuid.uuid4().hex[:12]}"


def raise_one(conn, dataset, *, supply="s1", kind=supply_holds.ASSIGNMENT_RULE,
               reason=None, raised_by="cp_run_001", delivery="d-001"):
    return supply_holds.raise_hold(
        conn, dataset_id=dataset, supply_id=supply, kind=kind,
        reason=reason if reason is not None else {
            "unavailable": [["2026-Q1", "already filled"]]},
        raised_by=raised_by, delivery=delivery)


def a_decision(conn, dataset, **over) -> int:
    fields = dict(
        agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
        action=dl.PROMOTE, supply="cp_clients__20260930060000000000",
        actor="keith@example.gov.au", actor_kind=dl.PERSON,
        effective_at="2026-09-30T06:00:00+08:00", to_slot="2026-Q3")
    fields.update(over)
    with dl.apply_decision(conn, dl.Decision(**fields)) as entry_id:
        return entry_id


class TestAHoldIsRecorded:
    """Criterion 1 - naming the supply, the reason and the run."""

    def test_it_names_the_supply_the_reason_and_the_run(self, conn, dataset):
        raise_one(conn, dataset, supply="cp@1", raised_by="cp_run_042")
        [held] = supply_holds.outstanding(conn, dataset_id=dataset)
        assert held.supply_id == "cp@1"
        assert held.raised_by == "cp_run_042"
        assert held.unavailable == (("2026-Q1", "already filled"),)

    def test_an_unknown_kind_is_refused_rather_than_stored(self, conn, dataset):
        """A kind nothing can resolve is a hold nobody can clear, which
        the requirement's own NFR 2 calls indistinguishable from a bug."""
        with pytest.raises(ValueError, match="unknown hold kind"):
            raise_one(conn, dataset, kind="whatever")

    def test_the_retired_delivery_level_kind_is_refused(self, conn, dataset):
        """Criterion 3 used to put two kinds in one place. The
        delivery-level one is retired (REQ-PIPE-105 criterion 6,
        2026-10-02) - two files for one dataset are CONTESTED instead -
        and a kind nothing produces any more is refused, not stored."""
        with pytest.raises(ValueError, match="unknown hold kind"):
            raise_one(conn, dataset, kind="delivery-level")

    def test_each_kind_carries_what_a_person_does_about_it(self, conn, dataset):
        """NFR 2 - the record carries the resolution path, not just the
        fact, and the two kinds need different acts."""
        raise_one(conn, dataset, kind=supply_holds.ASSIGNMENT_RULE,
                   reason={"unavailable": [["2026-Q1", "already filled"]]})
        [held] = supply_holds.outstanding(conn, dataset_id=dataset)
        assert "slot" in " ".join(held.responses)


class TestALaterRunDoesNotClearIt:
    """Criterion 2 - the defect this requirement exists to fix."""

    def test_it_survives_a_second_pass_over_the_same_supply(self, conn, dataset):
        assert raise_one(conn, dataset, raised_by="cp_run_001") is True
        assert raise_one(conn, dataset, raised_by="cp_run_002") is False
        [held] = supply_holds.outstanding(conn, dataset_id=dataset)
        assert held.raised_by == "cp_run_001", \
            "the first run to see it owns when it started"

    def test_only_a_decision_ends_it(self, conn, dataset):
        raise_one(conn, dataset)
        assert supply_holds.outstanding(conn, dataset_id=dataset)
        decision = a_decision(conn, dataset)
        assert supply_holds.resolve(conn, dataset_id=dataset, supply_id="s1",
                                     decision_id=decision) is True
        assert supply_holds.outstanding(conn, dataset_id=dataset) == ()

    def test_resolving_what_nobody_held_is_not_an_error(self, conn, dataset):
        """A promotion of a supply nobody held is the ordinary path,
        not a failure to find something."""
        decision = a_decision(conn, dataset)
        assert supply_holds.resolve(conn, dataset_id=dataset, supply_id="s1",
                                     decision_id=decision) is False


class TestWhichDecisionEndedIt:
    """Criterion 6."""

    def test_the_row_keeps_pointing_at_the_decision(self, conn, dataset):
        raise_one(conn, dataset)
        decision = a_decision(conn, dataset)
        supply_holds.resolve(conn, dataset_id=dataset, supply_id="s1",
                              decision_id=decision)
        row = conn.execute(
            "SELECT resolved_by, resolved_at FROM qa.hold "
            "WHERE dataset_id = ? AND supply_id = ?", [dataset, "s1"]).fetchall()
        assert row[0][0] == decision and row[0][1] is not None

    def test_a_second_decision_does_not_rewrite_which_one_closed_it(
            self, conn, dataset):
        raise_one(conn, dataset)
        first = a_decision(conn, dataset)
        supply_holds.resolve(conn, dataset_id=dataset, supply_id="s1",
                              decision_id=first)
        second = a_decision(conn, dataset, action=dl.DEMOTE,
                     to_slot=None, from_slot="2026-Q3")
        assert supply_holds.resolve(conn, dataset_id=dataset, supply_id="s1",
                                     decision_id=second) is False
        row = conn.execute("SELECT resolved_by FROM qa.hold WHERE dataset_id = ?",
                            [dataset]).fetchall()
        assert row[0][0] == first

    def test_a_resolution_is_whole_or_absent(self, conn, dataset):
        """The database refuses half a resolution - a decision id with
        no instant says a hold closed at no particular time."""
        raise_one(conn, dataset)
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("UPDATE qa.hold SET resolved_at = now() "
                          "WHERE dataset_id = ?", [dataset])


class TestItCountsWithoutReadingEveryRow:
    """Criterion 8, which is a scale requirement rather than a
    micro-optimisation."""

    def test_the_tally_groups_by_dataset_and_by_kind(self, conn, dataset):
        other = f"{dataset}-b"
        raise_one(conn, dataset, supply="s1")
        raise_one(conn, dataset, supply="s2")
        raise_one(conn, other, supply="s1", kind=supply_holds.ASSIGNMENT_RULE,
                   reason={"unavailable": []})
        counted = supply_holds.tally(conn)
        mine = dict(counted.by_dataset)
        assert mine[dataset] == 2 and mine[other] == 1
        assert dict(counted.by_kind)[supply_holds.ASSIGNMENT_RULE] >= 1

    def test_a_resolved_hold_leaves_the_count(self, conn, dataset):
        raise_one(conn, dataset)
        before = dict(supply_holds.tally(conn).by_dataset)[dataset]
        supply_holds.resolve(conn, dataset_id=dataset, supply_id="s1",
                              decision_id=a_decision(conn, dataset))
        assert dataset not in dict(supply_holds.tally(conn).by_dataset)
        assert before == 1

    def test_counting_reads_no_supply_rows(self, conn, dataset):
        """The dashboard build reads this (criterion 4), so it may touch
        recorded observations and nothing else."""
        raise_one(conn, dataset)
        plan = conn.execute(
            "EXPLAIN SELECT dataset_id, count(*) FROM qa.hold "
            "WHERE resolved_by IS NULL GROUP BY dataset_id").fetchall()
        text = " ".join(str(row[0]) for row in plan)
        assert "staging" not in text and "promoted" not in text


class TestWhichDatasetsAreHeldRightNow:
    """What criteria 5 and 9 are asked in practice."""

    def test_it_answers_in_one_query(self, conn, dataset):
        raise_one(conn, dataset)
        assert dataset in supply_holds.held_datasets(conn)

    def test_a_resolved_hold_is_not_held(self, conn, dataset):
        raise_one(conn, dataset)
        supply_holds.resolve(conn, dataset_id=dataset, supply_id="s1",
                              decision_id=a_decision(conn, dataset))
        assert dataset not in supply_holds.held_datasets(conn)

    def test_an_empty_scope_asks_nothing(self, conn):
        assert supply_holds.held_datasets(conn, dataset_ids=[]) == frozenset()
