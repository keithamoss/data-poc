"""qa_tools/common/delivery_log.py - one committed file per delivery,
written once at recognition (REQ-PIPE-069).

It is also REQ-PIPE-058 criterion 8's corpus, so what it records is not
only a historical nicety: the collision gate reads filename-to-dataset
pairs straight out of these files.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

import duckdb
import pytest

from qa_tools.common import delivery_log, validate_arrival_patterns

PERTH = timezone.utc


@dataclass
class _Delivery:
    name: str
    files: tuple
    received_at: datetime
    anomalies: tuple = ()


@dataclass
class _Recognition:
    by_dataset: dict = field(default_factory=dict)
    contested: dict = field(default_factory=dict)
    collections: tuple = ()


def _one(tmp_path, name="monday", files=("cp_clients.csv",), **kw):
    d = _Delivery(name=name, files=files,
                  received_at=datetime(2026, 9, 25, 9, 0, tzinfo=PERTH),
                  anomalies=kw.pop("anomalies", ()))
    r = _Recognition(by_dataset=kw.pop("by_dataset", {"cp-clients": ("cp_clients.csv",)}),
                     contested=kw.pop("contested", {}),
                     collections=kw.pop("collections", ("child-protection",)))
    return delivery_log.record(d, r, log_dir=tmp_path), d, r


class TestWrittenOnce:
    def test_a_delivery_is_recorded_with_what_it_was_attributed_to(self, tmp_path):
        path, _d, _r = _one(tmp_path)
        record = json.loads(path.read_text())
        assert record["delivery"] == "monday"
        assert record["collections"] == ["child-protection"]
        assert record["files"] == [
            {"filename": "cp_clients.csv", "dataset_id": "cp-clients", "contested_by": None}]

    def test_a_second_recognition_does_not_rewrite_it(self, tmp_path):
        """A delivery spanning collections is recognised by both
        orchestrators, so the no-op is the ordinary case rather than a
        guard against a bug - and a record that can be rewritten is one
        nobody can trust to be what was seen at the time."""
        first, d, r = _one(tmp_path)
        before = first.read_text()
        assert delivery_log.record(d, r, log_dir=tmp_path) is None
        assert first.read_text() == before

    def test_a_supplier_name_with_spaces_becomes_a_usable_filename(self, tmp_path):
        """The PoC's own delivery names already contain spaces, so this
        is a real transform rather than a defensive formality."""
        path, _d, _r = _one(tmp_path, name="Data Extract 01 Feb 2023")
        assert " " not in path.name
        assert json.loads(path.read_text())["delivery"] == "Data Extract 01 Feb 2023"


class TestEveryFileByTheNameItArrivedUnder:
    def test_a_junk_file_is_recorded_even_though_it_is_no_table(self, tmp_path):
        """The sharper half of criterion 3. REQ-PIPE-057 requires every
        artefact we declined to act on be recorded alongside the
        delivery it came in - and without this the warning fires once
        at recognition and the durable record loses it, so a supplier
        drifting over time is invisible unless somebody happened to be
        watching that run."""
        path, _d, _r = _one(tmp_path, files=("cp_clients.csv", "notes_for_jenny.docx"))
        record = json.loads(path.read_text())
        names = [f["filename"] for f in record["files"]]
        assert names == ["cp_clients.csv", "notes_for_jenny.docx"]
        assert record["files"][1]["dataset_id"] is None

    def test_a_contested_file_says_which_datasets_claimed_it(self, tmp_path):
        path, _d, _r = _one(
            tmp_path, files=("shared.csv",), by_dataset={},
            contested={"shared.csv": ("alpha", "beta")}, collections=())
        [entry] = json.loads(path.read_text())["files"]
        assert entry["dataset_id"] is None
        assert entry["contested_by"] == ["alpha", "beta"]

    def test_anomalies_are_recorded_rather_than_lost(self, tmp_path):
        """A receipt lookalike is excluded from `files` on purpose, so
        this is the only place its presence survives."""
        path, _d, _r = _one(tmp_path, anomalies=("receipt.json looks like a receipt record",))
        assert "receipt" in json.loads(path.read_text())["anomalies"][0]


class TestTheOffsetSurvives:
    def test_an_instant_keeps_the_clock_it_was_recorded_on(self, tmp_path):
        """Criterion 5. Normalising to UTC would throw away which clock
        the receiving side was on, which is what REQ-PIPE-048 exists
        for."""
        from datetime import timedelta

        d = _Delivery(name="perth", files=(),
                      received_at=datetime(2026, 9, 25, 9, 0,
                                           tzinfo=timezone(timedelta(hours=8))))
        path = delivery_log.record(d, _Recognition(), log_dir=tmp_path)
        assert json.loads(path.read_text())["received_at"].endswith("+08:00")


class TestQueryableAsSql:
    def test_duckdb_reads_the_committed_files_directly(self, tmp_path):
        """Criterion 4, by real experiment rather than assertion: no
        second copy in the warehouse, nothing synced."""
        _one(tmp_path, name="monday")
        _one(tmp_path, name="tuesday", files=("cp_carers.csv",),
             by_dataset={"cp-carers": ("cp_carers.csv",)})
        conn = duckdb.connect()
        rows = conn.execute(delivery_log.sql(tmp_path) + " ORDER BY delivery").fetchall()
        assert [r[0] for r in rows] == ["monday", "tuesday"]

    def test_the_filename_to_dataset_pairs_can_be_unnested(self, tmp_path):
        """What REQ-PIPE-058's collision gate actually wants."""
        _one(tmp_path, files=("cp_clients.csv", "notes.pdf"))
        conn = duckdb.connect()
        rows = conn.execute(
            f"SELECT f.filename, f.dataset_id FROM ({delivery_log.sql(tmp_path)}) t, "
            f"UNNEST(t.files) AS u(f) ORDER BY f.filename").fetchall()
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

    def test_a_record_for_a_delivery_that_is_gone_is_removed(self, tmp_path):
        _one(tmp_path, name="still-here")
        _one(tmp_path, name="deleted-upstream")
        gone = delivery_log.prune({"still-here"}, tmp_path)
        assert gone == ["deleted-upstream"]
        assert [r["delivery"] for r in delivery_log.records(tmp_path)] == ["still-here"]

    def test_a_record_for_a_delivery_still_present_is_left_alone(self, tmp_path):
        """Records are write-once, so a record for a delivery still
        present IS what a regeneration would write again - which is
        what makes pruning and wiping the same end state for every case
        that can actually arise."""
        path, _d, _r = _one(tmp_path, name="still-here")
        before = path.read_text()
        assert delivery_log.prune({"still-here"}, tmp_path) == []
        assert path.read_text() == before

    def test_it_says_what_it_removed(self, tmp_path):
        """A silent delete of committed files is the wrong shape even
        when it is correct."""
        _one(tmp_path, name="a")
        assert delivery_log.prune(set(), tmp_path) == ["a"]

    def test_an_unreadable_record_is_removed_rather_than_left(self, tmp_path):
        """It cannot be checked against what is present, and it fails
        the gate that reads this log - removing it is the only outcome
        that leaves the log in a state anything can use."""
        (tmp_path / "broken.json").write_text("{not json")
        assert delivery_log.prune(set(), tmp_path) == ["broken.json"]

    def test_pruning_nothing_is_not_an_error(self, tmp_path):
        assert delivery_log.prune(set(), tmp_path / "nothing-here") == []


class TestItIsTheCollisionGatesCorpus:
    def test_the_gate_reads_filenames_out_of_the_log(self, tmp_path):
        _one(tmp_path, files=("cp_clients.csv", "cp_carers.csv"))
        assert validate_arrival_patterns.committed_filenames(tmp_path) == [
            "cp_carers.csv", "cp_clients.csv"]

    def test_an_unreadable_record_fails_the_gate_rather_than_being_skipped(self, tmp_path):
        """A gate that quietly ignores what it cannot parse is a gate
        that passes for the wrong reason."""
        (tmp_path / "broken.json").write_text("{not json")
        with pytest.raises(validate_arrival_patterns.ArrivalPatternConfigError):
            validate_arrival_patterns.committed_filenames(tmp_path)
