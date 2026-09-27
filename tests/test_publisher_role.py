"""The dashboard build gets a role that can read recorded results and
nothing else (REQ-PIPE-089 criteria 7 and 23).

WHY A ROLE RATHER THAN A SEPARATE DATABASE. Keith settled this on
2026-09-26, and he got there by pushing back on an argument this
project had overstated: the claim that a separate metadata database
means the publisher's credentials "literally cannot" reach supply data
was wrong - it is a GRANT either way, not a wall. What separation
actually buys is least privilege per component, and a role in one
database buys exactly that. Against a second database was something
concrete: REQ-PIPE-075 criterion 9's ordering rule collapses into a
single transaction only while the log and the tables share one.

So the guarantee has to be TESTED rather than asserted, because a
grant is only as good as what it leaves out. These drive a real
connection as the real role against a real PostgreSQL - a mock would
confirm that the code calls the functions it calls, which is not the
claim.
"""
from __future__ import annotations

import psycopg
import pytest

from qa_tools.common import qa_store, supply_db

ROLE = "mothman_publisher_test"
PASSWORD = "publisher-test-password"


@pytest.fixture
def publisher(supply_dsn):
    """The real role, created the real way, with a connection as it."""
    with supply_db.connect(label="test-publisher-setup") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
        conn.execute(
            f'CREATE TABLE IF NOT EXISTS "{supply_db.STAGING_SCHEMA}".secret_supply '
            "(id int, surname text)")
        qa_store.ensure_publisher_role(conn, ROLE, PASSWORD)

    fields = supply_db.connection_fields()
    dsn = (f"postgresql://{ROLE}:{PASSWORD}@{fields['host']}:{fields['port']}"
           f"/{fields['dbname']}")
    with supply_db.connect(dsn=dsn, label="test-publisher") as conn:
        yield conn


class TestItCanReadWhatTheBuildNeeds:
    def test_it_reads_recorded_check_results(self, publisher):
        publisher.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".check_result_visible')

    def test_it_reads_the_load_outcomes(self, publisher):
        publisher.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".load_outcome')

    def test_it_reads_the_delivery_records(self, publisher):
        publisher.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".delivery')
        publisher.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".delivery_file')

    def test_it_reads_the_dataset_stats_the_dashboard_renders(self, publisher):
        publisher.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".dataset_stats_visible')


class TestItCannotReachSupplyRows:
    """Criterion 23's second half, and the half worth testing: "and to
    nothing else - never to any schema holding supply rows"."""

    def test_it_cannot_read_a_staged_table(self, publisher):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            publisher.execute(
                f'SELECT * FROM "{supply_db.STAGING_SCHEMA}".secret_supply')

    def test_it_cannot_list_what_is_in_the_staging_schema(self, publisher):
        """Refused at the SCHEMA, not per table - otherwise every table
        created after the grant would arrive readable."""
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            publisher.execute(
                f'CREATE TABLE "{supply_db.STAGING_SCHEMA}".probe (id int)')


class TestItCannotWriteAnything:
    """A publisher that can rewrite history is not a publisher."""

    def test_it_cannot_insert_a_result(self, publisher):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            publisher.execute(
                f'INSERT INTO "{qa_store.SCHEMA}".run '
                "(run_key, agency_id, collection_id, run_timestamp) "
                "VALUES ('forged', 'a', 'b', now())")

    def test_it_cannot_delete_history(self, publisher):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            publisher.execute(f'DELETE FROM "{qa_store.SCHEMA}".check_result')

    def test_it_cannot_mark_a_run_complete(self, publisher):
        """The one write that would let a half-finished run be
        published as a finished one."""
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            publisher.execute(f'UPDATE "{qa_store.SCHEMA}".run SET completed_at = now()')


class TestATableAddedLaterIsCoveredToo:
    """The grant has to be about the SCHEMA's future as well as its
    present, or the next table lands unreadable and somebody fixes it
    by granting everything."""

    def test_a_new_metadata_table_is_readable_without_a_second_grant(
            self, publisher, supply_dsn):
        with supply_db.connect(label="test-publisher-setup") as conn:
            conn.execute(f'CREATE TABLE IF NOT EXISTS "{qa_store.SCHEMA}".later (id int)')
        try:
            publisher.execute(f'SELECT count(*) FROM "{qa_store.SCHEMA}".later')
        finally:
            with supply_db.connect(label="test-publisher-setup") as conn:
                conn.execute(f'DROP TABLE IF EXISTS "{qa_store.SCHEMA}".later')
