"""A dataset whose participation is VERSIONED, owing nothing for one quarter
and everything again afterwards (REQ-GEN-251), is owed nothing in that
quarter - read from the version in force on the period's own date.

A REAL DEFECT FOUND PLANNING REQ-GEN-205 (2026-10-18): inheritance asked
`schedule.delivery_months(dataset)` with no date, so it read the NEWEST
participation version. A gap that is a middle version - owed, then not, then
owed again - was never seen, and the gap quarter inherited nothing.
"""
from __future__ import annotations

import yaml

from qa_tools.common import agreement, inheritance

ED = "ed-presentations"


def _with_gap(tmp_path, monkeypatch):
    """The real calendar, with ED owing nothing for 2024-Q2 (May) alone."""
    raw = yaml.safe_load(agreement.CALENDAR_YAML.read_text())
    entry = next(d for d in raw["datasets"] if d["id"] == ED)
    first = entry["participation"]["versions"][0]
    note = [{"date": "2026-10-18", "author": "test", "change": "a gap for a test"}]
    entry["participation"]["versions"] = [
        first,
        {"effective_from": "2024-04-01", "participates": ["February", "August", "November"],
         "reason": "Not owed for May 2024, for a test.", "changelog": note},
        {"effective_from": "2024-06-01", "changelog": note},
    ]
    path = tmp_path / "calendar.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    monkeypatch.setattr(agreement, "CALENDAR_YAML", path)


def test_the_gap_quarter_is_owed_nothing(tmp_path, monkeypatch):
    _with_gap(tmp_path, monkeypatch)
    owes_nothing, reason = inheritance._does_not_participate(ED, "2024-Q2")
    assert owes_nothing, "the version in force for 2024-Q2 owes nothing for May"
    assert "May" not in reason and "February" in reason


def test_the_quarters_either_side_are_still_owed(tmp_path, monkeypatch):
    _with_gap(tmp_path, monkeypatch)
    assert not inheritance._does_not_participate(ED, "2024-Q1")[0]
    assert not inheritance._does_not_participate(ED, "2024-Q3")[0]
