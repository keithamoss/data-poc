"""Tests for qa_tools/common/check_lifecycle.py - parsing check-lifecycle
metadata from all 4 tools' own definition formats, and the two
validations that gate publishing (plans/publishing-and-history.md
Thread D, Phase 1): globally-unique check_id, and no undocumented
config changes. Fixtures throughout, not the real ~60-100 production
checks - keeps this fast and focused on the parsing/validation logic
itself, same convention as the rest of this project's test suite."""
from __future__ import annotations

import textwrap

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


def test_parse_dbt_check_metadata_skips_tests_without_check_id(tmp_path):
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

    checks = cl.parse_dbt_check_metadata(path)

    assert checks == [], "a bare test name and a test with no meta block have no check_id - not migrated, not an error"


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
        """)

    checks = cl.parse_soda_check_metadata(path)

    assert checks == [], "a dataset-level 'attributes:' default block is not a check, and the row_count check has no check_id"


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


# ---- Top-level validate() ------------------------------------------------

def test_validate_returns_empty_list_when_everything_is_clean():
    checks = [cl.CheckMetadata(check_id="a", tool="dbt", config_hash="h1", source_file="f")]

    assert cl.validate(checks, checks) == []


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
