"""Tests for qa_tools/common/hierarchy.py (REQ-QAC-039).

Deliberately tested against the REAL contract/data-asset.yaml rather
than a fixture built to match it. The whole point of this module is
that one statement of the tree is authoritative, and a fixture would
let the module and the real config drift apart while every test stayed
green - which is the failure this requirement exists to remove, rebuilt
one level up.

The synthetic-config tests below use tmp_path for the cases the real
file cannot express (a duplicate id, an empty tree), since those must
raise rather than be tolerated and the real file must never contain
them.
"""
from __future__ import annotations

import pytest
import yaml

from qa_tools.common import hierarchy


@pytest.fixture(autouse=True)
def _clear_cache():
    """The loader is lru_cached, so a test that repoints DATA_ASSET_YAML
    would otherwise see the previous test's tree."""
    hierarchy._load.cache_clear()
    yield
    hierarchy._load.cache_clear()


class TestAgainstTheRealConfig:
    def test_every_dataset_resolves_to_a_full_path_through_the_tree(self):
        for entry in hierarchy.all_datasets():
            assert entry.data_asset_id
            assert entry.agency_id and entry.agency_name
            assert entry.collection_id and entry.collection_name
            assert entry.dataset_id and entry.dataset_name
            assert entry.table

    def test_dataset_ids_are_unique_across_the_whole_asset(self):
        ids = [d.dataset_id for d in hierarchy.all_datasets()]
        assert len(ids) == len(set(ids))

    def test_tables_are_unique_so_the_inverse_lookup_is_real(self):
        # dataset-to-table is 1:1 by construction under the supply model
        # (Thread F). If two datasets ever shared a table,
        # dataset_for_table() would silently return whichever came
        # first and the supply model's slot identity would be ambiguous.
        tables = [d.table for d in hierarchy.all_datasets()]
        assert len(tables) == len(set(tables))

    def test_a_dataset_resolves_by_its_own_table_name(self):
        for entry in hierarchy.all_datasets():
            assert hierarchy.dataset_for_table(entry.table) is entry

    def test_qa_results_scope_is_agency_and_collection_for_every_dataset(self):
        # The asymmetry REQ-QAC-039 removes: CP wrote under its
        # collection, BDM under its dataset id. Both are the collection
        # now, so a scope built from this never depends on which
        # dataset it came from.
        for entry in hierarchy.all_datasets():
            assert entry.qa_results_scope == (entry.agency_id, entry.collection_id)

    def test_child_protection_holds_its_six_real_datasets(self):
        found = hierarchy.datasets_in_collection("child-protection")
        assert [d.table for d in found] == [
            "cp_clients", "cp_notifications", "cp_investigations",
            "cp_placements", "cp_carers", "cp_case_workers",
        ]

    def test_birth_registrations_has_a_collection_like_child_protection_does(self):
        # Criterion: "model a collection for Birth Registrations by the
        # same mechanism Child Protection uses, rather than skipping the
        # level". Before this, BDM's collection existed only in the
        # dashboard's own hardcoded tree and in two of its four tool
        # scripts.
        entry = hierarchy.dataset("birth-registrations")
        assert entry.collection_id == "civil-registration"
        assert hierarchy.datasets_in_collection("civil-registration") == [entry]


class TestFailsLoudly:
    def test_an_unknown_dataset_id_names_the_ones_that_exist(self):
        with pytest.raises(hierarchy.UnknownDatasetError) as exc:
            hierarchy.dataset("birth_registrations")  # underscores, not hyphens
        assert "birth-registrations" in str(exc.value)

    def test_an_unknown_table_names_the_tables_that_exist(self):
        with pytest.raises(hierarchy.UnknownDatasetError) as exc:
            hierarchy.dataset_for_table("cp-clients")  # the dataset id, not the table
        assert "cp_clients" in str(exc.value)

    def test_an_unknown_collection_names_the_collections_that_exist(self):
        with pytest.raises(hierarchy.UnknownDatasetError) as exc:
            hierarchy.datasets_in_collection("child_protection")
        assert "child-protection" in str(exc.value)

    def test_it_is_still_a_keyerror_so_existing_handlers_catch_it(self):
        with pytest.raises(KeyError):
            hierarchy.dataset("nope")

    def _write(self, tmp_path, monkeypatch, doc):
        path = tmp_path / "data-asset.yaml"
        path.write_text(yaml.safe_dump(doc))
        monkeypatch.setattr(hierarchy, "DATA_ASSET_YAML", path)
        hierarchy._load.cache_clear()

    def test_a_duplicate_dataset_id_is_an_error_not_a_last_one_wins(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, {
            "data_asset_id": "a",
            "hierarchy": {"agencies": [{"id": "ag", "name": "Ag", "collections": [
                {"id": "c1", "name": "C1", "contract": "c.yaml", "datasets": [{"id": "d", "name": "D", "table": "t1"}]},
                {"id": "c2", "name": "C2", "contract": "c.yaml", "datasets": [{"id": "d", "name": "D", "table": "t2"}]},
            ]}]},
        })
        with pytest.raises(ValueError, match="defined twice"):
            hierarchy.all_datasets()

    def test_a_missing_data_asset_id_is_an_error(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, {"hierarchy": {"agencies": []}})
        with pytest.raises(ValueError, match="data_asset_id"):
            hierarchy.data_asset_id()

    def test_an_empty_tree_is_an_error_rather_than_an_empty_list(self, tmp_path, monkeypatch):
        # Returning [] would let a build produce zero results and call
        # it success - the same green-by-vacuum shape the supply model's
        # zero-active-checks gate exists to stop.
        self._write(tmp_path, monkeypatch, {"data_asset_id": "a", "hierarchy": {"agencies": []}})
        with pytest.raises(ValueError, match="no datasets"):
            hierarchy.all_datasets()
