"""Emergency Department's generator provider (REQ-GEN-232) and the two
scenarios planted on it (REQ-GEN-236), driven through the shared driver into a
scratch directory - never the repository's own data/."""
from __future__ import annotations

import csv
import hashlib
import io
import json

import pytest

from generator import driver
from generator.output import redirect

ED = "emergency-department"
COLUMNS = ["presentation_id", "arrival_datetime", "triage_category", "age_group", "sex",
           "postcode", "departure_status", "length_of_stay_minutes"]


def _generate(root):
    undo = redirect(root)
    try:
        return driver.generate(ED)
    finally:
        undo()


def _tree(root) -> dict[str, str]:
    """Every delivered and receipt file under `root`, by path, as a digest."""
    out = {}
    for sub in ("deliveries", "receipts"):
        for path in sorted((root / sub).rglob("*")):
            if path.is_file():
                out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert out, f"nothing was generated under {root}"
    return out


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    root = tmp_path_factory.mktemp("ed")
    manifest = _generate(root)
    return root, manifest


class TestTheProvider:
    def test_two_generations_with_the_same_seed_are_byte_identical(self, generated,
                                                                    tmp_path):
        """Criterion 8: deliveries and receipts, file for file."""
        root, _manifest = generated
        _generate(tmp_path)
        assert _tree(tmp_path) == _tree(root)

    def test_each_supply_is_one_file_with_the_contracts_eight_columns(self, generated):
        """Criterion 1."""
        root, manifest = generated
        for entry in manifest:
            files = list((root / "deliveries" / entry["delivery"]).iterdir())
            assert [f.name for f in files] == ["ed_presentations.csv"], entry["delivery"]
            header = next(csv.reader(io.StringIO(files[0].read_text())))
            assert header == COLUMNS

    def test_the_ordinary_quarters_carry_child_protections_severity_mix(self, generated):
        """Criterion 3: the oldest clean, two reds each with a resupply after
        it, and about a quarter of the quarters amber."""
        _root, manifest = generated
        first_by_period = {}
        for entry in manifest:
            first_by_period.setdefault(entry["period"], entry)
        firsts = list(first_by_period.values())
        severities = [e["dirty_severity"] for e in firsts]
        assert severities[0] is None
        assert severities.count("red") == 2
        assert round(len(firsts) * 0.25) - 1 <= severities.count("amber") <= round(len(firsts) * 0.25) + 1
        for entry in firsts:
            if entry["dirty_severity"] == "red":
                after = [e for e in manifest if e["period"] == entry["period"]]
                assert len(after) >= 2, f"{entry['period']}'s red has no resupply"

    def test_postcodes_come_from_the_wa_pool(self, generated):
        """Criterion 5."""
        from generator.names_au import SUBURBS

        pool = {postcode for _suburb, postcode in SUBURBS}
        root, manifest = generated
        seen = set()
        for entry in manifest:
            path = root / "deliveries" / entry["delivery"] / "ed_presentations.csv"
            seen |= {row["postcode"] for row in csv.DictReader(io.StringIO(path.read_text()))}
        seen.discard("")
        assert seen and seen <= pool


class TestTheQuarterlyArrivalsJustOutsideTheWindow:
    """REQ-GEN-236: TS-3a and TS-3b - shapes only, placed by anchor."""

    def _placements(self, root):
        placed = json.loads((root / "scenario_placements.json").read_text())
        items = placed if isinstance(placed, list) else placed.get("placements", placed)
        items = items if isinstance(items, list) else list(items.values())
        return {p["scenario_id"]: p for p in items}

    def test_ts_3a_arrives_a_day_before_its_quarters_window_with_the_previous_filled(
            self, generated):
        root, manifest = generated
        placed = self._placements(root)["TS-3a"]
        quarter = placed["period"]
        [early] = [e for e in manifest if e["period"] == quarter]
        assert early["received_at"].startswith(_fifteen_days_before(quarter) + "T10:00")
        previous = _previous(quarter)
        assert [e for e in manifest if e["period"] == previous], f"{previous} must be filled"

    def test_ts_3b_is_the_same_arrival_with_the_previous_quarter_suppressed(self, generated):
        root, manifest = generated
        placed = self._placements(root)["TS-3b"]
        quarter = placed["period"]
        [early] = [e for e in manifest if e["period"] == quarter]
        assert early["received_at"].startswith(_fifteen_days_before(quarter) + "T10:00")
        assert not [e for e in manifest if e["period"] == _previous(quarter)]

    def test_neither_generates_a_resupply(self, generated):
        """Criterion 3: the arrival shape only."""
        root, manifest = generated
        for scenario in ("TS-3a", "TS-3b"):
            quarter = self._placements(root)[scenario]["period"]
            assert len([e for e in manifest if e["period"] == quarter]) == 1


def _quarter_date(name: str):
    from datetime import date

    year, q = name.split("-Q")
    return date(int(year), {1: 2, 2: 5, 3: 8, 4: 11}[int(q)], 1)


def _fifteen_days_before(name: str) -> str:
    from datetime import timedelta

    return (_quarter_date(name) - timedelta(days=15)).isoformat()


def _previous(name: str) -> str:
    year, q = (int(x) for x in name.split("-Q"))
    return f"{year - 1}-Q4" if q == 1 else f"{year}-Q{q - 1}"
