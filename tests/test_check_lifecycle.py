"""Tests for qa_tools/common/check_lifecycle.py - parsing check-lifecycle
metadata from all 4 tools' own definition formats, and the two
validations that gate publishing (plans/publishing-and-history.md
Thread D, Phase 1): globally-unique check_id, and no undocumented
config changes. Fixtures throughout, not the real ~60-100 production
checks - keeps this fast and focused on the parsing/validation logic
itself, same convention as the rest of this project's test suite."""
from __future__ import annotations

import textwrap

import pytest

from qa_tools.common import check_lifecycle as cl


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(textwrap.dedent(content))
    return path


# ---- dbt parsing --------------------------------------------------------

def test_parse_dbt_check_metadata_extracts_check_id_and_lifecycle_fields(tmp_path):
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
            columns:
              - name: registration_number
                tests:
                  - not_null:
                      meta:
                        check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.registration_number.not_null
                        introduced_date: "2026-01-15"
                        description: "Every record must carry a registration number."
                        changelog: []
                      config:
                        warn_if: ">90"
        """)

    checks = cl.parse_dbt_check_metadata(path)

    assert len(checks) == 1
    c = checks[0]
    assert c.check_id == "data-asset-1.bdm.birth_registrations.stg_birth_registrations.registration_number.not_null"
    assert c.tool == "dbt"
    assert c.introduced_date == "2026-01-15"
    assert c.description == "Every record must carry a registration number."
    assert c.changelog == []


def test_parse_dbt_check_metadata_raises_for_tests_without_check_id(tmp_path):
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
            columns:
              - name: registration_number
                tests:
                  - unique
                  - not_null:
                      config:
                        warn_if: ">90"
        """)

    with pytest.raises(cl.MissingCheckIdError) as exc_info:
        cl.parse_dbt_check_metadata(path)

    message = str(exc_info.value)
    assert "unique" in message, "a bare test name has no check_id and must be reported"
    assert "not_null" in message, "a dict test with no meta.check_id must also be reported"


def test_parse_dbt_check_metadata_covers_singular_tests(tmp_path):
    """Regression for a real, pre-existing gap found 2026-09-16: this
    function only ever walked models[].tests/models[].columns[].tests -
    a singular test (tests/*.sql, config'd via a top-level `tests:`
    block, not nested under any model) had no check_id anywhere and was
    silently invisible here, not caught by check_lifecycle.validate()
    at all. Confirmed failing against the pre-fix code (git stash the
    parser change, this assertion goes from 1 to 0) before fixing."""
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
        tests:
          - name: multiple_birth_sibling
            config:
              meta:
                check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.is_multiple_birth.multiple_birth_sibling_dbt
                introduced_date: "2026-01-15"
                description: "Every multiple-birth record needs a matching sibling."
                changelog: []
        """)

    checks = cl.parse_dbt_check_metadata(path)

    assert len(checks) == 1
    c = checks[0]
    assert c.check_id == ("data-asset-1.bdm.birth_registrations.stg_birth_registrations."
                           "is_multiple_birth.multiple_birth_sibling_dbt")
    assert c.tool == "dbt"
    assert c.introduced_date == "2026-01-15"


def test_parse_dbt_check_metadata_raises_for_singular_test_without_check_id(tmp_path):
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
        tests:
          - name: multiple_birth_sibling
            config: {}
        """)

    with pytest.raises(cl.MissingCheckIdError) as exc_info:
        cl.parse_dbt_check_metadata(path)

    assert "multiple_birth_sibling" in str(exc_info.value)


def test_dbt_check_id_lookup_keys_generic_tests_by_column_and_type(tmp_path):
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
            columns:
              - name: registration_number
                tests:
                  - not_null:
                      meta:
                        check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.registration_number.not_null_dbt
        """)

    lookup = cl.dbt_check_id_lookup(path)

    assert lookup[("registration_number", "not_null")] == (
        "data-asset-1.bdm.birth_registrations.stg_birth_registrations.registration_number.not_null_dbt")


def test_dbt_check_id_lookup_keys_singular_tests_by_name_with_no_column(tmp_path):
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
        tests:
          - name: multiple_birth_sibling
            config:
              meta:
                check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.is_multiple_birth.multiple_birth_sibling_dbt
        """)

    lookup = cl.dbt_check_id_lookup(path)

    assert lookup[(None, "multiple_birth_sibling")] == (
        "data-asset-1.bdm.birth_registrations.stg_birth_registrations."
        "is_multiple_birth.multiple_birth_sibling_dbt")


def test_parse_dbt_check_metadata_covers_model_level_tests(tmp_path):
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
            tests:
              - dbt_utils.recency:
                  meta:
                    check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.recency
                    changelog: []
                  field: date_of_birth
        """)

    checks = cl.parse_dbt_check_metadata(path)

    assert len(checks) == 1
    assert checks[0].check_id == "data-asset-1.bdm.birth_registrations.stg_birth_registrations.recency"


def test_parse_dbt_check_metadata_config_hash_excludes_meta_but_includes_config(tmp_path):
    base = """\
        models:
          - name: m
            columns:
              - name: c
                tests:
                  - not_null:
                      meta:
                        check_id: x.y.z.m.c.not_null
                        description: "{desc}"
                        changelog: []
                      config:
                        warn_if: "{warn}"
        """
    path_a = _write(tmp_path, "a.yml", base.format(desc="first description", warn=">90"))
    path_b = _write(tmp_path, "b.yml", base.format(desc="a totally different description", warn=">90"))
    path_c = _write(tmp_path, "c.yml", base.format(desc="first description", warn=">50"))

    hash_a = cl.parse_dbt_check_metadata(path_a)[0].config_hash
    hash_b = cl.parse_dbt_check_metadata(path_b)[0].config_hash
    hash_c = cl.parse_dbt_check_metadata(path_c)[0].config_hash

    assert hash_a == hash_b, "changing only the human-written description must NOT change the config hash"
    assert hash_a != hash_c, "changing an actual config value (warn_if) MUST change the config hash"


# ---- Soda parsing ---------------------------------------------------------

def test_parse_soda_check_metadata_extracts_check_id_from_attributes(tmp_path):
    path = _write(tmp_path, "checks.yml", """\
        checks for birth_registrations:
          - missing_percent(place_of_birth_facility) > 5%:
              name: facility missing rate
              attributes:
                check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.place_of_birth_facility.missing_percent
                description: "Facility should usually be captured."
                changelog: []
        """)

    checks = cl.parse_soda_check_metadata(path)

    assert len(checks) == 1
    assert checks[0].check_id == "data-asset-1.bdm.birth_registrations.stg_birth_registrations.place_of_birth_facility.missing_percent"
    assert checks[0].tool == "soda"


def test_parse_soda_check_metadata_ignores_dataset_level_attributes_block(tmp_path):
    path = _write(tmp_path, "checks.yml", """\
        checks for birth_registrations:
          - attributes:
              owner: some-team
          - row_count > 0:
              name: has rows
              attributes:
                check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.row_count
        """)

    checks = cl.parse_soda_check_metadata(path)

    assert len(checks) == 1, "a dataset-level 'attributes:' default block is not a check and must be skipped"
    assert checks[0].check_id == "data-asset-1.bdm.birth_registrations.stg_birth_registrations.row_count"


def test_parse_soda_check_metadata_raises_for_checks_without_check_id(tmp_path):
    path = _write(tmp_path, "checks.yml", """\
        checks for birth_registrations:
          - row_count > 0:
              name: has rows
        """)

    with pytest.raises(cl.MissingCheckIdError, match="row_count"):
        cl.parse_soda_check_metadata(path)


def test_parse_soda_check_metadata_config_hash_ignores_name_and_attributes(tmp_path):
    base = """\
        checks for t:
          - missing_percent(col) > 5%:
              name: "{name}"
              attributes:
                check_id: x.y.t.col.missing_percent
                changelog: []
              samples limit: 100
        """
    path_a = _write(tmp_path, "a.yml", base.format(name="original name"))
    path_b = _write(tmp_path, "b.yml", base.format(name="renamed label"))

    hash_a = cl.parse_soda_check_metadata(path_a)[0].config_hash
    hash_b = cl.parse_soda_check_metadata(path_b)[0].config_hash

    assert hash_a == hash_b, "renaming a check's cosmetic name: field must not change its config hash"


# ---- Contract parsing -------------------------------------------------

def test_parse_contract_check_metadata_extracts_check_id_from_custom_properties(tmp_path):
    path = _write(tmp_path, "contract.yaml", """\
        schema:
          - name: birth_registrations
            properties:
              - name: registration_number
                quality:
                  - metric: nullValues
                    mustBe: 0
                    customProperties:
                      - property: check_id
                        value: data-asset-1.bdm.birth_registrations.stg_birth_registrations.registration_number.nullValues
                      - property: introduced_date
                        value: "2026-01-15"
        """)

    checks = cl.parse_contract_check_metadata(path)

    assert len(checks) == 1
    assert checks[0].check_id == "data-asset-1.bdm.birth_registrations.stg_birth_registrations.registration_number.nullValues"
    assert checks[0].introduced_date == "2026-01-15"


def test_parse_contract_check_metadata_reuses_native_description(tmp_path):
    path = _write(tmp_path, "contract.yaml", """\
        schema:
          - name: t
            properties:
              - name: c
                quality:
                  - metric: nullValues
                    mustBe: 0
                    description: "A native ODCS description, not duplicated into customProperties."
                    customProperties:
                      - property: check_id
                        value: x.y.t.tbl.c.nullValues
        """)

    checks = cl.parse_contract_check_metadata(path)

    assert checks[0].description == "A native ODCS description, not duplicated into customProperties."


def test_parse_contract_check_metadata_covers_table_level_quality(tmp_path):
    path = _write(tmp_path, "contract.yaml", """\
        schema:
          - name: birth_registrations
            quality:
              - metric: rowCount
                mustBeGreaterThan: 0
                customProperties:
                  - property: check_id
                    value: x.y.birth_registrations.stg_birth_registrations.rowCount
        """)

    checks = cl.parse_contract_check_metadata(path)

    assert len(checks) == 1
    assert checks[0].check_id == "x.y.birth_registrations.stg_birth_registrations.rowCount"


def test_parse_contract_check_metadata_raises_for_quality_rule_without_check_id(tmp_path):
    path = _write(tmp_path, "contract.yaml", """\
        schema:
          - name: birth_registrations
            properties:
              - name: registration_number
                quality:
                  - metric: nullValues
                    mustBe: 0
        """)

    with pytest.raises(cl.MissingCheckIdError, match="nullValues"):
        cl.parse_contract_check_metadata(path)


# ---- Evidently parsing (plain dict, no file I/O) -----------------------

def test_parse_evidently_check_metadata_reads_a_check_lifecycle_dict():
    check_lifecycle = {
        "data-asset-1.bdm.birth_registrations.stg_birth_registrations.row_count_growth": {
            "introduced_date": "2026-02-01",
            "description": "Row count should mostly grow run over run.",
            "changelog": [],
        },
    }

    checks = cl.parse_evidently_check_metadata(check_lifecycle, source="run_evidently_bdm.py")

    assert len(checks) == 1
    assert checks[0].check_id == "data-asset-1.bdm.birth_registrations.stg_birth_registrations.row_count_growth"
    assert checks[0].tool == "evidently"
    assert checks[0].source_file == "run_evidently_bdm.py"


# ---- Duplicate detection -------------------------------------------------

def test_find_duplicate_check_ids_flags_ids_used_more_than_once():
    checks = [
        cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="f1"),
        cl.CheckMetadata(check_id="b", tool="soda", config_hash="h2", source_file="f2"),
        cl.CheckMetadata(check_id="a", tool="datacontract", config_hash="h3", source_file="f3"),
    ]

    assert cl.find_duplicate_check_ids(checks) == ["a"]


def test_find_duplicate_check_ids_empty_for_all_unique():
    checks = [
        cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="f1"),
        cl.CheckMetadata(check_id="b", tool="soda", config_hash="h2", source_file="f2"),
    ]

    assert cl.find_duplicate_check_ids(checks) == []


# ---- Undocumented-change detection ---------------------------------------

def test_find_undocumented_changes_flags_a_hash_change_with_no_new_changelog_entry():
    old = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]
    new = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="hash2", source_file="f", changelog=[])]

    assert cl.find_undocumented_changes(old, new) == ["a"]


def test_find_undocumented_changes_allows_a_hash_change_with_a_new_changelog_entry():
    old = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]
    new = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="hash2", source_file="f",
                             changelog=[{"date": "2026-06-01", "description": "tightened it", "author": "Keith Moss", "breaking": False}])]

    assert cl.find_undocumented_changes(old, new) == []


def test_find_undocumented_changes_ignores_checks_with_no_hash_change():
    old = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]
    new = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]

    assert cl.find_undocumented_changes(old, new) == []


def test_find_undocumented_changes_ignores_brand_new_check_ids():
    old = []
    new = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]

    assert cl.find_undocumented_changes(old, new) == [], \
        "a check that didn't exist before has nothing to have 'changed' from"


# ---- find_disappeared_check_ids() -----------------------------------------

def test_find_disappeared_check_ids_flags_a_check_id_missing_from_new():
    old = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="f")]
    new = []

    assert cl.find_disappeared_check_ids(old, new) == ["a"]


def test_find_disappeared_check_ids_allows_a_properly_retired_check():
    """A check_id, once introduced, must never be deleted or renamed -
    but retiring it (moving its metadata to that tool's own -retired
    sibling file) is legitimate: the caller's own collection already
    reads both active and retired sources into one list (see
    validate_check_lifecycle.py's _YAML_SOURCES), so a properly-retired
    check_id is still present in `new_checks`, just now carrying
    retired_as_of - this function only ever sees "is the check_id there
    at all", not which file it came from."""
    old = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="schema.yml")]
    new = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="schema-retired.yml",
                             retired_as_of="2026-09-16", retired_reason="superseded")]

    assert cl.find_disappeared_check_ids(old, new) == []


def test_find_disappeared_check_ids_empty_when_nothing_changed():
    checks = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="f")]

    assert cl.find_disappeared_check_ids(checks, checks) == []


def test_find_disappeared_check_ids_ignores_brand_new_check_ids():
    old = []
    new = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="f")]

    assert cl.find_disappeared_check_ids(old, new) == []


# ---- Top-level validate() ------------------------------------------------

def test_validate_returns_empty_list_when_everything_is_clean():
    checks = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="f")]

    assert cl.validate(checks, checks) == []


def test_validate_reports_a_disappeared_check_id():
    old = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="f")]
    new = []

    errors = cl.validate(old, new)

    assert len(errors) == 1
    assert "disappeared" in errors[0] and "'a'" in errors[0]


def test_validate_allows_a_properly_retired_check_id():
    old = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="schema.yml", changelog=[])]
    new = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="schema-retired.yml",
                             changelog=[], retired_as_of="2026-09-16", retired_reason="superseded")]

    assert cl.validate(old, new) == []


def test_validate_reports_both_kinds_of_error_together():
    old = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="f", changelog=[])]
    new = [
        cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h2", source_file="f", changelog=[]),  # undocumented change
        cl.CheckMetadata(check_id="b", tool="soda", config_hash="h3", source_file="f2"),
        cl.CheckMetadata(check_id="b", tool="datacontract", config_hash="h4", source_file="f3"),  # duplicate
    ]

    errors = cl.validate(old, new)

    assert len(errors) == 2
    assert any("Duplicate check_id" in e and "'b'" in e for e in errors)
    assert any("changed without a new changelog entry" in e and "'a'" in e for e in errors)
