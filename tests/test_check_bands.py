"""The catalogue of every check's warn and fail bands, read from the
committed definitions the four tools run (REQ-GEN-183 criteria 1-7, 13, 14).

A rule is the checks that implement it across tools - grouped by dataset,
column and category (Keith, 2026-10-11) - and its amber band, for a given
row count, is where no implementing check fails and at least one warns,
honouring each tool's own unit and comparison operator.
"""
from __future__ import annotations

import math
import textwrap

import pytest

from qa_tools.common import check_bands as cb

BDM = "birth-registrations"
FACILITY = (BDM, "place_of_birth_facility", "completeness")


@pytest.fixture(scope="module")
def catalogue():
    return cb.catalogue()


class TestTheRealDefinitions:
    def test_facility_nulls_have_a_band_in_every_tool(self, catalogue):
        """Soda warns over 15% and fails over 35%; dbt warns over 300 rows
        and fails over 600; the contract fails at 35% or more. At 2,000 rows
        that is amber from 301 to 600 unrecognised... missing values."""
        rule = catalogue.rule(*FACILITY)
        assert {c.tool for c in rule.checks} == {"soda", "dbt", "datacontract"}
        assert rule.amber(2000) == [(301, 600)]

    def test_sex_invalid_values_have_no_amber_band_and_name_what_closes_it(self, catalogue):
        rule = catalogue.rule(BDM, "sex", "conformity")
        assert rule.amber(2000) == []
        assert any(c.endswith("sex.invalidValues_datacontract") for c in rule.closed_by(2000))

    def test_client_postcodes_are_amber_from_one_to_fifteen_in_527(self, catalogue):
        """REQ-QAC-187's own arithmetic, now read off the definitions."""
        assert catalogue.rule("cp-clients", "postcode", "conformity").amber(527) == [(1, 15)]

    def test_a_sql_check_is_single_tier(self, catalogue):
        [c] = [c for c in catalogue.checks
               if c.check_id.endswith("is_multiple_birth.sibling_match_soda")]
        assert c.single_tier and c.reads_columns

    def test_a_dbt_test_with_no_warn_if_is_single_tier(self, catalogue):
        [c] = [c for c in catalogue.checks
               if c.check_id.endswith("registration_number.unique_dbt")]
        assert c.single_tier

    def test_a_warning_only_contract_rule_never_fails(self, catalogue):
        [c] = [c for c in catalogue.checks if c.tool == "datacontract"
               and c.dataset_id == "cp-clients" and c.metric == "rowCount"]
        assert c.fail == () and c.warn and not c.single_tier

    def test_evidently_is_read_from_its_own_entry(self, catalogue):
        """Since REQ-QAC-223 each Evidently check's bands live in its own
        entry in its collection's check file, where the changelog gate sees
        them."""
        from qa_tools.common.evidently_common import collection_checks

        [psi] = [c for c in catalogue.checks if c.check_id.endswith("sex.drift_psi_evidently")]
        entry = collection_checks("civil-registration").checks[psi.check_id]
        assert [b.value for b in psi.warn] == [entry["warn_threshold"]]
        assert [b.value for b in psi.fail] == [entry["fail_threshold"]]

    def test_every_dataset_is_catalogued(self, catalogue):
        from qa_tools.common import hierarchy

        expected = {d.dataset_id for c in ("civil-registration", "child-protection")
                    for d in hierarchy.datasets_in_collection(c)}
        assert {c.dataset_id for c in catalogue.checks} >= expected

    def test_it_never_opens_a_database(self, monkeypatch):
        """Criterion 13: configuration only."""
        from qa_tools.common import supply_db

        def refuse(*_a, **_k):
            raise AssertionError("the catalogue opened a database")
        monkeypatch.setattr(supply_db, "connect", refuse)
        assert cb.catalogue().checks


class TestUnparseable:
    def test_an_unknown_threshold_shape_fails_naming_the_check_and_file(self, tmp_path):
        """Criterion 4: never a guessed bound."""
        path = tmp_path / "soda.yml"
        path.write_text(textwrap.dedent("""
            checks for birth_registrations:
              - missing_count(sex):
                  warn: when somewhat high
                  attributes:
                    check_id: data-asset-1.registry-services.civil-registration.birth-registrations.sex.x_soda
                    category: completeness
            """))
        with pytest.raises(cb.CatalogueError, match=r"sex\.x_soda.*soda\.yml|soda\.yml.*sex\.x_soda"):
            cb.soda_bounds(path)


class TestRetired:
    def test_a_retired_check_is_left_out(self, catalogue):
        """Criterion 5."""
        from qa_tools.common import validate_check_lifecycle as vcl

        retired = {c.check_id for c in vcl.collect_checks(None) if c.retired_as_of}
        assert retired, "the fixture of a retired check exists"
        assert not retired & {c.check_id for c in catalogue.checks}


class TestTheCommand:
    def test_it_lists_rules_bands_and_single_tier_readers(self):
        from click.testing import CliRunner

        from cli import scenarios

        got = CliRunner().invoke(scenarios.scenarios_group,
                                 ["bands", "--dataset", BDM, "--rows", "2000"])
        assert got.exit_code == 0, got.output
        text = " ".join(got.output.split())
        assert "place_of_birth_facility" in text and "301" in text and "600" in text
        assert "no amber band" in text
        assert "sibling_match" in text   # a single-tier check reading facility


# ---- post-build-review #153: the critic's findings, each failing first ----

class TestGroupingByName:
    """Keith, 2026-10-11: checks sharing an authored name are one rule across
    tools; otherwise dataset, column, category and measure."""

    def test_escalation_completeness_is_its_own_rule_in_three_tools(self, catalogue):
        rule = catalogue.named("cp-notifications", "Escalation completeness")
        assert {c.tool for c in rule.checks} == {"dbt", "soda", "datacontract"}

    def test_notification_id_nulls_no_longer_carry_the_escalation_checks(self, catalogue):
        rule = catalogue.rule("cp-notifications", "notification_id", "completeness")
        assert not [c for c in rule.checks if "escalation" in c.check_id]

    def test_a_rule_split_across_columns_comes_together(self, catalogue):
        rule = catalogue.named(BDM, "Registered on or after birth")
        assert {c.tool for c in rule.checks} == {"dbt", "soda", "datacontract"}

    def test_carer_reference_and_approval_compliance_are_two_rules(self, catalogue):
        ref = catalogue.named("cp-placements", "Carer reference")
        assert not [c for c in ref.checks if "approval" in c.check_id]

    def test_a_column_order_problem_alone_reads_amber(self, catalogue):
        assert catalogue.named(BDM, "Column order").amber(2000)
        assert not catalogue.named(BDM, "Text encoding").amber(2000)


class TestEachToolsOwnArithmetic:
    def test_soda_rounds_a_percentage_to_two_places(self):
        """Finding 4: 51/1019 = 5.0049%, which Soda reads as 5.00 - not > 5%."""
        c = cb.Check("x_soda", "soda", BDM, "c", "completeness", "missing_percent", "f",
                     warn=(cb.Bound(">", 5, cb.PERCENT),))
        assert not c.warns(51, 1019) and c.warns(52, 1019)

    def test_a_dbt_test_with_only_error_if_warns_below_it(self):
        """Finding 5: dbt defaults warn_if to != 0."""
        _cid, (_m, warn, fail) = cb._dbt_one(
            "not_null", {"config": {"error_if": ">5"}}, {"check_id": "x_dbt"}, "schema.yml")
        c = cb.Check("x_dbt", "dbt", BDM, "c", "completeness", "not_null", "f",
                     warn=warn, fail=fail)
        assert c.warns(3, 100) and not c.fails(3, 100) and not c.single_tier

    def test_a_dbt_test_with_neither_is_single_tier(self):
        _cid, (_m, warn, fail) = cb._dbt_one("not_null", {}, {"check_id": "x_dbt"}, "s.yml")
        c = cb.Check("x_dbt", "dbt", BDM, "c", "completeness", "not_null", "f",
                     warn=warn, fail=fail)
        assert c.single_tier

    def test_dbt_counting_rows_in_duplicated_groups_is_not_soda_counting_keys(self, catalogue):
        """Finding 3: never one axis."""
        for rule in catalogue.rules():
            tools_units = {(c.tool, c.unit) for c in rule.checks}
            if any(u == cb.DUP_ROWS for _t, u in tools_units):
                assert all(u == cb.DUP_ROWS for _t, u in tools_units), rule

    def test_a_size_band_nothing_fails_above_is_open_ended(self, catalogue):
        """Finding 6: never an invented upper edge."""
        [rule] = [r for r in catalogue.rules() if r.dataset_id == "cp-investigations"
                  and r.measure == cb.TABLE_ROWS]
        assert rule.amber(500)[-1][1] == math.inf


class TestReaders:
    def test_soda_reference_checks_read_the_parent_column(self, catalogue):
        """Finding 8."""
        readers = catalogue.single_tier_readers("cp-clients")["cp_client_id"]
        assert any(r.endswith("cp_client_id.relationships_soda") for r in readers)


class TestNoSilentDefaults:
    """Finding 11: fail loudly, never default."""

    def test_an_evidently_check_of_unknown_kind(self):
        with pytest.raises(cb.CatalogueError, match="x.y.z_evidently"):
            cb.evidently_bounds(["x.y.z_evidently"])

    def test_a_file_check_file_checks_yaml_does_not_name(self):
        class M:
            tool, check_id = "file", "a.b.c.birth-registrations.mystery_file"
        with pytest.raises(cb.CatalogueError, match="mystery"):
            cb.file_bounds([M()], {"checks": [{"check": "encoding", "severity": "failure"}]})

    def test_a_file_check_severity_it_does_not_know(self):
        class M:
            tool, check_id = "file", "a.b.c.birth-registrations.encoding_file"
        with pytest.raises(cb.CatalogueError, match="encoding"):
            cb.file_bounds([M()], {"checks": [{"check": "encoding", "severity": "info"}]})

    def test_a_contract_severity_it_does_not_know(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text(textwrap.dedent("""
            schema:
              - name: t
                properties:
                  - name: sex
                    quality:
                      - metric: nullValues
                        mustBe: 0
                        severity: info
                        customProperties:
                          - {property: check_id, value: a.b.c.d.sex.n_datacontract}
            """))
        with pytest.raises(cb.CatalogueError, match="n_datacontract.*info"):
            cb.contract_bounds(path)

    def test_default_rows_reads_the_contract(self, catalogue):
        assert cb.default_rows("cp-clients", catalogue) > 0

    def test_default_rows_with_nothing_to_read_refuses(self):
        with pytest.raises(cb.CatalogueError, match="--rows"):
            cb.default_rows("cp-clients", cb.Catalogue([]))


class TestTheListing:
    def _out(self, *args):
        from click.testing import CliRunner

        from cli import scenarios
        got = CliRunner().invoke(scenarios.scenarios_group, ["bands", *args],
                                 env={"COLUMNS": "80"})
        assert got.exit_code == 0, got.output
        return got.output

    def test_a_tolerant_single_tier_check_prints_its_bound(self):
        """Finding 2: the contract fails at 3% or more, not on any."""
        out = self._out("--dataset", "cp-clients", "--rows", "527")
        line = next(ln for ln in out.splitlines() if "datacontract" in ln and ">= 3%" in ln)
        assert "fails on any" not in line

    def test_every_line_fits_eighty_columns_and_continues_indented(self):
        """Finding 9."""
        lines = self._out("--dataset", "cp-notifications", "--rows", "1000").splitlines()
        assert all(len(ln) <= 80 for ln in lines), [ln for ln in lines if len(ln) > 80]
        body = [ln for ln in lines if ln.strip()][1:]
        assert all(ln.startswith("  ") for ln in body)

    def test_a_reader_from_another_dataset_is_named_with_it(self):
        out = " ".join(self._out("--dataset", "cp-clients", "--rows", "527").split())
        assert "cp-notifications.cp_client_id.relationships_dbt" in out

    def test_a_file_rule_says_which_one(self):
        out = self._out("--dataset", BDM, "--rows", "2000")
        assert "Column order" in out and "Text encoding" in out

    def test_with_no_rows_and_nothing_to_read_it_asks_for_them(self, monkeypatch):
        from click.testing import CliRunner

        from cli import scenarios

        def refuse(ds, cat):
            raise cb.CatalogueError(f"{ds}: no ordinary size; pass --rows")
        monkeypatch.setattr(cb, "default_rows", refuse)
        got = CliRunner().invoke(scenarios.scenarios_group, ["bands", "--dataset", BDM])
        assert got.exit_code != 0 and "--rows" in got.output
