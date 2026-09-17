"""Shared pytest fixtures for real-tool integration tests (Phase 6,
plans/publishing-and-history.md): qa_tools/{bdm,cp}/run_{dbt,soda,
datacontract,evidently}_*.py's actual output-PARSING logic had zero
test coverage before this - the one test that touches orchestrate_
bdm.py/orchestrate_cp.py (tests/test_orchestrate_reference_run.py)
deliberately monkeypatches every one of these functions out, correctly
for that test's own narrow purpose (checking reference-run forwarding),
but with the side effect that the real "turn this tool's actual output
into our check-result shape" logic was never exercised under pytest at
all - only a full, slow `./run_pipeline.sh` run ever called it.

These fixtures build small, REAL, session-scoped BDM/CP data (real
generator output, real per-run DuckDB warehouses, via this project's
own real loading code) once per test session, so every real-tool test
that uses them doesn't pay the cost of rebuilding from scratch - the
real per-tool invocations (dbt build/soda scan/datacontract-cli/
Evidently) still each pay their own real, unavoidable startup cost,
since genuinely testing "does this correctly parse the real tool's
real output" requires actually running the real tool."""
from __future__ import annotations

import json
from datetime import date

import pytest

from generator.daily_batch import generate_daily_batch
from generator.dirty import apply_birth_registrations_presets

# Real, calibrated defect injection (generator/dirty.py's own "severity:
# 'amber' or 'red' - matches the warn/fail bands ... exactly" contract)
# plus a deliberately much smaller row count than the reference run -
# both real, deterministic ways to force at least one genuine fail/warn
# status out of each of the 4 real tools without hand-crafting fixture
# rows that don't reflect what the real generator actually produces.
_REF_RUN_ID = "pytest_bdm_ref"
_DIRTY_RUN_ID = "pytest_bdm_dirty"


@pytest.fixture(scope="session")
def bdm_raw_dir(tmp_path_factory):
    """A tiny (relative to real production volume), real data/raw/-
    shaped directory: two runs, a clean reference (600 rows - comfortably
    clear of the real Soda row_count check's own 500-row warn floor,
    contract/bdm-birth-registrations-soda-checks.yml - a fixture much
    smaller than that would trip a real check for being implausibly
    small, exactly the kind of thing that check exists to catch) and a
    red-severity dirty run with a real defect injection AND a much
    smaller row count (20 rows, a ~97% drop off the reference - well
    past both that same row_count floor AND evidently's own 25%
    row-count-growth fail threshold) - real generator output, not
    hand-crafted rows."""
    raw_dir = tmp_path_factory.mktemp("bdm_raw")

    ref_df = generate_daily_batch(date(2026, 1, 1), seed=90001, n_rows=600)
    ref_df.to_csv(raw_dir / f"{_REF_RUN_ID}.csv", index=False)

    dirty_df = generate_daily_batch(date(2026, 1, 2), seed=90002, n_rows=20)
    dirty_df = apply_birth_registrations_presets(dirty_df, severity="red", seed=90003, previous_row_count=600)
    dirty_df.to_csv(raw_dir / f"{_DIRTY_RUN_ID}.csv", index=False)

    manifest = [
        {"run_id": _REF_RUN_ID, "file": f"{_REF_RUN_ID}.csv", "run_date": "2026-01-01", "dirty_severity": None},
        {"run_id": _DIRTY_RUN_ID, "file": f"{_DIRTY_RUN_ID}.csv", "run_date": "2026-01-02", "dirty_severity": "red"},
    ]
    with open(raw_dir / "manifest.json", "w") as f:
        json.dump(manifest, f)

    return str(raw_dir)


@pytest.fixture(scope="session")
def bdm_duckdb_dir(tmp_path_factory, bdm_raw_dir):
    """Per-run DuckDB warehouses for bdm_raw_dir's same two runs, built
    via the real qa_tools.bdm.build_per_run_warehouses.build_all() -
    the exact loading code path the real pipeline uses, not a
    hand-rolled copy of it."""
    from qa_tools.bdm.build_per_run_warehouses import build_all

    out_dir = tmp_path_factory.mktemp("bdm_duckdb_runs")
    build_all(raw_dir=bdm_raw_dir, out_dir=str(out_dir))
    return str(out_dir)
