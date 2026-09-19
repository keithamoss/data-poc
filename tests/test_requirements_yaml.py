"""Tests for dashboard/requirements_yaml.py - the requirements.yaml
parser (item 75, plans/qa-pipeline.md). Fixture-based (a small
hand-written YAML string per test), not the real committed
requirements.yaml - that file's own content changes over time and
isn't what this module's own correctness depends on (its schema
enforcement is qa_tools/common/validate_requirements.py's own job,
tested separately in tests/test_validate_requirements.py)."""
from __future__ import annotations

from dashboard.requirements_yaml import parse_requirements


def _write(tmp_path, content: str):
    path = tmp_path / "requirements.yaml"
    path.write_text(content)
    return path


def test_parses_a_full_entry(tmp_path):
    path = _write(tmp_path, """
requirements:
  - id: REQ-001
    title: A real feature
    story: As a user, I want X, so that Y.
    moscow: must
    status: built
    acceptance_criteria:
      - It does the thing.
    linked_tests:
      - tests/test_x.py
""")
    reqs = parse_requirements(path)
    assert len(reqs) == 1
    assert reqs[0] == {
        "id": "REQ-001", "title": "A real feature", "story": "As a user, I want X, so that Y.",
        "moscow": "must", "status": "built",
        "acceptance_criteria": ["It does the thing."], "linked_tests": ["tests/test_x.py"],
        "date_written": "", "source": "", "non_functional_requirements": [], "dependencies": [],
        "open_questions": [], "evidence": [],
    }


def test_preserves_file_order(tmp_path):
    path = _write(tmp_path, """
requirements:
  - id: REQ-002
    title: Second in the file
  - id: REQ-001
    title: First in the file
""")
    ids = [r["id"] for r in parse_requirements(path)]
    assert ids == ["REQ-002", "REQ-001"], \
        "entries must preserve the file's own top-to-bottom order, never re-sorted"


def test_missing_optional_fields_default_rather_than_error(tmp_path):
    path = _write(tmp_path, """
requirements:
  - id: REQ-001
    title: Bare minimum
""")
    req = parse_requirements(path)[0]
    assert req["moscow"] == "could"
    assert req["status"] == "not_started"
    assert req["acceptance_criteria"] == []
    assert req["linked_tests"] == []
    assert req["story"] == ""
    assert req["date_written"] == ""
    assert req["source"] == ""
    assert req["non_functional_requirements"] == []
    assert req["dependencies"] == []
    assert req["open_questions"] == []
    assert req["evidence"] == []


def test_parses_the_6_optional_fields_when_present(tmp_path):
    path = _write(tmp_path, """
requirements:
  - id: REQ-DASH-023
    title: A real feature
    date_written: "2026-09-19"
    source: Keith, voice-dictated batch, 2026-09-19
    non_functional_requirements:
      - CI must never touch live data
    dependencies:
      - REQ-002
    open_questions:
      - Should this apply to Child Protection too?
    evidence:
      - Playwright walkthrough 2026-09-20, confirmed it renders.
""")
    req = parse_requirements(path)[0]
    assert req["date_written"] == "2026-09-19"
    assert req["source"] == "Keith, voice-dictated batch, 2026-09-19"
    assert req["non_functional_requirements"] == ["CI must never touch live data"]
    assert req["dependencies"] == ["REQ-002"]
    assert req["open_questions"] == ["Should this apply to Child Protection too?"]
    assert req["evidence"] == ["Playwright walkthrough 2026-09-20, confirmed it renders."]


def test_folded_scalar_story_is_stripped_of_trailing_newline(tmp_path):
    path = _write(tmp_path, """
requirements:
  - id: REQ-001
    title: Folded story
    story: >
      As a user, I want X,
      so that Y.
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
