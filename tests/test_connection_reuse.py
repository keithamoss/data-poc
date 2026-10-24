"""A process reuses its database connections (REQ-PIPE-158, signed by Keith
2026-10-06): an idle, already-checked connection is handed over rather than
a new one opened, and a handed-over connection is exactly what a new one
would have been."""
from __future__ import annotations

import threading

import psycopg
import pytest

from qa_tools.common import supply_db


@pytest.fixture(autouse=True)
def _empty_pool(supply_dsn):
    supply_db.release_connections()
    yield
    supply_db.release_connections()


def _backend(conn) -> int:
    return conn.execute("SELECT pg_backend_pid()").fetchone()[0]


class TestItIsReused:

    def test_a_closed_connection_is_handed_to_the_next_caller(self):
        with supply_db.connect(label="test-reuse-a") as first:
            pid = _backend(first)
        with supply_db.connect(label="test-reuse-b") as second:
            assert _backend(second) == pid

    def test_the_checks_run_once_per_connection_opened(self, monkeypatch):
        from qa_tools.common import db_identity
        checked = []
        real = db_identity.check
        monkeypatch.setattr(db_identity, "check", lambda s: (checked.append(s), real(s))[1])
        for _ in range(5):
            with supply_db.connect(label="test-reuse"):
                pass
        assert len(checked) == 1

    def test_nested_callers_get_different_connections(self):
        with supply_db.connect(label="outer") as outer, supply_db.connect(label="inner") as inner:
            assert _backend(outer) != _backend(inner)


class TestAHandedOverConnectionIsAsNew:

    def test_a_writer_never_inherits_a_readers_session(self):
        with supply_db.connect(read_only=True, label="reader") as r:
            pid = _backend(r)
        with supply_db.connect(label="writer") as w:
            assert _backend(w) == pid
            w.execute("CREATE TEMP TABLE reuse_probe (x int)")
            w.execute("INSERT INTO reuse_probe VALUES (1)")

    def test_a_reader_never_inherits_a_writers_session(self):
        with supply_db.connect(label="writer"):
            pass
        with supply_db.connect(read_only=True, label="reader") as r:
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                r.execute("CREATE TEMP TABLE reuse_probe_ro (x int)")

    def test_session_settings_and_the_callers_name_are_its_own(self):
        with supply_db.connect(label="first") as a:
            a.execute("SET search_path TO pg_catalog")
            a.execute("SET lock_timeout = 1")
        with supply_db.connect(label="second") as b:
            name, path = b.execute(
                "SELECT current_setting('application_name'), current_setting('search_path')"
            ).fetchone()
            assert name == "second"
            assert "pg_catalog" != path.strip()
            assert b.execute("SHOW lock_timeout").fetchone()[0] != "1ms"

    def test_an_open_transaction_is_rolled_back_not_handed_on(self):
        with supply_db.connect(label="first") as a:
            a.execute("CREATE TABLE IF NOT EXISTS public.reuse_tx_probe (x int)")
            a.execute("TRUNCATE public.reuse_tx_probe")
            a.raw.execute("BEGIN")
            a.execute("INSERT INTO public.reuse_tx_probe VALUES (1)")
        with supply_db.connect(label="second") as b:
            assert b.raw.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            assert b.execute("SELECT count(*) FROM public.reuse_tx_probe").fetchone()[0] == 0
            b.execute("DROP TABLE public.reuse_tx_probe")

    def test_a_session_lock_is_released_as_closing_released_it(self):
        with supply_db.connect(label="locker") as a:
            assert a.execute("SELECT pg_try_advisory_lock(424242)").fetchone()[0]
        with psycopg.connect(supply_db.supply_db_dsn(), autocommit=True) as other:
            assert other.execute("SELECT pg_try_advisory_lock(424242)").fetchone()[0], \
                "the lock outlived the connection being closed"
            other.execute("SELECT pg_advisory_unlock(424242)")

    def test_temporary_tables_go_with_the_caller(self):
        with supply_db.connect(label="first") as a:
            a.execute("CREATE TEMP TABLE reuse_temp (x int)")
        with supply_db.connect(label="second") as b:
            assert b.execute("SELECT to_regclass('pg_temp.reuse_temp')").fetchone()[0] is None


class TestABrokenConnectionIsReplaced:

    def test_a_terminated_idle_connection_is_never_handed_over(self):
        with supply_db.connect(label="first") as a:
            pid = _backend(a)
        with psycopg.connect(supply_db.supply_db_dsn(), autocommit=True) as admin:
            admin.execute("SELECT pg_terminate_backend(%s)", [pid])
        with supply_db.connect(label="second") as b:
            assert _backend(b) != pid
            assert b.execute("SELECT 1").fetchone()[0] == 1


class TestThreadsAndTheEnd:

    def test_two_threads_never_share_a_connection(self):
        seen, barrier = [], threading.Barrier(4)

        def work():
            with supply_db.connect(label="thread") as c:
                barrier.wait(timeout=10)
                seen.append(_backend(c))
        threads = [threading.Thread(target=work) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(seen)) == 4

    def test_releasing_closes_every_held_connection(self):
        with supply_db.connect(label="held") as a:
            raw = a.raw
        supply_db.release_connections()
        assert raw.closed


class TestWhatTheDatabaseSaysAboutAReusedConnection:

    def test_a_held_pass_lock_says_when_it_was_taken_not_when_the_connection_opened(self):
        """The pass lock's refusal names its holder 'since' a time
        (REQ-PIPE-152 criterion 16). A connection opened earlier and handed
        over later must not make the lock look older than it is - in a warm
        Lambda container that could be hours."""
        import time
        from datetime import datetime, timezone

        from qa_tools.common import processing_pass as pp

        with supply_db.connect(label="opened-early"):
            pass
        time.sleep(1.5)
        taken = datetime.now(timezone.utc).replace(microsecond=0)
        with pp.pass_lock("process"):
            with pytest.raises(pp.PassLockHeld) as caught:
                with supply_db.connect(label="other"):
                    with pp.pass_lock("bootstrap"):
                        pass
        assert datetime.fromisoformat(caught.value.since) >= taken
