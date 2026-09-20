"""Tests for the "What's New" feed - dashboard/changelog_yaml.py and
qa_tools/common/validate_changelog.py (2026-09-20).

Replaces tests/test_changelog_md.py, which tested a line-by-line
Markdown parser that no longer exists. The file it parsed had become an
engineering log; the rewrite made it a reader-facing feed in structured
YAML, modelled on keithamoss/mapa's own in-app What's New page.
"""
from __future__ import annotations

import textwrap

import pytest

import yaml

from dashboard.changelog_yaml import parse_changelog
from qa_tools.common.validate_changelog import (
    CATEGORIES,
    CHANGELOG_YAML,
    VALID_COMPONENTS,
    validate,
)


def _raw(path):
    """validate() takes the RAW parsed YAML, not parse_changelog()'s
    output - deliberately, since that parser fills in defaults for
    missing fields and would hide exactly the absences being tested."""
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _write(tmp_path, body: str):
    path = tmp_path / "CHANGELOG.yaml"
    path.write_text(textwrap.dedent(body))
    return path


_ONE_DAY = """
    intro: >
      Some intro prose.
    releases:
      - date: "2026-09-20"
        summary: >
          One sentence for the day.
        changes:
          - category: Improved
            items:
              - headline: Checks know where they belong
                components: ["QA checks & contract"]
                description: >
                  A rule about a carer's identifier now appears under
                  that identifier.
"""


# ---- parsing ---------------------------------------------------------

def test_parses_a_day_into_the_shape_the_dashboard_renders(tmp_path):
    feed = parse_changelog(_write(tmp_path, _ONE_DAY))
    assert feed["intro"] == ["Some intro prose."]
    (entry,) = feed["entries"]
    assert entry["date"] == "2026-09-20"
    assert entry["summary"] == "One sentence for the day."
    (section,) = entry["sections"]
    assert section["category"] == "Improved"
    (item,) = section["items"]
    assert item["headline"] == "Checks know where they belong"
    assert item["components"] == ["QA checks & contract"]
    assert "carer's identifier" in item["text"]
    assert item["time"] is None


def test_the_files_own_order_is_never_re_sorted(tmp_path):
    """Authored newest-first, which IS the intended reading order - the
    same convention requirements_yaml.py follows."""
    feed = parse_changelog(_write(tmp_path, """
        releases:
          - date: "2026-09-20"
            summary: Later.
            changes: []
          - date: "2026-09-18"
            summary: Earlier.
            changes: []
    """))
    assert [e["date"] for e in feed["entries"]] == ["2026-09-20", "2026-09-18"]


def test_a_missing_optional_field_defaults_rather_than_raising(tmp_path):
    """This module renders whatever is really there; enforcing the
    schema is validate_changelog.py's job, as its own CI gate."""
    feed = parse_changelog(_write(tmp_path, 'releases:\n  - date: "2026-09-20"\n'))
    (entry,) = feed["entries"]
    assert entry["summary"] == ""
    assert entry["sections"] == []


# ---- validation ------------------------------------------------------

def test_the_real_committed_changelog_is_valid():
    assert validate(_raw(CHANGELOG_YAML)) == []


def test_an_unknown_component_is_rejected(tmp_path):
    """Keith's own ask - "the components should be CI checked as well,
    obviously".

    This is the failure that would otherwise be silent: "Dashboard"
    instead of "Dashboard UI" fails no other check in the repo, and
    simply renders as a tag matching no filter and grouping with
    nothing."""
    feed = _raw(_write(tmp_path, _ONE_DAY.replace(
        '["QA checks & contract"]', '["Dashboard"]')))
    errors = validate(feed)
    assert any("got 'Dashboard'" in e for e in errors), errors


def test_components_come_from_the_same_source_as_requirement_ids():
    """Not a list copied into this module - adding a component to the
    taxonomy must not leave the changelog gate behind."""
    from qa_tools.common.validate_requirements import _COMPONENT_CODES
    assert VALID_COMPONENTS == frozenset(_COMPONENT_CODES.values())


@pytest.mark.parametrize("body, expected", [
    pytest.param("""
        releases:
          - date: "2026-09-20"
            changes:
              - category: Fixed
                items:
                  - headline: A thing
                    components: ["Dashboard UI"]
                    description: It works now.
    """, "summary", id="no-summary"),
    pytest.param("""
        releases:
          - date: "2026-09-20"
            summary: A day.
            changes:
              - category: Fixed
                items:
                  - components: ["Dashboard UI"]
                    description: It works now.
    """, "headline", id="no-headline"),
    pytest.param("""
        releases:
          - date: "2026-09-20"
            summary: A day.
            changes:
              - category: Fixed
                items:
                  - headline: A thing
                    description: It works now.
    """, "components", id="no-components"),
    pytest.param("""
        releases:
          - date: "20th September"
            summary: A day.
            changes:
              - category: Fixed
                items:
                  - headline: A thing
                    components: ["Dashboard UI"]
                    description: It works now.
    """, "date", id="bad-date"),
])
def test_a_missing_or_malformed_required_field_is_reported(tmp_path, body, expected):
    """Written as whole documents rather than by deleting a line from a
    good one - removing a line from YAML leaves broken indentation, so
    the first version of this test was failing on a parse error and
    proving nothing about validation."""
    errors = validate(_raw(_write(tmp_path, body)))
    assert any(expected in e for e in errors), errors


def test_an_unknown_category_is_rejected(tmp_path):
    """A closed vocabulary, because an open one drifts into six
    near-synonyms within a month."""
    feed = _raw(_write(tmp_path, _ONE_DAY.replace(
        "category: Improved", "category: Tweaks")))
    assert any("got 'Tweaks'" in e for e in validate(feed)), validate(feed)
    assert all(c in ("New", "Improved", "Fixed") for c in CATEGORIES)


def test_the_same_day_appearing_twice_is_rejected(tmp_path):
    """Two blocks for one date means a reader sees the day twice and
    cannot tell which is authoritative."""
    feed = _raw(_write(tmp_path, _ONE_DAY + _ONE_DAY.split("releases:")[1]))
    assert any("appears 2 times" in e for e in validate(feed))


def test_an_empty_feed_is_rejected(tmp_path):
    errors = validate(_raw(_write(tmp_path, "releases: []\n")))
    assert any("releases" in e and "at least 1 item" in e for e in errors), errors
