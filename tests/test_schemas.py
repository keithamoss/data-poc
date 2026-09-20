"""Tests for qa_tools/common/schemas.py - the declared schemas
(REQ-DOCS-029).

Keith's challenge, 2026-09-20: "can't we use a YAML schema validation
library and give it a spec rather than writing these hacky scripts?"
He was right about the half of the validators that is genuinely schema
work. These cover what moved, and - just as importantly - assert the
one new guarantee the move bought, plus the boundary where a schema
stops being able to help.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from qa_tools.common.schemas import Changelog, Requirement, format_error
from qa_tools.common.vocab import (
    CHANGELOG_CATEGORIES,
    COMPONENT_CODES,
    MOSCOW,
    REQUIREMENT_STATUSES,
)

_REQ = dict(id="REQ-QAC-001", title="T", story="S", moscow="must",
            status="not_started", acceptance_criteria=["A real criterion."])
_ITEM = {"headline": "H", "description": "D", "components": ["Dashboard UI"]}
_FEED = {"releases": [{"date": "2026-09-20", "summary": "A day.",
                       "changes": [{"category": "Fixed", "items": [_ITEM]}]}]}


def test_a_valid_requirement_parses():
    assert Requirement(**_REQ).id == "REQ-QAC-001"


def test_a_valid_changelog_parses():
    assert len(Changelog(**_FEED).releases) == 1


def test_an_unknown_field_is_rejected():
    """The guarantee this move BOUGHT, and the reason it is worth having
    beyond tidiness. A typo'd field name - `priorty` for `priority` -
    used to be accepted and silently ignored forever, which is the same
    shape as the duplicate key that started this work: content that
    looks authored but reaches nothing."""
    with pytest.raises(ValidationError) as e:
        Requirement(**_REQ, priorty="high")
    assert "priorty" in str(e.value)


@pytest.mark.parametrize("bad", [
    {"id": "REQ-999"},                       # no component code
    {"id": "REQ-NOPE-001"},                  # unknown component code
    {"moscow": "maybe"},
    {"status": "shipped"},
    {"acceptance_criteria": []},
    {"acceptance_criteria": ["  "]},
    {"date_written": "20 Sept 2026"},
    {"non_functional_requirements": "a bare string"},
])
def test_a_malformed_requirement_field_is_rejected(bad):
    with pytest.raises(ValidationError):
        Requirement(**{**_REQ, **bad})


@pytest.mark.parametrize("mutate", [
    lambda f: f["releases"][0].pop("summary"),
    lambda f: f["releases"][0].update(date="20 Sept"),
    lambda f: f["releases"][0]["changes"][0].update(category="Tweaks"),
    lambda f: f["releases"][0]["changes"][0]["items"][0].update(components=["Dashboard"]),
    lambda f: f["releases"][0]["changes"][0]["items"][0].update(components=[]),
    lambda f: f["releases"][0]["changes"][0]["items"][0].pop("headline"),
])
def test_a_malformed_changelog_is_rejected(mutate):
    import copy
    feed = copy.deepcopy(_FEED)
    mutate(feed)
    with pytest.raises(ValidationError):
        Changelog(**feed)


def test_missing_when_built_names_every_absent_field():
    """Required-once-built is a rule about the whole record, and it
    reports ALL four rather than stopping at the first so an author
    fixes them in one pass."""
    r = Requirement(**{**_REQ, "status": "built"})
    assert r.missing_when_built() == ["linked_tests", "implemented_by",
                                       "evidence", "decisions"]
    assert Requirement(**_REQ).missing_when_built() == []


def test_the_error_formatter_names_the_offending_value():
    """Pydantic says what a field SHOULD be but not what was written -
    "Input should be 'Data generation', ..." leaves you to go and find
    it. The validators this replaced always named it, so the formatter
    restores that rather than accepting a quieter error as the price of
    using a schema."""
    try:
        Changelog(**{"releases": [{"date": "2026-09-20", "summary": "S", "changes": [
            {"category": "Tweaks", "items": [_ITEM]}]}]})
    except ValidationError as e:
        line = format_error(e.errors()[0], "somewhere")
        assert "got 'Tweaks'" in line, line
    else:
        pytest.fail("a bad category should not validate")


def test_a_missing_field_error_does_not_claim_a_value():
    """`got ''` on a field that was never written would be nonsense."""
    try:
        Requirement(**{k: v for k, v in _REQ.items() if k != "title"})
    except ValidationError as e:
        line = format_error(e.errors()[0], "somewhere")
        assert "got" not in line, line


def test_the_vocabularies_have_one_home():
    """Extracted so the schema and the validators can share them without
    importing each other. validate_requirements re-exports the component
    codes under their old private name, because the taxonomy consistency
    test imports them from there."""
    from qa_tools.common.validate_requirements import _COMPONENT_CODES
    assert _COMPONENT_CODES is COMPONENT_CODES
    assert len(COMPONENT_CODES) == 7
    assert MOSCOW == ("must", "should", "could", "wont")
    assert REQUIREMENT_STATUSES == ("not_started", "in_progress", "built")
    assert CHANGELOG_CATEGORIES == ("New", "Improved", "Fixed")
