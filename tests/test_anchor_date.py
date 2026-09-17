"""Tests for generator/anchor_date.py's get_anchor_date() - the shared
"today" both generate_runs.py (BDM) and generate_cp_runs.py (CP) anchor
their rolling date windows to, overridable via GENERATOR_ANCHOR_DATE for
reproducing a past regeneration byte-for-byte (module docstring)."""
from __future__ import annotations

from datetime import date

from generator.anchor_date import get_anchor_date


def test_defaults_to_real_wall_clock_today(monkeypatch):
    monkeypatch.delenv("GENERATOR_ANCHOR_DATE", raising=False)
    assert get_anchor_date() == date.today()


def test_honours_the_override_env_var(monkeypatch):
    monkeypatch.setenv("GENERATOR_ANCHOR_DATE", "2026-03-15")
    assert get_anchor_date() == date(2026, 3, 15)
