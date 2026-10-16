"""The collection registry (REQ-PIPE-240): one list of collections, read from
the hierarchy, behind every dispatch site whose code survives the series -
and the gate that keeps it the only one."""
from __future__ import annotations

import contextlib
import json
import sys
from types import SimpleNamespace

import pytest
import yaml

from qa_tools import collections
from qa_tools.common import hierarchy
from qa_tools.common import validate_collections as gate
# The fixtures `third_collection` and `without_adapter` come from
# tests/third_collection.py, made available by tests/conftest.py.
from third_collection import BARE_ID, CODE, FAKE_DATASET, FAKE_ID, FAKE_SHORT


class TestTheRegistry:
    """Criteria 1 to 4."""

    def test_it_lists_the_hierarchys_collections_in_order(self):
        got = [(c.id, c.short, c.run_prefix) for c in collections.all_collections()]
        assert got == [("civil-registration", "bdm", "run_"),
                       ("child-protection", "cp", "cp_run_")]

    def test_a_collection_resolves_by_id_short_or_run_prefix(self):
        for value in ("child-protection", "cp", "cp_run_"):
            assert collections.resolve(value).id == "child-protection"
        assert collections.by_short("bdm").id == "civil-registration"
        assert collections.by_run_prefix("run_").id == "civil-registration"

    def test_a_dataset_resolves_through_one_index(self):
        assert collections.collection_of("cp-carers").id == "child-protection"
        assert collections.dataset("birth-registrations").table == "birth_registrations"

    @pytest.mark.parametrize("lookup,value,known", [
        (collections.by_id, "emergency-department", "civil-registration, child-protection"),
        (collections.by_short, "ed", "bdm, cp"),
        (collections.by_run_prefix, "ed_run_", "run_, cp_run_"),
    ])
    def test_an_unknown_value_is_refused_naming_it_and_every_known_one(self, lookup, value,
                                                                       known):
        with pytest.raises(collections.UnknownCollectionError) as raised:
            lookup(value)
        assert repr(value) in str(raised.value) and known in str(raised.value)

    def test_an_unknown_dataset_is_refused_naming_it(self):
        with pytest.raises(hierarchy.UnknownDatasetError, match="'ed-attendances'"):
            collections.dataset("ed-attendances")

    def test_adapters_load_only_from_this_package(self):
        adapter = collections.adapter("cp")
        assert adapter.collection_id == "child-protection"
        assert type(adapter).__module__ == "qa_tools.collections.base"

    def test_an_id_that_is_not_a_hierarchy_id_never_becomes_a_module_name(self):
        rogue = collections.Collection(id="os.path", name="x", agency_id="a", agency_name="a",
                                       short="x", run_prefix="x_", contract="c",
                                       datasets=())
        with pytest.raises(collections.UnknownCollectionError, match="not a hierarchy id"):
            collections.adapter(rogue)

    def test_a_collection_without_an_adapter_is_refused_by_name(self, without_adapter):
        with pytest.raises(collections.NoAdapterError, match=BARE_ID):
            collections.adapter(BARE_ID)


# ---- criterion 6: a third collection, at every site ---------------------

def _datasets_json(path, doc) -> None:
    path.write_text(json.dumps(doc))


class TestAThirdCollectionAtEverySite:
    """Criterion 6: one test per site, through its entry point. A third
    collection with an adapter is included and run through ITS adapter; one
    without is refused by name."""

    def test_the_processing_pass_reads_its_arrivals(self, third_collection, monkeypatch):
        from qa_tools.common import arrivals, processing_pass

        asked = []
        monkeypatch.setattr(arrivals, "arrivals_from_records",
                            lambda collection_id, _d: asked.append(collection_id) or [])
        processing_pass.all_arrivals()
        assert asked == ["civil-registration", "child-protection", FAKE_ID]

    def test_the_processing_pass_runs_it_with_its_own_code(self, third_collection):
        from qa_tools.common import processing_pass

        orchestrator, builder = processing_pass._modules(FAKE_ID)
        assert orchestrator is sys.modules[CODE] and builder is sys.modules[CODE]

    def test_the_processing_pass_refuses_one_with_no_adapter(self, without_adapter):
        from qa_tools.common import processing_pass

        with pytest.raises(collections.NoAdapterError, match=BARE_ID):
            processing_pass._modules(BARE_ID)

    @pytest.fixture
    def filed(self, supply_dsn):
        import filing_support
        from qa_tools.common import supply_db

        def file(dataset_id):
            supply = f"{dataset_id}@202601010100000000"
            delivery = f"pytest-third-{dataset_id}-{id(self)}"
            filing_support.ensure_delivery(delivery, dataset_id, None)
            with supply_db.connect(label="pytest:third") as conn:
                filing_support.place(conn, dataset_id, supply, "2026-01-01", delivery)
            return supply
        return file

    def test_a_recheck_runs_it_with_its_own_code(self, third_collection, filed, monkeypatch):
        from qa_tools.common import period_overlay, recheck, supply_files

        supply = filed(FAKE_DATASET)
        monkeypatch.setattr(supply_files, "arrival_run_id_of",
                            lambda *_: "fake_things__202601010100000000")
        monkeypatch.setattr(period_overlay, "rebuild_for_arrival", lambda *a, **k: None)
        recheck.execute(dataset_id=FAKE_DATASET, supply_id=supply,
                        run_key="fake_things__202601010100000000__r1", purpose={},
                        run_by="pytest")
        assert [c[0] for c in third_collection] == ["run_one"]

    def test_a_recheck_refuses_one_with_no_adapter(self, without_adapter, filed):
        from qa_tools.common import recheck

        supply = filed("bare-things")
        with pytest.raises(collections.NoAdapterError, match=BARE_ID):
            recheck.execute(dataset_id="bare-things", supply_id=supply,
                            run_key="bare_things__202601010100000000__r1", purpose={},
                            run_by="pytest")

    def test_a_checkpoint_resume_is_named_with_its_short(self, third_collection, monkeypatch):
        from qa_tools.common import checkpoints

        copied = []
        monkeypatch.setattr(checkpoints, "_admin", lambda dsn=None: contextlib.nullcontext())
        monkeypatch.setattr(checkpoints, "_copy", lambda _a, src, dst: copied.append(dst))
        cp = SimpleNamespace(name="mothman_ckpt_fk_003_x", collection_id=FAKE_ID, before=3)
        checkpoints.copy_for_resume(cp, "postgresql://u:p@localhost:5432/anything")
        assert copied and copied[0].startswith(f"{checkpoints.RESUME_PREFIX}{FAKE_SHORT}_003_")

    @pytest.fixture
    def empty_db(self, monkeypatch):
        import dbsupport
        from qa_tools.common import supply_db

        dbsupport.use_empty_supply_db(monkeypatch)
        with supply_db.connect(label="test") as conn:
            supply_db.ensure_schemas(conn)
            yield conn

    def _stub_the_real_collections(self, monkeypatch):
        from qa_tools.common import bootstrap as boot

        dispatched = []
        monkeypatch.setattr("cli.bdm.generate_synthetic_data", lambda **_: None)
        monkeypatch.setattr("cli.cp.generate_synthetic_data", lambda **_: None)
        monkeypatch.setattr("qa_tools.bdm.orchestrate_bdm.run_pipeline", lambda **_: None)
        monkeypatch.setattr("qa_tools.cp.orchestrate_cp.run_pipeline_cp", lambda **_: None)
        monkeypatch.setattr(boot, "_record_deliveries", lambda: None)
        monkeypatch.setattr(boot, "targets_agree", lambda names: ())
        monkeypatch.setattr("qa_tools.common.correction_replay.confirm_due", lambda **k: [])

        def run(names, sequential):
            dispatched.append(list(names))
            return {n: boot._run_collection(n, sequential) for n in names}
        monkeypatch.setattr(boot, "_run_concurrently", run)
        return dispatched

    def test_a_bootstrap_generates_and_runs_it_beside_the_others(self, third_collection,
                                                                 empty_db, monkeypatch):
        """And criterion 11: every registered collection goes to the
        process-per-collection dispatch together."""
        from qa_tools.common import bootstrap as boot

        dispatched = self._stub_the_real_collections(monkeypatch)
        result = boot.bootstrap(collection="all")
        assert result.populated
        assert dispatched == [["bdm", "cp", FAKE_SHORT]]
        assert [c[0] for c in third_collection] == ["generate", "run_pipeline"]

    def test_a_bootstrap_refuses_one_with_no_adapter_before_anything_runs(
            self, without_adapter, empty_db, monkeypatch):
        from qa_tools.common import bootstrap as boot

        dispatched = self._stub_the_real_collections(monkeypatch)
        result = boot.bootstrap(collection="all")
        assert result.refused and BARE_ID in result.reason
        assert dispatched == [] and without_adapter == []

    def test_ticket_sync_reads_its_datasets(self, third_collection, monkeypatch, tmp_path):
        from qa_tools.common import ticket_sync

        built = tmp_path / "built"
        built.mkdir()
        _datasets_json(built / "birth_registrations_dashboard.json",
                       {"id": "birth-registrations", "name": "Birth Registrations"})
        _datasets_json(built / "child_protection_dashboard.json",
                       {"datasets": [{"id": "cp-clients", "name": "Client Register"}]})
        _datasets_json(built / "fake_collection_dashboard.json",
                       {"datasets": [{"id": FAKE_DATASET, "name": "Fake Things"}]})
        monkeypatch.setattr(ticket_sync, "REPORTS_DIR", str(built))
        got = [(s.id, s.agency_id, s.collection_id) for s, _ in ticket_sync._load_scopes()]
        assert got[-1] == (FAKE_DATASET, "fake-agency", FAKE_ID)
        assert [g[0] for g in got] == ["birth-registrations", "cp-clients", FAKE_DATASET]

    def test_ticket_sync_refuses_one_with_no_adapter(self, without_adapter):
        from qa_tools.common import ticket_sync

        with pytest.raises(collections.NoAdapterError, match=BARE_ID):
            ticket_sync._load_scopes()


# ---- criterion 7: the configuration gate --------------------------------

def _package(tmp_path, *modules):
    package = tmp_path / "package"
    package.mkdir(exist_ok=True)
    for m in modules:
        (package / f"{m}.py").write_text("")
    return package


def _edit(edit) -> None:
    doc = yaml.safe_load(hierarchy.DATA_ASSET_YAML.read_text())
    edit(doc["hierarchy"]["agencies"][-1]["collections"][0], doc)
    hierarchy.DATA_ASSET_YAML.write_text(yaml.safe_dump(doc, sort_keys=False))
    hierarchy._load.cache_clear()
    collections._load.cache_clear()


class TestTheConfigurationGate:

    REAL = ("civil_registration", "child_protection")

    def test_the_real_configuration_passes(self):
        assert gate.config_problems() == []

    def test_a_third_collection_with_an_adapter_passes(self, third_collection, tmp_path):
        assert gate.config_problems(_package(tmp_path, *self.REAL, "fake_collection")) == []

    def test_a_collection_with_no_adapter_fails(self, third_collection, tmp_path):
        got = gate.config_problems(_package(tmp_path, *self.REAL))
        assert got == [f"collection {FAKE_ID!r} has no adapter "
                       "(qa_tools/collections/fake_collection.py)"]

    def test_an_adapter_naming_no_collection_fails(self, tmp_path):
        got = gate.config_problems(_package(tmp_path, *self.REAL, "emergency_department"))
        assert got == ["qa_tools/collections/emergency_department.py names no declared "
                       "collection"]

    @pytest.mark.parametrize("edit,expected", [
        (lambda c, _d: c.update(short="cp"), "share the short 'cp'"),
        (lambda c, _d: c.update(run_prefix="cp_run_"), "share the run_prefix 'cp_run_'"),
        (lambda c, _d: c.update(run_prefix="cp_run_fk_"), "begins with 'child-protection'"),
        (lambda c, _d: c.update(run_prefix="fk-run-"), "not made only of a-z, 0-9"),
        (lambda c, _d: c.update(run_prefix="f" * 30 + "_"), "over PostgreSQL's 63"),
        (lambda c, _d: c["datasets"][0].update(id="cp-clients"), "dataset id 'cp-clients'"),
        (lambda c, _d: c["datasets"][0].update(table="cp_clients"), "the table 'cp_clients'"),
        (lambda c, _d: c.update(contract="fake-agency/no-such-contract.yaml"),
         "contract file contract/fake-agency/no-such-contract.yaml is missing"),
    ])
    def test_each_configuration_fault_fails_naming_it(self, third_collection, tmp_path, edit,
                                                      expected):
        _edit(edit)
        got = gate.config_problems(_package(tmp_path, *self.REAL, "fake_collection"))
        assert any(expected in p for p in got), got


# ---- criteria 8 to 10: the literal gate ---------------------------------

def _tree(tmp_path, files: dict[str, str]):
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


class TestTheLiteralGate:

    def _found(self, tmp_path, files):
        return {(rel, text) for rel, _line, text in gate.literal_findings(_tree(tmp_path, files))}

    def test_it_finds_each_kind_of_collection_literal(self, tmp_path):
        got = self._found(tmp_path, {"qa_tools/x.py": (
            'A = "child-protection"\n'
            'B = "cp"\n'
            'C = "contract/bdm-birth-registrations-soda-checks.yml"\n'
            'D = f"cp_run_{n}"\n'
            'E = f"run_7{n}"\n')})
        assert got == {("qa_tools/x.py", "child-protection"), ("qa_tools/x.py", "cp"),
                       ("qa_tools/x.py", "contract/bdm-birth-registrations-soda-checks.yml"),
                       ("qa_tools/x.py", "cp_run_"), ("qa_tools/x.py", "run_7")}

    def test_it_leaves_what_names_no_collection(self, tmp_path):
        assert self._found(tmp_path, {"qa_tools/x.py": (
            '"""A docstring naming child-protection is prose."""\n'
            'A = "cpx"\n'
            'B = "cp-clients@202601010100000000"\n'
            'C = f"run_id {n}"\n'
            'D = "run_"\n'
            'def f():\n    """child-protection, again prose."""\n')}) == set()

    def test_the_exempt_places_are_exempt(self, tmp_path):
        assert self._found(tmp_path, {
            "qa_tools/collections/child_protection.py": 'A = "child-protection"\n',
            "generator/collections/cp.py": 'A = "cp"\n',
            "generator/scenario_injection.py": ('INJECTIONS = ("cp-clients",)\n'
                                                'INHERITING_DATASET = "cp-case-workers"\n'),
        }) == set()

    def test_the_scenario_register_is_exempt_only_in_its_two_values(self, tmp_path):
        assert self._found(tmp_path, {"generator/scenario_injection.py": (
            'INJECTIONS = ("cp-clients",)\nOTHER = "child-protection"\n')}) == {
            ("generator/scenario_injection.py", "child-protection")}

    def test_the_dashboard_template_is_read_too(self, tmp_path):
        assert self._found(tmp_path, {"dashboard/qa-reporting-dashboard.template.html": (
            "<script>const a = 'cp-notifications'; const b = `cp_run_${n}`;</script>\n")}) == {
            ("dashboard/qa-reporting-dashboard.template.html", "cp-notifications"),
            ("dashboard/qa-reporting-dashboard.template.html", "cp_run_${n}")}

    def test_an_unlisted_file_fails_naming_file_line_and_literal(self, tmp_path):
        root = _tree(tmp_path, {"cli/x.py": 'A = 1\nB = "bdm"\n'})
        assert gate.literal_problems(root, allowlist={}) == [
            "cli/x.py:2: 'bdm' names a collection - read it from the registry "
            "(qa_tools.collections), or list the file on the migration allowlist with the "
            "requirement that rewires it"]

    def test_a_listed_file_passes_and_the_list_only_shrinks(self, tmp_path):
        root = _tree(tmp_path, {"cli/x.py": 'B = "bdm"\n', "cli/y.py": "C = 1\n"})
        assert gate.literal_problems(root, allowlist={"cli/x.py": "REQ-TEST-245"}) == []
        got = gate.literal_problems(root, allowlist={"cli/x.py": "REQ-TEST-245",
                                                     "cli/y.py": "REQ-TEST-245"})
        assert got == ["cli/y.py is on the migration allowlist (REQ-TEST-245) but no longer "
                       "holds a collection literal - take it off, so the allowlist only "
                       "shrinks"]

    def test_the_real_tree_passes_with_its_allowlist(self):
        assert gate.literal_findings(), "the real tree must hold something to check"
        assert gate.literal_problems() == []

    def test_every_allowlisted_file_names_a_requirement_of_this_set(self):
        signed = {"REQ-QAC-241", "REQ-QAC-242", "REQ-PIPE-243", "REQ-DASH-244",
                  "REQ-TEST-245", "REQ-GEN-246", "REQ-PIPE-248"}
        assert gate.ALLOWLIST and set(gate.ALLOWLIST.values()) <= signed



# ---- REQ-QAC-241 criteria 2, 5 and 9: the check-file gate ------------------

class TestTheCheckFileGate:

    def test_the_real_tree_passes(self):
        assert gate.check_file_problems() == []

    def test_a_third_collection_with_its_files_passes(self, third_collection, tmp_path):
        assert gate.check_file_problems() == []

    @pytest.mark.parametrize("kind", ["soda-checks", "evidently-checks"])
    def test_a_missing_check_file_fails_naming_the_collection_and_file(
            self, third_collection, tmp_path, kind):
        (tmp_path / "contract" / "fake-agency" / f"fake-things-{kind}.yml").unlink()
        got = gate.check_file_problems()
        assert got == [f"collection {FAKE_ID!r} is missing its {kind.split('-')[0]} check file "
                       f"contract/fake-agency/fake-things-{kind}.yml"]

    def test_a_check_file_outside_its_agencys_folder_fails_naming_it(self, third_collection,
                                                                    tmp_path):
        moved = tmp_path / "contract" / "registry-services" / "fake-things-soda-checks.yml"
        (tmp_path / "contract" / "fake-agency" / "fake-things-soda-checks.yml").rename(moved)
        got = gate.check_file_problems()
        assert ("contract/registry-services/fake-things-soda-checks.yml is "
                f"{FAKE_ID!r}'s, which belongs in its agency's folder contract/fake-agency/") in got

    def test_a_collection_file_at_the_top_of_contract_fails(self, third_collection, tmp_path):
        (tmp_path / "contract" / "fake-things-contract-retired.yaml").write_text("{}\n")
        got = gate.check_file_problems()
        assert any(p.startswith("contract/fake-things-contract-retired.yaml is at the top of "
                                "contract/") for p in got), got

    def test_a_dbt_model_outside_every_collections_folder_fails(self, third_collection, tmp_path):
        (tmp_path / "dbt_project" / "models" / "staging").mkdir(parents=True)
        (tmp_path / "dbt_project" / "models" / "staging" / "stg_x.sql").write_text("select 1\n")
        (tmp_path / "dbt_project" / "tests" / "generic").mkdir(parents=True)
        (tmp_path / "dbt_project" / "tests" / "generic" / "shared.sql").write_text("select 1\n")
        assert gate.check_file_problems() == [
            "dbt_project/models/staging/stg_x.sql sits outside every collection's dbt folder "
            "(dbt_project/models/<collection-id>/, dbt_project/tests/<collection-id>/)"]

    def test_two_collections_declaring_one_singular_test_name_fails(self, third_collection,
                                                                   tmp_path):
        for collection in ("child-protection", FAKE_ID):
            folder = tmp_path / "dbt_project" / "tests" / collection
            folder.mkdir(parents=True)
            (folder / "same_rule.sql").write_text("select 1\n")
        [problem] = gate.check_file_problems()
        assert "singular test 'same_rule' is declared in both" in problem
