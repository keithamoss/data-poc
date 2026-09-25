"""Tests for dashboard/requirements_yaml.py - the requirements.yaml
parser (item 75, plans/qa-pipeline.md). Fixture-based (a small
hand-written YAML string per test), not the real committed
requirements.yaml - that file's own content changes over time and
isn't what this module's own correctness depends on.

Rewritten 2026-09-20 (REQ-DOCS-029). This module used to carry its own
`_DEFAULTS` dict and fill in whatever a file left out, so most of these
tests asserted what a half-written entry defaulted TO. It now validates
against the one declared schema in qa_tools/common/schemas.py and
raises, by Keith's own call - so they assert that instead. The heavier
cross-reference checks (AST-verified symbols, dependency resolution)
remain qa_tools/common/validate_requirements.py's job, tested in
tests/test_validate_requirements.py."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from dashboard.requirements_yaml import parse_requirements

_FULL = """
requirements:
  - id: REQ-DASH-001
    title: A real feature
    story: As a user, I want X, so that Y.
    moscow: must
    status: built
    source: A real person, on a real date.
    acceptance_criteria:
      - It does the thing.
    linked_tests:
      - tests/test_x.py
"""


def _write(tmp_path, content: str):
    path = tmp_path / "requirements.yaml"
    path.write_text(content)
    return path


def test_parses_a_full_entry(tmp_path):
    reqs = parse_requirements(_write(tmp_path, _FULL))
    assert len(reqs) == 1
    assert reqs[0] == {
        "id": "REQ-DASH-001", "title": "A real feature",
        "story": "As a user, I want X, so that Y.",
        "moscow": "must", "status": "built",
        "source": "A real person, on a real date.",
        "acceptance_criteria": ["It does the thing."], "linked_tests": ["tests/test_x.py"],
        "date_written": "", "non_functional_requirements": [], "dependencies": [],
        "open_questions": [], "evidence": [], "implemented_by": [],
        "decisions": [], "signed_off": None,
        # post-build-review #33. This pins the WHOLE shape on purpose,
        # so a new field has to be added here to pass - which is how it
        # should behave: the parser's output is what the dashboard
        # renders, and a field appearing in it silently is one nobody
        # decided to show.
        "unmet_criteria": [],
    }


def test_preserves_file_order(tmp_path):
    path = _write(tmp_path, _FULL + _FULL.split("requirements:")[1].replace(
        "REQ-DASH-001", "REQ-DASH-002"))
    ids = [r["id"] for r in parse_requirements(path)]
    assert ids == ["REQ-DASH-001", "REQ-DASH-002"], \
        "entries must preserve the file's own top-to-bottom order, never re-sorted"


def test_an_entry_missing_a_required_field_raises(tmp_path):
    """The behaviour change, 2026-09-20. This used to default `story` to
    "" and render a requirement with no story - which a reader cannot
    tell apart from a requirement that genuinely has nothing to say."""
    path = _write(tmp_path, """
requirements:
  - id: REQ-DASH-001
    title: Bare minimum
""")
    with pytest.raises(ValidationError) as exc:
        parse_requirements(path)
    assert "story" in str(exc.value)


def test_a_misspelt_field_name_raises_rather_than_being_ignored(tmp_path):
    """`extra="forbid"`. A typo'd key in a hand-authored file would
    otherwise sit there looking filled in forever - the same silent
    shape as the duplicate mapping key that prompted this work."""
    path = _write(tmp_path, _FULL + "    evidense:\n      - A typo.\n")
    with pytest.raises(ValidationError) as exc:
        parse_requirements(path)
    assert "evidense" in str(exc.value)


def test_a_present_but_blank_optional_field_raises(tmp_path):
    """Keith's call, 2026-09-20. A blank value is someone who started
    filling it in and stopped; it is not the same as omitting the key,
    and the file should be able to say so.

    Uses `date_written` rather than `source`, which became required
    later the same day - the rule being tested here is about OPTIONAL
    fields, where absent is legal and blank still is not."""
    path = _write(tmp_path, _FULL + '    date_written: "   "\n')
    with pytest.raises(ValidationError) as exc:
        parse_requirements(path)
    assert "date_written" in str(exc.value)


def test_omitted_optional_fields_default(tmp_path):
    """Absent stays legal - only blank-when-written is rejected.

    `source` is not among them any more: it became required the same
    day, since it is the only field nobody can reconstruct later."""
    req = parse_requirements(_write(tmp_path, _FULL))[0]
    assert req["date_written"] == ""
    assert req["open_questions"] == []


def test_parses_the_optional_fields_when_present(tmp_path):
    path = _write(tmp_path, """
requirements:
  - id: REQ-DASH-023
    title: A real feature
    story: As a user, I want X, so that Y.
    moscow: must
    status: not_started
    acceptance_criteria:
      - It does the thing.
    date_written: "2026-09-19"
    source: Keith, voice-dictated batch, 2026-09-19
    non_functional_requirements:
      - CI must never touch live data
    dependencies:
      - REQ-DASH-001
    open_questions:
      - Should this apply to Child Protection too?
    evidence:
      - Playwright walkthrough 2026-09-20, confirmed it renders.
""")
    req = parse_requirements(path)[0]
    assert req["date_written"] == "2026-09-19"
    assert req["source"] == "Keith, voice-dictated batch, 2026-09-19"
    assert req["non_functional_requirements"] == ["CI must never touch live data"]
    assert req["dependencies"] == ["REQ-DASH-001"]
    assert req["open_questions"] == ["Should this apply to Child Protection too?"]
    assert req["evidence"] == ["Playwright walkthrough 2026-09-20, confirmed it renders."]


def test_folded_scalar_story_is_stripped_of_trailing_newline(tmp_path):
    """requirements.yaml authors `story` with YAML's `>` folded scalar
    for readability in the source file, which leaves a trailing newline
    the dashboard would otherwise carry through."""
    path = _write(tmp_path, """
requirements:
  - id: REQ-DASH-001
    title: Folded story
    story: >
      As a user, I want X,
      so that Y.
    moscow: must
    status: not_started
    source: A real person, on a real date.
    acceptance_criteria:
      - It does the thing.
""")
    req = parse_requirements(path)[0]
    assert req["story"] == "As a user, I want X, so that Y."
    assert not req["story"].endswith("\n")


def test_empty_requirements_list(tmp_path):
    path = _write(tmp_path, "requirements: []\n")
    assert parse_requirements(path) == []


def test_missing_requirements_key_returns_empty_list(tmp_path):
    path = _write(tmp_path, "# nothing here yet\n")
    assert parse_requirements(path) == []
