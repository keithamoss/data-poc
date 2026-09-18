"""Tests for dashboard/changelog_md.py - the CHANGELOG.md parser (item
62, plans/qa-pipeline.md). Fixture-based (a small hand-written markdown
string per test), not the real committed CHANGELOG.md - that file's
own content changes over time and isn't what this module's own
correctness depends on."""
from __future__ import annotations

from dashboard.changelog_md import parse_changelog


def _write(tmp_path, content: str):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(content)
    return path


def test_parses_a_single_entry_with_one_section(tmp_path):
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- First feature
- Second feature
""")
    result = parse_changelog(path)
    assert result["intro"] == []
    assert len(result["entries"]) == 1
    entry = result["entries"][0]
    assert entry["date"] == "2026-01-01"
    assert entry["sections"] == [{"category": "Added", "items": [
        {"time": None, "text": "First feature"},
        {"time": None, "text": "Second feature"},
    ]}]


def test_parses_an_item_leading_timestamp_and_strips_it_from_the_text(tmp_path):
    """Real convention since the 2026-09-18 timestamp retrofit
    (plans/qa-pipeline.md): `- **<time>** — <text>`, real AWST git-commit
    time. Optional - see the next test for the no-timestamp case, which
    must keep working for any entry that predates the retrofit."""
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- **6:12am** — First feature
- **12:24pm** — Second feature
""")
    items = parse_changelog(path)["entries"][0]["sections"][0]["items"]
    assert items == [
        {"time": "6:12am", "text": "First feature"},
        {"time": "12:24pm", "text": "Second feature"},
    ]


def test_an_item_with_no_leading_timestamp_still_parses_with_a_none_time(tmp_path):
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- No timestamp on this one
""")
    items = parse_changelog(path)["entries"][0]["sections"][0]["items"]
    assert items == [{"time": None, "text": "No timestamp on this one"}]


def test_parses_multiple_entries_in_file_order(tmp_path):
    path = _write(tmp_path, """# Changelog

## 2026-01-02

### Added
- Newer thing

## 2026-01-01

### Added
- Older thing
""")
    result = parse_changelog(path)
    dates = [e["date"] for e in result["entries"]]
    assert dates == ["2026-01-02", "2026-01-01"], \
        "entries must preserve the file's own top-to-bottom order, never re-sorted"


def test_parses_multiple_sections_within_one_entry(tmp_path):
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- A new thing

### Fixed
- A bug
""")
    entry = parse_changelog(path)["entries"][0]
    assert [s["category"] for s in entry["sections"]] == ["Added", "Fixed"]
    assert entry["sections"][0]["items"] == [{"time": None, "text": "A new thing"}]
    assert entry["sections"][1]["items"] == [{"time": None, "text": "A bug"}]


def test_joins_a_soft_wrapped_bullet_across_multiple_lines(tmp_path):
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Fixed
- A long entry that wraps across
  multiple lines in the markdown
  source, same paragraph.
- A second, unrelated entry
""")
    items = parse_changelog(path)["entries"][0]["sections"][0]["items"]
    assert items == [
        {"time": None, "text": "A long entry that wraps across multiple lines in the markdown source, same paragraph."},
        {"time": None, "text": "A second, unrelated entry"},
    ]


def test_joins_a_soft_wrapped_bullet_that_starts_with_a_timestamp(tmp_path):
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Fixed
- **6:12am** — A long entry that wraps across
  multiple lines in the markdown source.
""")
    items = parse_changelog(path)["entries"][0]["sections"][0]["items"]
    assert items == [
        {"time": "6:12am", "text": "A long entry that wraps across multiple lines in the markdown source."},
    ]


def test_captures_intro_paragraphs_before_the_first_heading(tmp_path):
    path = _write(tmp_path, """# Changelog

First intro paragraph, wrapped
across two lines.

Second intro paragraph.

## 2026-01-01

### Added
- Something
""")
    result = parse_changelog(path)
    assert result["intro"] == [
        "First intro paragraph, wrapped across two lines.",
        "Second intro paragraph.",
    ]


def test_no_intro_when_the_first_heading_is_the_very_first_content(tmp_path):
    path = _write(tmp_path, """# Changelog
## 2026-01-01

### Added
- Something
""")
    assert parse_changelog(path)["intro"] == []


def test_empty_file_after_title_produces_no_entries(tmp_path):
    path = _write(tmp_path, "# Changelog\n")
    result = parse_changelog(path)
    assert result == {"intro": [], "entries": []}
