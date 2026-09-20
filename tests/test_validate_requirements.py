"""Tests for qa_tools/common/validate_requirements.py - the
requirements.yaml CI gate (item 75, plans/qa-pipeline.md). validate()
is tested against small, hand-built fixture dicts (never the real
committed requirements.yaml, whose own content changes over time); the
linked-test existence checks are tested against this repo's own real,
stable test files - deliberately real files, not more fixtures, since
the whole point of this gate is confirming a REAL file/test exists, not
just that some string matches some other string."""
from __future__ import annotations

from qa_tools.common.validate_requirements import _linked_test_exists, _python_symbol_exists, validate


def _valid_entry(**overrides):
    entry = {
        "id": "REQ-QAC-001",
        "title": "A real feature",
        "story": "As a user, I want X, so that Y.",
        "moscow": "must",
        "status": "built",
        "acceptance_criteria": ["It does the thing."],
        "linked_tests": ["tests/test_resupply.py::test_add_business_days_skips_weekends"],
        # Both required once `status` is "built" (2026-09-20) - so the
        # base fixture, which IS built, has to carry them to stay valid.
        "implemented_by": ["qa_tools/common/validate_requirements.py::validate"],
        "evidence": ["2026-09-20: 27 requirements validate with zero errors."],
        "decisions": ["Kept the register as YAML rather than a database, so it "
                      "diffs and reviews like the code it describes."],
    }
    entry.update(overrides)
    return entry


# ---- validate() ------------------------------------------------------

def test_validate_returns_empty_list_for_a_fully_valid_requirement():
    assert validate([_valid_entry()]) == []


def test_validate_rejects_a_malformed_id():
    errors = validate([_valid_entry(id="not-an-id")])
    assert any("id" in e and "not-an-id" in e for e in errors)


def test_validate_rejects_the_old_legacy_bare_id_format():
    """2026-09-19, Keith's own follow-up ask: drop the legacy "REQ-NNN"
    shape entirely rather than grandfather it - the 22 pre-2026-09-19
    entries were migrated to the component-coded shape the same day
    (requirements.yaml's own header comment has the full migration
    note), so the bare shape is a real validation error now, not just
    an old convention nobody uses any more."""
    errors = validate([_valid_entry(id="REQ-014")])
    assert any("id" in e and "REQ-014" in e for e in errors)


def test_validate_accepts_a_current_component_coded_id():
    """2026-09-19, Keith's own follow-up ask: a real 3-4 letter
    component code in the id's middle segment."""
    assert validate([_valid_entry(id="REQ-DASH-023")]) == []


def test_validate_rejects_a_component_code_not_in_the_real_taxonomy():
    errors = validate([_valid_entry(id="REQ-FOO-023")])
    assert any("id" in e and "REQ-FOO-023" in e for e in errors)


def test_validate_rejects_duplicate_ids():
    errors = validate([_valid_entry(id="REQ-QAC-001"), _valid_entry(id="REQ-QAC-001")])
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


# ---- _linked_test_exists() / _python_symbol_exists() - against REAL repo files --

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


def test_python_symbol_exists_returns_false_for_a_missing_file():
    assert _python_symbol_exists("tests/does_not_exist.py", ["test_x"]) is False


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
    # Behaviour CHANGED deliberately 2026-09-20 (REQ-DOCS-029). The
    # schema strips whitespace, so "   " becomes "" - which is exactly
    # the value an ABSENT source already has, and source is optional.
    # Erroring on it was noise for no benefit: there is no difference in
    # intent between "I left it blank" and "I left it out".
    assert validate([_valid_entry(source="   ")]) == []


def test_source_can_be_real_free_text():
    assert validate([_valid_entry(source="Keith, voice-dictated batch, 2026-09-19")]) == []


def test_date_written_is_optional_and_absent_is_fine():
    assert validate([_valid_entry()]) == []


def test_date_written_defaulted_to_empty_string_by_the_real_parser_is_fine():
    """Same real-parser-default treatment as `source` above -
    dashboard/requirements_yaml.py's parse_requirements() also defaults
    an unset `date_written` to `""`, not `None`."""
    assert validate([_valid_entry(date_written="")]) == []


def test_date_written_accepts_a_real_iso_date():
    assert validate([_valid_entry(date_written="2026-09-19")]) == []


def test_date_written_rejects_a_non_iso_date():
    errors = validate([_valid_entry(date_written="19/09/2026")])
    assert any("date_written" in e for e in errors)


def test_non_functional_requirements_absent_is_fine():
    assert validate([_valid_entry()]) == []


def test_non_functional_requirements_must_be_a_list_not_a_bare_string():
    errors = validate([_valid_entry(non_functional_requirements="CI must never touch live data")])
    assert any("non_functional_requirements" in e and "valid list" in e for e in errors), errors


def test_non_functional_requirements_rejects_empty_entries():
    errors = validate([_valid_entry(non_functional_requirements=["", "  "])])
    assert any("non_functional_requirements" in e and "non-empty strings" in e for e in errors), errors


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
    errors = validate([_valid_entry(dependencies="REQ-QAC-002")])
    assert any("dependencies" in e and "valid list" in e for e in errors), errors


def test_dependencies_referencing_a_real_id_in_the_same_file_is_fine():
    errors = validate([_valid_entry(id="REQ-QAC-001", dependencies=["REQ-QAC-002"]),
                        _valid_entry(id="REQ-QAC-002")])
    assert errors == []


def test_dependencies_referencing_a_nonexistent_id_is_an_error():
    errors = validate([_valid_entry(id="REQ-QAC-001", dependencies=["REQ-QAC-999"])])
    assert any("dependencies entry 'REQ-QAC-999' does not match any real requirement id" in e for e in errors)


# ---- implemented_by ------------------------------------------------------
#
# Keith's call, 2026-09-20 (plans/tooling.md #18). The register already
# says which TESTS verify a requirement; it never said where the thing
# lives. The lesson driving the shape is the `evidence` field sitting at
# zero use a day after it shipped, despite a well-written spec: it was
# assigned to an agent that is read-only and so cannot write it, and no
# instruction anywhere tells anyone to populate it. A field with no
# forcing function stays empty, so this one is required once a
# requirement is `built` and CI refuses to pass without it.

def test_a_built_requirement_must_say_where_it_is_implemented():
    errors = validate([_valid_entry(implemented_by=[])])
    assert any("implemented_by" in e for e in errors), errors


def test_implemented_by_is_optional_until_a_requirement_is_built():
    assert validate([_valid_entry(status="not_started", linked_tests=[])]) == []


def test_a_python_entry_must_name_a_symbol_not_just_a_file():
    """Keith's explicit call: "Python code must have a symbol."

    A bare path is verified only by `Path.exists()`, which stays green
    while the file is gutted, stubbed, or emptied - the same weak
    guarantee that let plans/*.md `touches:` lines rot while looking
    authoritative. A symbol is AST-verified, so a rename breaks the
    build and names the requirement that claimed it."""
    errors = validate([_valid_entry(implemented_by=["qa_tools/common/validate_requirements.py"])])
    assert any("symbol" in e.lower() for e in errors), errors


def test_a_python_symbol_that_does_not_exist_is_an_error():
    errors = validate([_valid_entry(implemented_by=[
        "qa_tools/common/validate_requirements.py::no_such_function"])])
    assert any("no_such_function" in e for e in errors), errors


def test_a_real_python_symbol_resolves():
    assert validate([_valid_entry(implemented_by=[
        "qa_tools/common/check_lifecycle.py::parse_contract_check_metadata",
        "qa_tools/common/check_lifecycle.py::CheckMetadata"])]) == []


def test_a_front_end_path_may_be_bare():
    """No AST parser for the template's inline JS on the Python side, so
    a bare path is allowed there rather than pretending to a rigour this
    toolchain does not have. The JS symbol form is checked by the Node
    toolchain instead - tests-js/implemented_by.test.js."""
    assert validate([_valid_entry(implemented_by=[
        "dashboard/qa-reporting-dashboard.template.html"])]) == []


def test_a_symbol_on_a_file_neither_python_nor_front_end_is_rejected():
    """Nothing verifies a `::` on a YAML or SQL file, so accepting one
    would record an unchecked claim in a field whose whole point is that
    it is checked."""
    errors = validate([_valid_entry(implemented_by=[
        "contract/data-asset.yaml::data_asset_id"])])
    assert any("contract/data-asset.yaml" in e for e in errors), errors


def test_an_implemented_by_path_that_does_not_exist_is_an_error():
    errors = validate([_valid_entry(implemented_by=["qa_tools/common/nope.py::thing"])])
    assert any("nope.py" in e for e in errors), errors


def test_a_built_requirement_must_carry_a_measured_result():
    """Keith's call, 2026-09-20: mandate it, no exceptions.

    The field went unused on all 27 requirements for the day and a half
    it was optional, and nothing noticed. The same forcing function
    `implemented_by` gets - CI refusing to go green - is what keeps it
    from drifting back.

    Asked whether a requirement with no obvious measurement (dark mode)
    should be allowed an explicit opt-out, he said no exceptions. That
    turned out to be the right call: demanding a real number produced
    one - all 21 colour tokens redefined under the dark theme, zero
    falling through to their light value - and produced it by measuring
    the real page rather than asserting a toggle flips."""
    errors = validate([_valid_entry(evidence=[])])
    assert any("evidence" in e for e in errors), errors


def test_evidence_is_optional_until_a_requirement_is_built():
    assert validate([_valid_entry(status="not_started", linked_tests=[],
                                   implemented_by=[], evidence=[])]) == []


# ---- decisions -------------------------------------------------------
#
# Keith's idea, 2026-09-20, and the thing that makes deleting plans prose
# safe rather than merely reversible. Git preserves a deleted write-up,
# but finding one needs `git log -S"<phrase>"` with a phrase you must
# already suspect. This field moves the reasoning INTO the requirement -
# "decisions taken, other pathways rejected... our collective memory of
# the thinking that went into that requirement" - so it does not have to
# be recovered from history or kept in a massive plans file.
#
# It sits opposite `open_questions`: that field holds the forks NOT
# resolved, this one holds the forks that were.

def test_a_built_requirement_must_record_its_decisions():
    errors = validate([_valid_entry(decisions=[])])
    assert any("decisions" in e for e in errors), errors


def test_decisions_is_optional_until_a_requirement_is_built():
    assert validate([_valid_entry(status="not_started", linked_tests=[],
                                   implemented_by=[], evidence=[], decisions=[])]) == []


def test_decisions_must_be_a_list_of_non_empty_strings():
    errors = validate([_valid_entry(decisions=["   "])])
    assert any("decisions" in e for e in errors), errors


def test_a_module_level_constant_counts_as_a_symbol():
    """Found by the gate itself, 2026-09-20: a module that is purely
    constants - qa_tools/common/vocab.py - could not satisfy
    implemented_by at all, because the AST check only looked for
    functions and classes. A path alone was rejected (rightly), and no
    symbol was acceptable (wrongly).

    A constant is a symbol worth pinning for exactly the same reason a
    function is: delete COMPONENT_CODES and the requirement claiming it
    should break, rather than a bare path staying green over an empty
    file."""
    assert _python_symbol_exists("qa_tools/common/vocab.py", ["COMPONENT_CODES"]) is True
    assert _python_symbol_exists("qa_tools/common/vocab.py", ["NOT_A_REAL_CONST"]) is False
