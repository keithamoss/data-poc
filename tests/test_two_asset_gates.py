"""The configuration gates against a repository holding TWO asset folders
(REQ-PIPE-364 criterion 6; REQ-PIPE-342 criterion 10).

Each refusal REQ-PIPE-364 names is driven here against tests/two_assets.py's
fixture repository, whose two assets are copies of one real asset - so they
reuse every identifier, a collection id among them, and each must still pass
(criterion 3: nothing is compared across assets). A duplicate is made INSIDE
one asset and refused there, with the other asset untouched and still
passing; a read of an item only the other asset holds is refused without the
other asset being consulted (criterion 4); and the top of assets/ holds only
environments.yaml and asset folders (criterion 5).

What names the ASSET in a failure is `mothman check`'s per-asset pass, which
prefixes every line a gate prints with the asset it ran for - tested in
tests/test_cli_check.py. The tests here assert what each gate itself says:
both items, and, for a read across assets, the declaring dataset, the item
and the asset folder checked.
"""
from __future__ import annotations

import pytest

import two_assets as ta
from qa_tools.common import validate_collections as vc
from qa_tools.common import validate_layout as vl


@pytest.fixture
def repo(tmp_path):
    return ta.make(tmp_path)


def _config(repo, name, monkeypatch) -> list[str]:
    ta.acting_for(repo, name, monkeypatch)
    return vc.config_problems()


class TestBothAssetsReuseEveryIdentifierAndPass:
    """Criterion 6's passing case: one collection id, short, run prefix,
    dataset id, table, agency short and seed range in both assets."""

    def test_the_collections_gate_passes_for_each(self, repo, monkeypatch):
        for name in ta.NAMES:
            assert _config(repo, name, monkeypatch) == [], name

    def test_the_providers_gate_passes_for_each(self, repo, monkeypatch):
        from generator import validate_providers

        for name in ta.NAMES:
            ta.acting_for(repo, name, monkeypatch)
            assert validate_providers.problems() == [], name

    def test_linked_datasets_and_reads_pass_for_each(self, repo, monkeypatch):
        from asset_model import linked_datasets
        from qa_tools.common import run_reads

        for name in ta.NAMES:
            ta.acting_for(repo, name, monkeypatch)
            assert linked_datasets.problems(repo) == [], name
            assert run_reads.declaration_problems() == [], name

    def test_both_really_declare_the_same_collection(self, repo):
        ids = {name: ta.collection(ta.hierarchy_of(repo, name))["id"] for name in ta.NAMES}
        assert len(set(ids.values())) == 1, ids


class TestUniqueWithinAnAsset:
    """Criterion 3: a duplicate inside one asset fails, naming both items; the
    other asset - holding the same identifiers once each - still passes."""

    def _refused(self, repo, monkeypatch, *needles: str) -> list[str]:
        found = _config(repo, "one", monkeypatch)
        assert any(all(n in p for n in needles) for p in found), found
        assert _config(repo, "two", monkeypatch) == []
        return found

    def test_a_collection_id_declared_twice(self, repo, monkeypatch):
        coll = ta.collection(ta.hierarchy_of(repo, "one"))["id"]
        ta.add_collection(repo, "one", collection_id=coll, short="bd2", run_prefix="rb2_",
                          dataset_id="ds-two", table="t_two", label="Another")
        self._refused(repo, monkeypatch, f"collection id {coll!r}", "declared twice",
                      "registry-services")

    def test_a_short_shared_by_two_collections(self, repo, monkeypatch):
        short = ta.collection(ta.hierarchy_of(repo, "one"))["short"]
        ta.add_collection(repo, "one", collection_id="other-coll", short=short,
                          run_prefix="rb2_", dataset_id="ds-two", table="t_two", label="Another")
        self._refused(repo, monkeypatch, "'other-coll'", "share the short", repr(short))

    def test_a_run_prefix_shared_by_two_collections(self, repo, monkeypatch):
        prefix = ta.collection(ta.hierarchy_of(repo, "one"))["run_prefix"]
        ta.add_collection(repo, "one", collection_id="other-coll", short="bd2",
                          run_prefix=prefix, dataset_id="ds-two", table="t_two", label="Another")
        self._refused(repo, monkeypatch, "'other-coll'", "share the run_prefix", repr(prefix))

    def test_a_dataset_id_declared_in_two_collections(self, repo, monkeypatch):
        doc = ta.hierarchy_of(repo, "one")
        first, dataset = ta.collection(doc)["id"], ta.dataset(doc)["id"]
        ta.add_collection(repo, "one", collection_id="other-coll", short="bd2",
                          run_prefix="rb2_", dataset_id=dataset, table="t_two", label="Another")
        self._refused(repo, monkeypatch, f"dataset id {dataset!r}", "defined twice",
                      repr(first), "'other-coll'")

    def test_a_table_declared_in_two_collections(self, repo, monkeypatch):
        table = ta.dataset(ta.hierarchy_of(repo, "one"))["table"]
        ta.add_collection(repo, "one", collection_id="other-coll", short="bd2",
                          run_prefix="rb2_", dataset_id="ds-two", table=table, label="Another")
        self._refused(repo, monkeypatch, "table", repr(table), "'other-coll'")

    def test_a_table_declared_by_two_datasets_of_one_collection(self, repo, monkeypatch):
        doc = ta.hierarchy_of(repo, "one")
        dataset, table = ta.dataset(doc)["id"], ta.dataset(doc)["table"]
        ta.add_dataset(repo, "one", "ds-two", table)
        self._refused(repo, monkeypatch, "table", repr(table), repr(dataset), "'ds-two'")

    def test_an_agency_short_shared_by_two_agencies(self, repo, monkeypatch):
        doc = ta.hierarchy_of(repo, "one")
        agency = doc["hierarchy"]["agencies"][0]
        ta.add_collection(repo, "one", collection_id="other-coll", short="bd2",
                          run_prefix="rb2_", dataset_id="ds-two", table="t_two", label="Another")
        doc = ta.hierarchy_of(repo, "one")
        moved = doc["hierarchy"]["agencies"][0]["collections"].pop()
        doc["hierarchy"]["agencies"].append(
            {"id": "other-agency", "name": "Other", "short": agency["short"],
             "collections": [moved]})
        ta.write_hierarchy(repo, "one", doc)
        self._refused(repo, monkeypatch, "'other-agency'", repr(agency["id"]),
                      f"short {agency['short']!r}")

    def test_provider_seed_ranges_that_overlap(self, repo, monkeypatch):
        from generator import validate_providers

        coll = ta.collection(ta.hierarchy_of(repo, "one"))["id"]
        ta.add_collection(repo, "one", collection_id="other-coll", short="bd2",
                          run_prefix="rb2_", dataset_id="ds-two", table="t_two", label="Another")
        ta.acting_for(repo, "one", monkeypatch)
        found = validate_providers.problems()
        assert any(coll in p and "other-coll" in p and "overlap" in p for p in found), found
        ta.acting_for(repo, "two", monkeypatch)
        assert validate_providers.problems() == []


class TestNothingIsLookedUpInTheOtherAsset:
    """Criterion 4: an item only the other asset holds is refused, naming the
    declaring dataset, the item and the asset folder checked."""

    def test_a_linked_dataset_only_the_other_asset_holds(self, repo, monkeypatch):
        from asset_model import linked_datasets

        ta.add_dataset(repo, "two", "two-only", "t_two_only")
        doc = ta.hierarchy_of(repo, "one")
        declaring = ta.dataset(doc)
        declaring["linked_datasets"] = [{"dataset": "two-only",
                                         "id_columns": ["registration_number"]}]
        ta.write_hierarchy(repo, "one", doc)
        asset = ta.acting_for(repo, "one", monkeypatch)
        found = linked_datasets.problems(repo)
        assert any(declaring["id"] in p and "'two-only'" in p and str(asset.folder) in p
                   for p in found), found

    def test_a_read_of_a_table_only_the_other_asset_holds(self, repo, monkeypatch):
        from qa_tools.common import run_reads

        ta.add_dataset(repo, "two", "two-only", "t_two_only")
        doc = ta.hierarchy_of(repo, "one")
        agency, coll, ds = (doc["hierarchy"]["agencies"][0]["id"], ta.collection(doc)["id"],
                            ta.dataset(doc)["id"])
        check = f"one.{agency}.{coll}.{ds}.some_check_soda"
        asset = ta.acting_for(repo, "one", monkeypatch)
        found = run_reads.declaration_problems({check: ["t_two_only"]})
        assert any(ds in p and "'t_two_only'" in p and str(asset.folder) in p
                   for p in found), found


class TestTheTopOfAssets:
    """Criterion 5: only environments.yaml and asset folders - each holding a
    data-asset.yaml - at the top of assets/."""

    def test_the_fixtures_own_layout_passes(self, repo):
        assert vl.assets_top_problems(repo) == []

    def test_a_stray_file_is_refused_naming_it(self, repo):
        (repo / "assets" / "moved-paths.yaml").write_text("moves: []\n")
        assert vl.assets_top_problems(repo) == [
            "assets/moved-paths.yaml sits at the top of assets/, where only environments.yaml "
            "and the asset folders belong"]

    @pytest.mark.parametrize("folder", ["three", "_half-made", ".hidden"])
    def test_a_folder_holding_no_data_asset_yaml_is_refused_naming_it(self, repo, folder):
        (repo / "assets" / folder / "collections").mkdir(parents=True)
        assert vl.assets_top_problems(repo) == [
            f"assets/{folder}/ holds no data-asset.yaml, so it is no asset - make it one, "
            f"or remove it"]


class TestTheSharedTree:
    """REQ-PIPE-342 criterion 10: the shared code tree holds no collection's
    file - qa_tools/collections/ and generator/collections/ only their shared
    base modules, dbt_shared/ only the shared macros and generic tests."""

    def test_the_real_shared_tree_passes(self):
        assert vl.shared_tree_problems() == []

    def test_the_fixtures_copy_passes(self, repo):
        assert vl.shared_tree_problems(repo) == []

    @pytest.mark.parametrize("tree", ["qa_tools/collections", "generator/collections"])
    def test_a_collections_module_in_the_shared_tree_is_refused(self, repo, tree):
        (repo / tree / "civil_registration.py").write_text("ADAPTER = None\n")
        found = vl.shared_tree_problems(repo)
        assert len(found) == 1 and found[0].startswith(f"{tree}/civil_registration.py ")

    def test_a_singular_test_in_dbt_shared_is_refused(self, repo):
        path = repo / "dbt_shared" / "tests" / "civil-registration" / "recency.sql"
        path.parent.mkdir(parents=True)
        path.write_text("select 1 where false\n")
        found = vl.shared_tree_problems(repo)
        assert len(found) == 1 and found[0].startswith(
            "dbt_shared/tests/civil-registration/recency.sql ")

    def test_a_generic_folder_file_that_defines_no_generic_test_is_refused(self, repo):
        (repo / "dbt_shared" / "tests" / "generic" / "orphan.sql").write_text(
            "select * from birth_registrations where false\n")
        found = vl.shared_tree_problems(repo)
        assert len(found) == 1 and found[0].startswith("dbt_shared/tests/generic/orphan.sql ")

    def test_a_shared_macro_naming_a_collections_model_is_refused(self, repo):
        (repo / "dbt_shared" / "macros" / "reads_one.sql").write_text(
            "{% macro reads_one() %}select * from {{ ref('stg_birth_registrations') }}"
            "{% endmacro %}\n")
        found = vl.shared_tree_problems(repo)
        assert len(found) == 1 and "stg_birth_registrations" in found[0]


class TestTheLayoutGateIsAMothmanCommand:
    """CLAUDE.md: every entry point is a mothman subcommand - so `mothman
    check`'s layout gate runs `mothman dashboard validate-layout`, as its
    neighbours run theirs, never `python3 -m` on the module."""

    def test_the_command_passes_over_this_repository(self):
        from click.testing import CliRunner

        from cli.dashboard import dashboard_group

        result = CliRunner().invoke(dashboard_group, ["validate-layout"])
        assert result.exit_code == 0, result.output
        assert "layout OK" in result.output

    def test_the_command_fails_when_the_gate_does(self, monkeypatch):
        from click.testing import CliRunner

        from cli.dashboard import dashboard_group

        monkeypatch.setattr(vl, "assets_top_problems", lambda: ["assets/stray.yaml sits here"])
        result = CliRunner().invoke(dashboard_group, ["validate-layout"])
        assert result.exit_code != 0
        assert "assets/stray.yaml sits here" in result.output
        assert "layout validation failed" in result.output

    def test_mothman_check_runs_it_through_the_command(self):
        import cli.check as check_cli

        argv = {g[0]: g[1] for g in check_cli._GATES}["layout"]
        assert argv == ["uv", "run", "mothman", "dashboard", "validate-layout"]


#: The fixture's assets are copies of this one (tests/two_assets.py).
pytestmark = pytest.mark.asset("daily")
