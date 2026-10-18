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
from third_collection import BARE_ID, FAKE_DATASET, FAKE_ID, FAKE_PREFIX, FAKE_SHORT, FAKE_TABLE


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

    def test_the_processing_pass_runs_it_through_the_shared_orchestrator(
            self, third_collection, monkeypatch):
        """Staging, the run, filing and promotion are all shared code now
        (REQ-QAC-242, REQ-PIPE-243): the pass asks the one orchestrator for
        the collection's lifecycle steps, and each step carries ITS id."""
        from qa_tools.common import processing_pass
        from qa_tools.tools import orchestrate

        ran = []
        monkeypatch.setattr(orchestrate, "run_one",
                            lambda collection_id, entry, *a, **k: ran.append((collection_id, entry)) or [])
        steps = processing_pass._steps(FAKE_ID)
        steps.run_one({"run_id": "fk_run_001"}, "now", "pytest")
        assert ran == [(FAKE_ID, {"run_id": "fk_run_001"})]

    def test_the_processing_pass_refuses_one_with_no_adapter(self, without_adapter):
        from qa_tools.common import processing_pass

        with pytest.raises(collections.NoAdapterError, match=BARE_ID):
            processing_pass._steps(BARE_ID)

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

    def test_a_recheck_runs_it_through_the_shared_orchestrator(self, third_collection, filed,
                                                               monkeypatch):
        from qa_tools.common import period_overlay, recheck, supply_files
        from qa_tools.tools import orchestrate

        ran = []
        monkeypatch.setattr(orchestrate, "run_one",
                            lambda collection_id, entry, *a, **k: ran.append(collection_id) or [])
        monkeypatch.setattr(orchestrate, "discard_run_schemas", lambda run_key: None)
        supply = filed(FAKE_DATASET)
        monkeypatch.setattr(supply_files, "arrival_run_id_of",
                            lambda *_: "fake_things__202601010100000000")
        monkeypatch.setattr(period_overlay, "rebuild_for_arrival", lambda *a, **k: None)
        recheck.execute(dataset_id=FAKE_DATASET, supply_id=supply,
                        run_key="fake_things__202601010100000000__r1", purpose={},
                        run_by="pytest")
        assert ran == [FAKE_ID]

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

        dispatched, self.ran = [], []
        import tempfile
        from pathlib import Path

        from generator import driver, scenario_injection

        # The two real collections generate nothing; the fake's own plan()
        # records that the shared driver asked for it (REQ-GEN-246), with
        # everything the driver writes kept out of the real data/.
        scratch = Path(tempfile.mkdtemp())
        for name, value in (("DELIVERIES_DIR", scratch / "deliveries"),
                            ("RECEIPTS_DIR", scratch / "receipts"),
                            ("BOOKKEEPING_PATH", scratch / "bookkeeping.json")):
            monkeypatch.setattr(driver, name, value)
        monkeypatch.setattr(scenario_injection, "PLACEMENTS_PATH", scratch / "placements.json")
        real = driver.generate
        monkeypatch.setattr(driver, "generate", lambda cid: real(cid) if cid == FAKE_ID else [])
        monkeypatch.setattr("qa_tools.common.scenario_map.write_map", lambda: None)
        monkeypatch.setattr(__import__("cli.collection_cli", fromlist=["of"]).of("bdm"), "try_targets", lambda **_: 0)
        monkeypatch.setattr("qa_tools.tools.orchestrate.run_pipeline",
                            lambda collection_id, *_, **__: self.ran.append(collection_id))
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
        assert [c[0] for c in third_collection] == ["generate"]
        assert self.ran == ["civil-registration", "child-protection", FAKE_ID]

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
        # post-build-review #230: every picker shows a collection by its label
        # and dispatches on it, so two that share one would send a person to
        # the wrong collection.
        (lambda c, _d: c["datasets"][0].update(name="Child Protection"),
         "share the label 'Child Protection'"),
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



# ---- REQ-QAC-242: the shared tool modules ----------------------------------

class TestTheSharedToolModules:
    """Criterion 9: each rewired site run for a third collection, through its
    own adapter - the tool itself stood in for, since the fixture has no
    warehouse."""

    def test_datacontract_reads_everything_it_needs_from_the_adapter(
            self, third_collection, monkeypatch):
        from qa_tools.tools import run_datacontract as dc

        check = SimpleNamespace(
            type="field_quality_sql", model=FAKE_TABLE, field="things", name="n",
            qualityDefinition=f"a.fake-agency.{FAKE_ID}.{FAKE_DATASET}.things.pair_datacontract",
            diagnostics={"metric": "custom_sql", "value": 2, "severity": "error"},
            dimension="consistency", result=SimpleNamespace(value="failed"))
        sampled, written = [], []
        monkeypatch.setattr(dc.asked_for, "ask", lambda *a, **k: [])
        monkeypatch.setattr(dc.asked_for, "SCOPED", frozenset())
        monkeypatch.setattr(dc, "run_against_warehouse", lambda path, schema, **o: SimpleNamespace(
            checks=[check], model_dump=lambda: {"path": path}))
        monkeypatch.setattr(dc, "_unreadable_in", lambda run_id, tables: frozenset())
        monkeypatch.setattr(dc, "_declared_reads_tables", lambda: {})
        monkeypatch.setattr(dc, "_authored_names", lambda path: {check.qualityDefinition: "Pair"})
        monkeypatch.setattr(dc, "check_id_from_quality_definition", lambda q: q)
        monkeypatch.setattr(dc, "fail_threshold_from_quality_definition", lambda *a: 0)
        monkeypatch.setattr(dc, "failing_sample_keys", lambda c, key: sampled.append(key) or [])
        monkeypatch.setattr(dc, "write_qa_result", lambda *a, **k: written.append(a))

        [r] = dc.evaluate(FAKE_ID, "fake_things__1", "2026-01-01T00:00:00Z")

        assert (r["agency_id"], r["collection_id"], r["dataset_id"]) == \
            ("fake-agency", FAKE_ID, FAKE_DATASET)
        assert r["label"] == "Fake pair" and r["check_name"] == "datacontract:sql: Pair"
        assert written[0][:2] == ("fake-agency", FAKE_ID)
        assert written[0][5]["path"].endswith("contract/fake-agency/fake-things-contract.yaml")
        assert sampled == []  # custom_sql is never sampled; the key is the adapter's when it is

    def test_a_rule_over_an_unreadable_table_is_left_out_and_noted(
            self, third_collection, monkeypatch):
        """A rule over a table the run has no view for is not recorded, and
        is noted as left out - for every collection since REQ-QAC-247
        retired Birth Registrations' exemption."""
        from qa_tools.tools import run_datacontract as dc

        check = SimpleNamespace(
            type="field_null_values", model=FAKE_TABLE, field="things", name="n",
            qualityDefinition=f"a.fake-agency.{FAKE_ID}.{FAKE_DATASET}.things.nullValues_datacontract",
            diagnostics={"metric": "null_count", "value": 0}, dimension="completeness",
            result=SimpleNamespace(value="failed"))
        notes = []
        monkeypatch.setattr(dc.asked_for, "ask", lambda *a, **k: [])
        monkeypatch.setattr(dc.asked_for, "SCOPED", frozenset())
        monkeypatch.setattr(dc, "run_against_warehouse", lambda *a, **o: SimpleNamespace(
            checks=[check], model_dump=lambda: {}))
        monkeypatch.setattr(dc, "_unreadable_in", lambda run_id, tables: frozenset({FAKE_TABLE}))
        monkeypatch.setattr(dc, "_declared_reads_tables", lambda: {})
        monkeypatch.setattr(dc, "_authored_names", lambda path: {})
        monkeypatch.setattr(dc, "check_id_from_quality_definition", lambda q: q)
        monkeypatch.setattr(dc, "fail_threshold_from_quality_definition", lambda *a: 0)
        monkeypatch.setattr(dc, "failing_sample_keys", lambda c, key: [])
        monkeypatch.setattr(dc, "write_qa_result", lambda *a, **k: None)
        monkeypatch.setattr(dc.left_out, "note", lambda run_id, tool, ids: notes.extend(ids))

        got = dc.evaluate(FAKE_ID, "fake_things__1", "2026-01-01T00:00:00Z")

        assert (len(got), len(notes)) == (0, 1)

    def _soda(self, monkeypatch, tmp_path, legacy=frozenset(), soda=None, readable=(FAKE_TABLE,)):
        """The shared Soda runner over a stub scan, for the third collection:
        one generic check with a filter, one custom-named `failed rows`."""
        import dataclasses

        from qa_tools.collections.base import SodaSpec
        from qa_tools.tools import run_soda

        adapter = sys.modules["qa_tools.collections.fake_collection"]
        adapter.ADAPTER = dataclasses.replace(
            adapter.ADAPTER, legacy=legacy,
            soda=soda or SodaSpec(data_source="fake_source",
                                  column_by_name={"things pair up": "things"},
                                  label_by_name={"things pair up": "Pairing"},
                                  dimension_by_name={"things pair up": "consistency"},
                                  dimension_by_metric={"missing_count": "completeness"}))
        checks = tmp_path / "fake-soda.yml"
        checks.write_text(f"checks for {FAKE_TABLE}:\n  - row_count > 0:\n"
                          f"      attributes: {{check_id: x}}\n")
        prefix = f"a.fake-agency.{FAKE_ID}.{FAKE_DATASET}"
        scan_results = {"metrics": [{"identity": "m1", "metricName": "missing_count"}], "checks": [
            {"table": FAKE_TABLE, "column": "things", "name": "missing_count(things) = 0 warn when > 0",
             "filter": "recent", "metrics": ["m1"], "outcome": "fail",
             "diagnostics": {"value": 3}, "resourceAttributes": [
                 {"name": "check_id", "value": f"{prefix}.things.missing_count_soda"}]},
            {"table": FAKE_TABLE, "column": None, "name": "things pair up", "filter": None,
             "metrics": [], "outcome": "fail", "diagnostics": {"value": 2}, "resourceAttributes": [
                 {"name": "check_id", "value": f"{prefix}.things.pair_soda"}]},
        ]}
        conn = SimpleNamespace(execute=lambda sql: SimpleNamespace(fetchone=lambda: (7,)),
                               close=lambda: None)
        written = []
        monkeypatch.setattr(run_soda.asked_for, "ask", lambda *a, **k: [])
        monkeypatch.setattr(run_soda.asked_for, "SCOPED", frozenset())
        monkeypatch.setattr(run_soda, "checks_path", lambda collection_id: str(checks))
        monkeypatch.setattr(run_soda.supply_db, "connect", lambda **k: conn)
        monkeypatch.setattr(run_soda.supply_db, "readable_in", lambda c, run_id: set(readable))
        monkeypatch.setattr(run_soda, "execute_scan", lambda scan: scan_results)
        monkeypatch.setattr(run_soda, "unreported_checks", lambda *a: [])
        monkeypatch.setattr(run_soda, "write_qa_result", lambda *a, **k: written.append(a))
        got = run_soda.evaluate(FAKE_ID, "fake_things__1", "2026-01-01T00:00:00Z")
        return {r["check_id"].rsplit(".", 1)[-1]: r for r in got}, written

    def test_soda_reads_everything_it_needs_from_the_adapter(self, third_collection,
                                                             monkeypatch, tmp_path):
        got, written = self._soda(monkeypatch, tmp_path)
        generic, named = got["missing_count_soda"], got["pair_soda"]
        assert {r["collection_id"] for r in got.values()} == {FAKE_ID}
        assert (generic["check_name"], generic["dimension"], generic["label"]) == \
            ("missing_count", "completeness", "Null rate")
        assert (named["column_name"], named["label"], named["dimension"]) == \
            ("things", "Pairing", "consistency")
        assert generic["row_count_total"] == 7 and written[0][:2] == ("fake-agency", FAKE_ID)

    @pytest.mark.parametrize("flag,field,without,with_", [
        ("soda.scope_suffix", ("missing_count_soda", "check_name"),
         "missing_count", "missing_count[recent]"),
        ("soda.named_check_value_is_invalid_count", ("pair_soda", "row_count_invalid"), None, 2),
    ])
    def test_each_soda_flag_changes_only_its_own_field(self, third_collection, monkeypatch,
                                                      tmp_path, flag, field, without, with_):
        check, key = field
        plain, _ = self._soda(monkeypatch, tmp_path)
        flagged, _ = self._soda(monkeypatch, tmp_path, legacy=frozenset({flag}))
        assert (plain[check][key], flagged[check][key]) == (without, with_)
        flagged[check][key] = plain[check][key]
        assert flagged == plain

    def test_soda_is_never_handed_a_check_over_an_unreadable_table(self, third_collection,
                                                                    monkeypatch, tmp_path):
        from qa_tools.tools import run_soda

        handed = []
        monkeypatch.setattr(run_soda, "readable_checks_yaml",
                            lambda path, unreadable, keep=None: handed.append(set(unreadable)) or "")
        try:
            self._soda(monkeypatch, tmp_path, readable=())
        except KeyError:
            pass  # nothing readable, so no row count for the stub's checks
        assert handed == [{FAKE_TABLE}]

    def _evidently(self, monkeypatch, legacy=frozenset(), readable=True):
        """The shared Evidently runner for the third collection, the tool and
        the warehouse stood in for: one drift check, one volume check."""
        import dataclasses

        import pandas as pd

        from qa_tools.common.evidently_common import EvidentlyChecks
        from qa_tools.tools import run_evidently as ev

        adapter = sys.modules["qa_tools.collections.fake_collection"]
        adapter.ADAPTER = dataclasses.replace(adapter.ADAPTER, legacy=legacy)
        prefix = f"a.fake-agency.{FAKE_ID}.{FAKE_DATASET}"
        band = {"warn_threshold": 0.1, "fail_threshold": 0.25}
        checks = EvidentlyChecks(
            {f"{prefix}.kind.drift_psi_evidently": {"column": "kind", "method": "psi", **band},
             f"{prefix}.row_count_growth_evidently": {"column": "fake_id", "method": "row_drop", **band}},
            f"{prefix}.kind.drift_psi_evidently", {FAKE_TABLE: f"{prefix}.row_count_growth_evidently"})
        written, notes = [], []
        monkeypatch.setattr(ev, "collection_checks", lambda collection_id: checks)
        monkeypatch.setattr(ev.asked_for, "ask", lambda *a, **k: [])
        monkeypatch.setattr(ev, "_psi_applies", lambda run_id, table: readable)
        monkeypatch.setattr(ev, "_unreadable", lambda run_id, table: not readable)
        monkeypatch.setattr(ev, "_current_frame", lambda *a: pd.DataFrame({"kind": ["a", "b", "a"]}))
        monkeypatch.setattr(ev, "_current_row_counts", lambda run_id, tables: {FAKE_TABLE: 90})
        monkeypatch.setattr(ev, "_row_count_of", lambda df: (len(df), {"rows": len(df)}))
        monkeypatch.setattr(ev, "recorded_row_counts", lambda *a: {FAKE_TABLE: 100})
        monkeypatch.setattr(ev, "recorded_row_count", lambda *a: 100)
        monkeypatch.setattr(ev, "_reference_frame", lambda *a: pd.DataFrame({"kind": ["a", "b", "b"]}))
        monkeypatch.setattr(ev, "compute_psi", lambda current, reference, column: (0.05, {"psi": 0.05}))
        monkeypatch.setattr(ev.drift_reference, "judge", lambda results, assessment: None)
        monkeypatch.setattr(ev.left_out, "note", lambda run_id, tool, ids: notes.extend(ids))
        monkeypatch.setattr(ev, "write_qa_result", lambda *a, **k: written.append(a))
        got = ev.evaluate(FAKE_ID, "fake_things__1", "2026-01-01T00:00:00Z", reference_run_id="r")
        return {r["check_name"]: r for r in got}, written[0][5], notes

    def test_evidently_reads_everything_it_needs_from_the_adapter(self, third_collection,
                                                                  monkeypatch):
        got, raw, notes = self._evidently(monkeypatch)
        psi, volume = got["drift:PSI"], got["evidently:row_count_growth"]
        assert {psi["collection_id"], volume["collection_id"]} == {FAKE_ID}
        assert (psi["dataset_id"], psi["column_name"]) == (FAKE_DATASET, "kind")
        assert (volume["column_name"], volume["metric_value"], volume["row_count_total"]) == \
            ("(table)", 10.0, 90)
        assert set(raw) == {"psi"} and notes == []

    def test_evidently_volume_from_drift_frame_keeps_the_single_table_count(
            self, third_collection, monkeypatch):
        got, raw, _ = self._evidently(
            monkeypatch, legacy=frozenset({"evidently.volume_from_drift_frame"}))
        volume = got["evidently:row_count_growth"]
        assert (volume["column_name"], volume["row_count_total"], volume["metric_value"]) == \
            ("fake_id", 3, 97.0)
        assert raw["row_count"] == {"rows": 3}

    def test_the_drift_check_over_an_unreadable_table_is_left_out_and_noted(
            self, third_collection, monkeypatch):
        got, _, notes = self._evidently(monkeypatch, readable=False)
        assert ("drift:PSI" in got, bool(notes)) == (False, True)

    def _dbt(self, monkeypatch, tmp_path, legacy=frozenset(), status="pass", built=True,
             unreadable=frozenset(), asked=(), ran=True):
        """The shared dbt runner for the third collection, dbt itself and the
        warehouse stood in for: one not_null test on its one model, and one
        test of another collection's model, which it must leave alone."""
        import dataclasses
        import json

        from qa_tools.collections.base import DbtSpec
        from qa_tools.tools import run_dbt

        adapter = sys.modules["qa_tools.collections.fake_collection"]
        adapter.ADAPTER = dataclasses.replace(
            adapter.ADAPTER, legacy=legacy,
            dbt=DbtSpec(dimension_by_test={"not_null": "completeness"},
                        label_by_test={"not_null": "Null rate"}))
        mine = {"name": "not_null_x", "resource_type": "test", "column_name": "things",
                "test_metadata": {"name": "not_null"}, "attached_node": f"model.p.stg_{FAKE_TABLE}",
                "config": {}, "relation_name": '"audit"."not_null_x"'}
        theirs = dict(mine, name="not_null_y", attached_node="model.p.stg_cp_clients")
        (tmp_path / "manifest.json").write_text(json.dumps(
            {"nodes": {"test.p.mine": mine, "test.p.theirs": theirs}}))
        (tmp_path / "run_results.json").write_text(json.dumps({"results": [
            {"unique_id": "test.p.mine", "status": status, "failures": 0},
            {"unique_id": "test.p.theirs", "status": "pass", "failures": 0}][0 if ran else 1:]}))
        queries, built_models, built_runs = [], {f"stg_{FAKE_TABLE}"} if built else set(), []

        class _Conn:
            def execute(self, sql, *a):
                queries.append(sql)
                rows = [(m,) for m in built_models] if "information_schema" in sql else [(4,)]
                return SimpleNamespace(fetchall=lambda: rows, fetchone=lambda: rows[0])

            def close(self):
                pass
        notes = []
        monkeypatch.setattr(run_dbt.asked_for, "ask", lambda *a, **k: list(asked))
        monkeypatch.setattr(run_dbt.asked_for, "SCOPED", frozenset())
        monkeypatch.setattr(run_dbt.supply_db, "dbt_target_path", lambda run_id: tmp_path)
        monkeypatch.setattr(run_dbt.supply_db, "connect_dbt", lambda run_id: _Conn())
        monkeypatch.setattr(run_dbt, "_unreadable_in", lambda run_id: unreadable)
        monkeypatch.setattr(run_dbt, "exclude_unreadable", lambda models, unreadable:
                            [f"stg_{t}" for t in unreadable])
        monkeypatch.setattr(run_dbt, "run_dbt", lambda command, select, *a, **k: built_runs.append(select))
        monkeypatch.setattr(run_dbt, "_check_ids", lambda path: {
            (f"stg_{FAKE_TABLE}", "things", "not_null"): "fake.not_null_dbt"})
        monkeypatch.setattr(run_dbt, "failing_sample_keys_direct", lambda *a: [])
        monkeypatch.setattr(run_dbt.left_out, "note", lambda run_id, tool, ids: notes.extend(ids))
        monkeypatch.setattr(run_dbt, "write_qa_result", lambda *a, **k: None)
        got = run_dbt.evaluate(FAKE_ID, "fake_things__1", "2026-01-01T00:00:00Z")
        return got, built_runs, queries, notes

    def test_dbt_builds_only_this_collections_models_and_reads_the_adapter(
            self, third_collection, monkeypatch, tmp_path):
        got, built_runs, _, _ = self._dbt(monkeypatch, tmp_path)
        assert built_runs == [[f"stg_{FAKE_TABLE}"]]
        [r] = got  # the other collection's test is left alone
        assert (r["collection_id"], r["dataset_id"], r["dimension"], r["label"]) == \
            (FAKE_ID, FAKE_DATASET, "completeness", "Null rate")
        assert (r["metric_value"], r["status"], r["row_count_total"]) == (4, "fail", 4)

    def test_dbt_never_recounts_a_skipped_test(self, third_collection, monkeypatch, tmp_path):
        _, _, queries, _ = self._dbt(monkeypatch, tmp_path, status="skipped")
        assert queries, "the stub recorded no queries - the test would prove nothing"
        assert not any('"audit"' in q for q in queries)

    def test_dbt_counts_nothing_over_a_model_it_did_not_build(self, third_collection,
                                                                monkeypatch, tmp_path):
        [r], _, _, _ = self._dbt(monkeypatch, tmp_path, built=False)
        assert r["row_count_total"] is None

    def test_dbt_notes_a_test_left_out_for_an_unreadable_model(self, third_collection,
                                                                 monkeypatch, tmp_path):
        """A test excluded for an unreadable model never runs, so it is absent
        from run_results - and is noted as left out."""
        _, _, _, notes = self._dbt(monkeypatch, tmp_path, unreadable={FAKE_TABLE},
                                   asked=["fake.not_null_dbt"], ran=False)
        assert notes == ["fake.not_null_dbt"]

    def test_an_unknown_legacy_flag_fails_the_gate_naming_it(self, third_collection, tmp_path):
        import dataclasses

        adapter = sys.modules["qa_tools.collections.fake_collection"]
        adapter.ADAPTER = dataclasses.replace(adapter.ADAPTER, legacy=frozenset({"no.such.flag"}))
        got = gate.config_problems(_package(tmp_path, *TestTheConfigurationGate.REAL,
                                            "fake_collection"))
        assert got == ["qa_tools/collections/fake_collection.py declares legacy flag "
                       "'no.such.flag', which no shared module knows (qa_tools/tools/legacy.py)"]


class TestTheSharedStagingModule:
    """Criterion 9 for staging, for real: a third collection's file staged
    through qa_tools/tools/stage.py into this worker's own database, its
    table, dataset and run prefix all from the registry."""

    RECEIVED = "2026-01-01T01:00:00+00:00"

    def _stage(self, tmp_path, monkeypatch, legacy=frozenset()):
        import dataclasses

        from qa_tools.common import supply_db
        from qa_tools.tools import stage

        adapter = sys.modules["qa_tools.collections.fake_collection"]
        adapter.ADAPTER = dataclasses.replace(adapter.ADAPTER, legacy=legacy)
        contract = tmp_path / "fake-contract.yaml"
        contract.write_text(yaml.safe_dump({"schema": [{"name": FAKE_TABLE, "properties": [
            {"name": "fake_id"}, {"name": "things"}]}]}))
        csv = tmp_path / "fake_things.csv"
        csv.write_text("fake_id,things\nF1,2\nF2,3\n")
        run_id = f"{FAKE_PREFIX}001"
        physical = stage.stage_table(FAKE_ID, run_id, FAKE_TABLE, str(csv),
                                     contract_path=str(contract), received_at=self.RECEIVED,
                                     run_date="2026-01-01")
        with supply_db.connect(read_only=True, label="test-third-stage") as conn:
            cols = [r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
                [supply_db.STAGING_SCHEMA, physical]).fetchall()]
            viewed = conn.execute(
                f'SELECT count(*) FROM "{supply_db.run_schema(run_id)}"."{FAKE_TABLE}"').fetchone()[0]
        return physical, cols, viewed

    def test_a_third_collections_file_is_staged_and_readable(
            self, third_collection, supply_dsn, tmp_path, monkeypatch):
        from qa_tools.common import load_log

        physical, cols, viewed = self._stage(tmp_path, monkeypatch)
        assert physical.startswith(FAKE_TABLE) and viewed == 2
        assert cols == ["fake_id", "things"]
        [record] = [r for r in load_log.records() if r.physical == physical]
        assert record.dataset_id == FAKE_DATASET

    @pytest.mark.parametrize("legacy,stamped", [
        (frozenset(), False),
        (frozenset({"stage.stamps_run_columns"}), True),
    ])
    def test_stamps_run_columns_keeps_birth_registrations_behaviour(
            self, third_collection, supply_dsn, tmp_path, monkeypatch, legacy, stamped):
        """The flag's whole effect, on the one thing it changes: the staged
        table's columns."""
        _, cols, _ = self._stage(tmp_path, monkeypatch, legacy)
        assert ("run_id" in cols and "run_date" in cols) is stamped
        assert cols[:2] == ["fake_id", "things"]


class TestTheSharedOrchestratorStatsAndRebuild:
    """REQ-PIPE-243 criterion 8's third-collection tests for the three
    modules it shares: the dataset statistics, the results rebuild and the
    orchestrator's claim window, each driven for the fake collection with
    nothing of its own but an adapter."""

    def test_dataset_stats_count_a_third_collections_tables_from_the_registry(
            self, third_collection):
        import duckdb

        from qa_tools.tools import dataset_stats

        conn = duckdb.connect(":memory:")
        conn.execute(f"CREATE TABLE {FAKE_TABLE} (fake_id VARCHAR, extract_timestamp TIMESTAMP)")
        conn.execute(f"INSERT INTO {FAKE_TABLE} VALUES ('F1', '2026-01-01 09:00:00'), "
                     "('F2', '2026-01-01 08:00:00')")
        entry = {"run_id": f"{FAKE_PREFIX}001", "run_index": 1, "delivery": "fk-1",
                 "received_at": "2026-01-01T01:00:00+00:00", "seed": 7}

        stats = dataset_stats.compute_dataset_stats(FAKE_ID, conn, entry)

        # The shared shape, not Birth Registrations' single-table one; the
        # generator's seed does not survive into the record.
        assert stats["row_counts"] == {FAKE_TABLE: 2}
        assert stats["arrival"][FAKE_TABLE]["earliest_extract"].startswith("2026-01-01T08:00:00")
        assert stats["arrival_record"] == {k: entry[k] for k in
                                           ("run_id", "run_index", "received_at", "delivery")}
        assert stats["value_counts"] == {} and stats["check_aggregates"] == {}

    def test_the_rebuild_writes_a_third_collections_results_file(
            self, third_collection, clean_qa_history, tmp_path, monkeypatch):
        import rebuild_support

        rebuild_support.record_run(FAKE_ID, f"{FAKE_PREFIX}001", 1, {
            "dbt": [rebuild_support.check(FAKE_ID, "row_count", "dbt", dataset=FAKE_DATASET)]})

        output = rebuild_support.rebuild(FAKE_ID, tmp_path, monkeypatch)

        assert output["collection"] == f"fake-agency.{FAKE_ID}"
        assert output["datasets"] == [FAKE_DATASET]
        assert [r["run_id"] for r in output["runs"]] == [f"{FAKE_PREFIX}001"]
        assert len(output["results"]) == 1
        written = rebuild_support.output_path(FAKE_ID, tmp_path)
        assert written.name == "results_fk.json" and written.is_file()

    def test_a_third_collection_claims_under_no_borrowed_window(self, third_collection):
        """Criterion 2: an adapter that names no claim-window dataset and an
        arrival that names no files gets NO window - never cp-clients'."""
        from qa_tools.tools import orchestrate

        arrival = SimpleNamespace(received_at="2026-01-01T01:00:00+00:00", files_by_dataset={})
        assert orchestrate._claim_window(FAKE_ID, arrival) is None
        assert orchestrate._claim_window("child-protection", arrival) is not None


class TestTheAdapterLineReport:
    """REQ-TEST-249 criterion 5: each adapter's lines of logic against a soft
    budget, each provider's beside it, reported and never enforced."""

    def test_every_collection_is_reported_with_its_provider(self):
        from qa_tools.common import validate_collections as vc

        lines = vc.line_report()
        assert len(lines) == len(collections.all_collections()) > 0
        assert all("against a budget of 150" in line and "generator provider" in line
                   for line in lines), lines

    def test_an_adapter_over_budget_is_reported_and_the_gate_still_passes(self, tmp_path, capsys):
        from qa_tools.common import validate_collections as vc

        for coll in collections.all_collections():
            path = tmp_path / "qa_tools" / "collections" / f"{coll.module_name}.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('"""A docstring is not logic."""\n# nor is a comment\n\n'
                            + "".join(f"x{i} = {i}\n" for i in range(160)))
        lines = vc.line_report(tmp_path)
        assert all("adapter 160 lines" in line and "10 over" in line
                   and "no generator provider" in line for line in lines), lines
        assert vc.main() == 0
        assert "against a budget of 150" in capsys.readouterr().out
