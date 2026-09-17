"""Tests for pipeline/orchestrate.py's prepare_warehouse() - a thin
local-dev wrapper (regenerate -> load into the combined data/warehouse.duckdb)
that hardcodes real project paths, not overridable like pipeline/load.py's
own load_all(). Genuinely regenerating/loading real project data here
would violate CLAUDE.md's "CI/tests must never touch data/" rule, so this
tests the wiring itself (does regenerate=True call generate_runs.main()
before load_all(), does regenerate=False skip it) via monkeypatched stubs,
not a real end-to-end run."""
from __future__ import annotations

from generator import generate_runs
from pipeline import load as load_mod
from pipeline.orchestrate import DB_PATH, prepare_warehouse


def test_regenerate_true_calls_generate_then_load(monkeypatch):
    calls = []
    monkeypatch.setattr(generate_runs, "main", lambda: calls.append("generate"))
    monkeypatch.setattr(load_mod, "load_all", lambda db_path, raw_dir: calls.append(("load", db_path, raw_dir)))

    prepare_warehouse(regenerate=True)

    assert calls[0] == "generate", "must regenerate before loading, not after"
    assert calls[1][0] == "load"
    assert calls[1][1] == DB_PATH


def test_regenerate_false_skips_generation(monkeypatch):
    calls = []
    monkeypatch.setattr(generate_runs, "main", lambda: calls.append("generate"))
    monkeypatch.setattr(load_mod, "load_all", lambda db_path, raw_dir: calls.append("load"))

    prepare_warehouse(regenerate=False)

    assert calls == ["load"], "regenerate=False must not call generate_runs.main() at all"
