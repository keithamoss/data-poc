"""ensure_schema refuses a qa schema from another version rather than
half-applying its own (REQ-PIPE-144 criteria 28-29, REQ-PIPE-107 criteria
13-14).

NEWER: a checkout older than the database used to run its own DDL over
the newer schema and then REWRITE the recorded version DOWN to its own -
a silent downgrade (post-build-review #79). REQ-PIPE-107 criterion 14
asks for that to be reproduced by a failing test first; this module's
first test is that reproduction.

OLDER: REQ-PIPE-144 reshapes qa.filing and qa.delivery, and `CREATE TABLE
IF NOT EXISTS` leaves an existing table exactly as it was - so applying
the new DDL over an older database would half-apply it. Regenerate, never
migrate: refuse and say to rebuild from empty.
"""
from __future__ import annotations

import pytest

from qa_tools.common import qa_store, supply_db


def _version(conn) -> int:
    return conn.execute(
        f'SELECT version FROM "{qa_store.SCHEMA}".schema_version').fetchall()[0][0]


def _set_version(conn, version: int) -> None:
    conn.execute(f'UPDATE "{qa_store.SCHEMA}".schema_version SET version = ?', [version])


class TestANewerSchemaIsRefused:

    def test_it_is_not_downgraded(self, private_supply_dsn):
        """The reproduction REQ-PIPE-107 criterion 14 asks for."""
        newer = qa_store.SCHEMA_VERSION + 1
        with supply_db.connect(label="test-newer-schema") as conn:
            qa_store.ensure_schema(conn)
            _set_version(conn, newer)
            with pytest.raises(qa_store.SchemaVersionError):
                qa_store.ensure_schema(conn)
            assert _version(conn) == newer, "the recorded version was rewritten"

    def test_the_refusal_names_both_versions(self, private_supply_dsn):
        newer = qa_store.SCHEMA_VERSION + 3
        with supply_db.connect(label="test-newer-schema") as conn:
            qa_store.ensure_schema(conn)
            _set_version(conn, newer)
            with pytest.raises(qa_store.SchemaVersionError) as caught:
                qa_store.ensure_schema(conn)
        assert str(newer) in str(caught.value)
        assert str(qa_store.SCHEMA_VERSION) in str(caught.value)


class TestAnOlderReshapedSchemaIsRefused:

    def test_it_is_refused_and_told_to_rebuild_from_empty(self, private_supply_dsn):
        older = qa_store.RESHAPED_AT - 1
        with supply_db.connect(label="test-older-schema") as conn:
            qa_store.ensure_schema(conn)
            _set_version(conn, older)
            with pytest.raises(qa_store.SchemaVersionError) as caught:
                qa_store.ensure_schema(conn)
            assert _version(conn) == older, "nothing may be half-applied"
        assert "empty" in str(caught.value).lower()
        assert "reset-synthetic" in str(caught.value)

    def test_an_empty_database_is_built_as_ever(self, private_supply_dsn):
        with supply_db.connect(label="test-fresh-schema") as conn:
            qa_store.ensure_schema(conn)
            assert _version(conn) == qa_store.SCHEMA_VERSION
            qa_store.ensure_schema(conn)   # and again, a no-op
            assert _version(conn) == qa_store.SCHEMA_VERSION


def test_a_command_on_an_old_schema_says_so_cleanly(private_supply_dsn):
    """delivery-critic, overnight sprint 4: it surfaced as a traceback."""
    from click.testing import CliRunner
    from cli.app import cli

    with supply_db.connect(label="test-old-schema-cli") as conn:
        qa_store.ensure_schema(conn)
        _set_version(conn, qa_store.RESHAPED_AT - 1)
    result = CliRunner().invoke(cli, ["supply", "filings", "--dataset", "birth-registrations"])
    assert result.exit_code != 0
    assert "reset-synthetic" in result.output
    assert not isinstance(result.exception, qa_store.SchemaVersionError), \
        "it escaped as an exception rather than a clean refusal"


class TestEveryOlderSchemaIsRefused:
    """ALWAYS WIPE AND REBUILD (Keith, 2026-10-05): a schema even one
    version behind is refused, not brought up to date in place - schemas
    19 to 23 had been additive in-place migrations, a departure from the
    standing 'regenerate, never migrate' rule."""

    def test_one_version_behind_is_refused(self, private_supply_dsn):
        older = qa_store.SCHEMA_VERSION - 1
        with supply_db.connect(label="test-one-behind") as conn:
            qa_store.ensure_schema(conn)
            _set_version(conn, older)
            with pytest.raises(qa_store.SchemaVersionError) as caught:
                qa_store.ensure_schema(conn)
            assert _version(conn) == older, "it was migrated in place"
        assert "reset-synthetic" in str(caught.value)
