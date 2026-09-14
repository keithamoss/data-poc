"""
Prep step: generate -> load into the combined warehouse
(data/warehouse.duckdb), deterministically (every generator call is
seeded).

Used to also run four hand-written equivalent check engines here too -
engines/*.py, built when the original session had no PyPI access. That
constraint is gone and those engines had already drifted out of sync with
newer checks (Child Protection, the row-count-growth/freshness checks)
that were only ever built real-tools-only - so they were removed rather
than kept half-maintained. See plans/wider.md's repo-tidy-up entries for
the full history.

What's left here is still a real prerequisite, not a leftover: this
combined warehouse (one `birth_registrations` table, tagged by run_id) is
what pipeline/build_dashboard_data.py's own direct DuckDB queries (e.g.
the sex value-count chart) run against - real_tools/orchestrate_real.py
builds its own separate PER-RUN warehouses for dbt/Soda to connect to,
but doesn't build this combined one.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "generator"))
sys.path.insert(0, os.path.dirname(__file__))

ROOT = os.path.join(os.path.dirname(__file__), "..")
DB_PATH = os.path.join(ROOT, "data", "warehouse.duckdb")


def prepare_warehouse(regenerate: bool = True) -> None:
    if regenerate:
        import generate_runs
        generate_runs.main()

    import load as load_mod
    load_mod.load_all(DB_PATH, os.path.join(ROOT, "data", "raw"))
    print(f"Loaded combined warehouse -> {DB_PATH}")


if __name__ == "__main__":
    prepare_warehouse(regenerate=True)
