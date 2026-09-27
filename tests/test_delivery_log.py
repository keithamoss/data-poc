"""qa_tools/common/delivery_log.py - one record per delivery, written
once at recognition (REQ-PIPE-069, moved into the database by
REQ-PIPE-089 criteria 16 and 22).

It is also REQ-PIPE-058 criterion 8's corpus, so what it records is not
only a historical nicety: the collision gate reads filename-to-dataset
pairs straight out of it.

THREE CLAIMS HERE CHANGED SHAPE WITH THE MOVE, and each says so where
it sits: the filename-ordering tests, which were about a property of
names that no longer exist; the corrupt-record tests, which defended
against a failure mode a row cannot have; and the DuckDB
`read_json_auto` tests, which existed to make committed files
queryable and are now a plain SELECT.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from qa_tools.common import delivery as delivery_module
from qa_tools.common import delivery_log, supply_db, validate_arrival_patterns

PERTH = timezone.utc


@pytest.fixture
def log(clean_delivery_log):
    """An empty delivery log on this worker's own database.

    A temporary directory until REQ-PIPE-089; the name stays because
    what it means has not.
    """
    return clean_delivery_log


@dataclass
class _Delivery:
    name: str
    files: tuple
    received_at: datetime
    anomalies: tuple = ()
    #: REQ-PIPE-061's receipt write order. It used to reach the
    #: record's own FILENAME, which is what the write-once defect
    #: below was about; nothing reads it now.
    sequence: int = 1
    #: WHICH CLOCK STAMPED `received_at` (REQ-PIPE-105 criterion 4).
    #: Defaulted to our clock here, which is the weaker claim, so a test
    #: that does not care says the honest thing rather than asserting
    #: storage reported an instant.
    received_from: str = delivery_module.RECEIVED_FROM_OUR_CLOCK


@dataclass
class _Recognition:
    by_dataset: dict = field(default_factory=dict)
    contested: dict = field(default_factory=dict)
    collections: tuple = ()


def _one(log, name="monday", files=("cp_clients.csv",), **kw):
    d = _Delivery(name=name, files=files,
                  received_at=kw.pop("received_at",
                                     datetime(2026, 9, 25, 9, 0, tzinfo=PERTH)),
                  anomalies=kw.pop("anomalies", ()))
    r = _Recognition(by_dataset=kw.pop("by_dataset", {"cp-clients": ("cp_clients.csv",)}),
                     contested=kw.pop("contested", {}),
                     collections=kw.pop("collections", ("child-protection",)))
    return delivery_log.record(d, r, conn=log), d, r


class TestWrittenOnce:
    def test_a_delivery_is_recorded_with_what_it_was_attributed_to(self, log):
        record, _d, _r = _one(log)
        assert record["delivery"] == "monday"
        assert record["collections"] == ["child-protection"]
        assert record["files"] == [
            {"filename": "cp_clients.csv", "dataset_id": "cp-clients", "contested_by": None}]

    def test_a_second_recognition_does_not_rewrite_it(self, log):
        """A delivery spanning collections is recognised by both
        orchestrators, so the no-op is the ordinary case rather than a
        guard against a bug - and a record that can be rewritten is one
        nobody can trust to be what was seen at the time."""
        first, d, r = _one(log)
        assert delivery_log.record(d, r, conn=log) is None
        assert delivery_log.records(log) == [first], \
            "the second recognition changed what the first one recorded"

    def test_a_supplier_name_with_spaces_is_kept_exactly(self, log):
        """The PoC's own delivery names already contain spaces. They
        used to be scrubbed out of a FILENAME and kept intact inside
        the record; there is no filename now, so the scrubbing is gone
        and only the exact name remains - which was always the part
        that mattered."""
        record, _d, _r = _one(log, name="Data Extract 01 Feb 2023")
        assert record["delivery"] == "Data Extract 01 Feb 2023"
        assert [r["delivery"] for r in delivery_log.records(log)] == [
            "Data Extract 01 Feb 2023"]


class TestEveryFileByTheNameItArrivedUnder:
    def test_a_junk_file_is_recorded_even_though_it_is_no_table(self, log):
        """The sharper half of criterion 3. REQ-PIPE-057 requires every
        artefact we declined to act on be recorded alongside the
        delivery it came in - and without this the warning fires once
        at recognition and the durable record loses it, so a supplier
        drifting over time is invisible unless somebody happened to be
        watching that run."""
        record, _d, _r = _one(log, files=("cp_clients.csv", "notes_for_jenny.docx"))
        names = [f["filename"] for f in record["files"]]
        assert names == ["cp_clients.csv", "notes_for_jenny.docx"]
        assert record["files"][1]["dataset_id"] is None

    def test_a_contested_file_says_which_datasets_claimed_it(self, log):
        record, _d, _r = _one(
            log, files=("shared.csv",), by_dataset={},
            contested={"shared.csv": ("alpha", "beta")}, collections=())
        [entry] = record["files"]
        assert entry["dataset_id"] is None
        assert entry["contested_by"] == ["alpha", "beta"]

    def test_anomalies_are_recorded_rather_than_lost(self, log):
        """A receipt lookalike is excluded from `files` on purpose, so
        this is the only place its presence survives."""
        record, _d, _r = _one(log, anomalies=("receipt.json looks like a receipt record",))
        assert "receipt" in record["anomalies"][0]


class TestTheOffsetSurvives:
    def test_an_instant_keeps_the_clock_it_was_recorded_on(self, log):
        """Criterion 5. Normalising to UTC would throw away which clock
        the receiving side was on, which is what REQ-PIPE-048 exists
        for."""
        from datetime import timedelta

        d = _Delivery(name="perth", files=(),
                      received_at=datetime(2026, 9, 25, 9, 0,
                                           tzinfo=timezone(timedelta(hours=8))))
        record = delivery_log.record(d, _Recognition(), conn=log)
        assert record["received_at"].endswith("+08:00")
        assert delivery_log.records(log)[0]["received_at"].endswith("+08:00"), \
            "the offset survived the write and was lost on the way back out"


class TestQueryableAsSql:
    """Criterion 4. It used to hand back a DuckDB `read_json_auto` over
    the committed files, so the log could be joined against the staging
    and period schemas with nothing synced and no second copy. The
    record is IN the warehouse now, so the join needs no special reader
    - which is what the criterion wanted and the file version could
    only approximate.
    """

    def test_the_log_is_selectable_beside_the_data_it_describes(self, log):
        _one(log, name="monday")
        _one(log, name="tuesday", files=("cp_carers.csv",),
             by_dataset={"cp-carers": ("cp_carers.csv",)})
        with supply_db.connect(label="test-delivery-sql") as conn:
            rows = conn.execute(
                f"SELECT DISTINCT delivery FROM ({delivery_log.sql()}) t "
                "ORDER BY delivery").fetchall()
        assert [r[0] for r in rows] == ["monday", "tuesday"]

    def test_the_filename_to_dataset_pairs_come_back_as_rows(self, log):
        """What REQ-PIPE-058's collision gate actually wants - and it
        needs no UNNEST now, because the files are rows rather than a
        nested array inside a document."""
        _one(log, files=("cp_clients.csv", "notes.pdf"))
        with supply_db.connect(label="test-delivery-sql") as conn:
            rows = conn.execute(
                f"SELECT filename, dataset_id FROM ({delivery_log.sql()}) t "
                "ORDER BY filename").fetchall()
        assert rows == [("cp_clients.csv", "cp-clients"), ("notes.pdf", None)]


class TestItNeverDescribesAHistoryThatIsGone:
    """Criterion 6, built as a PRUNE rather than a wipe - and the
    reason is a real incident rather than a preference.

    The first version cleared the whole log at the top of `mothman
    pipeline run`. The test suite invokes that command with the real
    work stubbed out, so the next gate run deleted sixty committed
    records and nothing rewrote them, because the thing that would
    have was the part being stubbed.
    """

    def test_a_record_for_a_delivery_that_is_gone_is_removed(self, log):
        _one(log, name="still-here")
        _one(log, name="deleted-upstream")
        gone = delivery_log.prune({"still-here"}, log)
        assert gone == ["deleted-upstream"]
        assert [r["delivery"] for r in delivery_log.records(log)] == ["still-here"]

    def test_a_record_for_a_delivery_still_present_is_left_alone(self, log):
        """Records are write-once, so a record for a delivery still
        present IS what a regeneration would write again - which is
        what makes pruning and wiping the same end state for every case
        that can actually arise."""
        record, _d, _r = _one(log, name="still-here")
        assert delivery_log.prune({"still-here"}, log) == []
        assert delivery_log.records(log) == [record]

    def test_it_says_what_it_removed(self, log):
        """A silent delete of durable records is the wrong shape even
        when it is correct."""
        _one(log, name="a")
        assert delivery_log.prune(set(), log) == ["a"]

    def test_an_unreadable_record_is_removed_rather_than_left(self, log):
        """RETIRED BY REQ-PIPE-089, kept as a note rather than deleted.

        A corrupt JSON file could be neither checked against what was
        present nor attributed to a delivery, so removing it was the
        only outcome that left the log usable. A row is either
        committed or it is not, so there is nothing left to be
        unreadable - and a defence removed with its hazard should say
        which hazard, or somebody reintroduces a file-backed log
        without knowing what it costs.
        """

    def test_pruning_nothing_is_not_an_error(self, log):
        assert delivery_log.prune(set(), log) == []


class TestItIsTheCollisionGatesCorpus:
    def test_the_gate_reads_filenames_out_of_the_log(self, log):
        _one(log, files=("cp_clients.csv", "cp_carers.csv"))
        assert validate_arrival_patterns.committed_filenames(log) == [
            "cp_carers.csv", "cp_clients.csv"]

    def test_no_database_is_reported_rather_than_read_as_an_empty_corpus(self, log):
        """The case REQ-PIPE-089 creates and REQ-PIPE-092 criterion 9
        has to survive: this gate runs where no database is reachable,
        and its corpus is now a table. `None` says the check was
        SKIPPED; an empty list would say it ran and found nothing,
        which is the one answer that would be a lie.
        """
        class _Unreachable:
            def __getattr__(self, _name):
                raise supply_db.SupplyDbError("no database here")

        import qa_tools.common.delivery_log as module
        real = module.records
        module.records = lambda *a, **k: (_ for _ in ()).throw(
            supply_db.SupplyDbError("no database here"))
        try:
            assert validate_arrival_patterns.committed_filenames() is None
        finally:
            module.records = real


class TestWriteOnceSurvivesAReIssuedReceipt:
    """A real defect, found by a gate rather than by review
    (2026-09-25), and the mechanism that caused it is now gone.

    REQ-PIPE-034 put the receipt's SEQUENCE in the committed record's
    FILENAME so a directory listing would be in receipt order. But the
    sequence is re-issued when the synthetic data is regenerated - same
    delivery, same instant, different number - so `path_for()` produced
    a new path and the write-once guard, which only asked whether THAT
    path existed, never fired. Measured on the real tree: 120 records
    for 60 deliveries, and every dataset's arrival history exactly
    doubled.

    THE GENERAL RULE: a write-once record whose filename encodes a
    MUTABLE value is not write-once.

    REQ-PIPE-089 removes the filename, and with it both the ordering
    trick and the defect - the delivery NAME is a primary key, so a
    second record for a delivery already logged is refused by the
    database rather than by a guard somebody has to get right. The
    tests below keep the property and drop the two that were about
    names: one asserted the sequence was absent from a filename, the
    other that a directory listing sorted into receipt order. Ordering
    is an ORDER BY now, which the last test still checks.
    """

    def test_a_delivery_is_not_logged_twice_when_its_sequence_changes(self, log):
        first, delivery_one, recognition = _one(log)
        assert first is not None

        # The same delivery, same receipt instant, a re-issued sequence.
        again = _Delivery(name=delivery_one.name, files=delivery_one.files,
                           received_at=delivery_one.received_at,
                           anomalies=delivery_one.anomalies,
                           sequence=delivery_one.sequence + 60)
        assert delivery_log.record(again, recognition, conn=log) is None, (
            "a second record for a delivery already logged is exactly what write-once "
            "forbids, whatever the receipt sequence works out to")
        assert len(delivery_log.records(log)) == 1

    def test_records_still_come_back_in_receipt_order(self, log):
        """The reason the instant was in the filename at all - a
        listing had to BE receipt order. It is an ORDER BY on the
        instant now, which does not depend on how a name sorts."""
        from datetime import datetime, timedelta, timezone

        perth = timezone(timedelta(hours=8))
        for n, day in enumerate([3, 1, 2], start=1):
            d = _Delivery(name=f"drop-{day}", files=("cp_clients.csv",),
                           received_at=datetime(2026, 6, day, 9, tzinfo=perth),
                           sequence=n)
            delivery_log.record(d, _Recognition(
                by_dataset={"cp-clients": ("cp_clients.csv",)},
                collections=("child-protection",)), conn=log)
        assert [r["delivery"] for r in delivery_log.records(log)] == [
            "drop-1", "drop-2", "drop-3"]
