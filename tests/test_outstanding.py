"""Everything that needs a person, in one queue (REQ-DASH-070).

The failure this defends against is not an item being wrong. It is six
items, produced by six requirements, each correctly reporting itself
and nobody reporting the six - which at 2 datasets looks like a tidy
design and at 30 is how a held supply goes unseen for a month.

Nothing here may read the real records. Since REQ-PIPE-089 two of the
four producers - the delivery log and the load log - live in the
database, so isolation for those comes from this worker having its own
and from the two `clean_*` fixtures emptying them per test; the other
two still write into tmp_path behind conftest's session guard.
"""
from __future__ import annotations

import json

import pytest

from qa_tools.common import load_log, outstanding


def _delivery(conn, name="monday", **overrides):
    """One delivery record, straight into this worker's database.

    STILL BUILT BY HAND rather than through delivery_log.record(),
    which is deliberate and unchanged from when these were files: the
    point of this module is what the QUEUE does with a record, and
    several of these records describe states - a contested file, a
    hold - that would otherwise need a whole recognition set up to
    produce. What changed is only where the hand-built record lands.
    """
    from qa_tools.common import qa_store

    record = {"delivery": name, "received_at": "2026-09-01T09:00:00+08:00",
              "collections": ["child-protection"], "files": [], "held": [],
              "anomalies": []}
    record.update(overrides)
    conn.execute(
        f'INSERT INTO "{qa_store.SCHEMA}".delivery '
        "(name, received_at, received_instant, collections, held, anomalies) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [record["delivery"], record["received_at"], record["received_at"],
         json.dumps(record["collections"]), json.dumps(record["held"]),
         json.dumps(record["anomalies"])])
    for entry in record["files"]:
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".delivery_file '
            "(delivery, filename, dataset_id, contested_by) VALUES (?, ?, ?, ?)",
            [record["delivery"], entry["filename"], entry.get("dataset_id"),
             json.dumps(entry["contested_by"]) if entry.get("contested_by") else None])
    return record


@pytest.fixture(autouse=True)
def _empty_database_records(clean_delivery_log, clean_load_log):
    """Every test here surveys the whole outstanding queue, and a failed
    LOAD is one of its four producers. Since REQ-PIPE-089 those live in
    the worker's database rather than in each test's own directory, so
    without this a failure written by one test shows up in the next
    one's total. Autouse in this file specifically, because surveying
    everything is what this file does. The delivery log joins it for
    the same reason."""
    return clean_delivery_log


def _survey(tmp_path, **kwargs):
    return outstanding.survey(
        observations_dir=kwargs.get("observations_dir", tmp_path / "observations"),
        filings_dir=kwargs.get("filings_dir", tmp_path / "filings"))


class TestOneQueueNotOnePerRule:
    """Criterion 1: ONE element carrying a total, never one per item
    and never one per producing rule."""

    def test_items_from_four_different_producers_land_in_one_total(self, tmp_path, clean_delivery_log):
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None, "contested_by": None},
                          {"filename": "both.csv", "dataset_id": None,
                           "contested_by": ["cp-carers", "cp-clients"]}])
        # A failed load, which since REQ-PIPE-089 is a row rather than a
        # file. `clean_load_log` is what makes "this is the only failure"
        # true on a worker database shared with other tests.
        load_log.record("monday", "cp-carers", "cp_carers", load_log.FAILED,
                        "2026-09-01T09:05:00+08:00", reason="not valid CSV")

        found = _survey(tmp_path)

        assert found.total == 4, found.summary()
        kinds = sorted({i.kind for i in found.items})
        assert kinds == ["contested-file", "failed-load", "held-supply",
                          "unrecognised-file"]

    def test_an_empty_queue_says_so_rather_than_being_absent(self, tmp_path):
        """Criterion 13. 'Nothing is waiting' and 'nobody looked' are
        the same thing to a reader who sees an empty box."""
        found = _survey(tmp_path)
        assert found.total == 0
        assert found.summary() == "Nothing is waiting for a person."


class TestBlockingIsASecondAxis:
    """Criterion 3: an item that BLOCKS a supply is distinguished from
    one that merely needs review, so a non-blocking item cannot read as
    blocking work."""

    def test_a_held_supply_blocks_and_an_unrecognised_file_does_not(self, tmp_path, clean_delivery_log):
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None}])

        found = _survey(tmp_path)

        blocking = {i.kind for i in found.blocking}
        review = {i.kind for i in found.needs_review}
        assert blocking == {"held-supply"}
        assert review == {"unrecognised-file"}

    def test_an_unrecognised_file_is_a_warning_not_a_failure(self, tmp_path, clean_delivery_log):
        """REQ-PIPE-057 criterion 9 says explicitly it does not fail the
        delivery, and its own detail has to say so where a reader will
        meet it - a covering note is ordinary."""
        _delivery(clean_delivery_log, "monday",
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None}])

        item, = _survey(tmp_path).items

        assert item.severity == outstanding.WARNING
        assert item.blocking is False
        assert "did not fail the delivery" in item.detail

    def test_blocking_items_sort_ahead_of_items_needing_review(self, tmp_path, clean_delivery_log):
        """A queue ordered by when things happened puts the thing
        somebody has to do today below six things they have seen."""
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None}])

        kinds = [i.kind for i in _survey(tmp_path).items]

        assert kinds[0] == "held-supply"


class TestSeverityIsNotADataVerdict:
    """Criterion 5: event severity uses its own vocabulary, never the
    one a check's verdict uses."""

    @pytest.mark.parametrize("severity", [outstanding.INFORMATIONAL,
                                           outstanding.WARNING,
                                           outstanding.NEEDS_ACTION])
    def test_no_severity_is_a_status_word(self, severity):
        assert severity not in {"green", "amber", "red", "nodata", "exhausted",
                                 "inactive"}

    def test_an_in_flight_delivery_is_informational_and_asks_nothing(self, tmp_path):
        directory = tmp_path / "observations"
        directory.mkdir()
        (directory / "cp.json").write_text(json.dumps({
            "observed_at": "2026-09-01T09:00:00+08:00", "observed_by": "child-protection",
            "in_flight": [{"delivery": "tuesday", "files": ["a.csv"]}]}))

        item, = _survey(tmp_path).items

        assert item.severity == outstanding.INFORMATIONAL
        assert item.blocking is False
        assert "at the last regeneration" in item.detail.lower()


class TestPerScopeCounts:
    """Criterion 2: a per-scope count on each affected agency and
    collection, so a rollup cannot absorb it."""

    def test_a_dataset_item_counts_against_its_agency_and_collection(self, tmp_path, clean_delivery_log):
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

        found = _survey(tmp_path)

        assert found.by_dataset == {"cp-clients": 1}
        assert sum(found.by_collection.values()) == 1
        assert sum(found.by_agency.values()) == 1

    def test_an_unknown_dataset_id_does_not_take_the_queue_down(self, tmp_path, clean_delivery_log):
        """Committed history may name a dataset since renamed or
        retired. A queue that raises on one stale record shows a reader
        nothing at all, which is strictly worse than showing them the
        item unscoped."""
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "a-dataset-that-never-existed",
                          "files": ["a.csv", "b.csv"]}])

        item, = _survey(tmp_path).items

        assert item.agency_id is None
        assert item.dataset_id == "a-dataset-that-never-existed"


class TestResponsesAreNamedNeverOffered:
    """Criterion 8: name the responses, and never present one that
    cannot yet be taken as a control."""

    def test_every_item_names_what_would_resolve_it(self, tmp_path, clean_delivery_log):
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None}])

        for item in _survey(tmp_path).items:
            assert item.responses, item.kind

    def test_nothing_is_actionable_while_the_resolution_path_is_unbuilt(self, tmp_path, clean_delivery_log):
        """The write path belongs with the decision log, delivery sprint
        12. A hold nobody can clear is indistinguishable from a bug, so
        the item says which it is rather than offering a dead control."""
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

        item, = _survey(tmp_path).items

        assert item.actionable is False


class TestItFaultsNobody:
    """Criterion 12: explain what happened and whose task it is, never
    attribute fault to the reader."""

    BLAMING = ("you failed", "you forgot", "your mistake", "you should have",
                "user error")

    def test_no_item_blames_the_reader(self, tmp_path, clean_delivery_log):
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None},
                          {"filename": "both.csv", "dataset_id": None,
                           "contested_by": ["cp-carers", "cp-clients"]}])

        for item in _survey(tmp_path).items:
            text = (item.headline + " " + item.detail).lower()
            for phrase in self.BLAMING:
                assert phrase not in text, (item.kind, phrase)


class TestItReadsRecordsAndNeverSupplyRows:
    """The NFR, RESTATED rather than kept as it was.

    It used to read "this feeds a dashboard build and may never open
    data/", and it was tested by asserting the module named no
    database driver at all - which worked while every record it needed
    was a committed file. REQ-PIPE-089 moved two of its four producers
    into the database, so "opens no database" would now be a test that
    passes only because the import sits one module away, which is
    worse than no test.

    The line it has to hold is Keith's own, 2026-09-27: a build may
    read recorded QA results, never actual data, and never anything
    else. The delivery record and the load outcome are recorded
    metadata; a staged, promoted, rejected or period schema holds the
    extract itself. So the claim is about WHICH schema, not about
    whether a connection exists.
    """

    #: Every schema that holds supply rows. Named here rather than
    #: derived, because the point is that a new one must be added
    #: deliberately - a derivation would quietly admit whatever came
    #: along next.
    FORBIDDEN = ("staging", "rejected", "promoted", "period_", "sample")

    def test_it_reads_no_schema_that_holds_supply_rows(self):
        source = (outstanding.__file__ and open(outstanding.__file__).read()) or ""
        named = [s for s in self.FORBIDDEN if s in source]
        assert not named, (
            f"outstanding.py names {named}, which hold the extract itself. It may read "
            f"recorded metadata and nothing else.")

    def test_it_reaches_the_database_only_through_the_record_modules(self):
        """A connection of its own would be the thing to worry about:
        the two modules it goes through can only answer questions about
        records, and `supply_db.connect` can answer any question at
        all."""
        import ast

        source = (outstanding.__file__ and open(outstanding.__file__).read()) or ""
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.update(a.name for a in node.names)
                if node.module:
                    imported.add(node.module.split(".")[0])

        # THE IMPORTS, not the source text. Written as a substring
        # search first, which promptly failed on a docstring explaining
        # why `supply_db` is not imported - a test that cannot tell
        # prose from code is a test that punishes the explanation.
        assert "supply_db" not in imported
        assert "duckdb" not in imported


class TestTheRecordTheDashboardReads:
    def test_as_record_carries_the_total_and_the_per_scope_counts(self, tmp_path, clean_delivery_log):
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

        record = _survey(tmp_path).as_record()

        assert record["total"] == 1
        assert record["blockingCount"] == 1
        assert record["byDataset"] == {"cp-clients": 1}
        assert record["items"][0]["blocking"] is True
        assert record["items"][0]["actionable"] is False

    def test_the_record_is_json_serialisable(self, tmp_path, clean_delivery_log):
        """It is embedded into a single-file page, so anything that
        cannot round-trip through json breaks the build rather than
        one panel."""
        _delivery(clean_delivery_log, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])
        record = _survey(tmp_path).as_record()
        assert json.loads(json.dumps(record)) == record
