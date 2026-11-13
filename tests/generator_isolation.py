"""Redirecting a generator's output, all of it (REQ-GEN-043) - now
generator/output.py's, re-exported here so every test keeps its import.

A generator writes several things, not one: the delivery tree, the
receipts beside it, and the shared bookkeeping file. These used to
default to the real ones under data/, so redirecting a generator's
flat CSV output alone - which is what both generator test modules
did, back when there was one - left a test run deleting and rewriting
the real delivery tree as a side effect.
Deterministic, so the bytes came back identical and nothing noticed; a
run interrupted mid-write would have left it half-deleted.

NEITHER GENERATOR WRITES A FLAT COPY ANY MORE (REQ-PIPE-102):
Child Protection stopped first, Birth Registrations followed, and
with them went the raw directories the copies lived in. What is left
to redirect is the delivery tree, the receipts beside it, and the
shared bookkeeping file. The hasattr() guard below stays, so a
generator legitimately lacking one of these is not an error.

Kept in one place so the next output added has one obvious place to be
added to, and so the two generator modules cannot drift apart on it.
"""
from __future__ import annotations

import os
from pathlib import Path

from generator.output import redirect  # noqa: F401 - the one copy, re-exported

#: The real data/ tree, which a redirected generator must leave alone.
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

#: What a copy of a delivered file would be saved as.
_SUPPLY_SUFFIXES = {".csv", ".parquet", ".json"}


def supply_files_under_data() -> set[Path]:
    """Every supply-shaped file under the REAL data/, skipping dbt's scratch.

    For a before/after comparison: anything new is a copy of a supply
    written somewhere other than where it was meant to go - the flat
    data/raw/ and data/cp_raw/ copies REQ-PIPE-102 removed were exactly
    that.

    A SUPPLY-SHAPED FILE, not every path under data/, and the narrowing
    is a real fix rather than a loosening (2026-09-27). Snapshotting all
    of data/ passed by luck and then failed on another worker's compiled
    dbt .sql files mid-run. dbt's compiled SQL is not a copy of a supply,
    and another worker's scratch is not the code under test's doing.

    PRUNED, NOT FILTERED AFTERWARDS (2026-10-11): rglob walked INTO
    data/dbt_scratch/ and filtered it out later, so another worker
    removing its finished dbt target mid-walk raised FileNotFoundError -
    twice in one day's full gates, never alone.
    """
    out = set()
    for root, dirs, files in os.walk(DATA_DIR, onerror=lambda _e: None):
        dirs[:] = [d for d in dirs if d != "dbt_scratch"]
        out |= {Path(root) / f for f in files
                if Path(f).suffix.lower() in _SUPPLY_SUFFIXES}
    return out


#: Everything a generator run legitimately leaves under its output root.
GENERATOR_OUTPUTS = {"deliveries", "receipts", "generator_bookkeeping.json",
                     "scenario_placements.json"}
