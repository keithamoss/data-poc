"""Tests for qa_tools/common/validate_requirements.py - the
requirements.yaml CI gate (item 75, plans/qa-pipeline.md). validate()
is tested against small, hand-built fixture dicts (never the real
committed requirements.yaml, whose own content changes over time); the
linked-test existence checks are tested against this repo's own real,
stable test files - deliberately real files, not more fixtures, since
the whole point of this gate is confirming a REAL file/test exists, not
just that some string matches some other string."""
from __future__ import annotations

from qa_tools.common.validate_requirements import _linked_test_exists, _python_test_exists, validate


def _valid_entry(**overrides):
    entry = {
        "id": "REQ-001",
        "title": "A real feature",
        "story": "As a user, I want X, so that Y.",
        "moscow": "must",
        "status": "built",
        "acceptance_criteria": ["It does the thing."],
        "linked_tests": ["tests/test_resupply.py::test_add_business_days_skips_weekends"],
    }
    entry.update(overrides)
    return entry


# ---- validate() ------------------------------------------------------

def test_validate_returns_empty_list_for_a_fully_valid_requirement():
    assert validate([_valid_entry()]) == []


def test_validate_rejects_a_malformed_id():
    errors = validate([_valid_entry(id="not-an-id")])
    assert any("id" in e and "not-an-id" in e for e in errors)


def test_validate_rejects_duplicate_ids():
    errors = validate([_valid_entry(id="REQ-001"), _valid_entry(id="REQ-001")])
    assert any("globally unique" in e for e in errors)


def test_validate_rejects_missing_title():
    errors = validate([_valid_entry(title="")])
    assert any("title" in e for e in errors)


def test_validate_rejects_missing_story():
    errors = validate([_valid_entry(story="  ")])
    assert any("story" in e for e in errors)


def test_validate_rejects_invalid_moscow():
    errors = validate([_valid_entry(moscow="urgent")])
    assert any("moscow" in e for e in errors)


def test_validate_rejects_invalid_status():
    errors = validate([_valid_entry(status="done")])
    assert any("status" in e for e in errors)


def test_validate_rejects_empty_acceptance_criteria():
    errors = validate([_valid_entry(acceptance_criteria=[])])
    assert any("acceptance_criteria" in e for e in errors)


def test_validate_rejects_a_built_requirement_with_no_linked_tests():
    errors = validate([_valid_entry(status="built", linked_tests=[])])
    assert any("linked_tests is empty" in e for e in errors)


def test_validate_allows_not_started_with_no_linked_tests():
    errors = validate([_valid_entry(status="not_started", linked_tests=[])])
    assert errors == []


def test_validate_rejects_a_linked_test_that_does_not_exist():
    errors = validate([_valid_entry(linked_tests=["tests/test_this_file_does_not_exist.py"])])
    assert any("does not resolve" in e for e in errors)


def test_validate_rejects_a_linked_test_naming_a_real_file_but_fake_function():
    errors = validate([_valid_entry(linked_tests=["tests/test_resupply.py::test_this_does_not_exist"])])
    assert any("does not resolve" in e for e in errors)


# ---- _linked_test_exists() / _python_test_exists() - against REAL repo files --

def test_real_module_level_test_function_resolves():
    assert _linked_test_exists("tests/test_resupply.py::test_add_business_days_skips_weekends") is True


def test_real_class_and_method_resolves():
    assert _linked_test_exists(
        "tests/test_dashboard_e2e.py::TestDarkModeToggle::test_toggling_dark_mode_persists_across_a_reload"
    ) is True


def test_bare_class_reference_resolves():
    assert _linked_test_exists("tests/test_dashboard_e2e.py::TestDarkModeToggle") is True


def test_real_file_with_no_node_id_resolves_on_existence_alone():
    assert _linked_test_exists("tests/test_resupply.py") is True


def test_real_js_test_file_resolves_on_existence_alone():
    assert _linked_test_exists("tests-js/supply-history.test.js") is True


def test_missing_js_file_does_not_resolve():
    assert _linked_test_exists("tests-js/this_does_not_exist.test.js") is False


def test_method_name_that_does_not_exist_in_a_real_class_does_not_resolve():
    assert _linked_test_exists("tests/test_dashboard_e2e.py::TestDarkModeToggle::test_nonexistent") is False


def test_python_test_exists_returns_false_for_a_missing_file():
    assert _python_test_exists("tests/does_not_exist.py", ["test_x"]) is False


# ---- 5 new optional fields (2026-09-19, plans/wider.md #10) ---------

def test_source_is_optional_and_absent_is_fine():
    assert validate([_valid_entry()]) == []


def test_source_defaulted_to_empty_string_by_the_real_parser_is_fine():
    """Real bug found live, 2026-09-19: dashboard/requirements_yaml.py's
    parse_requirements() defaults an unset `source` to `""` (falsy),
    not `None` - and main() below always runs against parser output,
    never a raw dict. An earlier version of this check used `is not
    None`, which treated that real default as "present but invalid",
    failing all 22 real requirements.yaml entries at once. Confirmed
    failing against the pre-fix code by actually running `python3 -m
    qa_tools.common.validate_requirements` against the real committed
    file before this fix."""
    assert validate([_valid_entry(source="")]) == []


def test_source_if_present_must_be_a_non_empty_string():
    errors = validate([_valid_entry(source="   ")])
    assert any("source" in e for e in errors)


def test_source_can_be_real_free_text():
    assert validate([_valid_entry(source="Keith, voice-dictated batch, 2026-09-19")]) == []


def test_non_functional_requirements_absent_is_fine():
    assert validate([_valid_entry()]) == []


def test_non_functional_requirements_must_be_a_list_not_a_bare_string():
    errors = validate([_valid_entry(non_functional_requirements="CI must never touch live data")])
    assert any("non_functional_requirements must be a list" in e for e in errors)


def test_non_functional_requirements_rejects_empty_entries():
    errors = validate([_valid_entry(non_functional_requirements=["", "  "])])
    assert any("non_functional_requirements entries must be non-empty strings" in e for e in errors)


def test_non_functional_requirements_accepts_real_entries():
    assert validate([_valid_entry(non_functional_requirements=["CI must never touch live data"])]) == []


def test_open_questions_must_be_a_list_of_non_empty_strings():
    errors = validate([_valid_entry(open_questions=[None])])
    assert any("open_questions" in e for e in errors)


def test_evidence_must_be_a_list_of_non_empty_strings():
    errors = validate([_valid_entry(evidence=[123])])
    assert any("evidence" in e for e in errors)


def test_dependencies_absent_is_fine():
    assert validate([_valid_entry()]) == []


def test_dependencies_must_be_a_list():
    errors = validate([_valid_entry(dependencies="REQ-002")])
    assert any("dependencies must be a list" in e for e in errors)


def test_dependencies_referencing_a_real_id_in_the_same_file_is_fine():
    errors = validate([_valid_entry(id="REQ-001", dependencies=["REQ-002"]), _valid_entry(id="REQ-002")])
    assert errors == []


def test_dependencies_referencing_a_nonexistent_id_is_an_error():
    errors = validate([_valid_entry(id="REQ-001", dependencies=["REQ-999"])])
    assert any("dependencies entry 'REQ-999' does not match any real requirement id" in e for e in errors)
