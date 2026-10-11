"""The catalogue of every check's warn and fail bands, read from the
committed definitions the four tools run (REQ-GEN-183 criteria 1-7, 13, 14).

A rule is the checks that implement it across tools - grouped by dataset,
column and category (Keith, 2026-10-11) - and its amber band, for a given
row count, is where no implementing check fails and at least one warns,
honouring each tool's own unit and comparison operator.
"""
from __future__ import annotations

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

    def test_evidently_is_read_from_its_own_constants(self, catalogue):
        from qa_tools.common import evidently_common as ec

        [psi] = [c for c in catalogue.checks if c.check_id.endswith("sex.drift_psi_evidently")]
        assert [b.value for b in psi.warn] == [ec.WARN_THRESHOLD]
        assert [b.value for b in psi.fail] == [ec.FAIL_THRESHOLD]

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
