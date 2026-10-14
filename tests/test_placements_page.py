"""What the dashboard is told about a person's placement of a held supply
(REQ-DASH-175): who, when, why and where - recorded decisions only, and only
a PERSON's re-file from no period (criterion 9). Written first."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import test_place_held_supply as place
from pipeline import placements
from qa_tools.common import decision_log as dl
from qa_tools.common import people
from test_place_held_supply import DS, REAL_PERSON, WHEN, _held, _place

conn = place.conn
period = place.period
target = place.target


class TestAPlacementIsSent:
    """Criteria 1, 5 and 8."""

    def test_a_persons_placement_names_the_period_person_time_and_reason(self, conn, period,
                                                                         target):
        supply, _ = _held(conn, period)
        _place(conn, supply, target)
        got = placements.for_dataset(DS, conn)[supply]
        assert got["period"] == target
        assert got["actor"] == people.display_name(REAL_PERSON) and "@" not in got["actor"]
        assert got["reason"] == "supplier's Q3 file"
        assert got["at"].startswith(WHEN[:10])

    def test_the_rules_refile_from_no_period_is_not_a_placement(self, conn, period, target):
        """Criterion 9: a held supply the rule filed once configuration
        covered it keeps the wording it has."""
        supply, _ = _held(conn, period)
        with conn.raw.transaction():
            with dl.apply_decision(conn, dl.Decision(
                    agency_id="child-protection-family-support", collection_id="child-protection",
                    dataset_id=DS, action=dl.REFILE, supply=supply, actor="schedule drain",
                    actor_kind=dl.RULE, effective_at=WHEN, from_slot=None, to_slot=target,
                    reason="dates added")):
                pass
        assert supply not in placements.for_dataset(DS, conn)


class TestClosedOrNotYetOpen:
    """Criterion 2, against the slot's own instants."""

    class _Slot:
        def __init__(self, opens, closes):
            self.claim_opens_at, self.closes_at = opens, closes

    T = datetime(2026, 5, 1, tzinfo=timezone.utc)

    def test_each_of_the_three(self):
        slot = self._Slot(self.T, self.T + timedelta(days=90))
        assert placements.when_received(slot, self.T + timedelta(days=100)) == "closed"
        assert placements.when_received(slot, self.T - timedelta(days=1)) == "not-yet-open"
        assert placements.when_received(slot, self.T + timedelta(days=1)) is None
        assert placements.when_received(None, self.T) is None


class TestDecisionsSayPlaced:
    """Criterion 7: wherever a past decision is described, a placement is
    'placed in <period>', never a re-file - so the build marks it."""

    def test_the_supplys_states_mark_the_placement(self, conn, period, target):
        from pipeline import slot_timeline

        supply, _ = _held(conn, period)
        _place(conn, supply, target)
        entries = slot_timeline.supply_states(DS, conn)[supply]
        (placed,) = [e for e in entries if e["action"] == dl.REFILE]
        assert placed["placedIn"] == target

    def test_only_a_persons_refile_from_no_period(self):
        assert placements.placed_in(dl.REFILE, dl.PERSON, None, "2025-Q1") == "2025-Q1"
        assert placements.placed_in(dl.REFILE, dl.RULE, None, "2025-Q1") is None
        assert placements.placed_in(dl.REFILE, dl.PERSON, "2024-Q4", "2025-Q1") is None
        assert placements.placed_in(dl.PROMOTE, dl.PERSON, None, "2025-Q1") is None
