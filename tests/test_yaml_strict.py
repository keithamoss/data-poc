"""Tests for qa_tools/common/yaml_strict.py - the duplicate-key guard.

Encodes a real incident, not a hypothetical. On 2026-09-20
requirements.yaml's REQ-QAC-023 ended up with two `decisions:` blocks.
PyYAML kept the last and silently discarded the first, losing five real
decisions - including a rejected design alternative that had been moved
there deliberately BEFORE the plans prose describing it was deleted, on
the reasoning that the requirement would carry it.

Nothing in the Python stack noticed: safe_load accepted it, the
check-yaml pre-commit hook uses safe_load too, both validators passed,
and the whole test suite passed. It surfaced only because the JavaScript
`yaml` package refuses duplicate keys, failing one CI job while every
local check stayed green.
"""
from __future__ import annotations

import textwrap

import pytest

from qa_tools.common.yaml_strict import find_duplicate_keys


def _write(tmp_path, body: str):
    path = tmp_path / "doc.yaml"
    path.write_text(textwrap.dedent(body))
    return path


def test_a_clean_file_reports_nothing(tmp_path):
    assert find_duplicate_keys(_write(tmp_path, """
        items:
          - id: one
            note: fine
    """)) == []


def test_a_duplicate_key_is_found_and_both_lines_named(tmp_path):
    """Both line numbers, because the useful question when fixing one is
    'what was in the block I cannot see any more' - which needs where it
    started, not just where the clash was detected."""
    errors = find_duplicate_keys(_write(tmp_path, """
        items:
          - id: one
            decisions:
              - first block
            note: something in between
            decisions:
              - second block
    """))
    assert len(errors) == 1
    assert "decisions" in errors[0]
    assert "line 7" in errors[0] and "line 4" in errors[0], errors[0]


def test_it_finds_duplicates_nested_inside_sequences(tmp_path):
    """The real one was inside a list of requirements, so walking only
    the top-level mapping would have missed it entirely."""
    assert len(find_duplicate_keys(_write(tmp_path, """
        outer:
          - inner:
              a: 1
              a: 2
    """))) == 1


def test_an_empty_document_is_not_an_error(tmp_path):
    assert find_duplicate_keys(_write(tmp_path, "")) == []


@pytest.mark.parametrize("path", [
    "requirements.yaml",
    "CHANGELOG.yaml",
    "contract/data-asset.yaml",
    "contract/bdm-birth-registrations-contract.yaml",
    "contract/child-protection-contract.yaml",
])
def test_every_hand_authored_yaml_file_in_this_repo_is_clean(path):
    """The real files, not fixtures - this is the assertion that would
    have caught the incident."""
    assert find_duplicate_keys(path) == []
