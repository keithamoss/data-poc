"""What a check read besides its own table (REQ-PIPE-036 criteria 10
and 11).

The failure this defends against is not a wrong table name. It is a
red referential-integrity check, read a year later, that says which
version of ITS OWN table it ran against and nothing about the parent it
was red against - so the one fact needed to diagnose it is the one fact
missing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import dbsupport

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


class TestItReachesTheRecordedResult:
    """The end-to-end path, because everything above tests a function and
    the requirement is about what is RECORDED. It asserted on a committed
    JSON file until REQ-PIPE-089 made the results rows."""

    def test_a_cross_table_checks_recorded_result_carries_what_it_read(
            self, monkeypatch, finish_runs):
        # EMPTY FIRST, then record - the order matters and getting it
        # wrong is invisible: resetting after the resolution was written
        # simply deleted it, and the test then failed reporting a missing
        # table rather than a missing setup step.
        dbsupport.use_empty_supply_db(monkeypatch)
        conn = supply_db.connect()
        try:
            supply_db.ensure_schemas(conn)
            supply_db.record_resolution(conn, supply_db.Resolution(
                run_id="cp_run_001", schema=supply_db.run_schema("cp_run_001"),
                resolved={"cp_placements": "cp_placements__20260801010000",
                           "cp_carers": "cp_carers__20260801010000"}))
        finally:
            conn.close()

        # A REAL check_id from this repo's own sources, so this cannot
        # pass against a declaration that no longer exists.
        from qa_tools.common.validate_check_lifecycle import collect_checks
        declaring = [c for c in collect_checks(None)
                      if c.reads_tables == ["cp_carers"] and c.tool == "dbt"]
        assert declaring, "no real check declares it reads cp_carers"
        check_id = declaring[0].check_id

        qa_results_writer._declared_reads_tables.cache_clear()
        qa_results_writer.write_qa_result(
            "child-protection-family-support", "child-protection", "cp_run_001",
            "2026-09-25T22:00:00+08:00", "dbt", {"raw": True},
            verified=[_result(check_id)])
        finish_runs("cp_run_001", agency="child-protection-family-support",
                    collection="child-protection", when="2026-09-25T22:00:00+08:00")

        # THE RECORD FOLLOWED THE CHECK. REQ-QAC-037 moved cross-table
        # results out of the dataset's own results and into the reserved
        # scope, so this asserts where the check actually is rather than
        # where it used to be - and asserts it LEFT, which is that
        # requirement's criterion 2.
        assert qa_results_reader.read_one("child-protection-family-support", "child-protection",
                                "cp_run_001", "dbt", dataset="cp-placements") == [], \
            "the record did not leave"
        cross = qa_results_reader.read_cross_table_results("child-protection-family-support",
                                                 "child-protection")
        assert len(cross) == 1
        assert cross[0][tr.RESULT_FIELD] == {"cp_carers": "cp_carers__20260801010000"}

    def test_a_run_with_no_recorded_resolution_records_no_tables_read(
            self, monkeypatch, finish_runs):
        """Quiet on purpose, and safe to be: the run-level tables_read
        record carries the same resolution for the whole run, so an
        absence here is visible against something always recorded."""
        # An EMPTY database on this worker's PostgreSQL, which is what a
        # fresh file used to give (REQ-TEST-095).
        dbsupport.use_empty_supply_db(monkeypatch)
        qa_results_writer._declared_reads_tables.cache_clear()

        qa_results_writer.write_qa_result(
            "a", "b", "run_1", "2026-09-25T22:00:00+08:00", "dbt", {},
            verified=[_result("anything")])
        finish_runs("run_1", agency="a", collection="b",
                    when="2026-09-25T22:00:00+08:00")

        recorded = qa_results_reader.read_one("a", "b", "run_1", "dbt", dataset="cp-placements")
        assert recorded, "nothing was recorded at all"
        assert not recorded[0].get(tr.RESULT_FIELD)


class TestAPartialRunIsNotRecordedAsACompleteOne:
    """Criterion 12. Deriving completeness from every expected file
    being present means there is no third state to get wrong: a run is
    complete because everything it owes is there, not because something
    said so."""

    def _run(self, conn, run_id, tools, datasets=()):
        """One run's recorded output, which is what REQ-PIPE-089 made of
        the `_raw` scope: a `tool_output` row per invocation, and a
        `dataset_stats`/`tables_read` row for each pseudo-tool.
        """
        from qa_tools.common import qa_store

        qa_store.record_run(conn, run_key=run_id, agency_id="a", collection_id="b",
                            run_timestamp="2026-01-01T00:00:00+00:00",
                            run_by="t@e.gov.au", environment="sandbox")
        for tool in tools:
            if tool == "dataset_stats":
                qa_store.record_dataset_stats(conn, run_id, "", {})
            elif tool == "tables_read":
                qa_store.record_tables_read(conn, run_id, {"t": "t__1"})
            else:
                qa_store.record_tool_output(conn, run_id, tool, {})
        for dataset in datasets:
            qa_store.record_results(
                conn, run_id,
                [{"dataset_id": dataset, "check_id": "x", "status": "pass"}],
                tool="soda", agency_id="a", collection_id="b")

    def test_a_run_missing_a_tool_says_which(self, clean_qa_history):
        """`missing_tools` SURVIVES as the per-tool diagnostic. What it
        no longer decides is whether the run is complete - see the
        retirement note below."""
        self._run(clean_qa_history, "run_1", ["dbt", "soda"])
        assert qa_results_reader.missing_tools("a", "b", "run_1") == [
            "_raw/datacontract", "_raw/evidently", "_raw/dataset_stats", "_raw/tables_read"]

    def test_completeness_is_recorded_rather_than_counted(
            self, clean_qa_history, finish_runs):
        """RETIRED AND REPLACED (REQ-PIPE-089 criterion 13).

        Two tests here asserted that a run with every expected FILE was
        complete, and that a run missing one was not. That derivation
        was always a proxy, and its own docstring above says why it was
        chosen - "there is no third state to get wrong". The trouble is
        that it gets the SECOND state wrong: a run that died after
        writing its last file has every file and is not finished, and a
        run whose last tool legitimately produced nothing is finished
        and looks broken.

        There is one place that flips now, and this is it.
        """
        self._run(clean_qa_history, "run_1", qa_results_reader.EXPECTED_TOOLS)
        assert not qa_results_reader.run_is_complete("a", "b", "run_1"), \
            "every expected tool recorded output, and the run never said it finished"

        finish_runs("run_1")
        assert qa_results_reader.run_is_complete("a", "b", "run_1")

    def test_incomplete_runs_names_every_partial_run(
            self, clean_qa_history, finish_runs):
        self._run(clean_qa_history, "run_1", qa_results_reader.EXPECTED_TOOLS)
        self._run(clean_qa_history, "run_2", ["dbt"])
        finish_runs("run_1")

        found = qa_results_reader.incomplete_runs("a", "b")
        assert list(found) == ["run_2"]

    def test_a_dataset_owing_a_tool_it_never_wrote_is_named_too(self, clean_qa_history):
        """The other half of the diagnostic: `_raw` catches a run that
        died between tools, and the per-dataset records catch a tool
        that ran and recorded nothing."""
        self._run(clean_qa_history, "run_1", qa_results_reader.EXPECTED_TOOLS,
                  datasets=["cp-carers"])

        missing = qa_results_reader.missing_tools("a", "b", "run_1")

        assert "cp-carers/dbt" in missing
        # WHICH TOOLS cp-carers OWES IS DERIVED, not fixed - it gained
        # Evidently on 2026-09-29 when REQ-QAC-108 gave every Child
        # Protection dataset a relative volume check. This used to name
        # Evidently as the tool it did not owe, which made the test read
        # as being about that pair rather than about the rule.
        owed = qa_results_reader.expected_tools_for("cp-carers")
        for tool in qa_results_reader.EXPECTED_TOOLS:
            if tool in owed:
                continue
            assert f"cp-carers/{tool}" not in missing, (
                f"no {tool} check is defined against cp-carers, so it owes no record")


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


class TestTheBusinessRuleShapes:
    """The two shapes the gate's first version could not see
    (2026-09-26).

    It knew a dbt `relationships` test and a SodaCL "must exist in"
    sentence, both of which announce a join in their check TYPE. A
    business rule does not: it is an ordinary singular test or an
    ordinary `failed rows`, and the join is in its SQL. Six real checks
    were joining a second table under a gate that called the repo
    clean, and they were found by eye - one business rule appearing
    twice on a dataset page, once in the table section and once in the
    cross-table one, because only its datacontract third had declared.
    """

    def _dbt_project(self, tmp_path, sql: str, declare: bool):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "joins_two.sql").write_text(sql)
        staging = tmp_path / "models" / "staging"
        staging.mkdir(parents=True)
        declaration = "        reads_tables: [cp_clients]\n" if declare else ""
        (staging / "schema.yml").write_text(
            "version: 2\n"
            "tests:\n"
            "  - name: joins_two\n"
            "    config:\n"
            "      meta:\n"
            "        check_id: a.b.c.d.e.joins_two_dbt\n"
            f"{declaration}"
            "        category: consistency\n")
        return staging / "schema.yml"

    def test_a_dbt_singular_test_joining_two_models_must_declare(self, tmp_path):
        schema = self._dbt_project(
            tmp_path,
            "select * from {{ ref('stg_cp_investigations') }} i\n"
            "join {{ ref('stg_cp_clients') }} c on i.cp_client_id = c.cp_client_id\n",
            declare=False)

        problems = tr.undeclared_cross_table(dbt_schema=schema)

        assert len(problems) == 1
        assert "joins_two_dbt" in problems[0]
        assert "cp_clients" in problems[0] and "cp_investigations" in problems[0]

    def test_declaring_it_satisfies_the_gate(self, tmp_path):
        schema = self._dbt_project(
            tmp_path,
            "select * from {{ ref('stg_cp_investigations') }} i\n"
            "join {{ ref('stg_cp_clients') }} c on i.cp_client_id = c.cp_client_id\n",
            declare=True)

        assert tr.undeclared_cross_table(dbt_schema=schema) == []

    def test_a_singular_test_over_one_model_is_left_alone(self, tmp_path):
        """The gate costs an author a declaration for every false
        positive, so a single-table rule must not be one. Two of this
        repo's five singular tests are exactly that."""
        schema = self._dbt_project(
            tmp_path,
            "select * from {{ ref('stg_cp_clients') }} where case_status is null\n",
            declare=False)

        assert tr.undeclared_cross_table(dbt_schema=schema) == []

    def _soda_file(self, tmp_path, declare: bool):
        declaration = "        reads_tables: [cp_carers]\n" if declare else ""
        path = tmp_path / "soda.yml"
        path.write_text(
            "checks for cp_placements:\n"
            "  - failed rows:\n"
            "      name: Carer approval compliance\n"
            "      fail query: |\n"
            "        SELECT p.placement_id\n"
            "        FROM cp_placements p JOIN cp_carers c ON p.carer_id = c.carer_id\n"
            "        WHERE c.approval_status <> 'Approved'\n"
            "      attributes:\n"
            "        check_id: a.b.c.d.e.approval_compliance_soda\n"
            f"{declaration}"
            "        category: consistency\n")
        return path

    def test_a_soda_fail_query_naming_another_table_must_declare(self, tmp_path):
        problems = tr.undeclared_cross_table(
            soda_checks=[self._soda_file(tmp_path, declare=False)])

        assert len(problems) == 1
        assert "approval_compliance_soda" in problems[0]
        assert "cp_carers" in problems[0]

    def test_a_soda_fail_query_naming_only_its_own_table_is_left_alone(self, tmp_path):
        """`cp_placements` appears in this query too - it is the FROM.
        A scan that flagged its own table would flag every business
        rule in the repo."""
        path = tmp_path / "soda.yml"
        path.write_text(
            "checks for cp_placements:\n"
            "  - failed rows:\n"
            "      fail query: SELECT placement_id FROM cp_placements WHERE end_date < start_date\n"
            "      attributes:\n"
            "        check_id: a.b.c.d.e.dates_soda\n")

        assert tr.undeclared_cross_table(soda_checks=[path]) == []

    def test_declaring_the_soda_rule_satisfies_the_gate(self, tmp_path):
        assert tr.undeclared_cross_table(
            soda_checks=[self._soda_file(tmp_path, declare=True)]) == []

    def test_the_six_real_business_rules_declare_what_they_join(self):
        """Named individually rather than counted, because the point is
        that each pair's three tools now agree - which is what stopped
        one rule rendering in two sections at once."""
        from qa_tools.common.validate_check_lifecycle import collect_checks

        declared = {c.check_id.split(".")[-1]: c.reads_tables
                     for c in collect_checks(None) if c.reads_tables}
        for suffix, table in [
            ("escalation_completeness_dbt", "cp_investigations"),
            ("escalation_completeness_soda", "cp_investigations"),
            ("closed_case_investigation_hygiene_dbt", "cp_clients"),
            ("closed_case_hygiene_soda", "cp_clients"),
            ("placement_carer_approval_dbt", "cp_carers"),
            ("approval_compliance_soda", "cp_carers"),
        ]:
            assert declared.get(suffix) == [table], suffix


class TestTheReservedNameIsGuardedBeforeItReachesGit:
    """Keith's own ask, 2026-09-26: tests that the reserved name is not
    used, AND a guard against it ever being used. The first half is
    TestTheReservedScope above; this is the second."""

    def test_a_pre_commit_hook_runs_the_hierarchy_gate(self):
        import yaml

        config = yaml.safe_load(Path(".pre-commit-config.yaml").read_text())
        hooks = [h for repo in config["repos"] for h in repo.get("hooks", [])]
        hook = next((h for h in hooks if h["id"] == "mothman-check-hierarchy"), None)

        assert hook is not None, "the reserved name has no pre-commit guard"
        assert "hierarchy" in hook["entry"]

    def test_the_hook_watches_the_files_that_define_the_tree(self):
        """A hook scoped to the wrong paths never runs. The hierarchy
        is defined in contract/, so that is what has to trigger it."""
        import re as _re
        import yaml

        config = yaml.safe_load(Path(".pre-commit-config.yaml").read_text())
        hook = next(h for repo in config["repos"] for h in repo.get("hooks", [])
                     if h["id"] == "mothman-check-hierarchy")

        assert _re.search(hook["files"], "contract/child-protection-contract.yaml")
