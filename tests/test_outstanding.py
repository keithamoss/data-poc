"""Everything that needs a person, in one queue (REQ-DASH-070).

The failure this defends against is not an item being wrong. It is six
items, produced by six requirements, each correctly reporting itself
and nobody reporting the six - which at 2 datasets looks like a tidy
design and at 30 is how a held supply goes unseen for a month.

Every fixture here writes into tmp_path. Nothing in this module may
read the real committed trees: tests/conftest.py's own session guard
redirects them, and passing an explicit directory is the second lock
rather than a redundant one.
"""
from __future__ import annotations

import json

import pytest

from qa_tools.common import outstanding


def _delivery(tmp_path, name="monday", **overrides):
    directory = tmp_path / "delivery_log"
    directory.mkdir(parents=True, exist_ok=True)
    record = {"delivery": name, "received_at": "2026-09-01T09:00:00+08:00",
               "collections": ["child-protection"], "files": [], "held": [],
               "anomalies": []}
    record.update(overrides)
    (directory / f"{name}.json").write_text(json.dumps(record))
    return directory


def _survey(tmp_path, **kwargs):
    return outstanding.survey(
        delivery_log_dir=kwargs.get("delivery_log_dir", tmp_path / "delivery_log"),
        processing_log_dir=kwargs.get("processing_log_dir", tmp_path / "processing_log"),
        observations_dir=kwargs.get("observations_dir", tmp_path / "observations"),
        filings_dir=kwargs.get("filings_dir", tmp_path / "filings"))


class TestOneQueueNotOnePerRule:
    """Criterion 1: ONE element carrying a total, never one per item
    and never one per producing rule."""

    def test_items_from_four_different_producers_land_in_one_total(self, tmp_path):
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None, "contested_by": None},
                          {"filename": "both.csv", "dataset_id": None,
                           "contested_by": ["cp-carers", "cp-clients"]}])
        log = tmp_path / "processing_log"
        log.mkdir()
        (log / "one.json").write_text(json.dumps({
            "delivery": "monday", "dataset_id": "cp-carers", "physical": "cp_carers",
            "outcome": "failed", "recorded_at": "2026-09-01T09:05:00+08:00",
            "reason": "not valid CSV", "row_count": None}))

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

    def test_a_held_supply_blocks_and_an_unrecognised_file_does_not(self, tmp_path):
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None}])

        found = _survey(tmp_path)

        blocking = {i.kind for i in found.blocking}
        review = {i.kind for i in found.needs_review}
        assert blocking == {"held-supply"}
        assert review == {"unrecognised-file"}

    def test_an_unrecognised_file_is_a_warning_not_a_failure(self, tmp_path):
        """REQ-PIPE-057 criterion 9 says explicitly it does not fail the
        delivery, and its own detail has to say so where a reader will
        meet it - a covering note is ordinary."""
        _delivery(tmp_path, "monday",
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None}])

        item, = _survey(tmp_path).items

        assert item.severity == outstanding.WARNING
        assert item.blocking is False
        assert "did not fail the delivery" in item.detail

    def test_blocking_items_sort_ahead_of_items_needing_review(self, tmp_path):
        """A queue ordered by when things happened puts the thing
        somebody has to do today below six things they have seen."""
        _delivery(tmp_path, "monday",
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

    def test_a_dataset_item_counts_against_its_agency_and_collection(self, tmp_path):
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

        found = _survey(tmp_path)

        assert found.by_dataset == {"cp-clients": 1}
        assert sum(found.by_collection.values()) == 1
        assert sum(found.by_agency.values()) == 1

    def test_an_unknown_dataset_id_does_not_take_the_queue_down(self, tmp_path):
        """Committed history may name a dataset since renamed or
        retired. A queue that raises on one stale record shows a reader
        nothing at all, which is strictly worse than showing them the
        item unscoped."""
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "a-dataset-that-never-existed",
                          "files": ["a.csv", "b.csv"]}])

        item, = _survey(tmp_path).items

        assert item.agency_id is None
        assert item.dataset_id == "a-dataset-that-never-existed"


class TestResponsesAreNamedNeverOffered:
    """Criterion 8: name the responses, and never present one that
    cannot yet be taken as a control."""

    def test_every_item_names_what_would_resolve_it(self, tmp_path):
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None}])

        for item in _survey(tmp_path).items:
            assert item.responses, item.kind

    def test_nothing_is_actionable_while_the_resolution_path_is_unbuilt(self, tmp_path):
        """The write path belongs with the decision log, delivery sprint
        12. A hold nobody can clear is indistinguishable from a bug, so
        the item says which it is rather than offering a dead control."""
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

        item, = _survey(tmp_path).items

        assert item.actionable is False


class TestItFaultsNobody:
    """Criterion 12: explain what happened and whose task it is, never
    attribute fault to the reader."""

    BLAMING = ("you failed", "you forgot", "your mistake", "you should have",
                "user error")

    def test_no_item_blames_the_reader(self, tmp_path):
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None},
                          {"filename": "both.csv", "dataset_id": None,
                           "contested_by": ["cp-carers", "cp-clients"]}])

        for item in _survey(tmp_path).items:
            text = (item.headline + " " + item.detail).lower()
            for phrase in self.BLAMING:
                assert phrase not in text, (item.kind, phrase)


class TestCommittedHistoryOnly:
    """The NFR: this feeds a dashboard build and may never open data/."""

    def test_the_module_imports_no_database_driver(self):
        source = (outstanding.__file__ and open(outstanding.__file__).read()) or ""
        assert "import duckdb" not in source
        assert "supply_db" not in source

    def test_a_malformed_record_is_skipped_rather_than_fatal(self, tmp_path):
        directory = tmp_path / "delivery_log"
        directory.mkdir(parents=True)
        (directory / "broken.json").write_text("{not json")
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

        found = _survey(tmp_path)

        assert found.total == 1


class TestTheRecordTheDashboardReads:
    def test_as_record_carries_the_total_and_the_per_scope_counts(self, tmp_path):
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

        record = _survey(tmp_path).as_record()

        assert record["total"] == 1
        assert record["blockingCount"] == 1
        assert record["byDataset"] == {"cp-clients": 1}
        assert record["items"][0]["blocking"] is True
        assert record["items"][0]["actionable"] is False

    def test_the_record_is_json_serialisable(self, tmp_path):
        """It is embedded into a single-file page, so anything that
        cannot round-trip through json breaks the build rather than
        one panel."""
        _delivery(tmp_path, "monday",
                   held=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])
        record = _survey(tmp_path).as_record()
        assert json.loads(json.dumps(record)) == record
