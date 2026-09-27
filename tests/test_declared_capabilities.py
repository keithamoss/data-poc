"""What the engine can do is DECLARED, not discovered (REQ-PIPE-087
criterion 9).

WHY THIS IS A CRITERION AT ALL. Promotion (REQ-PIPE-081) has to move a
staged table into a period's schema. On PostgreSQL that is
`ALTER TABLE ... SET SCHEMA` - a catalogue rewrite that copies no rows,
so promoting a supply is instant whatever its size. The alternative
shape, and the one this criterion exists to forbid, is a caller that
tries the move and catches whatever comes back: a failure then means
either "this engine cannot do it" or "it can and something else went
wrong", and nothing can tell those apart.
"""
from __future__ import annotations

import pytest

from qa_tools.common import supply_db


def test_the_capability_is_declared_rather_than_inferred():
    assert supply_db.CAN_MOVE_TABLE_BETWEEN_SCHEMAS is True


def test_a_real_move_carries_the_rows_and_leaves_nothing_behind(supply_dsn):
    with supply_db.connect(label="test-capabilities") as conn:
        supply_db.ensure_schemas(conn)
        conn.execute('CREATE SCHEMA IF NOT EXISTS "period_2099q9"')
        conn.execute(
            f'CREATE TABLE "{supply_db.STAGING_SCHEMA}".cap_move_probe (id integer)')
        conn.execute(
            f'INSERT INTO "{supply_db.STAGING_SCHEMA}".cap_move_probe VALUES (1), (2)')

        supply_db.move_table(conn, "cap_move_probe",
                              supply_db.STAGING_SCHEMA, "period_2099q9")

        rows = conn.execute(
            'SELECT count(*) FROM "period_2099q9".cap_move_probe').fetchone()[0]
        assert rows == 2, "the move lost rows"
        # AND IT IS GONE FROM STAGING, which is what makes promotion a
        # move rather than a copy - two versions of one supply in two
        # schemas is exactly the ambiguity the model refuses.
        left = conn.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = ? AND table_name = 'cap_move_probe'",
            [supply_db.STAGING_SCHEMA]).fetchone()[0]
        assert left == 0, "the table is still in staging - this was a copy, not a move"

        conn.execute('DROP SCHEMA "period_2099q9" CASCADE')


def test_an_unsafe_schema_or_table_name_is_refused(supply_dsn):
    """The identifiers are quoted, so this is not what keeps the SQL
    safe - it is what stops a name existing when quoted and being
    unfindable when a tool writes it unquoted, which is the failure
    supply_db._ident() exists for."""
    with supply_db.connect(label="test-capabilities") as conn:
        with pytest.raises(supply_db.SupplyDbError):
            supply_db.move_table(conn, "Bad Name", supply_db.STAGING_SCHEMA, "x")


def test_the_move_refuses_rather_than_falling_back_where_undeclared(monkeypatch, supply_dsn):
    """A fallback that copied the rows instead would turn promotion
    from an instant rename into an operation whose cost scales with the
    supply, invisibly."""
    monkeypatch.setattr(supply_db, "CAN_MOVE_TABLE_BETWEEN_SCHEMAS", False)
    with supply_db.connect(label="test-capabilities") as conn:
        with pytest.raises(supply_db.SupplyDbError, match="does not declare"):
            supply_db.move_table(conn, "anything", supply_db.STAGING_SCHEMA, "x")
