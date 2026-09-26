"""REQ-PIPE-038 - committed history is keyed per dataset.

Three scopes under a collection, and each answers a different question:
the dataset directories hold the results that describe that table, the
`_cross-table` one holds the records that span tables (REQ-QAC-037), and
`_raw` holds the one genuinely-unmodified output per tool invocation
plus the two pseudo-tools that describe a RUN.

Written against a temporary tree rather than the real committed one for
most of this, because the point is the RULE - what a write produces and
what a read finds - and a fixture can hold the awkward cases the real
history does not happen to contain today.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_tools.common import qa_results_reader as reader
from qa_tools.common import tables_read as tr
from qa_tools.common.qa_results_writer import write_qa_result

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"


def _verified(dataset_id: str, tail: str, run_id: str = "r1") -> dict:
    return {"check_id": f"a.b.{COLLECTION}.{dataset_id}.col.{tail}",
             "dataset_id": dataset_id, "run_id": run_id, "status": "pass"}


@pytest.fixture
def tree(tmp_path):
    """One run of one tool, spanning two datasets."""
    write_qa_result(AGENCY, COLLECTION, "r1", "2026-09-26T10:00:00+08:00", "soda",
                     {"scanStartTimestamp": "2026-09-26T10:00:00", "hasErrors": False},
                     [_verified("cp-clients", "missing_count_soda"),
                      _verified("cp-carers", "missing_count_soda"),
                      _verified("cp-clients", "duplicate_count_soda")],
                     results_dir=tmp_path)
    return tmp_path


class TestAResultIsStoredUnderTheDatasetItDescribes:
    """Criterion 1."""

    def test_one_invocation_fans_out_to_one_file_per_dataset(self, tree):
        written = sorted(str(p.relative_to(tree)) for p in tree.rglob("*.json"))
        assert written == [
            f"{AGENCY}/{COLLECTION}/_raw/r1/soda.json",
            f"{AGENCY}/{COLLECTION}/cp-carers/r1/soda.json",
            f"{AGENCY}/{COLLECTION}/cp-clients/r1/soda.json",
        ]

    def test_each_dataset_file_holds_only_its_own_records(self, tree):
        for dataset, expected in [("cp-clients", 2), ("cp-carers", 1)]:
            path = tree / AGENCY / COLLECTION / dataset / "r1" / "soda.json"
            records = json.loads(path.read_text())["verified"]
            assert len(records) == expected
            assert {r["dataset_id"] for r in records} == {dataset}

    def test_the_result_is_filed_by_what_it_says_not_by_how_it_was_invoked(self, tree):
        """The whole point. A Child Protection Soda scan is invoked
        against the collection, and before this every one of its
        results landed in a single collection-level file - so finding
        one table's history meant filtering that file through a map
        somebody maintained by hand."""
        assert not (tree / AGENCY / COLLECTION / "r1").exists()
        assert (tree / AGENCY / COLLECTION / "cp-clients" / "r1").is_dir()


class TestRawOutputIsRecordedOnce:
    """The decision Keith settled 2026-09-26: recorded where it is
    true, rather than copied into each dataset or filtered per
    dataset."""

    def test_it_lives_in_its_own_scope(self, tree):
        raw = json.loads((tree / AGENCY / COLLECTION / "_raw" / "r1" / "soda.json").read_text())
        assert raw["raw_output"] == {"scanStartTimestamp": "2026-09-26T10:00:00",
                                      "hasErrors": False}

    def test_no_dataset_file_claims_a_raw_output_of_its_own(self, tree):
        """A copy would have each of six files assert that it is the
        output of a scan that covered all six."""
        for dataset in ("cp-clients", "cp-carers"):
            payload = json.loads(
                (tree / AGENCY / COLLECTION / dataset / "r1" / "soda.json").read_text())
            assert payload["raw_output"] is None

    def test_it_is_not_filtered_down_to_one_dataset_anywhere(self, tree):
        """Filtering would break the genuinely-unmodified guarantee
        that is the only reason raw_output is kept at all - a Soda
        document's hasErrors is a fact about the invocation."""
        raw = json.loads((tree / AGENCY / COLLECTION / "_raw" / "r1" / "soda.json").read_text())
        assert set(raw["raw_output"]) == {"scanStartTimestamp", "hasErrors"}

    def test_the_write_returns_the_raw_path(self, tmp_path):
        """It used to return the dataset-scoped path, which no longer
        exists for a tool that produced no record for any dataset."""
        path = write_qa_result(AGENCY, COLLECTION, "r1", "t", "evidently", {"x": 1}, [],
                                results_dir=tmp_path)
        assert path == tmp_path / AGENCY / COLLECTION / "_raw" / "r1" / "evidently.json"
        assert path.is_file()


class TestThePseudoToolsDescribeARun:
    def test_dataset_stats_writes_no_dataset_file(self, tmp_path):
        write_qa_result(AGENCY, COLLECTION, "r1", "t", "dataset_stats",
                         {"row_counts": {"cp_clients": 5}}, run_by="a@b.c",
                         results_dir=tmp_path)
        written = [str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*.json")]
        assert written == [f"{AGENCY}/{COLLECTION}/_raw/r1/dataset_stats.json"]

    def test_its_provenance_is_still_readable(self, tmp_path):
        write_qa_result(AGENCY, COLLECTION, "r1", "2026-09-26T10:00:00+08:00",
                         "dataset_stats", {"row_counts": {}}, run_by="a@b.c",
                         results_dir=tmp_path)
        assert reader.read_run_provenance(AGENCY, COLLECTION, "r1", tmp_path) == {
            "run_timestamp": "2026-09-26T10:00:00+08:00", "run_by": "a@b.c"}

    def test_both_pseudo_tools_are_named_as_run_scoped(self):
        assert tr.RUN_SCOPED_TOOLS == ("dataset_stats", "tables_read")


class TestReadingItBack:
    def test_runs_are_listed_from_the_raw_scope(self, tree):
        """Not from a dataset, which would lose a run entirely if no
        tool had anything to say about that one table."""
        assert reader.list_run_ids(AGENCY, COLLECTION, tree) == ["r1"]

    def test_a_scope_is_never_listed_as_a_run(self, tree):
        assert tr.RAW_SCOPE not in reader.list_run_ids(AGENCY, COLLECTION, tree)
        assert tr.CROSS_TABLE_SCOPE not in reader.list_run_ids(AGENCY, COLLECTION, tree)

    def test_reading_a_tool_without_naming_a_dataset_reads_them_all(self, tree):
        found = reader.read_one(AGENCY, COLLECTION, "r1", "soda", tree)
        assert len(found) == 3

    def test_reading_one_dataset_is_opening_one_directory(self, tree):
        found = reader.read_one(AGENCY, COLLECTION, "r1", "soda", tree, dataset="cp-clients")
        assert {r["dataset_id"] for r in found} == {"cp-clients"}

    def test_a_dataset_with_no_history_reads_as_nothing(self, tree):
        assert reader.read_one(AGENCY, COLLECTION, "r1", "soda", tree,
                                dataset="cp-investigations") == []

    def test_an_absent_collection_reads_as_nothing(self, tmp_path):
        assert reader.list_run_ids(AGENCY, COLLECTION, tmp_path) == []
        assert reader.read_qa_results(AGENCY, COLLECTION, tmp_path) == []


class TestCompletenessIsWhatThisDatasetActuallyOwes:
    """Keith, 2026-09-26. Evidently defines one check in the whole
    collection, so a fixed six-file rule would call five of six
    datasets permanently incomplete."""

    def test_only_cp_notifications_owes_an_evidently_file(self):
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

    def test_a_run_missing_a_raw_file_is_incomplete_and_says_which(self, tree):
        missing = reader.missing_tools(AGENCY, COLLECTION, "r1", tree)
        assert "_raw/dbt" in missing
        assert "_raw/soda" not in missing

    def test_a_dataset_missing_a_tool_it_owes_is_named(self, tree):
        missing = reader.missing_tools(AGENCY, COLLECTION, "r1", tree)
        assert "cp-clients/dbt" in missing

    def test_a_dataset_is_not_asked_for_a_tool_that_does_not_check_it(self, tree):
        missing = reader.missing_tools(AGENCY, COLLECTION, "r1", tree)
        assert "cp-clients/evidently" not in missing


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
        appends them after the dataset files. 1,494 of 3,204 records
        landed in a different position, which is what this catches.
        """
        records = [{"run_id": "r1", "dataset_id": "a", "check_id": f"x.y.{n}_dbt"}
                    for n in ("zebra", "apple", "mango")]

        assert [r["check_id"] for r in reader.canonical_order(records)] == [
            "x.y.apple_dbt", "x.y.mango_dbt", "x.y.zebra_dbt"]
        # The property that actually matters: the SAME records shuffled
        # into any order come out identical.
        assert reader.canonical_order(records) == reader.canonical_order(records[::-1])

    def test_the_real_committed_history_has_a_unique_key_to_sort_on(self):
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
        a file that differs from the others for no reason a reader
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
        import inspect

        from cli import pipeline

        source = inspect.getsource(pipeline.regenerate_history_command.callback)
        assert "rmtree" in source
        # No reshaping of committed files in place - criterion 4 says
        # SHALL NOT migrate, reshape or patch, and a regeneration that
        # quietly edited would satisfy every other criterion.
        assert "json.load" not in source

    def test_it_refuses_to_finish_with_a_stray_scope_left_behind(self):
        """Criterion 5. A leftover run directory at collection level
        reads as a dataset called `run_014`, which is silent."""
        import inspect

        from cli import pipeline

        assert "is_reserved_scope" in inspect.getsource(
            pipeline.regenerate_history_command.callback)


class TestTheRealCommittedHistory:
    """The tree CI actually publishes from."""

    def _collections(self):
        return [("registry-services", "civil-registration"),
                (AGENCY, COLLECTION)]

    def test_every_child_of_a_collection_is_a_dataset_or_a_reserved_scope(self):
        """Criterion 5, against the real tree - nothing left in the old
        shape, where a run directory sat at collection level."""
        from qa_tools.common.hierarchy import datasets_in_collection

        root = Path("qa_results")
        for agency, collection in self._collections():
            base = root / agency / collection
            if not base.is_dir():
                pytest.skip(f"{base} is not present in this checkout")
            known = {d.dataset_id for d in datasets_in_collection(collection)}
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                assert tr.is_reserved_scope(child.name) or child.name in known, (
                    f"{agency}/{collection}/{child.name} is neither a dataset nor a "
                    f"reserved scope - committed history is still in the old shape")

    def test_both_collections_are_keyed_by_the_same_rule(self):
        """Criterion 3. Birth Registrations' collection holds exactly
        one dataset, which is precisely where a special case would look
        harmless."""
        root = Path("qa_results")
        shapes = {}
        for agency, collection in self._collections():
            base = root / agency / collection
            if not base.is_dir():
                pytest.skip(f"{base} is not present in this checkout")
            shapes[collection] = tr.RAW_SCOPE in {d.name for d in base.iterdir() if d.is_dir()}
        assert all(shapes.values()), f"not every collection has a {tr.RAW_SCOPE} scope: {shapes}"
