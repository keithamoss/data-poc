"""Tests for dashboard/plans_md.py - the plans/*.md parser (running-
thoughts.md #10). Fixture-based (small hand-written markdown strings per
test), not the real committed plans/*.md files - those change over time
and aren't what this module's own correctness depends on."""
from __future__ import annotations

from dashboard.plans_md import _parse_numbered_items, _parse_notes, _parse_threads, parse_plans


def test_parses_a_single_numbered_item_with_one_component(tmp_path):
    text = """1. **[done, 2026-09-18]** **[Dashboard UI]** A real feature shipped.
"""
    items = _parse_numbered_items(text, "wider")
    assert items == [{
        "file": "wider", "number": 1, "status": "done", "date": "2026-09-18",
        "components": ["Dashboard UI"], "section": None, "text": "A real feature shipped.",
    }]


def test_parses_multiple_components_on_one_item(tmp_path):
    text = "1. **[todo, 2026-09-18]** **[QA checks & contract]** **[Pipeline & publishing]** Two things.\n"
    items = _parse_numbered_items(text, "qa-pipeline")
    assert items[0]["components"] == ["QA checks & contract", "Pipeline & publishing"]


def test_joins_a_wrapped_paragraph_across_multiple_lines(tmp_path):
    text = """1. **[investigate, 2026-09-18]** **[Docs & process]** A long item that wraps
   across multiple lines in the markdown
   source, same paragraph.
"""
    items = _parse_numbered_items(text, "wider")
    assert items[0]["text"] == "A long item that wraps across multiple lines in the markdown source, same paragraph."


def test_preserves_paragraph_breaks_within_one_item(tmp_path):
    text = """1. **[done, 2026-09-18]** **[Dashboard UI]** First paragraph.

   Second paragraph, a separate thought.
"""
    items = _parse_numbered_items(text, "wider")
    assert items[0]["text"] == "First paragraph.\n\nSecond paragraph, a separate thought."


def test_preserves_a_bullet_list_within_one_item_as_its_own_lines(tmp_path):
    text = """1. **[done, 2026-09-18]** **[Dashboard UI]** Built:
   - first thing done
   - second thing done, wrapped
     across two lines
"""
    items = _parse_numbered_items(text, "wider")
    assert items[0]["text"] == (
        "Built:\n\n- first thing done\n- second thing done, wrapped across two lines"
    )


def test_parses_multiple_items_in_file_order(tmp_path):
    text = """1. **[done, 2026-09-18]** **[Dashboard UI]** First item.

2. **[todo, 2026-09-18]** **[Docs & process]** Second item.
"""
    items = _parse_numbered_items(text, "wider")
    assert [i["number"] for i in items] == [1, 2]
    assert [i["status"] for i in items] == ["done", "todo"]


def test_captures_the_nearest_preceding_section_heading(tmp_path):
    text = """## Found running the real tools

1. **[done, 2026-09-18]** **[QA checks & contract]** First item.

## Held over from the original build

7. **[old-format-not-a-real-status]** Untagged legacy item, skipped entirely.
"""
    items = _parse_numbered_items(text, "qa-pipeline")
    assert len(items) == 1
    assert items[0]["section"] == "Found running the real tools"


def test_an_item_in_the_old_untagged_format_is_silently_skipped(tmp_path):
    """Real content: qa-pipeline.md's own "Held over from the original
    (equivalent-only) build" section restarts its own numbering in the
    OLD, pre-retrofit tag format - this parser doesn't retrofit-match it,
    same "skip what doesn't match" philosophy as changelog_md.py's own
    optional fields."""
    text = "7. **[open]** An old-format item with no date/component tags.\n"
    assert _parse_numbered_items(text, "qa-pipeline") == []


def test_parses_a_tagged_thread_with_status_and_category(tmp_path):
    text = """## Thread A - resupply-chain modeling (2026-09-17)

**Status:** done (2026-09-17) · **Category:** QA checks & contract

**The tension.** Some real design prose here,
wrapped across two lines.

A second paragraph.
"""
    threads = _parse_threads(text, "conceptual-design")
    assert len(threads) == 1
    t = threads[0]
    assert t["heading"] == "Thread A - resupply-chain modeling (2026-09-17)"
    assert t["status"] == "done"
    assert t["date"] == "2026-09-17"
    assert t["category"] == "QA checks & contract"
    assert t["body"] == "**The tension.** Some real design prose here,\nwrapped across two lines.\n\nA second paragraph."


def test_a_heading_with_no_status_line_is_not_captured_as_a_thread(tmp_path):
    text = """## Doc updates needed once this starts landing

Just some prose, no Status/Category tag line under this heading at all.

## Thread B - a real tagged section

**Status:** parked (2026-09-16) · **Category:** Pipeline & publishing

Body.
"""
    threads = _parse_threads(text, "publishing-and-history")
    assert len(threads) == 1
    assert threads[0]["heading"] == "Thread B - a real tagged section"


def test_parses_multiple_threads_in_file_order(tmp_path):
    text = """## Thread B - first

**Status:** done (2026-09-16) · **Category:** Pipeline & publishing

First body.

## Thread A - second

**Status:** parked (2026-09-17) · **Category:** QA checks & contract

Second body.
"""
    threads = _parse_threads(text, "publishing-and-history")
    assert [t["heading"] for t in threads] == ["Thread B - first", "Thread A - second"]


def test_parses_a_numbered_note_with_title_and_body(tmp_path):
    text = """### 4. GitHub Issues -> Microsoft Teams integration (research first)

Some raw prose, no status/component tags at all - running-thoughts.md
keeps its own simpler shape by design.

Second paragraph.
"""
    notes = _parse_notes(text)
    assert len(notes) == 1
    assert notes[0]["number"] == 4
    assert notes[0]["title"] == "GitHub Issues -> Microsoft Teams integration (research first)"
    assert notes[0]["body"] == (
        "Some raw prose, no status/component tags at all - running-thoughts.md\n"
        "keeps its own simpler shape by design.\n\nSecond paragraph."
    )


def test_a_note_heading_with_no_leading_number_still_parses(tmp_path):
    text = "### Untitled idea with no number\n\nBody.\n"
    notes = _parse_notes(text)
    assert notes[0]["number"] is None
    assert notes[0]["title"] == "Untitled idea with no number"


def test_note_body_stops_at_the_next_two_hash_batch_heading(tmp_path):
    text = """### 1. First idea

Body of the first idea.

## Also flagged, queued separately

### 2. Second idea

Body of the second idea.
"""
    notes = _parse_notes(text)
    assert len(notes) == 2
    assert notes[0]["body"] == "Body of the first idea."
    assert notes[1]["body"] == "Body of the second idea."


def test_parse_plans_reads_all_files_and_returns_the_combined_shape(tmp_path):
    plans_dir = tmp_path
    (plans_dir / "wider.md").write_text("1. **[done, 2026-09-18]** **[Dashboard UI]** A wider item.\n")
    (plans_dir / "qa-pipeline.md").write_text("1. **[todo, 2026-09-18]** **[QA checks & contract]** A QA item.\n")
    (plans_dir / "dashboard.md").write_text("1. **[done, 2026-09-18]** **[Dashboard UI]** A dashboard item.\n")
    (plans_dir / "data-generation.md").write_text("1. **[parked, 2026-09-18]** **[Data generation]** A data-gen item.\n")
    (plans_dir / "publishing-and-history.md").write_text(
        "## Thread B - a thread\n\n**Status:** done (2026-09-16) · **Category:** Pipeline & publishing\n\nBody.\n"
    )
    (plans_dir / "conceptual-design.md").write_text(
        "## Thread A - a thread\n\n**Status:** parked (2026-09-17) · **Category:** QA checks & contract\n\nBody.\n"
    )
    (plans_dir / "running-thoughts.md").write_text("### 1. A raw idea\n\nBody.\n")

    result = parse_plans(plans_dir)
    assert len(result["items"]) == 4
    assert {i["file"] for i in result["items"]} == {"wider", "qa-pipeline", "dashboard", "data-generation"}
    assert len(result["threads"]) == 2
    assert {t["file"] for t in result["threads"]} == {"publishing-and-history", "conceptual-design"}
    assert len(result["notes"]) == 1
    assert result["notes"][0]["title"] == "A raw idea"
