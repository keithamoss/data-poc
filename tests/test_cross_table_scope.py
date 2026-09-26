"""A cross-table check belongs to the cross-table scope (REQ-QAC-037).

The defect this removes is arbitrariness. A referential check between
placements and carers is equally about both tables, and which one it
got recorded against was decided by where somebody happened to write
the check down - which then decided whose history it appeared in and
whose status carried it.
"""
from __future__ import annotations

import json

import pytest

from qa_tools.common import qa_results_reader as reader
from qa_tools.common import qa_results_writer as writer
from qa_tools.common import tables_read as tr

AGENCY = "child-protection-family-support"
COLLECTION = "child-protection"


def _a_real_cross_table_check_id() -> str:
    from qa_tools.common.validate_check_lifecycle import collect_checks

    declared = tr.declared_by_check_id(collect_checks(None))
    assert declared, "no check in this repo declares that it reads another table"
    return sorted(declared)[0]


class TestItIsRecordedInItsOwnScope:
    """Criteria 1 and 2."""

    def test_a_cross_table_result_lands_in_the_reserved_scope(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MOTHMAN_SUPPLY_DB", str(tmp_path / "absent.duckdb"))
        writer._declared_reads_tables.cache_clear()
        check_id = _a_real_cross_table_check_id()

        writer.write_qa_result(
            AGENCY, COLLECTION, "run_1", "2026-09-26T09:00:00+08:00", "dbt", {},
            verified=[{"check_id": check_id, "dataset_id": "cp-placements", "status": "fail"}],
            results_dir=tmp_path / "qa_results")

        cross = (tmp_path / "qa_results" / AGENCY / COLLECTION
                  / tr.CROSS_TABLE_SCOPE / "run_1" / "dbt.json")
        assert cross.is_file(), "the cross-table result was not written to the reserved scope"
        assert json.loads(cross.read_text())["verified"][0]["check_id"] == check_id

    def test_it_LEAVES_the_dataset_file_rather_than_being_copied(self, tmp_path, monkeypatch):
        """Criterion 2. Two records saying one thing is two records to
        keep in step, and they diverge the first time one is rewritten."""
        monkeypatch.setenv("MOTHMAN_SUPPLY_DB", str(tmp_path / "absent.duckdb"))
        writer._declared_reads_tables.cache_clear()

        path = writer.write_qa_result(
            AGENCY, COLLECTION, "run_1", "2026-09-26T09:00:00+08:00", "dbt", {},
            verified=[{"check_id": _a_real_cross_table_check_id(),
                        "dataset_id": "cp-placements", "status": "fail"}],
            results_dir=tmp_path / "qa_results")

        assert json.loads(path.read_text())["verified"] == []

    def test_an_ordinary_check_stays_where_it_was(self, tmp_path, monkeypatch):
        """The change must not sweep up single-table checks - 235 of the
        259 checks in this repo read only their own table."""
        monkeypatch.setenv("MOTHMAN_SUPPLY_DB", str(tmp_path / "absent.duckdb"))
        writer._declared_reads_tables.cache_clear()

        path = writer.write_qa_result(
            AGENCY, COLLECTION, "run_1", "2026-09-26T09:00:00+08:00", "dbt", {},
            verified=[{"check_id": "not-a-cross-table-check",
                        "dataset_id": "cp-placements", "status": "pass"}],
            results_dir=tmp_path / "qa_results")

        assert len(json.loads(path.read_text())["verified"]) == 1
        assert not (path.parent.parent / tr.CROSS_TABLE_SCOPE).exists()

    def test_the_raw_output_is_not_duplicated_into_the_scope(self, tmp_path, monkeypatch):
        """One tool invocation's native output covers the whole
        collection, and raw_output is already 61% of committed history.
        Copying it would double that to say the same thing twice."""
        monkeypatch.setenv("MOTHMAN_SUPPLY_DB", str(tmp_path / "absent.duckdb"))
        writer._declared_reads_tables.cache_clear()

        writer.write_qa_result(
            AGENCY, COLLECTION, "run_1", "2026-09-26T09:00:00+08:00", "dbt",
            {"a-big": "raw payload"},
            verified=[{"check_id": _a_real_cross_table_check_id(),
                        "dataset_id": "cp-placements", "status": "fail"}],
            results_dir=tmp_path / "qa_results")

        cross = (tmp_path / "qa_results" / AGENCY / COLLECTION
                  / tr.CROSS_TABLE_SCOPE / "run_1" / "dbt.json")
        assert json.loads(cross.read_text())["raw_output"] is None


class TestTheScopeIsNotMistakenForARun:
    """The reserved folder is a SIBLING of the run directories, so
    anything walking that level has to skip it."""

    def test_the_scope_is_not_listed_as_a_run(self, real_committed_history):
        assert tr.CROSS_TABLE_SCOPE not in reader.list_run_ids(AGENCY, COLLECTION)

    def test_the_scope_is_not_reported_as_an_incomplete_run(self, real_committed_history):
        """It holds four tool files, not six - so a walk that read it as
        a run would report it permanently missing dataset_stats and
        tables_read."""
        assert tr.CROSS_TABLE_SCOPE not in reader.incomplete_runs(AGENCY, COLLECTION)

    def test_dataset_scoped_reads_do_not_pick_up_cross_table_results(self, real_committed_history):
        from qa_tools.common.validate_check_lifecycle import collect_checks

        declared = set(tr.declared_by_check_id(collect_checks(None)))
        main = reader.read_qa_results(AGENCY, COLLECTION)
        assert main, "the committed history is empty - this would prove nothing"
        assert not [r for r in main if r.get("check_id") in declared]


class TestTheRebuildPathReadsTheScope:
    """The path CI publishes from, and the one that silently dropped
    every cross-table check when the scope was first introduced -
    3,204 results live against 2,772 rebuilt, with nothing saying so."""

    def test_the_committed_scope_holds_real_cross_table_results(self, real_committed_history):
        found = reader.read_cross_table_results(AGENCY, COLLECTION)
        assert found, "no cross-table results in the committed scope"
        from qa_tools.common.validate_check_lifecycle import collect_checks
        declared = set(tr.declared_by_check_id(collect_checks(None)))
        assert all(r["check_id"] in declared for r in found)

    def test_an_absent_scope_reads_as_nothing_rather_than_raising(self, tmp_path):
        assert reader.read_cross_table_results(AGENCY, COLLECTION, tmp_path) == []

    @pytest.mark.parametrize("module", ["qa_tools.cp.build_results_from_history",
                                         "qa_tools.bdm.build_results_from_history"])
    def test_both_rebuild_paths_read_the_scope(self, module):
        """Asserted structurally. A rebuild that omits this looks
        entirely healthy - it just publishes fewer checks than the run
        actually produced."""
        import importlib
        import inspect

        mod = importlib.import_module(module)
        assert "read_cross_table_results" in inspect.getsource(mod.build_results_from_history)


class TestItReachesEveryParticipatingDataset:
    """Criteria 6 and 7, at the data layer. The render layer is
    asserted separately in tests/test_dashboard_e2e.py, because a
    correct builder says nothing about a template with its own
    transform."""

    def test_a_dataset_that_only_READS_a_check_still_carries_it(self):
        import json as _json
        from pathlib import Path

        built = Path("reports/child_protection_dashboard.json")
        if not built.is_file():
            pytest.skip("the dashboard data has not been built in this checkout")
        data = _json.loads(built.read_text())
        by_id = {d["id"]: d for d in data["datasets"]}

        # cp-carers declares none of these checks; it is only READ by
        # them. Before this requirement it carried none at all.
        carers = [c for c in by_id["cp-carers"]["columns"] if c.get("scope") == "cross-table"]
        assert carers, "cp-carers carries no cross-table section"
        assert sum(len(c["checks"]) for c in carers) > 0

    def test_every_dataset_in_the_collection_carries_the_section(self):
        import json as _json
        from pathlib import Path

        built = Path("reports/child_protection_dashboard.json")
        if not built.is_file():
            pytest.skip("the dashboard data has not been built in this checkout")
        for ds in _json.loads(built.read_text())["datasets"]:
            scoped = [c for c in ds["columns"] if c.get("scope") == "cross-table"]
            assert scoped, f"{ds['id']} carries no cross-table section"

    def test_a_cross_table_check_is_not_rendered_among_the_real_columns(self):
        """It has a column name of its own and that name means nothing
        on the tables it reads - a cp_client_id column on cp_carers
        would be an invented column."""
        import json as _json
        from pathlib import Path

        from qa_tools.common.validate_check_lifecycle import collect_checks

        built = Path("reports/child_protection_dashboard.json")
        if not built.is_file():
            pytest.skip("the dashboard data has not been built in this checkout")
        declared = set(tr.declared_by_check_id(collect_checks(None)))
        for ds in _json.loads(built.read_text())["datasets"]:
            for col in ds["columns"]:
                if col.get("scope"):
                    continue
                for ck in col["checks"]:
                    assert ck.get("check_id") not in declared, (
                        f"{ds['id']}: cross-table check rendered as column {col['name']!r}")


class TestPooledChecksKeepSeparateIdentities:
    """A real defect, found 2026-09-26 by reading the rendered page
    rather than the built JSON.

    REQ-QAC-023 guarantees a check's tail is unique WITHIN ITS COLUMN,
    and that guarantee is what `url_key()` keys on. The cross-table
    section breaks its precondition: it pools checks from several real
    columns into one pseudo-column, so `relationships_soda` on
    `cp_client_id` and `relationships_soda` on `carer_id` arrive as the
    same key.

    Nothing failed. The template looks a row's check up by key and takes
    the first match, so cp-placements rendered "Client reference" twice
    where the second row is really "Carer reference" - and clicking
    either opened the same panel. Wrong information, silently, which is
    the direction this project's own shape-change lesson is about.
    """

    def _built(self):
        import json as _json
        from pathlib import Path

        built = Path("reports/child_protection_dashboard.json")
        if not built.is_file():
            pytest.skip("the dashboard data has not been built in this checkout")
        return _json.loads(built.read_text())

    def test_no_two_checks_in_a_section_share_a_key(self):
        for ds in self._built()["datasets"]:
            for col in ds["columns"]:
                if not col.get("scope"):
                    continue
                keys = [ck["key"] for ck in col["checks"]]
                assert len(keys) == len(set(keys)), (
                    f"{ds['id']} / {col['name']}: duplicate keys "
                    f"{sorted(k for k in keys if keys.count(k) > 1)}")

    def test_the_pooled_section_really_does_mix_columns(self):
        """Otherwise the test above passes because the precondition it
        guards never occurs - and would keep passing after a change
        that reintroduced the collision."""
        from pipeline.dashboard_check_labels import try_parse

        mixed = False
        for ds in self._built()["datasets"]:
            for col in ds["columns"]:
                if col.get("scope") != "cross-table":
                    continue
                columns = {try_parse(ck["check_id"]).column
                            for ck in col["checks"] if try_parse(ck["check_id"])}
                mixed = mixed or len(columns) > 1
        assert mixed, "no section pools more than one real column"

    def test_a_key_still_identifies_exactly_one_check_across_the_dataset(self):
        """The key is what a /check/<key> URL carries, resolved within
        one column - so uniqueness is required there and nowhere else.
        Asserted per column rather than per dataset for that reason."""
        for ds in self._built()["datasets"]:
            for col in ds["columns"]:
                by_key = {}
                for ck in col["checks"]:
                    # The synthesized "no rule defined" placeholder has
                    # no check_id by design - it is not a check.
                    check_id = ck.get("check_id")
                    if check_id is None:
                        continue
                    assert by_key.get(ck["key"], check_id) == check_id, (
                        f"{ds['id']} / {col['name']}: {ck['key']!r} resolves to "
                        f"both {by_key[ck['key']]} and {check_id}")
                    by_key[ck["key"]] = check_id
