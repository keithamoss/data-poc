"""The Cancer and Mental Health providers (REQ-GEN-349, REQ-GEN-351, criteria
2, 3 and 5's first half), each driven alone through the shared driver into a
scratch directory - never the repository's own data/.

Each generates alone, as Emergency Department's provider test does, so its
delivery names are its own rather than chosen around another collection's.
The scenario arrivals (TS-114 to TS-117) are placed by REQ-GEN-349/351
criterion 4 and tested by tests/test_annual_participation.py and
tests/test_weekly_participation.py; here they are named and left out of the
window rule, which is about the ordinary supplies.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime

import pytest

from asset_model import slots
from generator import driver
from generator.output import redirect

UNTIL = date(2026, 12, 31)


def _generate(collection, root):
    undo = redirect(root)
    try:
        return driver.generate(collection)
    finally:
        undo()


def _tree(root) -> dict[str, str]:
    out = {}
    for sub in ("deliveries", "receipts"):
        for path in sorted((root / sub).rglob("*")):
            if path.is_file():
                out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert out, f"nothing was generated under {root}"
    return out


def _firsts(book):
    """The first arrival of each period, in order."""
    seen = {}
    for entry in book:
        seen.setdefault(entry["period"], entry)
    return list(seen.values())


class _Provider:
    collection: str
    dataset: str
    #: received_at of the planted scenario arrivals, which criterion 2's
    #: window rule does not govern.
    scenario_arrivals: frozenset[str] = frozenset()
    #: Days from a failing supply to its passing resupply.
    resupply_gap: tuple[int, int] = (5, 20)

    @pytest.fixture(scope="class")
    def book(self, tmp_path_factory):
        return _generate(self.collection, tmp_path_factory.mktemp(self.collection))

    def test_two_generations_with_the_same_seed_are_byte_identical(self, tmp_path):
        """Criterion 5's first half: deliveries and receipts, file for file."""
        first = _generate(self.collection, tmp_path / "a")
        assert _generate(self.collection, tmp_path / "b") == first
        assert _tree(tmp_path / "b") == _tree(tmp_path / "a")

    def test_every_owed_round_has_one_ordinary_supply_inside_its_window(self, book):
        """Criterion 2: one first arrival per owed round, received inside its
        claim window and before its due time."""
        owed = {s.name: s for s in slots.slots_for_dataset(self.dataset, until=UNTIL)}
        firsts = _firsts(book)
        assert len(firsts) >= 10, "test precondition - a history of owed rounds"
        assert {e["period"] for e in firsts} <= set(owed), sorted({e["period"] for e in firsts} - set(owed))
        for entry in firsts:
            slot = owed[entry["period"]]
            got = datetime.fromisoformat(entry["received_at"])
            assert slot.claim_opens_at <= got <= slot.due_at, (entry["run_id"], got, slot.due_at)
        others = [e for e in book if e not in firsts and e["dirty_severity"] is None]
        assert all(e["received_at"] in self.scenario_arrivals or
                   any(f["period"] == e["period"] and f["dirty_severity"] == "red" for f in firsts)
                   for e in others), [e["run_id"] for e in others]

    def test_no_two_supplies_share_a_receipt_instant(self, book):
        """Criterion 2's refusal (REQ-GEN-334 criterion 13)."""
        instants = [e["received_at"] for e in book]
        assert len(instants) == len(set(instants))

    def test_the_ordinary_severity_mix(self, book):
        """Criterion 3: the oldest passing, about a quarter warning, at least
        one failing with a passing resupply - five to twenty days later on the
        quarterly asset (REQ-GEN-349), the same day on the daily one, as Birth
        Registrations' resupplies come (REQ-GEN-351's "the collections' mix")."""
        firsts = _firsts(book)
        severities = [e["dirty_severity"] for e in firsts]
        assert severities[0] is None
        quarter = round(len(firsts) * 0.25)
        assert quarter - 1 <= severities.count("amber") <= quarter + 1, severities
        reds = [e for e in firsts if e["dirty_severity"] == "red"]
        assert reds, severities
        for red in reds:
            after = [e for e in book if e["period"] == red["period"] and e is not red]
            assert after and after[0]["dirty_severity"] is None, red["run_id"]
            gap = (datetime.fromisoformat(after[0]["received_at"])
                   - datetime.fromisoformat(red["received_at"])).days
            assert self.resupply_gap[0] <= gap <= self.resupply_gap[1], (red["run_id"], gap)


@pytest.mark.asset("quarterly")
class TestTheCancerProvider(_Provider):
    collection = "cancer"
    dataset = "cancer-notifications"
    scenario_arrivals = frozenset({"2024-11-01T10:00:00+08:00"})  # TS-114


@pytest.mark.asset("daily")
class TestTheMentalHealthProvider(_Provider):
    collection = "mental-health"
    dataset = "mental-health-contacts"
    resupply_gap = (0, 0)

    @pytest.fixture(scope="class")
    def book(self, tmp_path_factory):
        book = _generate(self.collection, tmp_path_factory.mktemp(self.collection))
        # TS-117's Tuesday arrival, found by its weekday rather than a date.
        type(self).scenario_arrivals = frozenset(
            e["received_at"] for e in book
            if datetime.fromisoformat(e["received_at"]).weekday() == 1)
        return book


#: The quarterly asset by default; the Mental Health class names the daily.
pytestmark = pytest.mark.asset("quarterly")
