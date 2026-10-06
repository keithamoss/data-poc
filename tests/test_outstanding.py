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


@pytest.fixture(autouse=True)
def _no_closed_periods(monkeypatch, request):
    """An empty database has every past slot CLOSED and unfilled, and
    REQ-PIPE-132 turns each into a queue item - real, and not what these
    tests are about. Its own tests are in tests/test_not_supplied.py and
    the class below, which opts back in."""
    if request.node.get_closest_marker("closed_periods") is None:
        monkeypatch.setattr(outstanding, "_from_unfilled_periods", lambda conn=None: [])


@pytest.fixture(autouse=True)
def _a_database_nobody_else_writes_to(private_supply_dsn):
    """EVERY test here runs against a database OF ITS OWN, and each
    tightening was forced by a real failure rather than chosen.

    IT WAS `supply_dsn` UNTIL 2026-09-29 - one database per WORKER,
    which isolates this module from the deployment and from other
    workers but NOT from the other modules pytest-xdist puts on the same
    worker. That is enough for a test asserting on rows it wrote itself.
    It is not enough here, because these tests assert on a GLOBAL total:
    "the queue is empty" is a claim about everything in the database, so
    any module sharing the worker can falsify it.

    It held only by luck of file distribution. Splitting CI into two
    halves moved 270 tests out of the run, `--dist loadfile`
    redistributed the rest, and nine tests here began reporting 28
    items where they expected none - a failure this module had already
    seen the first version of, below.

    Two of the queue's producers read the decision log through narrow
    readers that open their own connection - closed slots through
    filing.filled_slots(), refused inheritances through
    inheritance.refusals(). Both were structurally EMPTY while nothing
    was ever promoted, so a test that asked for no database at all got
    an empty queue for free. The night promotion started working, the
    real deployment's 84 promotions arrived in the middle of nine tests
    asserting on totals.

    Requested autouse rather than per-test, because the failure mode is
    a test that forgets: it passes on an empty deployment and fails on a
    populated one, which is a flake nobody can reproduce.
    """
    return private_supply_dsn


def _delivery(conn, name="monday", **overrides):
    """One delivery record, straight into this worker's database.

    STILL BUILT BY HAND rather than through delivery_log.record(),
    which is deliberate and unchanged from when these were files: the
    point of this module is what the QUEUE does with a record, and
    several of these records describe states - a contested file, a
    hold - that would otherwise need a whole recognition set up to
    produce. What changed is only where the hand-built record lands.

    A `held=` ENTRY ALSO RAISES A REAL HOLD (REQ-PIPE-078). The queue
    stopped reading `qa.delivery.held` when holds got a store of their
    own, because a delivery record is written once and never rewritten,
    so a hold read from one could never stop being outstanding. Both
    are written here because both are what really happens: the
    recognition records what it saw, and the filing pass raises the
    work item.
    """
    from qa_tools.common import qa_store, supply_holds

    record = {"delivery": name, "received_at": "2026-09-01T09:00:00+08:00",
              "collections": ["child-protection"], "files": [], "contested": [],
              "anomalies": []}
    record.update(overrides)
    conn.execute(
        f'INSERT INTO "{qa_store.SCHEMA}".delivery '
        "(name, received_at, received_instant, collections, anomalies) "
        "VALUES (?, ?, ?, ?, ?)",
        [record["delivery"], record["received_at"], record["received_at"],
         json.dumps(record["collections"]), json.dumps(record["anomalies"])])
    for entry in record["contested"]:
        supply_holds.raise_hold(
            conn, dataset_id=entry["dataset_id"],
            supply_id=f"{entry['dataset_id']}@{record['delivery']}",
            # THE ASSIGNMENT-RULE KIND, the only one left: the
            # delivery-level hold was retired 2026-10-02 (REQ-PIPE-105
            # criterion 6). This seeds the queue; which kind does not
            # matter to what these tests assert about it.
            kind=supply_holds.ASSIGNMENT_RULE,
            reason={"unavailable": []},
            raised_by=f"run-for-{record['delivery']}", delivery=record["delivery"])
    for entry in record["files"]:
        conn.execute(
            f'INSERT INTO "{qa_store.SCHEMA}".delivery_file '
            "(delivery, filename, dataset_id, contested_by, received_at, received_instant, "
            "received_from, receipt_sequence) VALUES (?, ?, ?, ?, ?, ?, 'our-clock', 0)",
            [record["delivery"], entry["filename"], entry.get("dataset_id"),
             json.dumps(entry["contested_by"]) if entry.get("contested_by") else None,
             record["received_at"], record["received_at"]])
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
    # NO `filings_dir` since REQ-PIPE-104 - filings are a table, and
    # isolation comes from this worker's own database rather than from a
    # redirected path. The `_clean_filings` fixture below empties it.
    return outstanding.survey(
        observations_dir=kwargs.get("observations_dir", tmp_path / "observations"))


@pytest.fixture(autouse=True)
def _clean_filings(supply_dsn):
    """An empty filing table per test, for the same reason the delivery
    log gets one: this module surveys EVERYTHING, so a filing left behind
    by one test shows up in the next one's total."""
    from qa_tools.common import qa_store, supply_db

    with supply_db.connect(label="test-outstanding-filings") as conn:
        qa_store.ensure_schema(conn)
        conn.execute(f'TRUNCATE "{qa_store.SCHEMA}".filing')
        yield conn


class TestOneQueueNotOnePerRule:
    """Criterion 1: ONE element carrying a total, never one per item
    and never one per producing rule."""

    def test_items_from_four_different_producers_land_in_one_total(self, tmp_path, clean_delivery_log):
        _delivery(clean_delivery_log, "monday",
                   contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
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
                   contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
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
                   contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
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
                   contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

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
                   contested=[{"dataset_id": "a-dataset-that-never-existed",
                          "files": ["a.csv", "b.csv"]}])

        item, = _survey(tmp_path).items

        assert item.agency_id is None
        assert item.dataset_id == "a-dataset-that-never-existed"


class TestResponsesAreNamedNeverOffered:
    """Criterion 8: name the responses, and never present one that
    cannot yet be taken as a control."""

    def test_every_item_names_what_would_resolve_it(self, tmp_path, clean_delivery_log):
        _delivery(clean_delivery_log, "monday",
                   contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
                   files=[{"filename": "note.pdf", "dataset_id": None,
                           "contested_by": None}])

        for item in _survey(tmp_path).items:
            assert item.responses, item.kind

    def test_nothing_is_actionable_while_the_resolution_path_is_unbuilt(self, tmp_path, clean_delivery_log):
        """The write path belongs with the decision log, delivery sprint
        12. A hold nobody can clear is indistinguishable from a bug, so
        the item says which it is rather than offering a dead control."""
        _delivery(clean_delivery_log, "monday",
                   contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

        item, = _survey(tmp_path).items

        assert item.actionable is False


class TestItFaultsNobody:
    """Criterion 12: explain what happened and whose task it is, never
    attribute fault to the reader."""

    BLAMING = ("you failed", "you forgot", "your mistake", "you should have",
                "user error")

    def test_no_item_blames_the_reader(self, tmp_path, clean_delivery_log):
        _delivery(clean_delivery_log, "monday",
                   contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}],
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
                   contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])

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
                   contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])
        record = _survey(tmp_path).as_record()
        assert json.loads(json.dumps(record)) == record


class TestTheRetiredProducersAreGone:
    """REQ-PIPE-131 retired the rules three producers here read: the
    uncertain assignment (REQ-PIPE-065 criteria 1-2), the slot closed by
    monotonic filling (REQ-PIPE-063) and the off-cycle withheld
    promotion (REQ-PIPE-077). Each is removed rather than left as a
    second rule (NFR 4)."""

    def test_none_of_them_remains(self):
        from qa_tools.common import outstanding as out_mod
        for gone in ("_from_filings", "_from_closed_slots", "_from_withheld_promotions",
                     "UNCERTAIN_ASSIGNMENT", "WITHHELD_PROMOTION"):
            assert not hasattr(out_mod, gone), gone

    def test_an_item_carries_no_ambiguity_field(self):
        from qa_tools.common import outstanding as out_mod
        item = out_mod.Item(kind="k", severity=out_mod.WARNING, blocking=False,
                            headline="h", detail="d")
        assert "ambiguity" not in item.as_record()


class TestAHoldLeavesTheQueueWhenItIsResolved:
    """REQ-PIPE-078 criterion 2, and the defect it exists to fix.

    The queue used to read `qa.delivery.held`, a record written once
    and never rewritten - so resolving a hold changed nothing a reader
    could see and the queue went on asking for work already done.
    """

    def test_an_outstanding_hold_is_in_the_queue(self, tmp_path, clean_delivery_log):
        with clean_delivery_log as conn:
            _delivery(conn, "monday",
                       contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])
        found = outstanding.survey(observations_dir=tmp_path)
        assert [i.kind for i in found.items] == ["held-supply"]

    def test_it_is_observed_at_its_receipt_not_when_the_pass_ran(
            self, tmp_path, clean_delivery_log):
        """REAL DEFECT (post-build-review #123 A2): the item carried the
        hold's `raised_at`, the replay's wall clock, so on any past as-of
        date the page dropped every held supply from the queue while the
        dataset row still said Held."""
        with clean_delivery_log as conn:
            _delivery(conn, "monday",
                       contested=[{"dataset_id": "cp-clients", "files": ["a.csv"]}],
                       files=[{"filename": "cp_clients.csv", "dataset_id": "cp-clients"}])
        [item] = outstanding.survey(observations_dir=tmp_path).items
        assert item.observed_at.startswith("2026-09-01")

    def test_a_resolved_one_is_not(self, tmp_path, clean_delivery_log):
        from qa_tools.common import decision_log as dl
        from qa_tools.common import supply_holds

        with clean_delivery_log as conn:
            _delivery(conn, "monday",
                       contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])
            with dl.apply_decision(conn, dl.Decision(
                    agency_id="child-protection-family-support",
                    collection_id="child-protection", dataset_id="cp-clients",
                    action=dl.PROMOTE, supply="cp_clients__20260930060000000000",
                    actor="keith@example.gov.au", actor_kind=dl.PERSON,
                    effective_at="2026-09-30T06:00:00+08:00",
                    to_slot="2026-Q3")) as entry_id:
                pass
            assert supply_holds.resolve(conn, dataset_id="cp-clients",
                                         supply_id="cp-clients@monday",
                                         decision_id=entry_id) is True
        found = outstanding.survey(observations_dir=tmp_path)
        # Only the HOLD is asserted on: promoting into 2026-Q3 closes
        # the earlier unfilled slots, which is REQ-PIPE-063 working
        # rather than residue from this test.
        assert [i.kind for i in found.items if i.kind == "held-supply"] == []

    def test_the_item_says_what_to_do_about_it(self, tmp_path, clean_delivery_log):
        """NFR 2 - a hold nobody can clear is indistinguishable from a
        bug, so the record carries the resolution path."""
        with clean_delivery_log as conn:
            _delivery(conn, "monday",
                       contested=[{"dataset_id": "cp-clients", "files": ["a.csv", "b.csv"]}])
        [item] = outstanding.survey(observations_dir=tmp_path).items
        assert item.responses and any("file" in r for r in item.responses)



@pytest.mark.closed_periods
class TestClosedUnfilledPeriodsAreOneItemPerRun:
    """REQ-PIPE-132 criteria 10 and 11: every closed, unfilled, unmarked
    period is in the queue, consecutive ones of a dataset as one item."""

    def test_they_are_grouped_per_dataset(self):
        items = [i for i in outstanding.survey().items
                 if i.kind == outstanding.CLOSED_UNFILLED_SLOT]
        assert items, "an empty history has closed, unfilled periods"
        per_dataset = {}
        for i in items:
            per_dataset[i.dataset_id] = per_dataset.get(i.dataset_id, 0) + 1
        # Nothing was ever supplied here, so each dataset's gaps are one run.
        assert set(per_dataset.values()) == {1}
        assert all("with no supply" in i.headline and not i.blocking for i in items)
