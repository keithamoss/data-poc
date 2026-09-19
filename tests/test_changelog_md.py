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
        {"time": None, "headline": None, "components": [], "text": "First feature"},
        {"time": None, "headline": None, "components": [], "text": "Second feature"},
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
        {"time": "6:12am", "headline": None, "components": [], "text": "First feature"},
        {"time": "12:24pm", "headline": None, "components": [], "text": "Second feature"},
    ]


def test_an_item_with_no_leading_timestamp_still_parses_with_a_none_time(tmp_path):
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- No timestamp on this one
""")
    items = parse_changelog(path)["entries"][0]["sections"][0]["items"]
    assert items == [{"time": None, "headline": None, "components": [], "text": "No timestamp on this one"}]


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
    assert entry["sections"][0]["items"] == [{"time": None, "headline": None, "components": [], "text": "A new thing"}]
    assert entry["sections"][1]["items"] == [{"time": None, "headline": None, "components": [], "text": "A bug"}]


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
        {"time": None, "headline": None, "components": [],
         "text": "A long entry that wraps across multiple lines in the markdown source, same paragraph."},
        {"time": None, "headline": None, "components": [], "text": "A second, unrelated entry"},
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
        {"time": "6:12am", "headline": None, "components": [],
         "text": "A long entry that wraps across multiple lines in the markdown source."},
    ]


def test_parses_a_headline_and_single_component_after_the_timestamp(tmp_path):
    """The 2026-09-18 evening headline/component retrofit (plans/qa-
    pipeline.md, Keith's ask for a bold label, iconography, and the
    component(s) shown alongside each release note)."""
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- **6:12am** — **Leaderboard Streaks** **[Dashboard UI]** A real leaderboard.
""")
    items = parse_changelog(path)["entries"][0]["sections"][0]["items"]
    assert items == [{
        "time": "6:12am", "headline": "Leaderboard Streaks",
        "components": ["Dashboard UI"], "text": "A real leaderboard.",
    }]


def test_parses_multiple_components_on_one_item(tmp_path):
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- **Cross-Cutting Fix** **[QA checks & contract]** **[Pipeline & publishing]** Two things at once.
""")
    items = parse_changelog(path)["entries"][0]["sections"][0]["items"]
    assert items == [{
        "time": None, "headline": "Cross-Cutting Fix",
        "components": ["QA checks & contract", "Pipeline & publishing"],
        "text": "Two things at once.",
    }]


def test_headline_with_no_component_tag_still_parses(tmp_path):
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- **Just A Headline** No component here.
""")
    items = parse_changelog(path)["entries"][0]["sections"][0]["items"]
    assert items == [{
        "time": None, "headline": "Just A Headline",
        "components": [], "text": "No component here.",
    }]


def test_a_bracket_tag_with_no_preceding_headline_is_not_mistaken_for_one(tmp_path):
    """A `**[Component]**` tag never gets swallowed as the headline itself
    - the headline regex explicitly excludes a leading `[`, so an item
    that (unusually) opens straight with a component tag and no headline
    still parses that tag as a real component, not bogus headline text."""
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- **[Docs & process]** No headline on this one.
""")
    items = parse_changelog(path)["entries"][0]["sections"][0]["items"]
    assert items == [{
        "time": None, "headline": None,
        "components": ["Docs & process"], "text": "No headline on this one.",
    }]


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


# --- plans/dashboard.md #17 (fixed 2026-09-19) -------------------------
#
# _parse_item() used to be handed only a bullet's FIRST source line, with
# soft-wrapped continuation lines appended to ["text"] afterwards. So a
# **[Component]** tag only got parsed if it happened to fit on line one -
# pure luck, not a rule anyone follows when writing an entry. 3 of 92
# real CHANGELOG.md entries were affected, each rendering in the live
# Release Notes panel with no component badge and the raw markup showing
# as body text.

def test_a_component_tag_wrapped_onto_the_next_line_is_still_parsed(tmp_path):
    """The commonest shape: a long headline fills line one, pushing the
    component tag onto the continuation line."""
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Changed
- **4:27pm** — **A Headline Long Enough To Fill The Whole First Line**
  **[Docs & process]** The real body text follows here.
""")
    item = parse_changelog(path)["entries"][0]["sections"][0]["items"][0]
    assert item["headline"] == "A Headline Long Enough To Fill The Whole First Line"
    assert item["components"] == ["Docs & process"]
    assert item["text"] == "The real body text follows here."


def test_a_component_tag_split_mid_tag_across_lines_is_still_parsed(tmp_path):
    """The nastier shape, and a real one in this repo's own history: the
    wrap lands INSIDE the tag, so even joining-then-parsing only works
    because the join restores the single space."""
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Added
- **4:23pm** — **Another Real Headline** **[Docs &
  process]** Body text after a tag that was split across the wrap.
""")
    item = parse_changelog(path)["entries"][0]["sections"][0]["items"][0]
    assert item["headline"] == "Another Real Headline"
    assert item["components"] == ["Docs & process"]
    assert item["text"] == "Body text after a tag that was split across the wrap."


def test_an_escaped_asterisk_in_a_headline_does_not_break_parsing(tmp_path):
    """A real entry title ends `...Renamed to delivery-\\*` - the escaped
    asterisk sits immediately before the closing `**`, making `***`. The
    old regex consumed two of the three and left a stray `*` that then
    blocked the component match entirely. The backslash is a markdown
    escape, not content, so it's stripped from the parsed headline."""
    path = _write(tmp_path, r"""# Changelog

## 2026-01-01

### Changed
- **7:25pm** — **The 8 Subagents Renamed to delivery-\*** **[Docs & process]**
  Real body text here.
""")
    item = parse_changelog(path)["entries"][0]["sections"][0]["items"][0]
    assert item["headline"] == "The 8 Subagents Renamed to delivery-*"
    assert item["components"] == ["Docs & process"]
    assert item["text"] == "Real body text here."


def test_multiple_components_survive_a_wrap_between_them(tmp_path):
    """Several entries carry two tags; the wrap can land between them."""
    path = _write(tmp_path, """# Changelog

## 2026-01-01

### Fixed
- **1:00pm** — **Two Tags, One Wrap** **[Dashboard UI]**
  **[Testing & dev tooling]** Body text.
""")
    item = parse_changelog(path)["entries"][0]["sections"][0]["items"][0]
    assert item["components"] == ["Dashboard UI", "Testing & dev tooling"]
    assert item["text"] == "Body text."
