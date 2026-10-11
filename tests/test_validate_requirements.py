"""Tests for qa_tools/common/validate_requirements.py - the
requirements.yaml CI gate (item 75, plans/qa-pipeline.md). validate()
is tested against small, hand-built fixture dicts (never the real
committed requirements.yaml, whose own content changes over time); the
linked-test existence checks are tested against this repo's own real,
stable test files - deliberately real files, not more fixtures, since
the whole point of this gate is confirming a REAL file/test exists, not
just that some string matches some other string."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from qa_tools.common.validate_requirements import _linked_test_exists, _python_symbol_exists, validate

ROOT = Path(__file__).resolve().parent.parent


def _valid_entry(**overrides):
    entry = {
        "id": "REQ-QAC-001",
        "title": "A real feature",
        "story": "As a user, I want X, so that Y.",
        "moscow": "must",
        "status": "built",
        # Required since 2026-09-20 - the one field nobody can
        # reconstruct after the fact, so the fixture has to carry it.
        "source": "Keith, voice-dictated batch, 2026-09-19",
        "acceptance_criteria": ["It does the thing."],
        "linked_tests": ["tests/test_resupply.py::test_add_business_days_skips_weekends"],
        # Both required once `status` is "built" (2026-09-20) - so the
        # base fixture, which IS built, has to carry them to stay valid.
        "implemented_by": ["qa_tools/common/validate_requirements.py::validate"],
        "evidence": ["2026-09-20: 27 requirements validate with zero errors."],
        "decisions": ["Kept the register as YAML rather than a database, so it "
                      "diffs and reviews like the code it describes."],
        # Required from the moment status leaves "not_started"
        # (2026-09-20), so the base fixture carries it for the same
        # reason it carries the four above.
        "signed_off": {"by": "Keith", "date": "2026-09-20"},
    }
    entry.update(overrides)
    return entry


# An override value meaning "omit this key entirely" - a different thing
# from writing it blank, and the validator tells them apart.
_DROP = object()


def _entry(overrides):
    entry = _valid_entry(**{k: v for k, v in overrides.items() if v is not _DROP})
    for key in [k for k, v in overrides.items() if v is _DROP]:
        del entry[key]
    return entry


_UNSTARTED = dict(status="not_started", linked_tests=[], implemented_by=[], evidence=[])


# ---- validate(): one bad field is reported, naming the field ---------
#
# Each row is the overrides applied to an otherwise valid entry, and the
# substrings that must all appear together in one reported error (a row
# with several groups needs each group reported). Row ids are the names
# of the tests the rows replaced.

@pytest.mark.parametrize("overrides, expected", [
    pytest.param({"id": "not-an-id"}, [("id", "not-an-id")],
                 id="test_validate_rejects_a_malformed_id"),
    # 2026-09-19, Keith's own follow-up ask: drop the legacy "REQ-NNN"
    # shape entirely rather than grandfather it - the 22 pre-2026-09-19
    # entries were migrated to the component-coded shape the same day
    # (requirements.yaml's own header comment has the full migration note).
    pytest.param({"id": "REQ-014"}, [("id", "REQ-014")],
                 id="test_validate_rejects_the_old_legacy_bare_id_format"),
    pytest.param({"id": "REQ-FOO-023"}, [("id", "REQ-FOO-023")],
                 id="test_validate_rejects_a_component_code_not_in_the_real_taxonomy"),
    pytest.param({"title": ""}, [("title",)], id="test_validate_rejects_missing_title"),
    pytest.param({"story": "  "}, [("story",)], id="test_validate_rejects_missing_story"),
    pytest.param({"moscow": "urgent"}, [("moscow",)], id="test_validate_rejects_invalid_moscow"),
    pytest.param({"status": "done"}, [("status",)], id="test_validate_rejects_invalid_status"),
    pytest.param({"acceptance_criteria": []}, [("acceptance_criteria",)],
                 id="test_validate_rejects_empty_acceptance_criteria"),
    pytest.param({"status": "built", "linked_tests": []}, [("linked_tests is empty",)],
                 id="test_validate_rejects_a_built_requirement_with_no_linked_tests"),
    pytest.param({"linked_tests": ["tests/test_this_file_does_not_exist.py"]},
                 [("does not resolve",)],
                 id="test_validate_rejects_a_linked_test_that_does_not_exist"),
    pytest.param({"linked_tests": ["tests/test_resupply.py::test_this_does_not_exist"]},
                 [("does not resolve",)],
                 id="test_validate_rejects_a_linked_test_naming_a_real_file_but_fake_function"),
    # Keith, 2026-09-20: "I'm happy to make the source field a required
    # field. As in, it must be there and it must not be white space only or
    # empty." It was optional until then because backfilling provenance for
    # the 22 pre-2026-09-19 entries would have meant guessing; that was
    # answered by going and finding it instead.
    pytest.param({"source": _DROP}, [("source", "required")], id="test_source_is_required"),
    # A blank `source` is someone who started filling it in and stopped -
    # different from omitting the key. Until 2026-09-20 this gate ran on
    # parse_requirements() OUTPUT, which filled every unset optional field
    # with "", so rejecting "" failed all 22 real entries at once; main()
    # now reads the raw YAML, so an absent key never reaches the schema.
    pytest.param({"source": ""}, [("source", "blank")],
                 id="test_source_written_as_an_empty_string_is_rejected"),
    pytest.param({"source": "   "}, [("source", "blank")],
                 id="test_source_written_as_whitespace_only_is_rejected"),
    # Same treatment as `source` - the rule is about any field written with
    # nothing in it, not about one field in particular.
    pytest.param({"date_written": ""}, [("date_written", "blank")],
                 id="test_date_written_written_as_an_empty_string_is_rejected"),
    pytest.param({"date_written": "19/09/2026"}, [("date_written",)],
                 id="test_date_written_rejects_a_non_iso_date"),
    pytest.param({"non_functional_requirements": "CI must never touch live data"},
                 [("non_functional_requirements", "valid list")],
                 id="test_non_functional_requirements_must_be_a_list_not_a_bare_string"),
    pytest.param({"non_functional_requirements": ["", "  "]},
                 [("non_functional_requirements", "non-empty strings")],
                 id="test_non_functional_requirements_rejects_empty_entries"),
    pytest.param({"open_questions": [None]}, [("open_questions",)],
                 id="test_open_questions_must_be_a_list_of_non_empty_strings"),
    pytest.param({"evidence": [123]}, [("evidence",)],
                 id="test_evidence_must_be_a_list_of_non_empty_strings"),
    pytest.param({"dependencies": "REQ-QAC-002"}, [("dependencies", "valid list")],
                 id="test_dependencies_must_be_a_list"),
    pytest.param({"id": "REQ-QAC-001", "dependencies": ["REQ-QAC-999"]},
                 [("dependencies entry 'REQ-QAC-999' does not match any real requirement id",)],
                 id="test_dependencies_referencing_a_nonexistent_id_is_an_error"),
    # implemented_by - Keith's call, 2026-09-20 (plans/tooling.md #18). The
    # `evidence` field sat at zero use a day after it shipped: a field with
    # no forcing function stays empty, so this one is required once a
    # requirement is `built` and CI refuses to pass without it.
    pytest.param({"implemented_by": []}, [("implemented_by",)],
                 id="test_a_built_requirement_must_say_where_it_is_implemented"),
    # Keith: "Python code must have a symbol." A bare path is verified only
    # by Path.exists(), which stays green while the file is gutted; a
    # symbol is AST-verified, so a rename breaks the build.
    pytest.param({"implemented_by": ["qa_tools/common/validate_requirements.py"]}, [("symbol",)],
                 id="test_a_python_entry_must_name_a_symbol_not_just_a_file"),
    pytest.param({"implemented_by": ["qa_tools/common/validate_requirements.py::no_such_function"]},
                 [("no_such_function",)],
                 id="test_a_python_symbol_that_does_not_exist_is_an_error"),
    # Nothing verifies a `::` on a YAML or SQL file, so accepting one would
    # record an unchecked claim in a field whose whole point is the check.
    pytest.param({"implemented_by": ["contract/data-asset.yaml::data_asset_id"]},
                 [("contract/data-asset.yaml",)],
                 id="test_a_symbol_on_a_file_neither_python_nor_front_end_is_rejected"),
    pytest.param({"implemented_by": ["qa_tools/common/nope.py::thing"]}, [("nope.py",)],
                 id="test_an_implemented_by_path_that_does_not_exist_is_an_error"),
    # Keith's call, 2026-09-20: mandate a measured result, no exceptions -
    # not even dark mode, where demanding a real number produced one (all
    # 21 colour tokens redefined under the dark theme) by measuring the
    # real page rather than asserting a toggle flips.
    pytest.param({"evidence": []}, [("evidence",)],
                 id="test_a_built_requirement_must_carry_a_measured_result"),
    # decisions - Keith's idea, 2026-09-20, and what makes deleting plans
    # prose safe rather than merely reversible: the reasoning lives in the
    # requirement. It sits opposite `open_questions` - the forks resolved.
    pytest.param({"decisions": []}, [("decisions",)],
                 id="test_a_built_requirement_must_record_its_decisions"),
    pytest.param({"decisions": ["   "]}, [("decisions",)],
                 id="test_decisions_must_be_a_list_of_non_empty_strings"),
    # The inverse rule, found for real 2026-09-20: REQ-QAC-024 was finished
    # and its status still read `not_started`, because the edit meant to
    # flip it matched nothing. Built-only fields were only DEMANDED once
    # status is "built", so nothing caught it - Keith asking did.
    pytest.param({"status": "not_started"}, [("implemented_by", "but status is")],
                 id="test_a_not_started_requirement_cannot_claim_where_it_is_implemented"),
    pytest.param({"status": "not_started"},
                 [("linked_tests", "but status is"), ("evidence", "but status is")],
                 id="test_a_not_started_requirement_cannot_carry_tests_or_evidence"),
    # The rule is about what the fields claim, not one status value - a
    # requirement half-built cannot have a measured result either.
    pytest.param({"status": "in_progress"}, [("but status is 'in_progress'",)],
                 id="test_in_progress_is_caught_too_not_just_not_started"),
    # Sign-off. Keith's standing instruction, 2026-09-20: a requirement is
    # agreed BEFORE building starts. REQ-DASH-026 sat in the register while
    # work went ahead against one of its criteria backwards, because nothing
    # required anyone to open it. These rows are the control.
    pytest.param({"signed_off": _DROP}, [("signed it off",)],
                 id="test_a_built_requirement_must_be_signed_off"),
    # About building having STARTED, so in_progress is as covered as built.
    pytest.param({**_UNSTARTED, "status": "in_progress", "decisions": [], "signed_off": _DROP},
                 [("signed it off",)],
                 id="test_an_in_progress_requirement_must_be_signed_off"),
    pytest.param({"signed_off": {"by": "Keith"}}, [("date",)],
                 id="test_sign_off_must_carry_both_a_name_and_a_date-no-date"),
    pytest.param({"signed_off": {"date": "2026-09-20"}}, [("by",)],
                 id="test_sign_off_must_carry_both_a_name_and_a_date-no-name"),
    pytest.param({"signed_off": {"by": "Keith", "date": "yesterday"}}, [("date",)],
                 id="test_sign_off_rejects_a_date_that_is_not_a_real_iso_date"),
    pytest.param({"signed_off": {"by": "   ", "date": "2026-09-20"}}, [("by",)],
                 id="test_sign_off_rejects_a_blank_name"),
    # `extra="forbid"` reaches the nested model too - a typo'd
    # `signed_off: {name: ...}` would otherwise look signed with no name.
    pytest.param({"signed_off": {"by": "Keith", "date": "2026-09-20", "note": "looks good"}},
                 [("note",)],
                 id="test_sign_off_rejects_an_undeclared_field"),
])
def test_one_bad_field_is_reported_by_name(overrides, expected):
    errors = validate([_entry(overrides)])
    for substrings in expected:
        assert any(all(s in e for s in substrings) for e in errors), (substrings, errors)


def test_validate_rejects_duplicate_ids():
    errors = validate([_valid_entry(id="REQ-QAC-001"), _valid_entry(id="REQ-QAC-001")])
    assert any("globally unique" in e for e in errors)


# ---- validate(): these shapes are valid ------------------------------
#
# Each row is a list of entries, each given as overrides on a valid one.

@pytest.mark.parametrize("entries", [
    pytest.param([{}], id="test_validate_returns_empty_list_for_a_fully_valid_requirement"),
    # A real 3-4 letter component code in the id's middle segment.
    pytest.param([{"id": "REQ-DASH-023"}], id="test_validate_accepts_a_current_component_coded_id"),
    # Also clears implemented_by and evidence: a not_started requirement may
    # not carry those either, so keeping them would assert something the
    # schema forbids rather than the optionality this row is about.
    pytest.param([_UNSTARTED], id="test_validate_allows_not_started_with_no_linked_tests"),
    pytest.param([{"source": "Keith, voice-dictated batch, 2026-09-19"}],
                 id="test_source_can_be_real_free_text"),
    pytest.param([{"date_written": "2026-09-19"}], id="test_date_written_accepts_a_real_iso_date"),
    pytest.param([{"non_functional_requirements": ["CI must never touch live data"]}],
                 id="test_non_functional_requirements_accepts_real_entries"),
    pytest.param([{"id": "REQ-QAC-001", "dependencies": ["REQ-QAC-002"]}, {"id": "REQ-QAC-002"}],
                 id="test_dependencies_referencing_a_real_id_in_the_same_file_is_fine"),
    pytest.param([{"implemented_by": ["qa_tools/common/check_lifecycle.py::parse_contract_check_metadata",
                                      "qa_tools/common/check_lifecycle.py::CheckMetadata"]}],
                 id="test_a_real_python_symbol_resolves"),
    # No AST parser for the template's inline JS on the Python side, so a
    # bare path is allowed there; the JS symbol form is checked by the Node
    # toolchain instead - tests-js/implemented_by.test.js.
    pytest.param([{"implemented_by": ["dashboard/qa-reporting-dashboard.template.html"]}],
                 id="test_a_front_end_path_may_be_bare"),
    pytest.param([{**_UNSTARTED, "decisions": []}],
                 id="test_decisions_is_optional_until_a_requirement_is_built"),
    # Deliberately excluded from the inverse rule (Keith, 2026-09-20):
    # `decisions` is scoping material and legitimately grows before any
    # code does - REQ-QAC-024 accumulated fourteen while reading
    # `not_started`, and a rule covering it would have failed every push.
    pytest.param([_UNSTARTED], id="test_decisions_may_precede_the_work_and_are_not_flagged"),
    # Signed-off-then-built is the whole shape of the rule, so agreed but
    # not begun is the normal resting state between the two.
    pytest.param([{**_UNSTARTED, "decisions": [], "signed_off": _DROP}],
                 id="test_sign_off_is_optional_while_a_requirement_is_not_started"),
])
def test_a_valid_shape_reports_nothing(entries):
    assert validate([_entry(e) for e in entries]) == []


# ---- _linked_test_exists() / _python_symbol_exists() - against REAL repo files --

@pytest.mark.parametrize("check, args, expected", [
    pytest.param(_linked_test_exists, ("tests/test_resupply.py::test_add_business_days_skips_weekends",),
                 True, id="test_real_module_level_test_function_resolves"),
    pytest.param(_linked_test_exists,
                 ("tests/test_dashboard_e2e.py::TestDarkModeToggle::"
                  "test_toggling_dark_mode_persists_across_a_reload",),
                 True, id="test_real_class_and_method_resolves"),
    pytest.param(_linked_test_exists, ("tests/test_dashboard_e2e.py::TestDarkModeToggle",),
                 True, id="test_bare_class_reference_resolves"),
    pytest.param(_linked_test_exists, ("tests/test_resupply.py",),
                 True, id="test_real_file_with_no_node_id_resolves_on_existence_alone"),
    pytest.param(_linked_test_exists, ("tests-js/supply-history.test.js",),
                 True, id="test_real_js_test_file_resolves_on_existence_alone"),
    pytest.param(_linked_test_exists, ("tests-js/this_does_not_exist.test.js",),
                 False, id="test_missing_js_file_does_not_resolve"),
    pytest.param(_linked_test_exists, ("tests/test_dashboard_e2e.py::TestDarkModeToggle::test_nonexistent",),
                 False, id="test_method_name_that_does_not_exist_in_a_real_class_does_not_resolve"),
    pytest.param(_python_symbol_exists, ("tests/does_not_exist.py", ["test_x"]),
                 False, id="test_python_symbol_exists_returns_false_for_a_missing_file"),
    # Found by the gate itself, 2026-09-20: a module that is purely
    # constants (qa_tools/common/vocab.py) could not satisfy implemented_by
    # at all, because the AST check only looked for functions and classes.
    # A constant is worth pinning for the same reason a function is.
    pytest.param(_python_symbol_exists, ("qa_tools/common/vocab.py", ["COMPONENT_CODES"]),
                 True, id="test_a_module_level_constant_counts_as_a_symbol-present"),
    pytest.param(_python_symbol_exists, ("qa_tools/common/vocab.py", ["NOT_A_REAL_CONST"]),
                 False, id="test_a_module_level_constant_counts_as_a_symbol-absent"),
])
def test_a_reference_resolves_only_when_it_is_real(check, args, expected):
    assert check(*args) is expected


# ---- unmet_criteria (post-build-review #33) and blocked_by (REQ-DOCS-073) --
#
# REQ-PIPE-053 was marked `built` with one dashboard criterion not built,
# and the register's binary built/not_started model had no way to say
# "built except for these". Keith, 2026-09-25: "I'm open to that. Give me
# a proposal", then "ship it" - an optional `unmet_criteria:` list rather
# than a third STATUS, since a status is what the register is indexed and
# filtered by, and every consumer would have to decide what a third meant.
#
# `owner` was already a dependency edge nothing could resolve, so seven
# deferrals pointed at work that had shipped; `blocked_by` is the
# resolvable half.

def _deferral(**blocked_by):
    return _valid_entry(unmet_criteria=[
        {"criterion": "x", "why": "y", "owner": "z", "blocked_by": blocked_by}])


def _naming_itself():
    """Keith, 2026-09-26 - and/or, not either/or. Seventeen deferrals wait on
    a sprint that owns no requirement, so ids alone cannot express them."""
    entry = _deferral(sprints=[11])
    entry["unmet_criteria"][0]["blocked_by"]["requirements"] = [entry["id"]]
    return entry


_VALID = object()
_REFUSED = object()


@pytest.mark.parametrize("entry, expected", [
    pytest.param(lambda: _valid_entry(unmet_criteria=[
        {"criterion": "surface the low-runway warning in the dashboard",
         "why": "the gate half shipped; the dashboard half was never built",
         "owner": "post-build-review #2", "blocked_by": {"unowned": True}}]),
        _VALID, id="test_a_built_requirement_may_declare_unmet_criteria"),
    # A bare list of strings would let "some criteria are unmet" pass as a
    # record, which is what the prose already did.
    pytest.param(lambda: _valid_entry(unmet_criteria=[{"criterion": "x"}]), _REFUSED,
                 id="test_an_unmet_criterion_must_say_which_one_and_why-no-why"),
    pytest.param(lambda: _valid_entry(unmet_criteria=[{"why": "y"}]), _REFUSED,
                 id="test_an_unmet_criterion_must_say_which_one_and_why-no-criterion"),
    pytest.param(lambda: _valid_entry(unmet_criteria=["just a string"]), _REFUSED,
                 id="test_an_unmet_criterion_must_say_which_one_and_why-a-string"),
    # The field exists so a gap has somewhere to go, not somewhere to sit.
    pytest.param(lambda: _valid_entry(unmet_criteria=[{"criterion": "x", "why": "y"}]), _REFUSED,
                 id="test_an_unmet_criterion_must_name_who_owns_it_next"),
    # Nothing is built, so nothing is unmet - allowing it would make the
    # field mean two different things.
    pytest.param(lambda: _valid_entry(**_UNSTARTED, decisions=[], signed_off=None,
                                      unmet_criteria=[{"criterion": "x", "why": "y", "owner": "z",
                                                       "blocked_by": {"unowned": True}}]),
                 _REFUSED, id="test_a_requirement_that_is_not_started_cannot_have_unmet_criteria"),
    # Omitting it is refused rather than defaulted: no blocker is a real
    # state (`unowned`) and must be said out loud.
    pytest.param(lambda: _valid_entry(unmet_criteria=[{"criterion": "x", "why": "y", "owner": "z"}]),
                 _REFUSED, id="test_a_deferral_must_say_what_it_waits_on"),
    # Criterion 7. A typo'd number drops the deferral out of every view
    # that resolves it. The FIRST error must name it.
    pytest.param(lambda: _deferral(sprints=[999]), "999",
                 id="test_a_sprint_that_does_not_exist_is_refused"),
    pytest.param(lambda: _deferral(requirements=["REQ-NOPE-999"]), "REQ-NOPE-999",
                 id="test_a_requirement_that_does_not_exist_is_refused"),
    # Guards the guard: if every sprint number were rejected, the row
    # above would pass while proving nothing.
    pytest.param(lambda: _deferral(sprints=[11]), _VALID, id="test_a_real_sprint_is_accepted"),
    pytest.param(_naming_itself, _VALID, id="test_it_may_name_both_a_sprint_and_a_requirement"),
    # `unowned` says nobody has it; two empty lists say somebody forgot.
    pytest.param(lambda: _deferral(), _REFUSED, id="test_empty_is_refused_rather_than_read_as_unowned"),
    pytest.param(lambda: _deferral(unowned=True, sprints=[11]), _REFUSED,
                 id="test_unowned_cannot_also_name_a_blocker"),
])
def test_an_unmet_criterion_and_its_blocker(entry, expected):
    problems = validate([entry()])
    if expected is _VALID:
        assert problems == []
    elif expected is _REFUSED:
        assert problems
    else:
        assert problems and expected in problems[0], problems


class TestNoHyphenWrapArtifacts:
    """A line break taken AT a hyphen silently inserts a space.

    Both of these files are folded YAML - every scalar uses `>` and
    neither has a single literal `|` block - so a line break inside a
    scalar becomes a SPACE when the file is read. Break a line at an
    existing hyphen and `read-committed-history` is stored as
    `read- committed-history`, which is not what anybody wrote and not
    what any reader wants to see.

    Found 2026-09-27: fifty of them across the register, left behind by
    ad hoc `textwrap.fill()` calls in session scripts, whose default
    `break_on_hyphens=True` does exactly this. Four were introduced the
    same night by my own. There is no committed writer to fix, which is
    why this is a gate rather than a change to a tool.

    NO ALLOWLIST IS NEEDED, and that is the point of checking the RAW
    text rather than the parsed strings. English really does use a
    suspended hyphen - "meta-, ctrl- and shift-click" is correct and
    appears in this register - but that is a hyphen followed by a real
    space on one line, which this pattern cannot match. A hyphen at the
    END of a line followed by a word has no legitimate form here.
    """

    FILES = ("requirements.yaml", "CHANGELOG.yaml")
    #: A word character, a hyphen, a line break, indentation, a word
    #: character. `.`, `)` and `]` are included before the hyphen so a
    #: path or a parenthetical is caught too.
    PATTERN = re.compile(r"([A-Za-z0-9_.)\]])-\n(\s+)([A-Za-z0-9_])")

    @pytest.mark.parametrize("name", FILES)
    def test_no_scalar_is_wrapped_at_a_hyphen(self, name):
        raw = (ROOT / name).read_text()
        found = []
        for m in self.PATTERN.finditer(raw):
            line = raw[: m.start()].count("\n") + 1
            found.append(f"{name}:{line} ...{m.group(1)}- / {m.group(3)}...")
        assert not found, (
            "a line is wrapped at a hyphen, so the folded text will carry a "
            "space that nobody wrote - join the token onto one line:\n  "
            + "\n  ".join(found))

    @pytest.mark.parametrize("name", FILES)
    def test_the_file_really_is_folded_throughout(self, name):
        """Guards the guard. The test above is only sound while every
        scalar is folded - in a literal `|` block a line break is
        PRESERVED, so joining those lines would change the content
        rather than repair it. If a literal block is ever added, this
        fails and the rule above needs narrowing to exclude it."""
        raw = (ROOT / name).read_text()
        literal = [i + 1 for i, line in enumerate(raw.split("\n"))
                   if re.search(r":\s*\|[-+]?\s*$", line)]
        assert not literal, (
            f"{name} now has a literal block at line(s) {literal} - "
            f"test_no_scalar_is_wrapped_at_a_hyphen assumes folded scalars "
            f"throughout and must be narrowed to skip it")


class TestARetiredRequirement:
    """REQ-DOCS-143: a requirement a later one replaced stays in the
    register as history, saying when, who decided and what replaced it."""

    _RETIRED = {"date": "2026-10-04", "by": "Keith", "replaced_by": ["REQ-QAC-002"]}

    def _pair(self, **overrides):
        return [_valid_entry(**overrides), _valid_entry(id="REQ-QAC-002")]

    def test_a_retired_requirement_with_its_three_facts_is_valid(self):
        assert validate(self._pair(status="retired", retired=dict(self._RETIRED))) == []

    def test_retired_without_saying_when_who_and_what_replaced_it_is_refused(self):
        errors = validate(self._pair(status="retired"))
        assert any("no `retired:` block" in e for e in errors), errors

    @pytest.mark.parametrize("missing", ["date", "by", "replaced_by"])
    def test_each_of_the_three_facts_is_required(self, missing):
        retired = {k: v for k, v in self._RETIRED.items() if k != missing}
        assert validate(self._pair(status="retired", retired=retired)), missing

    def test_a_retired_block_on_a_live_requirement_is_refused(self):
        errors = validate(self._pair(retired=dict(self._RETIRED)))
        assert any("has a `retired:` block but status is 'built'" in e for e in errors), errors

    def test_its_record_of_code_since_removed_is_kept_as_history(self):
        """Found retiring REQ-PIPE-063 and REQ-PIPE-077 (2026-10-04): the
        whole point of a retirement is usually that its code was REMOVED,
        and a retired requirement "keeps whatever it carried as history"
        (REQ-DOCS-143's own decision) - so demanding its implemented_by and
        linked_tests still resolve would force the history to be deleted."""
        reqs = self._pair(status="retired", retired=dict(self._RETIRED),
                          implemented_by=["qa_tools/common/assignment.py::gone_long_ago"],
                          linked_tests=["tests/test_never_existed.py"])
        assert validate(reqs) == []

    def test_a_live_requirement_still_needs_its_code_to_exist(self):
        """The control: only a RETIRED record is history."""
        reqs = self._pair(implemented_by=["qa_tools/common/assignment.py::gone_long_ago"])
        assert any("gone_long_ago" in e for e in validate(reqs))

    def test_the_successor_must_exist(self):
        errors = validate([_valid_entry(status="retired",
                                         retired={**self._RETIRED, "replaced_by": ["REQ-QAC-099"]})])
        assert any("REQ-QAC-099" in e for e in errors), errors

    def test_depending_on_a_retired_requirement_is_refused(self):
        reqs = self._pair(status="retired", retired=dict(self._RETIRED))
        reqs[1]["dependencies"] = ["REQ-QAC-001"]
        errors = validate(reqs)
        assert any("depends on REQ-QAC-001, which is retired" in e for e in errors), errors

    def test_a_never_signed_draft_can_be_retired(self):
        assert validate(self._pair(status="retired", retired=dict(self._RETIRED),
                                   signed_off=None, linked_tests=[], implemented_by=[],
                                   evidence=[])) == []


class TestARetiredCriterion:
    """REQ-DOCS-143 criterion 3: one criterion retires, the rest stands."""

    def test_a_retired_criterion_is_valid_by_position(self):
        reqs = [_valid_entry(acceptance_criteria=["One.", "Two."],
                             retired_criteria=[{"criterion": 2, "date": "2026-10-04",
                                                "by": "Keith", "replaced_by": ["REQ-QAC-002"]}]),
                _valid_entry(id="REQ-QAC-002")]
        assert validate(reqs) == []

    def test_a_position_past_the_last_criterion_is_refused(self):
        reqs = [_valid_entry(retired_criteria=[{"criterion": 5, "date": "2026-10-04",
                                                "by": "Keith", "replaced_by": ["REQ-QAC-002"]}]),
                _valid_entry(id="REQ-QAC-002")]
        assert any("only 1" in e for e in validate(reqs))
