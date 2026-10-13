"""Settling a contested pair - choose-file (REQ-PIPE-193)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from qa_tools.common import decision_log, qa_store, rejection, supply_db

DATASET = "cp-case-workers"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-choose-file") as c:
        qa_store.ensure_schema(c)
        yield c


class TestASettlementDoesNotBarAutomaticPromotion:
    """Criterion 22: the person said which file to judge, not whether to
    accept it - the gate may promote the settled supply."""

    def test_a_choose_file_is_not_a_decision_about_its_data(self, conn):
        supply = f"{DATASET}@{uuid.uuid4().int % 10**18:018d}#1"
        at = datetime(2031, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=1)
        with decision_log.apply_decision(conn, decision_log.Decision(
                agency_id="a", collection_id="c", dataset_id=DATASET,
                action=decision_log.CHOOSE_FILE, supply=supply, from_slot="2031-Q1",
                actor="p@example.com", actor_kind=decision_log.PERSON, reason="r",
                effective_at=at.isoformat())):
            pass
        assert not rejection.decided_by_a_person(conn, DATASET, supply)
