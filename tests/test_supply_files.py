"""The one resolver: which file, staged table, period and staging key a
supply is (REQ-PIPE-193 criterion 13), and the receipt view reading a
settled pair's own file (criterion 10)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

import filing_support
from qa_tools.common import filing, load_log, qa_store, supply_db, supply_files

DATASET = "cp-case-workers"
LOGICAL = "cp_case_workers"
# '-' sorts before '_' in byte order, so the file NAMED first by a person
# reading "v2 then resend" is staged SECOND.
LATER = "cp_case_workers_v2.csv"
EARLIER = "cp_case_workers-resend.csv"


@pytest.fixture
def received():
    return datetime(2031, 5, 6, tzinfo=timezone.utc) + timedelta(
        seconds=uuid.uuid4().int % 10_000_000)


@pytest.fixture
def conn(supply_dsn):
    with supply_db.connect(label="test-supply-files") as c:
        qa_store.ensure_schema(c)
        yield c


def _key(at):
    return supply_db.arrival_segment(at.isoformat())


def _delivery(conn, at, files):
    """One delivery; `files` is [(filename, receipt)] - the pair's own
    receipts, each its own instant."""
    name = f"pytest-sf-{uuid.uuid4().hex[:10]}"
    conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".delivery (name, received_at, '
                 "received_instant) VALUES (?, ?, ?)", [name, at.isoformat(), at])
    for n, (filename, receipt) in enumerate(files):
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".delivery_file (delivery, filename, dataset_id, '
            "received_at, received_instant, received_from, receipt_sequence) "
            "VALUES (?, ?, ?, ?, ?, 'our-clock', ?)",
            [name, filename, DATASET, receipt.isoformat(), receipt, n])
    return name


def _settle(conn, pair_period, rows):
    """A choose-file entry and its per-file rows, written directly - the
    decision path is filing_decisions' to test; this is the resolver's."""
    decision_id = conn.execute(
        f'INSERT INTO "{qa_store.SCHEMA}".decision (agency_id, collection_id, dataset_id, '
        "action, supply, actor, actor_kind, reason, effective_at, from_slot) "
        "VALUES ('a', 'c', ?, 'choose-file', ?, 'pytest', 'person', 'r', now(), ?) "
        "RETURNING id", [DATASET, rows[0][1].split("#")[0] + "#1", pair_period]
    ).fetchall()[0][0]
    for filename, supply_id, outcome, to_slot in rows:
        conn.execute(f'INSERT INTO "{qa_store.SCHEMA}".decision_file (decision_id, filename, '
                     "supply_id, outcome, to_slot) VALUES (?, ?, ?, ?, ?)",
                     [decision_id, filename, supply_id, outcome, to_slot])
    return decision_id


class TestAnOrdinarySupplyIsItsOneTable:
    def test_one_file(self, conn, received):
        delivery = _delivery(conn, received, [(f"{LOGICAL}.csv", received)])
        supply = f"{DATASET}@{_key(received)}"
        filing_support.place(conn, DATASET, supply, "2031-Q2", delivery)
        got = supply_files.resolve(conn, DATASET, supply)
        assert got.tables == (f"{LOGICAL}__{_key(received)}",)
        assert got.period == "2031-Q2"
        assert got.filename == f"{LOGICAL}.csv" and not got.settled

    def test_never_filed_is_its_plain_table_with_no_period(self, conn, received):
        got = supply_files.resolve(conn, DATASET, f"{DATASET}@{_key(received)}")
        assert got.tables == (f"{LOGICAL}__{_key(received)}",) and got.period is None

    def test_an_unfiled_pair_file_resolves_to_nothing(self, conn, received):
        """Without its delivery, `#2` cannot be told from `#1`."""
        assert supply_files.resolve(conn, DATASET, f"{DATASET}@{_key(received)}#2").tables == ()


class TestAnOpenPairsFirstSupplyOwnsBothFiles:
    def test_both_tables_in_byte_order(self, conn, received):
        delivery = _delivery(conn, received, [(LATER, received),
                                              (EARLIER, received + timedelta(minutes=5))])
        supply = f"{DATASET}@{_key(received)}#1"
        filing_support.place(conn, DATASET, supply, "2031-Q2", delivery)
        got = supply_files.resolve(conn, DATASET, supply)
        key = _key(received)
        assert got.tables == (f"{LOGICAL}__{key}__1", f"{LOGICAL}__{key}__2")
        assert supply_files.files_in_order(conn, DATASET, delivery) == [EARLIER, LATER]
        assert got.filename is None and not got.settled

    def test_a_file_the_load_refused_is_not_one_of_its_tables(self, conn, received):
        delivery = _delivery(conn, received, [(LATER, received), (EARLIER, received)])
        supply = f"{DATASET}@{_key(received)}#1"
        filing_support.place(conn, DATASET, supply, "2031-Q2", delivery)
        refused = f"{LOGICAL}__{_key(received)}__1"
        load_log.record(delivery, DATASET, refused, load_log.FAILED, received.isoformat(),
                        reason="ragged")
        try:
            assert supply_files.resolve(conn, DATASET, supply).tables == (
                f"{LOGICAL}__{_key(received)}__2",)
        finally:
            conn.execute(f'DELETE FROM "{qa_store.SCHEMA}".load_outcome WHERE physical = ?',
                         [refused])


class TestASettledPairsSuppliesAreEachTheirOwnFile:
    """The file settled as #1 is staged as `__2` here: nothing may read #N
    as __N (criterion 13)."""

    def _settled(self, conn, received, later_outcome=("superseded", None)):
        key = _key(received)
        delivery = _delivery(conn, received, [(LATER, received),
                                              (EARLIER, received + timedelta(minutes=10))])
        one, two = f"{DATASET}@{key}#1", f"{DATASET}@{key}#2"
        filing_support.place(conn, DATASET, one, "2031-Q2", delivery)
        filing_support.place(conn, DATASET, two, later_outcome[1] or "2031-Q2", delivery)
        _settle(conn, "2031-Q2", [(LATER, one, "supply", None),
                                  (EARLIER, two, *later_outcome)])
        return key, one, two

    def test_each_supply_resolves_to_its_own_table(self, conn, received):
        key, one, two = self._settled(conn, received)
        a = supply_files.resolve(conn, DATASET, one)
        b = supply_files.resolve(conn, DATASET, two)
        assert a.tables == (f"{LOGICAL}__{key}__2",) and a.filename == LATER and a.settled
        assert b.tables == (f"{LOGICAL}__{key}__1",) and b.filename == EARLIER

    def test_a_re_filed_file_resolves_to_its_target_period(self, conn, received):
        _key_, _one, two = self._settled(conn, received, ("refiled", "2031-Q3"))
        assert supply_files.resolve(conn, DATASET, two).period == "2031-Q3"

    def test_the_reverse_maps_each_table_to_its_supply(self, conn, received):
        key, one, two = self._settled(conn, received)
        assert supply_files.supply_for_table(conn, DATASET, f"{LOGICAL}__{key}__2") == one
        assert supply_files.supply_for_table(conn, DATASET, f"{LOGICAL}__{key}__1") == two

    def test_the_receipt_view_reads_each_supplys_own_file(self, conn, received):
        """Criterion 10: the later file chosen, its receipt is the supply's."""
        _key_, one, two = self._settled(conn, received)
        rows = dict(conn.execute(
            f"SELECT supply_id, received_instant FROM {filing.RECEIPT} "
            "WHERE dataset_id = ? AND supply_id IN (?, ?)", [DATASET, one, two]).fetchall())
        assert rows[one] == received
        assert rows[two] == received + timedelta(minutes=10)


class TestRunIds:
    """Criterion 14: a settled supply's runs are its own; its arrival's run
    is shared and carries the run_index."""

    def test_each_supply_has_its_own_and_the_arrival_one_is_shared(self):
        assert supply_files.run_id_of(DATASET, f"{DATASET}@123#2") == f"{LOGICAL}__123__2"
        assert supply_files.run_id_of(DATASET, f"{DATASET}@123") == f"{LOGICAL}__123"
        assert supply_files.arrival_run_id_of(DATASET, f"{DATASET}@123#2") == f"{LOGICAL}__123"

    def test_the_id_is_split_in_one_place(self):
        assert supply_files.staging_key_of(f"{DATASET}@123#2") == "123"
        assert supply_files.ordinal_of(f"{DATASET}@123#2") == "2"
        assert supply_files.ordinal_of(f"{DATASET}@123") == ""
        assert supply_files.pair_supply(f"{DATASET}@123#2") == f"{DATASET}@123#1"
