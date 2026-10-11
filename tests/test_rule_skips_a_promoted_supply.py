"""The promotion rule records nothing against a supply a person has
already promoted - a guard, not a regression test.

Written 2026-10-11 to reproduce what looked like a defect while planting
TS-43 (REQ-GEN-185): the decision log read "promoted by a person" and then
"promotion-withheld" by the rule. It did NOT reproduce - the rule already
defers to a person's decision. The real cause was the REPLAY: the rule ran
at TS-43's own arrival but its invented lag stamped it the next day, after
the scripted promotion's instant, so the log read in the wrong order. The
lag is now capped at the claim window (Keith, 2026-10-11). This keeps the
behaviour that turned out to be right.
"""
from __future__ import annotations

import uuid

import pytest

from qa_tools.common import amber_setting
from qa_tools.common import decision_log as dl
from qa_tools.common import promotion, qa_store, supply_db

AGENCY = "registry-services"
COLLECTION = "civil-registration"
SLOT = "2099-09-05"
WHEN = "2099-09-05T18:00:00+08:00"


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-rule-skips-promoted") as c:
        qa_store.ensure_schema(c)
        yield c


@pytest.fixture
def dataset():
    return f"bdm-{uuid.uuid4().hex[:12]}"


def _promoted_by_a_person(conn, dataset, supply):
    with dl.apply_decision(conn, dl.Decision(
            agency_id=AGENCY, collection_id=COLLECTION, dataset_id=dataset,
            action=dl.PROMOTE, supply=supply, actor="someone@example.gov.au",
            actor_kind=dl.PERSON, effective_at="2099-09-05T17:00:00+08:00", to_slot=SLOT,
            reason="accepted")):
        pass
    conn.commit()


def test_an_amber_supply_a_person_promoted_gets_no_withheld_note(conn, dataset, monkeypatch):
    supply = f"{dataset}@209909051400000800"
    _promoted_by_a_person(conn, dataset, supply)
    assert dl.promoted_into(conn, dataset, SLOT) == supply, "precondition"
    monkeypatch.setattr(promotion, "status_of", lambda *a, **k: "amber")
    monkeypatch.setattr(amber_setting, "resolve", lambda *a, **k: type(
        "R", (), {"value": "hold", "level": "data asset", "version": "2099-09-01"})())
    out = promotion.after_run(
        conn, agency_id=AGENCY, collection_id=COLLECTION,
        supplies=[dict(dataset_id=dataset, supply=supply, period=SLOT,
                       physical_tables=["t"])],
        results=[], reads={}, actor=promotion.RULE_ACTOR, actor_kind=dl.RULE,
        effective_at=WHEN)
    actions = [d["action"] for d in dl.decisions_for(conn, dataset)]
    assert actions == [dl.PROMOTE], actions
    assert "a person has already decided" in out.refused[dataset]
