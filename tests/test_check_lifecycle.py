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
                        category: completeness
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
                category: consistency
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

    assert lookup[("stg_birth_registrations", "registration_number", "not_null")] == (
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

    assert lookup[(None, None, "multiple_birth_sibling")] == (
        "data-asset-1.bdm.birth_registrations.stg_birth_registrations."
        "is_multiple_birth.multiple_birth_sibling_dbt")


def test_dbt_check_id_lookup_strips_the_package_prefix_from_cross_package_macros(tmp_path):
    """A real bug, found 2026-09-16 wiring this lookup into run_dbt_bdm.py
    for real: schema.yml's own key for a dbt_utils macro is package-
    qualified ("dbt_utils.accepted_range"), but dbt's compiled manifest
    reports that same test's name UNqualified (test_metadata["name"] ==
    "accepted_range") - confirmed against a real manifest, not assumed.
    Without stripping the prefix here, every dbt_utils-sourced check_id
    silently never matched the caller's own resolved test_name."""
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
            columns:
              - name: date_of_birth
                tests:
                  - dbt_utils.accepted_range:
                      meta:
                        check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.date_of_birth.accepted_range_dbt
        """)

    lookup = cl.dbt_check_id_lookup(path)

    assert lookup[("stg_birth_registrations", "date_of_birth", "accepted_range")] == (
        "data-asset-1.bdm.birth_registrations.stg_birth_registrations."
        "date_of_birth.accepted_range_dbt")
    assert ("stg_birth_registrations", "date_of_birth", "dbt_utils.accepted_range") not in lookup


def test_dbt_check_id_lookup_does_not_collide_across_models_with_the_same_column_and_test_type(tmp_path):
    """A real bug, found 2026-09-16 wiring this into run_dbt_bdm.py/
    run_dbt_cp.py for real: schema.yml holds every dataset's models
    together in one file, and both BDM's stg_birth_registrations and
    CP's stg_cp_clients have a date_of_birth column with an
    accepted_range test. Without the model in the lookup key, the second
    one parsed silently overwrote the first's check_id - real BDM
    results were coming back tagged with CP's check_id."""
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
            columns:
              - name: date_of_birth
                tests:
                  - dbt_utils.accepted_range:
                      meta:
                        check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.date_of_birth.accepted_range_dbt
          - name: stg_cp_clients
            columns:
              - name: date_of_birth
                tests:
                  - dbt_utils.accepted_range:
                      meta:
                        check_id: data-asset-1.cp.child_protection.stg_cp_clients.date_of_birth.accepted_range_dbt
        """)

    lookup = cl.dbt_check_id_lookup(path)

    assert lookup[("stg_birth_registrations", "date_of_birth", "accepted_range")] == (
        "data-asset-1.bdm.birth_registrations.stg_birth_registrations."
        "date_of_birth.accepted_range_dbt")
    assert lookup[("stg_cp_clients", "date_of_birth", "accepted_range")] == (
        "data-asset-1.cp.child_protection.stg_cp_clients.date_of_birth.accepted_range_dbt")


def test_parse_dbt_check_metadata_covers_model_level_tests(tmp_path):
    path = _write(tmp_path, "schema.yml", """\
        models:
          - name: stg_birth_registrations
            tests:
              - dbt_utils.recency:
                  meta:
                    check_id: data-asset-1.bdm.birth_registrations.stg_birth_registrations.recency
                    category: timeliness
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
                        category: completeness
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
                category: completeness
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
                category: completeness
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
                category: completeness
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
                    dimension: completeness
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
                    dimension: completeness
                    mustBe: 0
                    description: "A native ODCS description, not duplicated into customProperties."
                    customProperties:
                      - property: check_id
                        value: x.y.t.tbl.c.nullValues
        """)

    checks = cl.parse_contract_check_metadata(path)

    assert checks[0].description == "A native ODCS description, not duplicated into customProperties."


def test_parse_contract_check_metadata_reads_failure_indicates_and_technical_note(tmp_path):
    """REQ-QAC-024's two prose fields, on the ODCS contract specifically.

    Found 2026-09-20, before the authoring pass wrote a single one of
    them: this parser built its CheckMetadata field list by hand rather
    than through `_lifecycle_fields()` like the other four, so both new
    fields were silently dropped - authored in the YAML, `None` on the
    way out, no error anywhere. 89 of 257 active checks are
    datacontract checks, so a third of the corpus would have been
    written, committed, and quietly never rendered.

    The hand-built list is the failure mode CLAUDE.md already names:
    "a hand-maintained allowlist of copied fields drops new fields in
    silence; spread-then-override carries them by default". This test
    is what makes the next field added to CheckMetadata fail loudly
    here instead.
    """
    path = _write(tmp_path, "contract.yaml", """\
        schema:
          - name: t
            properties:
              - name: c
                quality:
                  - metric: invalidValues
                    dimension: conformity
                    mustBe: 0
                    description: "A single unrecognised value fails."
                    customProperties:
                      - property: check_id
                        value: x.y.t.tbl.c.invalidValues
                      - property: failure_indicates
                        value: "The source system has started emitting a value that was never agreed."
                      - property: technical_note
                        value: "Paired with the Soda check on the same column."
        """)

    checks = cl.parse_contract_check_metadata(path)

    assert checks[0].description == "A single unrecognised value fails."
    assert checks[0].failure_indicates == (
        "The source system has started emitting a value that was never agreed.")
    assert checks[0].technical_note == "Paired with the Soda check on the same column."


def test_parse_contract_check_metadata_covers_table_level_quality(tmp_path):
    path = _write(tmp_path, "contract.yaml", """\
        schema:
          - name: birth_registrations
            quality:
              - metric: rowCount
                dimension: completeness
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
            "category": "completeness",
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


@pytest.mark.parametrize("field, value", [
    ("description", "A different plain-English sentence."),
    ("name", "A hand-authored display name"),
    ("failure_indicates", "The upstream extract probably ran early."),
    ("technical_note", "Paired with the Soda check on the same column."),
])
def test_authored_prose_never_changes_an_evidently_checks_config_hash(field, value):
    """The trap REQ-QAC-024 named before a line of it was written, and
    it is real.

    dbt and Soda exclude their WHOLE metadata block from the config
    hash, so any field added there is automatically cosmetic. Evidently
    does the opposite - it hashes everything EXCEPT an explicit list of
    names - so a new authored field is hashed by default, and every
    Evidently check "changes" the moment someone writes one. A changed
    hash with no changelog entry is what `find_undocumented_changes`
    fails CI on, so the symptom is a broken build blaming a proofread.

    `name` is in here because it has the same defect and shipped
    earlier: REQ-QAC-023 added it to the dataclass and to the dbt/Soda
    side, and no Evidently check happens to carry one yet - so the bug
    is latent rather than absent, and the first one to get a display
    name would have found it."""
    base = {"category": "completeness", "introduced_date": "2026-02-01",
            "description": "Row count should mostly grow run over run.", "changelog": []}
    cid = "data-asset-1.bdm.birth_registrations.stg_birth_registrations.row_count_growth"

    before = cl.parse_evidently_check_metadata({cid: base}, source="s")[0].config_hash
    after = cl.parse_evidently_check_metadata(
        {cid: {**base, field: value}}, source="s")[0].config_hash

    assert before == after, (
        f"authoring {field!r} changed the config hash - the check now reads as "
        f"modified, and CI will demand a changelog entry for a wording change")


def test_the_evidently_hash_still_notices_a_real_config_change():
    """The other side of it. Widening the exclusion list is only safe
    while something a check actually DOES still moves the hash - an
    exclusion list that grew until it covered everything would make the
    whole lifecycle gate silently useless."""
    cid = "data-asset-1.bdm.birth_registrations.stg_birth_registrations.row_count_growth"
    base = {"category": "completeness", "description": "d", "changelog": [], "threshold": 0.1}
    before = cl.parse_evidently_check_metadata({cid: base}, source="s")[0].config_hash
    after = cl.parse_evidently_check_metadata(
        {cid: {**base, "threshold": 0.5}}, source="s")[0].config_hash
    assert before != after


# ---- Duplicate detection -------------------------------------------------

def test_find_duplicate_check_ids_flags_ids_used_more_than_once():
    checks = [
        cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="f1"),
        cl.CheckMetadata(check_id="b", category="completeness", tool="soda", config_hash="h2", source_file="f2"),
        cl.CheckMetadata(check_id="a", category="completeness", tool="datacontract", config_hash="h3", source_file="f3"),
    ]

    assert cl.find_duplicate_check_ids(checks) == ["a"]


def test_find_duplicate_check_ids_empty_for_all_unique():
    checks = [
        cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="f1"),
        cl.CheckMetadata(check_id="b", category="completeness", tool="soda", config_hash="h2", source_file="f2"),
    ]

    assert cl.find_duplicate_check_ids(checks) == []


# ---- Undocumented-change detection ---------------------------------------

def test_find_undocumented_changes_flags_a_hash_change_with_no_new_changelog_entry():
    old = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]
    new = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="hash2", source_file="f", changelog=[])]

    assert cl.find_undocumented_changes(old, new) == ["a"]


def test_find_undocumented_changes_allows_a_hash_change_with_a_new_changelog_entry():
    old = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]
    new = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="hash2", source_file="f",
                             changelog=[{"date": "2026-06-01", "description": "tightened it", "author": "Keith Moss", "breaking": False}])]

    assert cl.find_undocumented_changes(old, new) == []


def test_find_undocumented_changes_ignores_checks_with_no_hash_change():
    old = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]
    new = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]

    assert cl.find_undocumented_changes(old, new) == []


def test_find_undocumented_changes_ignores_brand_new_check_ids():
    old = []
    new = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="hash1", source_file="f", changelog=[])]

    assert cl.find_undocumented_changes(old, new) == [], \
        "a check that didn't exist before has nothing to have 'changed' from"


# ---- find_disappeared_check_ids() -----------------------------------------

def test_find_disappeared_check_ids_flags_a_check_id_missing_from_new():
    old = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="f")]
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
    old = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="schema.yml")]
    new = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="schema-retired.yml",
                             retired_as_of="2026-09-16", retired_reason="superseded")]

    assert cl.find_disappeared_check_ids(old, new) == []


def test_find_disappeared_check_ids_empty_when_nothing_changed():
    checks = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="f")]

    assert cl.find_disappeared_check_ids(checks, checks) == []


def test_find_disappeared_check_ids_ignores_brand_new_check_ids():
    old = []
    new = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="f")]

    assert cl.find_disappeared_check_ids(old, new) == []


# ---- Top-level validate() ------------------------------------------------

def test_validate_returns_empty_list_when_everything_is_clean():
    checks = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="f")]

    assert cl.validate(checks, checks) == []


def test_validate_reports_a_disappeared_check_id():
    old = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="f")]
    new = []

    errors = cl.validate(old, new)

    assert len(errors) == 1
    assert "disappeared" in errors[0] and "'a'" in errors[0]


def test_validate_allows_a_properly_retired_check_id():
    old = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="schema.yml", changelog=[])]
    new = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="schema-retired.yml",
                             changelog=[], retired_as_of="2026-09-16", retired_reason="superseded")]

    assert cl.validate(old, new) == []


def test_validate_reports_both_kinds_of_error_together():
    old = [cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h1", source_file="f", changelog=[])]
    new = [
        cl.CheckMetadata(check_id="a", category="completeness", tool="dbt", config_hash="h2", source_file="f", changelog=[]),  # undocumented change
        cl.CheckMetadata(check_id="b", category="completeness", tool="soda", config_hash="h3", source_file="f2"),
        cl.CheckMetadata(check_id="b", category="completeness", tool="datacontract", config_hash="h4", source_file="f3"),  # duplicate
    ]

    errors = cl.validate(old, new)

    assert len(errors) == 2
    assert any("Duplicate check_id" in e and "'b'" in e for e in errors)
    assert any("changed without a new changelog entry" in e and "'a'" in e for e in errors)
