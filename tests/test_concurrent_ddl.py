"""Two collections bootstrapping at once create the shared staging objects
at the same moment (found by CI on 2026-10-05: the bootstrap's two
processes both ran `CREATE TABLE IF NOT EXISTS staging._resolutions` and one
died with a UniqueViolation on pg_type - PostgreSQL's IF NOT EXISTS is not
safe against a concurrent creator)."""
from __future__ import annotations

import threading

from qa_tools.common import supply_db


def _race(n, work):
    barrier = threading.Barrier(n)
    errors: list[BaseException] = []

    def one(i):
        try:
            with supply_db.connect(label=f"test-ddl-race-{i}") as conn:
                barrier.wait()
                work(conn, i)
        except BaseException as exc:  # noqa: BLE001 - collected and asserted on
            errors.append(exc)

    threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def test_concurrent_first_resolutions_do_not_collide(supply_dsn):
    for attempt in range(15):
        with supply_db.connect(label="test-ddl-race") as conn:
            conn.execute(f'DROP TABLE IF EXISTS "{supply_db.STAGING_SCHEMA}"."_resolutions"')
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
        errors = _race(8, lambda conn, i: supply_db.record_resolution(
            conn, supply_db.Resolution(run_id=f"race_{attempt}_{i}", schema="x")))
        assert not errors, f"attempt {attempt}: {errors[0]!r}"


def test_concurrent_creates_inside_transactions_do_not_collide(supply_dsn):
    """The same race one level in: a period or superseded schema created
    inside a decision's transaction. The lock has to last until COMMIT, or
    the second creator passes IF NOT EXISTS against the first's uncommitted
    row and dies when it commits."""
    import uuid

    for attempt in range(5):
        name = f"race_{uuid.uuid4().hex[:8]}"

        def work(conn, i, name=name):
            with conn.raw.transaction():
                supply_db.create_if_absent(conn, f'CREATE SCHEMA IF NOT EXISTS "{name}"')

        errors = _race(6, work)
        with supply_db.connect(label="test-ddl-race") as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{name}"')
        assert not errors, f"attempt {attempt}: {errors[0]!r}"
