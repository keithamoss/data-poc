"""A held supply or a contested table is one dataset-level signal, open
from its receipt until a decision ends it (REQ-PIPE-115 criteria 8, 12,
24 and 27)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import filing_support
from qa_tools.common import (dataset_blockers, load_log, outstanding, qa_store,
                             supply_db, supply_holds)

DATASET = "cp-case-workers"
RECEIVED = datetime(2030, 3, 4, 5, 6, 7, tzinfo=timezone.utc)
DELIVERY = "pytest-contested-pair"


@pytest.fixture(autouse=True)
def _own_instant(monkeypatch):
    import uuid

    global RECEIVED
    RECEIVED = datetime(2030, 3, 4, tzinfo=timezone.utc) + timedelta(
        seconds=uuid.uuid4().int % 10_000_000)


@pytest.fixture
def clean(supply_dsn):
    with supply_db.connect(label="test-blockers") as conn:
        qa_store.ensure_schema(conn)
        # qa.decision is append-only, so it is never truncated: each test
        # takes its own receipt instant instead, which keeps a decision
        # from an earlier test from answering this one's contest.
        for table in ("hold", "load_outcome", "filing", "delivery_file", "delivery"):
            conn.execute(f'TRUNCATE "{qa_store.SCHEMA}"."{table}" CASCADE')
        yield conn
        # Nothing this module raised may outlive it: an open hold withholds
        # its table from every later run on the worker, and a failed load
        # record makes a later run's own table read as refused.
        for table in ("hold", "load_outcome"):
            conn.execute(f'TRUNCATE "{qa_store.SCHEMA}"."{table}" CASCADE')


def _pair(names=("cp_case_workers.csv", "cp_case_workers_v2.csv")):
    for name in names:
        filing_support.ensure_delivery(DELIVERY, DATASET, RECEIVED, filename=name)


def _key():
    return supply_db.arrival_segment(RECEIVED.isoformat())


class TestATableTwoFilesClaimRaisesOneDatasetItem:
    """Criterion 8."""

    def test_it_is_dataset_scoped_blocking_and_names_both_files(self, clean):
        _pair()
        items = [i for i in outstanding.survey(clean).items
                 if i.kind == outstanding.CONTESTED_TABLE]
        assert len(items) == 1
        item = items[0]
        assert item.dataset_id == DATASET and item.blocking
        assert "cp_case_workers.csv" in item.detail and "cp_case_workers_v2.csv" in item.detail
        assert "choose" in item.headline

    def test_it_is_not_the_contested_file_kind(self, clean):
        """The opposite case - one file claimed by several datasets - keeps
        its own label."""
        _pair()
        assert not [i for i in outstanding.survey(clean).items
                    if i.kind == outstanding.CONTESTED_FILE]

    def test_one_file_is_not_a_contest(self, clean):
        _pair(names=("cp_case_workers.csv",))
        assert not [i for i in outstanding.survey(clean).items
                    if i.kind == outstanding.CONTESTED_TABLE]


class TestAPairWithARefusedFileStaysContested:
    """Criteria 24 and 27."""

    def test_the_contest_names_the_refused_file_and_no_failed_load_item_is_raised(
            self, clean):
        _pair()
        load_log.record(DELIVERY, DATASET, f"cp_case_workers__{_key()}__2",
                        load_log.FAILED, RECEIVED.isoformat(), reason="bad header")
        items = outstanding.survey(clean).items
        contested = [i for i in items if i.kind == outstanding.CONTESTED_TABLE]
        assert len(contested) == 1
        assert "cp_case_workers_v2.csv could not be loaded (bad header)" in contested[0].detail
        assert not [i for i in items if i.kind == outstanding.FAILED_LOAD], (
            "one dataset's one problem is one item")

    def test_a_refused_load_outside_any_contest_is_still_its_own_item(self, clean):
        _pair(names=("cp_case_workers.csv",))
        load_log.record(DELIVERY, DATASET, f"cp_case_workers__{_key()}",
                        load_log.FAILED, RECEIVED.isoformat(), reason="bad header")
        assert [i for i in outstanding.survey(clean).items
                if i.kind == outstanding.FAILED_LOAD]


class TestOpenFromTheReceiptInstant:
    """Criterion 12: open from the supply's own receipt - not from when
    the hold was recorded - until the decision that ended it."""

    def test_a_hold_opens_at_its_receipt_not_when_it_was_raised(self, clean):
        filing_support.ensure_delivery(DELIVERY, DATASET, RECEIVED)
        supply_holds.raise_hold(clean, dataset_id=DATASET, supply_id=f"{DATASET}@{_key()}",
                                kind=supply_holds.ASSIGNMENT_RULE, reason={},
                                raised_by="t", delivery=DELIVERY)
        (blocker,) = dataset_blockers.all_blockers(clean)
        assert blocker.kind == dataset_blockers.HELD and blocker.is_open
        assert datetime.fromisoformat(blocker.opened_at) == RECEIVED
        assert not blocker.open_at(RECEIVED - timedelta(seconds=1))
        assert blocker.open_at(RECEIVED)

    def test_a_contest_closes_when_a_decision_about_its_arrival_takes_effect(self, clean):
        from qa_tools.common import decision_log

        _pair()
        decided = RECEIVED + timedelta(days=2)
        with decision_log.apply_decision(clean, decision_log.Decision(
            agency_id="a", collection_id="c", dataset_id=DATASET,
            action=decision_log.REJECT, supply=f"cp_case_workers__{_key()}__2",
            from_slot="2030-Q1",
            actor="person@example.com", actor_kind=decision_log.PERSON,
            reason="the second file was a mistake", effective_at=decided.isoformat())):
            pass
        (blocker,) = dataset_blockers.all_blockers(clean)
        assert blocker.kind == dataset_blockers.CONTESTED
        assert blocker.open_at(decided - timedelta(seconds=1))
        assert not blocker.open_at(decided)
        assert not [i for i in outstanding.survey(clean).items
                    if i.kind == outstanding.CONTESTED_TABLE]

    def test_the_whole_life_reaches_the_built_record(self, clean):
        _pair()
        record = outstanding.survey(clean).as_record()
        (blocker,) = record["blockers"]
        assert blocker["kind"] == "contested" and blocker["resolvedAt"] is None
        assert blocker["datasetId"] == DATASET


class TestTheFailedLoadItemOpensAtTheReceipt:
    """post-build-review #118 D-B (REQ-DASH-148 criterion 3): the failed-load
    ITEM is open from the supply's receipt, as its blocker is - not from when
    the load record happened to be written, which on a replayed history is
    the night of the rebuild and hid the item on the scenario's own date."""

    def test_its_observed_instant_is_the_receipt(self, clean):
        _pair(names=("cp_case_workers.csv",))
        written = (RECEIVED + timedelta(days=200)).isoformat()
        load_log.record(DELIVERY, DATASET, f"cp_case_workers__{_key()}",
                        load_log.FAILED, written, reason="bad header")
        (item,) = [i for i in outstanding.survey(clean).items
                   if i.kind == outstanding.FAILED_LOAD]
        assert datetime.fromisoformat(item.observed_at) == RECEIVED

    def test_its_reason_ends_its_sentence(self, clean):
        """D-G: '...were expected Nothing can read the table' ran together."""
        _pair(names=("cp_case_workers.csv",))
        load_log.record(DELIVERY, DATASET, f"cp_case_workers__{_key()}",
                        load_log.FAILED, RECEIVED.isoformat(), reason="bad header")
        (item,) = [i for i in outstanding.survey(clean).items
                   if i.kind == outstanding.FAILED_LOAD]
        assert "bad header. Nothing can read" in item.detail

    def test_the_blockers_reason_has_one_full_stop(self, clean):
        """#118 D-G's follow-on: a recorded reason now ends its own sentence,
        and the blocker added another - 'were expected.. Nothing'."""
        _pair(names=("cp_case_workers.csv",))
        load_log.record(DELIVERY, DATASET, f"cp_case_workers__{_key()}",
                        load_log.FAILED, RECEIVED.isoformat(), reason="bad header.")
        (blocker,) = [b for b in dataset_blockers.all_blockers(clean)
                      if b.kind == dataset_blockers.REFUSED]
        assert ".." not in blocker.reason and "bad header. Nothing" in blocker.reason
