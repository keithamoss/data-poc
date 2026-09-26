"""What a check read besides its own table (REQ-PIPE-036 criteria 10
and 11).

The failure this defends against is not a wrong table name. It is a
red referential-integrity check, read a year later, that says which
version of ITS OWN table it ran against and nothing about the parent it
was red against - so the one fact needed to diagnose it is the one fact
missing.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from qa_tools.common import qa_results_reader, qa_results_writer, supply_db
from qa_tools.common import tables_read as tr


def _result(check_id, dataset_id="cp-placements", **extra):
    return {"check_id": check_id, "dataset_id": dataset_id, "status": "pass", **extra}


class TestWhatIsRecorded:
    """Criterion 10: the PHYSICAL table name of every table the check
    read other than the one it is filed against."""

    RESOLVED = {"cp_placements": "cp_placements__20260801010000",
                 "cp_carers": "cp_carers__20260801010000"}

    def test_a_cross_table_check_records_the_physical_name_it_read(self):
        out, = tr.attach([_result("carer-ref")], self.RESOLVED,
                          {"carer-ref": ["cp_carers"]})
        assert out[tr.RESULT_FIELD] == {"cp_carers": "cp_carers__20260801010000"}

    def test_a_single_table_check_records_nothing_at_all(self):
        """Criterion 10 asks for a record WHERE a check reads another
        table. A field present and empty on 235 of 259 checks says
        something different from a field that is absent."""
        out, = tr.attach([_result("row-count")], self.RESOLVED, {})
        assert tr.RESULT_FIELD not in out

    def test_its_OWN_table_is_not_recorded_as_another_table_it_read(self):
        out, = tr.attach([_result("carer-ref")], self.RESOLVED,
                          {"carer-ref": ["cp_carers", "cp_placements"]})
        assert set(out[tr.RESULT_FIELD]) == {"cp_carers"}

    def test_a_declared_table_the_run_could_not_resolve_is_recorded_as_None(self):
        """Omitting it would make "read one table" and "read one table
        and could not read another" identical in the record - and the
        second is the interesting one."""
        out, = tr.attach([_result("carer-ref")], {"cp_placements": "p__1"},
                          {"carer-ref": ["cp_carers"]})
        assert out[tr.RESULT_FIELD] == {"cp_carers": None}

    def test_the_original_result_is_not_mutated(self):
        original = _result("carer-ref")
        tr.attach([original], self.RESOLVED, {"carer-ref": ["cp_carers"]})
        assert tr.RESULT_FIELD not in original


class TestNoOtherTablesStatusIsRecorded:
    """Criterion 11, and the temptation is obvious: a reader wanting to
    know whether cp_carers was itself red would be saved a click.

    It is the wrong shape twice over - it freezes another dataset's
    verdict into this check's result where it goes stale the moment
    that dataset is re-checked, and it makes one dataset's results
    depend on another's, which is the per-dataset independence this
    requirement's own story is about.
    """

    def test_only_names_are_recorded_never_a_verdict(self):
        out, = tr.attach([_result("carer-ref")],
                          {"cp_carers": "cp_carers__1", "cp_placements": "p__1"},
                          {"carer-ref": ["cp_carers"]})
        recorded = out[tr.RESULT_FIELD]
        assert list(recorded) == ["cp_carers"]
        assert all(isinstance(v, (str, type(None))) for v in recorded.values())

    def test_attach_is_given_no_way_to_learn_another_tables_status(self):
        """Asserted on the signature rather than on one output, because
        the rule is that the information is not REACHABLE here - a
        function that could look it up would eventually be asked to."""
        import inspect

        params = inspect.signature(tr.attach).parameters
        assert set(params) == {"results", "resolved", "declared"}


class TestTheDeclarationsInThisRepo:
    """The real check sources, not a fixture. These are the checks a
    reader will actually meet."""

    def test_every_mechanical_cross_table_check_declares_what_it_reads(self):
        assert tr.undeclared_in_this_repo() == []

    def test_the_gate_is_not_passing_vacuously(self, tmp_path):
        """A gate over a corpus that cannot fail is a gate that proves
        nothing. This removes one real declaration and asserts it is
        caught."""
        source = Path("dbt_project/models/staging/schema.yml").read_text()
        assert "reads_tables:" in source, "nothing declared - this test would prove nothing"
        stripped = "\n".join(line for line in source.split("\n")
                              if "reads_tables:" not in line)
        path = tmp_path / "schema.yml"
        path.write_text(stripped)

        problems = tr.undeclared_cross_table(dbt_schema=path)

        assert problems, "the gate did not notice seven undeclared relationships tests"
        assert all("declares no reads_tables" in p for p in problems)

    def test_declaring_a_table_does_not_change_any_checks_config_hash(self):
        """Naming what a check already read is not a change to what it
        does - so this must not report 24 checks as changed and demand
        24 changelog entries."""
        from qa_tools.common.validate_check_lifecycle import collect_checks

        checks = collect_checks(None)
        declaring = [c for c in checks if c.reads_tables]
        assert len(declaring) >= 20, "the real declarations have gone"
        # The field is excluded from the hash BY CONSTRUCTION - it is
        # part of _lifecycle_fields, from which _NON_CONFIG_FIELDS is
        # derived - so this asserts the derivation, not a snapshot.
        from qa_tools.common import check_lifecycle as cl
        assert "reads_tables" in cl._NON_CONFIG_FIELDS

    def test_a_bare_string_declaration_is_accepted_and_wrapped(self):
        """The single-table case is the common one, and refusing the
        obvious shortcut would mean a silently undeclared check the
        first time somebody took it."""
        from qa_tools.common import check_lifecycle as cl

        assert cl._table_list({"reads_tables": "cp_clients"}, "reads_tables") == ["cp_clients"]
        assert cl._table_list({}, "reads_tables") == []


class TestItReachesTheCommittedFile:
    """The end-to-end path, because everything above tests a function
    and the requirement is about what is COMMITTED."""

    def test_a_cross_table_checks_committed_result_carries_what_it_read(
            self, tmp_path, monkeypatch):
        db = tmp_path / "supply.duckdb"
        conn = duckdb.connect(str(db))
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{supply_db.STAGING_SCHEMA}"')
        supply_db.record_resolution(conn, supply_db.Resolution(
            run_id="cp_run_001", schema="qa_run_cp_run_001",
            resolved={"cp_placements": "cp_placements__20260801010000",
                       "cp_carers": "cp_carers__20260801010000"}))
        conn.close()
        monkeypatch.setenv(supply_db.SUPPLY_DB_ENV, str(db))

        # A REAL check_id from this repo's own sources, so this cannot
        # pass against a declaration that no longer exists.
        from qa_tools.common.validate_check_lifecycle import collect_checks
        declaring = [c for c in collect_checks(None)
                      if c.reads_tables == ["cp_carers"] and c.tool == "dbt"]
        assert declaring, "no real check declares it reads cp_carers"
        check_id = declaring[0].check_id

        qa_results_writer._declared_reads_tables.cache_clear()
        path = qa_results_writer.write_qa_result(
            "child-protection-family-support", "child-protection", "cp_run_001",
            "2026-09-25T22:00:00+08:00", "dbt", {"raw": True},
            verified=[_result(check_id)], results_dir=tmp_path / "qa_results")

        # THE RECORD FOLLOWED THE CHECK. REQ-QAC-037 moved cross-table
        # results out of the dataset file and into the reserved scope
        # beside it, so this asserts where the check actually is rather
        # than where it used to be - and asserts it LEFT, which is that
        # requirement's criterion 2.
        assert json.loads(Path(path).read_text())["verified"] == []
        cross = (Path(path).parent.parent / tr.CROSS_TABLE_SCOPE
                  / "cp_run_001" / "dbt.json")
        written = json.loads(cross.read_text())
        assert written["verified"][0][tr.RESULT_FIELD] == {
            "cp_carers": "cp_carers__20260801010000"}

    def test_a_run_with_no_recorded_resolution_writes_no_tables_read(
            self, tmp_path, monkeypatch):
        """Quiet on purpose, and safe to be: the run-level
        tables_read.json records the same resolution for the whole run,
        so an absence here is visible against a file that is always
        written."""
        monkeypatch.setenv(supply_db.SUPPLY_DB_ENV, str(tmp_path / "missing.duckdb"))
        qa_results_writer._declared_reads_tables.cache_clear()

        path = qa_results_writer.write_qa_result(
            "a", "b", "run_1", "2026-09-25T22:00:00+08:00", "dbt", {},
            verified=[_result("anything")], results_dir=tmp_path / "qa_results")

        assert tr.RESULT_FIELD not in json.loads(Path(path).read_text())["verified"][0]


class TestAPartialRunIsNotRecordedAsACompleteOne:
    """Criterion 12. Deriving completeness from every expected file
    being present means there is no third state to get wrong: a run is
    complete because everything it owes is there, not because something
    said so."""

    def _run(self, root, run_id, tools):
        d = root / "a" / "b" / run_id
        d.mkdir(parents=True)
        for tool in tools:
            (d / f"{tool}.json").write_text("{}")
        return d

    def test_a_run_missing_a_tool_is_not_complete_and_says_which(self, tmp_path):
        self._run(tmp_path, "run_1", ["dbt", "soda"])
        assert not qa_results_reader.run_is_complete("a", "b", "run_1", tmp_path)
        assert qa_results_reader.missing_tools("a", "b", "run_1", tmp_path) == [
            "datacontract", "evidently", "dataset_stats", "tables_read"]

    def test_a_run_with_every_expected_file_is_complete(self, tmp_path):
        self._run(tmp_path, "run_1", qa_results_reader.EXPECTED_TOOLS)
        assert qa_results_reader.run_is_complete("a", "b", "run_1", tmp_path)

    def test_incomplete_runs_names_every_partial_run(self, tmp_path):
        self._run(tmp_path, "run_1", qa_results_reader.EXPECTED_TOOLS)
        self._run(tmp_path, "run_2", ["dbt"])
        found = qa_results_reader.incomplete_runs("a", "b", tmp_path)
        assert list(found) == ["run_2"]

    def test_every_real_committed_run_is_complete(self, real_committed_history):
        """The corpus this rule was derived from - 60 runs, six files
        each. A regression here means something stopped writing."""
        for agency, dataset in (("registry-services", "civil-registration"),
                                 ("child-protection-family-support", "child-protection")):
            assert qa_results_reader.incomplete_runs(agency, dataset) == {}


class TestTheFailureNamesTheDatasetAndTheTool:
    """Criterion 12's other half: "datacontract-cli exited 1" sends
    somebody to the logs to work out whose run it was."""

    @pytest.mark.parametrize("module", ["qa_tools.bdm.orchestrate_bdm",
                                         "qa_tools.cp.orchestrate_cp"])
    def test_a_tool_failure_is_re_raised_naming_both(self, module):
        import importlib

        mod = importlib.import_module(module)

        def boom():
            raise ValueError("exit code 1")

        with pytest.raises(mod.QaRunFailure) as caught:
            mod._run_step("child-protection", "datacontract-cli", "cp_run_007", boom)

        message = str(caught.value)
        assert "child-protection" in message
        assert "datacontract-cli" in message
        assert "cp_run_007" in message
        assert "INCOMPLETE" in message
        # The original diagnosis is chained, never replaced.
        assert isinstance(caught.value.__cause__, ValueError)

    @pytest.mark.parametrize("module", ["qa_tools.bdm.orchestrate_bdm",
                                         "qa_tools.cp.orchestrate_cp"])
    def test_a_succeeding_step_is_returned_untouched(self, module):
        import importlib

        mod = importlib.import_module(module)
        assert mod._run_step("c", "t", "r", lambda: ["a result"]) == ["a result"]


class TestTheReservedScope:
    """REQ-QAC-037 criterion 1's cross-table scope, and the guard that
    makes reserving a name mean something.

    Keith's own ask, 2026-09-26: "have tests covering the reserved name
    not being used, and also a guard against it ever being used." Both,
    because the two catch different things - the test catches today's
    tree, the gate catches the dataset somebody adds next year.
    """

    def test_no_real_dataset_id_begins_with_the_reserved_prefix(self):
        from qa_tools.common import hierarchy

        taken = [d.dataset_id for d in hierarchy.all_datasets()
                  if tr.is_reserved_scope(d.dataset_id)]
        assert taken == [], (
            f"these dataset ids collide with the reserved scope prefix: {taken}")

    def test_no_real_collection_or_agency_id_does_either(self):
        """The scope sits beside datasets under a collection, so a
        collection or agency taking the prefix would not collide
        today - but it would make the tree unreadable in the same way,
        and the cost of widening the rule is nothing."""
        from qa_tools.common import hierarchy

        ids = {d.collection_id for d in hierarchy.all_datasets()}
        ids |= {d.agency_id for d in hierarchy.all_datasets()}
        assert not [i for i in ids if tr.is_reserved_scope(i)]

    def test_the_scope_name_is_itself_reserved(self):
        """A guard that does not cover the one name it exists for is a
        guard somebody has misread."""
        assert tr.is_reserved_scope(tr.CROSS_TABLE_SCOPE)

    def test_an_ordinary_dataset_id_is_not_reserved(self):
        assert not tr.is_reserved_scope("cp-clients")
        assert not tr.is_reserved_scope("")


class TestTheGateRefusesAReservedDatasetId:
    """The half a test over today's tree cannot cover: the dataset
    somebody adds next year."""

    def test_the_hierarchy_gate_rejects_a_dataset_id_using_the_prefix(self):
        from qa_tools.common import validate_hierarchy

        errors = validate_hierarchy.reserved_name_errors(
            [("registry-services", "civil-registration", "_cross-table")])

        assert errors, "the gate accepted a dataset id using the reserved prefix"
        assert "_cross-table" in errors[0]

    def test_it_accepts_the_real_tree(self):
        from qa_tools.common import hierarchy, validate_hierarchy

        real = [(d.agency_id, d.collection_id, d.dataset_id)
                 for d in hierarchy.all_datasets()]
        assert validate_hierarchy.reserved_name_errors(real) == []

    def test_the_gate_runs_as_part_of_the_real_hierarchy_validation(self):
        """Wired in, not merely written. A validator function nothing
        calls is the shape of guard that passes review and catches
        nothing."""
        import inspect

        from qa_tools.common import validate_hierarchy

        assert "reserved_name_errors" in inspect.getsource(validate_hierarchy.validate)
