"""Every SQL-bodied check declares the columns it reads (REQ-GEN-183
criteria 8-12; Keith, 2026-10-11).

A check whose rule lives in SQL - a Soda failed-rows check, a dbt singular,
relationships or dbt_utils.expression_is_true test, an ODCS rule of type sql
- names every column that SQL reads as `reads_columns`, a flat list of
contract table.column entries, beside `reads_tables`. The check-definition
gate refuses one without it, or one naming a column the contract does not
define, and the list is never part of a check's config hash.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from qa_tools.common import check_lifecycle as cl
from qa_tools.common import validate_check_lifecycle as vcl

DEFINED = {"birth_registrations": {"date_of_birth", "place_of_birth_facility",
                                   "registering_parent_1_name", "sex"}}


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return path


def _soda(tmp_path, attrs: str = "", expr: str = "failed rows") -> list[cl.CheckMetadata]:
    return cl.parse_soda_check_metadata(_write(tmp_path, "soda.yml", f"""
        checks for birth_registrations:
          - {expr}:
              fail query: SELECT * FROM birth_registrations WHERE sex IS NULL
              attributes:
                check_id: a.b.c.d.sex.x_soda
                category: consistency
        {attrs}
        """))


class TestWhichChecksAreSqlBodied:
    def test_a_soda_failed_rows_check_is(self, tmp_path):
        [c] = _soda(tmp_path)
        assert c.sql_bodied

    def test_a_soda_metric_check_is_not(self, tmp_path):
        [c] = cl.parse_soda_check_metadata(_write(tmp_path, "soda.yml", """
            checks for birth_registrations:
              - missing_percent(sex):
                  warn: when > 1%
                  attributes:
                    check_id: a.b.c.d.sex.missing_soda
                    category: completeness
            """))
        assert not c.sql_bodied

    def test_a_soda_reference_check_is_not(self, tmp_path):
        """Keith: its columns are already structured fields."""
        [c] = cl.parse_soda_check_metadata(_write(tmp_path, "soda.yml", """
            checks for cp_notifications:
              - values in (cp_client_id) must exist in cp_clients (cp_client_id):
                  attributes:
                    check_id: a.b.c.d.cp_client_id.relationships_soda
                    category: consistency
            """))
        assert not c.sql_bodied

    def test_dbt_singular_relationships_and_expression_tests_are(self, tmp_path):
        checks = cl.parse_dbt_check_metadata(_write(tmp_path, "schema.yml", """
            version: 2
            tests:
              - name: multiple_birth_sibling
                config:
                  meta: {check_id: a.b.c.d.x.sibling_dbt, category: consistency}
            models:
              - name: stg_birth_registrations
                tests:
                  - dbt_utils.expression_is_true:
                      meta: {check_id: a.b.c.d.x.expr_dbt, category: consistency}
                      expression: "date_registered >= date_of_birth"
                columns:
                  - name: sex
                    tests:
                      - not_null:
                          meta: {check_id: a.b.c.d.sex.not_null_dbt, category: completeness}
                      - relationships:
                          meta: {check_id: a.b.c.d.sex.rel_dbt, category: consistency}
                          to: ref('x')
                          field: sex
            """))
        by_id = {c.check_id: c.sql_bodied for c in checks}
        assert by_id == {"a.b.c.d.x.sibling_dbt": True, "a.b.c.d.x.expr_dbt": True,
                         "a.b.c.d.sex.not_null_dbt": False, "a.b.c.d.sex.rel_dbt": True}

    def test_an_odcs_sql_rule_is_and_a_metric_rule_is_not(self, tmp_path):
        checks = cl.parse_contract_check_metadata(_write(tmp_path, "contract.yaml", """
            schema:
              - name: birth_registrations
                properties:
                  - name: sex
                    quality:
                      - metric: nullValues
                        dimension: completeness
                        mustBe: 0
                        id: a:b:c:d:sex:null_datacontract
                        customProperties:
                          - {property: check_id, value: a.b.c.d.sex.null_datacontract}
                quality:
                  - type: sql
                    dimension: consistency
                    query: SELECT COUNT(*) FROM {model} WHERE sex IS NULL
                    mustBe: 0
                    id: a:b:c:d:x:sql_datacontract
                    customProperties:
                      - {property: check_id, value: a.b.c.d.x.sql_datacontract}
            """))
        assert {c.check_id: c.sql_bodied for c in checks} == {
            "a.b.c.d.sex.null_datacontract": False, "a.b.c.d.x.sql_datacontract": True}


class TestTheGate:
    def test_a_sql_check_with_no_reads_columns_is_refused_naming_it_and_its_file(
            self, tmp_path):
        checks = _soda(tmp_path)
        [error] = cl.reads_columns_errors(checks, DEFINED)
        assert "a.b.c.d.sex.x_soda" in error and "soda.yml" in error

    def test_one_that_declares_them_passes(self, tmp_path):
        checks = cl.parse_soda_check_metadata(_write(tmp_path, "soda.yml", """
            checks for birth_registrations:
              - failed rows:
                  fail query: SELECT * FROM birth_registrations WHERE sex IS NULL
                  attributes:
                    check_id: a.b.c.d.sex.x_soda
                    category: consistency
                    reads_columns: [birth_registrations.sex]
            """))
        assert checks[0].reads_columns == ["birth_registrations.sex"]
        assert cl.reads_columns_errors(checks, DEFINED) == []

    @pytest.mark.parametrize("entry", ["birth_registrations.nope", "stg_birth_registrations.sex",
                                       "sex"])
    def test_an_entry_the_contract_does_not_define_is_refused(self, tmp_path, entry):
        checks = cl.parse_soda_check_metadata(_write(tmp_path, "soda.yml", f"""
            checks for birth_registrations:
              - failed rows:
                  fail query: SELECT 1
                  attributes:
                    check_id: a.b.c.d.sex.x_soda
                    category: consistency
                    reads_columns: ["{entry}"]
            """))
        [error] = cl.reads_columns_errors(checks, DEFINED)
        assert "a.b.c.d.sex.x_soda" in error and entry in error

    def test_a_retired_check_is_not_held_to_it(self, tmp_path):
        checks = cl.parse_soda_check_metadata(_write(tmp_path, "soda.yml", """
            checks for birth_registrations:
              - failed rows:
                  fail query: SELECT 1
                  attributes:
                    check_id: a.b.c.d.sex.x_soda
                    category: consistency
                    retired_as_of: "2026-01-01"
                    retired_reason: gone
            """))
        assert cl.reads_columns_errors(checks, DEFINED) == []

    def test_the_lifecycle_gate_runs_it(self, monkeypatch, tmp_path):
        checks = _soda(tmp_path)
        monkeypatch.setattr(vcl, "collect_checks", lambda ref: checks)
        assert vcl.main() == 1


class TestNeverInTheConfigHash:
    def test_declaring_it_changes_no_hash(self, tmp_path):
        """Criterion 12, in each tool's own parser."""
        before = _soda(tmp_path)[0].config_hash
        after = cl.parse_soda_check_metadata(_write(tmp_path, "soda.yml", """
            checks for birth_registrations:
              - failed rows:
                  fail query: SELECT * FROM birth_registrations WHERE sex IS NULL
                  attributes:
                    check_id: a.b.c.d.sex.x_soda
                    category: consistency
                    reads_columns: [birth_registrations.sex]
            """))[0].config_hash
        assert before == after

    def test_evidently_excludes_it_by_name(self):
        assert "reads_columns" in cl._NON_CONFIG_FIELDS


class TestTheCommittedDefinitions:
    def test_every_sql_bodied_check_in_force_declares_its_columns(self):
        """Criterion 11: the real files pass the gate."""
        checks = vcl.collect_checks(None)
        assert any(c.sql_bodied for c in checks), "the survey found no SQL-bodied check"
        assert cl.reads_columns_errors(checks, cl.contract_columns()) == []


class TestMothmanCheckRunsIt:
    def test_it_is_a_gate(self):
        from cli import check
        assert any(label == "columns" for label, *_ in check._GATES)

    def test_it_fails_on_an_undeclared_check(self, monkeypatch, tmp_path, capsys):
        from qa_tools.common import validate_reads_columns as vrc

        checks = _soda(tmp_path)
        monkeypatch.setattr(vcl, "collect_checks", lambda ref: checks)
        assert vrc.main() == 1
        assert "a.b.c.d.sex.x_soda" in capsys.readouterr().err

    def test_the_committed_tree_passes(self):
        from qa_tools.common import validate_reads_columns as vrc
        assert vrc.main() == 0


class TestAJsonStringValue:
    def test_a_contract_value_given_as_a_json_string_is_read_as_the_list(self, tmp_path):
        """post-build-review #153 finding 10: the recorded decision says it
        survives customProperties' scalar values as a JSON string, the way
        changelog does."""
        [c] = cl.parse_contract_check_metadata(_write(tmp_path, "contract.yaml", """
            schema:
              - name: birth_registrations
                quality:
                  - type: sql
                    dimension: consistency
                    query: SELECT COUNT(*) FROM {model} WHERE sex IS NULL
                    mustBe: 0
                    id: a:b:c:d:x:sql_datacontract
                    customProperties:
                      - {property: check_id, value: a.b.c.d.x.sql_datacontract}
                      - property: reads_columns
                        value: '["birth_registrations.sex"]'
            """))
        assert c.reads_columns == ["birth_registrations.sex"]
        assert cl.reads_columns_errors([c], DEFINED) == []


class TestItIsAMothmanCommand:
    def test_mothman_dashboard_validate_reads_columns(self):
        """Finding 14: every gate has a mothman subcommand."""
        from click.testing import CliRunner

        from cli import dashboard
        got = CliRunner().invoke(dashboard.dashboard_group, ["validate-reads-columns"])
        assert got.exit_code == 0, got.output

    def test_mothman_check_calls_it_through_mothman(self):
        from cli import check
        [cmd] = [c for label, c, *_ in check._GATES if label == "columns"]
        assert "mothman" in " ".join(cmd)
