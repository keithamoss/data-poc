"""Helpers for tests that need the supply database in a known state.

NOT A FIXTURE MODULE and deliberately not conftest.py: these are called
from inside existing fixtures and helper functions across two dozen test
modules, which is a plain function call rather than a fixture
dependency. conftest.py owns the per-worker database itself
(REQ-TEST-095); this owns putting it back to empty.

WHY RESETTING BEATS A DATABASE PER TEST. Creating a PostgreSQL database
costs real time - enough that doing it for each of ~1900 tests would
dominate the suite - while dropping the schemas the code under test
creates is a catalogue operation and costs almost nothing. The isolation
is the same either way, because every name this pipeline uses lives
inside one of those schemas.
"""
from __future__ import annotations

from qa_tools.common import supply_db

#: Schemas PostgreSQL itself owns, which must survive a reset. `public`
#: is included because dropping it breaks extensions and search_path
#: defaults for everything afterwards, and nothing in this project puts
#: supply data there - the four-kinds-of-schema design is what makes that
#: true (REQ-PIPE-087).
_KEEP = frozenset({"information_schema", "public"})


def reset_supply_db() -> None:
    """Drop every schema this pipeline creates, leaving an empty database.

    Covers staging, rejected, dbt's own, every period schema and every
    per-run view schema - found by ASKING THE CATALOGUE rather than by
    listing the names here, so a schema kind added later is reset without
    anybody remembering to update this.
    """
    conn = supply_db.connect()
    try:
        rows = conn.execute("SELECT schema_name FROM information_schema.schemata").fetchall()
        for (schema,) in rows:
            if schema in _KEEP or schema.startswith("pg_"):
                continue
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        conn.close()
