"""REQ-PIPE-038 - recorded history is keyed per dataset.

Three scopes under a collection, and each answers a different question:
a dataset's own scope holds the results that describe that table, the
`_cross-table` one holds the records that span tables (REQ-QAC-037), and
`_raw` holds the one genuinely-unmodified output per tool invocation
plus the two pseudo-tools that describe a RUN.

THIS USED TO ASSERT ON A DIRECTORY TREE, and the rewrite is the point
rather than a tidy-up. REQ-PIPE-089 made the history rows in the `qa`
schema, so the three scopes are a column instead of three directories -
but every RULE below is unchanged, because the scopes were always about
what a record DESCRIBES rather than about where it was kept. Each test
now asks the reader what it finds, which is what a real consumer does;
the old ones asked the filesystem what was written, which only the
writer could answer.

WHAT WENT WITH THE TREE, so nobody looks for it: the assertions about
the real committed history's own shape (every child of a collection is a
dataset or a reserved scope; both collections keyed by the same rule).
There is no tree to walk. The claim they protected is now the
regeneration command's own closing check, which refuses to finish with a
stray scope recorded - see TestTheRegenerationCommand.
"""
from __future__ import annotations

import pytest

from qa_tools.common import qa_results_reader as reader
from qa_tools.common import tables_read as tr
from qa_tools.common.qa_results_writer import write_qa_result

#: A real instant rather than the bare "t" these fixtures used to pass.
#: It was only ever a JSON string before REQ-PIPE-089; a run's timestamp
#: is now a timestamptz, and "t" is not one.
_WHEN = "2026-09-26T10:00:00+08:00"

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"


def _verified(dataset_id: str, tail: str, run_id: str = "r1") -> dict:
    return {"check_id": f"a.b.{COLLECTION}.{dataset_id}.col.{tail}",
             "dataset_id": dataset_id, "run_id": run_id, "status": "pass"}


@pytest.fixture
def recorded(clean_qa_history, finish_runs):
    """One run of one tool, spanning two datasets.

    THE RUN IS FINISHED HERE, which REQ-PIPE-089 criterion 13 makes a
    precondition rather than a detail: results are observable only once
    their run says it completed, so a fixture that writes and stops is
    correctly invisible to every reader below.
    """
    write_qa_result(AGENCY, COLLECTION, "r1", _WHEN, "soda",
                     {"scanStartTimestamp": "2026-09-26T10:00:00", "hasErrors": False},
                     [_verified("cp-clients", "missing_count_soda"),
                      _verified("cp-carers", "missing_count_soda"),
                      _verified("cp-clients", "duplicate_count_soda")],
                     run_by="a@b.c")
    finish_runs("r1", agency=AGENCY, collection=COLLECTION, when=_WHEN, run_by="a@b.c")


class TestAResultIsStoredUnderTheDatasetItDescribes:
    """Criterion 1."""

    def test_one_invocation_fans_out_to_one_record_set_per_dataset(self, recorded):
        found = reader.read_one(AGENCY, COLLECTION, "r1", "soda")
        by_dataset = {}
        for record in found:
            by_dataset.setdefault(record["dataset_id"], []).append(record)
        assert {k: len(v) for k, v in sorted(by_dataset.items())} == {
            "cp-carers": 1, "cp-clients": 2}

    def test_each_dataset_holds_only_its_own_records(self, recorded):
        for dataset in ("cp-clients", "cp-carers"):
            found = reader.read_one(AGENCY, COLLECTION, "r1", "soda", dataset=dataset)
            assert found, dataset
            assert {r["dataset_id"] for r in found} == {dataset}

    def test_the_result_is_filed_by_what_it_says_not_by_how_it_was_invoked(self, recorded):
        """The tool was invoked against the COLLECTION, and not one
        record is stored against it - each went to the dataset its own
        record named."""
        found = reader.read_one(AGENCY, COLLECTION, "r1", "soda")
        assert COLLECTION not in {r["dataset_id"] for r in found}
        assert "cp-clients" in {r["dataset_id"] for r in found}


class TestRawOutputIsRecordedOnce:
    """Criterion 2 - it describes the INVOCATION, not a dataset, so
    neither copying it per dataset nor filtering it down was acceptable."""

    def test_it_lives_in_its_own_scope(self, recorded):
        """read_raw() returns the whole ENVELOPE - the payload plus the
        provenance the run recorded - rather than the payload alone, and
        that is its contract rather than an accident: the two are stored
        apart precisely so a verdict query does not drag megabytes of
        tool output it never wanted, and reassembled here for a caller
        that does."""
        envelope = reader.read_raw(AGENCY, COLLECTION, "r1", "soda")
        assert envelope["raw_output"]["hasErrors"] is False
        assert envelope["run_by"] == "a@b.c"

    def test_no_dataset_record_claims_a_raw_output_of_its_own(self, recorded):
        """Asserted through the reader rather than by counting files:
        the raw output is reachable once, by asking for it, and never
        arrives attached to a dataset's results."""
        for dataset in ("cp-clients", "cp-carers"):
            for record in reader.read_one(AGENCY, COLLECTION, "r1", "soda", dataset=dataset):
                assert "raw_output" not in record
                assert "hasErrors" not in record

    def test_it_is_not_filtered_down_to_one_dataset_anywhere(self, recorded):
        envelope = reader.read_raw(AGENCY, COLLECTION, "r1", "soda")
        assert envelope["raw_output"] == {
            "scanStartTimestamp": "2026-09-26T10:00:00", "hasErrors": False}


class TestThePseudoToolsDescribeARun:
    def test_dataset_stats_records_nothing_against_a_dataset(self, clean_qa_history,
                                                              finish_runs):
        write_qa_result(AGENCY, COLLECTION, "r9", _WHEN, "dataset_stats",
                         {"row_counts": {"cp_clients": 3}}, run_by="a@b.c")
        finish_runs("r9", agency=AGENCY, collection=COLLECTION, when=_WHEN, run_by="a@b.c")
        assert reader.read_one(AGENCY, COLLECTION, "r9", "dataset_stats") == []

    def test_its_provenance_is_still_readable(self, clean_qa_history, finish_runs):
        write_qa_result(AGENCY, COLLECTION, "r9", _WHEN, "dataset_stats",
                         {"row_counts": {"cp_clients": 3}}, run_by="a@b.c")
        finish_runs("r9", agency=AGENCY, collection=COLLECTION, when=_WHEN, run_by="a@b.c")
        stats = reader.read_dataset_stats(AGENCY, COLLECTION, "r9")
        assert stats["row_counts"] == {"cp_clients": 3}

    def test_both_pseudo_tools_are_named_as_run_scoped(self):
        assert tr.is_reserved_scope(tr.RAW_SCOPE)
        assert tr.is_reserved_scope(tr.CROSS_TABLE_SCOPE)


class TestReadingItBack:
    def test_runs_are_listed_whatever_any_one_dataset_has_to_say(self, recorded):
        """Not derived from a dataset's own results, which would lose a
        run entirely if no tool had anything to say about that table."""
        assert reader.list_run_ids(AGENCY, COLLECTION) == ["r1"]

    def test_a_scope_is_never_listed_as_a_run(self, recorded):
        listed = reader.list_run_ids(AGENCY, COLLECTION)
        assert tr.RAW_SCOPE not in listed
        assert tr.CROSS_TABLE_SCOPE not in listed

    def test_reading_a_tool_without_naming_a_dataset_reads_them_all(self, recorded):
        assert len(reader.read_one(AGENCY, COLLECTION, "r1", "soda")) == 3

    def test_reading_one_dataset_reads_only_that_one(self, recorded):
        found = reader.read_one(AGENCY, COLLECTION, "r1", "soda", dataset="cp-clients")
        assert {r["dataset_id"] for r in found} == {"cp-clients"}

    def test_a_dataset_with_no_history_reads_as_nothing(self, recorded):
        assert reader.read_one(AGENCY, COLLECTION, "r1", "soda",
                                dataset="cp-investigations") == []

    def test_an_absent_collection_reads_as_nothing(self, clean_qa_history):
        assert reader.list_run_ids(AGENCY, COLLECTION) == []
        assert reader.read_qa_results(AGENCY, COLLECTION) == []


class TestCompletenessIsWhatThisDatasetActuallyOwes:
    """Keith, 2026-09-26. Evidently defines one check in the whole
    collection, so a fixed six-tool rule would call five of six
    datasets permanently incomplete."""

    def test_only_cp_notifications_owes_an_evidently_result(self):
        assert "evidently" in reader.expected_tools_for("cp-notifications")
        for dataset in ("cp-clients", "cp-carers", "cp-case-workers",
                         "cp-investigations", "cp-placements"):
            assert "evidently" not in reader.expected_tools_for(dataset), dataset

    def test_every_dataset_owes_the_three_tools_that_do_check_it(self):
        for dataset in ("cp-clients", "cp-carers", "cp-notifications"):
            assert set(reader.expected_tools_for(dataset)) >= {"dbt", "soda", "datacontract"}

    def test_it_is_derived_from_the_checks_rather_than_configured(self):
        """So a dataset's first Evidently check changes what it owes
        with no list anywhere to remember."""
        import inspect
        source = inspect.getsource(reader.expected_tools_for)
        assert "collect_checks" in source

    def test_a_run_missing_a_tools_raw_output_is_incomplete_and_says_which(self, recorded):
        missing = reader.missing_tools(AGENCY, COLLECTION, "r1")
        assert "_raw/dbt" in missing
        assert "_raw/soda" not in missing

    def test_a_dataset_missing_a_tool_it_owes_is_named(self, recorded):
        assert "cp-clients/dbt" in reader.missing_tools(AGENCY, COLLECTION, "r1")

    def test_a_dataset_is_not_asked_for_a_tool_that_does_not_check_it(self, recorded):
        assert "cp-clients/evidently" not in reader.missing_tools(AGENCY, COLLECTION, "r1")


class TestOneAgreedOrdering:
    """canonical_order(). A live run and a rebuild hold the same
    records in a different sequence now, and diffing the two is how
    several behaviour-preserving refactors were actually verified."""

    def test_it_orders_by_run_then_tool_then_dataset(self):
        records = [
            {"run_id": "r2", "dataset_id": "b", "check_id": "x.y.a_dbt"},
            {"run_id": "r1", "dataset_id": "b", "check_id": "x.y.a_soda"},
            {"run_id": "r1", "dataset_id": "a", "check_id": "x.y.a_soda"},
            {"run_id": "r1", "dataset_id": "a", "check_id": "x.y.a_dbt"},
        ]
        ordered = reader.canonical_order(records)
        assert [(r["run_id"], r["check_id"].rsplit("_", 1)[-1], r["dataset_id"])
                 for r in ordered] == [
            ("r1", "dbt", "a"), ("r1", "soda", "a"), ("r1", "soda", "b"), ("r2", "dbt", "b")]

    def test_runs_sort_numerically_not_as_strings(self):
        records = [{"run_id": f"cp_run_{n}", "dataset_id": "a", "check_id": "x.y.a_dbt"}
                    for n in ("100", "11", "9")]
        assert [r["run_id"] for r in reader.canonical_order(records)] == [
            "cp_run_9", "cp_run_11", "cp_run_100"]

    def test_it_is_a_TOTAL_order_and_not_merely_a_stable_one(self):
        """The first version left ties to the input order, on the
        reasoning that a tool's own order for one table is identical
        down both paths. It is not - a live run holds cross-table
        records interleaved where the tool emitted them, a rebuild
        appends them after the dataset ones. 1,494 of 3,204 records
        landed in a different position, which is what this catches.
        """
        records = [{"run_id": "r1", "dataset_id": "a", "check_id": f"x.y.{n}_dbt"}
                    for n in ("zebra", "apple", "mango")]

        assert [r["check_id"] for r in reader.canonical_order(records)] == [
            "x.y.apple_dbt", "x.y.mango_dbt", "x.y.zebra_dbt"]
        # The property that actually matters: the SAME records shuffled
        # into any order come out identical.
        assert reader.canonical_order(records) == reader.canonical_order(records[::-1])

    def test_the_real_recorded_history_has_a_unique_key_to_sort_on(self):
        """A total order is only available because one run produces one
        result per check. If that ever stops being true the ordering
        silently goes back to depending on input order."""
        import json as _json
        from collections import Counter
        from pathlib import Path as _Path

        for name in ("cp", "bdm"):
            built = _Path(f"reports/results_{name}.json")
            if not built.is_file():
                pytest.skip("the results have not been built in this checkout")
            results = _json.loads(built.read_text())["results"]
            keys = Counter((r["run_id"], r["check_id"]) for r in results)
            assert len(keys) == len(results), (
                f"{name}: {len(results) - len(keys)} duplicate (run_id, check_id) pairs")

    def test_both_orchestrators_and_both_rebuilds_apply_it(self):
        """Asserted structurally. A path that skipped it would produce
        results that differ from the others for no reason a reader
        could see."""
        import importlib
        import inspect
        for module, function in [
            ("qa_tools.cp.orchestrate_cp", "run_pipeline_cp"),
            ("qa_tools.bdm.orchestrate_bdm", "run_pipeline"),
            ("qa_tools.cp.build_results_from_history", "build_results_from_history"),
            ("qa_tools.bdm.build_results_from_history", "build_results_from_history"),
        ]:
            mod = importlib.import_module(module)
            assert "canonical_order" in inspect.getsource(getattr(mod, function)), module


class TestTheRegenerationCommand:
    """Criteria 4-7."""

    def test_it_is_a_mothman_subcommand(self):
        from cli.pipeline import pipeline_group

        assert "regenerate-history" in pipeline_group.commands

    def test_it_deletes_rather_than_migrating(self):
        """It deleted directories and now deletes runs - criterion 4
        says SHALL NOT migrate, reshape or patch, and a regeneration
        that quietly edited recorded results in place would satisfy
        every other criterion."""
        import inspect

        from cli import pipeline

        source = inspect.getsource(pipeline.regenerate_history_command.callback)
        assert "delete_history" in source
        assert "UPDATE" not in source

    def test_one_delete_takes_a_runs_whole_record_with_it(self, clean_qa_history,
                                                           finish_runs):
        """Not seven statements that can disagree about what a
        collection is - everything hangs off `run` by a foreign key
        with ON DELETE CASCADE, which is the point of modelling it that
        way."""
        from qa_tools.common import qa_store

        write_qa_result(AGENCY, COLLECTION, "r1", _WHEN, "soda", {"hasErrors": False},
                         [_verified("cp-clients", "missing_count_soda")], run_by="a@b.c")
        finish_runs("r1", agency=AGENCY, collection=COLLECTION, when=_WHEN, run_by="a@b.c")
        assert reader.read_one(AGENCY, COLLECTION, "r1", "soda")

        with __import__("qa_tools.common.supply_db", fromlist=["x"]).connect(
                label="test-regenerate") as conn:
            qa_store.ensure_schema(conn)
            assert qa_store.delete_history(conn, AGENCY, COLLECTION) == 1

        assert reader.list_run_ids(AGENCY, COLLECTION) == []
        assert reader.read_one(AGENCY, COLLECTION, "r1", "soda") == []
        assert reader.read_raw(AGENCY, COLLECTION, "r1", "soda") is None

    def test_it_refuses_to_finish_with_a_stray_scope_recorded(self):
        """Criterion 5. A scope that is neither a dataset nor a reserved
        name reads as a dataset nobody configured, which is silent."""
        import inspect

        from cli import pipeline

        assert "is_reserved_scope" in inspect.getsource(
            pipeline.regenerate_history_command.callback)
